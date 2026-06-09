"""Tests for the three-pass DTD parser."""

from pathlib import Path

import pytest

from app.core.content_model import parse_content_model
from app.core.dtd_parser import DTDParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def parser() -> DTDParser:
    return DTDParser(base_dir=FIXTURES)


def test_parse_parametric_enums(parser: DTDParser):
    dtd = """
    <!ENTITY % Boolean "(true|false)">
    <!ENTITY % Status "(active|inactive)">
    <!ELEMENT Root EMPTY>
    <!ATTLIST Root
        active %Boolean; #REQUIRED
        status %Status; #IMPLIED
    >
    """
    schema = parser.parse_string(dtd)

    root = schema.elements["Root"]
    assert root.attributes["active"].attr_type == "ENUM"
    assert root.attributes["active"].allowed_values == ["true", "false"]
    assert root.attributes["status"].allowed_values == [
        "active",
        "inactive",
    ]


def test_extract_doc_and_att_comments(parser: DTDParser):
    dtd = """
    <!-- Документ платежного поручения.
         @doc Основной корневой элемент
         @att kladr код КЛАДР
    -->
    <!ELEMENT PayDoc (Header)>
    <!ATTLIST PayDoc
        id ID #REQUIRED
        kladr CDATA #REQUIRED
    >
    """
    schema = parser.parse_string(dtd)
    paydoc = schema.elements["PayDoc"]

    assert "Основной корневой элемент" in paydoc.doc
    assert paydoc.attributes["kladr"].doc == "код КЛАДР"


def test_content_model_sequence(parser: DTDParser):
    dtd = """
    <!ELEMENT PayDoc (Header, Body, Footer?)>
    <!ELEMENT Header EMPTY>
    <!ELEMENT Body EMPTY>
    <!ELEMENT Footer EMPTY>
    """
    schema = parser.parse_string(dtd)
    model = schema.elements["PayDoc"].content_model

    assert model.kind == "SEQUENCE"
    refs = [c.ref for c in model.children]
    assert refs == ["Header", "Body", "Footer"]
    assert model.children[2].quantifier == "?"


def test_required_and_implied_attributes(parser: DTDParser):
    dtd = """
    <!ELEMENT Item EMPTY>
    <!ATTLIST Item
        id ID #REQUIRED
        label CDATA #IMPLIED
        version CDATA #FIXED "1.0"
    >
    """
    schema = parser.parse_string(dtd)
    attrs = schema.elements["Item"].attributes

    assert attrs["id"].default_decl == "#REQUIRED"
    assert attrs["label"].default_decl == "#IMPLIED"
    assert attrs["version"].default_decl == '#FIXED "1.0"'


def test_enum_attribute_type(parser: DTDParser):
    dtd = """
    <!ELEMENT Field (#PCDATA)>
    <!ATTLIST Field
        type (string|number|date) #REQUIRED
    >
    """
    schema = parser.parse_string(dtd)
    field_attr = schema.elements["Field"].attributes["type"]

    assert field_attr.attr_type == "ENUM"
    assert field_attr.allowed_values == ["string", "number", "date"]


def test_external_system_entity_resolution(parser: DTDParser):
    schema = parser.parse_file(FIXTURES / "main.dtd")

    assert len(schema.source_files) >= 2
    paydoc = schema.elements["PayDoc"]

    assert "Основной корневой элемент" in paydoc.doc
    assert paydoc.attributes["active"].allowed_values == ["true", "false"]
    assert paydoc.attributes["status"].allowed_values == [
        "active",
        "inactive",
        "pending",
    ]

    body = schema.elements["Body"]
    assert body.content_model.ref == "Record"
    assert body.content_model.quantifier == "+"


def test_mixed_and_choice_content(parser: DTDParser):
    schema = parser.parse_file(FIXTURES / "main.dtd")

    title = schema.elements["Title"]
    assert title.content_model.kind == "PCDATA"

    record = schema.elements["Record"]
    assert record.content_model.kind == "CHOICE"
    assert record.content_model.quantifier == "*"


def test_param_entities_collected(parser: DTDParser):
    schema = parser.parse_file(FIXTURES / "main.dtd")

    assert "Boolean" in schema.param_entities
    assert "Status" in schema.param_entities
    assert "true" in schema.param_entities["Boolean"]


def test_root_elements_sorted(parser: DTDParser):
    schema = parser.parse_file(FIXTURES / "main.dtd")
    names = schema.root_elements()
    assert names == sorted(names)
    assert "PayDoc" in names


def test_footer_empty_element(parser: DTDParser):
    schema = parser.parse_file(FIXTURES / "main.dtd")
    footer = schema.elements["Footer"]
    assert footer.content_model.kind == "EMPTY"
