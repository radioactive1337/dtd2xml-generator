"""Shared helpers for XML tree navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from app.core.dtd_models import AttributeDef

ElementPath = tuple[tuple[str, int], ...]
ProtectedAttrs = frozenset[tuple[ElementPath, str]]


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
