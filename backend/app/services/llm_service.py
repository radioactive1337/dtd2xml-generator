"""OpenAI-compatible LLM service for XML data population."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.config import get_llm_api_key, load_connections
from app.core.dtd_models import DTDSchema

_SYSTEM_PROMPT = (
    "You are a test data generator for QA automation. "
    "Fill in the provided XML skeleton with realistic Russian business test data. "
    "Preserve the exact XML structure, element names, and attribute names. "
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

    async def populate_xml(self, xml_text: str, schema: DTDSchema) -> str:
        if not self.base_url:
            raise ValueError("LLM base URL is not configured in connections.json or .env")

        metadata = self._extract_metadata(schema)
        user_message = (
            "Fill the following XML skeleton with realistic test data.\n\n"
            f"Schema metadata (JavaDoc-style comments):\n{metadata}\n\n"
            f"XML skeleton:\n{xml_text}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
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
        return self._extract_xml(content)

    def _extract_metadata(self, schema: DTDSchema) -> str:
        lines: list[str] = []
        for elem in schema.elements.values():
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


async def populate_with_llm(
    xml_text: str,
    schema: DTDSchema,
    alias: str = "default",
) -> str:
    """Populate XML using the configured LLM service."""
    return await LLMService(alias=alias).populate_xml(xml_text, schema)
