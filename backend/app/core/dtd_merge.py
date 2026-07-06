"""Merge multiple parsed DTD schemas into one validation view."""

from __future__ import annotations

from app.core.dtd_models import DTDSchema


def merge_dtd_schemas(schemas: list[DTDSchema]) -> DTDSchema:
    """Combine elements and parameter entities from several loaded DTD entry points."""
    if not schemas:
        raise ValueError("At least one schema is required")
    if len(schemas) == 1:
        return schemas[0]

    merged_elements: dict = {}
    merged_params: dict[str, str] = {}
    merged_sources: list[str] = []
    seen_sources: set[str] = set()

    for schema in schemas:
        merged_params.update(schema.param_entities)
        merged_elements.update(schema.elements)
        for source in schema.source_files:
            if source not in seen_sources:
                seen_sources.add(source)
                merged_sources.append(source)

    return DTDSchema(
        elements=merged_elements,
        param_entities=merged_params,
        source_files=merged_sources,
    )
