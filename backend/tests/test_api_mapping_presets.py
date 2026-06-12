"""Tests for mapping preset API endpoints."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import mapping_presets as mapping_presets_routes
from app.main import app


@pytest.fixture(autouse=True)
def isolated_presets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    presets_dir = tmp_path / "mapping_presets"
    monkeypatch.setattr(mapping_presets_routes, "PRESETS_DIR", presets_dir)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


SAMPLE_PRESET = {
    "name": "Customer mapping",
    "schema_id": "schema-1",
    "mappings": [
        {
            "target_element": "Customer",
            "query": "SELECT id, name FROM customers WHERE ROWNUM = 1",
            "db_alias": "oracle_dev",
            "fields": [
                {"db_col": "id", "xml_attr": "customerId"},
                {"db_col": "name", "xml_attr": "customerName"},
            ],
        }
    ],
}


def test_save_and_load_mapping_preset(client: TestClient):
    response = client.post("/api/mapping-presets", json=SAMPLE_PRESET)
    assert response.status_code == 200
    assert response.json()["name"] == "Customer mapping"
    assert "db_alias" not in response.json()

    response = client.get("/api/mapping-presets/Customer%20mapping")
    assert response.status_code == 200
    data = response.json()
    assert data["mappings"][0]["db_alias"] == "oracle_dev"
    assert data["mappings"][0]["fields"][0]["db_col"] == "id"


def test_list_mapping_presets_filters_by_schema(client: TestClient):
    client.post("/api/mapping-presets", json=SAMPLE_PRESET)
    client.post(
        "/api/mapping-presets",
        json={**SAMPLE_PRESET, "name": "Other schema", "schema_id": "schema-2"},
    )

    response = client.get("/api/mapping-presets")
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client.get("/api/mapping-presets", params={"schema_id": "schema-1"})
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Customer mapping"]


def test_delete_mapping_preset(client: TestClient):
    client.post("/api/mapping-presets", json=SAMPLE_PRESET)

    response = client.delete("/api/mapping-presets/Customer%20mapping")
    assert response.status_code == 200

    response = client.get("/api/mapping-presets/Customer%20mapping")
    assert response.status_code == 404


def test_load_legacy_dict_fields(client: TestClient, tmp_path: Path):
    presets_dir = mapping_presets_routes.PRESETS_DIR
    presets_dir.mkdir(parents=True, exist_ok=True)
    legacy = {
        "name": "Legacy",
        "schema_id": "",
        "db_alias": "pg",
        "mappings": [
            {
                "target_element": "Item",
                "query": "SELECT a FROM t",
                "fields": {"a": "attrA"},
            }
        ],
    }
    (presets_dir / "Legacy.json").write_text(json.dumps(legacy), encoding="utf-8")

    response = client.get("/api/mapping-presets/Legacy")
    assert response.status_code == 200
    data = response.json()
    assert data["mappings"][0]["fields"] == [{"db_col": "a", "xml_attr": "attrA"}]
    assert data["mappings"][0]["db_alias"] == "pg"
    assert "db_alias" not in data
