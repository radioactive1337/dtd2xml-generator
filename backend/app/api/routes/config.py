"""Connection configuration and health-check endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.db_service import DBService
from app.services.llm_service import LLMService

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)


class AliasRequest(BaseModel):
    alias: str


class ConnectionTestResponse(BaseModel):
    alias: str
    ok: bool
    message: str


@router.post("/test-db", response_model=ConnectionTestResponse)
async def test_db_connection(request: AliasRequest) -> ConnectionTestResponse:
    """Check whether a configured database alias is reachable."""
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="Database alias is required")

    try:
        message = await DBService().test_connection(alias)
    except ValueError as exc:
        logger.warning("Database connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))
    except Exception as exc:
        logger.error("Database connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))

    return ConnectionTestResponse(alias=alias, ok=True, message=message)


@router.post("/test-llm", response_model=ConnectionTestResponse)
async def test_llm_connection(request: AliasRequest) -> ConnectionTestResponse:
    """Check whether a configured LLM alias is reachable."""
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="LLM alias is required")

    try:
        message = await LLMService(alias=alias).test_connection()
    except ValueError as exc:
        logger.warning("LLM connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))
    except Exception as exc:
        logger.error("LLM connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))

    return ConnectionTestResponse(alias=alias, ok=True, message=message)
