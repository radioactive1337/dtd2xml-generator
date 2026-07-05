"""DTD upload and schema introspection endpoints."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth.sessions import get_current_user
from app.core.dtd_archive import extract_jar_dtd_files
from app.core.dtd_models import DTDSchema, ElementDef
from app.core.dtd_parser import DTDParser
from app.user_context import UserContext

router = APIRouter(prefix="/dtd", tags=["dtd"])
logger = logging.getLogger(__name__)

DTD_EXTENSIONS = (".dtd", ".ent", ".mod")

# user_id -> schema_id -> DTDSchema
_schema_registry: dict[str, dict[str, DTDSchema]] = {}

# Legacy export for tests (dev-user path)
DTD_SCHEMA_DIR: Path | None = None


def _user_registry(user: UserContext) -> dict[str, DTDSchema]:
    if user.user_id not in _schema_registry:
        _schema_registry[user.user_id] = {}
    return _schema_registry[user.user_id]


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


def _parse_and_register(
    user: UserContext,
    dtd_path: Path,
    schema_id: str | None = None,
) -> str:
    parser = DTDParser(base_dir=user.dtd_dir)
    schema = parser.parse_file(dtd_path)

    sid = schema_id or _read_schema_id(dtd_path) or str(uuid.uuid4())
    _write_schema_id(dtd_path, sid)
    _user_registry(user)[sid] = schema
    return sid


_SYSTEM_REF_RE = re.compile(r'SYSTEM\s+["\']([^"\']+)["\']', re.IGNORECASE)


def _referenced_dtd_modules(schema_dir: Path) -> set[str]:
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


def _collect_system_ref_basenames(dtd_path: Path) -> set[str]:
    referenced: set[str] = set()
    to_scan = [dtd_path]
    scanned: set[Path] = set()

    while to_scan:
        path = to_scan.pop()
        resolved = path.resolve()
        if resolved in scanned:
            continue
        scanned.add(resolved)

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for match in _SYSTEM_REF_RE.finditer(text):
            ref_name = Path(match.group(1)).name
            referenced.add(ref_name)
            ref_path = (path.parent / ref_name).resolve()
            if ref_path.is_file() and ref_path not in scanned:
                to_scan.append(ref_path)

    return referenced


def _validate_dtd_references(entry_path: Path, available_basenames: set[str]) -> None:
    missing = _collect_system_ref_basenames(entry_path) - available_basenames
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"DTD references missing files: {missing_list}")


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
    user: UserContext,
    *,
    keep_basenames: set[str],
    keep_schema_ids: set[str],
) -> None:
    registry = _user_registry(user)
    for schema_id in list(registry):
        if schema_id not in keep_schema_ids:
            del registry[schema_id]

    schema_dir = user.dtd_dir
    if not schema_dir.is_dir():
        return

    for path in list(schema_dir.iterdir()):
        if not path.is_file():
            continue

        if path.name.endswith(".schema_id"):
            original_name = path.name[: -len(".schema_id")]
            if original_name not in keep_basenames:
                path.unlink()
            continue

        if path.suffix.lower() in DTD_EXTENSIONS and path.name not in keep_basenames:
            _delete_schema_artifacts(path)


def ensure_user_registry_loaded(user: UserContext) -> int:
    """Scan user's dtd_schemas/ and load the primary entry point if registry is empty."""
    registry = _user_registry(user)
    if registry:
        return len(registry)

    user.dtd_dir.mkdir(parents=True, exist_ok=True)
    entry_points = _entry_point_paths(user.dtd_dir)
    if not entry_points:
        return 0

    primary_path = _pick_primary_entry_point(entry_points)

    try:
        schema_id = _parse_and_register(user, primary_path)
    except Exception:
        logger.exception(
            "Failed to load DTD schema from disk [user=%s file=%s]",
            user.display_name,
            primary_path.name,
        )
        return 0

    schema = registry[schema_id]
    _cleanup_schema_storage(
        user,
        keep_basenames=_source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    logger.info(
        "Loaded DTD schema from disk [user=%s file=%s schema_id=%s]",
        user.display_name,
        primary_path.name,
        schema_id,
    )
    return 1


def initialize_schema_registry() -> int:
    """Legacy startup hook — no-op; registries load lazily per user."""
    return 0


class ElementSummary(BaseModel):
    name: str
    doc: str
    content_raw: str
    attributes: list[str]
    required_attributes: list[str]
    attribute_docs: dict[str, str] = {}


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
        attribute_docs={
            name: attr.doc for name, attr in elem.attributes.items() if attr.doc
        },
    )


@router.post("/upload", response_model=SchemaResponse)
async def upload_dtd(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
) -> SchemaResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not file.filename.lower().endswith(DTD_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Only .dtd, .ent, and .mod files are supported",
        )

    user.dtd_dir.mkdir(parents=True, exist_ok=True)
    saved_path = user.dtd_dir / file.filename
    content = await file.read()

    async with aiofiles.open(saved_path, "wb") as f:
        await f.write(content)

    try:
        schema_id = await asyncio.to_thread(
            _parse_and_register,
            user,
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

    schema = _user_registry(user)[schema_id]
    _cleanup_schema_storage(
        user,
        keep_basenames=_source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    return SchemaResponse(
        schema_id=schema_id,
        source_files=schema.source_files,
        element_count=len(schema.elements),
        elements=schema.root_elements(),
    )


@router.post("/upload-jar", response_model=SchemaResponse)
async def upload_dtd_jar(
    file: UploadFile = File(...),
    inner_path: str = Form("META-INF/dtd/"),
    entry_file: str = Form("v2.dtd"),
    user: UserContext = Depends(get_current_user),
) -> SchemaResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not file.filename.lower().endswith(".jar"):
        raise HTTPException(status_code=400, detail="Only .jar files are supported")

    entry_basename = Path(entry_file).name
    if entry_basename != entry_file or not entry_basename.lower().endswith(".dtd"):
        raise HTTPException(status_code=400, detail="entry_file must be a .dtd basename")

    user.dtd_dir.mkdir(parents=True, exist_ok=True)
    jar_bytes = await file.read()

    try:
        extracted = extract_jar_dtd_files(jar_bytes, user.dtd_dir, prefix=inner_path)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid JAR archive") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if entry_basename not in extracted:
        raise HTTPException(
            status_code=404,
            detail=f"entry_file '{entry_basename}' not found in {inner_path}",
        )

    entry_path = extracted[entry_basename]
    available_basenames = set(extracted)

    try:
        _validate_dtd_references(entry_path, available_basenames)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        schema_id = await asyncio.to_thread(
            _parse_and_register,
            user,
            entry_path,
            schema_id=_read_schema_id(entry_path),
        )
    except FileNotFoundError as exc:
        logger.warning(
            "DTD file not found during JAR parse [entry=%s]: %s",
            entry_basename,
            exc,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "DTD parsing failed [jar=%s entry=%s path=%s size=%d]",
            file.filename,
            entry_basename,
            entry_path,
            len(jar_bytes),
        )
        raise HTTPException(
            status_code=422, detail=f"DTD parsing failed: {exc}"
        ) from exc

    schema = _user_registry(user)[schema_id]
    _cleanup_schema_storage(
        user,
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
async def list_schemas(user: UserContext = Depends(get_current_user)) -> list[SchemaResponse]:
    ensure_user_registry_loaded(user)
    registry = _user_registry(user)
    return [
        SchemaResponse(
            schema_id=sid,
            source_files=schema.source_files,
            element_count=len(schema.elements),
            elements=schema.root_elements(),
        )
        for sid, schema in registry.items()
    ]


@router.get("/{schema_id}/elements", response_model=list[ElementSummary])
async def list_elements(
    schema_id: str,
    user: UserContext = Depends(get_current_user),
) -> list[ElementSummary]:
    schema = _get_schema(user, schema_id)
    return [_element_to_summary(elem) for elem in schema.elements.values()]


@router.get("/{schema_id}/elements/{element_name}", response_model=ElementDetailResponse)
async def get_element(
    schema_id: str,
    element_name: str,
    user: UserContext = Depends(get_current_user),
) -> ElementDetailResponse:
    schema = _get_schema(user, schema_id)
    if element_name not in schema.elements:
        raise HTTPException(
            status_code=404, detail=f"Element '{element_name}' not found"
        )
    return ElementDetailResponse(
        schema_id=schema_id,
        element=_element_to_summary(schema.elements[element_name]),
    )


@router.get("/{schema_id}/elements/{element_name}/tree")
async def get_element_tree(
    schema_id: str,
    element_name: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, Any]:
    schema = _get_schema(user, schema_id)
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


def _get_schema(user: UserContext, schema_id: str) -> DTDSchema:
    ensure_user_registry_loaded(user)
    registry = _user_registry(user)
    if schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' not found")
    return registry[schema_id]


def get_schema_registry(user: UserContext) -> dict[str, DTDSchema]:
    """Expose registry for other modules."""
    ensure_user_registry_loaded(user)
    return _user_registry(user)
