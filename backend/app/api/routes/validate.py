"""XML DTD validation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.routes.dtd import get_schema_registry
from app.core.dtd_validator import ValidationResult, validate_xml

router = APIRouter(prefix="/validate", tags=["validate"])


class ValidateRequest(BaseModel):
    schema_id: str
    xml_text: str


@router.post("", response_model=ValidationResult)
async def validate_xml_against_dtd(request: ValidateRequest) -> ValidationResult:
    """Validate XML text against a registered DTD schema."""
    registry = get_schema_registry()
    if request.schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{request.schema_id}' not found")

    schema = registry[request.schema_id]
    return validate_xml(request.xml_text, schema)
