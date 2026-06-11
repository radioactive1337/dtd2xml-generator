"""OpenAI-compatible LLM service for XML data population."""

from __future__ import annotations

import os
import re

import httpx
from lxml import etree

from app.config import get_llm_api_key, load_connections
from app.core.dtd_models import DTDSchema
from app.core.xml_tree import ProtectedAttrs, element_path

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

        self.base_url = (base_url or (llm_cfg.base_url if llm_cfg else None) or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or (llm_cfg.model if llm_cfg else None) or os.getenv("LLM_MODEL", "gpt-4o-mini")
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
            raise ValueError("LLM base URL is not configured in connections.json or .env")

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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
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
        raise ValueError("LLM response did not contain valid XML")


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
        for attr_name in set(el.attrib) | set(filled_el.attrib):
            if (path, attr_name) in protected_attrs:
                continue
            original_value = el.attrib.get(attr_name, "")
            should_fill = not original_value.strip() or bool(protected_attrs)
            if not should_fill:
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