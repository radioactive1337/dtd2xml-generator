"""XML data population endpoints — two-stage hybrid pipeline."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.routes.dtd import get_schema_registry
from app.core.xml_tree import ProtectedAttrs
from app.services.db_service import SqlMapping, apply_db_overrides
from app.services.faker_service import populate_with_faker
from app.services.llm_service import populate_with_llm

router = APIRouter(prefix="/populate", tags=["populate"])

# fmt: off
Strategy = Literal[
    "faker",           # Smart Faker only
    "ai",              # LLM only
    "hybrid_db_faker", # Stage-1: DB overrides  →  Stage-2: Smart Faker fallback
    "hybrid_db_ai",    # Stage-1: DB overrides  →  Stage-2: LLM fallback
]
# fmt: on

_HYBRID = frozenset({"hybrid_db_faker", "hybrid_db_ai"})


class PopulateRequest(BaseModel):
    schema_id: str
    xml_text: str
    strategy: Strategy = "faker"

    # Hybrid pipeline: DB overrides (Stage 1)
    sql_mappings: list[SqlMapping] = Field(default_factory=list)
    db_alias: str | None = None

    # Fallback engine options (Stage 2)
    llm_alias: str = "default"
    faker_locale: str = "ru_RU"


class PopulateResponse(BaseModel):
    xml_text: str
    strategy: str


@router.post("", response_model=PopulateResponse)
async def populate_xml(request: PopulateRequest) -> PopulateResponse:
    """Populate XML with test data using a two-stage hybrid pipeline.

    Stage 1 (DB overrides) runs only for hybrid strategies and fills the
    attributes declared in *sql_mappings* with real database values.

    Stage 2 (fallback engine) fills every remaining empty attribute using
    either Smart Faker or LLM, depending on the chosen strategy.
    """
    registry = get_schema_registry()
    if request.schema_id not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_id}' not found",
        )

    schema = registry[request.schema_id]

    try:
        xml = request.xml_text
        protected_attrs: ProtectedAttrs = frozenset()

        # ── Stage 1: DB overrides (hybrid strategies only) ───────────────────
        if request.strategy in _HYBRID:
            if not request.db_alias:
                raise HTTPException(
                    status_code=400,
                    detail="db_alias is required for hybrid strategies",
                )
            if not request.sql_mappings:
                raise HTTPException(
                    status_code=400,
                    detail="sql_mappings cannot be empty for hybrid strategies",
                )
            try:
                xml, protected_attrs = await apply_db_overrides(
                    xml,
                    request.sql_mappings,
                    request.db_alias,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Database stage failed: {exc}",
                ) from exc

        # ── Stage 2: fallback engine for remaining empty fields ───────────────
        fill_empty_only = request.strategy in _HYBRID
        try:
            if request.strategy in ("faker", "hybrid_db_faker"):
                result = populate_with_faker(
                    xml,
                    schema,
                    locale=request.faker_locale,
                    fill_empty_only=fill_empty_only,
                    protected_attrs=protected_attrs,
                )
            elif request.strategy in ("ai", "hybrid_db_ai"):
                result = await populate_with_llm(
                    xml,
                    schema,
                    alias=request.llm_alias,
                    fill_empty_only=fill_empty_only,
                    protected_attrs=protected_attrs,
                )
                result = populate_with_faker(
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
            raise HTTPException(
                status_code=422,
                detail=f"{stage} stage failed: {exc}",
            ) from exc

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PopulateResponse(xml_text=result, strategy=request.strategy)
