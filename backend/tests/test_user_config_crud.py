"""Tests for per-user connection CRUD."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login_as


def test_create_and_list_database_alias(auth_client: TestClient):
    login_as(auth_client, "config_user", create=True)

    create = auth_client.post(
        "/api/config/databases",
        json={
            "alias": "MY_DB",
            "driver": "postgresql",
            "host": "db.local",
            "port": 5432,
            "database": "qa",
            "user": "qa",
            "password": "secret",
        },
    )
    assert create.status_code == 200
    data = create.json()
    assert data["alias"] == "MY_DB"
    assert "password" not in data

    connections = auth_client.get("/api/config/connections").json()
    aliases = [db["alias"] for db in connections["databases"]]
    assert "MY_DB" in aliases


def test_create_llm_alias_without_leaking_secret(auth_client: TestClient):
    login_as(auth_client, "llm_user", create=True)

    response = auth_client.post(
        "/api/config/llm",
        json={
            "alias": "OLLAMA",
            "base_url": "http://localhost:11434/v1",
            "api_key": "top-secret",
            "model": "gpt-4o-mini",
            "timeout": 120,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["alias"] == "OLLAMA"
    assert "api_key" not in body
    assert "top-secret" not in str(body)


def test_delete_database_alias(auth_client: TestClient):
    login_as(auth_client, "del_user", create=True)
    auth_client.post(
        "/api/config/databases",
        json={
            "alias": "TMP",
            "driver": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "db",
            "user": "u",
            "password": "p",
        },
    )
    delete = auth_client.delete("/api/config/databases/TMP")
    assert delete.status_code == 200
    aliases = auth_client.get("/api/config/aliases").json()["databases"]
    assert "TMP" not in aliases
