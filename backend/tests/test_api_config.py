"""Tests for connection test API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_test_db_success(client: TestClient):
    with patch(
        "app.api.routes.config.DBService.test_connection",
        new=AsyncMock(return_value="Connected (postgresql)"),
    ):
        response = client.post("/api/config/test-db", json={"alias": "PGSQL_DB"})

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "alias": "PGSQL_DB",
        "ok": True,
        "message": "Connected (postgresql)",
    }


def test_test_db_failure_returns_ok_false(client: TestClient):
    with patch(
        "app.api.routes.config.DBService.test_connection",
        new=AsyncMock(side_effect=ValueError("connection refused")),
    ):
        response = client.post("/api/config/test-db", json={"alias": "PGSQL_DB"})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "connection refused" in data["message"]


def test_test_db_rejects_empty_alias(client: TestClient):
    response = client.post("/api/config/test-db", json={"alias": "   "})
    assert response.status_code == 400


def test_test_llm_success(client: TestClient):
    with patch(
        "app.api.routes.config.LLMService.test_connection",
        new=AsyncMock(return_value="Reachable (model: gpt-4o-mini)"),
    ):
        response = client.post("/api/config/test-llm", json={"alias": "default"})

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "alias": "default",
        "ok": True,
        "message": "Reachable (model: gpt-4o-mini)",
    }


def test_test_llm_failure_returns_ok_false(client: TestClient):
    with patch(
        "app.api.routes.config.LLMService.test_connection",
        new=AsyncMock(side_effect=ValueError("LLM request failed: connection refused")),
    ):
        response = client.post("/api/config/test-llm", json={"alias": "default"})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "connection refused" in data["message"]


def test_test_llm_rejects_empty_alias(client: TestClient):
    response = client.post("/api/config/test-llm", json={"alias": ""})
    assert response.status_code == 400


def test_set_default_llm_success(client: TestClient):
    with patch(
        "app.api.routes.config.set_default_llm_alias",
        return_value="PROD_LLM",
    ):
        response = client.put("/api/config/default-llm", json={"alias": "PROD_LLM"})

    assert response.status_code == 200
    assert response.json() == {"default_llm": "PROD_LLM"}


def test_set_default_llm_rejects_invalid_alias(client: TestClient):
    with patch(
        "app.api.routes.config.set_default_llm_alias",
        side_effect=ValueError("LLM alias 'missing' is not configured. Available: default"),
    ):
        response = client.put("/api/config/default-llm", json={"alias": "missing"})

    assert response.status_code == 400
    assert "missing" in response.json()["detail"]
