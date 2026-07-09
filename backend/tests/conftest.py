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
    from app.auth.sessions import get_current_user
    from app.user_context import UserContext

    root = tmp_path / "dev-user-root"
    root.mkdir(parents=True, exist_ok=True)
    ctx = UserContext(user_id="dev-local", display_name="dev", root=root)
    ctx.ensure_workspace()

    monkeypatch.setattr("app.user_context.dev_user_context", lambda: ctx)

    async def _dev_user(_request=None):
        return ctx

    app.dependency_overrides[get_current_user] = _dev_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_enabled(monkeypatch: pytest.MonkeyPatch):
    from app.auth.sessions import get_current_user

    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_client(auth_enabled: None) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_registries():
    import shutil

    from app.config import DATA_DIR, shared_dtd_dir

    dtd_routes._schema_registry.clear()
    generate_routes._last_generated.clear()
    shared = shared_dtd_dir()
    if shared.is_dir():
        shutil.rmtree(shared)
    migration_flag = DATA_DIR / ".dtd_shared_migrated"
    migration_flag.unlink(missing_ok=True)
    yield
    dtd_routes._schema_registry.clear()
    generate_routes._last_generated.clear()
    if shared.is_dir():
        shutil.rmtree(shared)
    migration_flag.unlink(missing_ok=True)


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


@pytest.fixture
def reference_xml_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Tmp xml-library tree with config monkeypatched for reference XML tests."""
    cache = tmp_path / "reference-xml"
    root = cache / "xml-library"
    add_card = root / "add-card"
    add_card.mkdir(parents=True)
    (add_card / "add-card.txt").write_text("<root/>", encoding="utf-8")

    settings = {
        "enabled": True,
        "repo_url": "https://github.com/org/xml-library.git",
        "branch": "main",
        "subdir": "xml-library",
        "cache_dir": str(cache),
    }

    from app.config import ReferenceXmlSettings

    ref_settings = ReferenceXmlSettings(**settings)

    monkeypatch.setattr("app.config.get_reference_xml_settings", lambda: ref_settings)

    def _cache_dir():
        return cache

    def _root():
        return root

    monkeypatch.setattr("app.config.reference_xml_cache_dir", _cache_dir)
    monkeypatch.setattr("app.config.reference_xml_root", _root)

    return root
