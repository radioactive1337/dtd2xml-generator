"""Config-driven attribute validation rules.

Rules live in ``config/attribute_rules.json`` and gate Git push quality as well as
post-fill / git-AI fill results. Scoped rules (element + attr) take priority over
global fallbacks that match by attribute name only.

Each rule is validated independently when the file is loaded: a single malformed
rule (e.g. a bad regex, an ops typo) is logged and skipped rather than discarding
every other rule in the file.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree

from app.config import CONFIG_DIR
from app.core.attribute_rules_models import (
    AttributeRule,
    AttributeRuleSet,
    RuleCheck,
    RuleContext,
)
from app.core.dtd_models import DTDSchema
from app.core.xml_tree import (
    element_dot_path,
    is_fillable_attribute_value,
    prefixed_element_name,
)

logger = logging.getLogger(__name__)

ATTRIBUTE_RULES_FILE = CONFIG_DIR / "attribute_rules.json"
ATTRIBUTE_RULES_EXAMPLE = CONFIG_DIR / "attribute_rules.json.example"

_rules_cache: tuple[float, AttributeRuleSet] | None = None


@dataclass(frozen=True)
class RuleViolation:
    rule_id: str
    element: str
    attr: str
    path: str
    value: str
    severity: str
    message: str
    check_type: str


@dataclass
class DocumentValidationReport:
    errors: list[RuleViolation] = field(default_factory=list)
    warnings: list[RuleViolation] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def messages(self, *, include_warnings: bool = True) -> list[str]:
        items = list(self.errors)
        if include_warnings:
            items.extend(self.warnings)
        return [v.message for v in items]


def _empty_ruleset() -> AttributeRuleSet:
    return AttributeRuleSet()


def _parse_rules(raw_rules: object, *, source: str) -> list[AttributeRule]:
    """Validate each rule independently so one bad rule doesn't drop all rules."""
    if not isinstance(raw_rules, list):
        if raw_rules is not None:
            logger.warning("Attribute rules file %s: 'rules' must be a list", source)
        return []

    parsed: list[AttributeRule] = []
    for index, item in enumerate(raw_rules):
        rule_id = item.get("id") if isinstance(item, dict) else None
        try:
            parsed.append(AttributeRule.model_validate(item))
        except Exception as exc:
            logger.warning(
                "Skipping invalid attribute rule #%d (id=%s) in %s: %s",
                index,
                rule_id or "?",
                source,
                exc,
            )
    return parsed


def _load_ruleset_from_path(path: Path) -> AttributeRuleSet:
    if not path.is_file():
        return _empty_ruleset()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load attribute rules from %s: %s", path, exc)
        return _empty_ruleset()
    if not isinstance(raw, dict):
        logger.warning("Attribute rules file %s must contain a JSON object", path)
        return _empty_ruleset()

    version = raw.get("version", 1) if isinstance(raw.get("version", 1), int) else 1
    deny_copy = raw.get("deny_copy", [])
    if not isinstance(deny_copy, list) or not all(isinstance(p, str) for p in deny_copy):
        logger.warning("Attribute rules file %s: 'deny_copy' must be a list of strings", path)
        deny_copy = []

    rules = _parse_rules(raw.get("rules", []), source=str(path))
    return AttributeRuleSet(version=version, deny_copy=deny_copy, rules=rules)


def load_attribute_rules(*, force_reload: bool = False) -> AttributeRuleSet:
    """Load and cache ``config/attribute_rules.json`` (mtime-invalidated)."""
    global _rules_cache

    path = ATTRIBUTE_RULES_FILE
    if not path.is_file() and ATTRIBUTE_RULES_EXAMPLE.is_file():
        path = ATTRIBUTE_RULES_EXAMPLE

    if not path.is_file():
        _rules_cache = None
        return _empty_ruleset()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        _rules_cache = None
        return _empty_ruleset()

    if not force_reload and _rules_cache is not None and _rules_cache[0] == mtime:
        return _rules_cache[1]

    ruleset = _load_ruleset_from_path(path)
    _rules_cache = (mtime, ruleset)
    return ruleset


def clear_attribute_rules_cache() -> None:
    """Reset the in-memory rules cache (for tests)."""
    global _rules_cache
    _rules_cache = None


def _matches_pattern(name: str, pattern: str) -> bool:
    return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name.lower(), pattern.lower())


def _local_element_name(name: str) -> str:
    """Strip Clark ``{uri}local`` or DTD ``prefix:local`` down to the local name."""
    text = (name or "").strip()
    if text.startswith("{") and "}" in text:
        return text.split("}", 1)[1]
    if ":" in text:
        return text.split(":", 1)[1]
    return text


def _element_matches_rule(rule_element: str, actual: str) -> bool:
    """Match a rule's ``element`` against a parsed tag, including namespaces.

    ``cs:attribute`` must apply to ``{http://…}attribute`` (lxml Clark notation)
    and to a reconstructed prefixed name from the element's ``nsmap``.
    """
    if not rule_element or not actual:
        return False
    if rule_element == actual:
        return True
    rule_local = _local_element_name(rule_element)
    actual_local = _local_element_name(actual)
    return bool(rule_local) and rule_local == actual_local


def attribute_sibling_context(el: etree._Element) -> dict[str, str]:
    """Own attributes plus ``parent.*`` so checks can see the parent ``cs:attribute``."""
    ctx = dict(el.attrib)
    parent = el.getparent()
    if parent is None or not isinstance(parent.tag, str):
        return ctx
    ctx["parent.__element__"] = prefixed_element_name(parent)
    for key, val in parent.attrib.items():
        if key == "xmlns" or key.startswith("xmlns:"):
            continue
        ctx[f"parent.{key}"] = val
    return ctx


def _parent_context_mismatch(check: RuleCheck, siblings: dict[str, str] | None) -> bool:
    """True when a parent_* constraint is set and the parent does not match."""
    ctx = siblings or {}
    if check.parent_element is not None:
        actual = (ctx.get("parent.__element__") or "").strip()
        if not _element_matches_rule(check.parent_element, actual):
            return True
    if check.parent_name is not None:
        if (ctx.get("parent.name") or "").strip() != check.parent_name:
            return True
    if check.parent_value is not None:
        if (ctx.get("parent.value") or "").strip() != check.parent_value:
            return True
    return False


def is_deny_copy(attr: str, ruleset: AttributeRuleSet | None = None) -> bool:
    """Return True when *attr* must never be copied as-is from Git references."""
    ruleset = ruleset if ruleset is not None else load_attribute_rules()
    name = (attr or "").strip()
    if not name:
        return False
    return any(_matches_pattern(name, pattern) for pattern in ruleset.deny_copy)


def rules_for(
    element: str,
    attr: str,
    *,
    ruleset: AttributeRuleSet | None = None,
    context: RuleContext | None = None,
) -> list[AttributeRule]:
    """Return matching rules: scoped (element+attr) first, then global by attr name.

    ``attr`` on a rule may be a glob pattern (e.g. ``"passport*"``).
    ``element`` matches the DTD name (``cs:attribute``), the local name, or
    lxml Clark notation ``{uri}attribute``.
    """
    ruleset = ruleset if ruleset is not None else load_attribute_rules()
    elem = (element or "").strip()
    attr_name = (attr or "").strip()
    if not attr_name:
        return []

    scoped: list[AttributeRule] = []
    fallback: list[AttributeRule] = []
    for rule in ruleset.rules:
        if not _matches_pattern(attr_name, rule.attr):
            continue
        if context is not None and context not in rule.applies_to:
            continue
        if rule.element:
            if _element_matches_rule(rule.element, elem):
                scoped.append(rule)
        else:
            fallback.append(rule)

    return scoped + fallback


@lru_cache(maxsize=256)
def _compiled_regex(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _cross_field_fails(check: RuleCheck, value: str, siblings: dict[str, str]) -> bool:
    """Compare *value* against a sibling attribute on the same element.

    Deliberately a fixed set of ops instead of an eval'd expression -- see
    ``RuleCheck.op`` for the supported comparisons.
    """
    this_val = value.strip()
    other_val = (siblings.get(check.other or "") or "").strip()

    if check.op == "eq":
        return this_val != other_val
    if check.op == "ne":
        return this_val == other_val
    if check.op == "mapped_eq":
        expected = check.map.get(other_val)
        return expected is not None and this_val != expected
    if check.op == "regex_if":
        if other_val != check.when:
            return False
        assert check.pattern is not None
        return _compiled_regex(check.pattern).fullmatch(this_val) is None
    if check.op == "required_if":
        if other_val != check.when:
            return False
        return not this_val
    if check.op == "empty_if":
        if other_val != check.when:
            return False
        return bool(this_val)
    return False


def _check_fails(
    check: RuleCheck, value: str, *, attr_def=None, siblings: dict[str, str] | None = None
) -> bool:
    if _parent_context_mismatch(check, siblings):
        return False
    stripped = value.strip()
    if check.type == "regex":
        assert check.pattern is not None
        try:
            return _compiled_regex(check.pattern).fullmatch(stripped) is None
        except re.error:
            # Defense in depth: RuleCheck already validates the pattern compiles
            # at config-load time, so this should be unreachable in practice.
            logger.error("Regex check has an uncompilable pattern %r", check.pattern)
            return False
    if check.type == "enum":
        return stripped not in check.values
    if check.type == "not_placeholder":
        return is_fillable_attribute_value(stripped, attr_def=attr_def)
    if check.type == "charset":
        assert check.charset is not None
        allowed = set(check.charset)
        return any(ch not in allowed for ch in stripped)
    if check.type in {"length", "min_length", "max_length"}:
        length = len(stripped)
        if check.min_length is not None and length < check.min_length:
            return True
        if check.max_length is not None and length > check.max_length:
            return True
        return False
    if check.type == "cross_field":
        return _cross_field_fails(check, value, siblings or {})
    return False


def _default_message(rule: AttributeRule, check: RuleCheck, value: str) -> str:
    if rule.message:
        return rule.message
    preview = value if len(value) <= 40 else value[:37] + "…"
    return (
        f"Rule '{rule.id}' failed ({check.type}) for "
        f"{rule.element or '*'}@{rule.attr}={preview!r}"
    )


def validate_attribute(
    element: str,
    attr: str,
    value: str,
    *,
    context: RuleContext,
    path: str = "",
    attr_def=None,
    ruleset: AttributeRuleSet | None = None,
    siblings: dict[str, str] | None = None,
) -> list[RuleViolation]:
    """Validate a single attribute value against applicable rules for *context*.

    ``siblings`` are the other attributes on the same element (for
    ``cross_field`` checks); pass the element's own current ``attrib`` dict.
    """
    ruleset = ruleset if ruleset is not None else load_attribute_rules()
    violations: list[RuleViolation] = []
    for rule in rules_for(element, attr, ruleset=ruleset, context=context):
        for check in rule.checks:
            if not _check_fails(check, value, attr_def=attr_def, siblings=siblings):
                continue
            violations.append(
                RuleViolation(
                    rule_id=rule.id,
                    element=element,
                    attr=attr,
                    path=path or element,
                    value=value,
                    severity=rule.severity,
                    message=_default_message(rule, check, value),
                    check_type=check.type,
                )
            )
            # One reported violation per rule is enough for UI brevity.
            break
    return violations


def validate_document(
    xml_text: str,
    schema: DTDSchema | None = None,
    *,
    context: RuleContext,
    ruleset: AttributeRuleSet | None = None,
) -> DocumentValidationReport:
    """Walk the XML tree and collect rule violations for the given *context*.

    This does synchronous XML parsing; callers on the asyncio event loop should
    run it via ``asyncio.to_thread`` for large documents.
    """
    ruleset = ruleset if ruleset is not None else load_attribute_rules()
    report = DocumentValidationReport()
    if not xml_text or not xml_text.strip():
        return report

    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        report.errors.append(
            RuleViolation(
                rule_id="xml-parse",
                element="",
                attr="",
                path="",
                value="",
                severity="error",
                message=f"XML parse error: {exc}",
                check_type="regex",
            )
        )
        return report

    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        elem_name = prefixed_element_name(el)
        elem_def = schema.elements.get(el.tag) if schema else None
        if schema and elem_def is None:
            elem_def = schema.elements.get(elem_name)
        path = element_dot_path(el)
        siblings = attribute_sibling_context(el)
        for attr_name, attr_value in el.attrib.items():
            if attr_name == "xmlns" or attr_name.startswith("xmlns:"):
                continue
            attr_def = elem_def.attributes.get(attr_name) if elem_def else None
            for violation in validate_attribute(
                elem_name,
                attr_name,
                attr_value,
                context=context,
                path=path,
                attr_def=attr_def,
                ruleset=ruleset,
                siblings=siblings,
            ):
                if violation.severity == "error":
                    report.errors.append(violation)
                else:
                    report.warnings.append(violation)

    return report


PUSH_WARNINGS_REQUIRE_ACK = "warnings_require_ack"
PUSH_WARNING_ITEM_LIMIT = 20


def _violation_location(violation: RuleViolation) -> str:
    if violation.attr:
        return f"{violation.path}@{violation.attr}"
    return violation.path or violation.element


def format_push_rule_error(report: DocumentValidationReport) -> str | None:
    """User-facing Russian error when push-time rules fail with severity=error."""
    if not report.has_errors:
        return None
    lines = ["Документ не прошёл проверку правил атрибутов для отправки в Git:"]
    for violation in report.errors[:8]:
        lines.append(f"- {_violation_location(violation)}: {violation.message}")
    if len(report.errors) > 8:
        lines.append(f"… и ещё {len(report.errors) - 8}")
    return "\n".join(lines)


def serialize_push_warnings(
    report: DocumentValidationReport,
    *,
    limit: int = PUSH_WARNING_ITEM_LIMIT,
) -> list[dict[str, str]]:
    """Structured warning items for the Git-push confirmation step."""
    items: list[dict[str, str]] = []
    for violation in report.warnings[:limit]:
        items.append(
            {
                "path": violation.path,
                "attr": violation.attr,
                "location": _violation_location(violation),
                "message": violation.message,
            }
        )
    return items


def push_warnings_ack_detail(report: DocumentValidationReport) -> dict:
    """HTTP 409 payload when warning-level rules need explicit acknowledgement."""
    return {
        "code": PUSH_WARNINGS_REQUIRE_ACK,
        "message": "Документ содержит предупреждения правил атрибутов. Подтвердите отправку в Git.",
        "warnings": serialize_push_warnings(report),
        "warning_count": len(report.warnings),
    }
