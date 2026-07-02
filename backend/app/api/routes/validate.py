"""XML DTD validation endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.routes.dtd import get_schema_registry
from app.auth.sessions import get_current_user
from app.core.dtd_validator import ValidationResult, validate_xml
from app.user_context import UserContext

router = APIRouter(prefix="/validate", tags=["validate"])


class ValidateRequest(BaseModel):
    schema_id: str
    xml_text: str


@router.post("", response_model=ValidationResult)
async def validate_xml_against_dtd(
    request: ValidateRequest,
    user: UserContext = Depends(get_current_user),
) -> ValidationResult:
    registry = get_schema_registry(user)
    if request.schema_id not in registry:
        raise HTTPException(status_code=404, detail=f"Schema '{request.schema_id}' not found")

    schema = registry[request.schema_id]
    return await asyncio.to_thread(validate_xml, request.xml_text, schema)
