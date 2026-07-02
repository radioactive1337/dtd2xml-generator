"""Database introspection endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.sessions import get_current_user
from app.core.logging_config import truncate
from app.services.db_service import DBService
from app.user_context import UserContext

router = APIRouter(prefix="/db", tags=["db"])
logger = logging.getLogger(__name__)


class QueryColumnsRequest(BaseModel):
    db_alias: str
    query: str


class QueryColumnsResponse(BaseModel):
    columns: list[str]


class QueryPreviewRequest(BaseModel):
    db_alias: str
    query: str


class QueryPreviewResponse(BaseModel):
    columns: list[str]
    row: dict[str, object] | None = None


@router.post("/query-preview", response_model=QueryPreviewResponse)
async def query_preview(
    request: QueryPreviewRequest,
    user: UserContext = Depends(get_current_user),
) -> QueryPreviewResponse:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="SQL query is required")

    db = DBService(user)
    try:
        rows = await db.run_query(request.db_alias, query)
    except ValueError as exc:
        logger.warning(
            "Query preview validation failed [alias=%s query=%s]: %s",
            request.db_alias,
            truncate(query),
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "Query preview failed [alias=%s query=%s]: %s",
            request.db_alias,
            truncate(query),
            exc,
        )
        raise HTTPException(status_code=422, detail=f"Query failed: {exc}") from exc

    if not rows:
        columns = await db.get_query_columns(request.db_alias, query)
        return QueryPreviewResponse(columns=columns, row=None)

    row = rows[0]
    columns = list(row.keys())
    return QueryPreviewResponse(columns=columns, row=row)


@router.post("/query-columns", response_model=QueryColumnsResponse)
async def query_columns(
    request: QueryColumnsRequest,
    user: UserContext = Depends(get_current_user),
) -> QueryColumnsResponse:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="SQL query is required")

    db = DBService(user)
    try:
        columns = await db.get_query_columns(request.db_alias, query)
    except ValueError as exc:
        logger.warning(
            "Query columns validation failed [alias=%s query=%s]: %s",
            request.db_alias,
            truncate(query),
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "Query columns failed [alias=%s query=%s]: %s",
            request.db_alias,
            truncate(query),
            exc,
        )
        raise HTTPException(status_code=422, detail=f"Query failed: {exc}") from exc

    return QueryColumnsResponse(columns=columns)
