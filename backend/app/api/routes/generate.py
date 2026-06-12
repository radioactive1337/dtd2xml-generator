"""XML generation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.routes.dtd import get_schema_registry
from app.core.xml_builder import BuildConfig, BuildResult, build_xml

router = APIRouter(prefix="/generate", tags=["generate"])
logger = logging.getLogger(__name__)

# In-memory cache of last generated XML per schema
_last_generated: dict[str, str] = {}


@router.post("", response_model=BuildResult)
async def generate_xml(config: BuildConfig) -> BuildResult:
    """Generate XML skeleton from a registered DTD schema."""
    registry = get_schema_registry()
    if config.schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{config.schema_id}' not found")

    schema = registry[config.schema_id]
    if config.root_element not in schema.elements:
        raise HTTPException(
            status_code=404,
            detail=f"Root element '{config.root_element}' not found",
        )

    try:
        result = build_xml(schema, config)
    except ValueError as exc:
        logger.exception(
            "XML generation failed [schema_id=%s root=%s]",
            config.schema_id,
            config.root_element,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _last_generated[config.schema_id] = result.xml_text
    return result


def get_last_generated(schema_id: str) -> str | None:
    """Return the last generated XML for a schema."""
    return _last_generated.get(schema_id)
