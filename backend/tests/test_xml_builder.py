"""Tests for XML builder."""

from pathlib import Path

import pytest
from lxml import etree

from app.core.dtd_parser import DTDParser
from app.core.xml_builder import BuildConfig, build_xml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema():
    parser = DTDParser(base_dir=FIXTURES)
    return parser.parse_file(FIXTURES / "main.dtd")


def test_minimal_build(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="minimal",
    )
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert root.tag == "PayDoc"
    assert "id" in root.attrib
    assert "kladr" in root.attrib
    assert "status" not in root.attrib  # implied, not in minimal

    children = [c.tag for c in root]
    assert "Header" in children
    assert "Body" in children
    assert "Footer" not in children  # optional ?


def test_maximal_build(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="maximal",
        repeat_count=2,
    )
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert "status" in root.attrib
    assert "Footer" in [c.tag for c in root]

    body = root.find("Body")
    assert body is not None
    records = body.findall("Record")
    assert len(records) == 2


def test_custom_build(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="custom",
        custom_paths={"PayDoc.Footer", "PayDoc.Header.Meta"},
    )
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert "Footer" in [c.tag for c in root]
    header = root.find("Header")
    assert header is not None
    assert len(header.findall("Meta")) >= 1


def test_pcdata_element(schema):
    config = BuildConfig(root_element="Title", mode="minimal")
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))
    assert root.tag == "Title"
    assert root.text in (None, "")


def test_empty_element(schema):
    config = BuildConfig(root_element="Footer", mode="minimal")
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))
    assert root.tag == "Footer"
    assert len(root) == 0
