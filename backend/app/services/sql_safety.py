"""Guards for user-supplied SQL executed by the application."""

from __future__ import annotations

import re

_SELECT_START = re.compile(r"^(?:WITH\b|SELECT\b)", re.IGNORECASE | re.DOTALL)
_STATEMENT_TERMINATORS = frozenset({";", "\uff1b"})
_INVISIBLE_CHARS = re.compile(r"[\x00\u200b\u200c\u200d\ufeff]")
_SMART_QUOTES = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)
_ORACLE_ROW_LIMIT = re.compile(
    r"\b(?:ROWNUM\b|FETCH\s+(?:FIRST|NEXT)\s+\d+\s+ROWS?\s+ONLY)\b",
    re.IGNORECASE,
)


def strip_sql_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* */`` block comments."""
    result: list[str] = []
    i = 0
    length = len(sql)

    while i < length:
        if sql.startswith("--", i):
            while i < length and sql[i] != "\n":
                i += 1
            continue

        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
            continue

        result.append(sql[i])
        i += 1

    return "".join(result)


def normalize_sql_text(sql: str) -> str:
    """Remove invisible characters and trailing statement terminators."""
    normalized = _INVISIBLE_CHARS.sub("", sql).translate(_SMART_QUOTES).strip()
    while normalized and normalized[-1] in _STATEMENT_TERMINATORS:
        normalized = normalized[:-1].rstrip()
    return normalized


def validate_readonly_select(sql: str) -> str:
    """Ensure SQL is a single read-only SELECT (or WITH … SELECT).

    Returns the query without a trailing semicolon.
    """
    normalized = normalize_sql_text(sql)
    if not normalized:
        raise ValueError("SQL query is required")

    if any(terminator in normalized for terminator in _STATEMENT_TERMINATORS):
        raise ValueError("Multiple SQL statements are not allowed")

    cleaned = strip_sql_comments(normalized).strip()
    if not _SELECT_START.match(cleaned):
        raise ValueError("Only SELECT queries are allowed")

    return normalized


def apply_row_limit(sql: str, driver: str) -> str:
    """Wrap a validated SELECT so the database returns at most one row."""
    driver_key = driver.lower()
    if driver_key == "postgresql":
        return f"SELECT * FROM ({sql}) AS _safe_q LIMIT 1"
    if driver_key in {"oracle", "oracledb"}:
        if _ORACLE_ROW_LIMIT.search(sql):
            return sql
        return f"SELECT * FROM ({sql}) _safe_q WHERE ROWNUM <= 1"
    return sql


def prepare_safe_query(sql: str, driver: str, *, limit_rows: bool = True) -> str:
    """Validate user SQL and optionally enforce a single-row cap."""
    safe_sql = validate_readonly_select(sql)
    if limit_rows:
        return apply_row_limit(safe_sql, driver)
    return safe_sql
