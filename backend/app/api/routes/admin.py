"""Admin API: user management, backups, system settings."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import config
from app.auth.sessions import get_current_admin
from app.auth.users import create_user, delete_user, get_user_by_id, list_all_users, validate_username
from app.config import (
    DatabaseConfig,
    LLMConfig,
    is_allow_self_registration,
    load_app_settings,
    load_shared_connections,
    shared_dtd_dir,
    _load_raw_shared_connections,
    _save_raw_shared_connections,
)
from app.api.routes.config import (
    AliasRequest,
    ConnectionTestResponse,
    DatabaseAliasResponse,
    DatabaseCreateRequest,
    DatabaseUpdateRequest,
    LlmAliasResponse,
    LlmCreateRequest,
    LlmUpdateRequest,
    _validate_alias,
)
from app.services.db_service import DBService
from app.services.llm_service import LLMService
from app.user_context import UserContext, user_context_from_record

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


class AdminUserInfo(BaseModel):
    id: str
    display_name: str
    created_at: str
    last_seen: str
    is_admin: bool
    presets_count: int
    mapping_presets_count: int
    xml_documents_count: int
    workspace_bytes: int


class AdminUsersResponse(BaseModel):
    users: list[AdminUserInfo]
    total: int


class AdminStatsResponse(BaseModel):
    users_count: int
    dtd_schemas_count: int
    total_presets: int
    total_mapping_presets: int
    total_xml_documents: int
    data_dir_bytes: int
    allow_self_registration: bool


class AdminSettingsResponse(BaseModel):
    allow_self_registration: bool


class AdminSettingsUpdate(BaseModel):
    allow_self_registration: bool | None = None


class AdminCreateUserRequest(BaseModel):
    username: str


class AdminConnectionsResponse(BaseModel):
    databases: list[DatabaseAliasResponse]
    llm: list[LlmAliasResponse]


def _user_to_admin_info(user) -> AdminUserInfo:
    presets, mapping, xml_docs, workspace_bytes = _user_workspace_stats(user.id)
    return AdminUserInfo(
        id=user.id,
        display_name=user.display_name,
        created_at=user.created_at,
        last_seen=user.last_seen,
        is_admin=user.is_admin,
        presets_count=presets,
        mapping_presets_count=mapping,
        xml_documents_count=xml_docs,
        workspace_bytes=workspace_bytes,
    )


def _count_json_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.glob("*.json") if path.is_file())


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def _user_workspace_stats(user_id: str) -> tuple[int, int, int, int]:
    root = config.DATA_DIR / "users" / user_id
    presets = _count_json_files(root / "presets")
    mapping = _count_json_files(root / "mapping_presets")
    xml_docs = _count_json_files(root / "xml_documents")
    size = _dir_size(root)
    return presets, mapping, xml_docs, size


def _count_dtd_schemas() -> int:
    dtd_dir = shared_dtd_dir()
    if not dtd_dir.is_dir():
        return 0
    return sum(1 for path in dtd_dir.glob("*.dtd") if path.is_file())


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(_admin: UserContext = Depends(get_current_admin)) -> AdminStatsResponse:
    users = list_all_users()
    total_presets = 0
    total_mapping = 0
    total_xml = 0
    for user in users:
        presets, mapping, xml_docs, _ = _user_workspace_stats(user.id)
        total_presets += presets
        total_mapping += mapping
        total_xml += xml_docs

    return AdminStatsResponse(
        users_count=len(users),
        dtd_schemas_count=_count_dtd_schemas(),
        total_presets=total_presets,
        total_mapping_presets=total_mapping,
        total_xml_documents=total_xml,
        data_dir_bytes=_dir_size(config.DATA_DIR),
        allow_self_registration=is_allow_self_registration(),
    )


@router.get("/users", response_model=AdminUsersResponse)
async def admin_list_users(_admin: UserContext = Depends(get_current_admin)) -> AdminUsersResponse:
    users = list_all_users()
    items: list[AdminUserInfo] = []
    for user in users:
        items.append(_user_to_admin_info(user))
    return AdminUsersResponse(users=items, total=len(items))


@router.post("/users", response_model=AdminUserInfo, status_code=201)
async def admin_create_user(
    body: AdminCreateUserRequest,
    _admin: UserContext = Depends(get_current_admin),
) -> AdminUserInfo:
    try:
        display = validate_username(body.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        record = create_user(display)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    user_context_from_record(record)
    return _user_to_admin_info(record)


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    admin: UserContext = Depends(get_current_admin),
) -> dict[str, str]:
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    record = get_user_by_id(user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "ok", "deleted": record.display_name}


@router.get("/backup")
async def admin_backup(_admin: UserContext = Depends(get_current_admin)) -> StreamingResponse:
    buffer = io.BytesIO()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        data_dir = config.DATA_DIR
        if data_dir.is_dir():
            for path in data_dir.rglob("*"):
                if not path.is_file():
                    continue
                arcname = Path("data") / path.relative_to(data_dir)
                archive.write(path, arcname.as_posix())

        if config.APP_CONFIG_FILE.is_file():
            archive.write(config.APP_CONFIG_FILE, "config/app.json")

    buffer.seek(0)
    filename = f"xml-generator-backup-{timestamp}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/settings", response_model=AdminSettingsResponse)
async def admin_get_settings(
    _admin: UserContext = Depends(get_current_admin),
) -> AdminSettingsResponse:
    return AdminSettingsResponse(allow_self_registration=is_allow_self_registration())


@router.put("/settings", response_model=AdminSettingsResponse)
async def admin_update_settings(
    body: AdminSettingsUpdate,
    _admin: UserContext = Depends(get_current_admin),
) -> AdminSettingsResponse:
    if body.allow_self_registration is None:
        return AdminSettingsResponse(allow_self_registration=is_allow_self_registration())

    if not config.APP_CONFIG_FILE.is_file():
        raise HTTPException(status_code=500, detail="app.json not found")

    raw = json.loads(config.APP_CONFIG_FILE.read_text(encoding="utf-8"))
    app = raw.setdefault("app", {})
    app["allow_self_registration"] = body.allow_self_registration
    config.APP_CONFIG_FILE.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    config._invalidate_app_config_cache()
    load_app_settings()

    return AdminSettingsResponse(allow_self_registration=body.allow_self_registration)


@router.get("/connections", response_model=AdminConnectionsResponse)
async def admin_get_connections(
    _admin: UserContext = Depends(get_current_admin),
) -> AdminConnectionsResponse:
    connections = load_shared_connections()
    return AdminConnectionsResponse(
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
    )


@router.post("/databases", response_model=DatabaseAliasResponse)
async def admin_create_database_alias(
    body: DatabaseCreateRequest,
    _admin: UserContext = Depends(get_current_admin),
) -> DatabaseAliasResponse:
    alias = _validate_alias(body.alias)
    raw = _load_raw_shared_connections()
    databases = raw.setdefault("databases", {})
    if alias in databases:
        raise HTTPException(status_code=409, detail=f"Database alias '{alias}' already exists")

    entry = body.model_dump(exclude_none=True)
    entry.pop("alias", None)
    databases[alias] = entry
    _save_raw_shared_connections(raw)

    cfg = DatabaseConfig(alias=alias, **entry)
    return DatabaseAliasResponse(
        alias=cfg.alias,
        driver=cfg.driver,
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.user,
        sid=cfg.sid,
        managed=True,
    )


@router.put("/databases/{alias}", response_model=DatabaseAliasResponse)
async def admin_update_database_alias(
    alias: str,
    body: DatabaseUpdateRequest,
    _admin: UserContext = Depends(get_current_admin),
) -> DatabaseAliasResponse:
    alias = _validate_alias(alias)
    raw = _load_raw_shared_connections()
    databases = raw.setdefault("databases", {})
    if alias not in databases:
        raise HTTPException(status_code=404, detail=f"Database alias '{alias}' not found")

    current = dict(databases[alias])
    updates = body.model_dump(exclude_unset=True)
    if "password" in updates and updates["password"] is None:
        updates.pop("password")
    current.update({k: v for k, v in updates.items() if v is not None})
    databases[alias] = current
    _save_raw_shared_connections(raw)

    cfg = DatabaseConfig(alias=alias, **current)
    return DatabaseAliasResponse(
        alias=cfg.alias,
        driver=cfg.driver,
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.user,
        sid=cfg.sid,
        managed=True,
    )


@router.delete("/databases/{alias}")
async def admin_delete_database_alias(
    alias: str,
    _admin: UserContext = Depends(get_current_admin),
) -> dict[str, str]:
    alias = _validate_alias(alias)
    raw = _load_raw_shared_connections()
    databases = raw.get("databases", {})
    if alias not in databases:
        raise HTTPException(status_code=404, detail=f"Database alias '{alias}' not found")
    del raw["databases"][alias]
    _save_raw_shared_connections(raw)
    return {"status": "deleted", "alias": alias}


@router.post("/llm", response_model=LlmAliasResponse)
async def admin_create_llm_alias(
    body: LlmCreateRequest,
    _admin: UserContext = Depends(get_current_admin),
) -> LlmAliasResponse:
    alias = _validate_alias(body.alias)
    raw = _load_raw_shared_connections()
    llm = raw.setdefault("llm", {})
    if alias in llm:
        raise HTTPException(status_code=409, detail=f"LLM alias '{alias}' already exists")

    entry = body.model_dump(exclude_none=True)
    entry.pop("alias", None)
    llm[alias] = entry
    _save_raw_shared_connections(raw)

    cfg = LLMConfig(alias=alias, **entry)
    return LlmAliasResponse(
        alias=cfg.alias,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
        managed=True,
    )


@router.put("/llm/{alias}", response_model=LlmAliasResponse)
async def admin_update_llm_alias(
    alias: str,
    body: LlmUpdateRequest,
    _admin: UserContext = Depends(get_current_admin),
) -> LlmAliasResponse:
    alias = _validate_alias(alias)
    raw = _load_raw_shared_connections()
    llm = raw.setdefault("llm", {})
    if alias not in llm:
        raise HTTPException(status_code=404, detail=f"LLM alias '{alias}' not found")

    current = dict(llm[alias])
    updates = body.model_dump(exclude_unset=True)
    if "api_key" in updates and updates["api_key"] is None:
        updates.pop("api_key")
    current.update({k: v for k, v in updates.items() if v is not None})
    llm[alias] = current
    _save_raw_shared_connections(raw)

    cfg = LLMConfig(alias=alias, **current)
    return LlmAliasResponse(
        alias=cfg.alias,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
        managed=True,
    )


@router.delete("/llm/{alias}")
async def admin_delete_llm_alias(
    alias: str,
    _admin: UserContext = Depends(get_current_admin),
) -> dict[str, str]:
    alias = _validate_alias(alias)
    raw = _load_raw_shared_connections()
    llm = raw.get("llm", {})
    if alias not in llm:
        raise HTTPException(status_code=404, detail=f"LLM alias '{alias}' not found")
    llm.pop(alias)
    _save_raw_shared_connections(raw)
    return {"status": "deleted", "alias": alias}


@router.post("/test-db", response_model=ConnectionTestResponse)
async def admin_test_db_connection(
    request: AliasRequest,
    admin: UserContext = Depends(get_current_admin),
) -> ConnectionTestResponse:
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="Database alias is required")

    try:
        message = await DBService(admin).test_connection(alias)
    except ValueError as exc:
        logger.warning("Admin database connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))
    except Exception as exc:
        logger.error("Admin database connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))

    return ConnectionTestResponse(alias=alias, ok=True, message=message)


@router.post("/test-llm", response_model=ConnectionTestResponse)
async def admin_test_llm_connection(
    request: AliasRequest,
    admin: UserContext = Depends(get_current_admin),
) -> ConnectionTestResponse:
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail="LLM alias is required")

    try:
        message = await LLMService(admin, alias=alias).test_connection()
    except ValueError as exc:
        logger.warning("Admin LLM connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))
    except Exception as exc:
        logger.error("Admin LLM connection test failed [alias=%s]: %s", alias, exc)
        return ConnectionTestResponse(alias=alias, ok=False, message=str(exc))

    return ConnectionTestResponse(alias=alias, ok=True, message=message)
