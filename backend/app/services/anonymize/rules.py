"""Anonymization rules: global ``config/anonymize_rules.json`` + per-user overlay.

A rule maps ``(element, attr[, name][, parent])`` to a decision:

* ``replace`` -- the value is personal data, replace it with a fake of ``category``;
* ``keep`` -- the value is explicitly *not* personal data (enums, codes, flags).

A field with neither decision is *unclassified* and goes to the review queue.
The global layer is read-only for the API (it is versioned in the repository);
users build their own layer from the review queue. On conflicts the more
specific rule wins, and on a tie the personal rule wins over the global one.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

import app.config as app_config
from app.config import CONFIG_DIR, PROJECT_ROOT
from app.services.anonymize.categories import is_valid_category
from app.services.attribute_rules_service import _element_matches_rule
from app.user_context import UserContext

logger = logging.getLogger(__name__)

ANON_RULES_FILE = CONFIG_DIR / "anonymize_rules.json"
ANON_RULES_EXAMPLE = CONFIG_DIR / "anonymize_rules.json.example"

TEXT_ATTR = "#text"
RuleAction = Literal["replace", "keep"]
RuleSource = Literal["manual", "heuristic", "llm_suggested", "builtin"]

_GLOB_CHARS = frozenset("*?[")


class AnonRule(BaseModel):
    """One classification rule."""

    id: str = ""
    element: str | None = None
    attr: str
    name: str | None = None
    parent_element: str | None = None
    parent_name: str | None = None
    parent_value: str | None = None
    action: RuleAction
    category: str | None = None
    source: RuleSource = "manual"
    created_by: str = ""
    created_at: str = ""
    note: str = ""
    # Runtime-only: which layer the rule came from ("global" | "user").
    layer: str = Field(default="", exclude=True)

    @model_validator(mode="after")
    def _validate(self) -> AnonRule:
        self.attr = (self.attr or "").strip()
        if not self.attr:
            raise ValueError("rule requires 'attr'")
        for field in ("element", "name", "parent_element", "parent_name", "parent_value"):
            value = getattr(self, field)
            if value is not None:
                value = value.strip()
                setattr(self, field, value or None)
        if self.action == "replace":
            if not is_valid_category(self.category):
                raise ValueError(f"unknown category {self.category!r}")
        else:
            self.category = None
        return self

    @property
    def key(self) -> str:
        """Identity used for upserts: same scope == same rule."""
        parts = (
            self.element or "",
            self.attr,
            self.name or "",
            self.parent_element or "",
            self.parent_name or "",
            self.parent_value or "",
        )
        return "|".join(p.lower() for p in parts)


def _is_glob(pattern: str) -> bool:
    return any(ch in _GLOB_CHARS for ch in pattern)


def _ci_match(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value.lower(), pattern.lower())


class RuleSet:
    """Indexed collection of rules with specificity-based matching."""

    def __init__(self, rules: list[AnonRule] | None = None) -> None:
        self.rules: list[AnonRule] = list(rules or [])
        self._exact: dict[str, list[AnonRule]] = {}
        self._globs: list[AnonRule] = []
        for rule in self.rules:
            if _is_glob(rule.attr):
                self._globs.append(rule)
            else:
                self._exact.setdefault(rule.attr.lower(), []).append(rule)

    def __len__(self) -> int:
        return len(self.rules)

    @staticmethod
    def _score(
        rule: AnonRule, element_name: str, attr: str, ctx: dict[str, str]
    ) -> int | None:
        score = 0
        if _is_glob(rule.attr):
            if not _ci_match(rule.attr, attr):
                return None
        else:
            if rule.attr.lower() != attr.lower():
                return None
            score += 2
        if rule.element:
            if not _element_matches_rule(rule.element, element_name):
                return None
            score += 8
        if rule.name:
            if not _ci_match(rule.name, (ctx.get("name") or "").strip()):
                return None
            score += 8
        if rule.parent_element:
            actual = (ctx.get("parent.__element__") or "").strip()
            if not _element_matches_rule(rule.parent_element, actual):
                return None
            score += 4
        if rule.parent_name:
            if (ctx.get("parent.name") or "").strip() != rule.parent_name:
                return None
            score += 4
        if rule.parent_value:
            if (ctx.get("parent.value") or "").strip() != rule.parent_value:
                return None
            score += 4
        return score

    def match(
        self, element_name: str, attr: str, ctx: dict[str, str] | None = None
    ) -> AnonRule | None:
        ctx = ctx or {}
        best: AnonRule | None = None
        best_score = -1
        for rule in (*self._exact.get(attr.lower(), ()), *self._globs):
            score = self._score(rule, element_name, attr, ctx)
            if score is None:
                continue
            # ``>=``: on equal specificity the later rule (user layer) wins.
            if score >= best_score:
                best, best_score = rule, score
        return best


# ---------------------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------------------


def parse_rules(raw: object, *, source: str, layer: str) -> list[AnonRule]:
    """Validate rules one by one so a single bad rule never drops the rest."""
    if not isinstance(raw, list):
        if raw is not None:
            logger.warning("Anonymize rules %s: 'rules' must be a list", source)
        return []
    parsed: list[AnonRule] = []
    for index, item in enumerate(raw):
        try:
            rule = AnonRule.model_validate(item)
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning("Skipping invalid anonymize rule #%d in %s: %s", index, source, exc)
            continue
        rule.layer = layer
        if not rule.id:
            rule.id = f"{layer[:1]}-{uuid.uuid4().hex[:8]}"
        parsed.append(rule)
    return parsed


def _read_rules_file(path: Path, layer: str) -> list[AnonRule]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load anonymize rules from %s: %s", path, exc)
        return []
    if not isinstance(data, dict):
        logger.warning("Anonymize rules file %s must contain a JSON object", path)
        return []
    return parse_rules(data.get("rules", []), source=str(path), layer=layer)


_global_cache: tuple[str, float, list[AnonRule]] | None = None


def load_global_rules() -> list[AnonRule]:
    """Load ``config/anonymize_rules.json`` (falls back to ``.example``), mtime-cached."""
    global _global_cache
    path = ANON_RULES_FILE
    if not path.is_file() and ANON_RULES_EXAMPLE.is_file():
        path = ANON_RULES_EXAMPLE
    if not path.is_file():
        _global_cache = None
        return []
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _global_cache = None
        return []
    if _global_cache and _global_cache[0] == str(path) and _global_cache[1] == mtime:
        return list(_global_cache[2])
    rules = _read_rules_file(path, "global")
    _global_cache = (str(path), mtime, rules)
    return list(rules)


def clear_global_rules_cache() -> None:
    global _global_cache
    _global_cache = None


def anonymize_dir(user: UserContext) -> Path:
    """Per-user directory for rules, secret and suggestion cache."""
    if user.root == PROJECT_ROOT:
        # AUTH_DISABLED dev mode: user.root is the repository root; keep runtime
        # files under the git-ignored data directory instead.
        base = app_config.DATA_DIR / "dev-local"
    else:
        base = user.root
    path = base / "anonymize"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_rules_path(user: UserContext) -> Path:
    return anonymize_dir(user) / "anonymize_rules.json"


def load_user_rules(user: UserContext) -> list[AnonRule]:
    return _read_rules_file(user_rules_path(user), "user")


def save_user_rules(user: UserContext, rules: list[AnonRule]) -> None:
    payload = {
        "version": 1,
        "rules": [r.model_dump(exclude_none=True, exclude_defaults=False) for r in rules],
    }
    path = user_rules_path(user)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_effective_rules(user: UserContext) -> RuleSet:
    """Global rules first, user rules after (so they win ties)."""
    return RuleSet([*load_global_rules(), *load_user_rules(user)])


def upsert_user_rules(
    user: UserContext, incoming: list[AnonRule], *, replace_all: bool = False
) -> list[AnonRule]:
    """Merge *incoming* into the user's layer by scope key; incoming wins."""
    current = [] if replace_all else load_user_rules(user)
    by_key: dict[str, AnonRule] = {r.key: r for r in current}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rule in incoming:
        rule.layer = "user"
        if not rule.created_by:
            rule.created_by = user.display_name
        if not rule.created_at:
            rule.created_at = now
        existing = by_key.get(rule.key)
        if existing is not None and not rule.id:
            rule.id = existing.id
        if not rule.id:
            rule.id = f"u-{uuid.uuid4().hex[:8]}"
        by_key[rule.key] = rule
    merged = list(by_key.values())
    save_user_rules(user, merged)
    return merged


def delete_user_rule(user: UserContext, rule_id: str) -> bool:
    current = load_user_rules(user)
    kept = [r for r in current if r.id != rule_id]
    if len(kept) == len(current):
        return False
    save_user_rules(user, kept)
    return True


# ---------------------------------------------------------------------------
# Per-user secret (key for "user" consistency mode)
# ---------------------------------------------------------------------------


def get_user_secret(user: UserContext) -> bytes:
    """Return (creating on first use) the user's random anonymization secret."""
    path = anonymize_dir(user) / "secret.key"
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8").strip()
            if len(text) >= 32:
                return bytes.fromhex(text)
        except (OSError, ValueError):
            logger.warning("Anonymize secret unreadable; regenerating")
    secret = secrets.token_bytes(32)
    path.write_text(secret.hex(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret
