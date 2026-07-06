"""Export a flattened DTD from a parsed DTDSchema for libxml2 validation."""

from __future__ import annotations

import re

from app.core.dtd_models import AttributeDef, DTDSchema, ElementDef

_PARAM_REF_RE = re.compile(r"%([a-zA-Z][-a-zA-Z0-9_.]*);")


def dtd_local_name(name: str) -> str:
    """Map DTD qualified names like cs:add-object to the local XML name."""
    if ":" in name:
        return name.split(":", 1)[1]
    return name


def normalize_dtd_name_in_fragment(text: str) -> str:
    """Replace qualified DTD names in content models with local names."""

    def replacer(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.upper() in {"EMPTY", "ANY", "#PCDATA"}:
            return token
        return dtd_local_name(token)

    return re.sub(r"[A-Za-z][-A-Za-z0-9_:.]*", replacer, text)


def _resolve_param_refs(text: str, param_entities: dict[str, str]) -> str:
    """Replace %entity; references using collected parameter entities."""

    def replacer(match: re.Match[str]) -> str:
        name = match.group(1)
        return param_entities.get(name, match.group(0))

    resolved = _PARAM_REF_RE.sub(replacer, text)
    if resolved != text:
        return _resolve_param_refs(resolved, param_entities)
    return resolved


def _format_attr_type(attr: AttributeDef, param_entities: dict[str, str]) -> str:
    if attr.attr_type == "ENUM" and attr.allowed_values:
        return "(" + "|".join(attr.allowed_values) + ")"

    attr_type = _resolve_param_refs(attr.attr_type, param_entities)
    if attr_type.startswith("%"):
        raise ValueError(f"Unresolved parameter entity in attribute '{attr.name}': {attr.attr_type}")
    return attr_type


def _format_element_def(
    elem: ElementDef,
    param_entities: dict[str, str],
) -> list[str]:
    content_raw = _resolve_param_refs(elem.content_raw, param_entities)
    if "%" in content_raw:
        raise ValueError(
            f"Unresolved parameter entity in element '{elem.name}': {elem.content_raw}"
        )
    content_raw = normalize_dtd_name_in_fragment(content_raw)
    local_name = dtd_local_name(elem.name)
    lines = [f"<!ELEMENT {local_name} {content_raw}>"]

    if not elem.attributes:
        return lines

    attr_lines: list[str] = []
    for name, attr in elem.attributes.items():
        attr_type = _format_attr_type(attr, param_entities)
        default_decl = _resolve_param_refs(attr.default_decl, param_entities)
        attr_lines.append(f"    {dtd_local_name(name)} {attr_type} {default_decl}")

    lines.append(f"<!ATTLIST {local_name}\n" + "\n".join(attr_lines) + "\n>")
    return lines


def export_flat_dtd(schema: DTDSchema) -> str:
    """Reconstruct a parameter-entity-free DTD from a parsed schema."""
    lines: list[str] = []
    param_entities = schema.param_entities
    exported: set[str] = set()

    for elem in schema.elements.values():
        local_name = dtd_local_name(elem.name)
        if local_name in exported:
            continue
        exported.add(local_name)
        lines.extend(_format_element_def(elem, param_entities))

    return "\n".join(lines)
