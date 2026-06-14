"""OpenAI-compatible LLM service for XML data population."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from lxml import etree

from app.config import get_llm_api_key, load_connections, resolve_llm_alias
from app.core.dtd_models import DTDSchema
from app.core.logging_config import truncate
from app.core.xml_tree import (
    ProtectedAttrs,
    element_dot_path,
    element_path,
    find_elements_by_dot_path,
    is_fillable_attribute_value,
)

logger = logging.getLogger(__name__)

_LLM_BATCH_SIZE = 12
_LLM_MAX_CONCURRENT = 4

LlmProgressCallback = Callable[[str, str, int], Awaitable[None]]

_FILL_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill the provided XML skeleton with realistic Russian business test data. "
    "Preserve the exact element structure, indices, paths, and attribute names. "
    "Return only valid XML without markdown fences or explanations."
)

_FILL_XML_NOTE = (
    "Each <f> element has i (index) and p (path). "
    "Fill empty attributes and text. Do not add or remove elements.\n\n"
)

_FIELD_MAPPING_SYSTEM_PROMPT = (
    "You match SQL result column names to XML element attribute names. "
    "Use semantic meaning, naming conventions (snake_case, kebab-case, prefixes), "
    "and any provided documentation. "
    "Return only valid JSON without markdown fences or explanations."
)

_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client with connection pooling."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client

    async with _http_client_lock:
        if _http_client is not None and not _http_client.is_closed:
            return _http_client
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        return _http_client


async def close_llm_http_client() -> None:
    """Close the shared LLM HTTP client. Called on application shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


class LLMService:
    """Populate XML using an OpenAI-compatible chat completion API."""

    def __init__(
        self,
        alias: str = "default",
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.alias = resolve_llm_alias(alias)
        connections = load_connections()
        llm_cfg = connections.llm.get(self.alias)

        self.base_url = (base_url or (llm_cfg.base_url if llm_cfg else "") or "").rstrip("/")
        self.model = model or (llm_cfg.model if llm_cfg else "gpt-4o-mini")
        self.api_key = api_key or get_llm_api_key(self.alias)
        self.timeout = timeout

    async def populate_xml(
        self,
        xml_text: str,
        schema: DTDSchema,
        *,
        fill_empty_only: bool = False,
        protected_attrs: ProtectedAttrs = frozenset(),
        on_progress: LlmProgressCallback | None = None,
        progress_base: int = 15,
        progress_span: int = 70,
    ) -> str:
        if not self.base_url:
            logger.error("LLM base URL is not configured")
            raise ValueError("LLM base URL is not configured in connections.json")

        tasks = await asyncio.to_thread(
            collect_fill_tasks,
            xml_text,
            schema,
            fill_empty_only=fill_empty_only,
            protected_attrs=protected_attrs,
        )
        if not tasks:
            logger.debug("LLM populate skipped: no fillable fields")
            return xml_text

        metadata = self._extract_metadata_for_tasks(schema, tasks)
        batches = [
            tasks[index : index + _LLM_BATCH_SIZE]
            for index in range(0, len(tasks), _LLM_BATCH_SIZE)
        ]
        logger.info(
            "LLM populate [tasks=%d batches=%d fill_empty_only=%s]",
            len(tasks),
            len(batches),
            fill_empty_only,
        )

        if on_progress:
            await on_progress(
                "llm_prepare",
                f"Preparing {len(tasks)} fields in {len(batches)} batches",
                progress_base,
            )

        semaphore = asyncio.Semaphore(_LLM_MAX_CONCURRENT)
        completed_batches = 0
        batch_lock = asyncio.Lock()

        async def fill_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
            nonlocal completed_batches
            async with semaphore:
                result = await self._fill_tasks_batch(
                    batch,
                    metadata=metadata,
                    fill_empty_only=fill_empty_only,
                )
            async with batch_lock:
                completed_batches += 1
                if on_progress:
                    percent = progress_base + int(
                        (completed_batches / len(batches)) * progress_span
                    )
                    await on_progress(
                        "llm_batch",
                        f"LLM batch {completed_batches}/{len(batches)}",
                        min(percent, progress_base + progress_span),
                    )
            return result

        batch_results = await asyncio.gather(
            *(fill_batch(batch) for batch in batches),
            return_exceptions=True,
        )

        all_values: list[dict[str, Any]] = []
        for index, result in enumerate(batch_results):
            if isinstance(result, BaseException):
                logger.error("LLM batch %d failed: %s", index, result)
                raise ValueError(f"LLM batch {index + 1} failed: {result}") from result
            all_values.extend(result)

        return apply_llm_values(
            xml_text,
            all_values,
            tasks=tasks,
            fill_empty_only=fill_empty_only,
            protected_attrs=protected_attrs,
        )

    async def _fill_tasks_batch(
        self,
        batch: list[dict[str, Any]],
        *,
        metadata: str,
        fill_empty_only: bool,
    ) -> list[dict[str, Any]]:
        skeleton = build_batch_xml_skeleton(batch)
        prefix = (
            "Only fill empty or placeholder attribute values. "
            "Leave other attributes unchanged.\n\n"
            if fill_empty_only
            else ""
        )
        user_message = (
            f"{prefix}{_FILL_XML_NOTE}"
            f"Schema metadata (JavaDoc-style comments):\n{metadata}\n\n"
            f"XML skeleton:\n{skeleton}"
        )

        logger.debug(
            "LLM batch request [tasks=%d prompt_chars=%d]",
            len(batch),
            len(user_message),
        )

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                content = await self._chat_completion(
                    system_prompt=_FILL_SYSTEM_PROMPT,
                    user_message=user_message,
                    temperature=0.4 if attempt else 0.5,
                )
                return parse_batch_xml_response(content, batch)
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "LLM batch parse failed [attempt=%d tasks=%d]: %s",
                    attempt + 1,
                    len(batch),
                    exc,
                )
                if attempt == 0:
                    user_message += (
                        "\n\nIMPORTANT: Return only the filled XML skeleton, "
                        "no markdown and no explanations."
                    )

        assert last_error is not None
        raise last_error

    def _extract_metadata_for_tasks(self, schema: DTDSchema, tasks: list[dict[str, Any]]) -> str:
        element_names: set[str] = set()
        for task in tasks:
            for segment in task["p"].split("."):
                element_names.add(re.sub(r"\[\d+\]", "", segment))

        lines: list[str] = []
        for elem in schema.elements.values():
            if elem.name not in element_names:
                continue
            if elem.doc:
                lines.append(f"@doc {elem.name}: {elem.doc}")
            for attr_name, attr in elem.attributes.items():
                if attr.doc:
                    lines.append(f"@att {elem.name}.{attr_name}: {attr.doc}")
                if attr.allowed_values:
                    lines.append(
                        f"@enum {elem.name}.{attr_name}: {', '.join(attr.allowed_values)}"
                    )
        return "\n".join(lines) if lines else "(no metadata)"

    async def suggest_field_mappings_json(
        self,
        *,
        target_element: str,
        element_doc: str,
        columns: list[str],
        attributes: list[dict[str, Any]],
        existing_pairs: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Ask the LLM to map SQL columns to XML attributes."""
        if not self.base_url:
            raise ValueError("LLM base URL is not configured in connections.json")

        attr_lines = []
        for attr in attributes:
            line = f"- {attr['name']}"
            if attr.get("doc"):
                line += f": {attr['doc']}"
            if attr.get("allowed_values"):
                line += f" (allowed: {', '.join(attr['allowed_values'])})"
            attr_lines.append(line)

        existing_lines = [
            f"- {pair['db_col']} -> {pair['xml_attr']}"
            for pair in existing_pairs
            if pair.get("db_col") and pair.get("xml_attr")
        ]

        user_message = (
            f"Target XML element: {target_element}\n"
            f"Element documentation: {element_doc or '(none)'}\n\n"
            f"SQL columns to map (return one mapping per column, exact names):\n"
            + "\n".join(f"- {col}" for col in columns)
            + "\n\nAvailable XML attributes (use only these exact names):\n"
            + ("\n".join(attr_lines) if attr_lines else "(none)")
            + "\n\nAlready mapped pairs (do not reuse these columns or attributes):\n"
            + ("\n".join(existing_lines) if existing_lines else "(none)")
            + '\n\nReturn JSON: {"mappings": [{"db_col": "...", "xml_attr": "..."}]}\n'
            "Use only db_col values from the SQL columns list above — do not invent columns. "
            "Use an empty string for xml_attr when there is no confident match."
        )

        content = await self._chat_completion(
            system_prompt=_FIELD_MAPPING_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.2,
        )
        data = self._extract_json(content)
        mappings = data.get("mappings", [])
        if not isinstance(mappings, list):
            raise ValueError("LLM response JSON must contain a mappings array")
        return mappings

    async def _chat_completion(
        self,
        *,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"
        try:
            client = await _get_http_client()
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            body = truncate(exc.response.text, max_len=500)
            logger.error(
                "LLM API HTTP error [model=%s url=%s status=%s]: %s",
                self.model,
                url,
                exc.response.status_code,
                body,
            )
            raise ValueError(
                f"LLM API returned HTTP {exc.response.status_code}: {body}"
            ) from exc
        except httpx.RequestError as exc:
            logger.exception(
                "LLM request failed [model=%s url=%s timeout=%s]",
                self.model,
                url,
                self.timeout,
            )
            raise ValueError(f"LLM request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.error(
                "Unexpected LLM response shape [model=%s keys=%s]",
                self.model,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            raise ValueError("LLM response did not contain a message") from exc

    def _extract_json(self, content: str) -> dict[str, Any]:
        content = content.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content, re.IGNORECASE)
        if fence_match:
            content = fence_match.group(1).strip()
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error(
                "LLM response did not contain valid JSON [preview=%s]",
                truncate(content, max_len=300),
            )
            raise ValueError("LLM response did not contain valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("LLM response JSON must be an object")
        return data

    async def test_connection(self) -> str:
        """Verify that the configured LLM endpoint is reachable."""
        if not self.base_url:
            logger.error("LLM base URL is not configured")
            raise ValueError("LLM base URL is not configured in connections.json")

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/models"
        try:
            client = await _get_http_client()
            response = await client.get(url, headers=headers, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = truncate(exc.response.text, max_len=300)
            logger.error(
                "LLM connection test HTTP error [model=%s url=%s status=%s]: %s",
                self.model,
                url,
                exc.response.status_code,
                body,
            )
            raise ValueError(
                f"LLM API returned HTTP {exc.response.status_code}: {body}"
            ) from exc
        except httpx.RequestError as exc:
            logger.exception(
                "LLM connection test failed [model=%s url=%s]",
                self.model,
                url,
            )
            raise ValueError(f"LLM request failed: {exc}") from exc

        return f"Reachable (model: {self.model})"

def _extract_xml(content: str) -> str:
    content = content.strip()
    fence_match = re.search(r"```(?:xml)?\s*([\s\S]*?)```", content, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    start = content.find("<")
    if start >= 0:
        return content[start:].strip()
    logger.error(
        "LLM response did not contain valid XML [preview=%s]",
        truncate(content, max_len=300),
    )
    raise ValueError("LLM response did not contain valid XML")


def build_batch_xml_skeleton(batch: list[dict[str, Any]]) -> str:
    """Build a compact XML batch skeleton for LLM fill requests."""
    lines = ["<fill>"]
    for task in batch:
        index = task["i"]
        path = task["p"]
        attr_names: list[str] = task.get("a", [])
        needs_text = bool(task.get("t"))
        attrs = [f'i="{index}"', f'p="{path}"']
        for name in attr_names:
            attrs.append(f'{name}=""')
        attr_str = " ".join(attrs)
        if needs_text:
            lines.append(f"  <f {attr_str}></f>")
        else:
            lines.append(f"  <f {attr_str}/>")
    lines.append("</fill>")
    return "\n".join(lines)


def parse_batch_xml_response(content: str, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse filled batch XML from the LLM into value records."""
    xml_text = _extract_xml(content)
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise ValueError("LLM response did not contain valid XML") from exc

    allowed_indexes = {task["i"] for task in batch}
    attr_names_by_index = {
        task["i"]: set(task.get("a", []))
        for task in batch
    }
    values: list[dict[str, Any]] = []

    for node in root.iter("f"):
        index_raw = node.get("i")
        if index_raw is None:
            continue
        try:
            index = int(index_raw)
        except ValueError:
            continue
        if index not in allowed_indexes:
            continue

        item: dict[str, Any] = {"i": index}
        allowed_attrs = attr_names_by_index.get(index, set())
        filled_attrs = {
            name: value
            for name, value in node.attrib.items()
            if name not in {"i", "p"} and name in allowed_attrs and value.strip()
        }
        if filled_attrs:
            item["a"] = filled_attrs
        if (node.text or "").strip():
            item["t"] = node.text.strip()
        if len(item) > 1:
            values.append(item)

    if not values:
        raise ValueError("LLM response did not contain any filled field values")
    return values


def collect_fill_tasks(
    xml_text: str,
    schema: DTDSchema,
    *,
    fill_empty_only: bool = False,
    protected_attrs: ProtectedAttrs = frozenset(),
) -> list[dict[str, Any]]:
    """Build a compact indexed list of XML fields that need LLM-generated values."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    tasks: list[dict[str, Any]] = []

    for el in root.iter():
        elem_def = schema.elements.get(el.tag)
        dot_path = element_dot_path(el)
        tree_path = element_path(el)

        attr_names: list[str] = []
        for attr_name, attr_value in el.attrib.items():
            if (tree_path, attr_name) in protected_attrs:
                continue
            attr_def = elem_def.attributes.get(attr_name) if elem_def else None
            if fill_empty_only:
                if is_fillable_attribute_value(attr_value, attr_def=attr_def):
                    attr_names.append(attr_name)
            else:
                attr_names.append(attr_name)

        needs_text = False
        if not attr_names and elem_def and elem_def.content_model.kind == "PCDATA" and len(el) == 0:
            if fill_empty_only:
                needs_text = not (el.text or "").strip()
            else:
                needs_text = True

        if attr_names or needs_text:
            task: dict[str, Any] = {
                "i": len(tasks),
                "p": dot_path,
            }
            if attr_names:
                task["a"] = attr_names
            if needs_text:
                task["t"] = 1
            tasks.append(task)

    return tasks


def _normalize_llm_value_item(
    item: dict[str, Any],
    *,
    tasks: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    dot_path = item.get("path") or item.get("p")
    attrs = item.get("attrs") or item.get("a")
    text = item.get("text")
    if text is None and "t" in item:
        text = item["t"]

    if not dot_path and "i" in item and tasks is not None:
        index = item["i"]
        matched = next((task for task in tasks if task["i"] == index), None)
        if matched is None:
            return None
        dot_path = matched["p"]

    if not isinstance(dot_path, str) or not dot_path:
        return None

    normalized: dict[str, Any] = {"path": dot_path}
    if isinstance(attrs, dict):
        normalized["attrs"] = attrs
    if text is not None:
        normalized["text"] = text
    return normalized


def apply_llm_values(
    original_xml: str,
    values: list[dict[str, Any]],
    *,
    tasks: list[dict[str, Any]] | None = None,
    fill_empty_only: bool = False,
    protected_attrs: ProtectedAttrs = frozenset(),
) -> str:
    """Apply LLM JSON field values onto the original XML tree."""
    original_root = etree.fromstring(original_xml.encode("utf-8"))
    by_dot_path = {element_dot_path(el): el for el in original_root.iter()}

    for item in values:
        normalized = _normalize_llm_value_item(item, tasks=tasks)
        if normalized is None:
            continue

        dot_path = normalized["path"]
        el = by_dot_path.get(dot_path)
        if el is None:
            found = find_elements_by_dot_path(original_root, dot_path)
            el = found[0] if found else None
        if el is None:
            continue

        tree_path = element_path(el)

        attrs = normalized.get("attrs")
        if isinstance(attrs, dict):
            for attr_name, new_value in attrs.items():
                if (tree_path, attr_name) in protected_attrs:
                    continue
                if attr_name not in el.attrib:
                    continue
                if fill_empty_only and not is_fillable_attribute_value(el.attrib[attr_name]):
                    continue
                if new_value is not None and str(new_value).strip():
                    el.set(attr_name, str(new_value))

        if "text" in normalized:
            new_text = normalized["text"]
            if new_text is not None and str(new_text).strip():
                if fill_empty_only and (el.text or "").strip():
                    continue
                el.text = str(new_text)

    return etree.tostring(
        original_root,
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=False,
    ).decode("UTF-8")


def _build_path_map(root: etree._Element) -> dict[tuple[tuple[str, int], ...], etree._Element]:
    return {element_path(el): el for el in root.iter()}


def merge_fill_empty_only(
    original_xml: str,
    filled_xml: str,
    *,
    protected_attrs: ProtectedAttrs = frozenset(),
) -> str:
    """Keep the original tree; copy values from *filled_xml* for non-DB attributes."""
    original_root = etree.fromstring(original_xml.encode("utf-8"))
    filled_root = etree.fromstring(filled_xml.encode("utf-8"))
    filled_by_path = _build_path_map(filled_root)

    for el in original_root.iter():
        path = element_path(el)
        filled_el = filled_by_path.get(path)
        if filled_el is None:
            continue
        for attr_name in el.attrib:
            if (path, attr_name) in protected_attrs:
                continue
            original_value = el.attrib[attr_name]
            if not is_fillable_attribute_value(original_value):
                continue
            filled_value = filled_el.attrib.get(attr_name)
            if filled_value is not None and filled_value.strip():
                el.set(attr_name, filled_value)
        if not (el.text or "").strip() and (filled_el.text or "").strip():
            el.text = filled_el.text

    return etree.tostring(
        original_root,
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=False,
    ).decode("UTF-8")


async def populate_with_llm(
    xml_text: str,
    schema: DTDSchema,
    alias: str = "default",
    *,
    fill_empty_only: bool = False,
    protected_attrs: ProtectedAttrs = frozenset(),
    on_progress: LlmProgressCallback | None = None,
    progress_base: int = 15,
    progress_span: int = 70,
) -> str:
    """Populate XML using the configured LLM service."""
    return await LLMService(alias=alias).populate_xml(
        xml_text,
        schema,
        fill_empty_only=fill_empty_only,
        protected_attrs=protected_attrs,
        on_progress=on_progress,
        progress_base=progress_base,
        progress_span=progress_span,
    )
