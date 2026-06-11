"""Tests for Oracle thick mode initialization."""

from __future__ import annotations

import os
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


def test_derive_oracle_home_from_instant_client_directory():
    path = r"C:\oracle\instantclient_21_3"
    assert oracle_client.derive_oracle_home(path) == path


def test_ensure_oracle_thick_mode_sets_oracle_home_and_initializes():
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(oracledb, "is_thin_mode", return_value=True):
            with patch.object(oracledb, "init_oracle_client") as init_client:
                with patch(
                    "app.services.oracle_client.get_oracle_thick_mode_settings",
                    return_value=(True, r"C:\oracle\client_1\bin"),
                ):
                    oracle_client.ensure_oracle_thick_mode()
                    assert os.environ["ORACLE_HOME"] == r"C:\oracle\client_1"
                    init_client.assert_called_once_with(lib_dir=r"C:\oracle\client_1\bin")


def test_ensure_oracle_thick_mode_skips_when_not_configured():
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch.object(oracledb, "init_oracle_client") as init_client:
            with patch(
                "app.services.oracle_client.get_oracle_thick_mode_settings",
                return_value=(False, None),
            ):
                oracle_client.ensure_oracle_thick_mode()
                init_client.assert_not_called()


def test_map_oracle_client_error_maps_dpy_3010():
    exc = MagicMock()
    exc.__str__ = lambda self: "DPY-3010: connections to this database server version are not supported"
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        mapped = oracle_client.map_oracle_client_error(exc)
    assert mapped is not None
    assert "thick mode" in str(mapped)


def test_map_oracle_client_error_maps_ora_01804():
    exc = MagicMock()
    exc.__str__ = lambda self: "ORA-01804: failure to initialize timezone information"
    mapped = oracle_client.map_oracle_client_error(exc)
    assert mapped is not None
    assert "ORA-01804" in str(mapped)
    assert "ORACLE_HOME" in str(mapped)


def test_map_oracle_client_error_ignores_other_errors():
    exc = MagicMock()
    exc.__str__ = lambda self: "ORA-12154: TNS:could not resolve the connect identifier"
    assert oracle_client.map_oracle_client_error(exc) is None
