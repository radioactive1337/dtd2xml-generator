"""Tests for XML library API endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import ReferenceXmlSettings
from app.services.reference_xml_sync import SyncResult
from app.user_context import dev_user_context

SAMPLE_PERSONAL = {
    "name": "Мой тест",
    "schema_id": "schema-1",
    "category": "free-document",
    "description": "test doc",
    "xml_text": "<root>personal</root>",
}


@pytest.fixture
def reference_xml_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "reference-xml"
    root = cache / "xml-library"
    cat = root / "add-card"
    cat.mkdir(parents=True)
    (cat / "add-card.txt").write_text("<root>shared</root>", encoding="utf-8")

    settings = ReferenceXmlSettings(
        enabled=True,
        repo_url="https://github.com/org/xml-library.git",
        branch="main",
        subdir="xml-library",
        cache_dir=str(cache),
    )

    monkeypatch.setattr("app.config.get_reference_xml_settings", lambda: settings)

    def _cache_dir():
        return cache

    def _root():
        return root

    monkeypatch.setattr("app.config.reference_xml_cache_dir", _cache_dir)
    monkeypatch.setattr("app.config.reference_xml_root", _root)
    monkeypatch.setattr("app.api.routes.xml_library.get_reference_xml_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.xml_library.reference_xml_cache_dir", _cache_dir)
    monkeypatch.setattr("app.api.routes.xml_library.reference_xml_root", _root)
    monkeypatch.setattr(
        "app.api.routes.xml_library.resolve_git_auth",
        lambda _user: ("test-token", "oauth2"),
    )
    monkeypatch.setattr(
        "app.api.routes.xml_library.git_auth_configured",
        lambda _user: True,
    )

    return root


def test_shared_status_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.xml_library.get_reference_xml_settings", lambda: None)
    response = client.get("/api/xml-library/shared/status")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_shared_categories_and_load(client: TestClient, reference_xml_tree: Path):
    response = client.get("/api/xml-library/shared/categories")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "add-card"

    response = client.get("/api/xml-library/shared/categories/add-card")
    assert response.status_code == 200
    assert response.json()[0]["doc_id"] == "add-card"

    response = client.get("/api/xml-library/shared/categories/add-card/add-card")
    assert response.status_code == 200
    assert response.json()["xml_text"] == "<root>shared</root>"


def test_shared_invalid_category(client: TestClient, reference_xml_tree: Path):
    response = client.get("/api/xml-library/shared/categories/foo%2Fbar")
    assert response.status_code in {400, 404}


def test_shared_sync(client: TestClient, reference_xml_tree: Path):
    mock_result = SyncResult(
        status="ok",
        commit_sha="abc1234",
        synced_at="2026-07-06T12:00:00Z",
        message="Reference library updated successfully",
    )
    with patch(
        "app.api.routes.xml_library.sync_reference_repository",
        new=AsyncMock(return_value=mock_result),
    ):
        response = client.post("/api/xml-library/shared/sync")
    assert response.status_code == 200
    assert response.json()["commit_sha"] == "abc1234"


def test_personal_crud(client: TestClient):
    docs_dir = dev_user_context().xml_documents_dir
    docs_dir.mkdir(parents=True, exist_ok=True)
    for path in docs_dir.glob("*.json"):
        path.unlink()

    response = client.post("/api/xml-library/personal", json=SAMPLE_PERSONAL)
    assert response.status_code == 200
    assert response.json()["name"] == "Мой тест"
    assert response.json()["created_at"]

    response = client.get("/api/xml-library/personal")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get("/api/xml-library/personal/Мой%20тест")
    assert response.status_code == 200
    assert response.json()["xml_text"] == "<root>personal</root>"

    updated = {**SAMPLE_PERSONAL, "description": "updated"}
    response = client.put("/api/xml-library/personal/Мой%20тест", json=updated)
    assert response.status_code == 200
    assert response.json()["description"] == "updated"

    response = client.delete("/api/xml-library/personal/Мой%20тест")
    assert response.status_code == 200

    response = client.get("/api/xml-library/personal/Мой%20тест")
    assert response.status_code == 404


def test_list_personal_filters_by_schema(client: TestClient):
    docs_dir = dev_user_context().xml_documents_dir
    docs_dir.mkdir(parents=True, exist_ok=True)
    for path in docs_dir.glob("*.json"):
        path.unlink()

    client.post("/api/xml-library/personal", json=SAMPLE_PERSONAL)
    client.post(
        "/api/xml-library/personal",
        json={**SAMPLE_PERSONAL, "name": "Other", "schema_id": "schema-2"},
    )

    response = client.get("/api/xml-library/personal", params={"schema_id": "schema-1"})
    assert response.status_code == 200
    names = [d["name"] for d in response.json()]
    assert names == ["Мой тест"]
