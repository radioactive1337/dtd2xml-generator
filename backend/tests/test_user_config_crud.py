"""Tests for per-user connection CRUD."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import USER_ALIAS_FORBIDDEN_DETAIL
from tests.conftest import login_as


def test_user_cannot_create_database_alias(auth_client: TestClient):
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
    assert create.status_code == 403
    assert create.json()["detail"] == USER_ALIAS_FORBIDDEN_DETAIL
    assert "MY_DB" not in auth_client.get("/api/config/aliases").json()["databases"]


def test_user_cannot_create_llm_alias(auth_client: TestClient):
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
    assert response.status_code == 403
    assert response.json()["detail"] == USER_ALIAS_FORBIDDEN_DETAIL
    assert "OLLAMA" not in auth_client.get("/api/config/aliases").json()["llm"]


def test_user_cannot_delete_database_alias(auth_client: TestClient):
    login_as(auth_client, "del_user", create=True)
    delete = auth_client.delete("/api/config/databases/TMP")
    assert delete.status_code == 403
    assert delete.json()["detail"] == USER_ALIAS_FORBIDDEN_DETAIL


def test_git_settings_crud(auth_client: TestClient):
    login_as(auth_client, "git_user", create=True)

    initial = auth_client.get("/api/config/git")
    assert initial.status_code == 200
    assert initial.json()["configured"] is False

    update = auth_client.put(
        "/api/config/git",
        json={"token": "user-git-token", "user": "oauth2"},
    )
    assert update.status_code == 200
    assert update.json()["configured"] is True
    assert update.json()["user"] == "oauth2"
    assert "token" not in update.json()

    author_update = auth_client.put(
        "/api/config/git",
        json={"author_name": "Test User", "author_email": "test@example.com"},
    )
    assert author_update.status_code == 200
    assert author_update.json()["author_configured"] is True
    assert author_update.json()["author_name"] == "Test User"
    assert author_update.json()["author_email"] == "test@example.com"

    configured = auth_client.get("/api/config/git")
    assert configured.json()["configured"] is True

    delete = auth_client.delete("/api/config/git")
    assert delete.status_code == 200
    assert auth_client.get("/api/config/git").json()["configured"] is False
