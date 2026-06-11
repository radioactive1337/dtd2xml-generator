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


def test_derive_oracle_home_from_bin_directory():
    assert oracle_client.derive_oracle_home(r"C:\oracle\client_1\bin") == r"C:\oracle\client_1"


def test_resolve_client_lib_dir_accepts_bin_directory(tmp_path: Path):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    assert oracle_client.resolve_client_lib_dir(str(bin_dir)) == str(bin_dir)


def test_resolve_client_lib_dir_accepts_client_root_with_bin(tmp_path: Path):
    client_root = tmp_path / "client"
    bin_dir = client_root / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    assert oracle_client.resolve_client_lib_dir(str(client_root)) == str(bin_dir)


def test_resolve_ora_tzfile_returns_none_when_unset(tmp_path: Path):
    assert oracle_client.resolve_ora_tzfile(tmp_path, None) is None


def test_apply_oracle_environment_unsets_missing_ora_tzfile(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")
    monkeypatch.delenv("ORA_TZFILE", raising=False)

    resolved = oracle_client._apply_oracle_environment(str(bin_dir))

    assert resolved == str(bin_dir)
    assert os.environ["ORACLE_HOME"] == str(tmp_path / "client")
    assert "ORA_TZFILE" not in os.environ


def test_ensure_oracle_thick_mode_raises_when_lib_dir_missing():
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch(
            "app.services.oracle_client.get_oracle_thick_mode_settings",
            return_value=(True, None),
        ):
            with pytest.raises(ValueError, match="ORACLE_CLIENT_LIB_DIR is not set"):
                oracle_client.ensure_oracle_thick_mode()


def test_ensure_oracle_thick_mode_initializes_client(tmp_path: Path):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch.object(oracledb, "init_oracle_client") as init_client:
            with patch(
                "app.services.oracle_client.get_oracle_thick_mode_settings",
                return_value=(True, str(bin_dir)),
            ):
                oracle_client.ensure_oracle_thick_mode()
                init_client.assert_called_once_with(lib_dir=str(bin_dir))


def test_map_oracle_client_error_maps_configured_dpy_3010():
    exc = MagicMock()
    exc.__str__ = lambda self: "DPY-3010: connections to this database server version are not supported"
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch(
            "app.services.oracle_client.get_oracle_thick_mode_settings",
            return_value=(True, r"C:\Oracle\client19_64\bin"),
        ):
            mapped = oracle_client.map_oracle_client_error(exc)

    assert mapped is not None
    assert "still running in thin mode" in str(mapped)
    assert r"C:\Oracle\client19_64\bin" in str(mapped)
