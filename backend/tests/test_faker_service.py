"""Tests for Smart Faker service."""

from pathlib import Path

import pytest
from lxml import etree

from app.core.dtd_parser import DTDParser
from app.core.xml_builder import BuildConfig, build_xml
from app.services.faker_service import FakerService, populate_with_faker

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema():
    parser = DTDParser(base_dir=FIXTURES)
    return parser.parse_file(FIXTURES / "main.dtd")


@pytest.fixture
def skeleton_xml(schema):
    config = BuildConfig(root_element="PayDoc", mode="minimal")
    return build_xml(schema, config).xml_text


def test_populate_fills_required_attributes(schema, skeleton_xml):
    result = populate_with_faker(skeleton_xml, schema)
    root = etree.fromstring(result.encode("utf-8"))
    assert root.attrib.get("id")
    assert root.attrib.get("kladr")
    assert root.attrib.get("active") in ("true", "false")


def test_populate_enum_attribute(schema, skeleton_xml):
    result = populate_with_faker(skeleton_xml, schema)
    root = etree.fromstring(result.encode("utf-8"))
    body = root.find("Body")
    assert body is not None
    for record in body.findall("Record"):
        for field in record.findall("Field"):
            assert field.attrib.get("type") in ("string", "number", "date")


def test_faker_heuristics():
    service = FakerService()
    assert "@" in service.generate_attribute_value("email")
    assert service.generate_attribute_value("inn").isdigit()
    assert len(service.generate_attribute_value("kladr")) > 0


def test_faker_enum_from_attr_def(schema):
    service = FakerService()
    field_def = schema.elements["Field"]
    type_attr = field_def.attributes["type"]
    value = service.generate_attribute_value("type", type_attr)
    assert value in type_attr.allowed_values


def test_fill_empty_only_preserves_existing_values(schema, skeleton_xml):
    root = etree.fromstring(skeleton_xml.encode("utf-8"))
    root.set("id", "from-db")
    xml_with_db_value = etree.tostring(
        root,
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=False,
    ).decode("UTF-8")

    result = populate_with_faker(xml_with_db_value, schema, fill_empty_only=True)
    populated = etree.fromstring(result.encode("utf-8"))

    assert populated.attrib.get("id") == "from-db"
    assert populated.attrib.get("kladr")


def test_hybrid_fills_unmapped_placeholder_attributes(schema, skeleton_xml):
    root = etree.fromstring(skeleton_xml.encode("utf-8"))
    root.set("kladr", "from-db")
    xml_with_db_value = etree.tostring(
        root,
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=False,
    ).decode("UTF-8")
    protected = frozenset({((), "kladr")})

    result = populate_with_faker(
        xml_with_db_value,
        schema,
        fill_empty_only=True,
        protected_attrs=protected,
    )
    populated = etree.fromstring(result.encode("utf-8"))

    assert populated.attrib.get("kladr") == "from-db"
    assert populated.attrib.get("id") != "id-1"
    assert populated.attrib.get("active") in ("true", "false")
    field = populated.find("Body/Record/Field")
    assert field is not None
    assert field.attrib.get("name")
