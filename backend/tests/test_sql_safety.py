"""Tests for user-supplied SQL guards."""

from __future__ import annotations

import pytest

from app.services.sql_safety import (
    apply_row_limit,
    prepare_safe_query,
    validate_readonly_select,
)


def test_validate_allows_select():
    assert validate_readonly_select("SELECT 1") == "SELECT 1"


def test_validate_allows_with_cte():
    sql = "WITH cte AS (SELECT 1 AS n) SELECT n FROM cte"
    assert validate_readonly_select(sql) == sql


def test_validate_allows_leading_comments():
    sql = "-- preview\nSELECT 1"
    assert validate_readonly_select(sql) == sql


def test_validate_rejects_drop():
    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        validate_readonly_select("DROP TABLE users")


def test_validate_rejects_update():
    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        validate_readonly_select("UPDATE users SET name = 'x'")


def test_validate_rejects_multiple_statements():
    with pytest.raises(ValueError, match="Multiple SQL statements are not allowed"):
        validate_readonly_select("SELECT 1; DROP TABLE users")


def test_validate_strips_trailing_semicolon():
    assert validate_readonly_select("SELECT 1;") == "SELECT 1"


def test_apply_row_limit_postgresql():
    wrapped = apply_row_limit("SELECT id FROM big_table", "postgresql")
    assert wrapped == "SELECT * FROM (SELECT id FROM big_table) AS _safe_q LIMIT 1"


def test_apply_row_limit_oracle():
    wrapped = apply_row_limit("SELECT id FROM big_table", "oracle")
    assert wrapped == "SELECT * FROM (SELECT id FROM big_table) _safe_q WHERE ROWNUM <= 1"


def test_apply_row_limit_oracle_skips_when_rownum_present():
    sql = "SELECT id FROM big_table WHERE ROWNUM = 1"
    assert apply_row_limit(sql, "oracle") == sql


def test_normalize_strips_fullwidth_semicolon():
    from app.services.sql_safety import normalize_sql_text

    assert (
        normalize_sql_text("SELECT 1\uFF1B")
        == "SELECT 1"
    )


def test_normalize_replaces_smart_quotes():
    from app.services.sql_safety import normalize_sql_text

    assert (
        normalize_sql_text("SELECT 1 WHERE x = \u2018abc\u2019")
        == "SELECT 1 WHERE x = 'abc'"
    )


def test_prepare_safe_query_wraps_select():
    wrapped = prepare_safe_query("SELECT 1", "postgresql")
    assert "LIMIT 1" in wrapped
