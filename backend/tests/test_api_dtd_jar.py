"""Tests for JAR DTD upload flow."""

import io
import zipfile
from pathlib import Path

import pytest

from app.api.routes import dtd as dtd_routes
from app.core.dtd_archive import extract_jar_dtd_files
from app.user_context import UserContext

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def dtd_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UserContext:
    root = tmp_path / "jar-user"
    root.mkdir(parents=True, exist_ok=True)
    dtd_dir = root / "dtd_schemas"
    dtd_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dtd_routes, "_dtd_dir", lambda: dtd_dir)
    migration_flag = tmp_path / ".dtd_shared_migrated"
    migration_flag.write_text("test\n", encoding="utf-8")
    monkeypatch.setattr(dtd_routes, "_migration_flag_path", lambda: migration_flag)
    return UserContext(user_id="jar-test", display_name="jar", root=root)


def _shared_dir(dtd_user: UserContext) -> Path:
    return dtd_user.root / "dtd_schemas"


def _build_jar(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _upload_jar_from_bytes(
    dtd_user: UserContext,
    jar_bytes: bytes,
    *,
    inner_path: str = "META-INF/dtd/",
) -> dtd_routes.MultiSchemaResponse:
    shared = _shared_dir(dtd_user)
    extracted = extract_jar_dtd_files(jar_bytes, shared, prefix=inner_path)
    entry_points = dtd_routes._entry_point_paths(shared)
    if not entry_points:
        raise LookupError(f"No .dtd entry points found in {inner_path}")

    schema_ids = dtd_routes._parse_entry_points(
        entry_points,
        available_basenames=set(extracted),
    )
    return dtd_routes._multi_schema_response(schema_ids)


def test_upload_jar_parses_all_entry_points_and_cleans_stale_files(dtd_user: UserContext):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
            "META-INF/dtd/v1.dtd": (FIXTURES / "v1.dtd").read_bytes(),
            "META-INF/dtd/types.dtd": (FIXTURES / "types.dtd").read_bytes(),
        }
    )

    result = _upload_jar_from_bytes(dtd_user, jar_bytes)

    assert len(result.schemas) == 2
    assert result.primary_schema_id

    by_source = {
        Path(schema.source_files[0]).name: schema for schema in result.schemas
    }
    assert by_source["v2.dtd"].element_count > 0
    assert "PayDoc" in by_source["v2.dtd"].elements
    assert by_source["v1.dtd"].elements == ["Legacy"]

    source_basenames = {
        Path(path).name
        for schema in result.schemas
        for path in schema.source_files
    }
    assert source_basenames == {"v1.dtd", "v2.dtd", "types.dtd"}

    shared = _shared_dir(dtd_user)
    assert (shared / "v2.dtd").is_file()
    assert (shared / "v1.dtd").is_file()
    assert (shared / "types.dtd").is_file()


def test_upload_jar_no_entry_points(dtd_user: UserContext):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/types.ent": b"<!ENTITY % Boolean \"(true|false)\">",
        }
    )

    with pytest.raises(LookupError, match="No .dtd entry points found"):
        _upload_jar_from_bytes(dtd_user, jar_bytes)


def test_upload_jar_missing_referenced_file(dtd_user: UserContext):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
        }
    )

    with pytest.raises(ValueError, match="types.dtd"):
        _upload_jar_from_bytes(dtd_user, jar_bytes)
