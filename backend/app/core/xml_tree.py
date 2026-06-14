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


_ELEMENT_INDEX = re.compile(r"^(.+)\[(\d+)\]$")


def _parse_path_segment(segment: str) -> tuple[str, int | None]:
    match = _ELEMENT_INDEX.match(segment)
    if match:
        return match.group(1), int(match.group(2))
    return segment, None


def _child_by_tag_and_index(
    parent: etree._Element,
    tag: str,
    index: int | None,
) -> etree._Element | None:
    matches = [child for child in parent if child.tag == tag]
    if not matches:
        return None
    if index is not None:
        if index < 0 or index >= len(matches):
            return None
        return matches[index]
    if len(matches) == 1:
        return matches[0]
    return matches[0]


def find_elements_by_dot_path(
    root: etree._Element,
    path: str,
) -> list[etree._Element]:
    """Resolve a dot-separated element path to XML nodes.

    Supports sibling indices: ``PayDoc.client.contact[0]``, ``Body[1].client``.
    When multiple same-tag siblings exist and no index is given, the first match is used.
    """
    normalized = normalize_dot_path(path)
    if not normalized:
        return []

    segments = normalized.split(".")
    if root.tag != segments[0]:
        return []

    current: etree._Element = root
    for segment in segments[1:]:
        tag, index = _parse_path_segment(segment)
        found = _child_by_tag_and_index(current, tag, index)
        if found is None:
            return []
        current = found

    return [current]


def element_dot_path(el: etree._Element) -> str:
    """Dot-separated path from document root, with ``[index]`` for duplicate siblings."""
    chain: list[etree._Element] = []
    current: etree._Element | None = el
    while current is not None:
        chain.append(current)
        current = current.getparent()
    chain.reverse()

    segments: list[str] = []
    for index, node in enumerate(chain):
        tag = node.tag
        if index > 0:
            parent = chain[index - 1]
            siblings = [child for child in parent if child.tag == tag]
            if len(siblings) > 1:
                tag = f"{tag}[{siblings.index(node)}]"
        segments.append(tag)
    return ".".join(segments)


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
