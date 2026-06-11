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


def test_resolve_ora_tzfile_returns_none_when_unset(tmp_path: Path):
    assert oracle_client.resolve_ora_tzfile(tmp_path, None) is None


def test_resolve_ora_tzfile_finds_file_in_zoneinfo(tmp_path: Path):
    zoneinfo = tmp_path / "oracore" / "zoneinfo"
    zoneinfo.mkdir(parents=True)
    tz_file = zoneinfo / "timezlrg_1.dat"
    tz_file.write_bytes(b"tz")

    resolved = oracle_client.resolve_ora_tzfile(tmp_path, "timezlrg_1.dat")
    assert resolved == str(tz_file)


def test_resolve_ora_tzfile_raises_when_file_missing(tmp_path: Path):
    zoneinfo = tmp_path / "oracore" / "zoneinfo"
    zoneinfo.mkdir(parents=True)
    (zoneinfo / "timezlrg_32.dat").write_bytes(b"tz")

    with pytest.raises(ValueError, match="timezlrg_1.dat"):
        oracle_client.resolve_ora_tzfile(tmp_path, "timezlrg_1.dat")


def test_apply_oracle_environment_unsets_missing_ora_tzfile(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "client" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")

    monkeypatch.setenv("ORA_TZFILE", "")

    oracle_client._apply_oracle_environment(str(bin_dir))

    assert os.environ["ORACLE_HOME"] == str(tmp_path / "client")
    assert "ORA_TZFILE" not in os.environ


def test_apply_oracle_environment_sets_absolute_ora_tzfile(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "client" / "bin"
    zoneinfo = tmp_path / "client" / "oracore" / "zoneinfo"
    zoneinfo.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    (bin_dir / "oci.dll").write_bytes(b"oci")
    tz_file = zoneinfo / "timezlrg_1.dat"
    tz_file.write_bytes(b"tz")

    monkeypatch.setenv("ORA_TZFILE", "timezlrg_1.dat")

    oracle_client._apply_oracle_environment(str(bin_dir))

    assert os.environ["ORA_TZFILE"] == str(tz_file)


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


def test_map_oracle_client_error_maps_ora_01804(tmp_path: Path, monkeypatch):
    zoneinfo = tmp_path / "oracore" / "zoneinfo"
    zoneinfo.mkdir(parents=True)
    (zoneinfo / "timezlrg_32.dat").write_bytes(b"tz")

    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("ORA_TZFILE", "timezlrg_1.dat")

    exc = MagicMock()
    exc.__str__ = lambda self: "ORA-01804: failure to initialize timezone information"
    mapped = oracle_client.map_oracle_client_error(exc)

    assert mapped is not None
    assert "timezlrg_32.dat" in str(mapped)
    assert "Try removing ORA_TZFILE" in str(mapped)
