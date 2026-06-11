"""Tests for hybrid LLM merge behaviour."""

from lxml import etree

from app.services.llm_service import merge_fill_empty_only


def test_merge_keeps_original_structure_and_db_values():
    original = (
        '<PayDoc id="from-db" kladr="" active="">'
        "<Body><Record><Field type=\"\"/></Record></Body>"
        "</PayDoc>"
    )
    llm_output = (
        '<PayDoc id="ai-id" kladr="123" active="true">'
        "<Body><Record><Field type=\"string\"/></Record></Body>"
        "<Extra>hallucinated</Extra>"
        "</PayDoc>"
    )

    result = merge_fill_empty_only(original, llm_output)
    root = etree.fromstring(result.encode("utf-8"))

    assert root.attrib.get("id") == "from-db"
    assert root.attrib.get("kladr") == "123"
    assert root.attrib.get("active") == "true"
    assert root.find("Extra") is None
    field = root.find("Body/Record/Field")
    assert field is not None
    assert field.attrib.get("type") == "string"
