"""Tests for SQL column → XML attribute mapping suggestions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.field_mapping_service import (
    _validate_llm_mappings,
    suggest_field_mappings_fuzzy,
)


def test_fuzzy_maps_snake_case_to_kebab_case():
    result = suggest_field_mappings_fuzzy(
        ["is_non_resident", "name"],
        ["is-non-resident", "name"],
        [],
    )
    assert result == [
        {"db_col": "is_non_resident", "xml_attr": "is-non-resident"},
        {"db_col": "name", "xml_attr": "name"},
    ]


def test_fuzzy_skips_already_used_attributes():
    result = suggest_field_mappings_fuzzy(
        ["name", "client_name"],
        ["name", "full-name"],
        [{"db_col": "id", "xml_attr": "name"}],
    )
    assert result[0]["xml_attr"] == "full-name"
    assert result[1]["xml_attr"] == ""


def test_validate_llm_mappings_accepts_exact_names_only():
    validated = _validate_llm_mappings(
        [
            {"db_col": "CLIENT_NAME", "xml_attr": "name"},
            {"db_col": "inn", "xml_attr": "made-up-attr"},
            {"db_col": "unknown", "xml_attr": "name"},
        ],
        ["client_name", "inn"],
        ["name", "is-non-resident"],
    )
    assert validated == [
        {"db_col": "client_name", "xml_attr": "name"},
        {"db_col": "inn", "xml_attr": ""},
    ]


@pytest.mark.asyncio
async def test_suggest_field_mappings_uses_llm_when_available(schema_from_enterprise):
    from app.services.field_mapping_service import FieldMappingService

    service = FieldMappingService()
    service.llm.base_url = "http://llm.test"
    with patch.object(
        service.llm,
        "suggest_field_mappings_json",
        new=AsyncMock(
            return_value=[
                {"db_col": "client_name", "xml_attr": "name"},
            ],
        ),
    ):
        mappings, matcher = await service.suggest_mappings(
            schema_from_enterprise,
            "client",
            ["client_name"],
            [],
        )

    assert matcher == "llm"
    assert mappings == [{"db_col": "client_name", "xml_attr": "name"}]


@pytest.fixture
def schema_from_enterprise():
    from pathlib import Path

    from app.core.dtd_parser import DTDParser

    sample = Path(__file__).parent / "fixtures" / "enterprise_sample.dtd"
    return DTDParser(base_dir=sample.parent).parse_file(sample)
