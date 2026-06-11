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
    assert root.attrib.get("active") == "false"
    assert root.find("Extra") is None
    field = root.find("Body/Record/Field")
    assert field is not None
    assert field.attrib.get("name") == "filled"
    assert field.attrib.get("type") == "number"
