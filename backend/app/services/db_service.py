"""Database query service for hybrid XML data population."""

from __future__ import annotations

from typing import Any

import asyncpg
from pydantic import BaseModel

from app.config import get_db_password, load_connections
from app.core.dtd_models import DTDSchema
from lxml import etree


class SqlMapping(BaseModel):
    """Declarative mapping from a SQL query result to XML element attributes."""

    query: str
    target_element: str
    fields: dict[str, str]  # db_column -> xml_attribute (optionally prefixed with @)


class DBService:
    """Execute SQL queries against configured database aliases."""

    async def run_query(self, alias: str, sql: str) -> list[dict[str, Any]]:
        connections = load_connections()
        if alias not in connections.databases:
            raise ValueError(f"Database alias '{alias}' not found in connections.json")

        cfg = connections.databases[alias]
        if cfg.driver != "postgresql":
            raise ValueError(f"Unsupported database driver: {cfg.driver}")

        password = get_db_password(alias)
        conn = await asyncpg.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=password,
            database=cfg.database,
        )
        try:
            rows = await conn.fetch(sql)
            return [dict(row) for row in rows]
        finally:
            await conn.close()

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
        db_alias: str,
    ) -> str:
        """Stage-1 pipeline: inject DB values into specific elements by tag name.

        For every mapping, the first row of the SQL result is fetched once and its
        columns are written to the declared XML attributes of every matching element
        in the tree.  Values already set by this stage are intentionally left alone
        by the Stage-2 faker/LLM fallback.
        """
        root = etree.fromstring(xml_text.encode("utf-8"))

        for mapping in sql_mappings:
            if not mapping.query.strip() or not mapping.target_element:
                continue

            rows = await self.run_query(db_alias, mapping.query)
            if not rows:
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

        return etree.tostring(
            root,
            pretty_print=True,
            encoding="UTF-8",
            xml_declaration=False,
        ).decode("UTF-8")


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
    db_alias: str,
) -> str:
    """Stage-1 of the hybrid pipeline: targeted DB injections before faker/LLM fallback."""
    return await DBService().apply_overrides(xml_text, sql_mappings, db_alias)
