"""DTD upload and schema introspection endpoints."""

from __future__ import annotations

import logging
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

# In-memory schema registry (Phase 1; persistent storage in later phases)
_schema_registry: dict[str, DTDSchema] = {}


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

    if not file.filename.lower().endswith((".dtd", ".ent", ".mod")):
        raise HTTPException(
            status_code=400,
            detail="Only .dtd, .ent, and .mod files are supported",
        )

    schema_dir = PROJECT_ROOT / "dtd_schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)

    saved_path = schema_dir / file.filename
    content = await file.read()

    async with aiofiles.open(saved_path, "wb") as f:
        await f.write(content)

    try:
        parser = DTDParser(base_dir=schema_dir)
        schema = parser.parse_file(saved_path)
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

    schema_id = str(uuid.uuid4())
    _schema_registry[schema_id] = schema

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
