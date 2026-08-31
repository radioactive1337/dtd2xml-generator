"""Shared helpers for XML tree navigation."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from app.core.dtd_models import DTDSchema

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
    if attr_def.attr_type == "ENUM" and len(attr_def.allowed_values) > 1:
        # Builder already sampled from the pool; any in-pool value is final.
        return False
    if constrained := attr_def.dtd_default_value():
        return stripped == constrained
    return False


def prefill_empty_enums(xml_text: str, schema: DTDSchema | None) -> tuple[str, int]:
    """Assign a random allowed value to every empty/placeholder ENUM attribute.

    Runs once before any fill strategy (DB / Git reference / LLM) so none of them
    have to special-case ENUM attributes that can only hold one of a fixed set of
    values — by the time they see the XML, ENUM attributes are already valid.
    """
    if schema is None:
        return xml_text, 0

    root = etree.fromstring(xml_text.encode("utf-8"))
    filled = 0
    for el in root.iter():
        elem_def = schema.elements.get(el.tag)
        if not elem_def:
            continue
        for attr_name, attr_value in list(el.attrib.items()):
            attr_def = elem_def.attributes.get(attr_name)
            if not attr_def or attr_def.attr_type != "ENUM" or not attr_def.allowed_values:
                continue
            if not is_fillable_attribute_value(attr_value, attr_def=attr_def):
                continue  # already has a valid in-pool value
            el.set(attr_name, random.choice(attr_def.allowed_values))
            filled += 1

    if filled == 0:
        return xml_text, 0
    return etree.tostring(root, encoding="unicode"), filled


MIN_GIT_PUSH_ATTRIBUTE_FILL_RATE = 0.15


@dataclass(frozen=True)
class AttributeFillStats:
    total: int
    filled: int

    @property
    def fill_rate(self) -> float:
        if self.total == 0:
            return 1.0
        return self.filled / self.total

    @property
    def fill_percent(self) -> float:
        return round(self.fill_rate * 100, 1)


def compute_attribute_fill_stats(
    xml_text: str,
    schema: DTDSchema | None = None,
) -> AttributeFillStats:
    """Count attribute occurrences in XML and how many have real (non-placeholder) values."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    total = 0
    filled = 0

    for el in root.iter():
        elem_def = schema.elements.get(el.tag) if schema else None
        for attr_name, attr_value in el.attrib.items():
            if attr_name == "xmlns" or attr_name.startswith("xmlns:"):
                continue
            total += 1
            attr_def = elem_def.attributes.get(attr_name) if elem_def else None
            if not is_fillable_attribute_value(attr_value, attr_def=attr_def):
                filled += 1

    return AttributeFillStats(total=total, filled=filled)


def git_push_attribute_fill_error(
    xml_text: str,
    schema: DTDSchema,
    *,
    min_fill_rate: float = MIN_GIT_PUSH_ATTRIBUTE_FILL_RATE,
) -> str | None:
    """Return a user-facing error when fill rate is below the Git push minimum."""
    stats = compute_attribute_fill_stats(xml_text, schema)
    if stats.fill_rate >= min_fill_rate:
        return None
    min_pct = round(min_fill_rate * 100)
    return (
        f"Недостаточно заполненных атрибутов для отправки в Git: "
        f"заполнено {stats.fill_percent}% ({stats.filled} из {stats.total}). "
        f"Минимум — {min_pct}%. Дозаполните документ перед отправкой."
    )
