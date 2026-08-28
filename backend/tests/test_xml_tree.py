"""Tests for shared XML tree helpers."""

from lxml import etree

from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef
from app.core.xml_tree import (
    AttributeFillStats,
    compute_attribute_fill_stats,
    element_dot_path,
    git_push_attribute_fill_error,
    is_fillable_attribute_value,
    prefill_empty_enums,
)


def _paydoc_schema() -> DTDSchema:
    return DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="(Body)",
                content_model=ContentNode(kind="SEQUENCE", children=[ContentNode(kind="REF", ref="Body")]),
                attributes={
                    "id": AttributeDef(name="id", attr_type="ID", default_decl="#REQUIRED"),
                    "kladr": AttributeDef(name="kladr", attr_type="CDATA", default_decl="#IMPLIED"),
                    "active": AttributeDef(name="active", attr_type="CDATA", default_decl="#IMPLIED"),
                },
            ),
            "Body": ElementDef(
                name="Body",
                content_raw="(Field)",
                content_model=ContentNode(kind="SEQUENCE", children=[ContentNode(kind="REF", ref="Field")]),
                attributes={},
            ),
            "Field": ElementDef(
                name="Field",
                content_raw="#PCDATA",
                content_model=ContentNode(kind="PCDATA"),
                attributes={
                    "name": AttributeDef(name="name", attr_type="CDATA", default_decl="#IMPLIED"),
                    "type": AttributeDef(
                        name="type",
                        attr_type="ENUM",
                        default_decl="#REQUIRED",
                        allowed_values=["string", "number"],
                    ),
                },
            ),
        }
    )


def test_element_dot_path_uses_sibling_index():
    xml = "<PayDoc><Body><Record/><Record/></Body></PayDoc>"
    root = etree.fromstring(xml.encode("utf-8"))
    records = root.findall("Body/Record")

    assert element_dot_path(records[0]) == "PayDoc.Body.Record[0]"
    assert element_dot_path(records[1]) == "PayDoc.Body.Record[1]"


def test_empty_and_id_placeholder_are_fillable():
    assert is_fillable_attribute_value("")
    assert is_fillable_attribute_value("id-1")


def test_real_values_are_not_fillable_without_schema():
    assert not is_fillable_attribute_value("from-db")
    assert not is_fillable_attribute_value("false")


def test_enum_pool_values_are_not_placeholders():
    attr_def = AttributeDef(
        name="type",
        attr_type="ENUM",
        default_decl="#REQUIRED",
        allowed_values=["string", "number", "date"],
    )
    assert not is_fillable_attribute_value("string", attr_def=attr_def)
    assert not is_fillable_attribute_value("number", attr_def=attr_def)
    assert is_fillable_attribute_value("", attr_def=attr_def)


def test_compute_attribute_fill_stats_counts_placeholders_as_unfilled():
    xml = (
        '<PayDoc id="id-1" kladr="" active="true">'
        '<Body><Field name="" type="string"/></Body>'
        "</PayDoc>"
    )
    stats = compute_attribute_fill_stats(xml, _paydoc_schema())
    # id-1, empty kladr, empty name are placeholders; active="true" (CDATA)
    # and type="string" (enum pool value) count as filled.
    assert stats == AttributeFillStats(total=5, filled=2)
    assert stats.fill_percent == 40.0


def test_compute_attribute_fill_stats_empty_document_has_full_rate():
    stats = compute_attribute_fill_stats("<PayDoc/>", _paydoc_schema())
    assert stats.total == 0
    assert stats.fill_rate == 1.0


def test_git_push_attribute_fill_error_blocks_below_threshold():
    xml = '<PayDoc id="id-1" kladr="" active=""><Body/></PayDoc>'
    error = git_push_attribute_fill_error(xml, _paydoc_schema())
    assert error is not None
    assert "15%" in error
    assert "заполнено" in error


def test_git_push_attribute_fill_error_allows_sufficient_fill():
    xml = (
        '<PayDoc id="real-id" kladr="7700000000000" active="true">'
        '<Body><Field name="amount" type="number"/></Body>'
        "</PayDoc>"
    )
    assert git_push_attribute_fill_error(xml, _paydoc_schema()) is None


def test_git_push_attribute_fill_error_exact_threshold():
    xml = '<PayDoc id="real-id" kladr="filled" active="" extra=""/>'
    stats = compute_attribute_fill_stats(xml, None)
    assert stats.total == 4
    assert stats.filled == 2
    assert stats.fill_rate == 0.5
    assert git_push_attribute_fill_error(xml, None) is None


def test_git_push_attribute_fill_error_blocks_zero_fill():
    xml = '<PayDoc id="id-1" kladr="" active="" extra=""/>'
    assert git_push_attribute_fill_error(xml, None) is not None


def test_prefill_empty_enums_assigns_allowed_value():
    xml = '<PayDoc id="id-1"><Body><Field name="amount" type=""/></Body></PayDoc>'
    new_xml, count = prefill_empty_enums(xml, _paydoc_schema())
    assert count == 1
    root = etree.fromstring(new_xml.encode("utf-8"))
    field = root.find("Body/Field")
    assert field.get("type") in {"string", "number"}


def test_prefill_empty_enums_leaves_in_pool_value_untouched():
    xml = '<PayDoc id="id-1"><Body><Field name="amount" type="number"/></Body></PayDoc>'
    new_xml, count = prefill_empty_enums(xml, _paydoc_schema())
    assert count == 0
    assert new_xml == xml


def test_prefill_empty_enums_never_touches_non_enum_attrs():
    xml = '<PayDoc id="id-1" kladr="" active=""><Body><Field name="" type="string"/></Body></PayDoc>'
    new_xml, count = prefill_empty_enums(xml, _paydoc_schema())
    assert count == 0
    root = etree.fromstring(new_xml.encode("utf-8"))
    assert root.get("kladr") == ""
    assert root.get("active") == ""
    assert root.find("Body/Field").get("name") == ""


def test_prefill_empty_enums_returns_input_unchanged_without_schema():
    xml = '<PayDoc id="id-1"><Body><Field name="amount" type=""/></Body></PayDoc>'
    new_xml, count = prefill_empty_enums(xml, None)
    assert count == 0
    assert new_xml == xml


def test_prefill_empty_enums_fills_single_value_enum():
    schema = DTDSchema(
        elements={
            "Doc": ElementDef(
                name="Doc",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={
                    "kind": AttributeDef(
                        name="kind",
                        attr_type="ENUM",
                        default_decl="#REQUIRED",
                        allowed_values=["fixed-value"],
                    ),
                },
            ),
        }
    )
    xml = '<Doc kind=""/>'
    new_xml, count = prefill_empty_enums(xml, schema)
    assert count == 1
    root = etree.fromstring(new_xml.encode("utf-8"))
    assert root.get("kind") == "fixed-value"
