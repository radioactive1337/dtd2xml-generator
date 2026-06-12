"""Database introspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.db_service import DBService

router = APIRouter(prefix="/db", tags=["db"])


class QueryColumnsRequest(BaseModel):
    db_alias: str
    query: str


class QueryColumnsResponse(BaseModel):
    columns: list[str]


@router.post("/query-columns", response_model=QueryColumnsResponse)
async def query_columns(request: QueryColumnsRequest) -> QueryColumnsResponse:
    """Return result column names for a SQL query without fetching row data."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="SQL query is required")

    try:
        columns = await DBService().get_query_columns(request.db_alias, query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Query failed: {exc}") from exc

    return QueryColumnsResponse(columns=columns)
