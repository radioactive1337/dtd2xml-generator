"""Connection configuration and health-check endpoints."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.sessions import get_current_user
from app.config import (
    DatabaseConfig,
    LLMConfig,
    get_connection_aliases,
    load_connections,
    save_user_connections_raw,
    set_default_llm_alias,
    _load_raw_user_connections,
)
from app.services.db_service import DBService
from app.services.llm_service import LLMService
from app.user_context import UserContext

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)

_ALIAS_RE = re.compile(r"^[\w\-.]+$")


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


class DatabaseCreateRequest(BaseModel):
    alias: str
    driver: str
    host: str
    port: int
    database: str
    user: str
    password: str
    sid: str | None = None


class DatabaseUpdateRequest(BaseModel):
    driver: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    password: str | None = None
    sid: str | None = None


class LlmCreateRequest(BaseModel):
    alias: str
    base_url: str
    api_key: str = ""
    model: str
    timeout: float = 120.0


class LlmUpdateRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float | None = None


class DatabaseAliasResponse(BaseModel):
    alias: str
    driver: str
    host: str
    port: int
    database: str
    user: str
    sid: str | None = None


class LlmAliasResponse(BaseModel):
    alias: str
    base_url: str
    model: str
    timeout: float


class ConnectionsResponse(BaseModel):
    databases: list[DatabaseAliasResponse]
    llm: list[LlmAliasResponse]
    default_llm: str | None = None


def _validate_alias(alias: str) -> str:
    name = alias.strip()
    if not name or not _ALIAS_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid alias name")
    if ".." in name:
        raise HTTPException(status_code=400, detail="Invalid alias name")
    return name


@router.get("/connections", response_model=ConnectionsResponse)
async def get_connections(
    user: UserContext = Depends(get_current_user),
) -> ConnectionsResponse:
    connections = load_connections(user)
    aliases = get_connection_aliases(user)
    return ConnectionsResponse(
        databases=[
            DatabaseAliasResponse(
                alias=cfg.alias,
                driver=cfg.driver,
                host=cfg.host,
                port=cfg.port,
                database=cfg.database,
                user=cfg.user,
                sid=cfg.sid,
            )
            for cfg in connections.databases.values()
        ],
        llm=[
            LlmAliasResponse(
                alias=cfg.alias,
                base_url=cfg.base_url,
                model=cfg.model,
                timeout=cfg.timeout,
            )
            for cfg in connections.llm.values()
        ],
        default_llm=aliases.get("default_llm"),  # type: ignore[arg-type]
    )


@router.get("/aliases")
async def config_aliases(
    user: UserContext = Depends(get_current_user),
) -> dict[str, list[str] | str | None]:
    return get_connection_aliases(user)


@router.post("/databases", response_model=DatabaseAliasResponse)
async def create_database_alias(
    body: DatabaseCreateRequest,
    user: UserContext = Depends(get_current_user),
) -> DatabaseAliasResponse:
    alias = _validate_alias(body.alias)
    raw = _load_raw_user_connections(user)
    databases = raw.setdefault("databases", {})
    if alias in databases:
        raise HTTPException(status_code=409, detail=f"Database alias '{alias}' already exists")

    entry = body.model_dump(exclude_none=True)
    entry.pop("alias", None)
    databases[alias] = entry
    save_user_connections_raw(user, raw)

    cfg = DatabaseConfig(alias=alias, **entry)
    return DatabaseAliasResponse(
        alias=cfg.alias,
        driver=cfg.driver,
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.user,
        sid=cfg.sid,
    )


@router.put("/databases/{alias}", response_model=DatabaseAliasResponse)
async def update_database_alias(
    alias: str,
    body: DatabaseUpdateRequest,
    user: UserContext = Depends(get_current_user),
) -> DatabaseAliasResponse:
    alias = _validate_alias(alias)
    raw = _load_raw_user_connections(user)
    databases = raw.setdefault("databases", {})
    if alias not in databases:
        raise HTTPException(status_code=404, detail=f"Database alias '{alias}' not found")

    current = dict(databases[alias])
    updates = body.model_dump(exclude_unset=True)
    if "password" in updates and updates["password"] is None:
        updates.pop("password")
    current.update({k: v for k, v in updates.items() if v is not None})
    databases[alias] = current
    save_user_connections_raw(user, raw)

    cfg = DatabaseConfig(alias=alias, **current)
    return DatabaseAliasResponse(
        alias=cfg.alias,
        driver=cfg.driver,
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.user,
        sid=cfg.sid,
    )


@router.delete("/databases/{alias}")
async def delete_database_alias(
    alias: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    alias = _validate_alias(alias)
    raw = _load_raw_user_connections(user)
    databases = raw.get("databases", {})
    if alias not in databases:
        raise HTTPException(status_code=404, detail=f"Database alias '{alias}' not found")
    del raw["databases"][alias]
    save_user_connections_raw(user, raw)
    return {"status": "deleted", "alias": alias}


@router.post("/llm", response_model=LlmAliasResponse)
async def create_llm_alias(
    body: LlmCreateRequest,
    user: UserContext = Depends(get_current_user),
) -> LlmAliasResponse:
    alias = _validate_alias(body.alias)
    raw = _load_raw_user_connections(user)
    llm = raw.setdefault("llm", {})
    if alias in llm:
        raise HTTPException(status_code=409, detail=f"LLM alias '{alias}' already exists")

    entry = body.model_dump(exclude_none=True)
    entry.pop("alias", None)
    llm[alias] = entry
    save_user_connections_raw(user, raw)

    cfg = LLMConfig(alias=alias, **entry)
    return LlmAliasResponse(
        alias=cfg.alias,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
    )


@router.put("/llm/{alias}", response_model=LlmAliasResponse)
async def update_llm_alias(
    alias: str,
    body: LlmUpdateRequest,
    user: UserContext = Depends(get_current_user),
) -> LlmAliasResponse:
    alias = _validate_alias(alias)
    raw = _load_raw_user_connections(user)
    llm = raw.setdefault("llm", {})
    if alias not in llm:
        raise HTTPException(status_code=404, detail=f"LLM alias '{alias}' not found")

    current = dict(llm[alias])
    updates = body.model_dump(exclude_unset=True)
    if "api_key" in updates and updates["api_key"] is None:
        updates.pop("api_key")
    current.update({k: v for k, v in updates.items() if v is not None})
    llm[alias] = current
    save_user_connections_raw(user, raw)

    cfg = LLMConfig(alias=alias, **current)
    return LlmAliasResponse(
        alias=cfg.alias,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
    )


@router.delete("/llm/{alias}")
async def delete_llm_alias(
    alias: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    alias = _validate_alias(alias)
    raw = _load_raw_user_connections(user)
    llm = raw.get("llm", {})
    if alias not in llm:
        raise HTTPException(status_code=404, detail=f"LLM alias '{alias}' not found")
    llm.pop(alias)
    save_user_connections_raw(user, raw)
    return {"status": "deleted", "alias": alias}


@router.post("/test-db", response_model=ConnectionTestResponse)
async def test_db_connection(
    request: AliasRequest,
    user: UserContext = Depends(get_current_user),
) -> ConnectionTestResponse:
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="Database alias is required")

    try:
        message = await DBService(user).test_connection(alias)
    except ValueError as exc:
        logger.warning("Database connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))
    except Exception as exc:
        logger.error("Database connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))

    return ConnectionTestResponse(alias=alias, ok=True, message=message)


@router.post("/test-llm", response_model=ConnectionTestResponse)
async def test_llm_connection(
    request: AliasRequest,
    user: UserContext = Depends(get_current_user),
) -> ConnectionTestResponse:
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="LLM alias is required")

    try:
        message = await LLMService(user, alias=alias).test_connection()
    except ValueError as exc:
        logger.warning("LLM connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))
    except Exception as exc:
        logger.error("LLM connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))

    return ConnectionTestResponse(alias=alias, ok=True, message=message)


@router.put("/default-llm", response_model=DefaultLlmResponse)
async def set_default_llm(
    request: DefaultLlmRequest,
    user: UserContext = Depends(get_current_user),
) -> DefaultLlmResponse:
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="LLM alias is required")

    try:
        default_llm = set_default_llm_alias(user, alias)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DefaultLlmResponse(default_llm=default_llm)
