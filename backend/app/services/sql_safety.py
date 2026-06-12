"""Guards for user-supplied SQL executed by the application."""

from __future__ import annotations

import re

_SELECT_START = re.compile(r"^(?:WITH\b|SELECT\b)", re.IGNORECASE | re.DOTALL)
_STATEMENT_TERMINATORS = frozenset({";", "\uff1b"})
_INVISIBLE_CHARS = re.compile(r"[\x00\u200b\u200c\u200d\ufeff]")
_NON_ASCII_QUOTES = re.compile(r"[\u2018\u2019\u201a\u201b\u2032\u2035\u02bc\u02b9\u0060\u00b4]")


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
    normalized = _INVISIBLE_CHARS.sub("", sql)
    normalized = _NON_ASCII_QUOTES.sub("'", normalized).strip()
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


def prepare_safe_query(sql: str, driver: str, *, limit_rows: bool = True) -> str:
    """Validate user SQL. Row limits are enforced by the DB driver, not SQL rewriting."""
    del driver, limit_rows
    return validate_readonly_select(sql)
