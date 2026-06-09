"""XML data population endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.routes.dtd import get_schema_registry
from app.services.db_service import populate_with_db
from app.services.faker_service import populate_with_faker
from app.services.llm_service import populate_with_llm

router = APIRouter(prefix="/populate", tags=["populate"])

Strategy = Literal["faker", "llm", "db"]


class PopulateRequest(BaseModel):
    schema_id: str
    xml_text: str
    strategy: Strategy = "faker"
    db_alias: str | None = None
    sql: str | None = None
    llm_alias: str = "default"
    faker_locale: str = "ru_RU"


class PopulateResponse(BaseModel):
    xml_text: str
    strategy: Strategy


@router.post("", response_model=PopulateResponse)
async def populate_xml(request: PopulateRequest) -> PopulateResponse:
    """Populate XML with test data using faker, LLM, or database."""
    registry = get_schema_registry()
    if request.schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{request.schema_id}' not found")

    schema = registry[request.schema_id]

    try:
        if request.strategy == "faker":
            result = populate_with_faker(
                request.xml_text, schema, locale=request.faker_locale
            )
        elif request.strategy == "llm":
            result = await populate_with_llm(
                request.xml_text, schema, alias=request.llm_alias
            )
        elif request.strategy == "db":
            if not request.db_alias or not request.sql:
                raise HTTPException(
                    status_code=400,
                    detail="db_alias and sql are required for db strategy",
                )
            result = await populate_with_db(
                request.xml_text, schema, request.db_alias, request.sql
            )
        else:
            raise HTTPException(status_code=400, detail="Unknown strategy")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PopulateResponse(xml_text=result, strategy=request.strategy)
