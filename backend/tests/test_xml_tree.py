"""Tests for shared XML tree helpers."""

from lxml import etree

from app.core.dtd_models import AttributeDef
from app.core.xml_tree import element_dot_path, is_fillable_attribute_value


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


def test_enum_first_value_is_fillable():
    attr_def = AttributeDef(
        name="type",
        attr_type="ENUM",
        default_decl="#REQUIRED",
        allowed_values=["string", "number", "date"],
    )
    assert is_fillable_attribute_value("string", attr_def=attr_def)
    assert not is_fillable_attribute_value("number", attr_def=attr_def)
