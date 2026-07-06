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


def normalize_xml_for_dtd_validation(root: etree._Element) -> etree._Element:
    """Return a namespace-free tree with local element and attribute names."""

    def clone(element: etree._Element) -> etree._Element:
        node = etree.Element(_local_name(element.tag))

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
