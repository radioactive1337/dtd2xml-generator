"""Share mapping and tree presets between users."""

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

_SAFE_NAME_RE = re.compile(r"^[\w\-. ]+$")


class SharePresetRequest(BaseModel):
    recipient_username: str
    source_preset_name: str
    message: str = ""


class SharePresetResponse(BaseModel):
    recipient_display_name: str
    preset_name: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(name: str) -> str:
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid preset name")
    return name


def _mapping_preset_path(user: UserContext, name: str) -> Path:
    user.mapping_presets_dir.mkdir(parents=True, exist_ok=True)
    return user.mapping_presets_dir / f"{_safe_name(name)}.json"


def _tree_preset_path(user: UserContext, name: str) -> Path:
    user.presets_dir.mkdir(parents=True, exist_ok=True)
    return user.presets_dir / f"{_safe_name(name)}.json"


def _existing_names(directory: Path) -> set[str]:
    directory.mkdir(parents=True, exist_ok=True)
    return {path.stem for path in directory.glob("*.json")}


def _resolve_preset_name(
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


def _share_preset(
    sender: UserContext,
    request: SharePresetRequest,
    *,
    preset_path_fn,
    dest_dir_fn,
) -> SharePresetResponse:
    recipient_record = _resolve_recipient(request.recipient_username)
    if recipient_record.id == sender.user_id:
        raise HTTPException(status_code=400, detail="Cannot share a preset with yourself")

    source_path = preset_path_fn(sender, request.source_preset_name)
    if not source_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{request.source_preset_name}' not found",
        )
    source = json.loads(source_path.read_text(encoding="utf-8"))

    recipient = user_context_from_record(recipient_record)
    dest_dir = dest_dir_fn(recipient)
    base_name = _safe_name(str(source.get("name", request.source_preset_name)).strip())
    resolved_name = _resolve_preset_name(
        base_name,
        sender.display_name,
        _existing_names(dest_dir),
    )
    now = _utc_now()
    payload = {**source, "name": resolved_name}
    payload["shared_by_id"] = sender.user_id
    payload["shared_by_name"] = sender.display_name
    payload["shared_at"] = now
    if request.message.strip():
        payload["share_message"] = request.message.strip()

    dest_path = dest_dir / f"{_safe_name(resolved_name)}.json"
    dest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return SharePresetResponse(
        recipient_display_name=recipient.display_name,
        preset_name=resolved_name,
    )


def share_mapping_preset(
    sender: UserContext,
    request: SharePresetRequest,
) -> SharePresetResponse:
    return _share_preset(
        sender,
        request,
        preset_path_fn=_mapping_preset_path,
        dest_dir_fn=lambda user: user.mapping_presets_dir,
    )


def share_tree_preset(
    sender: UserContext,
    request: SharePresetRequest,
) -> SharePresetResponse:
    return _share_preset(
        sender,
        request,
        preset_path_fn=_tree_preset_path,
        dest_dir_fn=lambda user: user.presets_dir,
    )
