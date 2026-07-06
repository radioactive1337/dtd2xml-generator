"""Create lxml elements from DTD qualified element names."""

from __future__ import annotations

from lxml import etree

from app.core.dtd_exporter import dtd_local_name
from app.core.dtd_models import DTDSchema, ElementDef


def split_dtd_qualified_name(name: str) -> tuple[str | None, str]:
    if ":" in name:
        prefix, local = name.split(":", 1)
        return prefix, local
    return None, name


def fixed_xmlns_uri(elem_def: ElementDef, prefix: str) -> str | None:
    attr = elem_def.attributes.get(f"xmlns:{prefix}")
    if attr is None:
        return None
    return attr.dtd_default_value()


def schema_prefix_uri(schema: DTDSchema, prefix: str) -> str | None:
    for name, elem_def in schema.elements.items():
        if not name.startswith(f"{prefix}:"):
            continue
        uri = fixed_xmlns_uri(elem_def, prefix)
        if uri:
            return uri
    return None


def resolve_namespace_uri(
    schema: DTDSchema,
    elem_name: str,
    elem_def: ElementDef | None,
    parent: etree._Element | None,
) -> tuple[str | None, str, str | None]:
    """Return (namespace_uri, local_name, preferred_prefix)."""
    prefix, local = split_dtd_qualified_name(elem_name)
    if prefix is None:
        return None, local, None

    uri: str | None = None
    if elem_def is not None:
        uri = fixed_xmlns_uri(elem_def, prefix)
    if uri is None and parent is not None:
        parent_map = parent.nsmap or {}
        uri = parent_map.get(prefix)
        if uri is None:
            expected = schema_prefix_uri(schema, prefix)
            if expected:
                for candidate in parent_map.values():
                    if candidate == expected:
                        uri = expected
                        break
    if uri is None:
        uri = schema_prefix_uri(schema, prefix)
    return uri, local, prefix


def create_element_for_dtd_name(
    schema: DTDSchema,
    parent: etree._Element | None,
    elem_name: str,
    elem_def: ElementDef | None = None,
) -> etree._Element:
    """Build a namespaced XML element for a DTD name like cs:add-object."""
    uri, local, prefix = resolve_namespace_uri(schema, elem_name, elem_def, parent)

    if parent is None:
        if uri and prefix:
            return etree.Element(f"{{{uri}}}{local}", nsmap={prefix: uri})
        return etree.Element(local)
    if uri:
        kwargs = {"nsmap": {prefix: uri}} if prefix else {}
        return etree.SubElement(parent, f"{{{uri}}}{local}", **kwargs)
    return etree.SubElement(parent, local)


def schema_element_name(schema: DTDSchema, tag: str) -> str | None:
    """Map an lxml element tag back to a DTD schema element name."""
    if tag in schema.elements:
        return tag
    if not tag.startswith("{"):
        return None

    qname = etree.QName(tag)
    local = qname.localname
    uri = qname.namespace

    matches: list[str] = []
    for name in schema.elements:
        if dtd_local_name(name) != local:
            continue
        prefix, _ = split_dtd_qualified_name(name)
        if prefix is None:
            if uri is None:
                matches.append(name)
            continue
        elem_def = schema.elements[name]
        fixed_uri = fixed_xmlns_uri(elem_def, prefix)
        if fixed_uri == uri:
            matches.append(name)

    if len(matches) == 1:
        return matches[0]
    return None
