"""XML export endpoints."""

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.routes.generate import get_last_generated

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/xml")
async def export_xml(
    schema_id: str = Query(...),
    filename: str = Query(default="generated.xml"),
    xml_text: str | None = Query(default=None),
) -> StreamingResponse:
    """Download generated XML as a file attachment."""
    content = xml_text or get_last_generated(schema_id)
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
