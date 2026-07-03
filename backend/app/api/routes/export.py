"""XML export endpoints."""

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.routes.generate import get_last_generated
from app.auth.sessions import get_current_user
from app.user_context import UserContext

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/xml")
async def export_xml(
    schema_id: str = Query(...),
    filename: str = Query(default="generated.xml"),
    xml_text: str | None = Query(default=None),
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    content = xml_text or get_last_generated(user, schema_id)
    if not content:
        raise HTTPException(
            status_code=404,
            detail="No XML found. Generate XML first or pass xml_text parameter.",
        )

    if not filename.endswith(".xml"):
        filename = f"{filename}.xml"

    buffer = BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        buffer,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
