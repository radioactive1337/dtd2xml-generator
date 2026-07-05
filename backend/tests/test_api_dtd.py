"""Tests for DTD API endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_aliases_no_secrets(client: TestClient):
    response = client.get("/api/config/aliases")
    assert response.status_code == 200
    data = response.json()
    assert "databases" in data
    assert "llm" in data
    assert "default_llm" in data


def test_upload_dtd(client: TestClient):
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files={"file": ("main.dtd", f, "application/xml-dtd")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "schema_id" in data
    assert data["element_count"] > 0
    assert "PayDoc" in data["elements"]


def test_list_schemas(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get("/api/dtd/schemas")
    assert response.status_code == 200
    schemas = response.json()
    assert len(schemas) == 1
    assert schemas[0]["schema_id"] == schema_id
    assert schemas[0]["element_count"] > 0
    assert "PayDoc" in schemas[0]["elements"]


def test_list_elements(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get(f"/api/dtd/{schema_id}/elements")
    assert response.status_code == 200
    elements = response.json()
    names = [e["name"] for e in elements]
    assert "PayDoc" in names
    paydoc = next(e for e in elements if e["name"] == "PayDoc")
    assert "Основной корневой элемент" in paydoc["doc"]
    assert paydoc["attribute_docs"].get("kladr") == "код КЛАДР"


def test_get_element_detail(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get(f"/api/dtd/{schema_id}/elements/PayDoc")
    assert response.status_code == 200
    data = response.json()
    assert data["element"]["name"] == "PayDoc"
    assert "Основной корневой элемент" in data["element"]["doc"]
    assert "kladr" in data["element"]["required_attributes"]


def test_get_element_tree(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get(f"/api/dtd/{schema_id}/elements/PayDoc/tree")
    assert response.status_code == 200
    data = response.json()
    assert data["element"] == "PayDoc"
    assert data["content_model"]["kind"] == "SEQUENCE"


def test_schema_not_found(client: TestClient):
    response = client.get("/api/dtd/nonexistent/elements")
    assert response.status_code == 404


def _upload_fixture(client: TestClient) -> str:
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files={"file": ("main.dtd", f, "application/xml-dtd")},
        )
    return response.json()["schema_id"]
