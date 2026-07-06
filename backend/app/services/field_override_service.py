"""Manual fixed-value overrides for XML attributes during fill."""

from __future__ import annotations

import logging

from lxml import etree
from pydantic import BaseModel

from app.core.xml_tree import ProtectedAttrs, element_path, find_elements_by_dot_path

logger = logging.getLogger(__name__)


class FieldOverride(BaseModel):
    """Fixed attribute value at a specific element path."""

    target_path: str
    xml_attr: str
    value: str
    target_element: str | None = None


def apply_field_overrides(
    xml_text: str,
    field_overrides: list[FieldOverride],
) -> tuple[str, ProtectedAttrs, list[str]]:
    """Apply manual overrides after DB stage; values win over Faker/LLM."""
    active = [
        override
        for override in field_overrides
        if override.target_path.strip() and override.xml_attr.strip()
    ]
    if not active:
        return xml_text, frozenset(), []

    root = etree.fromstring(xml_text.encode("utf-8"))
    protected: set[tuple[tuple[tuple[str, int], ...], str]] = set()
    warnings: list[str] = []

    for override in active:
        path = override.target_path.strip()
        attr_name = override.xml_attr.lstrip("@").strip()
        if not attr_name:
            continue

        elements = find_elements_by_dot_path(root, path)
        if not elements:
            msg = f"field override path not found: {path} (attr={attr_name})"
            logger.warning(msg)
            warnings.append(msg)
            continue

        for el in elements:
            el.set(attr_name, override.value)
            protected.add((element_path(el), attr_name))

    xml_out = etree.tostring(
        root,
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=False,
    ).decode("UTF-8")
    return xml_out, frozenset(protected), warnings
