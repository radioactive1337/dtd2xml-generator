"""Structural comparison of an XML document against reference documents.

The structural signature of a document is the set of element paths (tag chains
from the root, without indices or namespaces). Comparing signatures makes the
comparison semantic: attribute order, whitespace, and values are ignored — only
the element structure matters.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree


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
    parts: list[str] = []
    current: etree._Element | None = element
    while current is not None:
        if isinstance(current.tag, str):
            parts.append(_local_name(current.tag))
        current = current.getparent()
    parts.reverse()
    return "/".join(parts)


def peek_root_element(xml_text: str) -> str:
    """Return the local name of the root element (namespace stripped)."""
    root = _parse(xml_text)
    if not isinstance(root.tag, str):
        raise XmlParseError("XML has no element root")
    return _local_name(root.tag)


def extract_paths(xml_text: str) -> set[str]:
    """Return the set of structural element paths of the document."""
    root = _parse(xml_text)
    paths: set[str] = set()
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue  # skip comments / processing instructions
        paths.add(_element_path(element))
    return paths


def compute_highlight_ranges(
    xml_text: str, unique_paths: set[str] | list[str]
) -> list[dict]:
    """Return line ranges of the top-most unique subtrees for highlighting.

    An element is a "top-most divergence point" when its path is unique but its
    parent path is not. For each such element we return the line range of its
    whole subtree ``[sourceline .. max descendant sourceline]`` so the entire new
    block gets highlighted.
    """
    unique = set(unique_paths)
    if not unique:
        return []

    root = _parse(xml_text)
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
            continue  # not a top-most divergence point

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


def compute_highlight_targets(
    xml_text: str, unique_paths: set[str] | list[str]
) -> list[dict]:
    """Return per-element highlight targets for every unique element.

    Unlike :func:`compute_highlight_ranges` (which returns line ranges of the
    top-most divergence subtrees), this returns one entry per unique element
    occurrence — its ``line`` (``sourceline``) and ``tag`` — so the editor can
    highlight only the element's tag instead of whole lines.
    """
    unique = set(unique_paths)
    if not unique:
        return []

    root = _parse(xml_text)
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
        targets.append(
            {"line": line, "path": path, "tag": _local_name(element.tag)}
        )
    return targets


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return round(len(a & b) / len(union), 4)


def compare_structure(
    xml_text: str, references: list[ReferenceDoc]
) -> dict:
    """Compare the current XML structure against every reference document.

    Returns a report with the unique paths (present in the current document but
    in none of the references), highlight line ranges, per-reference similarity
    scores and the closest reference.
    """
    current_paths = extract_paths(xml_text)
    root_element = peek_root_element(xml_text)

    union_paths: set[str] = set()
    similarities: list[dict] = []
    for ref in references:
        try:
            ref_paths = extract_paths(ref.xml_text)
        except XmlParseError:
            continue  # skip unparseable references
        union_paths |= ref_paths
        similarities.append(
            {
                "category": ref.category,
                "doc_id": ref.doc_id,
                "title": ref.title,
                "score": _jaccard(current_paths, ref_paths),
            }
        )

    similarities.sort(key=lambda s: s["score"], reverse=True)
    unique_paths = sorted(current_paths - union_paths)
    highlight_ranges = compute_highlight_ranges(xml_text, unique_paths)
    highlight_targets = compute_highlight_targets(xml_text, unique_paths)
    snippets = extract_snippets(xml_text, unique_paths)
    closest = similarities[0] if similarities else None

    return {
        "root_element": root_element,
        "references_count": len(similarities),
        "has_references": bool(similarities),
        "is_unique": bool(unique_paths),
        "unique_paths": unique_paths,
        "highlight_ranges": highlight_ranges,
        "highlight_targets": highlight_targets,
        "snippets": snippets,
        "similarities": similarities,
        "closest": closest,
    }


def extract_snippets(
    xml_text: str, unique_paths: set[str] | list[str], *, max_length: int = 600
) -> list[dict]:
    """Return short serialized XML fragments of top-most unique elements.

    Used to give the LLM concrete context. Each snippet is truncated to
    ``max_length`` characters.
    """
    unique = set(unique_paths)
    if not unique:
        return []

    root = _parse(xml_text)
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
