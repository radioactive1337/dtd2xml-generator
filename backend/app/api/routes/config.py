"""Connection configuration and health-check endpoints."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.sessions import get_current_user
from app.config import (
    USER_ALIAS_FORBIDDEN_DETAIL,
    clear_user_git_settings,
    get_connection_aliases,
    get_reference_xml_settings,
    get_user_git_author_email,
    get_user_git_author_name,
    get_user_git_user,
    load_connections,
    reference_xml_requires_https_token,
    resolve_git_auth,
    save_user_git_settings,
    set_default_llm_alias,
    user_git_author_configured,
    user_git_configured,
)
from app.services.db_service import DBService
from app.services.git_identity_service import fetch_git_author_identity
from app.services.llm_service import LLMService
from app.services.reference_xml_sync import GitAuth, test_git_access
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
    managed: bool = False


class LlmAliasResponse(BaseModel):
    alias: str
    base_url: str
    model: str
    timeout: float
    managed: bool = False


class ConnectionsResponse(BaseModel):
    databases: list[DatabaseAliasResponse]
    llm: list[LlmAliasResponse]
    default_llm: str | None = None


class GitSettingsResponse(BaseModel):
    configured: bool
    user: str = "oauth2"
    author_name: str = ""
    author_email: str = ""
    author_configured: bool = False


class GitSettingsUpdateRequest(BaseModel):
    token: str | None = None
    user: str | None = None
    author_name: str | None = None
    author_email: str | None = None


def _validate_alias(alias: str) -> str:
    name = alias.strip()
    if not name or not _ALIAS_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid alias name")
    if ".." in name:
        raise HTTPException(status_code=400, detail="Invalid alias name")
    return name


def _forbid_user_alias_write() -> NoReturn:
    raise HTTPException(status_code=403, detail=USER_ALIAS_FORBIDDEN_DETAIL)


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
                managed=True,
            )
            for cfg in connections.databases.values()
        ],
        llm=[
            LlmAliasResponse(
                alias=cfg.alias,
                base_url=cfg.base_url,
                model=cfg.model,
                timeout=cfg.timeout,
                managed=True,
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
    _forbid_user_alias_write()


@router.put("/databases/{alias}", response_model=DatabaseAliasResponse)
async def update_database_alias(
    alias: str,
    body: DatabaseUpdateRequest,
    user: UserContext = Depends(get_current_user),
) -> DatabaseAliasResponse:
    _forbid_user_alias_write()


@router.delete("/databases/{alias}")
async def delete_database_alias(
    alias: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    _forbid_user_alias_write()


@router.post("/llm", response_model=LlmAliasResponse)
async def create_llm_alias(
    body: LlmCreateRequest,
    user: UserContext = Depends(get_current_user),
) -> LlmAliasResponse:
    _forbid_user_alias_write()


@router.put("/llm/{alias}", response_model=LlmAliasResponse)
async def update_llm_alias(
    alias: str,
    body: LlmUpdateRequest,
    user: UserContext = Depends(get_current_user),
) -> LlmAliasResponse:
    _forbid_user_alias_write()


@router.delete("/llm/{alias}")
async def delete_llm_alias(
    alias: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    _forbid_user_alias_write()


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


@router.get("/git", response_model=GitSettingsResponse)
async def get_git_settings(
    user: UserContext = Depends(get_current_user),
) -> GitSettingsResponse:
    return GitSettingsResponse(
        configured=user_git_configured(user),
        user=get_user_git_user(user),
        author_name=get_user_git_author_name(user),
        author_email=get_user_git_author_email(user),
        author_configured=user_git_author_configured(user),
    )


async def _maybe_autofill_git_author(user: UserContext, token: str) -> None:
    if user_git_author_configured(user):
        return
    settings = get_reference_xml_settings()
    if settings is None:
        return
    identity = await asyncio.to_thread(
        fetch_git_author_identity,
        settings.repo_url,
        token,
    )
    if identity:
        save_user_git_settings(
            user,
            author_name=identity[0],
            author_email=identity[1],
        )


@router.put("/git", response_model=GitSettingsResponse)
async def update_git_settings(
    body: GitSettingsUpdateRequest,
    user: UserContext = Depends(get_current_user),
) -> GitSettingsResponse:
    if (
        body.token is None
        and body.user is None
        and body.author_name is None
        and body.author_email is None
    ):
        raise HTTPException(status_code=400, detail="No Git settings to update")

    kwargs: dict[str, str | None] = {}
    if body.token is not None:
        kwargs["token"] = body.token
    if body.user is not None:
        kwargs["git_user"] = body.user
    if body.author_name is not None:
        kwargs["author_name"] = body.author_name
    if body.author_email is not None:
        kwargs["author_email"] = body.author_email
    save_user_git_settings(user, **kwargs)

    if body.token and body.token.strip():
        await _maybe_autofill_git_author(user, body.token.strip())

    return GitSettingsResponse(
        configured=user_git_configured(user),
        user=get_user_git_user(user),
        author_name=get_user_git_author_name(user),
        author_email=get_user_git_author_email(user),
        author_configured=user_git_author_configured(user),
    )


@router.delete("/git")
async def delete_git_settings(
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    clear_user_git_settings(user)
    return {"status": "deleted"}


@router.post("/test-git", response_model=ConnectionTestResponse)
async def test_git_connection(
    user: UserContext = Depends(get_current_user),
) -> ConnectionTestResponse:
    settings = get_reference_xml_settings()
    if settings is None:
        return ConnectionTestResponse(
            alias="git",
            ok=False,
            message="Reference XML library is not configured",
        )

    token, git_user = resolve_git_auth(user)
    if reference_xml_requires_https_token(settings) and not token:
        return ConnectionTestResponse(
            alias="git",
            ok=False,
            message="Укажите Git-токен в настройках",
        )

    try:
        message = await asyncio.to_thread(
            test_git_access,
            settings,
            GitAuth(token=token, git_user=git_user),
        )
    except ValueError as exc:
        logger.warning("Git connection test failed: %s", exc)
        return ConnectionTestResponse(alias="git", ok=False, message=str(exc))
    except Exception as exc:
        logger.error("Git connection test failed: %s", exc)
        return ConnectionTestResponse(alias="git", ok=False, message=str(exc))

    return ConnectionTestResponse(alias="git", ok=True, message=message)
