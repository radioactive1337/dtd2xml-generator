"""Share personal XML documents between users."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from app.auth.users import (
    UserRecord,
    get_user_by_norm,
    normalize_username,
    suggest_similar_usernames,
    validate_username,
)
from app.user_context import UserContext, user_context_from_record

_SAFE_NAME_RE = re.compile(r"^[\w\-. ()]+$")


class InlineShareDocument(BaseModel):
    name: str
    schema_id: str = ""
    category: str = "free-document"
    description: str = ""
    xml_text: str = ""


class ShareDocumentRequest(BaseModel):
    recipient_username: str
    source_document_name: str | None = None
    document: InlineShareDocument | None = None
    message: str = ""


class ShareDocumentResponse(BaseModel):
    recipient_display_name: str
    document_name: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(name: str) -> str:
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid document name")
    return name


def _personal_path(user: UserContext, name: str) -> Path:
    user.xml_documents_dir.mkdir(parents=True, exist_ok=True)
    return user.xml_documents_dir / f"{_safe_name(name)}.json"


def _load_personal_document(user: UserContext, name: str) -> dict:
    path = _personal_path(user, name)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Personal document '{name}' not found",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_names(user: UserContext) -> set[str]:
    user.xml_documents_dir.mkdir(parents=True, exist_ok=True)
    return {path.stem for path in user.xml_documents_dir.glob("*.json")}


def _resolve_document_name(
    base_name: str,
    sender_name: str,
    existing: set[str],
) -> str:
    if base_name not in existing:
        return base_name
    candidate = f"{base_name} (от {sender_name})"
    if candidate not in existing:
        return candidate
    n = 2
    while True:
        candidate = f"{base_name} (от {sender_name}) ({n})"
        if candidate not in existing:
            return candidate
        n += 1


def _resolve_recipient(username: str) -> UserRecord:
    try:
        display = validate_username(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = get_user_by_norm(normalize_username(display))
    if record is None:
        suggestions = suggest_similar_usernames(display)
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"User '{display}' not found",
                "suggestions": suggestions,
            },
        )
    return record


def _build_description(original: str, message: str) -> str:
    original = (original or "").strip()
    message = (message or "").strip()
    if original and message:
        return f"{original}\n\n{message}"
    return original or message


def share_document(
    sender: UserContext,
    request: ShareDocumentRequest,
) -> ShareDocumentResponse:
    if not request.source_document_name and request.document is None:
        raise HTTPException(
            status_code=400,
            detail="Either source_document_name or document must be provided",
        )

    recipient_record = _resolve_recipient(request.recipient_username)
    if recipient_record.id == sender.user_id:
        raise HTTPException(status_code=400, detail="Cannot share a document with yourself")

    if request.source_document_name:
        source = _load_personal_document(sender, request.source_document_name)
    else:
        source = request.document.model_dump()
        if not source.get("xml_text"):
            raise HTTPException(status_code=400, detail="Document xml_text is required")

    recipient = user_context_from_record(recipient_record)
    base_name = _safe_name(str(source.get("name", "")).strip())
    resolved_name = _resolve_document_name(
        base_name,
        sender.display_name,
        _existing_names(recipient),
    )
    now = _utc_now()
    payload = {
        "name": resolved_name,
        "schema_id": source.get("schema_id", ""),
        "category": source.get("category", "free-document"),
        "description": _build_description(source.get("description", ""), request.message),
        "created_at": now,
        "updated_at": now,
        "xml_text": source.get("xml_text", ""),
        "shared_by_id": sender.user_id,
        "shared_by_name": sender.display_name,
        "shared_at": now,
    }
    path = _personal_path(recipient, resolved_name)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ShareDocumentResponse(
        recipient_display_name=recipient.display_name,
        document_name=resolved_name,
    )
