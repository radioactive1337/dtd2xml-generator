"""XML data fill endpoints — pipeline (DB / Git reference / AI)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.routes.dtd import get_schema_registry
from app.api.routes.generate import get_last_generated, set_last_generated
from app.auth.sessions import get_current_user
from app.config import reference_xml_root, resolve_llm_alias
from app.core.xml_tree import ProtectedAttrs, prefill_empty_enums
from app.services.attribute_rules_service import validate_document
from app.services.db_service import SqlMapping, apply_db_overrides
from app.services.field_mapping_service import suggest_field_mappings as suggest_field_mappings_service
from app.services.git_reference_fill_service import populate_from_git
from app.services.llm_service import LLMService, populate_with_llm
from app.services.xml_structure_service import peek_root_element
from app.user_context import UserContext

router = APIRouter(prefix="/fill", tags=["fill"])
logger = logging.getLogger(__name__)

# Allow at most this many LLM requests to run concurrently across all users.
# Keeps the LLM backend responsive and prevents a single runaway client from
# starving everyone else.  Adjust via env var LLM_CONCURRENCY if needed.
_LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "5"))
_llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

Strategy = Literal["ai", "db_ai", "git_ai", "git_ai_db"]

_DB_STRATEGIES = frozenset({"db_ai", "git_ai_db"})
_GIT_STRATEGIES = frozenset({"git_ai", "git_ai_db"})

ProgressCallback = Callable[[str, str, int], Awaitable[None]]


def _llm_progress_window(strategy: Strategy) -> tuple[int, int]:
    if strategy == "git_ai_db":
        return 55, 40
    if strategy in _DB_STRATEGIES or strategy in _GIT_STRATEGIES:
        return 45, 50
    return 15, 75


class FillRequest(BaseModel):
    schema_id: str
    xml_text: str | None = None
    strategy: Strategy = "ai"
    sql_mappings: list[SqlMapping] = Field(default_factory=list)
    llm_alias: str = "default"
    preserve_filled: bool = True


class FillResponse(BaseModel):
    xml_text: str
    strategy: str
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)


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
            detail="sql_mappings cannot be empty for DB fill strategies",
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


async def _run_git_reference_stage(
    user: UserContext,
    request: FillRequest,
    xml: str,
    protected_attrs: ProtectedAttrs,
    resolved_llm: str | None,
    on_progress: ProgressCallback,
    cancel_event: asyncio.Event | None = None,
    *,
    progress_percent: int = 15,
) -> tuple[str, ProtectedAttrs, list[str], dict[str, str]]:
    """Best-effort Git reference fill stage; returns updated xml/protected/warnings/provenance."""
    await on_progress("git_reference", "Filling from Git reference library...", progress_percent)

    ref_root = reference_xml_root()
    if ref_root is None:
        return xml, protected_attrs, ["Git reference library is not configured; skipped git fill stage"], {}

    try:
        root_element = peek_root_element(xml)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot detect root element for Git fill: {exc}",
        ) from exc

    llm_client = LLMService(user, alias=resolved_llm) if resolved_llm else None

    registry = get_schema_registry(user)
    schema = registry[request.schema_id]

    try:
        new_xml, git_protected, git_warnings, provenance = await populate_from_git(
            xml,
            schema,
            root=ref_root,
            root_element=root_element,
            fill_empty_only=request.preserve_filled,
            protected_attrs=protected_attrs,
            llm=llm_client,
            allow_ai=True,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
    except Exception as exc:
        logger.error(
            "Fill Git stage failed [schema_id=%s strategy=%s root=%s]: %s",
            request.schema_id,
            request.strategy,
            root_element,
            exc,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Git reference stage failed: {exc}",
        ) from exc

    warn_percent = min(progress_percent + 5, 99)
    for warning in git_warnings:
        await on_progress("git_warning", warning, warn_percent)

    return new_xml, protected_attrs | git_protected, git_warnings, provenance


async def execute_fill(
    user: UserContext,
    request: FillRequest,
    on_progress: ProgressCallback = _noop_progress,
    cancel_event: asyncio.Event | None = None,
) -> tuple[str, list[str], dict[str, str]]:
    try:
        resolved_llm = resolve_llm_alias(user, request.llm_alias)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    xml, enum_prefill_count = prefill_empty_enums(xml, schema)
    if enum_prefill_count:
        await on_progress(
            "enum_prefill",
            f"Заполнено {enum_prefill_count} enum-атрибут(ов) случайным допустимым значением",
            5,
        )

    protected_attrs: ProtectedAttrs = frozenset()
    fill_warnings: list[str] = []
    provenance: dict[str, str] = {}

    if request.strategy in _DB_STRATEGIES:
        active_mappings = _validate_hybrid_mappings(request)
        await on_progress("db_query", "Querying database...", 10)
        try:
            xml, protected_attrs, fill_warnings = await apply_db_overrides(
                user,
                xml,
                request.sql_mappings,
                fill_empty_only=request.preserve_filled,
                schema=schema,
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
        db_done_percent = 25 if request.strategy == "git_ai_db" else 35
        await on_progress("db_done", "Database values applied", db_done_percent)
        for warning in fill_warnings:
            await on_progress("db_warning", warning, db_done_percent)

    if request.strategy in _GIT_STRATEGIES:
        git_percent = 30 if request.strategy == "git_ai_db" else 15
        xml, protected_attrs, git_warnings, provenance = await _run_git_reference_stage(
            user,
            request,
            xml,
            protected_attrs,
            resolved_llm,
            on_progress,
            cancel_event,
            progress_percent=git_percent,
        )
        fill_warnings.extend(git_warnings)

    fill_empty_only = request.preserve_filled
    try:
        llm_percent, llm_span = _llm_progress_window(request.strategy)
        await on_progress(
            "llm_request",
            "Waiting for LLM response...",
            llm_percent,
        )

        async def llm_progress(step: str, message: str, percent: int) -> None:
            if step == "llm_fallback":
                fill_warnings.append(message)
            await on_progress(step, message, percent)

        async with _llm_semaphore:
            result = await populate_with_llm(
                xml,
                schema,
                user,
                alias=resolved_llm,
                fill_empty_only=fill_empty_only,
                protected_attrs=protected_attrs,
                on_progress=llm_progress,
                progress_base=llm_percent,
                progress_span=llm_span,
                cancel_event=cancel_event,
            )
    except asyncio.CancelledError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Fill LLM stage failed [schema_id=%s strategy=%s llm_alias=%s]: %s",
            request.schema_id,
            request.strategy,
            resolved_llm or request.llm_alias,
            exc,
        )
        raise HTTPException(
            status_code=422,
            detail=f"LLM stage failed: {exc}",
        ) from exc

    try:
        post_report = await asyncio.to_thread(validate_document, result, schema, context="post_fill")
        for violation in post_report.warnings + post_report.errors:
            loc = f"{violation.path}@{violation.attr}" if violation.attr else violation.path
            fill_warnings.append(f"[post_fill/{violation.severity}] {loc}: {violation.message}")
    except Exception as exc:
        logger.warning("Post-fill attribute rule validation failed: %s", exc)

    set_last_generated(user, request.schema_id, result)
    return result, fill_warnings, provenance


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
        async with _llm_semaphore:
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
        result, warnings, provenance = await execute_fill(user, request)
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

    return FillResponse(
        xml_text=result,
        strategy=request.strategy,
        warnings=warnings,
        provenance=provenance,
    )


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
            result, warnings, provenance = await execute_fill(
                user, request, on_progress, cancel_event
            )
            await queue.put({
                "step": "complete",
                "xml_text": result,
                "percent": 100,
                "warnings": warnings,
                "provenance": provenance,
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
                    # Send a data: ping rather than an SSE comment. Comments are
                    # ignored by the frontend parser and often buffered by proxies,
                    # which makes git_ai look stuck after a single keepalive.
                    yield _sse_event({"step": "ping"})
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
