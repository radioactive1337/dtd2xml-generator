"""DTD upload and schema introspection endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.auth.sessions import get_current_user
from app.config import DATA_DIR, PROJECT_ROOT, get_nexus_dtd_config, shared_dtd_dir
from app.core.dtd_archive import extract_jar_dtd_files
from app.core.dtd_merge import merge_dtd_schemas
from app.core.dtd_models import DTDSchema, ElementDef
from app.core.dtd_parser import DTDParser
from app.services.nexus_dtd_service import fetch_jar_bytes, resolve_jar_url
from app.user_context import UserContext

router = APIRouter(prefix="/dtd", tags=["dtd"])
logger = logging.getLogger(__name__)

DTD_EXTENSIONS = (".dtd", ".ent", ".mod")

_MAX_DTD_FILE_BYTES = 2 * 1024 * 1024   # 2 MB per DTD file
_MAX_JAR_FILE_BYTES = 50 * 1024 * 1024  # 50 MB for JAR archive


async def _read_upload_limited(file: UploadFile, max_bytes: int, label: str) -> bytes:
    """Read an uploaded file, refusing payloads that exceed *max_bytes*.

    Reads at most ``max_bytes + 1`` bytes from the stream so oversized uploads
    never fully land in RAM before we reject them.
    """
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds maximum allowed size ({max_bytes // (1024 * 1024)} MB)",
        )
    return data


# schema_id -> DTDSchema (shared across all users)
_schema_registry: dict[str, DTDSchema] = {}

# Legacy export for tests
DTD_SCHEMA_DIR: Path | None = None

_IMPORT_META_FILE = "import_meta.json"


def _migration_flag_path() -> Path:
    return DATA_DIR / ".dtd_shared_migrated"


def _dtd_dir() -> Path:
    return shared_dtd_dir()


def _registry() -> dict[str, DTDSchema]:
    return _schema_registry


def _user_registry(_user: UserContext | None = None) -> dict[str, DTDSchema]:
    """Backward-compatible alias used by tests."""
    return _registry()


class DtdImportMeta(BaseModel):
    import_source: str
    updated_at: str
    updated_by: str | None = None


def _read_import_meta() -> DtdImportMeta | None:
    meta_path = _dtd_dir() / _IMPORT_META_FILE
    if not meta_path.is_file():
        return None
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        return DtdImportMeta(**raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_import_meta(
    import_source: str,
    *,
    updated_by: str | None = None,
) -> DtdImportMeta:
    meta = DtdImportMeta(
        import_source=import_source,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=updated_by,
    )
    (_dtd_dir() / _IMPORT_META_FILE).write_text(
        json.dumps(meta.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta


def _import_meta_fields() -> dict[str, str | None]:
    meta = _read_import_meta()
    if meta is None:
        return {"import_source": None, "updated_at": None}
    return {
        "import_source": meta.import_source,
        "updated_at": meta.updated_at,
    }


def _dir_has_dtd_files(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    return any(
        path.is_file() and path.suffix.lower() in DTD_EXTENSIONS
        for path in directory.iterdir()
    )


def _copy_dtd_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if not item.is_file():
            continue
        target = dst / item.name
        if not target.exists():
            shutil.copy2(item, target)


def _maybe_migrate_to_shared_dtd() -> None:
    """One-time copy of legacy per-user or project-root DTD files into shared storage."""
    flag = _migration_flag_path()
    if flag.is_file():
        return

    shared = _dtd_dir()
    if _dir_has_dtd_files(shared):
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("already_shared\n", encoding="utf-8")
        return

    candidates: list[Path] = [PROJECT_ROOT / "dtd_schemas"]
    users_root = DATA_DIR / "users"
    if users_root.is_dir():
        for user_dir in sorted(users_root.iterdir()):
            user_dtd = user_dir / "dtd_schemas"
            if _dir_has_dtd_files(user_dtd):
                candidates.append(user_dtd)

    for candidate in candidates:
        if _dir_has_dtd_files(candidate):
            _copy_dtd_tree(candidate, shared)
            logger.info("Migrated DTD schemas to shared storage from %s", candidate)
            break

    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("done\n", encoding="utf-8")


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
    dtd_path: Path,
    schema_id: str | None = None,
) -> str:
    parser = DTDParser(base_dir=_dtd_dir())
    schema = parser.parse_file(dtd_path)

    sid = schema_id or _read_schema_id(dtd_path) or str(uuid.uuid4())
    _write_schema_id(dtd_path, sid)
    _registry()[sid] = schema
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


def _parse_entry_points(
    entry_paths: list[Path],
    *,
    available_basenames: set[str],
) -> list[str]:
    schema_ids: list[str] = []
    keep_basenames: set[str] = set()
    keep_schema_ids: set[str] = set()

    for entry_path in entry_paths:
        _validate_dtd_references(entry_path, available_basenames)
        schema_id = _parse_and_register(
            entry_path,
            schema_id=_read_schema_id(entry_path),
        )
        schema = _registry()[schema_id]
        schema_ids.append(schema_id)
        keep_schema_ids.add(schema_id)
        keep_basenames.update(_source_basenames(schema))

    _cleanup_schema_storage(
        keep_basenames=keep_basenames,
        keep_schema_ids=keep_schema_ids,
    )
    return schema_ids


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
    registry = _registry()
    for schema_id in list(registry):
        if schema_id not in keep_schema_ids:
            del registry[schema_id]

    schema_dir = _dtd_dir()
    if not schema_dir.is_dir():
        return

    for path in list(schema_dir.iterdir()):
        if not path.is_file():
            continue

        if path.name == _IMPORT_META_FILE:
            continue

        if path.name.endswith(".schema_id"):
            original_name = path.name[: -len(".schema_id")]
            if original_name not in keep_basenames:
                path.unlink()
            continue

        if path.suffix.lower() in DTD_EXTENSIONS and path.name not in keep_basenames:
            _delete_schema_artifacts(path)


def ensure_user_registry_loaded(_user: UserContext | None = None) -> int:
    """Scan shared dtd_schemas/ and load all entry points if registry is empty."""
    _maybe_migrate_to_shared_dtd()
    registry = _registry()
    if registry:
        return len(registry)

    schema_dir = _dtd_dir()
    entry_points = _entry_point_paths(schema_dir)
    if not entry_points:
        return 0

    available_basenames = {
        path.name for path in schema_dir.iterdir() if path.is_file()
    }
    loaded = 0

    try:
        schema_ids = _parse_entry_points(
            entry_points,
            available_basenames=available_basenames,
        )
        loaded = len(schema_ids)
    except Exception:
        logger.exception("Failed to load DTD schemas from shared storage")
        return 0

    for schema_id in schema_ids:
        primary_name = next(
            (
                Path(path).name
                for path in registry[schema_id].source_files
                if Path(path).suffix.lower() == ".dtd"
            ),
            schema_id,
        )
        logger.info(
            "Loaded DTD schema from disk [file=%s schema_id=%s]",
            primary_name,
            schema_id,
        )
    return loaded


def initialize_schema_registry() -> int:
    """Legacy startup hook — no-op; registry loads lazily on first access."""
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


class MultiSchemaResponse(BaseModel):
    schemas: list[SchemaResponse]
    primary_schema_id: str
    import_source: str | None = None
    updated_at: str | None = None


class SchemaListResponse(BaseModel):
    schemas: list[SchemaResponse]
    import_source: str | None = None
    updated_at: str | None = None


class NexusDtdConfigResponse(BaseModel):
    configured: bool
    artifact_id: str | None = None
    version: str | None = None


def _pick_primary_schema_id(schemas: list[SchemaResponse]) -> str:
    if not schemas:
        raise ValueError("schemas must not be empty")
    for preferred in ("main.dtd", "v2.dtd"):
        for schema in schemas:
            if any(Path(path).name.lower() == preferred for path in schema.source_files):
                return schema.schema_id
    return max(schemas, key=lambda schema: schema.element_count).schema_id


def _known_element_names(schema: DTDSchema) -> list[str]:
    return sorted(schema.elements)


def _schema_response(schema_id: str) -> SchemaResponse:
    schema = _registry()[schema_id]
    return SchemaResponse(
        schema_id=schema_id,
        source_files=schema.source_files,
        element_count=len(schema.elements),
        elements=_known_element_names(schema),
    )


def _multi_schema_response(schema_ids: list[str]) -> MultiSchemaResponse:
    schemas = [_schema_response(schema_id) for schema_id in schema_ids]
    return MultiSchemaResponse(
        schemas=schemas,
        primary_schema_id=_pick_primary_schema_id(schemas),
        **_import_meta_fields(),
    )


async def _extract_and_parse_jar(
    jar_bytes: bytes,
    *,
    inner_path: str,
) -> list[str]:
    extracted = extract_jar_dtd_files(jar_bytes, _dtd_dir(), prefix=inner_path)
    entry_points = _entry_point_paths(_dtd_dir())
    if not entry_points:
        raise HTTPException(
            status_code=404,
            detail=f"No .dtd entry points found in {inner_path}",
        )

    available_basenames = set(extracted)
    try:
        return await asyncio.to_thread(
            _parse_entry_points,
            entry_points,
            available_basenames=available_basenames,
        )
    except FileNotFoundError as exc:
        logger.warning("DTD file not found during JAR parse: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "DTD parsing failed [entries=%s size=%d]",
            [path.name for path in entry_points],
            len(jar_bytes),
        )
        raise HTTPException(
            status_code=422, detail=f"DTD parsing failed: {exc}"
        ) from exc


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


@router.post("/upload", response_model=MultiSchemaResponse)
async def upload_dtd(
    files: list[UploadFile] = File(...),
    user: UserContext = Depends(get_current_user),
) -> MultiSchemaResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    if len(files) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 DTD files per upload")

    for upload in files:
        if not upload.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        filename = Path(upload.filename).name
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        if filename.startswith("."):
            raise HTTPException(status_code=400, detail="Invalid filename")
        if not filename.lower().endswith(".dtd"):
            raise HTTPException(
                status_code=400,
                detail="Only .dtd files are supported (up to 3 at once)",
            )

    _dtd_dir().mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for upload in files:
        filename = Path(upload.filename).name
        content = await _read_upload_limited(
            upload, _MAX_DTD_FILE_BYTES, filename
        )
        saved_path = _dtd_dir() / filename
        async with aiofiles.open(saved_path, "wb") as f:
            await f.write(content)
        saved_paths.append(saved_path)

    available_basenames = {
        path.name for path in _dtd_dir().iterdir() if path.is_file()
    }

    try:
        schema_ids = await asyncio.to_thread(
            _parse_entry_points,
            saved_paths,
            available_basenames=available_basenames,
        )
    except FileNotFoundError as exc:
        logger.warning("DTD file not found during parse: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("DTD parsing failed [files=%s]", [path.name for path in saved_paths])
        raise HTTPException(
            status_code=422, detail=f"DTD parsing failed: {exc}"
        ) from exc

    file_names = ", ".join(Path(upload.filename).name for upload in files)
    _write_import_meta(
        f"Загрузка: {file_names}",
        updated_by=user.display_name,
    )
    return _multi_schema_response(schema_ids)


@router.post("/upload-jar", response_model=MultiSchemaResponse)
async def upload_dtd_jar(
    file: UploadFile = File(...),
    inner_path: str = Form("META-INF/dtd/"),
    user: UserContext = Depends(get_current_user),
) -> MultiSchemaResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not file.filename.lower().endswith(".jar"):
        raise HTTPException(status_code=400, detail="Only .jar files are supported")

    _dtd_dir().mkdir(parents=True, exist_ok=True)
    jar_bytes = await _read_upload_limited(
        file, _MAX_JAR_FILE_BYTES, file.filename or "JAR file"
    )

    try:
        schema_ids = await _extract_and_parse_jar(
            jar_bytes,
            inner_path=inner_path,
        )
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid JAR archive") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _write_import_meta(
        f"JAR: {file.filename}",
        updated_by=user.display_name,
    )
    return _multi_schema_response(schema_ids)


@router.get("/nexus-config", response_model=NexusDtdConfigResponse)
async def get_nexus_config() -> NexusDtdConfigResponse:
    cfg = get_nexus_dtd_config()
    if cfg is None:
        return NexusDtdConfigResponse(configured=False)
    return NexusDtdConfigResponse(
        configured=True,
        artifact_id=cfg.artifact_id,
        version=cfg.version,
    )


@router.post("/pull-nexus", response_model=MultiSchemaResponse)
async def pull_dtd_from_nexus(
    user: UserContext = Depends(get_current_user),
) -> MultiSchemaResponse:
    cfg = get_nexus_dtd_config()
    if cfg is None:
        raise HTTPException(status_code=404, detail="nexus_dtd is not configured")

    _dtd_dir().mkdir(parents=True, exist_ok=True)

    try:
        jar_url, resolved_version = await resolve_jar_url(cfg)
        jar_bytes = await fetch_jar_bytes(jar_url)
    except httpx.HTTPStatusError as exc:
        detail = (
            "Nexus artifact request failed: "
            f"HTTP {exc.response.status_code} ({exc.request.url})"
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Nexus request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        schema_ids = await _extract_and_parse_jar(
            jar_bytes,
            inner_path=cfg.inner_path,
        )
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=502, detail="Nexus artifact is not a valid JAR") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    version_label = resolved_version or cfg.version or "LATEST"
    _write_import_meta(
        f"Nexus {cfg.artifact_id}:{version_label}",
        updated_by=user.display_name,
    )
    logger.info(
        "DTD schemas pulled from Nexus [user=%s artifact=%s version=%s]",
        user.display_name,
        cfg.artifact_id,
        resolved_version,
    )
    return _multi_schema_response(schema_ids)


@router.get("/schemas", response_model=SchemaListResponse)
async def list_schemas(user: UserContext = Depends(get_current_user)) -> SchemaListResponse:
    ensure_user_registry_loaded(user)
    registry = _registry()
    return SchemaListResponse(
        schemas=[
            SchemaResponse(
                schema_id=sid,
                source_files=schema.source_files,
                element_count=len(schema.elements),
                elements=_known_element_names(schema),
            )
            for sid, schema in registry.items()
        ],
        **_import_meta_fields(),
    )


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


def _get_schema(_user: UserContext, schema_id: str) -> DTDSchema:
    ensure_user_registry_loaded(_user)
    registry = _registry()
    if schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' not found")
    return registry[schema_id]


def get_schema_registry(user: UserContext | None = None) -> dict[str, DTDSchema]:
    """Expose registry for other modules."""
    ensure_user_registry_loaded(user)
    return _registry()


def get_merged_schema(user: UserContext, schema_id: str) -> DTDSchema:
    """Return a schema that includes elements from all loaded DTD entry points."""
    registry = get_schema_registry(user)
    if schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' not found")
    return merge_dtd_schemas(list(registry.values()))
