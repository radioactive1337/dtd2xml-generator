"""Tests for JAR DTD upload flow."""

import io
import zipfile
from pathlib import Path

import pytest

from app.api.routes import dtd as dtd_routes
from app.core.dtd_archive import extract_jar_dtd_files

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def clear_registry():
    dtd_routes._schema_registry.clear()
    yield
    dtd_routes._schema_registry.clear()


@pytest.fixture
def schema_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dtd_routes, "DTD_SCHEMA_DIR", tmp_path)
    yield tmp_path


def _build_jar(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _upload_jar_from_bytes(
    jar_bytes: bytes,
    *,
    inner_path: str = "META-INF/dtd/",
    entry_file: str = "v2.dtd",
) -> dtd_routes.SchemaResponse:
    entry_basename = Path(entry_file).name
    extracted = extract_jar_dtd_files(jar_bytes, dtd_routes.DTD_SCHEMA_DIR, prefix=inner_path)

    if entry_basename not in extracted:
        raise LookupError(
            f"entry_file '{entry_basename}' not found in {inner_path}"
        )

    entry_path = extracted[entry_basename]
    dtd_routes._validate_dtd_references(entry_path, set(extracted))

    schema_id = dtd_routes._parse_and_register(
        entry_path,
        schema_id=dtd_routes._read_schema_id(entry_path),
    )
    schema = dtd_routes._schema_registry[schema_id]
    dtd_routes._cleanup_schema_storage(
        keep_basenames=dtd_routes._source_basenames(schema),
        keep_schema_ids={schema_id},
    )

    return dtd_routes.SchemaResponse(
        schema_id=schema_id,
        source_files=schema.source_files,
        element_count=len(schema.elements),
        elements=schema.root_elements(),
    )


def test_upload_jar_parses_entry_and_cleans_stale_files(schema_dir: Path):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
            "META-INF/dtd/v1.dtd": (FIXTURES / "v1.dtd").read_bytes(),
            "META-INF/dtd/types.dtd": (FIXTURES / "types.dtd").read_bytes(),
        }
    )

    result = _upload_jar_from_bytes(jar_bytes, entry_file="v2.dtd")

    assert result.element_count > 0
    assert "PayDoc" in result.elements

    source_basenames = {Path(path).name for path in result.source_files}
    assert source_basenames == {"v2.dtd", "types.dtd"}

    assert (schema_dir / "v2.dtd").is_file()
    assert (schema_dir / "types.dtd").is_file()
    assert not (schema_dir / "v1.dtd").exists()


def test_upload_jar_entry_file_not_found(schema_dir: Path):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v1.dtd": (FIXTURES / "v1.dtd").read_bytes(),
        }
    )

    with pytest.raises(LookupError, match="entry_file 'v2.dtd' not found"):
        _upload_jar_from_bytes(jar_bytes, entry_file="v2.dtd")


def test_upload_jar_missing_referenced_file(schema_dir: Path):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
        }
    )

    with pytest.raises(ValueError, match="types.dtd"):
        _upload_jar_from_bytes(jar_bytes, entry_file="v2.dtd")
