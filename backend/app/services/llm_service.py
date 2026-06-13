"""OpenAI-compatible LLM service for XML data population."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from lxml import etree

from app.config import get_llm_api_key, load_connections
from app.core.dtd_models import DTDSchema
from app.core.logging_config import truncate
from app.core.xml_tree import ProtectedAttrs, element_path, is_fillable_attribute_value

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill in the provided XML skeleton with realistic Russian business test data. "
    "Preserve the exact XML structure, element names, and attribute names. "
    "Return only valid XML without markdown fences or explanations."
)

_HYBRID_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill attribute values and text nodes that are empty or contain placeholder values "
    "(e.g. id-1, empty strings). "
    "Do NOT change attributes that already contain real database values. "
    "Do NOT add, remove, or rename any elements or attributes. "
    "Preserve the exact XML structure, element order, and nesting. "
    "Return only valid XML without markdown fences or explanations."
)

_FIELD_MAPPING_SYSTEM_PROMPT = (
    "You match SQL result column names to XML element attribute names. "
    "Use semantic meaning, naming conventions (snake_case, kebab-case, prefixes), "
    "and any provided documentation. "
    "Return only valid JSON without markdown fences or explanations."
)


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
        connections = load_connections()
        llm_cfg = connections.llm.get(alias)

        self.base_url = (base_url or (llm_cfg.base_url if llm_cfg else "") or "").rstrip("/")
        self.model = model or (llm_cfg.model if llm_cfg else "gpt-4o-mini")
        self.api_key = api_key or get_llm_api_key(alias)
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

        metadata = self._extract_metadata(schema, xml_text)
        if fill_empty_only:
            user_message = (
                "Fill attribute values and text nodes that are empty or still contain "
                "builder placeholders (e.g. id-1). "
                "Leave database-filled values unchanged. "
                "Do not add or remove any elements.\n\n"
                f"Schema metadata (JavaDoc-style comments):\n{metadata}\n\n"
                f"XML skeleton:\n{xml_text}"
            )
            system_prompt = _HYBRID_SYSTEM_PROMPT
        else:
            user_message = (
                "Fill the following XML skeleton with realistic test data.\n\n"
                f"Schema metadata (JavaDoc-style comments):\n{metadata}\n\n"
                f"XML skeleton:\n{xml_text}"
            )
            system_prompt = _SYSTEM_PROMPT

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
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
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.error(
                "Unexpected LLM response shape [model=%s keys=%s]",
                self.model,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            raise ValueError("LLM response did not contain a message") from exc

        llm_xml = self._extract_xml(content)
        if fill_empty_only:
            return merge_fill_empty_only(xml_text, llm_xml, protected_attrs=protected_attrs)
        return llm_xml

    def _extract_metadata(self, schema: DTDSchema, xml_text: str) -> str:
        lines: list[str] = []
        for elem in schema.elements.values():
            if f"<{elem.name}" in xml_text or f"</{elem.name}>" in xml_text:
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

    def _extract_xml(self, content: str) -> str:
        content = content.strip()
        fence_match = re.search(r"```(?:xml)?\s*([\s\S]*?)```", content, re.IGNORECASE)
        if fence_match:
            return fence_match.group(1).strip()
        if content.startswith("<?xml") or content.startswith("<"):
            return content
        logger.error(
            "LLM response did not contain valid XML [preview=%s]",
            truncate(content, max_len=300),
        )
        raise ValueError("LLM response did not contain valid XML")

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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
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