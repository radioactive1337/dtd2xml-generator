"""Git push for reference XML documents into the shared library repository."""

from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from app.config import ReferenceXmlSettings, reference_xml_push_cache_dir
from app.services.reference_xml_sync import _git_head_sha, _resolve_repo_url, _run_git

_push_lock = threading.Lock()

_SEGMENT_RE = re.compile(r"^[\w\-.]+$")
_FILENAME_RE = re.compile(r"^[\w\-. ()]+\.txt$")


@dataclass(frozen=True)
class PushResult:
    status: str
    commit_sha: str | None
    path: str
    message: str
    overwritten: bool


def _validate_segment(name: str, *, label: str) -> str:
    value = name.strip()
    if not value or value in {".", ".."}:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    if not _SEGMENT_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return value


def _validate_filename(filename: str) -> str:
    value = filename.strip()
    if not value.lower().endswith(".txt"):
        value = f"{value}.txt"
    if not _FILENAME_RE.match(value):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return value


def _repo_relative_path(settings: ReferenceXmlSettings, root_element: str, filename: str) -> str:
    subdir = settings.subdir.strip().strip("/\\")
    parts = [part for part in (subdir, root_element, filename) if part]
    return "/".join(parts)


def _resolve_target_file(
    cache_dir: Path,
    settings: ReferenceXmlSettings,
    root_element: str,
    filename: str,
) -> tuple[Path, str]:
    subdir = settings.subdir.strip().strip("/\\")
    base = cache_dir / subdir if subdir else cache_dir
    category_dir = base / root_element
    target = (category_dir / filename).resolve()
    cache_resolved = cache_dir.resolve()
    if not target.is_relative_to(cache_resolved):
        raise HTTPException(status_code=400, detail="Invalid target path")
    rel_path = _repo_relative_path(settings, root_element, filename)
    return target, rel_path


def _ensure_push_repo(settings: ReferenceXmlSettings) -> Path:
    cache_dir = reference_xml_push_cache_dir()
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
                "-b",
                branch,
                repo_url,
                str(cache_dir),
            ]
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "git clone failed").strip()
            raise HTTPException(status_code=502, detail=f"Git clone failed: {detail}")
        return cache_dir

    fetch = _run_git(["git", "-C", str(cache_dir), "fetch", "origin", branch])
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "git fetch failed").strip()
        raise HTTPException(status_code=502, detail=f"Git fetch failed: {detail}")

    checkout = _run_git(["git", "-C", str(cache_dir), "checkout", branch])
    if checkout.returncode != 0:
        detail = (checkout.stderr or checkout.stdout or "git checkout failed").strip()
        raise HTTPException(status_code=502, detail=f"Git checkout failed: {detail}")

    pull = _run_git(
        ["git", "-C", str(cache_dir), "pull", "--ff-only", "origin", branch]
    )
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or "git pull failed").strip()
        raise HTTPException(status_code=502, detail=f"Git pull failed: {detail}")

    return cache_dir


def _push_document_sync(
    settings: ReferenceXmlSettings,
    *,
    root_element: str,
    filename: str,
    xml_text: str,
    author_name: str,
    author_email: str,
    commit_message: str | None,
) -> PushResult:
    if not settings.push_enabled:
        raise HTTPException(status_code=503, detail="Git push is not enabled")

    safe_root = _validate_segment(root_element, label="root element")
    safe_filename = _validate_filename(filename)
    if not xml_text.strip():
        raise HTTPException(status_code=400, detail="XML text is empty")

    cache_dir = _ensure_push_repo(settings)
    target, rel_path = _resolve_target_file(cache_dir, settings, safe_root, safe_filename)
    overwritten = target.is_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(xml_text if xml_text.endswith("\n") else xml_text + "\n", encoding="utf-8")

    add = _run_git(["git", "-C", str(cache_dir), "add", "--", rel_path])
    if add.returncode != 0:
        detail = (add.stderr or add.stdout or "git add failed").strip()
        raise HTTPException(status_code=502, detail=f"Git add failed: {detail}")

    diff = _run_git(
        ["git", "-C", str(cache_dir), "diff", "--cached", "--quiet", "--", rel_path]
    )
    if diff.returncode == 0:
        return PushResult(
            status="unchanged",
            commit_sha=_git_head_sha(cache_dir),
            path=rel_path,
            message="No changes to commit",
            overwritten=overwritten,
        )

    default_message = (
        f"Update {safe_filename} in {safe_root}"
        if overwritten
        else f"Add {safe_filename} to {safe_root}"
    )
    message = (commit_message or "").strip() or default_message
    commit = _run_git(
        [
            "git",
            "-C",
            str(cache_dir),
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
            "--",
            rel_path,
        ]
    )
    if commit.returncode != 0:
        detail = (commit.stderr or commit.stdout or "git commit failed").strip()
        raise HTTPException(status_code=502, detail=f"Git commit failed: {detail}")

    branch = settings.branch.strip() or "main"
    push = _run_git(["git", "-C", str(cache_dir), "push", "origin", branch])
    if push.returncode != 0:
        detail = (push.stderr or push.stdout or "git push failed").strip()
        raise HTTPException(status_code=502, detail=f"Git push failed: {detail}")

    commit_sha = _git_head_sha(cache_dir)
    action = "updated" if overwritten else "added"
    return PushResult(
        status="ok",
        commit_sha=commit_sha,
        path=rel_path,
        message=f"Document {action} and pushed successfully",
        overwritten=overwritten,
    )


async def push_document(
    settings: ReferenceXmlSettings,
    *,
    root_element: str,
    filename: str,
    xml_text: str,
    author_name: str,
    author_email: str,
    commit_message: str | None = None,
) -> PushResult:
    if not _push_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Git push already in progress")
    try:
        return await asyncio.to_thread(
            _push_document_sync,
            settings,
            root_element=root_element,
            filename=filename,
            xml_text=xml_text,
            author_name=author_name,
            author_email=author_email,
            commit_message=commit_message,
        )
    finally:
        _push_lock.release()
