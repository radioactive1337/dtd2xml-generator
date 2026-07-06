"""Tests for per-user data isolation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _upload_dtd(client: TestClient) -> str:
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert response.status_code == 200
    return response.json()["primary_schema_id"]


def test_dtd_schemas_isolated_between_users(user_a_client: TestClient, user_b_client: TestClient):
    schema_id = _upload_dtd(user_a_client)

    response_b = user_b_client.get("/api/dtd/schemas")
    assert response_b.status_code == 200
    ids_b = {item["schema_id"] for item in response_b.json()}
    assert schema_id not in ids_b

    response_a = user_a_client.get("/api/dtd/schemas")
    ids_a = {item["schema_id"] for item in response_a.json()}
    assert schema_id in ids_a


def test_config_aliases_isolated(user_a_client: TestClient, user_b_client: TestClient):
    user_a_client.post(
        "/api/config/databases",
        json={
            "alias": "PG_A",
            "driver": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "db",
            "user": "u",
            "password": "p",
        },
    )

    aliases_a = user_a_client.get("/api/config/aliases").json()
    aliases_b = user_b_client.get("/api/config/aliases").json()

    assert "PG_A" in aliases_a["databases"]
    assert "PG_A" not in aliases_b["databases"]
