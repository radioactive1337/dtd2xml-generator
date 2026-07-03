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
def dtd_user(tmp_path: Path) -> UserContext:
    root = tmp_path / "jar-user"
    root.mkdir(parents=True, exist_ok=True)
    ctx = UserContext(user_id="jar-test", display_name="jar", root=root)
    ctx.dtd_dir.mkdir(parents=True, exist_ok=True)
    return ctx


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
    entry_file: str = "v2.dtd",
) -> dtd_routes.SchemaResponse:
    entry_basename = Path(entry_file).name
    extracted = extract_jar_dtd_files(jar_bytes, dtd_user.dtd_dir, prefix=inner_path)

    if entry_basename not in extracted:
        raise LookupError(
            f"entry_file '{entry_basename}' not found in {inner_path}"
        )

    entry_path = extracted[entry_basename]
    dtd_routes._validate_dtd_references(entry_path, set(extracted))

    schema_id = dtd_routes._parse_and_register(
        dtd_user,
        entry_path,
        schema_id=dtd_routes._read_schema_id(entry_path),
    )
    schema = dtd_routes._user_registry(dtd_user)[schema_id]
    dtd_routes._cleanup_schema_storage(
        dtd_user,
        keep_basenames=dtd_routes._source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    return dtd_routes.SchemaResponse(
        schema_id=schema_id,
        source_files=schema.source_files,
        element_count=len(schema.elements),
        elements=schema.root_elements(),
    )


def test_upload_jar_parses_entry_and_cleans_stale_files(dtd_user: UserContext):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
            "META-INF/dtd/v1.dtd": (FIXTURES / "v1.dtd").read_bytes(),
            "META-INF/dtd/types.dtd": (FIXTURES / "types.dtd").read_bytes(),
        }
    )

    result = _upload_jar_from_bytes(dtd_user, jar_bytes, entry_file="v2.dtd")

    assert result.element_count > 0
    assert "PayDoc" in result.elements

    source_basenames = {Path(path).name for path in result.source_files}
    assert source_basenames == {"v2.dtd", "types.dtd"}

    assert (dtd_user.dtd_dir / "v2.dtd").is_file()
    assert (dtd_user.dtd_dir / "types.dtd").is_file()
    assert not (dtd_user.dtd_dir / "v1.dtd").exists()


def test_upload_jar_entry_file_not_found(dtd_user: UserContext):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v1.dtd": (FIXTURES / "v1.dtd").read_bytes(),
        }
    )

    with pytest.raises(LookupError, match="entry_file 'v2.dtd' not found"):
        _upload_jar_from_bytes(dtd_user, jar_bytes, entry_file="v2.dtd")


def test_upload_jar_missing_referenced_file(dtd_user: UserContext):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
        }
    )

    with pytest.raises(ValueError, match="types.dtd"):
        _upload_jar_from_bytes(dtd_user, jar_bytes, entry_file="v2.dtd")
