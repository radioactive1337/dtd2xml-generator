"""Normalize namespaced XML for DTD validation."""

from __future__ import annotations

from lxml import etree

_XMLNS_URI = "http://www.w3.org/2000/xmlns/"


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return etree.QName(tag).localname
    return tag


def _is_namespace_attr(name: str) -> bool:
    return name == "xmlns" or name.startswith("xmlns:") or name.startswith(f"{{{_XMLNS_URI}}}")


def _own_nsmap(element: etree._Element) -> dict[str | None, str]:
    """Namespace declarations introduced on this element (not inherited)."""
    parent = element.getparent()
    parent_map = dict(parent.nsmap) if parent is not None else {}
    current_map = dict(element.nsmap or {})
    own: dict[str | None, str] = {}
    for prefix, uri in current_map.items():
        if parent_map.get(prefix) != uri:
            own[prefix] = uri
    return own


def normalize_xml_for_dtd_validation(root: etree._Element) -> etree._Element:
    """Return a tree with local element names while preserving declared xmlns bindings."""

    def clone(element: etree._Element) -> etree._Element:
        own_nsmap = _own_nsmap(element)
        node = etree.Element(_local_name(element.tag), nsmap=own_nsmap or None)

        for key, value in element.attrib.items():
            if _is_namespace_attr(key):
                continue
            node.set(_local_name(key), value)

        node.text = element.text
        for child in element:
            cloned_child = clone(child)
            cloned_child.tail = child.tail
            node.append(cloned_child)
        return node

    return clone(root)
