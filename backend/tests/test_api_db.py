"""Tests for database introspection API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_query_preview_returns_row(client: TestClient):
    with patch(
        "app.api.routes.db.DBService.run_query",
        new=AsyncMock(return_value=[{"inn": "7701", "name": "Acme"}]),
    ):
        response = client.post(
            "/api/db/query-preview",
            json={"db_alias": "oracle_dev", "query": "SELECT inn, name FROM t"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["columns"] == ["inn", "name"]
    assert data["row"] == {"inn": "7701", "name": "Acme"}


def test_query_preview_zero_rows_returns_null_row(client: TestClient):
    with patch(
        "app.api.routes.db.DBService.run_query",
        new=AsyncMock(return_value=[]),
    ):
        with patch(
            "app.api.routes.db.DBService.get_query_columns",
            new=AsyncMock(return_value=["inn", "name"]),
        ):
            response = client.post(
                "/api/db/query-preview",
                json={"db_alias": "oracle_dev", "query": "SELECT inn, name FROM t WHERE 1=0"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["columns"] == ["inn", "name"]
    assert data["row"] is None


def test_query_preview_rejects_empty_query(client: TestClient):
    response = client.post(
        "/api/db/query-preview",
        json={"db_alias": "oracle_dev", "query": "   "},
    )
    assert response.status_code == 400
    assert "required" in response.json()["detail"].lower()


def test_query_preview_unknown_alias(client: TestClient):
    with patch(
        "app.api.routes.db.DBService.run_query",
        new=AsyncMock(side_effect=ValueError("Database alias 'missing' not found")),
    ):
        response = client.post(
            "/api/db/query-preview",
            json={"db_alias": "missing", "query": "SELECT 1 FROM dual"},
        )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_query_preview_invalid_sql(client: TestClient):
    with patch(
        "app.api.routes.db.DBService.run_query",
        new=AsyncMock(side_effect=ValueError("Only SELECT queries are allowed")),
    ):
        response = client.post(
            "/api/db/query-preview",
            json={"db_alias": "oracle_dev", "query": "DELETE FROM t"},
        )

    assert response.status_code == 400
    assert "SELECT" in response.json()["detail"]
