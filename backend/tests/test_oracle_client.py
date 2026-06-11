"""Tests for Oracle thick mode initialization."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest

from app.services import oracle_client


@pytest.fixture(autouse=True)
def reset_oracle_client_state():
    oracle_client._client_initialized = False
    oracle_client._init_lib_dir = None
    yield
    oracle_client._client_initialized = False
    oracle_client._init_lib_dir = None


def test_resolve_client_lib_dir_accepts_bin_directory(tmp_path: Path):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    assert oracle_client.resolve_client_lib_dir(str(bin_dir)) == str(bin_dir)


def test_prepare_windows_dll_path_updates_path(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", "C:\\Windows\\System32")

    with patch.object(os, "add_dll_directory") as add_dll_directory:
        oracle_client._prepare_windows_dll_path(str(bin_dir))
        add_dll_directory.assert_called_once_with(str(bin_dir))
        assert str(bin_dir) in os.environ["PATH"]


def test_apply_oracle_environment_unsets_missing_ora_tzfile(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")
    monkeypatch.delenv("ORA_TZFILE", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

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
            with patch("app.services.oracle_client.get_oracle_client_lib_dir", return_value=str(bin_dir)):
                with patch("app.services.oracle_client._prepare_windows_dll_path"):
                    oracle_client.ensure_oracle_thick_mode(required=True)
                    init_client.assert_called_once_with(lib_dir=str(bin_dir))


def test_map_oracle_client_error_includes_runtime_status():
    exc = MagicMock()
    exc.__str__ = lambda self: "DPY-3010: connections to this database server version are not supported"
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch(
            "app.services.oracle_client.get_oracle_env_diagnostics",
            return_value={"oracle_client_lib_dir": r"C:\Oracle\client19_64\bin"},
        ):
            mapped = oracle_client.map_oracle_client_error(exc)

    assert mapped is not None
    assert "thin mode" in str(mapped)
    assert "/api/health/oracle" in str(mapped)
