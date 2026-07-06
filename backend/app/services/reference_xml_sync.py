"""Git clone/pull for the reference XML library cache."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.config import ReferenceXmlSettings, reference_xml_cache_dir

_sync_lock = threading.Lock()
SYNC_STATE_FILE = "sync_state.json"


@dataclass(frozen=True)
class SyncResult:
    status: str
    commit_sha: str | None
    synced_at: str
    message: str


def _sync_state_path(cache_dir: Path) -> Path:
    return cache_dir / SYNC_STATE_FILE


def load_sync_state(cache_dir: Path) -> dict:
    path = _sync_state_path(cache_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sync_state(cache_dir: Path, state: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _sync_state_path(cache_dir).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _resolve_repo_url(settings: ReferenceXmlSettings) -> str:
    url = settings.repo_url.strip()
    if not url:
        raise HTTPException(status_code=503, detail="Reference XML repo_url is not configured")
    token = os.getenv("REFERENCE_XML_GIT_TOKEN", "").strip()
    if token and url.startswith("https://"):
        if "@" not in url.split("://", 1)[1]:
            url = url.replace("https://", f"https://{token}@", 1)
    return url


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_head_sha(cache_dir: Path) -> str | None:
    result = _run_git(["git", "-C", str(cache_dir), "rev-parse", "--short", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _sync_repository_sync(settings: ReferenceXmlSettings) -> SyncResult:
    cache_dir = reference_xml_cache_dir()
    if cache_dir is None:
        raise HTTPException(status_code=503, detail="Reference XML library is not configured")

    repo_url = _resolve_repo_url(settings)
    branch = settings.branch.strip() or "main"
    git_dir = cache_dir / ".git"

    if not git_dir.is_dir():
        cache_dir.mkdir(parents=True, exist_ok=True)
        result = _run_git(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "-b",
                branch,
                repo_url,
                str(cache_dir),
            ]
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "git clone failed").strip()
            raise HTTPException(status_code=502, detail=f"Git clone failed: {detail}")
        action = "cloned"
    else:
        fetch = _run_git(["git", "-C", str(cache_dir), "fetch", "origin", branch])
        if fetch.returncode != 0:
            detail = (fetch.stderr or fetch.stdout or "git fetch failed").strip()
            raise HTTPException(status_code=502, detail=f"Git fetch failed: {detail}")

        checkout = _run_git(
            ["git", "-C", str(cache_dir), "checkout", branch]
        )
        if checkout.returncode != 0:
            detail = (checkout.stderr or checkout.stdout or "git checkout failed").strip()
            raise HTTPException(status_code=502, detail=f"Git checkout failed: {detail}")

        pull = _run_git(
            ["git", "-C", str(cache_dir), "pull", "--ff-only", "origin", branch]
        )
        if pull.returncode != 0:
            detail = (pull.stderr or pull.stdout or "git pull failed").strip()
            raise HTTPException(status_code=502, detail=f"Git pull failed: {detail}")
        action = "updated"

    synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    commit_sha = _git_head_sha(cache_dir)
    message = f"Reference library {action} successfully"
    state = {
        "last_sync": synced_at,
        "commit_sha": commit_sha,
        "branch": branch,
        "message": message,
    }
    _save_sync_state(cache_dir, state)
    return SyncResult(
        status="ok",
        commit_sha=commit_sha,
        synced_at=synced_at,
        message=message,
    )


async def sync_reference_repository(settings: ReferenceXmlSettings) -> SyncResult:
    if not _sync_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Sync already in progress")
    try:
        return await asyncio.to_thread(_sync_repository_sync, settings)
    finally:
        _sync_lock.release()
