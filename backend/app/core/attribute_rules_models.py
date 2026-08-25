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
