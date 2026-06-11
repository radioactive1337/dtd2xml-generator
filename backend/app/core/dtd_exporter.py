"""Export a flattened DTD from a parsed DTDSchema for libxml2 validation."""

from __future__ import annotations

import re

from app.core.dtd_models import AttributeDef, DTDSchema

_PARAM_REF_RE = re.compile(r"%([a-zA-Z][-a-zA-Z0-9_.]*);")


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


def export_flat_dtd(schema: DTDSchema) -> str:
    """Reconstruct a parameter-entity-free DTD from a parsed schema."""
    lines: list[str] = []
    param_entities = schema.param_entities

    for elem in schema.elements.values():
        content_raw = _resolve_param_refs(elem.content_raw, param_entities)
        if "%" in content_raw:
            raise ValueError(
                f"Unresolved parameter entity in element '{elem.name}': {elem.content_raw}"
            )
        lines.append(f"<!ELEMENT {elem.name} {content_raw}>")

        if not elem.attributes:
            continue

        attr_lines: list[str] = []
        for name, attr in elem.attributes.items():
            attr_type = _format_attr_type(attr, param_entities)
            default_decl = _resolve_param_refs(attr.default_decl, param_entities)
            attr_lines.append(f"    {name} {attr_type} {default_decl}")

        lines.append(f"<!ATTLIST {elem.name}\n" + "\n".join(attr_lines) + "\n>")

    return "\n".join(lines)
