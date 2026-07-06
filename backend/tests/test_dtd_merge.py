"""Tests for merging multiple DTD schemas."""

from pathlib import Path

import pytest

from app.core.dtd_merge import merge_dtd_schemas
from app.core.dtd_parser import DTDParser
from app.core.dtd_validator import validate_xml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def split_dtd_dir(tmp_path: Path) -> Path:
    dtd_dir = tmp_path / "dtd"
    dtd_dir.mkdir()
    (dtd_dir / "root.dtd").write_text(
        '<!ELEMENT Root (add-object)>\n<!ATTLIST Root id ID #REQUIRED>\n',
        encoding="utf-8",
    )
    (dtd_dir / "cs.dtd").write_text(
        '<!ELEMENT add-object (add-field*)>\n'
        '<!ATTLIST add-object name CDATA #REQUIRED>\n'
        '<!ELEMENT add-field EMPTY>\n',
        encoding="utf-8",
    )
    return dtd_dir


@pytest.fixture
def root_schema(split_dtd_dir: Path):
    parser = DTDParser(base_dir=split_dtd_dir)
    return parser.parse_file(split_dtd_dir / "root.dtd")


@pytest.fixture
def module_schema(split_dtd_dir: Path):
    parser = DTDParser(base_dir=split_dtd_dir)
    return parser.parse_file(split_dtd_dir / "cs.dtd")


def test_merge_dtd_schemas_combines_elements(root_schema, module_schema):
    merged = merge_dtd_schemas([root_schema, module_schema])

    assert "Root" in merged.elements
    assert "add-object" in merged.elements
    assert "add-field" in merged.elements
    assert len(merged.source_files) == 2


def test_validate_xml_with_cross_dtd_children(root_schema, module_schema):
    merged = merge_dtd_schemas([root_schema, module_schema])
    xml_text = (
        '<?xml version="1.0"?>\n'
        '<Root id="doc-1"><add-object name="obj"><add-field/></add-object></Root>'
    )

    single_schema_result = validate_xml(xml_text, root_schema)
    merged_result = validate_xml(xml_text, merged)

    assert single_schema_result.valid is False
    assert any("add-object" in error.message for error in single_schema_result.errors)
    assert merged_result.valid is True


def test_merge_dtd_schemas_single_schema_is_noop():
    parser = DTDParser(base_dir=FIXTURES)
    schema = parser.parse_file(FIXTURES / "main.dtd")
    merged = merge_dtd_schemas([schema])
    assert merged is schema
