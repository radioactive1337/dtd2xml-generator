"""XML data fill endpoints — two-stage hybrid pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.routes.dtd import get_schema_registry
from app.api.routes.generate import get_last_generated, set_last_generated
from app.config import resolve_llm_alias
from app.core.xml_tree import ProtectedAttrs
from app.services.db_service import SqlMapping, apply_db_overrides
from app.services.field_mapping_service import suggest_field_mappings as suggest_field_mappings_service
from app.services.faker_service import populate_with_faker
from app.services.llm_service import populate_with_llm

router = APIRouter(prefix="/fill", tags=["fill"])
logger = logging.getLogger(__name__)

# fmt: off
Strategy = Literal[
    "faker",           # Smart Faker only
    "ai",              # LLM only
    "hybrid_db_faker", # Stage-1: DB overrides  →  Stage-2: Smart Faker fallback
    "hybrid_db_ai",    # Stage-1: DB overrides  →  Stage-2: LLM fallback
]
# fmt: on

_HYBRID = frozenset({"hybrid_db_faker", "hybrid_db_ai"})

ProgressCallback = Callable[[str, str, int], Awaitable[None]]


class FillRequest(BaseModel):
    schema_id: str
    xml_text: str | None = None
    strategy: Strategy = "faker"

    # Hybrid pipeline: DB overrides (Stage 1)
    sql_mappings: list[SqlMapping] = Field(default_factory=list)

    # Fallback engine options (Stage 2)
    llm_alias: str = "default"
    faker_locale: str = "ru_RU"

    @field_validator("llm_alias", mode="before")
    @classmethod
    def _resolve_llm_alias(cls, value: object) -> str:
        return resolve_llm_alias(str(value) if value is not None else None)


class FillResponse(BaseModel):
    xml_text: str
    strategy: str
    warnings: list[str] = Field(default_factory=list)


class FieldMappingPair(BaseModel):
    db_col: str = ""
    xml_attr: str = ""


class SuggestFieldMappingsRequest(BaseModel):
    schema_id: str
    target_element: str
    columns: list[str] = Field(default_factory=list)
    existing_mappings: list[FieldMappingPair] = Field(default_factory=list)
    llm_alias: str = "default"

    @field_validator("llm_alias", mode="before")
    @classmethod
    def _resolve_llm_alias(cls, value: object) -> str:
        return resolve_llm_alias(str(value) if value is not None else None)


class SuggestFieldMappingsResponse(BaseModel):
    mappings: list[FieldMappingPair]
    matcher: str  # "llm" | "fuzzy"


async def _noop_progress(_step: str, _message: str, _percent: int) -> None:
    pass


def _validate_hybrid_mappings(request: FillRequest) -> list[SqlMapping]:
    if not request.sql_mappings:
        raise HTTPException(
            status_code=400,
            detail="sql_mappings cannot be empty for hybrid strategies",
        )
    active_mappings = [
        m
        for m in request.sql_mappings
        if m.query.strip() and m.target_element
    ]
    if not active_mappings:
        raise HTTPException(
            status_code=400,
            detail="sql_mappings must include at least one mapping with query and target_element",
        )
    if any(not m.db_alias for m in active_mappings):
        raise HTTPException(
            status_code=400,
            detail="Each mapping must have db_alias",
        )
    return active_mappings


async def execute_fill(
    request: FillRequest,
    on_progress: ProgressCallback = _noop_progress,
) -> str:
    """Fill XML with test data, optionally emitting progress updates."""
    registry = get_schema_registry()
    if request.schema_id not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_id}' not found",
        )

    schema = registry[request.schema_id]
    await on_progress("started", "Preparing fill request...", 0)

    xml = (request.xml_text or "").strip() or get_last_generated(request.schema_id)
    if not xml:
        raise HTTPException(
            status_code=400,
            detail="xml_text is required when no generated XML is cached on the server",
        )
    protected_attrs: ProtectedAttrs = frozenset()
    fill_warnings: list[str] = []

    # ── Stage 1: DB overrides (hybrid strategies only) ───────────────────
    if request.strategy in _HYBRID:
        active_mappings = _validate_hybrid_mappings(request)
        await on_progress("db_query", "Querying database...", 10)
        try:
            xml, protected_attrs, fill_warnings = await apply_db_overrides(
                xml,
                request.sql_mappings,
            )
        except Exception as exc:
            aliases = sorted({m.db_alias for m in active_mappings if m.db_alias})
            logger.error(
                "Fill DB stage failed [schema_id=%s strategy=%s mappings=%d aliases=%s]: %s",
                request.schema_id,
                request.strategy,
                len(active_mappings),
                aliases,
                exc,
            )
            raise HTTPException(
                status_code=422,
                detail=f"Database stage failed: {exc}",
            ) from exc
        await on_progress("db_done", "Database values applied", 35)
        for warning in fill_warnings:
            await on_progress("db_warning", warning, 35)

    # ── Stage 2: fallback engine for remaining empty fields ───────────────
    fill_empty_only = request.strategy in _HYBRID
    try:
        if request.strategy in ("faker", "hybrid_db_faker"):
            percent = 45 if request.strategy in _HYBRID else 15
            await on_progress(
                "faker",
                "Generating test data with Smart Faker...",
                percent,
            )
            result = await asyncio.to_thread(
                populate_with_faker,
                xml,
                schema,
                locale=request.faker_locale,
                fill_empty_only=fill_empty_only,
                protected_attrs=protected_attrs,
            )
        elif request.strategy in ("ai", "hybrid_db_ai"):
            llm_percent = 40 if request.strategy in _HYBRID else 15
            await on_progress(
                "llm_request",
                "Waiting for LLM response...",
                llm_percent,
            )
            result = await populate_with_llm(
                xml,
                schema,
                alias=request.llm_alias,
                fill_empty_only=fill_empty_only,
                protected_attrs=protected_attrs,
            )
            if request.strategy == "hybrid_db_ai":
                await on_progress(
                    "faker_fallback",
                    "Filling remaining fields with Smart Faker...",
                    90,
                )
                result = await asyncio.to_thread(
                    populate_with_faker,
                    result,
                    schema,
                    locale=request.faker_locale,
                    fill_empty_only=True,
                    protected_attrs=protected_attrs,
                )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {request.strategy!r}")
    except HTTPException:
        raise
    except Exception as exc:
        stage = "LLM" if request.strategy in ("ai", "hybrid_db_ai") else "Faker"
        logger.error(
            "Fill %s stage failed [schema_id=%s strategy=%s locale=%s llm_alias=%s]: %s",
            stage,
            request.schema_id,
            request.strategy,
            request.faker_locale,
            request.llm_alias,
            exc,
        )
        raise HTTPException(
            status_code=422,
            detail=f"{stage} stage failed: {exc}",
        ) from exc

    set_last_generated(request.schema_id, result)
    return result, fill_warnings


@router.post("/suggest-field-mappings", response_model=SuggestFieldMappingsResponse)
async def suggest_field_mappings_route(
    request: SuggestFieldMappingsRequest,
) -> SuggestFieldMappingsResponse:
    """Use LLM (with fuzzy fallback) to map SQL columns to XML attributes."""
    registry = get_schema_registry()
    if request.schema_id not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_id}' not found",
        )

    target_element = request.target_element.strip()
    if not target_element:
        raise HTTPException(status_code=400, detail="target_element is required")

    columns = [col for col in request.columns if col and col.strip()]
    if not columns:
        raise HTTPException(status_code=400, detail="columns cannot be empty")

    schema = registry[request.schema_id]
    existing = [
        {"db_col": pair.db_col, "xml_attr": pair.xml_attr}
        for pair in request.existing_mappings
    ]

    try:
        mappings, matcher = await suggest_field_mappings_service(
            schema,
            target_element,
            columns,
            existing_pairs=existing,
            llm_alias=request.llm_alias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "Field mapping suggestion failed [schema_id=%s element=%s]: %s",
            request.schema_id,
            target_element,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SuggestFieldMappingsResponse(
        mappings=[FieldMappingPair(**row) for row in mappings],
        matcher=matcher,
    )


@router.post("", response_model=FillResponse)
async def fill_xml(request: FillRequest) -> FillResponse:
    """Fill XML with test data using a two-stage hybrid pipeline."""
    try:
        result, warnings = await execute_fill(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Fill failed [schema_id=%s strategy=%s]: %s",
            request.schema_id,
            request.strategy,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FillResponse(xml_text=result, strategy=request.strategy, warnings=warnings)


def _sse_event(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def fill_xml_stream(request: FillRequest) -> StreamingResponse:
    """Fill XML and stream progress updates as Server-Sent Events."""
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    queue.put_nowait({"step": "started", "message": "Preparing fill request...", "percent": 0})

    async def on_progress(step: str, message: str, percent: int) -> None:
        if step == "started":
            return
        await queue.put({"step": step, "message": message, "percent": percent})

    async def run_fill() -> None:
        try:
            result, warnings = await execute_fill(request, on_progress)
            await queue.put({
                "step": "complete",
                "xml_text": result,
                "percent": 100,
                "warnings": warnings,
            })
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            await queue.put({"step": "error", "message": detail, "status": exc.status_code})
        except Exception as exc:
            logger.error(
                "Fill stream failed [schema_id=%s strategy=%s]: %s",
                request.schema_id,
                request.strategy,
                exc,
            )
            await queue.put({"step": "error", "message": str(exc), "status": 422})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_fill())

    async def event_stream():
        yield ": connected\n\n"
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse_event(event)
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
