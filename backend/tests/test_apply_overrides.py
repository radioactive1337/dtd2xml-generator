"""Tests for hybrid DB override application."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.db_service import DBService, SqlMapping


SAMPLE_XML = """\
<PayDoc>
  <Body>
    <client inn="" name=""/>
    <client inn="" name=""/>
  </Body>
  <Body>
    <client inn="" name=""/>
  </Body>
</PayDoc>
"""


@pytest.mark.asyncio
async def test_apply_overrides_tag_only_fills_all_matches():
    mapping = SqlMapping(
        query="SELECT 1",
        target_element="client",
        fields={"inn": "inn", "name": "name"},
        db_alias="test_db",
    )

    with patch.object(
        DBService,
        "run_query",
        new=AsyncMock(return_value=[{"inn": "7701", "name": "Acme"}]),
    ):
        xml_out, protected, warnings = await DBService().apply_overrides(
            SAMPLE_XML,
            [mapping],
        )

    assert warnings == []
    assert xml_out.count('inn="7701"') == 3
    assert xml_out.count('name="Acme"') == 3
    assert len(protected) == 6


@pytest.mark.asyncio
async def test_apply_overrides_target_path_fills_single_element():
    mapping = SqlMapping(
        query="SELECT 1",
        target_element="client",
        target_path="PayDoc.Body.client",
        fields={"inn": "inn"},
        db_alias="test_db",
    )

    with patch.object(
        DBService,
        "run_query",
        new=AsyncMock(return_value=[{"inn": "9999"}]),
    ):
        xml_out, protected, warnings = await DBService().apply_overrides(
            SAMPLE_XML,
            [mapping],
        )

    assert warnings == []
    assert xml_out.count('inn="9999"') == 1
    assert len(protected) == 1


@pytest.mark.asyncio
async def test_apply_overrides_path_not_found_skips_with_warning():
    mapping = SqlMapping(
        query="SELECT 1",
        target_element="client",
        target_path="PayDoc.Missing.client",
        fields={"inn": "inn"},
        db_alias="test_db",
    )

    with patch.object(
        DBService,
        "run_query",
        new=AsyncMock(return_value=[{"inn": "9999"}]),
    ):
        xml_out, protected, warnings = await DBService().apply_overrides(
            SAMPLE_XML,
            [mapping],
        )

    assert 'inn="9999"' not in xml_out
    assert protected == frozenset()
    assert len(warnings) == 1
    assert "target_path not found" in warnings[0]


@pytest.mark.asyncio
async def test_apply_overrides_no_rows_adds_warning():
    mapping = SqlMapping(
        query="SELECT 1",
        target_element="client",
        fields={"inn": "inn"},
        db_alias="test_db",
    )

    with patch.object(
        DBService,
        "run_query",
        new=AsyncMock(return_value=[]),
    ):
        xml_out, protected, warnings = await DBService().apply_overrides(
            SAMPLE_XML,
            [mapping],
        )

    assert 'inn="9999"' not in xml_out
    assert protected == frozenset()
    assert len(warnings) == 1
    assert "no rows" in warnings[0].lower()
