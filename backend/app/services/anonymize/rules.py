"""Anonymization rules: global ``config/anonymize_rules.json`` + per-user overlay.

A rule maps ``(element, attr[, name][, parent])`` to a decision:

* ``replace`` -- the value is personal data, replace it with a fake of ``category``;
* ``keep`` -- the value is explicitly *not* personal data (enums, codes, flags).

A field with neither decision is *unclassified* and goes to the review queue.
Users add rules to their own layer first (from the review queue or the rules
form). Promoting a personal rule writes it into the shared
``config/anonymize_rules.json`` and drops the personal copy. On conflicts the
more specific rule wins, and on a tie the personal rule wins over the global one.
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


_NEW_RULE_ORDER = (
    "id",
    "element",
    "attr",
    "name",
    "parent_element",
    "parent_name",
    "parent_value",
    "action",
    "category",
    "source",
    "created_by",
    "created_at",
    "note",
)
# Fields a promotion may add or clear. ``id`` is kept so existing rules stay put.
_MANAGED_RULE_FIELDS = frozenset(_NEW_RULE_ORDER) - {"id"}


def _rule_payload(rule: AnonRule) -> dict:
    """JSON object for a rule file: no empty strings, no runtime ``layer``."""
    data = rule.model_dump(exclude_none=True)
    ordered: dict = {}
    for key in _NEW_RULE_ORDER:
        value = data.get(key)
        if value not in (None, ""):
            ordered[key] = value
    return ordered


def _dump_rule_line(rule: dict) -> str:
    """One compact object, matching the spacing of ``config/anonymize_rules.json``."""
    parts = [
        f"{json.dumps(key, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in rule.items()
    ]
    return "{ " + ", ".join(parts) + " }"


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _parse_rule_line(line: str) -> dict | None:
    core = line.strip()
    if core.endswith(","):
        core = core[:-1].rstrip()
    if not core.startswith("{"):
        return None
    try:
        value = json.loads(core)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict) and isinstance(value.get("attr"), str):
        return value
    return None


def _with_comma(line: str, comma: bool) -> str:
    core = line.strip()
    if core.endswith(","):
        core = core[:-1].rstrip()
    if comma:
        core += ","
    return _indent_of(line) + core


def _parsed_rule_lines(text: str) -> list[dict]:
    return [rule for line in text.splitlines() if (rule := _parse_rule_line(line)) is not None]


def _line_editable(text: str, data: dict) -> bool:
    """True when every rule is already one JSON object per line (blank lines allowed)."""
    rules = data.get("rules")
    if not isinstance(rules, list) or _parsed_rule_lines(text) != rules:
        return False
    if rules:
        return True
    return any(line.strip() == "]" for line in text.splitlines())


def _join_lines(text: str, lines: list[str]) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    body = newline.join(lines)
    if text.endswith(("\n", "\r\n")) or not text:
        body += newline
    return body


def _write_text(text: str) -> None:
    path = ANON_RULES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    clear_global_rules_cache()


def _rule_line_indexes(lines: list[str]) -> list[int]:
    return [index for index, line in enumerate(lines) if _parse_rule_line(line) is not None]


def _merge_rule_into_lines(lines: list[str], rule: AnonRule, now: str) -> None:
    rule.layer = "global"
    if not rule.created_at:
        rule.created_at = now
    indexes = _rule_line_indexes(lines)
    found: int | None = None
    for index in indexes:
        parsed = _parse_rule_line(lines[index])
        if parsed is None:
            continue
        try:
            if AnonRule.model_validate(parsed).key == rule.key:
                found = index
                break
        except (ValidationError, ValueError, TypeError):
            continue
    if found is None:
        rule.id = f"g-{uuid.uuid4().hex[:8]}"
        rendered = _dump_rule_line(_rule_payload(rule))
        if indexes:
            last = indexes[-1]
            lines[last] = _with_comma(lines[last], True)
            lines.insert(last + 1, f"{_indent_of(lines[last])}{rendered}")
            return
        for index, line in enumerate(lines):
            if line.strip() == "]":
                lines.insert(index, f"    {rendered}")
                return
        raise ValueError("shared anonymize rules file has no rules array")
    existing = _parse_rule_line(lines[found]) or {}
    rule.id = str(existing.get("id") or "") or f"g-{uuid.uuid4().hex[:8]}"
    payload = _rule_payload(rule)
    for key in [key for key in existing if key in _MANAGED_RULE_FIELDS and key not in payload]:
        existing.pop(key, None)
    for key, value in payload.items():
        if key != "id":
            existing[key] = value
    existing["id"] = rule.id
    comma = lines[found].rstrip().endswith(",")
    lines[found] = f"{_indent_of(lines[found])}{_dump_rule_line(existing)}{',' if comma else ''}"


def _upsert_lines(text: str, incoming: list[AnonRule]) -> str:
    lines = text.splitlines()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rule in incoming:
        _merge_rule_into_lines(lines, rule, now)
    return _join_lines(text, lines)


def _delete_rule_line(text: str, rule_id: str) -> str | None:
    lines = text.splitlines()
    indexes = _rule_line_indexes(lines)
    target: int | None = None
    for index in indexes:
        parsed = _parse_rule_line(lines[index])
        if parsed and parsed.get("id") == rule_id:
            target = index
            break
    if target is None:
        return None
    del lines[target]
    indexes = _rule_line_indexes(lines)
    if indexes:
        last = indexes[-1]
        lines[last] = _with_comma(lines[last], False)
        for index in indexes[:-1]:
            lines[index] = _with_comma(lines[index], True)
    return _join_lines(text, lines)


def _dump_global_document(data: dict) -> str:
    version = data.get("version", 1)
    version_text = version if isinstance(version, int) else json.dumps(version, ensure_ascii=False)
    lines = ["{", f'  "version": {version_text},', '  "rules": [']
    body = [
        "    " + (_dump_rule_line(rule) if isinstance(rule, dict) else json.dumps(rule, ensure_ascii=False))
        for rule in data.get("rules") or []
    ]
    if body:
        lines.append(",\n".join(body))
    lines.extend(["  ]", "}"])
    return "\n".join(lines) + "\n"


def _read_global_document() -> dict:
    """Raw shared rules. Falls back to the example without ever writing it."""
    path = ANON_RULES_FILE
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            raise ValueError("shared anonymize rules file must be an object with a rules list")
        return data
    if ANON_RULES_EXAMPLE.is_file():
        data = json.loads(ANON_RULES_EXAMPLE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rules"), list):
            return {"version": data.get("version", 1), "rules": list(data["rules"])}
    return {"version": 1, "rules": []}


def _write_global_document(data: dict) -> None:
    path = ANON_RULES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(_dump_global_document(data), encoding="utf-8")
    os.replace(tmp, path)
    clear_global_rules_cache()


def _merge_into_raw_rules(raw_rules: list, incoming: list[AnonRule]) -> None:
    """In-memory merge used when the file is not one object per line."""
    index_by_key: dict[str, int] = {}
    for index, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            continue
        try:
            parsed = AnonRule.model_validate(item)
        except (ValidationError, ValueError, TypeError):
            continue
        index_by_key[parsed.key] = index

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rule in incoming:
        rule.layer = "global"
        if not rule.created_at:
            rule.created_at = now
        existing_index = index_by_key.get(rule.key)
        if existing_index is None:
            rule.id = f"g-{uuid.uuid4().hex[:8]}"
            raw_rules.append(_rule_payload(rule))
            index_by_key[rule.key] = len(raw_rules) - 1
            continue
        existing = raw_rules[existing_index]
        rule.id = str(existing.get("id") or "") or f"g-{uuid.uuid4().hex[:8]}"
        payload = _rule_payload(rule)
        for key in [key for key in existing if key in _MANAGED_RULE_FIELDS and key not in payload]:
            existing.pop(key, None)
        for key, value in payload.items():
            if key != "id":
                existing[key] = value
        existing["id"] = rule.id


def upsert_global_rules(incoming: list[AnonRule]) -> list[AnonRule]:
    """Merge *incoming* into the shared file by scope key; incoming wins.

    A new scope is appended with a fresh ``g-`` id. An existing scope keeps its
    id. When the file is one JSON object per line, only that line changes and
    blank lines stay put.
    """
    path = ANON_RULES_FILE
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            raise ValueError("shared anonymize rules file must be an object with a rules list")
        if _line_editable(text, data):
            _write_text(_upsert_lines(text, incoming))
            return load_global_rules()
        _merge_into_raw_rules(data["rules"], incoming)
        _write_global_document(data)
        return load_global_rules()

    data = _read_global_document()
    _merge_into_raw_rules(data["rules"], incoming)
    _write_global_document(data)
    return load_global_rules()


def promote_user_rule(user: UserContext, rule_id: str) -> None:
    """Copy one personal rule into the shared file and remove the personal copy.

    Raises ``KeyError`` when *rule_id* is not in the user's layer.
    """
    found = next((rule for rule in load_user_rules(user) if rule.id == rule_id), None)
    if found is None:
        raise KeyError(rule_id)
    promoted = found.model_copy(deep=True)
    promoted.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not promoted.created_by:
        promoted.created_by = user.display_name
    upsert_global_rules([promoted])
    delete_user_rule(user, rule_id)


def delete_global_rule(rule_id: str) -> bool:
    path = ANON_RULES_FILE
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            raise ValueError("shared anonymize rules file must be an object with a rules list")
        if _line_editable(text, data):
            updated = _delete_rule_line(text, rule_id)
            if updated is None:
                return False
            _write_text(updated)
            return True
        raw_rules: list = data["rules"]
        kept = [
            item
            for item in raw_rules
            if not (isinstance(item, dict) and item.get("id") == rule_id)
        ]
        if len(kept) == len(raw_rules):
            return False
        data["rules"] = kept
        _write_global_document(data)
        return True

    data = _read_global_document()
    raw_rules = data["rules"]
    kept = [
        item
        for item in raw_rules
        if not (isinstance(item, dict) and item.get("id") == rule_id)
    ]
    if len(kept) == len(raw_rules):
        return False
    data["rules"] = kept
    _write_global_document(data)
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
