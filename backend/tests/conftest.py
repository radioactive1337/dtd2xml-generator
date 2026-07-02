"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import dtd as dtd_routes
from app.api.routes import generate as generate_routes
from app.auth.users import init_user_db
from app.config import is_auth_disabled
from app.main import app
from app.user_context import UserContext


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.DATA_DIR", data_dir)
    monkeypatch.setattr("app.auth.users.DATA_DIR", data_dir)
    monkeypatch.setattr("app.legacy_migration.DATA_DIR", data_dir)
    monkeypatch.setattr("app.legacy_migration._MIGRATION_FLAG", data_dir / ".legacy_migrated")
    init_user_db()


@pytest.fixture(autouse=True)
def _default_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")


@pytest.fixture(autouse=True)
def _dev_user_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from app.auth import sessions as auth_sessions
    from app.user_context import UserContext

    root = tmp_path / "dev-user-root"
    root.mkdir(parents=True, exist_ok=True)
    ctx = UserContext(user_id="dev-local", display_name="dev", root=root)
    ctx.ensure_workspace()

    monkeypatch.setattr("app.user_context.dev_user_context", lambda: ctx)

    async def _dev_user(_request=None):
        return ctx

    original_get_current_user = auth_sessions.get_current_user

    async def _get_current_user(request):
        if is_auth_disabled():
            return ctx
        return await original_get_current_user(request)

    monkeypatch.setattr(auth_sessions, "get_current_user", _get_current_user)


@pytest.fixture
def auth_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_client(auth_enabled: None) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_registries():
    dtd_routes._schema_registry.clear()
    generate_routes._last_generated.clear()
    yield
    dtd_routes._schema_registry.clear()
    generate_routes._last_generated.clear()


@pytest.fixture
def test_user_ctx(tmp_path: Path) -> UserContext:
    root = tmp_path / "user-workspace"
    root.mkdir(parents=True, exist_ok=True)
    ctx = UserContext(user_id="test-user-id", display_name="tester", root=root)
    ctx.ensure_workspace()
    return ctx


def login_as(client: TestClient, username: str, *, create: bool = True) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "create": create})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def user_a_client(auth_enabled: None) -> TestClient:
    client = TestClient(app)
    login_as(client, "alice")
    return client


@pytest.fixture
def user_b_client(auth_enabled: None) -> TestClient:
    client = TestClient(app)
    login_as(client, "bob")
    return client
