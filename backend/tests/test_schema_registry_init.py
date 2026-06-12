"""Tests for DTD schema registry startup initialization."""

from pathlib import Path

import pytest

from app.api.routes import dtd as dtd_routes

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dtd_routes, "DTD_SCHEMA_DIR", tmp_path)
    dtd_routes._schema_registry.clear()
    yield tmp_path
    dtd_routes._schema_registry.clear()


def test_initialize_schema_registry_loads_saved_dtd(schema_dir: Path):
    (schema_dir / "main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    (schema_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())

    loaded = dtd_routes.initialize_schema_registry()

    assert loaded == 1
    assert len(dtd_routes._schema_registry) == 1

    main_schema = next(
        s for s in dtd_routes._schema_registry.values() if "PayDoc" in s.elements
    )
    assert "PayDoc" in main_schema.root_elements()


def test_initialize_schema_registry_preserves_schema_id(schema_dir: Path):
    (schema_dir / "main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    (schema_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())

    dtd_routes.initialize_schema_registry()
    schema_ids = set(dtd_routes._schema_registry)

    dtd_routes._schema_registry.clear()
    dtd_routes.initialize_schema_registry()

    assert set(dtd_routes._schema_registry) == schema_ids


def test_initialize_schema_registry_empty_dir(schema_dir: Path):
    assert dtd_routes.initialize_schema_registry() == 0


def test_initialize_schema_registry_removes_stale_entry_points(schema_dir: Path):
    (schema_dir / "main.dtd").write_bytes((FIXTURES / "main.dtd").read_bytes())
    (schema_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())
    (schema_dir / "old-schema.dtd").write_text("<!ELEMENT Legacy EMPTY>", encoding="utf-8")
    (schema_dir / "old-schema.dtd.schema_id").write_text("stale-id", encoding="utf-8")

    dtd_routes.initialize_schema_registry()

    assert not (schema_dir / "old-schema.dtd").exists()
    assert not (schema_dir / "old-schema.dtd.schema_id").exists()
    assert (schema_dir / "main.dtd").exists()
    assert (schema_dir / "types.dtd").exists()


def test_cleanup_schema_storage_on_upload(schema_dir: Path):
    (schema_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())
    (schema_dir / "old-schema.dtd").write_text("<!ELEMENT Legacy EMPTY>", encoding="utf-8")
    (schema_dir / "old-schema.dtd.schema_id").write_text("stale-id", encoding="utf-8")

    main_path = schema_dir / "main.dtd"
    main_path.write_bytes((FIXTURES / "main.dtd").read_bytes())

    schema_id = dtd_routes._parse_and_register(main_path)
    schema = dtd_routes._schema_registry[schema_id]
    dtd_routes._cleanup_schema_storage(
        keep_basenames=dtd_routes._source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    assert not (schema_dir / "old-schema.dtd").exists()
    assert not (schema_dir / "old-schema.dtd.schema_id").exists()
    assert (schema_dir / "main.dtd").exists()
    assert (schema_dir / "types.dtd").exists()
    assert len(dtd_routes._schema_registry) == 1
