"""Preset management for custom tree checkbox selections."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.sessions import get_current_user
from app.services.preset_share_service import (
    SharePresetRequest,
    SharePresetResponse,
    share_tree_preset,
)
from app.user_context import UserContext

router = APIRouter(prefix="/presets", tags=["presets"])


class PresetSummary(BaseModel):
    name: str
    schema_id: str
    path_count: int
    shared_by_name: str = ""


class PresetData(BaseModel):
    name: str
    schema_id: str
    custom_paths: list[str] = Field(default_factory=list)


def _safe_name(name: str) -> str:
    if not re.match(r"^[\w\-. ]+$", name):
        raise HTTPException(status_code=400, detail="Invalid preset name")
    return name


def _preset_path(user: UserContext, name: str) -> Path:
    user.presets_dir.mkdir(parents=True, exist_ok=True)
    return user.presets_dir / f"{_safe_name(name)}.json"


@router.get("", response_model=list[PresetSummary])
async def list_presets(user: UserContext = Depends(get_current_user)) -> list[PresetSummary]:
    user.presets_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[PresetSummary] = []
    for path in sorted(user.presets_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        summaries.append(
            PresetSummary(
                name=data.get("name", path.stem),
                schema_id=data.get("schema_id", ""),
                path_count=len(data.get("custom_paths", [])),
                shared_by_name=data.get("shared_by_name", ""),
            )
        )
    return summaries


@router.post("", response_model=PresetData)
async def save_preset(
    preset: PresetData,
    user: UserContext = Depends(get_current_user),
) -> PresetData:
    path = _preset_path(user, preset.name)
    path.write_text(
        json.dumps(preset.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return preset


@router.post("/share", response_model=SharePresetResponse)
async def share_preset_route(
    body: SharePresetRequest,
    user: UserContext = Depends(get_current_user),
) -> SharePresetResponse:
    return share_tree_preset(user, body)


@router.get("/{name}", response_model=PresetData)
async def load_preset(
    name: str,
    user: UserContext = Depends(get_current_user),
) -> PresetData:
    path = _preset_path(user, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    return PresetData(**data)


@router.delete("/{name}")
async def delete_preset(
    name: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    path = _preset_path(user, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    path.unlink()
    return {"status": "deleted", "name": name}
