"""Tests for Oracle thick mode initialization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import oracledb
import pytest

from app.services import oracle_client


@pytest.fixture(autouse=True)
def reset_oracle_client_state():
    oracle_client._client_initialized = False
    yield
    oracle_client._client_initialized = False


def test_ensure_oracle_thick_mode_initializes_with_lib_dir():
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch.object(oracledb, "init_oracle_client") as init_client:
            with patch(
                "app.services.oracle_client.get_oracle_thick_mode_settings",
                return_value=(True, r"C:\oracle\instantclient_19_22"),
            ):
                oracle_client.ensure_oracle_thick_mode()
                init_client.assert_called_once_with(lib_dir=r"C:\oracle\instantclient_19_22")


def test_ensure_oracle_thick_mode_skips_when_not_configured():
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        with patch.object(oracledb, "init_oracle_client") as init_client:
            with patch(
                "app.services.oracle_client.get_oracle_thick_mode_settings",
                return_value=(False, None),
            ):
                oracle_client.ensure_oracle_thick_mode()
                init_client.assert_not_called()


def test_oracle_thick_mode_error_maps_dpy_3010():
    exc = MagicMock()
    exc.__str__ = lambda self: "DPY-3010: connections to this database server version are not supported"
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        mapped = oracle_client.oracle_thick_mode_error(exc)
    assert mapped is not None
    assert "thick mode" in str(mapped)


def test_oracle_thick_mode_error_ignores_other_errors():
    exc = MagicMock()
    exc.__str__ = lambda self: "ORA-12154: TNS:could not resolve the connect identifier"
    with patch.object(oracledb, "is_thin_mode", return_value=True):
        assert oracle_client.oracle_thick_mode_error(exc) is None
