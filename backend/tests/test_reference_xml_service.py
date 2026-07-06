"""Tests for reference XML service."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import reference_xml_service as svc


@pytest.fixture
def reference_tree(tmp_path: Path) -> Path:
    root = tmp_path / "xml-library"
    add_card = root / "add-card"
    add_card.mkdir(parents=True)
    (add_card / "add-card.txt").write_text("<root>add-card</root>", encoding="utf-8")

    free_doc = root / "free-document"
    free_doc.mkdir(parents=True)
    (
        free_doc / "free-document_ПП_c_диплинком_.txt"
    ).write_text("<root>pp</root>", encoding="utf-8")

    return root


def test_parse_entry_strips_category_prefix():
    doc_id, title = svc.parse_entry(
        "free-document", "free-document_ПП_c_диплинком_.txt"
    )
    assert doc_id == "free-document_ПП_c_диплинком_"
    assert title == "ПП c диплинком"


def test_parse_entry_without_prefix():
    doc_id, title = svc.parse_entry("add-card", "add-card.txt")
    assert doc_id == "add-card"
    assert title == "add-card"


def test_list_categories(reference_tree: Path):
    categories = svc.list_categories(reference_tree)
    names = {c.name for c in categories}
    assert names == {"add-card", "free-document"}
    free = next(c for c in categories if c.name == "free-document")
    assert free.document_count == 1


def test_list_documents(reference_tree: Path):
    docs = svc.list_documents(reference_tree, "free-document")
    assert len(docs) == 1
    assert docs[0].title == "ПП c диплинком"


def test_load_document(reference_tree: Path):
    entry = svc.load_document(
        reference_tree,
        "free-document",
        "free-document_ПП_c_диплинком_",
    )
    assert entry.xml_text == "<root>pp</root>"
    assert entry.title == "ПП c диплинком"


def test_path_traversal_category_dotdot(reference_tree: Path):
    with pytest.raises(HTTPException) as exc:
        svc.list_documents(reference_tree, "..")
    assert exc.value.status_code == 400


def test_path_traversal_doc_id(reference_tree: Path):
    with pytest.raises(HTTPException) as exc:
        svc.load_document(reference_tree, "add-card", "../../secret")
    assert exc.value.status_code == 400


def test_missing_category(reference_tree: Path):
    with pytest.raises(HTTPException) as exc:
        svc.list_documents(reference_tree, "missing")
    assert exc.value.status_code == 404


def test_missing_document(reference_tree: Path):
    with pytest.raises(HTTPException) as exc:
        svc.load_document(reference_tree, "add-card", "nonexistent")
    assert exc.value.status_code == 404
