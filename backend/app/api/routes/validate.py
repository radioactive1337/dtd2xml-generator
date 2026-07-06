"""XML DTD validation endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.routes.dtd import get_merged_schema
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
    schema = get_merged_schema(user, request.schema_id)
    return await asyncio.to_thread(validate_xml, request.xml_text, schema)
