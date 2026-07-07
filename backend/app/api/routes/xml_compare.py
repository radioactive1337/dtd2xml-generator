"""XML structure comparison: unique-path detection and optional AI explanation."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.sessions import get_current_user
from app.config import reference_xml_root, resolve_llm_alias
from app.services import reference_xml_service as ref_service
from app.services import xml_structure_service as structure_service
from app.services.llm_service import LLMService
from app.services.xml_structure_service import ReferenceDoc, XmlParseError
from app.user_context import UserContext

router = APIRouter(prefix="/xml-compare", tags=["xml-compare"])
logger = logging.getLogger(__name__)


class StructureCompareRequest(BaseModel):
    xml_text: str = Field(..., min_length=1)


class HighlightRange(BaseModel):
    start_line: int
    end_line: int
    path: str


class HighlightTarget(BaseModel):
    line: int
    path: str
    tag: str


class SimilarityEntry(BaseModel):
    category: str
    doc_id: str
    title: str
    score: float


class StructureSnippet(BaseModel):
    path: str
    xml: str


class StructureCompareResponse(BaseModel):
    root_element: str
    references_count: int
    has_references: bool
    is_unique: bool
    unique_paths: list[str]
    highlight_ranges: list[HighlightRange]
    highlight_targets: list[HighlightTarget]
    snippets: list[StructureSnippet]
    similarities: list[SimilarityEntry]
    closest: SimilarityEntry | None = None
    closest_paths: list[str] = Field(default_factory=list)


class ClosestReference(BaseModel):
    category: str = ""
    doc_id: str = ""
    title: str = ""
    score: float = 0.0


class ExplainSnippet(BaseModel):
    path: str = ""
    xml: str = ""


class StructureExplainRequest(BaseModel):
    root_element: str = ""
    unique_paths: list[str] = Field(default_factory=list)
    closest: ClosestReference | None = None
    closest_paths: list[str] = Field(default_factory=list)
    snippets: list[ExplainSnippet] = Field(default_factory=list)
    dtd_docs: dict[str, str] = Field(default_factory=dict)
    llm_alias: str | None = None


class StructureExplainResponse(BaseModel):
    explanation: str


def _require_root() -> Path:
    root = reference_xml_root()
    if root is None or not root.is_dir():
        raise HTTPException(
            status_code=503,
            detail="Reference XML library is not configured",
        )
    return root


def _collect_references(root: Path, root_element: str) -> list[ReferenceDoc]:
    references: list[ReferenceDoc] = []
    for category in ref_service.list_categories(root, root_element=root_element):
        for doc in ref_service.list_documents(root, category.name):
            entry = ref_service.load_document(root, category.name, doc.doc_id)
            references.append(
                ReferenceDoc(
                    category=entry.category,
                    doc_id=entry.doc_id,
                    title=entry.title,
                    xml_text=entry.xml_text,
                )
            )
    return references


@router.post("/structure", response_model=StructureCompareResponse)
async def compare_structure(
    request: StructureCompareRequest,
    _user: UserContext = Depends(get_current_user),
) -> StructureCompareResponse:
    root = _require_root()

    try:
        root_element = structure_service.peek_root_element(request.xml_text)
    except XmlParseError as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось разобрать XML: {exc}") from exc

    references = _collect_references(root, root_element)
    report = structure_service.compare_structure(request.xml_text, references)
    return StructureCompareResponse(**report)


@router.post("/explain", response_model=StructureExplainResponse)
async def explain_structure(
    request: StructureExplainRequest,
    user: UserContext = Depends(get_current_user),
) -> StructureExplainResponse:
    if not request.unique_paths:
        raise HTTPException(
            status_code=400,
            detail="Нет уникальных путей для объяснения",
        )

    try:
        alias = resolve_llm_alias(user, request.llm_alias)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    closest = request.closest.model_dump() if request.closest else None
    snippets = [s.model_dump() for s in request.snippets]

    try:
        explanation = await LLMService(user, alias=alias).explain_structure_diff(
            root_element=request.root_element,
            unique_paths=request.unique_paths,
            closest=closest,
            closest_paths=request.closest_paths,
            snippets=snippets,
            dtd_docs=request.dtd_docs,
        )
    except ValueError as exc:
        message = str(exc)
        status = 503 if "not configured" in message else 502
        logger.warning("Structure diff explanation failed [alias=%s]: %s", alias, exc)
        raise HTTPException(status_code=status, detail=message) from exc

    return StructureExplainResponse(explanation=explanation)
