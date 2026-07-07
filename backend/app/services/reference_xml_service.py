"""Read-only access to reference XML documents from a local Git cache."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException

_CATEGORY_RE = re.compile(r"^[\w\-.]+$")
_REFERENCE_EXTENSIONS = (".txt", ".xml")


def _strip_reference_extension(filename: str) -> str:
    lower = filename.lower()
    for ext in _REFERENCE_EXTENSIONS:
        if lower.endswith(ext):
            return filename[: -len(ext)]
    return filename


def _iter_reference_files(category_dir: Path):
    for ext in _REFERENCE_EXTENSIONS:
        for path in sorted(category_dir.glob(f"*{ext}")):
            if path.is_file():
                yield path


def _category_has_reference_files(category_dir: Path) -> bool:
    return any(True for _ in _iter_reference_files(category_dir))


@dataclass(frozen=True)
class CategorySummary:
    name: str
    document_count: int
    root_element: str | None = None


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
    stem = _strip_reference_extension(filename)
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
    cat_dir = (root / category).resolve()
    if not cat_dir.is_relative_to(root_resolved):
        raise HTTPException(status_code=400, detail="Invalid category path")

    candidates = [cat_dir / f"{doc_id}{ext}" for ext in _REFERENCE_EXTENSIONS]
    if any(doc_id.lower().endswith(ext) for ext in _REFERENCE_EXTENSIONS):
        candidates.insert(0, cat_dir / doc_id)

    for path in candidates:
        resolved = path.resolve()
        if resolved.is_relative_to(root_resolved) and resolved.is_file():
            return resolved

    fallback = (cat_dir / f"{doc_id}.xml").resolve()
    if not fallback.is_relative_to(root_resolved):
        raise HTTPException(status_code=400, detail="Invalid document path")
    return fallback


def _normalize_element_key(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", (text or "").lower())


def _peek_root_element(category_dir: Path) -> str | None:
    for path in _iter_reference_files(category_dir):
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except ET.ParseError:
            continue
        tag = root.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        return tag or None
    return None


def _is_reference_category_dir(entry: Path) -> bool:
    if not entry.is_dir():
        return False
    if entry.name.startswith("."):
        return False
    return any(path.is_file() for path in _iter_reference_files(entry))


def list_categories(
    root: Path,
    *,
    root_element: str | None = None,
) -> list[CategorySummary]:
    if not root.is_dir():
        return []
    filter_key = _normalize_element_key(root_element) if root_element else ""
    categories: list[CategorySummary] = []
    for entry in sorted(root.iterdir()):
        if not _is_reference_category_dir(entry):
            continue
        count = sum(1 for _ in _iter_reference_files(entry))
        peeked = _peek_root_element(entry)
        if filter_key:
            candidate_keys = {
                _normalize_element_key(peeked or ""),
                _normalize_element_key(entry.name),
            }
            if filter_key not in candidate_keys and not any(
                filter_key in key or key in filter_key for key in candidate_keys if key
            ):
                continue
        categories.append(
            CategorySummary(
                name=entry.name,
                document_count=count,
                root_element=peeked,
            )
        )
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
    for path in _iter_reference_files(cat_dir):
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
