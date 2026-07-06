"""Tests for DTD schema registry lazy initialization."""

from pathlib import Path

import pytest

from app.api.routes import dtd as dtd_routes
from app.user_context import UserContext

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def dtd_user(tmp_path: Path) -> UserContext:
    root = tmp_path / "dtd-user"
    root.mkdir(parents=True, exist_ok=True)
    ctx = UserContext(user_id="dtd-test", display_name="dtd", root=root)
    ctx.dtd_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def test_ensure_user_registry_loaded_loads_saved_dtd(dtd_user: UserContext):
    dtd_user.dtd_dir.joinpath("main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())

    loaded = dtd_routes.ensure_user_registry_loaded(dtd_user)

    assert loaded == 1
    registry = dtd_routes._user_registry(dtd_user)
    assert len(registry) == 1

    main_schema = next(s for s in registry.values() if "PayDoc" in s.elements)
    assert "PayDoc" in main_schema.root_elements()


def test_ensure_user_registry_preserves_schema_id(dtd_user: UserContext):
    dtd_user.dtd_dir.joinpath("main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())

    dtd_routes.ensure_user_registry_loaded(dtd_user)
    schema_ids = set(dtd_routes._user_registry(dtd_user))

    dtd_routes._schema_registry.clear()
    dtd_routes.ensure_user_registry_loaded(dtd_user)

    assert set(dtd_routes._user_registry(dtd_user)) == schema_ids


def test_ensure_user_registry_empty_dir(dtd_user: UserContext):
    assert dtd_routes.ensure_user_registry_loaded(dtd_user) == 0


def test_ensure_user_registry_loaded_loads_all_entry_points(dtd_user: UserContext):
    dtd_user.dtd_dir.joinpath("main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("old-schema.dtd").write_text(
        "<!ELEMENT Legacy EMPTY>", encoding="utf-8"
    )

    loaded = dtd_routes.ensure_user_registry_loaded(dtd_user)

    assert loaded == 2
    registry = dtd_routes._user_registry(dtd_user)
    assert len(registry) == 2
    assert any("PayDoc" in schema.elements for schema in registry.values())
    assert any("Legacy" in schema.elements for schema in registry.values())


def test_ensure_user_registry_removes_unreferenced_files(dtd_user: UserContext):
    dtd_user.dtd_dir.joinpath("main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("stale-module.ent").write_text(
        "<!ENTITY % Boolean \"(true|false)\">", encoding="utf-8"
    )

    dtd_routes.ensure_user_registry_loaded(dtd_user)

    assert not (dtd_user.dtd_dir / "stale-module.ent").exists()
    assert (dtd_user.dtd_dir / "main.dtd").exists()
    assert (dtd_user.dtd_dir / "types.dtd").exists()


def test_cleanup_schema_storage_on_upload(dtd_user: UserContext):
    dtd_user.dtd_dir.joinpath("types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())
    dtd_user.dtd_dir.joinpath("old-schema.dtd").write_text(
        "<!ELEMENT Legacy EMPTY>", encoding="utf-8"
    )
    dtd_user.dtd_dir.joinpath("old-schema.dtd.schema_id").write_text("stale-id", encoding="utf-8")

    main_path = dtd_user.dtd_dir / "main.dtd"
    main_path.write_bytes((FIXTURES / "main.dtd").read_bytes())

    schema_id = dtd_routes._parse_and_register(dtd_user, main_path)
    schema = dtd_routes._user_registry(dtd_user)[schema_id]
    dtd_routes._cleanup_schema_storage(
        dtd_user,
        keep_basenames=dtd_routes._source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    assert not (dtd_user.dtd_dir / "old-schema.dtd").exists()
    assert not (dtd_user.dtd_dir / "old-schema.dtd.schema_id").exists()
    assert (dtd_user.dtd_dir / "main.dtd").exists()
    assert (dtd_user.dtd_dir / "types.dtd").exists()
    assert len(dtd_routes._user_registry(dtd_user)) == 1
