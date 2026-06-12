"""Tests for database query service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import ConnectionsConfig, DatabaseConfig
from app.services.db_service import DBService, _oracle_dsn


def _oracle_cfg(**overrides) -> DatabaseConfig:
    defaults = {
        "alias": "ORACLE_DB",
        "driver": "oracle",
        "host": "db.example.com",
        "port": 1521,
        "database": "ORCLPDB1",
        "user": "app_user",
    }
    defaults.update(overrides)
    return DatabaseConfig(**defaults)


@pytest.mark.asyncio
async def test_run_query_rejects_unknown_driver():
    cfg = _oracle_cfg(driver="mysql")
    connections = ConnectionsConfig(databases={"ORACLE_DB": cfg})

    with patch("app.services.db_service.load_connections", return_value=connections):
        with pytest.raises(ValueError, match="Unsupported database driver: mysql"):
            await DBService().run_query("ORACLE_DB", "SELECT 1 FROM dual")


@pytest.mark.asyncio
async def test_run_query_oracle_returns_normalized_rows():
    cfg = _oracle_cfg()
    connections = ConnectionsConfig(databases={"ORACLE_DB": cfg})
    expected = [{"inn": "7701234567", "name": "Acme"}]

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("app.services.db_service.load_connections", return_value=connections):
        with patch("app.services.db_service.get_db_password", return_value="secret"):
            with patch(
                "app.services.db_service._oracle_query_sync",
                return_value=expected,
            ) as oracle_query:
                with patch(
                    "app.services.db_service.asyncio.to_thread",
                    new=fake_to_thread,
                ):
                    rows = await DBService().run_query(
                        "ORACLE_DB",
                        "SELECT inn, name FROM company WHERE rownum = 1",
                    )

    oracle_query.assert_called_once()
    assert rows == expected


@pytest.mark.asyncio
async def test_get_query_columns_oracle_returns_description_columns():
    cfg = _oracle_cfg()
    connections = ConnectionsConfig(databases={"ORACLE_DB": cfg})

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("app.services.db_service.load_connections", return_value=connections):
        with patch("app.services.db_service.get_db_password", return_value="secret"):
            with patch(
                "app.services.db_service._oracle_columns_sync",
                return_value=["inn", "name"],
            ) as oracle_columns:
                with patch(
                    "app.services.db_service.asyncio.to_thread",
                    new=fake_to_thread,
                ):
                    columns = await DBService().get_query_columns(
                        "ORACLE_DB",
                        "SELECT inn, name FROM company WHERE rownum = 1",
                    )

    oracle_columns.assert_called_once()
    assert columns == ["inn", "name"]


def test_oracle_dsn_uses_service_name_by_default():
    dsn = _oracle_dsn(_oracle_cfg())
    assert "ORCLPDB1" in dsn


def test_oracle_dsn_uses_sid_when_configured():
    dsn = _oracle_dsn(_oracle_cfg(database="", sid="ORCL"))
    assert "ORCL" in dsn
