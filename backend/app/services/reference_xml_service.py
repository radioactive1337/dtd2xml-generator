"""Read-only access to reference XML documents from a local Git cache."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

_CATEGORY_RE = re.compile(r"^[\w\-.]+$")


@dataclass(frozen=True)
class CategorySummary:
    name: str
    document_count: int


@dataclass(frozen=True)
class DocumentSummary:
    doc_id: str
    title: str
    filename: str


@dataclass(frozen=True)
class ReferenceEntry:
    category: str
    doc_id: str
    title: str
    filename: str
    xml_text: str


def parse_entry(category: str, filename: str) -> tuple[str, str]:
    """Return (doc_id, title) for a reference XML filename."""
    stem = filename.removesuffix(".txt")
    prefix = f"{category}_"
    title = stem[len(prefix) :] if stem.startswith(prefix) else stem
    title = title.replace("_", " ").strip(" _") or stem
    return stem, title


def _validate_category(category: str) -> str:
    if category in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid category name")
    if not _CATEGORY_RE.match(category):
        raise HTTPException(status_code=400, detail="Invalid category name")
    return category


def _validate_doc_id(doc_id: str) -> str:
    if not doc_id or "/" in doc_id or "\\" in doc_id or ".." in doc_id:
        raise HTTPException(status_code=400, detail="Invalid document id")
    return doc_id


def _resolve_document_path(root: Path, category: str, doc_id: str) -> Path:
    _validate_category(category)
    _validate_doc_id(doc_id)
    root_resolved = root.resolve()
    path = (root / category / f"{doc_id}.txt").resolve()
    if not path.is_relative_to(root_resolved):
        raise HTTPException(status_code=400, detail="Invalid document path")
    return path


def list_categories(root: Path) -> list[CategorySummary]:
    if not root.is_dir():
        return []
    categories: list[CategorySummary] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        count = sum(1 for f in entry.glob("*.txt") if f.is_file())
        categories.append(CategorySummary(name=entry.name, document_count=count))
    return categories


def list_documents(root: Path, category: str) -> list[DocumentSummary]:
    _validate_category(category)
    cat_dir = root / category
    if not cat_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
    root_resolved = root.resolve()
    if not cat_dir.resolve().is_relative_to(root_resolved):
        raise HTTPException(status_code=400, detail="Invalid category path")
    documents: list[DocumentSummary] = []
    for path in sorted(cat_dir.glob("*.txt")):
        if not path.is_file():
            continue
        doc_id, title = parse_entry(category, path.name)
        documents.append(
            DocumentSummary(doc_id=doc_id, title=title, filename=path.name)
        )
    return documents


def load_document(root: Path, category: str, doc_id: str) -> ReferenceEntry:
    path = _resolve_document_path(root, category, doc_id)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc_id}' not found in category '{category}'",
        )
    doc_id_parsed, title = parse_entry(category, path.name)
    xml_text = path.read_text(encoding="utf-8")
    return ReferenceEntry(
        category=category,
        doc_id=doc_id_parsed,
        title=title,
        filename=path.name,
        xml_text=xml_text,
    )
