"""Tests for config-driven attribute validation rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.attribute_rules_models import AttributeRuleSet
from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef
from app.services import attribute_rules_service as rules_svc


def _ruleset(payload: dict) -> AttributeRuleSet:
    return AttributeRuleSet.model_validate(payload)


@pytest.fixture(autouse=True)
def _clear_cache():
    rules_svc.clear_attribute_rules_cache()
    yield
    rules_svc.clear_attribute_rules_cache()


def test_rules_for_prefers_scoped_over_fallback():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "global-status",
                    "attr": "status",
                    "severity": "warning",
                    "applies_to": ["post_fill"],
                    "checks": [{"type": "enum", "values": ["A", "B"]}],
                },
                {
                    "id": "scoped-status",
                    "element": "PayDoc",
                    "attr": "status",
                    "severity": "error",
                    "applies_to": ["post_fill"],
                    "checks": [{"type": "enum", "values": ["NEW", "ACTIVE"]}],
                },
            ]
        }
    )
    matched = rules_svc.rules_for("PayDoc", "status", ruleset=ruleset, context="post_fill")
    assert [r.id for r in matched] == ["scoped-status", "global-status"]


def test_rules_for_supports_glob_attr_pattern():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "passport-like",
                    "attr": "passport*",
                    "severity": "error",
                    "applies_to": ["git_push"],
                    "checks": [{"type": "not_placeholder"}],
                }
            ]
        }
    )
    assert rules_svc.rules_for("Client", "passportSeries", ruleset=ruleset, context="git_push")
    assert rules_svc.rules_for("Client", "passportNumber", ruleset=ruleset, context="git_push")
    assert not rules_svc.rules_for("Client", "otherField", ruleset=ruleset, context="git_push")


def test_validate_attribute_regex_and_not_placeholder():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "kladr",
                    "element": "PayDoc",
                    "attr": "kladr",
                    "severity": "error",
                    "applies_to": ["git_push"],
                    "checks": [
                        {"type": "regex", "pattern": "^[0-9]{11}$"},
                        {"type": "not_placeholder"},
                    ],
                    "message": "bad kladr",
                }
            ]
        }
    )
    bad = rules_svc.validate_attribute("PayDoc", "kladr", "abc", context="git_push", ruleset=ruleset)
    assert len(bad) == 1
    assert bad[0].severity == "error"
    assert bad[0].message == "bad kladr"

    empty = rules_svc.validate_attribute("PayDoc", "kladr", "", context="git_push", ruleset=ruleset)
    assert empty and empty[0].check_type in {"regex", "not_placeholder"}

    ok = rules_svc.validate_attribute(
        "PayDoc", "kladr", "12345678901", context="git_push", ruleset=ruleset
    )
    assert ok == []


def test_validate_attribute_respects_context_filter():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "only-push",
                    "attr": "id",
                    "severity": "error",
                    "applies_to": ["git_push"],
                    "checks": [{"type": "min_length", "min_length": 5}],
                }
            ]
        }
    )
    assert rules_svc.validate_attribute("PayDoc", "id", "ab", context="post_fill", ruleset=ruleset) == []
    assert rules_svc.validate_attribute("PayDoc", "id", "ab", context="git_push", ruleset=ruleset)


def test_validate_document_groups_errors_and_warnings():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "id-error",
                    "attr": "id",
                    "severity": "error",
                    "applies_to": ["post_fill"],
                    "checks": [{"type": "not_placeholder"}],
                },
                {
                    "id": "status-warn",
                    "attr": "status",
                    "severity": "warning",
                    "applies_to": ["post_fill"],
                    "checks": [{"type": "enum", "values": ["NEW"]}],
                },
            ]
        }
    )
    xml = '<PayDoc id="id-1" status="WRONG"><Header version="1.0"/></PayDoc>'
    report = rules_svc.validate_document(xml, context="post_fill", ruleset=ruleset)
    assert report.has_errors
    assert len(report.errors) == 1
    assert report.errors[0].attr == "id"
    assert len(report.warnings) == 1
    assert report.warnings[0].attr == "status"


def test_length_and_charset_checks():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "code",
                    "attr": "code",
                    "severity": "error",
                    "applies_to": ["git_ai_fill"],
                    "checks": [
                        {"type": "length", "min_length": 3, "max_length": 5},
                        {"type": "charset", "charset": "ABC123"},
                    ],
                }
            ]
        }
    )
    assert rules_svc.validate_attribute("X", "code", "AB", context="git_ai_fill", ruleset=ruleset)
    assert rules_svc.validate_attribute("X", "code", "ABX", context="git_ai_fill", ruleset=ruleset)
    assert rules_svc.validate_attribute("X", "code", "A1B", context="git_ai_fill", ruleset=ruleset) == []


def test_deny_copy_patterns():
    ruleset = _ruleset({"deny_copy": ["inn", "passport*", "accountNumber"]})
    assert rules_svc.is_deny_copy("inn", ruleset)
    assert rules_svc.is_deny_copy("passportSeries", ruleset)
    assert rules_svc.is_deny_copy("accountNumber", ruleset)
    assert not rules_svc.is_deny_copy("status", ruleset)
    assert not rules_svc.is_deny_copy("", ruleset)


def test_cross_field_mapped_eq():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "currency-code",
                    "element": "account",
                    "attr": "currency-code",
                    "severity": "error",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {
                            "type": "cross_field",
                            "op": "mapped_eq",
                            "other": "currency",
                            "map": {"RUB": "643", "USD": "840"},
                        }
                    ],
                }
            ]
        }
    )
    ok = rules_svc.validate_attribute(
        "account", "currency-code", "643", context="post_fill", ruleset=ruleset,
        siblings={"currency": "RUB", "currency-code": "643"},
    )
    assert ok == []

    bad = rules_svc.validate_attribute(
        "account", "currency-code", "840", context="post_fill", ruleset=ruleset,
        siblings={"currency": "RUB", "currency-code": "840"},
    )
    assert len(bad) == 1

    # Sibling has no entry in the map: not applicable, must not fail.
    not_applicable = rules_svc.validate_attribute(
        "account", "currency-code", "anything", context="post_fill", ruleset=ruleset,
        siblings={"currency": "CNY", "currency-code": "anything"},
    )
    assert not_applicable == []


def test_cross_field_regex_if_only_applies_when_sibling_matches():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "contact-value-email",
                    "element": "contact",
                    "attr": "value",
                    "severity": "warning",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {
                            "type": "cross_field",
                            "op": "regex_if",
                            "other": "type",
                            "when": "email",
                            "pattern": "^[^@]+@[^@]+$",
                        }
                    ],
                }
            ]
        }
    )
    # type=phone: the email regex_if check doesn't apply, no failure even
    # though "value" isn't an email at all.
    phone_ok = rules_svc.validate_attribute(
        "contact", "value", "+79991234567", context="post_fill", ruleset=ruleset,
        siblings={"type": "phone", "value": "+79991234567"},
    )
    assert phone_ok == []

    # type=email with a bad value: must fail.
    email_bad = rules_svc.validate_attribute(
        "contact", "value", "not-an-email", context="post_fill", ruleset=ruleset,
        siblings={"type": "email", "value": "not-an-email"},
    )
    assert len(email_bad) == 1

    # type=email with a good value: passes.
    email_ok = rules_svc.validate_attribute(
        "contact", "value", "a@b.com", context="post_fill", ruleset=ruleset,
        siblings={"type": "email", "value": "a@b.com"},
    )
    assert email_ok == []


def test_cross_field_required_if_and_empty_if():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "raw-required",
                    "element": "address",
                    "attr": "raw",
                    "severity": "warning",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {"type": "cross_field", "op": "required_if", "other": "address-type", "when": "raw"}
                    ],
                },
                {
                    "id": "raw-empty",
                    "element": "address",
                    "attr": "raw",
                    "severity": "warning",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {"type": "cross_field", "op": "empty_if", "other": "address-type", "when": "structured"}
                    ],
                },
            ]
        }
    )
    assert rules_svc.validate_attribute(
        "address", "raw", "", context="post_fill", ruleset=ruleset,
        siblings={"address-type": "raw", "raw": ""},
    )
    assert rules_svc.validate_attribute(
        "address", "raw", "some raw text", context="post_fill", ruleset=ruleset,
        siblings={"address-type": "structured", "raw": "some raw text"},
    )
    assert rules_svc.validate_attribute(
        "address", "raw", "", context="post_fill", ruleset=ruleset,
        siblings={"address-type": "structured", "raw": ""},
    ) == []


def test_validate_document_passes_real_sibling_attributes():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "contact-value-email",
                    "element": "contact",
                    "attr": "value",
                    "severity": "error",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {
                            "type": "cross_field",
                            "op": "regex_if",
                            "other": "type",
                            "when": "email",
                            "pattern": "^[^@]+@[^@]+$",
                        }
                    ],
                }
            ]
        }
    )
    xml = (
        '<root>'
        '<contact type="email" value="bad-value"/>'
        '<contact type="phone" value="also-not-email"/>'
        "</root>"
    )
    report = rules_svc.validate_document(xml, context="post_fill", ruleset=ruleset)
    assert len(report.errors) == 1
    assert report.errors[0].value == "bad-value"


def test_cross_field_model_validation_requires_op_and_other():
    with pytest.raises(Exception):
        AttributeRuleSet.model_validate(
            {"rules": [{"id": "x", "attr": "value", "checks": [{"type": "cross_field"}]}]}
        )
    with pytest.raises(Exception):
        AttributeRuleSet.model_validate(
            {
                "rules": [
                    {
                        "id": "x",
                        "attr": "value",
                        "checks": [{"type": "cross_field", "op": "eq"}],
                    }
                ]
            }
        )


def test_cross_field_regex_if_requires_pattern_and_when():
    with pytest.raises(Exception):
        AttributeRuleSet.model_validate(
            {
                "rules": [
                    {
                        "id": "x",
                        "attr": "value",
                        "checks": [
                            {"type": "cross_field", "op": "regex_if", "other": "type"}
                        ],
                    }
                ]
            }
        )


def test_cross_field_mapped_eq_requires_map():
    with pytest.raises(Exception):
        AttributeRuleSet.model_validate(
            {
                "rules": [
                    {
                        "id": "x",
                        "attr": "value",
                        "checks": [
                            {"type": "cross_field", "op": "mapped_eq", "other": "type"}
                        ],
                    }
                ]
            }
        )


def test_invalid_regex_check_fails_model_validation():
    """A malformed regex must fail fast at rule-parse time, not at validate() time."""
    with pytest.raises(Exception):
        AttributeRuleSet.model_validate(
            {
                "rules": [
                    {
                        "id": "broken",
                        "attr": "x",
                        "checks": [{"type": "regex", "pattern": "["}],
                    }
                ]
            }
        )


def test_load_ruleset_skips_only_the_bad_rule(tmp_path: Path):
    """One malformed rule in the config file must not drop every other rule."""
    payload = {
        "version": 1,
        "rules": [
            {
                "id": "good-one",
                "attr": "id",
                "severity": "warning",
                "applies_to": ["post_fill"],
                "checks": [{"type": "min_length", "min_length": 1}],
            },
            {
                "id": "bad-regex",
                "attr": "kladr",
                "checks": [{"type": "regex", "pattern": "("}],
            },
        ],
    }
    path = tmp_path / "attribute_rules.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = rules_svc._load_ruleset_from_path(path)
    assert [r.id for r in loaded.rules] == ["good-one"]


def test_load_attribute_rules_from_file_and_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rules_path = tmp_path / "attribute_rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [
                    {
                        "id": "t",
                        "attr": "id",
                        "severity": "warning",
                        "applies_to": ["post_fill"],
                        "checks": [{"type": "min_length", "min_length": 1}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rules_svc, "ATTRIBUTE_RULES_FILE", rules_path)
    monkeypatch.setattr(rules_svc, "ATTRIBUTE_RULES_EXAMPLE", tmp_path / "missing.json")
    loaded = rules_svc.load_attribute_rules(force_reload=True)
    assert len(loaded.rules) == 1
    assert loaded.rules[0].id == "t"

    # Cache hit: same object returned without re-reading the file.
    again = rules_svc.load_attribute_rules()
    assert again is loaded


def test_format_push_rule_error():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "id-error",
                    "attr": "id",
                    "severity": "error",
                    "applies_to": ["git_push"],
                    "checks": [{"type": "not_placeholder"}],
                    "message": "id placeholder",
                }
            ]
        }
    )
    report = rules_svc.validate_document('<PayDoc id="id-1"/>', context="git_push", ruleset=ruleset)
    text = rules_svc.format_push_rule_error(report)
    assert text is not None
    assert "id placeholder" in text
    assert rules_svc.format_push_rule_error(rules_svc.DocumentValidationReport()) is None


def test_serialize_push_warnings_and_ack_detail():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "status-warn",
                    "attr": "status",
                    "severity": "warning",
                    "applies_to": ["git_push"],
                    "checks": [{"type": "enum", "values": ["NEW"]}],
                    "message": "unexpected status",
                }
            ]
        }
    )
    report = rules_svc.validate_document(
        '<PayDoc status="WRONG"/>',
        context="git_push",
        ruleset=ruleset,
    )
    items = rules_svc.serialize_push_warnings(report)
    assert len(items) == 1
    assert items[0]["attr"] == "status"
    assert items[0]["location"] == "PayDoc@status"
    assert items[0]["message"] == "unexpected status"

    detail = rules_svc.push_warnings_ack_detail(report)
    assert detail["code"] == rules_svc.PUSH_WARNINGS_REQUIRE_ACK
    assert detail["warning_count"] == 1
    assert detail["warnings"] == items


def test_validate_with_schema_attr_def_for_placeholder():
    schema = DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={
                    "active": AttributeDef(
                        name="active",
                        attr_type="ENUM",
                        default_decl="#REQUIRED",
                        allowed_values=["true", "false"],
                    )
                },
            )
        }
    )
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "active-real",
                    "element": "PayDoc",
                    "attr": "active",
                    "severity": "error",
                    "applies_to": ["git_push"],
                    "checks": [{"type": "not_placeholder"}],
                }
            ]
        }
    )
    # Empty enum is a placeholder; a value from the DTD pool is already filled.
    report = rules_svc.validate_document('<PayDoc active=""/>', schema, context="git_push", ruleset=ruleset)
    assert report.has_errors

    report_ok = rules_svc.validate_document('<PayDoc active="true"/>', schema, context="git_push", ruleset=ruleset)
    assert not report_ok.has_errors


def test_parent_name_gates_check():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "series",
                    "element": "cs:attribute",
                    "attr": "value",
                    "severity": "error",
                    "applies_to": ["git_push"],
                    "checks": [
                        {
                            "type": "cross_field",
                            "op": "regex_if",
                            "other": "name",
                            "when": "CardSeries",
                            "parent_name": "Passport",
                            "pattern": "^[0-9]{4}$",
                        }
                    ],
                }
            ]
        }
    )
    xml_bad = (
        '<root xmlns:cs="http://example.com/cs">'
        '<cs:attribute name="Passport">'
        '<cs:attribute name="CardSeries" value="a"/>'
        "</cs:attribute></root>"
    )
    xml_elsewhere = (
        '<root xmlns:cs="http://example.com/cs">'
        '<cs:attribute name="Other">'
        '<cs:attribute name="CardSeries" value="a"/>'
        "</cs:attribute></root>"
    )
    bad = rules_svc.validate_document(xml_bad, context="git_push", ruleset=ruleset)
    assert len(bad.errors) == 1
    skipped = rules_svc.validate_document(xml_elsewhere, context="git_push", ruleset=ruleset)
    assert not skipped.has_errors


def test_rules_for_matches_clark_notation_to_prefixed_element():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "cs-val",
                    "element": "cs:attribute",
                    "attr": "value",
                    "severity": "error",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {
                            "type": "cross_field",
                            "op": "regex_if",
                            "other": "name",
                            "when": "Inn",
                            "pattern": "^[0-9]{12}$",
                        }
                    ],
                }
            ]
        }
    )
    clark = "{http://example.com/cs}attribute"
    matched = rules_svc.rules_for(clark, "value", ruleset=ruleset, context="post_fill")
    assert [r.id for r in matched] == ["cs-val"]

    ok = rules_svc.validate_attribute(
        clark,
        "value",
        "123456789189",
        context="post_fill",
        ruleset=ruleset,
        siblings={"name": "Inn", "value": "123456789189"},
    )
    assert ok == []

    bad = rules_svc.validate_attribute(
        clark,
        "value",
        "2700001989072700",
        context="post_fill",
        ruleset=ruleset,
        siblings={"name": "Inn", "value": "2700001989072700"},
    )
    assert len(bad) == 1


_CS_PERSON_XML = """
<root xmlns:cs="http://example.com/cs">
  <cs:object type="person">
    <cs:attribute name="NotAddContract" value="true"/>
    <cs:attribute name="SystemRegNumber" value="213787"/>
    <cs:attribute name="Inn" value="123456789189"/>
    <cs:attribute name="LastName" value="Зайцев"/>
    <cs:attribute name="FirstName" value="Никита"/>
    <cs:attribute name="MiddleName" value="Иванович"/>
    <cs:attribute name="birth-date" value="1986-12-16"/>
    <cs:attribute name="citizenship" value="Россия"/>
    <cs:attribute name="Key">
      <cs:attribute name="SubjectDn" value="CN=zaytsev_ni, OU=lite client 724811, O=faktura.lite, L=Novosibirsk, C=RU"/>
      <cs:attribute name="IssuerDn" value="CN=Class 2 CA, OU=CAs, O=FTC, C=RU"/>
    </cs:attribute>
    <cs:attribute name="Addresses">
      <cs:attribute name="Address" value="Legal">
        <cs:attribute name="Index" value="408845"/>
        <cs:attribute name="Area" value=""/>
        <cs:attribute name="City" value=""/>
        <cs:attribute name="Street" value="проспект30"/>
      </cs:attribute>
    </cs:attribute>
    <cs:attribute name="Passport">
      <cs:attribute name="CardSeries" value="5009"/>
      <cs:attribute name="CardNumber" value="345543"/>
      <cs:attribute name="CardIssueDate" value="2003-08-20"/>
      <cs:attribute name="CardIssuer" value="УФМС Ельцовка"/>
      <cs:attribute name="UnitCode" value="777-888"/>
      <cs:attribute name="CardType" value="Паспорт"/>
    </cs:attribute>
    <cs:attribute name="IdentStage" value="full"/>
    <cs:attribute name="Contacts">
      <cs:attribute name="Contact" value="Phone">
        <cs:attribute name="ContactInfo" value="56765"/>
      </cs:attribute>
    </cs:attribute>
    <cs:attribute name="CorpSender">
      <cs:attribute name="Name" value="РКЦ ЛУЗА"/>
      <cs:attribute name="Inn" value="2700001989072700"/>
      <cs:attribute name="Bic" value="043388000"/>
    </cs:attribute>
  </cs:object>
</root>
"""


def test_cs_attribute_nested_leaf_names_on_sample_person():
    ruleset = rules_svc._load_ruleset_from_path(rules_svc.ATTRIBUTE_RULES_FILE)
    report = rules_svc.validate_document(_CS_PERSON_XML, context="post_fill", ruleset=ruleset)

    inn_errors = [v for v in report.errors if v.rule_id == "cs-inn-org"]
    assert len(inn_errors) == 1
    assert inn_errors[0].value == "2700001989072700"
    assert inn_errors[0].element == "cs:attribute"

    assert not any(v.value == "123456789189" for v in report.errors)
    assert not any(v.value == "Россия" for v in report.errors + report.warnings)
    assert not any(v.value == "full" for v in report.errors + report.warnings)
    assert not any(v.value == "Legal" for v in report.errors + report.warnings)
    assert not any(v.value == "Phone" for v in report.errors + report.warnings)

    contact_warn = [v for v in report.warnings if v.rule_id == "cs-contact-info"]
    assert len(contact_warn) == 1
    assert contact_warn[0].value == "56765"


def test_cs_passport_series_rejects_single_letter_on_git_push():
    ruleset = rules_svc._load_ruleset_from_path(rules_svc.ATTRIBUTE_RULES_FILE)
    for series in ("a", "A"):
        xml = (
            '<root xmlns:cs="http://example.com/cs">'
            '<cs:object type="person">'
            f'<cs:attribute name="Passport">'
            f'<cs:attribute name="CardSeries" value="{series}"/>'
            "</cs:attribute></cs:object></root>"
        )
        report = rules_svc.validate_document(xml, context="git_push", ruleset=ruleset)
        assert any(v.rule_id == "cs-passport-rf" and v.value == series for v in report.errors), series


def test_cs_attribute_leaf_name_not_dotted_path():
    ruleset = _ruleset(
        {
            "rules": [
                {
                    "id": "dotted",
                    "element": "cs:attribute",
                    "attr": "value",
                    "severity": "error",
                    "applies_to": ["post_fill"],
                    "checks": [
                        {
                            "type": "cross_field",
                            "op": "regex_if",
                            "other": "name",
                            "when": "Key.SubjectDn",
                            "pattern": "^FAIL$",
                        }
                    ],
                }
            ]
        }
    )
    xml = (
        '<root xmlns:cs="http://example.com/cs">'
        '<cs:attribute name="SubjectDn" value="CN=zaytsev_ni, C=RU"/>'
        "</root>"
    )
    report = rules_svc.validate_document(xml, context="post_fill", ruleset=ruleset)
    assert not report.has_errors
