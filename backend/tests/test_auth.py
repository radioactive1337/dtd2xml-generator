"""Tests for passwordless authentication."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login_as


def test_exists_unknown_user(auth_client: TestClient):
    response = auth_client.get("/api/auth/exists", params={"username": "nobody"})
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert isinstance(data["suggestions"], list)


def test_login_existing_user(auth_client: TestClient):
    login_as(auth_client, "john", create=True)
    client2 = TestClient(auth_client.app)
    response = client2.post("/api/auth/login", json={"username": "john", "create": False})
    assert response.status_code == 200
    assert response.json()["display_name"] == "john"


def test_login_unknown_without_create_returns_409(auth_client: TestClient):
    response = auth_client.post("/api/auth/login", json={"username": "newuser", "create": False})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "not found" in detail["message"].lower()
    assert isinstance(detail["suggestions"], list)


def test_login_create_user(auth_client: TestClient):
    response = auth_client.post("/api/auth/login", json={"username": "ivan", "create": True})
    assert response.status_code == 200
    assert response.json()["display_name"] == "ivan"


def test_username_normalization(auth_client: TestClient):
    auth_client.post("/api/auth/login", json={"username": "Ivan", "create": True})
    response = auth_client.post("/api/auth/login", json={"username": "ivan", "create": False})
    assert response.status_code == 200


def test_me_requires_session(auth_client: TestClient):
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_after_login(auth_client: TestClient):
    login_as(auth_client, "me_user", create=True)
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["display_name"] == "me_user"


def test_logout(auth_client: TestClient):
    login_as(auth_client, "logout_user", create=True)
    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 401


def test_protected_route_requires_auth(auth_client: TestClient):
    response = auth_client.get("/api/dtd/schemas")
    assert response.status_code == 401
