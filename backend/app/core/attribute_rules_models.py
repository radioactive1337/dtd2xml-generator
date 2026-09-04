"""Pydantic models for config-driven attribute validation rules."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RuleSeverity = Literal["error", "warning"]
RuleContext = Literal["git_push", "post_fill", "git_ai_fill"]
CheckType = Literal[
    "regex",
    "length",
    "min_length",
    "max_length",
    "enum",
    "not_placeholder",
    "charset",
    "cross_field",
]
CrossFieldOp = Literal["eq", "ne", "mapped_eq", "regex_if", "required_if", "empty_if"]


class RuleCheck(BaseModel):
    """A single typed check applied to an attribute value.

    Regex patterns are compiled eagerly here so a malformed pattern fails at
    config-load time (with a clear error attributable to one rule) instead of
    crashing validation later for every request that touches the attribute.
    """

    type: CheckType
    pattern: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    values: list[str] = Field(default_factory=list)
    charset: str | None = None
    expr: str | None = None

    # cross_field only: compare this attribute's value against a sibling
    # attribute (``other``) on the same element. No expression evaluation --
    # deliberately a fixed, safe set of ops instead of an eval'd ``expr``.
    op: CrossFieldOp | None = None
    other: str | None = None
    when: str | None = None
    map: dict[str, str] = Field(default_factory=dict)

    # Optional parent-element gate (cs:attribute trees). If set, the check
    # does not apply unless the parent matches — not a failure, just skipped.
    parent_element: str | None = None
    parent_name: str | None = None
    parent_value: str | None = None

    @model_validator(mode="after")
    def _validate_type_fields(self) -> RuleCheck:
        if self.type == "regex":
            if not self.pattern:
                raise ValueError("regex check requires 'pattern'")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern {self.pattern!r}: {exc}") from exc
        if self.type == "enum" and not self.values:
            raise ValueError("enum check requires 'values'")
        if self.type == "charset" and not self.charset:
            raise ValueError("charset check requires 'charset'")
        if self.type == "length" and self.min_length is None and self.max_length is None:
            raise ValueError("length check requires 'min_length' and/or 'max_length'")
        if self.type == "min_length" and self.min_length is None:
            raise ValueError("min_length check requires 'min_length'")
        if self.type == "max_length" and self.max_length is None:
            raise ValueError("max_length check requires 'max_length'")
        if (
            self.type == "length"
            and self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("length check: min_length cannot exceed max_length")
        if self.type == "cross_field":
            if not self.op:
                raise ValueError("cross_field check requires 'op'")
            if not self.other:
                raise ValueError("cross_field check requires 'other'")
            if self.op == "regex_if":
                if not self.pattern:
                    raise ValueError("cross_field op 'regex_if' requires 'pattern'")
                try:
                    re.compile(self.pattern)
                except re.error as exc:
                    raise ValueError(f"invalid regex pattern {self.pattern!r}: {exc}") from exc
                if self.when is None:
                    raise ValueError("cross_field op 'regex_if' requires 'when'")
            if self.op == "mapped_eq" and not self.map:
                raise ValueError("cross_field op 'mapped_eq' requires 'map'")
            if self.op in {"required_if", "empty_if"} and self.when is None:
                raise ValueError(f"cross_field op '{self.op}' requires 'when'")
        return self


class AttributeRule(BaseModel):
    """Validation rule for a specific attribute (optionally scoped to an element).

    ``attr`` supports glob patterns (e.g. ``"passport*"``), matched the same
    way as ``AttributeRuleSet.deny_copy``.
    """

    id: str
    element: str | None = None
    attr: str
    severity: RuleSeverity = "warning"
    applies_to: list[RuleContext] = Field(default_factory=lambda: ["git_push"])
    checks: list[RuleCheck] = Field(default_factory=list)
    message: str = ""


class AttributeRuleSet(BaseModel):
    """Top-level attribute rules configuration."""

    version: int = 1
    deny_copy: list[str] = Field(default_factory=list)
    rules: list[AttributeRule] = Field(default_factory=list)
