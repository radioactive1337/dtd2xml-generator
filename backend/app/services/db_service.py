"""Database query service for hybrid XML data population."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg
import oracledb
from pydantic import BaseModel

from app.config import DatabaseConfig, get_db_password, load_connections
from app.core.dtd_models import DTDSchema
from app.core.logging_config import truncate
from app.services.oracle_client import ensure_oracle_thick_mode, map_oracle_client_error
from app.services.sql_safety import prepare_safe_query
from lxml import etree

from app.core.xml_tree import ProtectedAttrs, element_path

logger = logging.getLogger(__name__)


class SqlMapping(BaseModel):
    """Declarative mapping from a SQL query result to XML element attributes."""

    query: str
    target_element: str
    fields: dict[str, str]  # db_column -> xml_attribute (optionally prefixed with @)
    db_alias: str | None = None


def _normalize_value(value: Any) -> Any:
    if hasattr(value, "read"):
        return value.read()
    return value


def _rows_to_dicts(columns: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    normalized_columns = [col.lower() for col in columns]
    return [
        {
            col: _normalize_value(val)
            for col, val in zip(normalized_columns, row, strict=True)
        }
        for row in rows
    ]


def _oracle_dsn(cfg: DatabaseConfig) -> str:
    if cfg.sid:
        return oracledb.makedsn(cfg.host, cfg.port, sid=cfg.sid)
    return oracledb.makedsn(cfg.host, cfg.port, service_name=cfg.database)


def _oracle_columns_sync(
    user: str,
    password: str,
    dsn: str,
    sql: str,
) -> list[str]:
    ensure_oracle_thick_mode(required=True)
    if oracledb.is_thin_mode():
        raise RuntimeError(
            "Oracle thick mode is required but the driver is still in thin mode."
        )

    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description is None:
                return []
            return [col[0].lower() for col in cursor.description]
    finally:
        conn.close()


def _oracle_query_sync(
    user: str,
    password: str,
    dsn: str,
    sql: str,
) -> list[dict[str, Any]]:
    """Run Oracle SQL via synchronous thick-mode connection.

    ``connect_async`` can still attempt thin mode on some Windows setups even after
    ``init_oracle_client()``, so thick mode queries use the sync driver in a worker
    thread instead.
    """
    ensure_oracle_thick_mode(required=True)
    if oracledb.is_thin_mode():
        raise RuntimeError(
            "Oracle thick mode is required but the driver is still in thin mode."
        )

    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with conn.cursor() as cursor:
            cursor.arraysize = 1
            cursor.prefetchrows = 1
            cursor.execute(sql)
            if cursor.description is None:
                return []
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            if row is None:
                return []
            return _rows_to_dicts(columns, [row])
    finally:
        conn.close()


class DBService:
    """Execute SQL queries against configured database aliases."""

    async def run_query(self, alias: str, sql: str) -> list[dict[str, Any]]:
        connections = load_connections()
        if alias not in connections.databases:
            logger.error("Unknown database alias: %s", alias)
            raise ValueError(f"Database alias '{alias}' not found in connections.json")

        cfg = connections.databases[alias]
        password = get_db_password(alias)
        driver = cfg.driver.lower()
        safe_sql = prepare_safe_query(sql, driver, limit_rows=True)

        try:
            if driver == "postgresql":
                return await self._query_postgresql(cfg, password, safe_sql)
            if driver in {"oracle", "oracledb"}:
                return await self._query_oracle(cfg, password, safe_sql)
        except Exception:
            logger.exception(
                "SQL query failed [alias=%s driver=%s host=%s:%s db=%s query=%s safe_query=%s]",
                alias,
                driver,
                cfg.host,
                cfg.port,
                cfg.database or cfg.sid,
                truncate(sql),
                truncate(safe_sql),
            )
            raise

        logger.error("Unsupported database driver [alias=%s driver=%s]", alias, cfg.driver)
        raise ValueError(f"Unsupported database driver: {cfg.driver}")

    async def get_query_columns(self, alias: str, sql: str) -> list[str]:
        connections = load_connections()
        if alias not in connections.databases:
            logger.error("Unknown database alias: %s", alias)
            raise ValueError(f"Database alias '{alias}' not found in connections.json")

        cfg = connections.databases[alias]
        password = get_db_password(alias)
        driver = cfg.driver.lower()
        safe_sql = prepare_safe_query(sql, driver, limit_rows=False)

        try:
            if driver == "postgresql":
                return await self._query_columns_postgresql(cfg, password, safe_sql)
            if driver in {"oracle", "oracledb"}:
                return await self._query_columns_oracle(cfg, password, safe_sql)
        except Exception:
            logger.exception(
                "SQL column introspection failed [alias=%s driver=%s host=%s:%s query=%s]",
                alias,
                driver,
                cfg.host,
                cfg.port,
                truncate(sql),
            )
            raise

        logger.error("Unsupported database driver [alias=%s driver=%s]", alias, cfg.driver)
        raise ValueError(f"Unsupported database driver: {cfg.driver}")

    async def _query_columns_postgresql(
        self,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[str]:
        conn = await asyncpg.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=password,
            database=cfg.database,
        )
        try:
            await conn.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
            )
            prepared = await conn.prepare(sql)
            return [attr.name.lower() for attr in prepared.get_attributes()]
        finally:
            await conn.close()

    async def _query_columns_oracle(
        self,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[str]:
        try:
            return await asyncio.to_thread(
                _oracle_columns_sync,
                cfg.user,
                password,
                _oracle_dsn(cfg),
                sql,
            )
        except oracledb.Error as exc:
            mapped = map_oracle_client_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise

    async def _query_postgresql(
        self,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[dict[str, Any]]:
        conn = await asyncpg.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=password,
            database=cfg.database,
        )
        try:
            await conn.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
            )
            row = await conn.fetchrow(sql)
            if row is None:
                return []
            return [{k.lower(): v for k, v in dict(row).items()}]
        finally:
            await conn.close()

    async def _query_oracle(
        self,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[dict[str, Any]]:
        try:
            return await asyncio.to_thread(
                _oracle_query_sync,
                cfg.user,
                password,
                _oracle_dsn(cfg),
                sql,
            )
        except oracledb.Error as exc:
            mapped = map_oracle_client_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise

    async def populate_xml(
        self,
        xml_text: str,
        schema: DTDSchema,
        alias: str,
        sql: str,
    ) -> str:
        rows = await self.run_query(alias, sql)
        if not rows:
            raise ValueError("SQL query returned no rows")

        row = rows[0]
        root = etree.fromstring(xml_text.encode("utf-8"))
        self._apply_row_to_element(root, row, schema)
        return etree.tostring(
            root,
            pretty_print=True,
            encoding="UTF-8",
            xml_declaration=False,
        ).decode("UTF-8")

    def _apply_row_to_element(
        self,
        el: etree._Element,
        row: dict[str, Any],
        schema: DTDSchema,
    ) -> None:
        elem_def = schema.elements.get(el.tag)
        lower_row = {k.lower(): v for k, v in row.items()}

        for attr_name in list(el.attrib.keys()):
            value = self._find_value(attr_name, lower_row)
            if value is not None:
                el.set(attr_name, str(value))

        if elem_def and elem_def.content_model.kind == "PCDATA":
            for key, value in lower_row.items():
                if key == el.tag.lower() or key in (el.tag.lower(),):
                    el.text = str(value)
                    break
            else:
                if lower_row:
                    el.text = str(next(iter(lower_row.values())))

        for child in el:
            self._apply_row_to_element(child, row, schema)

    def _find_value(self, name: str, row: dict[str, Any]) -> Any:
        if name in row:
            return row[name]
        lower = name.lower()
        if lower in row:
            return row[lower]
        for key, value in row.items():
            if key.lower() == lower:
                return value
        return None

    async def apply_overrides(
        self,
        xml_text: str,
        sql_mappings: list[SqlMapping],
    ) -> tuple[str, ProtectedAttrs]:
        """Stage-1 pipeline: inject DB values into specific elements by tag name.

        For every mapping, the first row of the SQL result is fetched once and its
        columns are written to the declared XML attributes of every matching element
        in the tree.  Returns the updated XML and the set of DB-filled attribute
        slots that Stage 2 must preserve.
        """
        root = etree.fromstring(xml_text.encode("utf-8"))
        protected: set[tuple[tuple[str, int], ...], str] = set()

        for mapping in sql_mappings:
            if not mapping.query.strip() or not mapping.target_element:
                continue

            if not mapping.db_alias:
                continue

            try:
                rows = await self.run_query(mapping.db_alias, mapping.query)
            except Exception:
                logger.exception(
                    "DB override mapping failed [alias=%s element=%s fields=%s query=%s]",
                    mapping.db_alias,
                    mapping.target_element,
                    list(mapping.fields.keys()),
                    truncate(mapping.query),
                )
                raise
            if not rows:
                logger.warning(
                    "DB override returned no rows [alias=%s element=%s query=%s]",
                    mapping.db_alias,
                    mapping.target_element,
                    truncate(mapping.query),
                )
                continue

            row = rows[0]
            lower_row: dict[str, str] = {
                k.lower(): str(v) for k, v in row.items() if v is not None
            }

            for el in root.iter(mapping.target_element):
                for db_col, xml_attr in mapping.fields.items():
                    value = lower_row.get(db_col.lower())
                    if value is None:
                        continue
                    # Accept both "inn" and "@inn" as XML attribute name notation.
                    attr_name = xml_attr.lstrip("@")
                    if attr_name:
                        el.set(attr_name, value)
                        protected.add((element_path(el), attr_name))

        xml_out = etree.tostring(
            root,
            pretty_print=True,
            encoding="UTF-8",
            xml_declaration=False,
        ).decode("UTF-8")
        return xml_out, frozenset(protected)


async def populate_with_db(
    xml_text: str,
    schema: DTDSchema,
    alias: str,
    sql: str,
) -> str:
    """Populate XML by mapping the first SQL result row onto matching nodes."""
    return await DBService().populate_xml(xml_text, schema, alias, sql)


async def apply_db_overrides(
    xml_text: str,
    sql_mappings: list[SqlMapping],
) -> tuple[str, ProtectedAttrs]:
    """Stage-1 of the hybrid pipeline: targeted DB injections before faker/LLM fallback."""
    return await DBService().apply_overrides(xml_text, sql_mappings)
