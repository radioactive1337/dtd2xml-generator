"""Regression tests for enterprise DTD patterns (hyphenated names, dotted entities)."""

from pathlib import Path

import pytest

from app.core.dtd_parser import DTDParser

SAMPLE = Path(__file__).parent / "fixtures" / "enterprise_sample.dtd"


@pytest.fixture
def schema():
    parser = DTDParser(base_dir=SAMPLE.parent)
    return parser.parse_file(SAMPLE)


def test_hyphenated_element_names(schema):
    for name in (
        "common-detail",
        "error-stack",
        "chief-accountant",
        "amount-national",
        "exchange-rate-terms",
        "identity-card",
        "market-rate",
        "source-document",
    ):
        assert name in schema.elements, f"Missing element: {name}"


def test_entity_substitution_in_content_model(schema):
    amount = schema.elements["amount"]
    assert amount.content_raw == "(amount-national?, amount-credit?)"
    refs = [c.ref for c in amount.content_model.children]
    assert refs == ["amount-national", "amount-credit"]


def test_entity_substitution_in_attributes(schema):
    client = schema.elements["client"]
    assert "name" in client.attributes
    assert "is-non-resident" in client.attributes
    assert client.attributes["is-non-resident"].allowed_values == ["true", "false"]


def test_hyphenated_attribute_names(schema):
    identity = schema.elements["identity-card"]
    assert "type-code" in identity.attributes
    assert "issue-date" in identity.attributes
    exchange = schema.elements["exchange-rate"]
    assert "currency-from-code" in exchange.attributes


def test_element_count(schema):
    assert len(schema.elements) >= 40


def test_literal_default_attribute(schema):
    fault = schema.elements["fault"]
    attr = fault.attributes["document_type"]
    assert attr.attr_type == "CDATA"
    assert attr.default_decl == '"a"'
    assert attr.dtd_default_value() == "a"


def test_single_value_enum_default():
    parser = DTDParser()
    dtd = """
    <!ELEMENT Root EMPTY>
    <!ATTLIST Root
        document_type (payment-order) #REQUIRED
    >
    """
    schema = parser.parse_string(dtd)
    attr = schema.elements["Root"].attributes["document_type"]
    assert attr.attr_type == "ENUM"
    assert attr.allowed_values == ["payment-order"]
    assert attr.dtd_default_value() == "payment-order"
