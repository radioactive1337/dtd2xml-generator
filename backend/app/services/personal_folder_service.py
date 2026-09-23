"""User-defined folders for personal XML documents.

Folders live in ``xml_documents/_meta/folders.json``. Document files stay as
``*.json`` in the parent directory, so the folder registry is not listed as a
document.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.user_context import UserContext

logger = logging.getLogger(__name__)

_MAX_FOLDER_NAME_LENGTH = 80


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _registry_path(user: UserContext) -> Path:
    return user.xml_documents_dir / "_meta" / "folders.json"


def normalize_folder_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned or cleaned in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid folder name")
    if len(cleaned) > _MAX_FOLDER_NAME_LENGTH:
        raise HTTPException(status_code=400, detail="Folder name is too long")
    if any(ord(ch) < 32 or ch in "/\\" for ch in cleaned):
        raise HTTPException(status_code=400, detail="Invalid folder name")
    return cleaned


def list_folders(user: UserContext) -> list[str]:
    path = _registry_path(user)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping unreadable folder registry %s: %s", path, exc)
        return []
    raw = data.get("folders", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item]


def resolve_folder_assignment(user: UserContext, folder: str) -> str:
    cleaned = (folder or "").strip()
    if not cleaned:
        return ""
    name = normalize_folder_name(cleaned)
    if name not in list_folders(user):
        raise HTTPException(status_code=400, detail="Unknown folder")
    return name


def create_folder(user: UserContext, name: str) -> list[str]:
    folder = normalize_folder_name(name)
    folders = list_folders(user)
    if folder in folders:
        raise HTTPException(status_code=409, detail="Folder already exists")
    folders.append(folder)
    _write_folders(user, folders)
    return _sorted(folders)


def rename_folder(user: UserContext, current: str, new_name: str) -> list[str]:
    old = normalize_folder_name(current)
    new = normalize_folder_name(new_name)
    folders = list_folders(user)
    if old not in folders:
        raise HTTPException(status_code=404, detail="Folder not found")
    if new != old and new in folders:
        raise HTTPException(status_code=409, detail="Folder already exists")
    updated = [new if item == old else item for item in folders]
    _write_folders(user, updated)
    if new != old:
        _rewrite_document_folders(user, old, new)
    return _sorted(updated)


def delete_folder(user: UserContext, name: str) -> list[str]:
    folder = normalize_folder_name(name)
    folders = list_folders(user)
    if folder not in folders:
        raise HTTPException(status_code=404, detail="Folder not found")
    remaining = [item for item in folders if item != folder]
    _write_folders(user, remaining)
    _rewrite_document_folders(user, folder, "")
    return _sorted(remaining)


def _sorted(folders: list[str]) -> list[str]:
    return sorted(folders, key=str.casefold)


def _write_folders(user: UserContext, folders: list[str]) -> None:
    path = _registry_path(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"folders": _sorted(folders)}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _rewrite_document_folders(user: UserContext, old: str, new: str) -> None:
    directory = user.xml_documents_dir
    if not directory.is_dir():
        return
    now = _utc_now()
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable personal document %s: %s", path.name, exc)
            continue
        if not isinstance(data, dict) or data.get("folder", "") != old:
            continue
        data["folder"] = new
        data["updated_at"] = now
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
