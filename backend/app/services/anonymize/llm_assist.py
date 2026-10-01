"""Optional LLM helpers for anonymization.

The LLM never rewrites the XML. It only answers two narrow questions and the
engine validates every answer:

* **entities** -- "which substrings of this free text are personal data?"
  (the engine checks each returned substring really occurs in the text and
  replaces it itself, consistently with the rest of the document);
* **categories** -- "which category does this field belong to?" given element
  and attribute names, the DTD doc string and, optionally, a sample value.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.services.anonymize.categories import CATEGORIES, CATEGORY_IDS
from app.services.llm_concurrency import llm_semaphore
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

_ENTITY_BATCH_ITEMS = 12
_ENTITY_BATCH_CHARS = 6000
_CATEGORY_BATCH_ITEMS = 40
_MAX_ENTITIES_PER_TEXT = 40

_ENTITY_TYPE_TO_CATEGORY = {
    "person": "person_full",
    "org": "org_name",
    "organization": "org_name",
    "address": "address_full",
    "phone": "phone",
    "email": "email",
    "id": "format_preserving",
    "birth_date": "birth_date",
}

_ENTITY_SYSTEM_PROMPT = (
    "Ты помогаешь обезличивать данные в тестовых XML-документах. "
    "Для каждого пронумерованного текста найди персональные и идентифицирующие данные: "
    "ФИО людей (type=person), названия организаций и банков (type=org), "
    "адреса (type=address), телефоны (type=phone), email (type=email), "
    "номера документов, счетов, ИНН, СНИЛС и подобные идентификаторы (type=id), "
    "даты рождения (type=birth_date). "
    "Поле text каждой найденной сущности должно быть ТОЧНОЙ подстрокой исходного текста, "
    "без изменений регистра, склонения и пробелов. Не выдумывай и не исправляй текст. "
    "Если в тексте нет персональных данных, верни пустой список entities. "
    'Верни только JSON вида {"items":[{"i":0,"entities":[{"text":"...","type":"person"}]}]} '
    "без markdown и пояснений."
)

_CATEGORY_SYSTEM_PROMPT = (
    "Ты классифицируешь поля XML-документов банковской/клиентской системы по типу "
    "персональных данных. Для каждого поля выбери ОДНУ категорию из списка либо none, "
    "если поле не содержит персональных данных (флаги, перечисления, технические коды, "
    "валюты, статусы). Используй имена элементов и атрибутов, описание из DTD и пример "
    "значения, если он дан. Верни только JSON вида "
    '{"suggestions":[{"key":"...","category":"inn"}]} без markdown и пояснений.'
)


def _chunk_texts(texts: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for text in texts:
        if current and (len(current) >= _ENTITY_BATCH_ITEMS or size + len(text) > _ENTITY_BATCH_CHARS):
            batches.append(current)
            current, size = [], 0
        current.append(text)
        size += len(text)
    if current:
        batches.append(current)
    return batches


async def _ask(llm: LLMService, system_prompt: str, user_message: str) -> dict[str, Any]:
    async with llm_semaphore:
        content = await llm.complete_text(
            system_prompt=system_prompt, user_message=user_message, temperature=0.0
        )
    return llm._extract_json(content)  # noqa: SLF001 - shared JSON-fence parser


def parse_entities(data: dict[str, Any], batch: list[str]) -> list[tuple[str, str]]:
    """Validate an LLM entity answer against the batch texts."""
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("LLM response must contain an 'items' array")
    found: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("i")
        if not isinstance(idx, int) or not 0 <= idx < len(batch):
            continue
        source = batch[idx]
        entities = item.get("entities")
        if not isinstance(entities, list):
            continue
        for entity in entities[:_MAX_ENTITIES_PER_TEXT]:
            if not isinstance(entity, dict):
                continue
            text = entity.get("text")
            category = _ENTITY_TYPE_TO_CATEGORY.get(str(entity.get("type", "")).strip().lower())
            if not isinstance(text, str) or category is None:
                continue
            text = text.strip()
            # The model may not invent text: it must literally occur in the source.
            if len(text) < 3 or text not in source:
                continue
            found.append((text, category))
    return found


async def find_entities(llm: LLMService, texts: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Ask the LLM for personal-data substrings. Returns ``(entities, warnings)``."""
    unique = list(dict.fromkeys(t for t in texts if t and t.strip()))
    if not unique:
        return [], []
    batches = _chunk_texts(unique)

    async def run(batch: list[str]) -> list[tuple[str, str]]:
        numbered = "\n".join(f"[{i}] {text}" for i, text in enumerate(batch))
        data = await _ask(llm, _ENTITY_SYSTEM_PROMPT, f"Тексты:\n{numbered}")
        return parse_entities(data, batch)

    results = await asyncio.gather(*(run(b) for b in batches), return_exceptions=True)
    entities: list[tuple[str, str]] = []
    warnings: list[str] = []
    for index, result in enumerate(results):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            logger.warning("Anonymize LLM entity batch %d failed: %s", index + 1, type(result).__name__)
            warnings.append(f"ИИ не обработал пакет текстов {index + 1}/{len(batches)}: {result}")
            continue
        entities.extend(result)
    return list(dict.fromkeys(entities)), warnings


def _category_catalog() -> str:
    return "\n".join(f"- {c.id}: {c.label}" for c in CATEGORIES if c.id != "free_text") + (
        "\n- free_text: поле со свободным текстом, где могут встретиться ПДн"
        "\n- none: не персональные данные"
    )


def parse_suggestions(data: dict[str, Any], allowed_keys: set[str]) -> dict[str, str | None]:
    raw = data.get("suggestions")
    if not isinstance(raw, list):
        raise ValueError("LLM response must contain a 'suggestions' array")
    out: dict[str, str | None] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        category = item.get("category")
        if not isinstance(key, str) or key not in allowed_keys or not isinstance(category, str):
            continue
        category = category.strip()
        if category == "none":
            out[key] = None
        elif category in CATEGORY_IDS:
            out[key] = category
    return out


async def suggest_categories(
    llm: LLMService,
    items: list[dict[str, Any]],
    *,
    include_samples: bool = False,
) -> tuple[dict[str, str | None], list[str]]:
    """Classify fields. *items*: ``{key, element, attr, name?, doc?, sample?}``.

    Returns ``({key: category | None}, warnings)``; ``None`` means "not PII".
    Samples are sent only when *include_samples* is true.
    """
    batches = [items[i : i + _CATEGORY_BATCH_ITEMS] for i in range(0, len(items), _CATEGORY_BATCH_ITEMS)]

    async def run(batch: list[dict[str, Any]]) -> dict[str, str | None]:
        lines: list[str] = []
        for item in batch:
            payload = {
                "key": item["key"],
                "element": item.get("element", ""),
                "attr": item.get("attr", ""),
            }
            if item.get("name"):
                payload["name"] = item["name"]
            if item.get("doc"):
                payload["doc"] = str(item["doc"])[:300]
            if include_samples and item.get("sample"):
                payload["sample"] = str(item["sample"])[:80]
            lines.append(json.dumps(payload, ensure_ascii=False))
        message = f"Категории:\n{_category_catalog()}\n\nПоля (по одному JSON на строку):\n" + "\n".join(lines)
        data = await _ask(llm, _CATEGORY_SYSTEM_PROMPT, message)
        return parse_suggestions(data, {i["key"] for i in batch})

    results = await asyncio.gather(*(run(b) for b in batches), return_exceptions=True)
    merged: dict[str, str | None] = {}
    warnings: list[str] = []
    for index, result in enumerate(results):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            logger.warning("Anonymize LLM category batch %d failed: %s", index + 1, type(result).__name__)
            warnings.append(f"ИИ не обработал пакет полей {index + 1}/{len(batches)}: {result}")
            continue
        merged.update(result)
    return merged, warnings
