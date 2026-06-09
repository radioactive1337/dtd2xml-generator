"""Preset management for custom tree checkbox selections."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT

router = APIRouter(prefix="/presets", tags=["presets"])

PRESETS_DIR = PROJECT_ROOT / "presets"


class PresetSummary(BaseModel):
    name: str
    schema_id: str
    path_count: int


class PresetData(BaseModel):
    name: str
    schema_id: str
    custom_paths: list[str] = Field(default_factory=list)


def _safe_name(name: str) -> str:
    if not re.match(r"^[\w\-. ]+$", name):
        raise HTTPException(status_code=400, detail="Invalid preset name")
    return name


def _preset_path(name: str) -> Path:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    return PRESETS_DIR / f"{_safe_name(name)}.json"


@router.get("", response_model=list[PresetSummary])
async def list_presets() -> list[PresetSummary]:
    """List all saved presets."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[PresetSummary] = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        summaries.append(
            PresetSummary(
                name=data.get("name", path.stem),
                schema_id=data.get("schema_id", ""),
                path_count=len(data.get("custom_paths", [])),
            )
        )
    return summaries


@router.post("", response_model=PresetData)
async def save_preset(preset: PresetData) -> PresetData:
    """Save a custom path preset to a local JSON file."""
    path = _preset_path(preset.name)
    path.write_text(
        json.dumps(preset.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return preset


@router.get("/{name}", response_model=PresetData)
async def load_preset(name: str) -> PresetData:
    """Load a saved preset by name."""
    path = _preset_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    return PresetData(**data)


@router.delete("/{name}")
async def delete_preset(name: str) -> dict[str, str]:
    """Delete a saved preset."""
    path = _preset_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    path.unlink()
    return {"status": "deleted", "name": name}
