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
