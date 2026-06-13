"""Shared helpers for XML tree navigation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from app.core.dtd_models import AttributeDef

ElementPath = tuple[tuple[str, int], ...]
ProtectedAttrs = frozenset[tuple[ElementPath, str]]


def normalize_dot_path(path: str) -> str:
    """Strip UI-only group-N segments so tree paths match element paths."""
    return re.sub(r"\.group-\d+(?=\.|$)", "", path.strip())


def find_elements_by_dot_path(
    root: etree._Element,
    path: str,
) -> list[etree._Element]:
    """Resolve a dot-separated element path (e.g. PayDoc.Body.client) to XML nodes."""
    normalized = normalize_dot_path(path)
    if not normalized:
        return []

    segments = normalized.split(".")
    if root.tag != segments[0]:
        return []

    current: etree._Element = root
    for segment in segments[1:]:
        found: etree._Element | None = None
        for child in current:
            if child.tag == segment:
                found = child
                break
        if found is None:
            return []
        current = found

    return [current]


def element_path(el: etree._Element) -> ElementPath:
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


def is_fillable_attribute_value(
    value: str,
    *,
    attr_def: AttributeDef | None = None,
) -> bool:
    """True when a value is empty or still a builder placeholder worth replacing."""
    stripped = value.strip()
    if not stripped:
        return True
    if stripped == "id-1":
        return True
    if attr_def is None:
        return False
    if constrained := attr_def.dtd_default_value():
        return stripped == constrained
    if attr_def.attr_type == "ENUM" and attr_def.allowed_values:
        return stripped == attr_def.allowed_values[0]
    return False
