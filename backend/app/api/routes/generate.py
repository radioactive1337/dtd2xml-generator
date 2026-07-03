"""XML generation endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.dtd import get_schema_registry
from app.auth.sessions import get_current_user
from app.core.xml_builder import BuildConfig, BuildResult, build_xml
from app.user_context import UserContext

router = APIRouter(prefix="/generate", tags=["generate"])
logger = logging.getLogger(__name__)

# user_id -> schema_id -> xml_text
_last_generated: dict[str, dict[str, str]] = {}


def _user_cache(user: UserContext) -> dict[str, str]:
    if user.user_id not in _last_generated:
        _last_generated[user.user_id] = {}
    return _last_generated[user.user_id]


@router.post("", response_model=BuildResult)
async def generate_xml(
    config: BuildConfig,
    user: UserContext = Depends(get_current_user),
) -> BuildResult:
    registry = get_schema_registry(user)
    if config.schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{config.schema_id}' not found")

    schema = registry[config.schema_id]
    if config.root_element not in schema.elements:
        raise HTTPException(
            status_code=404,
            detail=f"Root element '{config.root_element}' not found",
        )

    try:
        result = await asyncio.to_thread(build_xml, schema, config)
    except ValueError as exc:
        logger.exception(
            "XML generation failed [schema_id=%s root=%s]",
            config.schema_id,
            config.root_element,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _user_cache(user)[config.schema_id] = result.xml_text
    return result


def get_last_generated(user: UserContext, schema_id: str) -> str | None:
    return _user_cache(user).get(schema_id)


def set_last_generated(user: UserContext, schema_id: str, xml_text: str) -> None:
    _user_cache(user)[schema_id] = xml_text
