"""Tests for admin-managed shared DB/LLM aliases."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.users import get_admin_user
from app.config import (
    MANAGED_ALIAS_DETAIL,
    get_db_password,
    get_llm_api_key,
    _save_raw_shared_connections,
)
from tests.conftest import login_as


@pytest.fixture(autouse=True)
def _clear_shared_connections():
    _save_raw_shared_connections({"databases": {}, "llm": {}})
    yield
    _save_raw_shared_connections({"databases": {}, "llm": {}})


def _login_admin(client: TestClient) -> dict:
    admin = get_admin_user()
    assert admin is not None
    return login_as(client, admin.display_name, create=False)


def _seed_shared_db(alias: str = "SHARED_PG", password: str = "shared-secret") -> None:
    _save_raw_shared_connections(
        {
            "databases": {
                alias: {
                    "driver": "postgresql",
                    "host": "shared-host",
                    "port": 5432,
                    "database": "shared_db",
                    "user": "shared_user",
                    "password": password,
                }
            },
            "llm": {},
        }
    )


def _seed_shared_llm(alias: str = "SHARED_LLM", api_key: str = "shared-key") -> None:
    _save_raw_shared_connections(
        {
            "databases": {},
            "llm": {
                alias: {
                    "base_url": "http://shared-llm/v1",
                    "model": "shared-model",
                    "api_key": api_key,
                    "timeout": 90,
                }
            },
        }
    )


def test_shared_db_alias_visible_to_all_users(
    auth_client: TestClient,
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    _seed_shared_db()

    aliases_a = user_a_client.get("/api/config/aliases").json()
    aliases_b = user_b_client.get("/api/config/aliases").json()

    assert "SHARED_PG" in aliases_a["databases"]
    assert "SHARED_PG" in aliases_b["databases"]
    assert "SHARED_PG" in aliases_a["managed_databases"]
    assert "SHARED_PG" in aliases_b["managed_databases"]


def test_personal_aliases_still_isolated(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    user_a_client.post(
        "/api/config/databases",
        json={
            "alias": "PERSONAL_A",
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

    assert "PERSONAL_A" in aliases_a["databases"]
    assert "PERSONAL_A" not in aliases_b["databases"]
    assert "PERSONAL_A" not in aliases_a.get("managed_databases", [])


def test_user_cannot_create_conflicting_shared_db_alias(
    auth_client: TestClient,
    user_a_client: TestClient,
):
    _seed_shared_db("PROD")

    response = user_a_client.post(
        "/api/config/databases",
        json={
            "alias": "PROD",
            "driver": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "db",
            "user": "u",
            "password": "p",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == MANAGED_ALIAS_DETAIL


def test_user_cannot_modify_or_delete_shared_alias(user_a_client: TestClient):
    _seed_shared_db("PROD")

    update = user_a_client.put(
        "/api/config/databases/PROD",
        json={"host": "evil"},
    )
    assert update.status_code == 409
    assert update.json()["detail"] == MANAGED_ALIAS_DETAIL

    delete = user_a_client.delete("/api/config/databases/PROD")
    assert delete.status_code == 409
    assert delete.json()["detail"] == MANAGED_ALIAS_DETAIL


def test_shared_secrets_resolved_for_user(user_a_client: TestClient):
    from app.auth.users import get_user_by_id
    from app.user_context import user_context_from_record

    _save_raw_shared_connections(
        {
            "databases": {
                "PROD": {
                    "driver": "postgresql",
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "user": "u",
                    "password": "overlay-password",
                }
            },
            "llm": {
                "corp": {
                    "base_url": "http://shared-llm/v1",
                    "model": "m",
                    "api_key": "overlay-api-key",
                    "timeout": 90,
                }
            },
        }
    )

    me = user_a_client.get("/api/auth/me").json()
    user = get_user_by_id(me["id"])
    assert user is not None
    ctx = user_context_from_record(user)

    assert get_db_password(ctx, "PROD") == "overlay-password"
    assert get_llm_api_key(ctx, "corp") == "overlay-api-key"


def test_shared_overrides_personal_alias_name(user_a_client: TestClient):
    user_a_client.post(
        "/api/config/databases",
        json={
            "alias": "PROD",
            "driver": "postgresql",
            "host": "personal-host",
            "port": 5432,
            "database": "db",
            "user": "u",
            "password": "personal",
        },
    )
    _seed_shared_db("PROD", password="shared-wins")

    connections = user_a_client.get("/api/config/connections").json()
    prod = next(db for db in connections["databases"] if db["alias"] == "PROD")
    assert prod["host"] == "shared-host"
    assert prod["managed"] is True


def test_admin_shared_crud(auth_client: TestClient):
    _save_raw_shared_connections({"databases": {}, "llm": {}})

    admin_client = TestClient(auth_client.app)
    _login_admin(admin_client)

    create = admin_client.post(
        "/api/admin/databases",
        json={
            "alias": "ADMIN_DB",
            "driver": "postgresql",
            "host": "admin-host",
            "port": 5432,
            "database": "adm",
            "user": "adm",
            "password": "pw",
        },
    )
    assert create.status_code == 200
    assert create.json()["managed"] is True

    listed = admin_client.get("/api/admin/connections").json()
    assert any(db["alias"] == "ADMIN_DB" for db in listed["databases"])

    update = admin_client.put(
        "/api/admin/databases/ADMIN_DB",
        json={"host": "admin-host-2"},
    )
    assert update.status_code == 200
    assert update.json()["host"] == "admin-host-2"

    delete = admin_client.delete("/api/admin/databases/ADMIN_DB")
    assert delete.status_code == 200
    assert admin_client.get("/api/admin/connections").json()["databases"] == []


def test_non_admin_cannot_manage_shared_aliases(auth_client: TestClient):
    bob_client = TestClient(auth_client.app)
    login_as(bob_client, "bob", create=True)

    assert bob_client.get("/api/admin/connections").status_code == 403
    assert bob_client.post(
        "/api/admin/databases",
        json={
            "alias": "HACK",
            "driver": "postgresql",
            "host": "x",
            "port": 5432,
            "database": "d",
            "user": "u",
            "password": "p",
        },
    ).status_code == 403


def test_shared_connections_in_backup(auth_client: TestClient):
    import io
    import zipfile

    _seed_shared_db("BACKUP_DB")

    _login_admin(auth_client)
    response = auth_client.get("/api/admin/backup")
    assert response.status_code == 200

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert any(name.endswith("shared_connections.json") for name in names)
