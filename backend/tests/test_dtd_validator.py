"""Tests for DTD-based XML validation."""

from pathlib import Path

import pytest
from lxml import etree

from app.core.dtd_exporter import export_flat_dtd
from app.core.dtd_parser import DTDParser
from app.core.dtd_validator import validate_xml
from app.core.xml_builder import BuildConfig, build_xml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema():
    parser = DTDParser(base_dir=FIXTURES)
    return parser.parse_file(FIXTURES / "main.dtd")


def test_export_flat_dtd_resolves_parameter_entities(schema):
    dtd_text = export_flat_dtd(schema)
    assert "active (true|false)" in dtd_text
    assert "%Boolean;" not in dtd_text

    dtd = __import__("io").BytesIO(dtd_text.encode("utf-8"))
    etree.DTD(dtd)


def test_validate_generated_minimal_xml(schema):
    config = BuildConfig(root_element="PayDoc", mode="minimal")
    result = build_xml(schema, config)

    validation = validate_xml(result.xml_text, schema)
    assert validation.valid is True
    assert validation.errors == []


def test_validate_invalid_xml_missing_required_attribute(schema):
    config = BuildConfig(root_element="PayDoc", mode="minimal")
    result = build_xml(schema, config)
    bad_xml = result.xml_text.replace('id="', 'removed="', 1)

    validation = validate_xml(bad_xml, schema)
    assert validation.valid is False
    assert len(validation.errors) >= 1


def test_validate_empty_xml(schema):
    validation = validate_xml("", schema)
    assert validation.valid is False
    assert validation.errors[0].message == "XML is empty"


def test_validate_malformed_xml(schema):
    validation = validate_xml("<PayDoc><unclosed>", schema)
    assert validation.valid is False
    assert validation.errors[0].line > 0
