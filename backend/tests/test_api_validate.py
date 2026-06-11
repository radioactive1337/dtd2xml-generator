"""Tests for XML validation API."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import dtd as dtd_routes
from app.config import PROJECT_ROOT
from app.core.xml_builder import BuildConfig, build_xml
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_DIR = PROJECT_ROOT / "dtd_schemas"


@pytest.fixture(autouse=True)
def clear_registry():
    dtd_routes._schema_registry.clear()
    yield
    dtd_routes._schema_registry.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_validate_valid_xml(client: TestClient):
    schema_id = _upload_fixture(client)
    schema = dtd_routes._schema_registry[schema_id]
    xml_text = build_xml(schema, BuildConfig(root_element="PayDoc", mode="minimal")).xml_text

    response = client.post(
        "/api/validate",
        json={"schema_id": schema_id, "xml_text": xml_text},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_validate_invalid_xml(client: TestClient):
    schema_id = _upload_fixture(client)
    schema = dtd_routes._schema_registry[schema_id]
    xml_text = build_xml(schema, BuildConfig(root_element="PayDoc", mode="minimal")).xml_text
    bad_xml = xml_text.replace('id="', 'removed="', 1)

    response = client.post(
        "/api/validate",
        json={"schema_id": schema_id, "xml_text": bad_xml},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1


def test_validate_schema_not_found(client: TestClient):
    response = client.post(
        "/api/validate",
        json={"schema_id": "missing", "xml_text": "<root/>"},
    )
    assert response.status_code == 404


def _upload_fixture(client: TestClient) -> str:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "types.dtd", SCHEMA_DIR / "types.dtd")

    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files={"file": ("main.dtd", f, "application/xml-dtd")},
        )
    return response.json()["schema_id"]
