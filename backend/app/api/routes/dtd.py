"""DTD upload and schema introspection endpoints."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT
from app.core.dtd_models import DTDSchema, ElementDef
from app.core.dtd_parser import DTDParser

router = APIRouter(prefix="/dtd", tags=["dtd"])
logger = logging.getLogger(__name__)

DTD_SCHEMA_DIR = PROJECT_ROOT / "dtd_schemas"
DTD_EXTENSIONS = (".dtd", ".ent", ".mod")

# In-memory schema registry; warmed from disk on application startup.
_schema_registry: dict[str, DTDSchema] = {}


def _schema_id_sidecar(dtd_path: Path) -> Path:
    return dtd_path.with_suffix(dtd_path.suffix + ".schema_id")


def _read_schema_id(dtd_path: Path) -> str | None:
    sidecar = _schema_id_sidecar(dtd_path)
    if not sidecar.is_file():
        return None
    schema_id = sidecar.read_text(encoding="utf-8").strip()
    return schema_id or None


def _write_schema_id(dtd_path: Path, schema_id: str) -> None:
    _schema_id_sidecar(dtd_path).write_text(schema_id, encoding="utf-8")


def _parse_and_register(dtd_path: Path, schema_id: str | None = None) -> str:
    """Parse a DTD file from disk and register it in the in-memory registry."""
    parser = DTDParser(base_dir=DTD_SCHEMA_DIR)
    schema = parser.parse_file(dtd_path)

    sid = schema_id or _read_schema_id(dtd_path) or str(uuid.uuid4())
    _write_schema_id(dtd_path, sid)
    _schema_registry[sid] = schema
    return sid


_SYSTEM_REF_RE = re.compile(r'SYSTEM\s+["\']([^"\']+)["\']', re.IGNORECASE)


def _referenced_dtd_modules(schema_dir: Path) -> set[str]:
    """Return basenames of DTD modules included via SYSTEM from other files in the folder."""
    referenced: set[str] = set()
    for path in schema_dir.glob("*.dtd"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _SYSTEM_REF_RE.finditer(text):
            referenced.add(Path(match.group(1)).name.lower())
    return referenced


def _source_basenames(schema: DTDSchema) -> set[str]:
    return {Path(path).name for path in schema.source_files}


def _entry_point_paths(schema_dir: Path) -> list[Path]:
    referenced_modules = _referenced_dtd_modules(schema_dir)
    return [
        path
        for path in sorted(schema_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() == ".dtd"
        and path.name.lower() not in referenced_modules
    ]


def _pick_primary_entry_point(entry_points: list[Path]) -> Path:
    for path in entry_points:
        if path.name.lower() == "main.dtd":
            return path
    return entry_points[0]


def _delete_schema_artifacts(path: Path) -> None:
    if path.is_file():
        path.unlink()
    sidecar = _schema_id_sidecar(path)
    if sidecar.is_file():
        sidecar.unlink()


def _cleanup_schema_storage(
    *,
    keep_basenames: set[str],
    keep_schema_ids: set[str],
) -> None:
    """Remove stale DTD files, sidecars, and in-memory schemas."""
    for schema_id in list(_schema_registry):
        if schema_id not in keep_schema_ids:
            del _schema_registry[schema_id]

    if not DTD_SCHEMA_DIR.is_dir():
        return

    for path in list(DTD_SCHEMA_DIR.iterdir()):
        if not path.is_file():
            continue

        if path.name.endswith(".schema_id"):
            original_name = path.name[: -len(".schema_id")]
            if original_name not in keep_basenames:
                path.unlink()
            continue

        if path.suffix.lower() in DTD_EXTENSIONS and path.name not in keep_basenames:
            _delete_schema_artifacts(path)


def initialize_schema_registry() -> int:
    """Scan dtd_schemas/ and load the primary saved DTD entry point."""
    DTD_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    entry_points = _entry_point_paths(DTD_SCHEMA_DIR)
    if not entry_points:
        return 0

    primary_path = _pick_primary_entry_point(entry_points)

    try:
        schema_id = _parse_and_register(primary_path)
    except Exception:
        logger.exception(
            "Failed to load DTD schema from disk [file=%s]", primary_path.name
        )
        return 0

    schema = _schema_registry[schema_id]
    _cleanup_schema_storage(
        keep_basenames=_source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    logger.info(
        "Loaded DTD schema from disk [file=%s schema_id=%s]",
        primary_path.name,
        schema_id,
    )
    return 1


class ElementSummary(BaseModel):
    name: str
    doc: str
    content_raw: str
    attributes: list[str]
    required_attributes: list[str]


class SchemaResponse(BaseModel):
    schema_id: str
    source_files: list[str]
    element_count: int
    elements: list[str]


class ElementDetailResponse(BaseModel):
    schema_id: str
    element: ElementSummary


def _element_to_summary(elem: ElementDef) -> ElementSummary:
    required = [
        name
        for name, attr in elem.attributes.items()
        if attr.default_decl == "#REQUIRED"
    ]
    return ElementSummary(
        name=elem.name,
        doc=elem.doc,
        content_raw=elem.content_raw,
        attributes=list(elem.attributes.keys()),
        required_attributes=required,
    )


@router.post("/upload", response_model=SchemaResponse)
async def upload_dtd(file: UploadFile = File(...)) -> SchemaResponse:
    """Upload a DTD file, parse it, and register the resulting schema."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not file.filename.lower().endswith(DTD_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Only .dtd, .ent, and .mod files are supported",
        )

    DTD_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    saved_path = DTD_SCHEMA_DIR / file.filename
    content = await file.read()

    async with aiofiles.open(saved_path, "wb") as f:
        await f.write(content)

    try:
        schema_id = _parse_and_register(
            saved_path,
            schema_id=_read_schema_id(saved_path),
        )
    except FileNotFoundError as exc:
        logger.warning("DTD file not found during parse [file=%s]: %s", file.filename, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "DTD parsing failed [file=%s path=%s size=%d]",
            file.filename,
            saved_path,
            len(content),
        )
        raise HTTPException(
            status_code=422, detail=f"DTD parsing failed: {exc}"
        ) from exc

    schema = _schema_registry[schema_id]
    _cleanup_schema_storage(
        keep_basenames=_source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    return SchemaResponse(
        schema_id=schema_id,
        source_files=schema.source_files,
        element_count=len(schema.elements),
        elements=schema.root_elements(),
    )


@router.get("/schemas", response_model=list[SchemaResponse])
async def list_schemas() -> list[SchemaResponse]:
    """List all registered schemas."""
    return [
        SchemaResponse(
            schema_id=sid,
            source_files=schema.source_files,
            element_count=len(schema.elements),
            elements=schema.root_elements(),
        )
        for sid, schema in _schema_registry.items()
    ]


@router.get("/{schema_id}/elements", response_model=list[ElementSummary])
async def list_elements(schema_id: str) -> list[ElementSummary]:
    """Return all elements for a registered schema."""
    schema = _get_schema(schema_id)
    return [_element_to_summary(elem) for elem in schema.elements.values()]


@router.get("/{schema_id}/elements/{element_name}", response_model=ElementDetailResponse)
async def get_element(schema_id: str, element_name: str) -> ElementDetailResponse:
    """Return detailed metadata for a single element."""
    schema = _get_schema(schema_id)
    if element_name not in schema.elements:
        raise HTTPException(
            status_code=404, detail=f"Element '{element_name}' not found"
        )
    return ElementDetailResponse(
        schema_id=schema_id,
        element=_element_to_summary(schema.elements[element_name]),
    )


@router.get("/{schema_id}/elements/{element_name}/tree")
async def get_element_tree(schema_id: str, element_name: str) -> dict[str, Any]:
    """Return the full content model tree for lazy UI rendering."""
    schema = _get_schema(schema_id)
    if element_name not in schema.elements:
        raise HTTPException(
            status_code=404, detail=f"Element '{element_name}' not found"
        )
    elem = schema.elements[element_name]
    return {
        "schema_id": schema_id,
        "element": element_name,
        "doc": elem.doc,
        "content_model": elem.content_model.model_dump(),
        "attributes": {
            name: attr.model_dump()
            for name, attr in elem.attributes.items()
        },
    }


def _get_schema(schema_id: str) -> DTDSchema:
    if schema_id not in _schema_registry:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' not found")
    return _schema_registry[schema_id]


def get_schema_registry() -> dict[str, DTDSchema]:
    """Expose registry for tests and future modules."""
    return _schema_registry
