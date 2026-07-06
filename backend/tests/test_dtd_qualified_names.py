"""Tests for DTD qualified element names (cs:add-object)."""

from pathlib import Path

import pytest

from app.core.dtd_exporter import dtd_local_name, export_flat_dtd
from app.core.dtd_parser import DTDParser
from app.core.dtd_validator import validate_xml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def qualified_dtd_dir(tmp_path: Path) -> Path:
    dtd_dir = tmp_path / "dtd"
    dtd_dir.mkdir()
    (dtd_dir / "action.ent").write_text(
        '<!ENTITY % action.content "(cs:add-field*)">\n'
        '<!ENTITY % action.attributes "\n'
        "    source CDATA #REQUIRED\n"
        "    document_type CDATA #REQUIRED\n"
        '">\n',
        encoding="utf-8",
    )
    (dtd_dir / "cs.dtd").write_text(
        '<!ENTITY % action SYSTEM "action.ent">\n'
        '<!ENTITY % cs.namespace \'xmlns:cs CDATA #FIXED "http://www.faktura.ru/cs"\'>\n'
        "%action;\n"
        "<!ELEMENT cs:add-object %action.content;>\n"
        "<!ATTLIST cs:add-object %action.attributes; %cs.namespace;>\n"
        "<!ELEMENT cs:add-field EMPTY>\n",
        encoding="utf-8",
    )
    (dtd_dir / "root.dtd").write_text(
        '<!ELEMENT PayDoc (cs:add-object*)>\n'
        "<!ATTLIST PayDoc id ID #REQUIRED>\n",
        encoding="utf-8",
    )
    return dtd_dir


def test_parser_reads_qualified_element_names(qualified_dtd_dir: Path):
    parser = DTDParser(base_dir=qualified_dtd_dir)
    root_schema = parser.parse_file(qualified_dtd_dir / "root.dtd")
    module_schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    assert "cs:add-object" in module_schema.elements
    assert "cs:add-field" in module_schema.elements
    assert "PayDoc" in root_schema.elements
    assert "cs:add-object" in root_schema.elements["PayDoc"].content_raw


def test_export_flat_dtd_uses_local_names(qualified_dtd_dir: Path):
    parser = DTDParser(base_dir=qualified_dtd_dir)
    schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    dtd_text = export_flat_dtd(schema)

    assert "<!ELEMENT add-object" in dtd_text
    assert "<!ELEMENT add-field" in dtd_text
    assert "cs:add-object" not in dtd_text
    assert 'xmlns:cs CDATA #FIXED "http://www.faktura.ru/cs"' in dtd_text


def test_parser_reads_fixed_xmlns_attribute(qualified_dtd_dir: Path):
    parser = DTDParser(base_dir=qualified_dtd_dir)
    schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    xmlns_attr = schema.elements["cs:add-object"].attributes["xmlns:cs"]
    assert xmlns_attr.default_decl.startswith("#FIXED")
    assert "http://www.faktura.ru/cs" in xmlns_attr.default_decl


def test_validate_namespaced_xml_with_qualified_dtd(qualified_dtd_dir: Path):
    parser = DTDParser(base_dir=qualified_dtd_dir)
    root_schema = parser.parse_file(qualified_dtd_dir / "root.dtd")
    module_schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    from app.core.dtd_merge import merge_dtd_schemas

    merged = merge_dtd_schemas([root_schema, module_schema])
    xml_text = (
        '<?xml version="1.0"?>\n'
        '<PayDoc id="doc-1">'
        '<cs:add-object xmlns:cs="http://www.faktura.ru/cs" source="interpay" document_type="d">'
        "<cs:add-field/>"
        "</cs:add-object>"
        "</PayDoc>"
    )

    result = validate_xml(xml_text, merged)
    assert result.valid is True, result.errors


def test_validate_rejects_wrong_fixed_xmlns(qualified_dtd_dir: Path):
    parser = DTDParser(base_dir=qualified_dtd_dir)
    root_schema = parser.parse_file(qualified_dtd_dir / "root.dtd")
    module_schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    from app.core.dtd_merge import merge_dtd_schemas

    merged = merge_dtd_schemas([root_schema, module_schema])
    xml_text = (
        '<?xml version="1.0"?>\n'
        '<PayDoc id="doc-1">'
        '<cs:add-object xmlns:cs="http://wrong.example/cs" source="interpay" document_type="d"/>'
        "</PayDoc>"
    )

    result = validate_xml(xml_text, merged)
    assert result.valid is False
    assert any("namespace" in error.message.lower() for error in result.errors)


def test_validate_user_xmlns_case(qualified_dtd_dir: Path):
    parser = DTDParser(base_dir=qualified_dtd_dir)
    root_schema = parser.parse_file(qualified_dtd_dir / "root.dtd")
    module_schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    from app.core.dtd_merge import merge_dtd_schemas

    merged = merge_dtd_schemas([root_schema, module_schema])
    valid_xml = (
        '<PayDoc id="doc-1">'
        '<cs:add-object xmlns:cs="http://www.faktura.ru/cs" '
        'source="interpay" document_type="d"><cs:add-field/></cs:add-object>'
        "</PayDoc>"
    )
    invalid_xml = valid_xml.replace("http://www.faktura.ru/cs", "http://evil.example/cs")

    assert validate_xml(valid_xml, merged).valid is True
    assert validate_xml(invalid_xml, merged).valid is False


def test_dtd_local_name_helper():
    assert dtd_local_name("cs:add-object") == "add-object"
    assert dtd_local_name("PayDoc") == "PayDoc"


def test_known_element_names_keep_qualified_names_only(qualified_dtd_dir: Path):
    from app.api.routes.dtd import _known_element_names

    parser = DTDParser(base_dir=qualified_dtd_dir)
    module_schema = parser.parse_file(qualified_dtd_dir / "cs.dtd")

    names = _known_element_names(module_schema)

    assert "cs:add-object" in names
    assert "add-object" not in names
