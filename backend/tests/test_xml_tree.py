"""Tests for shared XML tree helpers."""

from app.core.dtd_models import AttributeDef
from app.core.xml_tree import is_fillable_attribute_value


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
