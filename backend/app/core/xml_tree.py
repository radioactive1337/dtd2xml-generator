"""Shared helpers for XML tree navigation."""

from __future__ import annotations

from lxml import etree

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
