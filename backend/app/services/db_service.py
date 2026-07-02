"""Database query service for hybrid XML data population."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import asyncpg
import oracledb
from pydantic import BaseModel

from app.config import DatabaseConfig, get_db_password, load_connections
from app.core.dtd_models import DTDSchema
from app.core.logging_config import truncate
from app.services.oracle_client import ensure_oracle_thick_mode, map_oracle_client_error
from app.services.sql_safety import validate_readonly_select
from app.user_context import UserContext
from lxml import etree

from app.core.xml_tree import ProtectedAttrs, element_path, find_elements_by_dot_path

logger = logging.getLogger(__name__)

_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 10

_pg_pools: dict[str, asyncpg.Pool] = {}
_pg_pool_lock = asyncio.Lock()
_oracle_pools: dict[str, oracledb.ConnectionPool] = {}
_oracle_pool_lock = threading.Lock()


def _pool_key(user: UserContext, alias: str) -> str:
    return f"{user.user_id}:{alias}"


async def _get_pg_pool(
    pool_key: str,
    cfg: DatabaseConfig,
    password: str,
) -> asyncpg.Pool:
    pool = _pg_pools.get(pool_key)
    if pool is not None:
        return pool

    async with _pg_pool_lock:
        pool = _pg_pools.get(pool_key)
        if pool is not None:
            return pool

        pool = await asyncpg.create_pool(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=password,
            database=cfg.database,
            min_size=_POOL_MIN_SIZE,
            max_size=_POOL_MAX_SIZE,
        )
        _pg_pools[pool_key] = pool
        logger.debug("Created PostgreSQL pool [key=%s max_size=%d]", pool_key, _POOL_MAX_SIZE)
        return pool


def _get_oracle_pool(
    pool_key: str,
    cfg: DatabaseConfig,
    password: str,
) -> oracledb.ConnectionPool:
    pool = _oracle_pools.get(pool_key)
    if pool is not None:
        return pool

    with _oracle_pool_lock:
        pool = _oracle_pools.get(pool_key)
        if pool is not None:
            return pool

        ensure_oracle_thick_mode(required=True)
        if oracledb.is_thin_mode():
            raise RuntimeError(
                "Oracle thick mode is required but the driver is still in thin mode."
            )

        pool = oracledb.create_pool(
            user=cfg.user,
            password=password,
            dsn=_oracle_dsn(cfg),
            min=_POOL_MIN_SIZE,
            max=_POOL_MAX_SIZE,
            increment=1,
        )
        _oracle_pools[pool_key] = pool
        logger.debug("Created Oracle pool [key=%s max=%d]", pool_key, _POOL_MAX_SIZE)
        return pool


async def close_db_pools() -> None:
    """Close all database connection pools. Called on application shutdown."""
    for alias, pool in list(_pg_pools.items()):
        await pool.close()
        logger.debug("Closed PostgreSQL pool [alias=%s]", alias)
    _pg_pools.clear()

    for alias, pool in list(_oracle_pools.items()):
        pool.close()
        logger.debug("Closed Oracle pool [alias=%s]", alias)
    _oracle_pools.clear()


class SqlMapping(BaseModel):
    """Declarative mapping from a SQL query result to XML element attributes."""

    query: str
    target_element: str
    fields: dict[str, str]  # db_column -> xml_attribute (optionally prefixed with @)
    db_alias: str | None = None
    target_path: str | None = None


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


def _oracle_columns_sync(pool: oracledb.ConnectionPool, sql: str) -> list[str]:
    conn = pool.acquire()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description is None:
                return []
            return [col[0].lower() for col in cursor.description]
    finally:
        pool.release(conn)


def _oracle_ping_sync(pool: oracledb.ConnectionPool) -> None:
    conn = pool.acquire()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
    finally:
        pool.release(conn)


def _oracle_query_sync(
    pool: oracledb.ConnectionPool,
    sql: str,
) -> list[dict[str, Any]]:
    """Run Oracle SQL via synchronous thick-mode connection pool.

    ``connect_async`` can still attempt thin mode on some Windows setups even after
    ``init_oracle_client()``, so thick mode queries use the sync driver in a worker
    thread instead.
    """
    conn = pool.acquire()
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
        pool.release(conn)


class DBService:
    """Execute SQL queries against configured database aliases."""

    def __init__(self, user: UserContext) -> None:
        self.user = user

    async def test_connection(self, alias: str) -> str:
        """Verify that a configured database alias is reachable."""
        connections = load_connections(self.user)
        if alias not in connections.databases:
            logger.error("Unknown database alias: %s", alias)
            raise ValueError(f"Database alias '{alias}' not found in connections")

        cfg = connections.databases[alias]
        password = get_db_password(self.user, alias)
        driver = cfg.driver.lower()
        key = _pool_key(self.user, alias)

        try:
            if driver == "postgresql":
                await self._test_postgresql(key, cfg, password)
                return f"Connected ({driver})"
            if driver in {"oracle", "oracledb"}:
                await self._test_oracle(key, cfg, password)
                return f"Connected ({driver})"
        except Exception:
            logger.exception(
                "Database connection test failed [alias=%s driver=%s host=%s:%s db=%s]",
                alias,
                driver,
                cfg.host,
                cfg.port,
                cfg.database or cfg.sid,
            )
            raise

        logger.error("Unsupported database driver [alias=%s driver=%s]", alias, cfg.driver)
        raise ValueError(f"Unsupported database driver: {cfg.driver}")

    async def _test_postgresql(
        self,
        pool_key: str,
        cfg: DatabaseConfig,
        password: str,
    ) -> None:
        pool = await _get_pg_pool(pool_key, cfg, password)
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    async def _test_oracle(
        self,
        pool_key: str,
        cfg: DatabaseConfig,
        password: str,
    ) -> None:
        pool = _get_oracle_pool(pool_key, cfg, password)
        try:
            await asyncio.to_thread(_oracle_ping_sync, pool)
        except oracledb.Error as exc:
            mapped = map_oracle_client_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise

    async def run_query(self, alias: str, sql: str) -> list[dict[str, Any]]:
        connections = load_connections(self.user)
        if alias not in connections.databases:
            logger.error("Unknown database alias: %s", alias)
            raise ValueError(f"Database alias '{alias}' not found in connections")

        cfg = connections.databases[alias]
        password = get_db_password(self.user, alias)
        driver = cfg.driver.lower()
        validated_sql = validate_readonly_select(sql)
        key = _pool_key(self.user, alias)

        try:
            if driver == "postgresql":
                return await self._query_postgresql(key, cfg, password, validated_sql)
            if driver in {"oracle", "oracledb"}:
                return await self._query_oracle(key, cfg, password, validated_sql)
        except Exception:
            logger.exception(
                "SQL query failed [alias=%s driver=%s host=%s:%s db=%s query=%s]",
                alias,
                driver,
                cfg.host,
                cfg.port,
                cfg.database or cfg.sid,
                truncate(validated_sql),
            )
            raise

        logger.error("Unsupported database driver [alias=%s driver=%s]", alias, cfg.driver)
        raise ValueError(f"Unsupported database driver: {cfg.driver}")

    async def get_query_columns(self, alias: str, sql: str) -> list[str]:
        connections = load_connections(self.user)
        if alias not in connections.databases:
            logger.error("Unknown database alias: %s", alias)
            raise ValueError(f"Database alias '{alias}' not found in connections")

        cfg = connections.databases[alias]
        password = get_db_password(self.user, alias)
        driver = cfg.driver.lower()
        validated_sql = validate_readonly_select(sql)
        key = _pool_key(self.user, alias)

        try:
            if driver == "postgresql":
                return await self._query_columns_postgresql(key, cfg, password, validated_sql)
            if driver in {"oracle", "oracledb"}:
                return await self._query_columns_oracle(key, cfg, password, validated_sql)
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
        pool_key: str,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[str]:
        pool = await _get_pg_pool(pool_key, cfg, password)
        async with pool.acquire() as conn:
            await conn.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
            )
            prepared = await conn.prepare(sql)
            return [attr.name.lower() for attr in prepared.get_attributes()]

    async def _query_columns_oracle(
        self,
        pool_key: str,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[str]:
        pool = _get_oracle_pool(pool_key, cfg, password)
        try:
            return await asyncio.to_thread(_oracle_columns_sync, pool, sql)
        except oracledb.Error as exc:
            mapped = map_oracle_client_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise

    async def _query_postgresql(
        self,
        pool_key: str,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[dict[str, Any]]:
        pool = await _get_pg_pool(pool_key, cfg, password)
        async with pool.acquire() as conn:
            await conn.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
            )
            row = await conn.fetchrow(sql)
            if row is None:
                return []
            return [{k.lower(): v for k, v in dict(row).items()}]

    async def _query_oracle(
        self,
        pool_key: str,
        cfg: DatabaseConfig,
        password: str,
        sql: str,
    ) -> list[dict[str, Any]]:
        pool = _get_oracle_pool(pool_key, cfg, password)
        try:
            return await asyncio.to_thread(_oracle_query_sync, pool, sql)
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
    ) -> tuple[str, ProtectedAttrs, list[str]]:
        """Stage-1 pipeline: inject DB values into specific elements by tag or path.

        For every mapping, the first row of the SQL result is fetched once and its
        columns are written to the declared XML attributes of every matching element
        in the tree.  When ``target_path`` is set, only the element at that dot-path
        is updated; otherwise all elements with ``target_element`` are matched.
        Returns the updated XML, protected attribute slots, and non-fatal warnings.
        """
        root = etree.fromstring(xml_text.encode("utf-8"))
        protected: set[tuple[tuple[str, int], ...], str] = set()
        warnings: list[str] = []

        active_mappings = [
            mapping
            for mapping in sql_mappings
            if mapping.query.strip() and mapping.target_element and mapping.db_alias
        ]

        async def _fetch_mapping_rows(mapping: SqlMapping) -> list[dict[str, Any]]:
            db_alias = mapping.db_alias
            if not db_alias:
                raise ValueError("db_alias is required for active mappings")
            try:
                return await self.run_query(db_alias, mapping.query)
            except Exception:
                logger.exception(
                    "DB override mapping failed [alias=%s element=%s path=%s fields=%s query=%s]",
                    mapping.db_alias,
                    mapping.target_element,
                    mapping.target_path,
                    list(mapping.fields.keys()),
                    truncate(mapping.query),
                )
                raise

        rows_by_mapping = await asyncio.gather(
            *[_fetch_mapping_rows(mapping) for mapping in active_mappings]
        )

        for mapping, rows in zip(active_mappings, rows_by_mapping, strict=True):
            if not rows:
                msg = (
                    f"DB override returned no rows "
                    f"[alias={mapping.db_alias} element={mapping.target_element}]"
                )
                logger.warning("%s query=%s", msg, truncate(mapping.query))
                warnings.append(msg)
                continue

            row = rows[0]
            lower_row: dict[str, str] = {
                k.lower(): str(v) for k, v in row.items() if v is not None
            }

            if mapping.target_path and mapping.target_path.strip():
                elements = find_elements_by_dot_path(root, mapping.target_path)
                if not elements:
                    msg = (
                        f"target_path not found: {mapping.target_path} "
                        f"(element={mapping.target_element})"
                    )
                    logger.warning(msg)
                    warnings.append(msg)
                    continue
            else:
                elements = list(root.iter(mapping.target_element))

            for el in elements:
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
        return xml_out, frozenset(protected), warnings


async def populate_with_db(
    user: UserContext,
    xml_text: str,
    schema: DTDSchema,
    alias: str,
    sql: str,
) -> str:
    """Populate XML by mapping the first SQL result row onto matching nodes."""
    return await DBService(user).populate_xml(xml_text, schema, alias, sql)


async def apply_db_overrides(
    user: UserContext,
    xml_text: str,
    sql_mappings: list[SqlMapping],
) -> tuple[str, ProtectedAttrs, list[str]]:
    """Stage-1 of the hybrid pipeline: targeted DB injections before faker/LLM fallback."""
    return await DBService(user).apply_overrides(xml_text, sql_mappings)
