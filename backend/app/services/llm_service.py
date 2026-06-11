"""OpenAI-compatible LLM service for XML data population."""

from __future__ import annotations

import os
import re

import httpx
from lxml import etree

from app.config import get_llm_api_key, load_connections
from app.core.dtd_models import DTDSchema

_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill in the provided XML skeleton with realistic Russian business test data. "
    "Preserve the exact XML structure, element names, and attribute names. "
    "Return only valid XML without markdown fences or explanations."
)

_HYBRID_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill ONLY empty attribute values and empty text nodes in the provided XML. "
    "Do NOT add, remove, or rename any elements or attributes. "
    "Do NOT change attributes or text that already contain values. "
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
    ) -> str:
        if not self.base_url:
            raise ValueError("LLM base URL is not configured in connections.json or .env")

        metadata = self._extract_metadata(schema, xml_text)
        if fill_empty_only:
            user_message = (
                "Fill ONLY the empty attribute values and empty text nodes. "
                "Leave every existing non-empty value unchanged. "
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
            return merge_fill_empty_only(xml_text, llm_xml)
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


def _element_path(el: etree._Element) -> tuple[tuple[str, int], ...]:
    """Indexed path from root to *el* (tag, sibling-index among same-tag children)."""
    parts: list[tuple[str, int]] = []
    current: etree._Element | None = el
    while current is not None and current.getparent() is not None:
        parent = current.getparent()
        assert parent is not None
        siblings = [child for child in parent if child.tag == current.tag]
        parts.append((current.tag, siblings.index(current)))
        current = parent
    parts.reverse()
    return tuple(parts)


def _build_path_map(root: etree._Element) -> dict[tuple[tuple[str, int], ...], etree._Element]:
    return {_element_path(el): el for el in root.iter()}


def merge_fill_empty_only(original_xml: str, filled_xml: str) -> str:
    """Keep the original tree; copy values from *filled_xml* only into empty slots."""
    original_root = etree.fromstring(original_xml.encode("utf-8"))
    filled_root = etree.fromstring(filled_xml.encode("utf-8"))
    filled_by_path = _build_path_map(filled_root)

    for el in original_root.iter():
        filled_el = filled_by_path.get(_element_path(el))
        if filled_el is None:
            continue
        for attr_name, attr_value in list(el.attrib.items()):
            if attr_value.strip():
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
) -> str:
    """Populate XML using the configured LLM service."""
    return await LLMService(alias=alias).populate_xml(
        xml_text,
        schema,
        fill_empty_only=fill_empty_only,
    )