"""Structural comparison of an XML document against reference documents.

The structural signature of a document is the set of element paths (tag chains
from the root, without indices or namespaces). Comparing signatures makes the
comparison semantic: attribute order, whitespace, and values are ignored — only
the element structure matters.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from lxml import etree

from app.core.xml_tree import structural_element_path


class XmlParseError(ValueError):
    """Raised when the provided XML text cannot be parsed."""


@dataclass(frozen=True)
class ReferenceDoc:
    """A reference document to compare the current XML against."""

    category: str
    doc_id: str
    title: str
    xml_text: str


def _local_name(tag: str) -> str:
    """Strip an optional ``{namespace}`` prefix from an lxml tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse(xml_text: str) -> etree._Element:
    if not xml_text or not xml_text.strip():
        raise XmlParseError("XML is empty")
    try:
        return etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise XmlParseError(str(exc)) from exc


def _element_path(element: etree._Element) -> str:
    """Build the structural path (``Root/child/grandchild``) for an element."""
    return structural_element_path(element)


# How many distinct reference values the compare tab receives per attribute.
_REFERENCE_VALUE_PREVIEW = 8


def _is_xmlns(name: str) -> bool:
    return name == "xmlns" or name.startswith("xmlns:")


def _attribute_counts(root: etree._Element) -> dict[tuple[str, str], Counter[str]]:
    """Non-empty attribute values keyed by ``(structural path, attr)``."""
    counts: dict[tuple[str, str], Counter[str]] = {}
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        path = _element_path(element)
        for name, raw in element.attrib.items():
            if _is_xmlns(name):
                continue
            value = (raw or "").strip()
            if not value:
                continue
            counts.setdefault((path, name), Counter())[value] += 1
    return counts


def _current_attributes(root: etree._Element) -> dict[tuple[str, str], dict]:
    """Attributes present on the current document, including empty ones."""
    found: dict[tuple[str, str], dict] = {}
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        path = _element_path(element)
        line = element.sourceline or None
        for name, raw in element.attrib.items():
            if _is_xmlns(name):
                continue
            key = (path, name)
            slot = found.get(key)
            if slot is None:
                slot = {"values": set(), "line": line}
                found[key] = slot
            elif slot["line"] is None and line:
                slot["line"] = line
            value = (raw or "").strip()
            if value:
                slot["values"].add(value)
    return found


def _attribute_value_report(
    current_root: etree._Element,
    ref_counts: dict[tuple[str, str], Counter[str]],
    *,
    skip_attr: Callable[[str], bool] | None,
    has_references: bool,
) -> list[dict]:
    """Catalog of reference values for attributes that exist in the current XML.

    The preview is capped. ``matches_references`` is computed from the full
    sets: an empty current value is not treated as a mismatch.
    """
    if not has_references:
        return []
    rows: list[dict] = []
    for (path, attr), info in sorted(_current_attributes(current_root).items()):
        if skip_attr is not None and skip_attr(attr):
            continue
        current_values: set[str] = info["values"]
        counts = ref_counts.get((path, attr), Counter())
        if not counts and not current_values:
            continue
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        missing = sorted(value for value in current_values if value not in counts)
        matched = sorted(value for value in current_values if value in counts)
        rows.append(
            {
                "path": path,
                "attr": attr,
                "reference_values": [value for value, _count in ranked[:_REFERENCE_VALUE_PREVIEW]],
                "reference_total": len(ranked),
                "current_values": (missing + matched)[:_REFERENCE_VALUE_PREVIEW],
                "current_total": len(current_values),
                "matches_references": not missing,
                "line": info["line"],
            }
        )
    return rows


def _extract_paths_from_root(root: etree._Element) -> set[str]:
    paths: set[str] = set()
    for element in root.iter():
        if isinstance(element.tag, str):
            paths.add(_element_path(element))
    return paths


def peek_root_element(xml_text: str) -> str:
    """Return the local name of the root element (namespace stripped)."""
    root = _parse(xml_text)
    if not isinstance(root.tag, str):
        raise XmlParseError("XML has no element root")
    return _local_name(root.tag)


def extract_paths(xml_text: str) -> set[str]:
    """Return the set of structural element paths of the document."""
    return _extract_paths_from_root(_parse(xml_text))


def _compute_highlight_ranges_from_root(
    root: etree._Element, unique: set[str]
) -> list[dict]:
    if not unique:
        return []
    ranges: list[dict] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        path = _element_path(element)
        if path not in unique:
            continue
        parent = element.getparent()
        parent_path = _element_path(parent) if parent is not None else ""
        if parent_path in unique:
            continue

        start = element.sourceline
        if not start:
            continue
        end = start
        for descendant in element.iter():
            line = descendant.sourceline
            if line and line > end:
                end = line
        ranges.append({"start_line": start, "end_line": end, "path": path})

    ranges.sort(key=lambda r: r["start_line"])
    return ranges


def _compute_highlight_targets_from_root(
    root: etree._Element, unique: set[str]
) -> list[dict]:
    if not unique:
        return []
    targets: list[dict] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        path = _element_path(element)
        if path not in unique:
            continue
        line = element.sourceline
        if not line:
            continue
        targets.append({"line": line, "path": path, "tag": _local_name(element.tag)})
    return targets


def compute_highlight_ranges(
    xml_text: str, unique_paths: set[str] | list[str]
) -> list[dict]:
    """Return line ranges of the top-most unique subtrees for highlighting.

    An element is a "top-most divergence point" when its path is unique but its
    parent path is not. For each such element we return the line range of its
    whole subtree ``[sourceline .. max descendant sourceline]`` so the entire new
    block gets highlighted.
    """
    return _compute_highlight_ranges_from_root(_parse(xml_text), set(unique_paths))


def compute_highlight_targets(
    xml_text: str, unique_paths: set[str] | list[str]
) -> list[dict]:
    """Return per-element highlight targets for every unique element.

    Unlike :func:`compute_highlight_ranges` (which returns line ranges of the
    top-most divergence subtrees), this returns one entry per unique element
    occurrence — its ``line`` (``sourceline``) and ``tag`` — so the editor can
    highlight only the element's tag instead of whole lines.
    """
    return _compute_highlight_targets_from_root(_parse(xml_text), set(unique_paths))


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return round(len(a & b) / len(union), 4)


def compare_structure(
    xml_text: str,
    references: Iterable[ReferenceDoc],
    *,
    skip_attr: Callable[[str], bool] | None = None,
) -> dict:
    """Compare the current XML structure against every reference document.

    Returns a report with the unique paths (present in the current document but
    in none of the references), highlight line ranges, per-reference similarity
    scores and the closest reference.

    ``references`` may be a generator — each document is processed and released
    immediately, so the full reference corpus never lives in memory at once.
    Only the closest reference's path set is retained.
    """
    # Parse the current document exactly once and reuse the tree for all
    # subsequent operations (highlight ranges, targets, snippets).
    current_root = _parse(xml_text)
    if not isinstance(current_root.tag, str):
        raise XmlParseError("XML has no element root")
    root_element = _local_name(current_root.tag)
    current_paths = _extract_paths_from_root(current_root)

    union_paths: set[str] = set()
    similarities: list[dict] = []
    ref_counts: dict[tuple[str, str], Counter[str]] = {}

    # Track only the best reference's paths to avoid keeping all path sets
    # in memory simultaneously.
    best_score = -1.0
    closest_ref_paths: set[str] = set()

    for ref in references:
        try:
            ref_root = _parse(ref.xml_text)
        except XmlParseError:
            continue  # skip unparseable references
        ref_paths = _extract_paths_from_root(ref_root)
        for key, counter in _attribute_counts(ref_root).items():
            ref_counts.setdefault(key, Counter()).update(counter)
        union_paths |= ref_paths
        score = _jaccard(current_paths, ref_paths)
        similarities.append(
            {
                "category": ref.category,
                "doc_id": ref.doc_id,
                "title": ref.title,
                "score": score,
            }
        )
        if score > best_score:
            best_score = score
            closest_ref_paths = ref_paths

    similarities.sort(key=lambda s: s["score"], reverse=True)
    unique_paths = sorted(current_paths - union_paths)
    unique_set = set(unique_paths)

    highlight_ranges = _compute_highlight_ranges_from_root(current_root, unique_set)
    highlight_targets = _compute_highlight_targets_from_root(current_root, unique_set)
    snippets = _extract_snippets_from_root(current_root, unique_set)
    closest = similarities[0] if similarities else None
    closest_paths = sorted(closest_ref_paths) if closest else []
    has_references = bool(similarities)

    return {
        "root_element": root_element,
        "references_count": len(similarities),
        "has_references": has_references,
        "is_unique": bool(unique_paths),
        "unique_paths": unique_paths,
        "highlight_ranges": highlight_ranges,
        "highlight_targets": highlight_targets,
        "snippets": snippets,
        "similarities": similarities,
        "closest": closest,
        "closest_paths": closest_paths,
        "attribute_values": _attribute_value_report(
            current_root,
            ref_counts,
            skip_attr=skip_attr,
            has_references=has_references,
        ),
    }


def _extract_snippets_from_root(
    root: etree._Element, unique: set[str], *, max_length: int = 600
) -> list[dict]:
    if not unique:
        return []
    snippets: list[dict] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        path = _element_path(element)
        if path not in unique:
            continue
        parent = element.getparent()
        parent_path = _element_path(parent) if parent is not None else ""
        if parent_path in unique:
            continue

        raw = etree.tostring(element, encoding="unicode", pretty_print=True).strip()
        if len(raw) > max_length:
            raw = raw[:max_length].rstrip() + "\n…"
        snippets.append({"path": path, "xml": raw})

    return snippets


def extract_snippets(
    xml_text: str, unique_paths: set[str] | list[str], *, max_length: int = 600
) -> list[dict]:
    """Return short serialized XML fragments of top-most unique elements.

    Used to give the LLM concrete context. Each snippet is truncated to
    ``max_length`` characters.
    """
    return _extract_snippets_from_root(_parse(xml_text), set(unique_paths), max_length=max_length)
