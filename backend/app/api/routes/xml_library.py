"""XML library API: shared reference documents and per-user personal repository."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.sessions import get_current_user
from app.config import (
    ReferenceXmlSettings,
    get_reference_xml_settings,
    reference_xml_cache_dir,
    reference_xml_root,
)
from app.services import reference_xml_service as ref_service
from app.services.git_push_service import push_document
from app.services.reference_xml_sync import load_sync_state, sync_reference_repository
from app.services.xml_share_service import (
    ShareDocumentRequest,
    ShareDocumentResponse,
    share_document,
)
from app.user_context import UserContext

router = APIRouter(prefix="/xml-library", tags=["xml-library"])
logger = logging.getLogger(__name__)


class SharedStatusResponse(BaseModel):
    enabled: bool
    configured: bool = False
    push_enabled: bool = False
    last_sync: str | None = None
    commit_sha: str | None = None
    categories_count: int = 0
    message: str | None = None


class SyncResponse(BaseModel):
    status: str
    commit_sha: str | None = None
    synced_at: str
    message: str


class PushToGitRequest(BaseModel):
    xml_text: str
    filename: str
    root_element: str
    commit_message: str | None = None


class PushToGitResponse(BaseModel):
    status: str
    commit_sha: str | None = None
    path: str
    message: str
    overwritten: bool = False


class CategoryResponse(BaseModel):
    name: str
    document_count: int
    root_element: str | None = None


class DocumentSummaryResponse(BaseModel):
    doc_id: str
    title: str
    filename: str


class SharedDocumentResponse(BaseModel):
    xml_text: str
    title: str
    category: str
    filename: str
    doc_id: str


class PersonalDocumentSummary(BaseModel):
    name: str
    schema_id: str = ""
    category: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    shared_by_id: str | None = None
    shared_by_name: str | None = None
    shared_at: str | None = None


class PersonalDocumentData(BaseModel):
    name: str
    schema_id: str = ""
    category: str = "free-document"
    description: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    xml_text: str = ""
    shared_by_id: str | None = None
    shared_by_name: str | None = None
    shared_at: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(name: str) -> str:
    if not re.match(r"^[\w\-. ()]+$", name):
        raise HTTPException(status_code=400, detail="Invalid document name")
    return name


def _require_settings() -> ReferenceXmlSettings:
    settings = get_reference_xml_settings()
    if settings is None:
        raise HTTPException(
            status_code=503,
            detail="Reference XML library is not configured",
        )
    return settings


def _require_push_settings() -> ReferenceXmlSettings:
    settings = _require_settings()
    if not settings.push_enabled:
        raise HTTPException(status_code=503, detail="Git push is not enabled")
    return settings


def _require_root() -> Path:
    root = reference_xml_root()
    if root is None or not root.is_dir():
        raise HTTPException(
            status_code=503,
            detail="Reference XML library is not configured",
        )
    return root


def _personal_path(user: UserContext, name: str) -> Path:
    user.xml_documents_dir.mkdir(parents=True, exist_ok=True)
    return user.xml_documents_dir / f"{_safe_name(name)}.json"


@router.get("/shared/status", response_model=SharedStatusResponse)
async def shared_status(
    _user: UserContext = Depends(get_current_user),
) -> SharedStatusResponse:
    settings = get_reference_xml_settings()
    if settings is None:
        return SharedStatusResponse(enabled=False, configured=False)

    root = reference_xml_root()
    cache_dir = reference_xml_cache_dir()
    state = load_sync_state(cache_dir) if cache_dir else {}
    categories_count = len(ref_service.list_categories(root)) if root and root.is_dir() else 0

    return SharedStatusResponse(
        enabled=True,
        configured=root is not None and root.is_dir(),
        push_enabled=settings.push_enabled,
        last_sync=state.get("last_sync"),
        commit_sha=state.get("commit_sha"),
        categories_count=categories_count,
        message=state.get("message"),
    )


@router.post("/shared/sync", response_model=SyncResponse)
async def shared_sync(
    _user: UserContext = Depends(get_current_user),
) -> SyncResponse:
    settings = _require_settings()
    result = await sync_reference_repository(settings)
    return SyncResponse(
        status=result.status,
        commit_sha=result.commit_sha,
        synced_at=result.synced_at,
        message=result.message,
    )


@router.post("/shared/push", response_model=PushToGitResponse)
async def push_to_git(
    body: PushToGitRequest,
    user: UserContext = Depends(get_current_user),
) -> PushToGitResponse:
    settings = _require_push_settings()
    author_name = f"{user.display_name} ({settings.push_author_name})"
    result = await push_document(
        settings,
        root_element=body.root_element,
        filename=body.filename,
        xml_text=body.xml_text,
        author_name=author_name,
        author_email=settings.push_author_email,
        commit_message=body.commit_message,
    )
    if result.status == "ok":
        await sync_reference_repository(settings)
    return PushToGitResponse(
        status=result.status,
        commit_sha=result.commit_sha,
        path=result.path,
        message=result.message,
        overwritten=result.overwritten,
    )


@router.get("/shared/categories", response_model=list[CategoryResponse])
async def list_shared_categories(
    root_element: str | None = Query(default=None),
    _user: UserContext = Depends(get_current_user),
) -> list[CategoryResponse]:
    root = _require_root()
    return [
        CategoryResponse(
            name=c.name,
            document_count=c.document_count,
            root_element=c.root_element,
        )
        for c in ref_service.list_categories(root, root_element=root_element)
    ]


@router.get(
    "/shared/categories/{category}",
    response_model=list[DocumentSummaryResponse],
)
async def list_shared_documents(
    category: str,
    _user: UserContext = Depends(get_current_user),
) -> list[DocumentSummaryResponse]:
    root = _require_root()
    return [
        DocumentSummaryResponse(doc_id=d.doc_id, title=d.title, filename=d.filename)
        for d in ref_service.list_documents(root, category)
    ]


@router.get(
    "/shared/categories/{category}/{doc_id}",
    response_model=SharedDocumentResponse,
)
async def load_shared_document(
    category: str,
    doc_id: str,
    _user: UserContext = Depends(get_current_user),
) -> SharedDocumentResponse:
    root = _require_root()
    entry = ref_service.load_document(root, category, doc_id)
    return SharedDocumentResponse(
        xml_text=entry.xml_text,
        title=entry.title,
        category=entry.category,
        filename=entry.filename,
        doc_id=entry.doc_id,
    )


@router.get("/personal", response_model=list[PersonalDocumentSummary])
async def list_personal_documents(
    schema_id: str | None = Query(default=None),
    user: UserContext = Depends(get_current_user),
) -> list[PersonalDocumentSummary]:
    user.xml_documents_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[PersonalDocumentSummary] = []
    for path in sorted(user.xml_documents_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable personal document %s: %s", path.name, exc)
            continue
        doc_schema = data.get("schema_id", "")
        if schema_id and doc_schema != schema_id:
            continue
        summaries.append(
            PersonalDocumentSummary(
                name=data.get("name", path.stem),
                schema_id=doc_schema,
                category=data.get("category", ""),
                description=data.get("description", ""),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                shared_by_id=data.get("shared_by_id"),
                shared_by_name=data.get("shared_by_name"),
                shared_at=data.get("shared_at"),
            )
        )
    return summaries


@router.post("/share", response_model=ShareDocumentResponse)
async def share_personal_document(
    body: ShareDocumentRequest,
    user: UserContext = Depends(get_current_user),
) -> ShareDocumentResponse:
    return share_document(user, body)


@router.post("/personal", response_model=PersonalDocumentData)
async def save_personal_document(
    document: PersonalDocumentData,
    user: UserContext = Depends(get_current_user),
) -> PersonalDocumentData:
    path = _personal_path(user, document.name)
    now = _utc_now()
    created_at = document.created_at or now
    payload = document.model_dump()
    payload["created_at"] = created_at
    payload["updated_at"] = now
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PersonalDocumentData(**payload)


@router.get("/personal/{name}", response_model=PersonalDocumentData)
async def load_personal_document(
    name: str,
    user: UserContext = Depends(get_current_user),
) -> PersonalDocumentData:
    path = _personal_path(user, name)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Personal document '{name}' not found",
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return PersonalDocumentData(**data)


@router.put("/personal/{name}", response_model=PersonalDocumentData)
async def update_personal_document(
    name: str,
    document: PersonalDocumentData,
    user: UserContext = Depends(get_current_user),
) -> PersonalDocumentData:
    safe = _safe_name(name)
    if document.name != safe:
        raise HTTPException(status_code=400, detail="Document name in body must match URL")
    path = _personal_path(user, name)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Personal document '{name}' not found",
        )
    existing = json.loads(path.read_text(encoding="utf-8"))
    now = _utc_now()
    payload = document.model_dump()
    payload["created_at"] = existing.get("created_at") or now
    payload["updated_at"] = now
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PersonalDocumentData(**payload)


@router.delete("/personal/{name}")
async def delete_personal_document(
    name: str,
    user: UserContext = Depends(get_current_user),
) -> dict[str, str]:
    path = _personal_path(user, name)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Personal document '{name}' not found",
        )
    path.unlink()
    return {"status": "deleted", "name": name}
