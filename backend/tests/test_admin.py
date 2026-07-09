"""Tests for admin functionality."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth.users import DEFAULT_ADMIN_USERNAME, ensure_admin_user, get_admin_user
from tests.conftest import login_as


def _login_admin(client: TestClient) -> dict:
    admin = get_admin_user()
    assert admin is not None
    return login_as(client, admin.display_name, create=False)


def test_admin_created_on_init(auth_client: TestClient):
    admin = get_admin_user()
    assert admin is not None
    assert admin.display_name == DEFAULT_ADMIN_USERNAME
    assert admin.is_admin is True


def test_admin_me_flag(auth_client: TestClient):
    _login_admin(auth_client)
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["is_admin"] is True
    assert data["display_name"] == DEFAULT_ADMIN_USERNAME


def test_regular_user_not_admin(auth_client: TestClient):
    login_as(auth_client, "regular_user", create=True)
    response = auth_client.get("/api/auth/me")
    assert response.json()["is_admin"] is False


def test_admin_routes_require_admin(auth_client: TestClient):
    login_as(auth_client, "bob", create=True)
    assert auth_client.get("/api/admin/stats").status_code == 403
    assert auth_client.get("/api/admin/users").status_code == 403
    assert auth_client.get("/api/admin/backup").status_code == 403


def test_admin_stats(auth_client: TestClient):
    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)
    alice_client = TestClient(auth_client.app)
    login_as(alice_client, "alice", create=True)

    response = admin_client.get("/api/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["users_count"] >= 2
    assert "dtd_schemas_count" in data
    assert "allow_self_registration" in data


def test_admin_list_users(auth_client: TestClient):
    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)
    charlie_client = TestClient(auth_client.app)
    login_as(charlie_client, "charlie", create=True)

    response = admin_client.get("/api/admin/users")
    assert response.status_code == 200
    data = response.json()
    names = {u["display_name"] for u in data["users"]}
    assert DEFAULT_ADMIN_USERNAME in names
    assert "charlie" in names


def test_admin_create_user(auth_client: TestClient):
    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)

    response = admin_client.post("/api/admin/users", json={"username": "newbie"})
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] == "newbie"
    assert data["is_admin"] is False
    assert data["presets_count"] == 0

    names = {u["display_name"] for u in admin_client.get("/api/admin/users").json()["users"]}
    assert "newbie" in names


def test_admin_create_user_duplicate(auth_client: TestClient):
    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)
    admin_client.post("/api/admin/users", json={"username": "dup"})

    response = admin_client.post("/api/admin/users", json={"username": "dup"})
    assert response.status_code == 409


def test_admin_create_user_requires_admin(auth_client: TestClient):
    bob_client = TestClient(auth_client.app)
    login_as(bob_client, "bob", create=True)

    response = bob_client.post("/api/admin/users", json={"username": "hacker"})
    assert response.status_code == 403


def test_admin_delete_user(auth_client: TestClient):
    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)

    victim_client = TestClient(auth_client.app)
    victim = login_as(victim_client, "victim", create=True)
    victim_root = Path("data") / "users" / victim["id"]
    # tmp_path monkeypatch makes DATA_DIR isolated — check via API instead

    response = admin_client.delete(f"/api/admin/users/{victim['id']}")
    assert response.status_code == 200

    assert admin_client.get("/api/admin/users").json()["users"]
    names = {u["display_name"] for u in admin_client.get("/api/admin/users").json()["users"]}
    assert "victim" not in names


def test_cannot_delete_admin(auth_client: TestClient):
    admin_client = TestClient(auth_client.app)
    admin = _login_admin(admin_client)

    response = admin_client.delete(f"/api/admin/users/{admin['id']}")
    assert response.status_code == 400


def test_admin_backup(auth_client: TestClient, tmp_path: Path, monkeypatch):
    from app.config import DATA_DIR

    marker = DATA_DIR / "backup-marker.txt"
    marker.write_text("test", encoding="utf-8")

    _login_admin(auth_client)
    response = auth_client.get("/api/admin/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert any(name.endswith("backup-marker.txt") for name in names)


def test_admin_settings_toggle(auth_client: TestClient, tmp_path: Path, monkeypatch):
    from app import config

    app_config = tmp_path / "app.json"
    app_config.write_text(
        json.dumps({"app": {"allow_self_registration": True}}, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "APP_CONFIG_FILE", app_config)
    monkeypatch.delenv("ALLOW_SELF_REGISTRATION", raising=False)
    config._invalidate_app_config_cache()

    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)

    response = admin_client.put(
        "/api/admin/settings",
        json={"allow_self_registration": False},
    )
    assert response.status_code == 200
    assert response.json()["allow_self_registration"] is False

    assert admin_client.get("/api/admin/settings").json()["allow_self_registration"] is False

    new_user_client = TestClient(auth_client.app)
    conflict = new_user_client.post(
        "/api/auth/login",
        json={"username": "blocked_user", "create": True},
    )
    assert conflict.status_code == 403


def test_only_one_admin(auth_client: TestClient):
    ensure_admin_user()
    admin = get_admin_user()
    assert admin is not None

    from app.auth.users import list_all_users

    admins = [u for u in list_all_users() if u.is_admin]
    assert len(admins) == 1
