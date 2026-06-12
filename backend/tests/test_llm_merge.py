"""Tests for hybrid LLM merge behaviour."""

from lxml import etree

from app.services.llm_service import merge_fill_empty_only


def test_merge_keeps_original_structure_and_db_values():
    original = (
        '<PayDoc id="id-1" kladr="from-db" active="true">'
        "<Body><Record><Field name=\"\" type=\"string\"/></Record></Body>"
        "</PayDoc>"
    )
    llm_output = (
        '<PayDoc id="ai-id" kladr="123" active="false">'
        "<Body><Record><Field name=\"filled\" type=\"number\"/></Record></Body>"
        "<Extra>hallucinated</Extra>"
        "</PayDoc>"
    )
    protected = frozenset({((), "kladr")})

    result = merge_fill_empty_only(original, llm_output, protected_attrs=protected)
    root = etree.fromstring(result.encode("utf-8"))

    assert root.attrib.get("kladr") == "from-db"
    assert root.attrib.get("id") == "ai-id"
    assert root.attrib.get("active") == "true"
    assert "status" not in root.attrib
    assert root.find("Extra") is None
    field = root.find("Body/Record/Field")
    assert field is not None
    assert field.attrib.get("name") == "filled"
    assert field.attrib.get("type") == "string"


def test_merge_does_not_add_attributes_from_llm():
    original = '<PayDoc id="id-1" kladr="" active="true"/>'
    llm_output = '<PayDoc id="ai-id" kladr="123" active="true" status="active"/>'

    result = merge_fill_empty_only(original, llm_output)
    root = etree.fromstring(result.encode("utf-8"))

    assert "status" not in root.attrib
    assert root.attrib.get("id") == "ai-id"


def test_merge_preserves_already_filled_values():
    original = '<PayDoc id="existing-id" kladr="from-db" active="false"/>'
    llm_output = '<PayDoc id="ai-id" kladr="999" active="true"/>'
    protected = frozenset({((), "kladr")})

    result = merge_fill_empty_only(original, llm_output, protected_attrs=protected)
    root = etree.fromstring(result.encode("utf-8"))

    assert root.attrib.get("kladr") == "from-db"
    assert root.attrib.get("id") == "existing-id"
    assert root.attrib.get("active") == "false"
