"""Tests for Oracle thick mode initialization."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest

from app.services import oracle_client


@pytest.fixture(autouse=True)
def reset_oracle_client_state():
    oracle_client._client_initialized = False
    yield
    oracle_client._client_initialized = False


def test_resolve_client_lib_dir_accepts_bin_directory(tmp_path: Path):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    assert oracle_client.resolve_client_lib_dir(str(bin_dir)) == str(bin_dir)


def test_apply_oracle_environment_unsets_missing_ora_tzfile(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")
    monkeypatch.delenv("ORA_TZFILE", raising=False)

    resolved = oracle_client._apply_oracle_environment(str(bin_dir))

    assert resolved == str(bin_dir)
    assert os.environ["ORACLE_HOME"] == str(tmp_path / "client")
    assert "ORA_TZFILE" not in os.environ


def test_ensure_oracle_thick_mode_required_raises_when_lib_dir_missing():
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch("app.services.oracle_client.get_oracle_client_lib_dir", return_value=None):
            with pytest.raises(ValueError, match="Oracle thick mode is required"):
                oracle_client.ensure_oracle_thick_mode(required=True)


def test_ensure_oracle_thick_mode_initializes_client(tmp_path: Path):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    thin_mode = iter([True, True, False])

    with patch.object(oracledb, "is_thin_mode", side_effect=lambda: next(thin_mode)):
        with patch.object(oracledb, "init_oracle_client") as init_client:
            with patch(
                "app.services.oracle_client.get_oracle_client_lib_dir",
                return_value=str(bin_dir),
            ):
                oracle_client.ensure_oracle_thick_mode(required=True)
                init_client.assert_called_once_with(lib_dir=str(bin_dir))


def test_map_oracle_client_error_includes_diagnostics():
    exc = MagicMock()
    exc.__str__ = lambda self: "DPY-3010: connections to this database server version are not supported"
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch(
            "app.services.oracle_client.get_oracle_env_diagnostics",
            return_value={"oracle_client_lib_dir": None},
        ):
            mapped = oracle_client.map_oracle_client_error(exc)

    assert mapped is not None
    assert "thin mode" in str(mapped)
    assert "Diagnostics" in str(mapped)
