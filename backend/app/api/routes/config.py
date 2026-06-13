"""Connection configuration and health-check endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.db_service import DBService
from app.services.llm_service import LLMService
from app.config import set_default_llm_alias

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)


class AliasRequest(BaseModel):
    alias: str


class ConnectionTestResponse(BaseModel):
    alias: str
    ok: bool
    message: str


class DefaultLlmRequest(BaseModel):
    alias: str


class DefaultLlmResponse(BaseModel):
    default_llm: str


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


@router.put("/default-llm", response_model=DefaultLlmResponse)
async def set_default_llm(request: DefaultLlmRequest) -> DefaultLlmResponse:
    """Set the default LLM alias in connections.json."""
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="LLM alias is required")

    try:
        default_llm = set_default_llm_alias(alias)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DefaultLlmResponse(default_llm=default_llm)
