"""Tests for peer preset sharing between users."""

from __future__ import annotations

from fastapi.testclient import TestClient

SAMPLE_MAPPING_PRESET = {
    "name": "Customer mapping",
    "schema_id": "schema-1",
    "mappings": [
        {
            "target_element": "Customer",
            "query": "SELECT id FROM customers",
            "db_alias": "oracle_dev",
            "fields": [{"db_col": "id", "xml_attr": "customerId"}],
        }
    ],
}

SAMPLE_TREE_PRESET = {
    "name": "My selection",
    "schema_id": "schema-1",
    "custom_paths": ["Root.Child[0].Field", "Root.Other"],
}


def test_share_mapping_preset_success(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    response = user_a_client.post("/api/mapping-presets", json=SAMPLE_MAPPING_PRESET)
    assert response.status_code == 200, response.text

    response = user_a_client.post(
        "/api/mapping-presets/share",
        json={
            "recipient_username": "bob",
            "source_preset_name": "Customer mapping",
            "message": "Для проверки",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["recipient_display_name"] == "bob"
    assert data["preset_name"] == "Customer mapping"

    bob_presets = user_b_client.get("/api/mapping-presets").json()
    assert len(bob_presets) == 1
    assert bob_presets[0]["name"] == "Customer mapping"
    assert bob_presets[0]["shared_by_name"] == "alice"

    loaded = user_b_client.get("/api/mapping-presets/Customer%20mapping").json()
    assert loaded["mappings"][0]["db_alias"] == "oracle_dev"

    alice_presets = user_a_client.get("/api/mapping-presets").json()
    assert any(p["name"] == "Customer mapping" for p in alice_presets)


def test_share_tree_preset_success(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    response = user_a_client.post("/api/presets", json=SAMPLE_TREE_PRESET)
    assert response.status_code == 200, response.text

    response = user_a_client.post(
        "/api/presets/share",
        json={
            "recipient_username": "bob",
            "source_preset_name": "My selection",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["preset_name"] == "My selection"

    bob_presets = user_b_client.get("/api/presets").json()
    assert len(bob_presets) == 1
    assert bob_presets[0]["shared_by_name"] == "alice"

    loaded = user_b_client.get("/api/presets/My%20selection").json()
    assert loaded["custom_paths"] == SAMPLE_TREE_PRESET["custom_paths"]


def test_share_mapping_preset_source_not_found(user_a_client: TestClient):
    response = user_a_client.post(
        "/api/mapping-presets/share",
        json={
            "recipient_username": "bob",
            "source_preset_name": "missing",
        },
    )
    assert response.status_code == 404


def test_share_mapping_preset_recipient_not_found(user_a_client: TestClient):
    user_a_client.post("/api/mapping-presets", json=SAMPLE_MAPPING_PRESET)
    response = user_a_client.post(
        "/api/mapping-presets/share",
        json={
            "recipient_username": "nobody",
            "source_preset_name": "Customer mapping",
        },
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message"] == "User 'nobody' not found"


def test_share_mapping_preset_to_self(user_a_client: TestClient):
    user_a_client.post("/api/mapping-presets", json=SAMPLE_MAPPING_PRESET)
    response = user_a_client.post(
        "/api/mapping-presets/share",
        json={
            "recipient_username": "alice",
            "source_preset_name": "Customer mapping",
        },
    )
    assert response.status_code == 400
    assert "yourself" in response.json()["detail"].lower()


def test_share_mapping_preset_name_conflict(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    user_b_client.post("/api/mapping-presets", json=SAMPLE_MAPPING_PRESET)
    user_a_client.post("/api/mapping-presets", json=SAMPLE_MAPPING_PRESET)

    response = user_a_client.post(
        "/api/mapping-presets/share",
        json={
            "recipient_username": "bob",
            "source_preset_name": "Customer mapping",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["preset_name"] == "Customer mapping (от alice)"

    response = user_a_client.post(
        "/api/mapping-presets/share",
        json={
            "recipient_username": "bob",
            "source_preset_name": "Customer mapping",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["preset_name"] == "Customer mapping (от alice) (2)"
