"""Suggest SQL column → XML attribute mappings (LLM with fuzzy fallback)."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.dtd_models import DTDSchema, ElementDef
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    return re.sub(r"^@", "", name or "", flags=re.IGNORECASE).lower().replace("-", "").replace("_", "")


def _resolve_name(name: str, allowed: dict[str, str]) -> str | None:
    """Map a name to its canonical form from *allowed* (lower -> original)."""
    if not name:
        return None
    if name in allowed.values():
        return name
    return allowed.get(name.lower()) or allowed.get(_normalize_name(name))


def suggest_field_mappings_fuzzy(
    columns: list[str],
    xml_attributes: list[str],
    existing_pairs: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Local fuzzy matcher used when LLM is unavailable or returns invalid data."""
    used_attrs = {
        _normalize_name(pair.get("xml_attr", ""))
        for pair in existing_pairs
        if pair.get("xml_attr", "").strip()
    }
    available = [attr for attr in xml_attributes if _normalize_name(attr) not in used_attrs]
    suggestions: list[dict[str, str]] = []

    for col in columns:
        norm_col = _normalize_name(col)
        if not norm_col:
            suggestions.append({"db_col": col, "xml_attr": ""})
            continue

        match = next(
            (attr for attr in available if _normalize_name(attr) == norm_col),
            None,
        )
        if not match:
            match = next(
                (
                    attr
                    for attr in available
                    if (norm_col in _normalize_name(attr) or _normalize_name(attr) in norm_col)
                ),
                None,
            )

        if match:
            suggestions.append({"db_col": col, "xml_attr": match})
            used_attrs.add(_normalize_name(match))
            available = [attr for attr in available if attr != match]
        else:
            suggestions.append({"db_col": col, "xml_attr": ""})

    return suggestions


def _column_lookup(columns: list[str]) -> dict[str, str]:
    return {_normalize_name(col): col for col in columns}


def _filter_pairs_to_columns(
    pairs: list[dict[str, str]],
    columns: list[str],
) -> list[dict[str, str]]:
    """Keep only manually confirmed pairs whose db_col is in *columns*."""
    lookup = _column_lookup(columns)
    result: list[dict[str, str]] = []
    seen_cols: set[str] = set()

    for pair in pairs:
        db_col = _resolve_name(str(pair.get("db_col", "")), lookup)
        xml_attr = str(pair.get("xml_attr", "")).strip()
        if not db_col or not xml_attr:
            continue
        norm = _normalize_name(db_col)
        if norm in seen_cols:
            continue
        result.append({"db_col": db_col, "xml_attr": xml_attr})
        seen_cols.add(norm)

    return result


def _merge_mappings_for_columns(
    kept: list[dict[str, str]],
    suggestions: list[dict[str, str]],
    columns: list[str],
) -> list[dict[str, str]]:
    """Return exactly one row per SQL column, in query column order."""
    by_col: dict[str, str] = {}

    for row in kept:
        by_col[row["db_col"]] = row["xml_attr"]

    for row in suggestions:
        db_col = row.get("db_col", "")
        if not db_col:
            continue
        if db_col not in by_col or not by_col[db_col].strip():
            by_col[db_col] = row.get("xml_attr", "")

    return [{"db_col": col, "xml_attr": by_col.get(col, "")} for col in columns]


def _attribute_context(elem: ElementDef) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for name, attr in elem.attributes.items():
        entry: dict[str, Any] = {"name": name}
        if attr.doc:
            entry["doc"] = attr.doc
        if attr.allowed_values:
            entry["allowed_values"] = attr.allowed_values
        lines.append(entry)
    return lines


def _validate_llm_mappings(
    raw_mappings: list[dict[str, Any]],
    columns: list[str],
    xml_attributes: list[str],
) -> list[dict[str, str]]:
    col_lookup = {_normalize_name(col): col for col in columns}
    attr_lookup = {_normalize_name(attr): attr for attr in xml_attributes}
    used_attrs: set[str] = set()
    by_col: dict[str, str] = {}

    for item in raw_mappings:
        if not isinstance(item, dict):
            continue
        db_col = _resolve_name(str(item.get("db_col", "")), col_lookup)
        xml_attr = _resolve_name(str(item.get("xml_attr", "")), attr_lookup)
        if not db_col or db_col in by_col:
            continue
        if xml_attr and _normalize_name(xml_attr) in used_attrs:
            xml_attr = None
        by_col[db_col] = xml_attr or ""
        if xml_attr:
            used_attrs.add(_normalize_name(xml_attr))

    return [{"db_col": col, "xml_attr": by_col.get(col, "")} for col in columns]


class FieldMappingService:
    """Orchestrate LLM-based field mapping suggestions."""

    def __init__(self, llm_alias: str = "default") -> None:
        self.llm = LLMService(alias=llm_alias)

    async def suggest_mappings(
        self,
        schema: DTDSchema,
        target_element: str,
        columns: list[str],
        existing_pairs: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], str]:
        """Return merged field rows and the matcher used: ``llm`` or ``fuzzy``."""
        if target_element not in schema.elements:
            raise ValueError(f"Element '{target_element}' not found in schema")

        elem = schema.elements[target_element]
        xml_attributes = list(elem.attributes.keys())

        kept = _filter_pairs_to_columns(existing_pairs, columns)
        used_cols = {_normalize_name(pair["db_col"]) for pair in kept}
        used_attrs = {_normalize_name(pair["xml_attr"]) for pair in kept}

        cols_to_map = [col for col in columns if _normalize_name(col) not in used_cols]
        available_attrs = [
            attr for attr in xml_attributes if _normalize_name(attr) not in used_attrs
        ]

        if not cols_to_map:
            return _merge_mappings_for_columns(kept, [], columns), "fuzzy"

        suggestions: list[dict[str, str]]
        matcher = "fuzzy"

        if available_attrs and self.llm.base_url:
            try:
                raw = await self.llm.suggest_field_mappings_json(
                    target_element=target_element,
                    element_doc=elem.doc,
                    columns=cols_to_map,
                    attributes=_attribute_context(elem),
                    existing_pairs=kept,
                )
                suggestions = _validate_llm_mappings(raw, cols_to_map, available_attrs)
                if any(row["xml_attr"] for row in suggestions):
                    matcher = "llm"
                else:
                    suggestions = suggest_field_mappings_fuzzy(
                        cols_to_map,
                        available_attrs,
                        kept,
                    )
            except Exception:
                logger.exception(
                    "LLM field mapping failed [element=%s columns=%s]",
                    target_element,
                    cols_to_map,
                )
                suggestions = suggest_field_mappings_fuzzy(
                    cols_to_map,
                    available_attrs,
                    kept,
                )
        else:
            suggestions = suggest_field_mappings_fuzzy(
                cols_to_map,
                available_attrs,
                kept,
            )

        return _merge_mappings_for_columns(kept, suggestions, columns), matcher


async def suggest_field_mappings(
    schema: DTDSchema,
    target_element: str,
    columns: list[str],
    existing_pairs: list[dict[str, str]] | None = None,
    llm_alias: str = "default",
) -> tuple[list[dict[str, str]], str]:
    """Suggest db_col → xml_attr rows for hybrid mapping UI."""
    return await FieldMappingService(llm_alias=llm_alias).suggest_mappings(
        schema,
        target_element,
        columns,
        existing_pairs or [],
    )
