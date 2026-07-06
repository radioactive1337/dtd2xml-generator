"""Tests for manual field override application."""

from __future__ import annotations

from app.services.field_override_service import FieldOverride, apply_field_overrides

SAMPLE_XML = """\
<PayDoc>
  <Body>
    <client inn="" name=""/>
    <client inn="" name=""/>
  </Body>
  <Body>
    <client inn="" name=""/>
  </Body>
</PayDoc>
"""


def test_apply_field_overrides_sets_value_at_path():
    override = FieldOverride(
        target_path="PayDoc.Body.client",
        xml_attr="inn",
        value="7707083893",
    )
    xml_out, protected, warnings = apply_field_overrides(SAMPLE_XML, [override])

    assert warnings == []
    assert xml_out.count('inn="7707083893"') == 1
    assert len(protected) == 1


def test_apply_field_overrides_wins_over_existing_value():
    override = FieldOverride(
        target_path="PayDoc.Body.client[0]",
        xml_attr="inn",
        value="7707083893",
    )
    xml_with_value = SAMPLE_XML.replace('inn=""', 'inn="old"', 1)
    xml_out, protected, warnings = apply_field_overrides(xml_with_value, [override])

    assert warnings == []
    assert 'inn="7707083893"' in xml_out
    assert 'inn="old"' not in xml_out
    assert len(protected) == 1


def test_apply_field_overrides_path_not_found_warns():
    override = FieldOverride(
        target_path="PayDoc.Missing.client",
        xml_attr="inn",
        value="7707083893",
    )
    xml_out, protected, warnings = apply_field_overrides(SAMPLE_XML, [override])

    assert 'inn="7707083893"' not in xml_out
    assert protected == frozenset()
    assert len(warnings) == 1
    assert "path not found" in warnings[0]


def test_apply_field_overrides_accepts_at_prefix_on_attr():
    override = FieldOverride(
        target_path="PayDoc.Body.client",
        xml_attr="@inn",
        value="7707083893",
    )
    xml_out, _, warnings = apply_field_overrides(SAMPLE_XML, [override])

    assert warnings == []
    assert 'inn="7707083893"' in xml_out


def test_apply_field_overrides_empty_list_is_noop():
    xml_out, protected, warnings = apply_field_overrides(SAMPLE_XML, [])

    assert xml_out == SAMPLE_XML
    assert protected == frozenset()
    assert warnings == []
