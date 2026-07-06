"""XML data fill endpoints — two-stage hybrid pipeline."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.routes.dtd import get_schema_registry
from app.api.routes.generate import get_last_generated, set_last_generated
from app.auth.sessions import get_current_user
from app.config import resolve_llm_alias
from app.core.xml_tree import ProtectedAttrs
from app.services.db_service import SqlMapping, apply_db_overrides
from app.services.field_override_service import FieldOverride, apply_field_overrides
from app.services.field_mapping_service import suggest_field_mappings as suggest_field_mappings_service
from app.services.faker_service import populate_with_faker
from app.services.llm_service import populate_with_llm
from app.user_context import UserContext

router = APIRouter(prefix="/fill", tags=["fill"])
logger = logging.getLogger(__name__)

# fmt: off
Strategy = Literal[
    "faker",
    "ai",
    "hybrid_db_faker",
    "hybrid_db_ai",
]
# fmt: on

_HYBRID = frozenset({"hybrid_db_faker", "hybrid_db_ai"})

ProgressCallback = Callable[[str, str, int], Awaitable[None]]


class FillRequest(BaseModel):
    schema_id: str
    xml_text: str | None = None
    strategy: Strategy = "faker"
    sql_mappings: list[SqlMapping] = Field(default_factory=list)
    field_overrides: list[FieldOverride] = Field(default_factory=list)
    llm_alias: str = "default"
    faker_locale: str = "ru_RU"


class FillResponse(BaseModel):
    xml_text: str
    strategy: str
    warnings: list[str] = Field(default_factory=list)


class XmlCacheRequest(BaseModel):
    schema_id: str
    xml_text: str


class FieldMappingPair(BaseModel):
    db_col: str = ""
    xml_attr: str = ""


class SuggestFieldMappingsRequest(BaseModel):
    schema_id: str
    target_element: str
    columns: list[str] = Field(default_factory=list)
    existing_mappings: list[FieldMappingPair] = Field(default_factory=list)
    llm_alias: str = "default"


class SuggestFieldMappingsResponse(BaseModel):
    mappings: list[FieldMappingPair]
    matcher: str


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
    user: UserContext,
    request: FillRequest,
    on_progress: ProgressCallback = _noop_progress,
    cancel_event: asyncio.Event | None = None,
) -> tuple[str, list[str]]:
    resolved_llm = resolve_llm_alias(user, request.llm_alias)

    registry = get_schema_registry(user)
    if request.schema_id not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_id}' not found",
        )

    schema = registry[request.schema_id]
    await on_progress("started", "Preparing fill request...", 0)

    xml = (request.xml_text or "").strip() or get_last_generated(user, request.schema_id)
    if not xml:
        raise HTTPException(
            status_code=400,
            detail="xml_text is required when no generated XML is cached on the server",
        )
    protected_attrs: ProtectedAttrs = frozenset()
    fill_warnings: list[str] = []

    if request.strategy in _HYBRID:
        active_mappings = _validate_hybrid_mappings(request)
        await on_progress("db_query", "Querying database...", 10)
        try:
            xml, protected_attrs, fill_warnings = await apply_db_overrides(
                user,
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

    active_overrides = [
        o
        for o in request.field_overrides
        if o.target_path.strip() and o.xml_attr.strip()
    ]
    if active_overrides:
        await on_progress("manual_overrides", "Applying fixed field values...", 38)
        xml, manual_protected, manual_warnings = await asyncio.to_thread(
            apply_field_overrides,
            xml,
            active_overrides,
        )
        protected_attrs = protected_attrs | manual_protected
        fill_warnings.extend(manual_warnings)
        for warning in manual_warnings:
            await on_progress("manual_warning", warning, 38)

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

            async def llm_progress(step: str, message: str, percent: int) -> None:
                await on_progress(step, message, percent)

            result = await populate_with_llm(
                xml,
                schema,
                user,
                alias=resolved_llm,
                fill_empty_only=fill_empty_only,
                protected_attrs=protected_attrs,
                on_progress=llm_progress,
                progress_base=llm_percent,
                progress_span=50 if request.strategy == "hybrid_db_ai" else 75,
                cancel_event=cancel_event,
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
    except asyncio.CancelledError:
        raise
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
            resolved_llm,
            exc,
        )
        raise HTTPException(
            status_code=422,
            detail=f"{stage} stage failed: {exc}",
        ) from exc

    set_last_generated(user, request.schema_id, result)
    return result, fill_warnings


@router.post("/suggest-field-mappings", response_model=SuggestFieldMappingsResponse)
async def suggest_field_mappings_route(
    request: SuggestFieldMappingsRequest,
    user: UserContext = Depends(get_current_user),
) -> SuggestFieldMappingsResponse:
    registry = get_schema_registry(user)
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
    resolved_llm = resolve_llm_alias(user, request.llm_alias)

    try:
        mappings, matcher = await suggest_field_mappings_service(
            schema,
            target_element,
            columns,
            user,
            existing_pairs=existing,
            llm_alias=resolved_llm,
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
async def fill_xml(
    request: FillRequest,
    user: UserContext = Depends(get_current_user),
) -> FillResponse:
    try:
        result, warnings = await execute_fill(user, request)
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


@router.put("/xml-cache")
async def stage_xml_cache(
    request: XmlCacheRequest,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    registry = get_schema_registry(user)
    if request.schema_id not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_id}' not found",
        )

    xml = request.xml_text.strip()
    if not xml:
        raise HTTPException(status_code=400, detail="xml_text cannot be empty")

    set_last_generated(user, request.schema_id, xml)
    logger.debug(
        "Staged XML cache [user=%s schema_id=%s chars=%d]",
        user.display_name,
        request.schema_id,
        len(xml),
    )
    return {"status": "ok"}


def _sse_event(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_SSE_KEEPALIVE_SEC = 2.0


@router.post("/stream")
async def fill_xml_stream(
    request: FillRequest,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    queue.put_nowait({"step": "started", "message": "Preparing fill request...", "percent": 0})
    cancel_event = asyncio.Event()

    async def on_progress(step: str, message: str, percent: int) -> None:
        if step == "started":
            return
        await queue.put({"step": step, "message": message, "percent": percent})

    async def run_fill() -> None:
        try:
            result, warnings = await execute_fill(user, request, on_progress, cancel_event)
            await queue.put({
                "step": "complete",
                "xml_text": result,
                "percent": 100,
                "warnings": warnings,
            })
        except asyncio.CancelledError:
            await queue.put({"step": "cancelled", "message": "Fill cancelled"})
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
        await asyncio.sleep(0)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SEC)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0)
                    continue
                if event is None:
                    break
                yield _sse_event(event)
                await asyncio.sleep(0)
        finally:
            cancel_event.set()
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
