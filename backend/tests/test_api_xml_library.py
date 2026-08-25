"""Tests for XML library API endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes import dtd as dtd_routes
from app.config import ReferenceXmlSettings
from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef
from app.services.git_push_service import PushResult
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


@pytest.fixture
def reference_xml_push_enabled(reference_xml_tree: Path, monkeypatch: pytest.MonkeyPatch):
    settings = ReferenceXmlSettings(
        enabled=True,
        push_enabled=True,
        repo_url="https://github.com/org/xml-library.git",
        branch="main",
        subdir="xml-library",
        cache_dir=str(reference_xml_tree.parent),
    )
    monkeypatch.setattr("app.config.get_reference_xml_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.xml_library.get_reference_xml_settings", lambda: settings)
    return settings


def _register_test_schema(schema_id: str = "push-test-schema") -> str:
    schema = DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="(Body)",
                content_model=ContentNode(
                    kind="SEQUENCE",
                    children=[ContentNode(kind="REF", ref="Body")],
                ),
                attributes={
                    "id": AttributeDef(name="id", attr_type="ID", default_decl="#REQUIRED"),
                    "kladr": AttributeDef(name="kladr", attr_type="CDATA", default_decl="#IMPLIED"),
                    "active": AttributeDef(name="active", attr_type="CDATA", default_decl="#IMPLIED"),
                },
            ),
            "Body": ElementDef(
                name="Body",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={},
            ),
        }
    )
    dtd_routes._schema_registry[schema_id] = schema
    return schema_id


def test_push_rejects_insufficient_attribute_fill(
    client: TestClient,
    reference_xml_push_enabled: ReferenceXmlSettings,
):
    schema_id = _register_test_schema()
    xml_text = '<PayDoc id="id-1" kladr="" active=""><Body/></PayDoc>'

    with patch("app.api.routes.xml_library.push_document", new=AsyncMock()) as push_mock:
        response = client.post(
            "/api/xml-library/shared/push",
            json={
                "schema_id": schema_id,
                "root_element": "PayDoc",
                "filename": "sparse.xml",
                "xml_text": xml_text,
            },
        )

    assert response.status_code == 400
    assert "15%" in response.json()["detail"]
    assert "заполнено" in response.json()["detail"]
    push_mock.assert_not_called()


def test_push_uses_xml_root_not_claimed_root(
    client: TestClient,
    reference_xml_push_enabled: ReferenceXmlSettings,
):
    schema_id = _register_test_schema()
    xml_text = (
        '<PayDoc id="real-id" kladr="7700000000000" active="true">'
        "<Body/></PayDoc>"
    )
    mock_result = PushResult(
        status="ok",
        commit_sha="abc1234",
        path="xml-library/PayDoc/paydoc.xml",
        message="added",
        overwritten=False,
    )

    with (
        patch(
            "app.api.routes.xml_library.git_push_attribute_fill_error",
            return_value=None,
        ),
        patch(
            "app.api.routes.xml_library.format_push_rule_error",
            return_value=None,
        ),
        patch(
            "app.api.routes.xml_library.ensure_git_commit_author",
            return_value=("Dev", "dev@example.com"),
        ),
        patch(
            "app.api.routes.xml_library.push_document",
            new=AsyncMock(return_value=mock_result),
        ) as push_mock,
        patch(
            "app.api.routes.xml_library.sync_reference_repository",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            "/api/xml-library/shared/push",
            json={
                "schema_id": schema_id,
                "root_element": "abs-client",
                "filename": "paydoc.xml",
                "xml_text": xml_text,
            },
        )

    assert response.status_code == 200
    assert push_mock.call_args.kwargs["root_element"] == "PayDoc"


def test_push_rejects_unparseable_xml_root(
    client: TestClient,
    reference_xml_push_enabled: ReferenceXmlSettings,
):
    schema_id = _register_test_schema()

    with (
        patch(
            "app.api.routes.xml_library.git_push_attribute_fill_error",
            return_value=None,
        ),
        patch(
            "app.api.routes.xml_library.format_push_rule_error",
            return_value=None,
        ),
        patch("app.api.routes.xml_library.push_document", new=AsyncMock()) as push_mock,
    ):
        response = client.post(
            "/api/xml-library/shared/push",
            json={
                "schema_id": schema_id,
                "root_element": "abs-client",
                "filename": "broken.xml",
                "xml_text": "<not-closed",
            },
        )

    assert response.status_code == 400
    assert "корневой элемент" in response.json()["detail"]
    push_mock.assert_not_called()


def test_push_requires_ack_when_warning_rules_fail(
    client: TestClient,
    reference_xml_push_enabled: ReferenceXmlSettings,
):
    schema_id = _register_test_schema()
    xml_text = (
        '<PayDoc id="real-id" kladr="7700000000000" active="true" status="FOO">'
        "<Body/></PayDoc>"
    )

    with patch("app.api.routes.xml_library.push_document", new=AsyncMock()) as push_mock:
        response = client.post(
            "/api/xml-library/shared/push",
            json={
                "schema_id": schema_id,
                "root_element": "PayDoc",
                "filename": "paydoc.xml",
                "xml_text": xml_text,
            },
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "warnings_require_ack"
    assert detail["warning_count"] >= 1
    assert any("status" in item["location"] for item in detail["warnings"])
    push_mock.assert_not_called()


def test_push_proceeds_when_warnings_acknowledged(
    client: TestClient,
    reference_xml_push_enabled: ReferenceXmlSettings,
):
    schema_id = _register_test_schema()
    xml_text = (
        '<PayDoc id="real-id" kladr="7700000000000" active="true" status="FOO">'
        "<Body/></PayDoc>"
    )
    mock_result = PushResult(
        status="ok",
        commit_sha="abc1234",
        path="xml-library/PayDoc/paydoc.xml",
        message="added",
        overwritten=False,
    )

    with (
        patch(
            "app.api.routes.xml_library.ensure_git_commit_author",
            return_value=("Dev", "dev@example.com"),
        ),
        patch(
            "app.api.routes.xml_library.push_document",
            new=AsyncMock(return_value=mock_result),
        ) as push_mock,
        patch(
            "app.api.routes.xml_library.sync_reference_repository",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            "/api/xml-library/shared/push",
            json={
                "schema_id": schema_id,
                "root_element": "PayDoc",
                "filename": "paydoc.xml",
                "xml_text": xml_text,
                "acknowledge_warnings": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["warnings"]
    push_mock.assert_called_once()
