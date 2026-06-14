"""OpenAI-compatible LLM service for XML data population."""

from __future__ import annotations

import asyncio
import json
import logging
import re
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

_FILL_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill the listed XML field paths with realistic Russian business test data. "
    "Return only valid JSON without markdown fences or explanations."
)

_FILL_JSON_FORMAT = (
    'Return JSON: {"values": [{"path": "...", "attrs": {"attr": "value"}, "text": "..."}]}\n'
    "Include only paths from the input list. Use exact attribute names from the input."
)

_HYBRID_FILL_NOTE = (
    "Only fill the listed empty or placeholder fields. "
    "Do not invent additional paths or attributes.\n\n"
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
    ) -> str:
        if not self.base_url:
            logger.error("LLM base URL is not configured")
            raise ValueError("LLM base URL is not configured in connections.json")

        tasks = collect_fill_tasks(
            xml_text,
            schema,
            fill_empty_only=fill_empty_only,
            protected_attrs=protected_attrs,
        )
        if not tasks:
            logger.debug("LLM populate skipped: no fillable fields")
            return xml_text

        metadata = self._extract_metadata_for_tasks(schema, tasks)
        tasks_json = json.dumps(tasks, ensure_ascii=False, separators=(",", ":"))
        prefix = _HYBRID_FILL_NOTE if fill_empty_only else ""
        user_message = (
            f"{prefix}Fill the following XML fields with realistic test data.\n\n"
            f"{_FILL_JSON_FORMAT}\n"
            f"Schema metadata (JavaDoc-style comments):\n{metadata}\n\n"
            f"Fields to fill:\n{tasks_json}"
        )

        logger.debug(
            "LLM populate request [tasks=%d prompt_chars=%d fill_empty_only=%s]",
            len(tasks),
            len(user_message),
            fill_empty_only,
        )

        content = await self._chat_completion(
            system_prompt=_FILL_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.7,
        )
        data = self._extract_json(content)
        values = data.get("values", [])
        if not isinstance(values, list):
            raise ValueError("LLM response JSON must contain a values array")
        return apply_llm_values(
            xml_text,
            values,
            fill_empty_only=fill_empty_only,
            protected_attrs=protected_attrs,
        )

    def _extract_metadata_for_tasks(self, schema: DTDSchema, tasks: list[dict[str, Any]]) -> str:
        element_names: set[str] = set()
        for task in tasks:
            for segment in task["path"].split("."):
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


def collect_fill_tasks(
    xml_text: str,
    schema: DTDSchema,
    *,
    fill_empty_only: bool = False,
    protected_attrs: ProtectedAttrs = frozenset(),
) -> list[dict[str, Any]]:
    """Build a compact list of XML fields that need LLM-generated values."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    tasks: list[dict[str, Any]] = []

    for el in root.iter():
        elem_def = schema.elements.get(el.tag)
        dot_path = element_dot_path(el)
        tree_path = element_path(el)

        attrs_to_fill: dict[str, str] = {}
        for attr_name, attr_value in el.attrib.items():
            if (tree_path, attr_name) in protected_attrs:
                continue
            attr_def = elem_def.attributes.get(attr_name) if elem_def else None
            if fill_empty_only:
                if is_fillable_attribute_value(attr_value, attr_def=attr_def):
                    attrs_to_fill[attr_name] = attr_value
            else:
                attrs_to_fill[attr_name] = attr_value

        text_to_fill: str | None = None
        if elem_def and elem_def.content_model.kind == "PCDATA":
            if fill_empty_only:
                if not (el.text or "").strip():
                    text_to_fill = ""
            else:
                text_to_fill = el.text or ""

        if attrs_to_fill or text_to_fill is not None:
            task: dict[str, Any] = {"path": dot_path}
            if attrs_to_fill:
                task["attrs"] = attrs_to_fill
            if text_to_fill is not None:
                task["text"] = text_to_fill
            tasks.append(task)

    return tasks


def apply_llm_values(
    original_xml: str,
    values: list[dict[str, Any]],
    *,
    fill_empty_only: bool = False,
    protected_attrs: ProtectedAttrs = frozenset(),
) -> str:
    """Apply LLM JSON field values onto the original XML tree."""
    original_root = etree.fromstring(original_xml.encode("utf-8"))
    by_dot_path = {element_dot_path(el): el for el in original_root.iter()}

    for item in values:
        if not isinstance(item, dict):
            continue
        dot_path = item.get("path")
        if not isinstance(dot_path, str) or not dot_path:
            continue

        el = by_dot_path.get(dot_path)
        if el is None:
            found = find_elements_by_dot_path(original_root, dot_path)
            el = found[0] if found else None
        if el is None:
            continue

        tree_path = element_path(el)

        attrs = item.get("attrs")
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

        if "text" in item:
            new_text = item["text"]
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
) -> str:
    """Populate XML using the configured LLM service."""
    return await LLMService(alias=alias).populate_xml(
        xml_text,
        schema,
        fill_empty_only=fill_empty_only,
        protected_attrs=protected_attrs,
    )
