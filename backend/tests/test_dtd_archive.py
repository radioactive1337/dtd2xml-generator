"""Tests for JAR DTD extraction."""

import io
import zipfile
from pathlib import Path

import pytest

from app.core.dtd_archive import extract_jar_dtd_files

FIXTURES = Path(__file__).parent / "fixtures"


def _build_jar(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_extract_jar_dtd_files_flat_by_basename(tmp_path: Path):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
            "META-INF/dtd/types.dtd": (FIXTURES / "types.dtd").read_bytes(),
            "META-INF/dtd/readme.txt": b"ignored",
            "other/v1.dtd": b"<!ELEMENT Other EMPTY>",
        }
    )

    extracted = extract_jar_dtd_files(jar_bytes, tmp_path)

    assert set(extracted) == {"v2.dtd", "types.dtd"}
    assert (tmp_path / "v2.dtd").is_file()
    assert (tmp_path / "types.dtd").is_file()
    assert not (tmp_path / "readme.txt").exists()
    assert not (tmp_path / "v1.dtd").exists()


def test_extract_jar_dtd_files_custom_prefix(tmp_path: Path):
    jar_bytes = _build_jar(
        {
            "schemas/pay/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
            "META-INF/dtd/v1.dtd": (FIXTURES / "v1.dtd").read_bytes(),
        }
    )

    extracted = extract_jar_dtd_files(
        jar_bytes, tmp_path, prefix="schemas/pay/"
    )

    assert set(extracted) == {"v2.dtd"}
    assert (tmp_path / "v2.dtd").is_file()


def test_extract_jar_dtd_files_rejects_zip_slip(tmp_path: Path):
    jar_bytes = _build_jar(
        {
            "META-INF/dtd/../../escape.dtd": b"<!ELEMENT Escape EMPTY>",
        }
    )

    with pytest.raises(ValueError, match="Zip-slip"):
        extract_jar_dtd_files(jar_bytes, tmp_path)
