"""Tests for per-user data isolation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_types_dtd() -> None:
    from app.config import shared_dtd_dir

    dtd_dir = shared_dtd_dir()
    dtd_dir.mkdir(parents=True, exist_ok=True)
    (dtd_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())


def _upload_dtd(client: TestClient) -> str:
    _seed_types_dtd()
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert response.status_code == 200
    return response.json()["primary_schema_id"]


def test_dtd_schemas_shared_between_users(user_a_client: TestClient, user_b_client: TestClient):
    schema_id = _upload_dtd(user_a_client)

    response_b = user_b_client.get("/api/dtd/schemas")
    assert response_b.status_code == 200
    data_b = response_b.json()
    ids_b = {item["schema_id"] for item in data_b["schemas"]}
    assert schema_id in ids_b
    assert data_b["import_source"] == "Загрузка: main.dtd"

    response_a = user_a_client.get("/api/dtd/schemas")
    ids_a = {item["schema_id"] for item in response_a.json()["schemas"]}
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
