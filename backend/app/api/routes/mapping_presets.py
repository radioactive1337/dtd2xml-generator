"""Preset management for database-to-XML field mappings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT

router = APIRouter(prefix="/mapping-presets", tags=["mapping-presets"])

PRESETS_DIR = PROJECT_ROOT / "mapping_presets"


class MappingField(BaseModel):
    db_col: str = ""
    xml_attr: str = ""


class SqlMappingEntry(BaseModel):
    target_element: str = ""
    query: str = ""
    fields: list[MappingField] = Field(default_factory=list)
    db_alias: str = ""
    target_path: str = ""


class MappingPresetSummary(BaseModel):
    name: str
    schema_id: str = ""
    mapping_count: int


class MappingPresetData(BaseModel):
    name: str
    schema_id: str = ""
    mappings: list[SqlMappingEntry] = Field(default_factory=list)


def _safe_name(name: str) -> str:
    if not re.match(r"^[\w\-. ]+$", name):
        raise HTTPException(status_code=400, detail="Invalid preset name")
    return name


def _preset_path(name: str) -> Path:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    return PRESETS_DIR / f"{_safe_name(name)}.json"


def _normalize_fields(raw_fields: list | dict) -> list[MappingField]:
    if isinstance(raw_fields, dict):
        return [
            MappingField(db_col=db_col, xml_attr=xml_attr)
            for db_col, xml_attr in raw_fields.items()
        ]
    return [MappingField(**field) for field in raw_fields]


@router.get("", response_model=list[MappingPresetSummary])
async def list_mapping_presets(
    schema_id: str | None = Query(default=None),
) -> list[MappingPresetSummary]:
    """List saved mapping presets, optionally filtered by schema."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[MappingPresetSummary] = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        preset_schema = data.get("schema_id", "")
        if schema_id and preset_schema != schema_id:
            continue
        summaries.append(
            MappingPresetSummary(
                name=data.get("name", path.stem),
                schema_id=preset_schema,
                mapping_count=len(data.get("mappings", [])),
            )
        )
    return summaries


@router.post("", response_model=MappingPresetData)
async def save_mapping_preset(preset: MappingPresetData) -> MappingPresetData:
    """Save a database mapping preset to a local JSON file."""
    path = _preset_path(preset.name)
    path.write_text(
        json.dumps(preset.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return preset


@router.get("/{name}", response_model=MappingPresetData)
async def load_mapping_preset(name: str) -> MappingPresetData:
    """Load a saved mapping preset by name."""
    path = _preset_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Mapping preset '{name}' not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    legacy_alias = data.get("db_alias", "")
    mappings = [
        SqlMappingEntry(
            target_element=m.get("target_element", ""),
            query=m.get("query", ""),
            fields=_normalize_fields(m.get("fields", [])),
            db_alias=m.get("db_alias") or legacy_alias,
            target_path=m.get("target_path", ""),
        )
        for m in data.get("mappings", [])
    ]
    return MappingPresetData(
        name=data.get("name", name),
        schema_id=data.get("schema_id", ""),
        mappings=mappings,
    )


@router.delete("/{name}")
async def delete_mapping_preset(name: str) -> dict[str, str]:
    """Delete a saved mapping preset."""
    path = _preset_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Mapping preset '{name}' not found")
    path.unlink()
    return {"status": "deleted", "name": name}
