"""Admin API: user management, backups, system settings."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import config
from app.auth.sessions import get_current_admin
from app.auth.users import delete_user, get_user_by_id, list_all_users
from app.config import (
    is_allow_self_registration,
    load_app_settings,
    shared_dtd_dir,
)
from app.user_context import UserContext

router = APIRouter(prefix="/admin", tags=["admin"])


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
        presets, mapping, xml_docs, workspace_bytes = _user_workspace_stats(user.id)
        items.append(
            AdminUserInfo(
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
        )
    return AdminUsersResponse(users=items, total=len(items))


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
