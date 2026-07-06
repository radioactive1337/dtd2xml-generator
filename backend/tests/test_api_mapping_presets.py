"""Tests for mapping preset API endpoints."""

import json

from fastapi.testclient import TestClient

from app.user_context import dev_user_context

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


def test_save_and_load_mapping_preset_with_field_overrides(client: TestClient):
    preset = {
        **SAMPLE_PRESET,
        "field_overrides": [
            {
                "target_path": "PayDoc.Body.client[0]",
                "xml_attr": "inn",
                "value": "7707083893",
            }
        ],
    }
    response = client.post("/api/mapping-presets", json=preset)
    assert response.status_code == 200
    assert response.json()["field_overrides"][0]["value"] == "7707083893"

    response = client.get("/api/mapping-presets/Customer%20mapping")
    assert response.status_code == 200
    data = response.json()
    assert data["field_overrides"][0]["xml_attr"] == "inn"


def test_list_mapping_presets_filters_by_schema(client: TestClient):
    presets_dir = dev_user_context().mapping_presets_dir
    for path in presets_dir.glob("*.json"):
        path.unlink()

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


def test_load_legacy_dict_fields(client: TestClient):
    presets_dir = dev_user_context().mapping_presets_dir
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
