"""Anonymization engine: scan an XML document, classify values, replace them.

Pipeline for :func:`apply_anonymization`:

1. parse safely (no entity resolution, no DTD loading, no network);
2. every attribute value and text node becomes a *slot* and gets a decision:
   ``replace`` / ``keep`` / ``skip`` / ``disabled`` / ``review`` (unclassified);
3. ``replace`` slots receive a deterministic fake of their category;
4. a *sweep* replaces known originals (and obvious e-mails/phones/SNILS) that
   occur in the remaining unclassified / free-text values and in comments;
5. a leak check reports originals that still survive in explicitly kept fields.

Real values never reach logs: only counts and categories are reported.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from app.core.dtd_models import DTDSchema
from app.core.xml_tree import (
    element_dot_path,
    prefixed_element_name,
    schema_element_def,
)
from app.services.anonymize.categories import CATEGORY_IDS, category_label
from app.services.anonymize.generators import (
    FakeFactory,
    _digits_only,
    _fill_template,
    _match_case,
    _norm_text,
    mask_value,
)
from app.services.anonymize.heuristics import guess_category, is_suspicious
from app.services.anonymize.rules import TEXT_ATTR, RuleSet
from app.services.attribute_rules_service import (
    attribute_sibling_context,
    is_deny_copy,
    load_attribute_rules,
)

DIGIT_CATEGORIES = frozenset(
    {
        "inn", "snils", "passport_full", "passport_series", "passport_number",
        "passport_unit_code", "kpp", "ogrn", "phone", "postcode",
        "account_number", "bic", "card_number",
    }
)
PERSON_CATEGORIES = frozenset({"person_full", "person_last", "person_first", "person_middle"})

_SKIP_ATTR_NAMESPACES = (
    "http://www.w3.org/2001/XMLSchema-instance",
    "http://www.w3.org/XML/1998/namespace",
)

_DECL_RE = re.compile(r"^\s*(<\?xml\b[^>]*\?>)", re.S)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\s+[^\[>]*(?:\[.*?\]\s*)?>", re.S | re.I)

_MIN_SWEEP_WORD = 4
_MIN_SWEEP_DIGITS = 6

_SCAN_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SCAN_SNILS = re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}[ -]\d{2}(?!\d)")
_SCAN_INN = re.compile(r"(?i)(?P<p>инн\D{0,6})(?P<n>\d{12}|\d{10})(?!\d)")
_SCAN_PHONE = re.compile(
    r"(?<![\w+])(?:\+7|8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)


class AnonymizeError(ValueError):
    """Input cannot be anonymized (not well-formed XML etc.)."""


@dataclass
class Override:
    action: str  # replace | keep | skip
    category: str | None = None


@dataclass
class Options:
    key: bytes
    enabled_categories: frozenset[str] | None = None
    strip_comments: bool = True
    overrides: dict[str, Override] = field(default_factory=dict)
    extra_entities: list[tuple[str, str]] = field(default_factory=list)
    schema: DTDSchema | None = None
    max_findings: int = 3000


@dataclass
class Slot:
    el: etree._Element
    kind: str  # attr | text | tail
    attr: str  # display attribute name or "#text"
    raw_attr: str
    value: str
    element_name: str
    name: str
    key: str
    line: int | None
    ctx: dict[str, str]
    action: str = "review"
    category: str | None = None
    source: str = ""
    rule_id: str = ""
    suspicious: bool = False
    suggested: str | None = None
    hint: str = ""
    doc: str = ""


@dataclass
class ParsedDoc:
    root: etree._Element
    declaration: str
    doctype: str


# ---------------------------------------------------------------------------
# Parsing / serialization
# ---------------------------------------------------------------------------


def parse_document(xml_text: str) -> ParsedDoc:
    text = (xml_text or "").lstrip("\ufeff")
    if not text.strip():
        raise AnonymizeError("XML пуст")
    match = _DECL_RE.match(text)
    declaration = match.group(1) if match else ""
    body = text[match.end() :] if match else text
    if match:
        # Keep line numbers aligned with the original text.
        body = "\n" * match.group(0).count("\n") + body
    doctype_match = _DOCTYPE_RE.search(body)
    doctype = doctype_match.group(0) if doctype_match else ""
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        strip_cdata=False,
        remove_comments=False,
    )
    try:
        root = etree.fromstring(body.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        raise AnonymizeError(f"Не удалось разобрать XML: {exc}") from exc
    return ParsedDoc(root=root, declaration=declaration, doctype=doctype)


def serialize_document(doc: ParsedDoc, *, strip_comments: bool) -> tuple[str, str]:
    """Return ``(full_text, body_without_declaration)``."""
    parts: list[str] = []
    if doc.doctype:
        parts.append(doc.doctype + "\n")
    if not strip_comments:
        for sibling in reversed(list(doc.root.itersiblings(preceding=True))):
            parts.append(etree.tostring(sibling, encoding="unicode"))
    parts.append(etree.tostring(doc.root, encoding="unicode", with_tail=False))
    if not strip_comments:
        for sibling in doc.root.itersiblings():
            parts.append(etree.tostring(sibling, encoding="unicode"))
    body = "".join(parts)
    full = f"{doc.declaration}\n{body}" if doc.declaration else body
    return full, body


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _attr_display(el: etree._Element, raw: str) -> str | None:
    if not raw.startswith("{"):
        return raw
    qname = etree.QName(raw)
    if qname.namespace in _SKIP_ATTR_NAMESPACES:
        return None
    for prefix, uri in (el.nsmap or {}).items():
        if uri == qname.namespace and prefix:
            return f"{prefix}:{qname.localname}"
    return qname.localname


def _is_pair_element(el: etree._Element) -> bool:
    return "name" in el.attrib and "value" in el.attrib


def _make_key(element_name: str, attr: str, name: str) -> str:
    return f"{element_name}|{attr}|{name}"


def _dtd_attr_is_safe(schema: DTDSchema | None, el: etree._Element, raw_attr: str) -> bool:
    if schema is None:
        return False
    elem_def = schema_element_def(el, schema)
    if elem_def is None:
        return False
    attr_def = elem_def.attributes.get(raw_attr)
    if attr_def is None:
        return False
    return bool(attr_def.allowed_values) or attr_def.is_declared_default()


def _dtd_attr_doc(schema: DTDSchema | None, el: etree._Element, raw_attr: str) -> str:
    if schema is None:
        return ""
    elem_def = schema_element_def(el, schema)
    if elem_def is None:
        return ""
    attr_def = elem_def.attributes.get(raw_attr)
    return (attr_def.doc if attr_def else "") or ""


def scan_slots(root: etree._Element, rules: RuleSet, opts: Options) -> list[Slot]:
    """Build and classify a slot for every non-empty attribute value and text node."""
    deny_ruleset = load_attribute_rules()
    slots: list[Slot] = []

    def decide(slot: Slot) -> None:
        override = opts.overrides.get(slot.key)
        decided = False
        if override is not None:
            if override.action == "skip":
                slot.action, slot.source, decided = "skip", "override", True
            elif override.action == "keep":
                slot.action, slot.source, decided = "keep", "override", True
            elif override.action == "replace" and override.category in CATEGORY_IDS:
                slot.action, slot.category, slot.source = "replace", override.category, "override"
                decided = True
        if not decided:
            rule = rules.match(slot.element_name, slot.attr, slot.ctx)
            if rule is not None:
                slot.action = rule.action
                slot.category = rule.category
                slot.source = rule.source or "rule"
                slot.rule_id = rule.id
                decided = True
        if not decided and slot.kind == "attr" and _dtd_attr_is_safe(opts.schema, slot.el, slot.raw_attr):
            slot.action, slot.source, decided = "keep", "dtd", True
        if not decided and slot.kind == "attr" and is_deny_copy(slot.attr, deny_ruleset):
            category, _ = guess_category(slot.attr, slot.value, slot.name)
            if category:
                slot.action, slot.category, slot.source = "replace", category, "builtin"
                decided = True
        if not decided:
            slot.action = "review"
            category, reason = guess_category(slot.attr, slot.value, slot.name)
            slot.suggested = category
            slot.hint = reason
            slot.suspicious = is_suspicious(slot.value)
            if slot.kind == "attr":
                slot.doc = _dtd_attr_doc(opts.schema, slot.el, slot.raw_attr)
            return
        if (
            slot.action == "replace"
            and opts.enabled_categories is not None
            and slot.category not in opts.enabled_categories
        ):
            slot.action = "disabled"

    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        element_name = prefixed_element_name(el)
        ctx = attribute_sibling_context(el)
        pair_name = (el.get("name") or "").strip() if _is_pair_element(el) else ""
        line = el.sourceline

        for raw_attr, value in el.attrib.items():
            if raw_attr == "xmlns" or raw_attr.startswith("xmlns:"):
                continue
            display = _attr_display(el, raw_attr)
            if display is None or not value.strip():
                continue
            slot = Slot(
                el=el, kind="attr", attr=display, raw_attr=raw_attr, value=value,
                element_name=element_name, name=pair_name,
                key=_make_key(element_name, display, pair_name), line=line, ctx=ctx,
            )
            decide(slot)
            slots.append(slot)

        if el.text and el.text.strip():
            slot = Slot(
                el=el, kind="text", attr=TEXT_ATTR, raw_attr=TEXT_ATTR, value=el.text,
                element_name=element_name, name=pair_name,
                key=_make_key(element_name, TEXT_ATTR, pair_name), line=line, ctx=ctx,
            )
            decide(slot)
            slots.append(slot)

        parent = el.getparent()
        if parent is not None and el.tail and el.tail.strip():
            parent_name = prefixed_element_name(parent)
            parent_ctx = attribute_sibling_context(parent)
            slot = Slot(
                el=el, kind="tail", attr=TEXT_ATTR, raw_attr=TEXT_ATTR, value=el.tail,
                element_name=parent_name, name="",
                key=_make_key(parent_name, TEXT_ATTR, ""), line=parent.sourceline,
                ctx=parent_ctx,
            )
            decide(slot)
            slots.append(slot)
    return slots


def _write_slot(slot: Slot, new_value: str) -> None:
    if slot.kind == "attr":
        slot.el.set(slot.raw_attr, new_value)
    elif slot.kind == "text":
        slot.el.text = new_value
    else:
        slot.el.tail = new_value


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def _word_pattern(key: str) -> str:
    out: list[str] = []
    for ch in key:
        if ch.isspace():
            out.append(r"\s+")
        elif ch == "е":
            out.append("[её]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


@dataclass
class _Person:
    last: str
    first: str
    middle: str
    fake_last: str
    fake_first: str
    fake_middle: str


class SweepMaps:
    """Known originals -> fakes, used to clean values no rule claimed."""

    def __init__(self, gen: FakeFactory) -> None:
        self.gen = gen
        self.words: dict[str, str] = {}
        self.digits: dict[str, str] = {}
        self.persons: list[_Person] = []
        self.categories: dict[str, str] = {}  # normalized original -> category
        self._word_re: re.Pattern[str] | None = None
        self._digit_res: list[tuple[re.Pattern[str], str]] = []
        self._initial_res: list[tuple[re.Pattern[str], str]] = []

    def _add_word(self, original: str, fake: str, category: str) -> None:
        key = _norm_text(original)
        if len(key) < _MIN_SWEEP_WORD or not fake or _norm_text(fake) == key:
            return
        self.words.setdefault(key, fake)
        self.categories.setdefault(key, category)

    def _add_digits(self, original: str, fake: str, category: str) -> None:
        d_orig, d_fake = _digits_only(original), _digits_only(fake)
        if len(d_orig) < _MIN_SWEEP_DIGITS or len(d_orig) != len(d_fake) or d_orig == d_fake:
            return
        self.digits.setdefault(d_orig, d_fake)
        self.categories.setdefault(d_orig, category)

    def register(self, category: str, original: str, fake: str) -> None:
        original = original.strip()
        if not original:
            return
        gen = self.gen
        if category in DIGIT_CATEGORIES:
            self._add_digits(original, fake, category)
            return
        self._add_word(original, fake, category)
        if category == "person_full":
            parts = gen.split_person(original)
            roles: dict[str, str] = {}
            for token, role in parts:
                if role == "initials":
                    continue
                roles[role] = token
                fake_token = {
                    "last": gen.fake_last,
                    "first": gen.fake_first,
                    "middle": gen.fake_middle,
                }[role](token)
                self._add_word(token, fake_token, "person_full")
            if roles.get("last") and roles.get("first"):
                self.persons.append(
                    _Person(
                        last=roles["last"],
                        first=roles["first"],
                        middle=roles.get("middle", ""),
                        fake_last=gen.fake_last(roles["last"]),
                        fake_first=gen.fake_first(roles["first"]),
                        fake_middle=gen.fake_middle(roles["middle"]) if roles.get("middle") else "",
                    )
                )
        elif category in PERSON_CATEGORIES:
            fn = {
                "person_last": gen.fake_last,
                "person_first": gen.fake_first,
                "person_middle": gen.fake_middle,
            }[category]
            for token in re.split(r"[\s-]+", original):
                if token:
                    self._add_word(token, fn(token), category)

    def compile(self) -> None:
        if self.words:
            keys = sorted(self.words, key=len, reverse=True)
            body = "|".join(_word_pattern(k) for k in keys)
            self._word_re = re.compile(rf"(?<!\w)(?:{body})(?!\w)", re.I | re.U)
        else:
            self._word_re = None
        self._digit_res = []
        for d, fake_d in self.digits.items():
            pattern = r"(?<!\d)" + r"[\s\-.()]{0,2}".join(re.escape(c) for c in d) + r"(?!\d)"
            self._digit_res.append((re.compile(pattern), fake_d))
        self._initial_res = []
        for p in self.persons:
            f0, m0 = p.first[:1], p.middle[:1]
            last = _word_pattern(_norm_text(p.last))
            ff, fm = p.fake_first[:1].upper(), p.fake_middle[:1].upper()
            variants: list[tuple[str, str]] = []
            if m0:
                variants.append(
                    (rf"(?<!\w){last}\s+{f0}\.\s?{m0}\.", f"{p.fake_last} {ff}.{fm or ff}.")
                )
                variants.append(
                    (rf"(?<!\w){f0}\.\s?{m0}\.\s+{last}(?!\w)", f"{ff}.{fm or ff}. {p.fake_last}")
                )
            variants.append((rf"(?<!\w){last}\s+{f0}\.(?!\w)", f"{p.fake_last} {ff}."))
            variants.append((rf"(?<!\w){f0}\.\s+{last}(?!\w)", f"{ff}. {p.fake_last}"))
            for pat, repl in variants:
                self._initial_res.append((re.compile(pat, re.I | re.U), repl))

    def _scan_patterns(self, text: str, hits: Counter[str]) -> str:
        gen = self.gen

        def _email(m: re.Match[str]) -> str:
            hits["email"] += 1
            return gen.fake_email(m.group(0))

        def _snils(m: re.Match[str]) -> str:
            hits["snils"] += 1
            return gen.fake_snils(m.group(0))

        def _inn(m: re.Match[str]) -> str:
            hits["inn"] += 1
            return m.group("p") + gen.fake_inn(m.group("n"))

        def _phone(m: re.Match[str]) -> str:
            hits["phone"] += 1
            return gen.fake_phone(m.group(0))

        text = _SCAN_EMAIL.sub(_email, text)
        text = _SCAN_SNILS.sub(_snils, text)
        text = _SCAN_INN.sub(_inn, text)
        text = _SCAN_PHONE.sub(_phone, text)
        return text

    def sweep(self, text: str, hits: Counter[str]) -> str:
        """Replace known originals and obvious PII patterns in *text*."""
        if not text or not text.strip():
            return text
        text = self._scan_patterns(text, hits)
        for pattern, repl in self._initial_res:
            text, n = pattern.subn(repl, text)
            hits["known_value"] += n
        if self._word_re is not None:

            def _word(m: re.Match[str]) -> str:
                fake = self.words.get(_norm_text(m.group(0)))
                if fake is None:
                    return m.group(0)
                hits["known_value"] += 1
                return _match_case(m.group(0), fake)

            text = self._word_re.sub(_word, text)
        if any(ch.isdigit() for ch in text):
            for pattern, fake_d in self._digit_res:

                def _digits(m: re.Match[str], fake_d: str = fake_d) -> str:
                    hits["known_value"] += 1
                    return _fill_template(m.group(0), fake_d)

                text = pattern.sub(_digits, text)
        return text

    def find_leak(self, text: str) -> str | None:
        """Return the category of a surviving original in *text*, if any."""
        if self._word_re is not None:
            m = self._word_re.search(text)
            if m:
                return self.categories.get(_norm_text(m.group(0)), "")
        if any(ch.isdigit() for ch in text):
            for pattern, _ in self._digit_res:
                m = pattern.search(text)
                if m:
                    return self.categories.get(_digits_only(m.group(0)), "")
        return None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class QueueItem:
    key: str
    element: str
    attr: str
    name: str
    count: int = 0
    lines: list[int] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)
    suspicious: bool = False
    suggested_category: str | None = None
    hint: str = ""
    doc: str = ""


def build_queue(slots: list[Slot]) -> list[QueueItem]:
    groups: dict[str, QueueItem] = {}
    for slot in slots:
        if slot.action != "review":
            continue
        item = groups.get(slot.key)
        if item is None:
            item = groups[slot.key] = QueueItem(
                key=slot.key, element=slot.element_name, attr=slot.attr, name=slot.name,
                doc=slot.doc,
            )
        item.count += 1
        if slot.line is not None and len(item.lines) < 5:
            item.lines.append(slot.line)
        sample = mask_value(slot.value.strip())
        if sample and sample not in item.samples and len(item.samples) < 2:
            item.samples.append(sample)
        if slot.suspicious:
            item.suspicious = True
        if slot.suggested and not item.suggested_category:
            item.suggested_category = slot.suggested
            item.hint = slot.hint
    return sorted(
        groups.values(),
        key=lambda i: (not i.suspicious, i.suggested_category is None, -i.count, i.key),
    )


def queue_to_dict(item: QueueItem) -> dict[str, Any]:
    return {
        "key": item.key,
        "element": item.element,
        "attr": item.attr,
        "name": item.name,
        "count": item.count,
        "lines": item.lines,
        "samples": item.samples,
        "suspicious": item.suspicious,
        "suggested_category": item.suggested_category,
        "hint": item.hint,
        "doc": item.doc,
    }


def build_findings(slots: list[Slot], limit: int) -> tuple[list[dict[str, Any]], bool]:
    findings: list[dict[str, Any]] = []
    truncated = False
    for slot in slots:
        if slot.action not in ("replace", "disabled"):
            continue
        if len(findings) >= limit:
            truncated = True
            break
        findings.append(
            {
                "key": slot.key,
                "path": element_dot_path(slot.el),
                "element": slot.element_name,
                "attr": slot.attr,
                "name": slot.name,
                "category": slot.category,
                "category_label": category_label(slot.category),
                "source": slot.source or "rule",
                "rule_id": slot.rule_id,
                "action": slot.action,
                "line": slot.line,
                "masked_preview": mask_value(slot.value.strip()),
            }
        )
    return findings, truncated


def slot_stats(slots: list[Slot]) -> dict[str, int]:
    c = Counter(s.action for s in slots)
    return {
        "total_values": len(slots),
        "replace": c.get("replace", 0),
        "keep": c.get("keep", 0),
        "skip": c.get("skip", 0),
        "disabled": c.get("disabled", 0),
        "unclassified": c.get("review", 0),
        "unclassified_suspicious": sum(1 for s in slots if s.action == "review" and s.suspicious),
    }


@dataclass
class AnalysisResult:
    findings: list[dict[str, Any]]
    findings_truncated: bool
    queue: list[QueueItem]
    stats: dict[str, int]
    root_element: str


def analyze_document(xml_text: str, rules: RuleSet, opts: Options) -> AnalysisResult:
    doc = parse_document(xml_text)
    slots = scan_slots(doc.root, rules, opts)
    findings, truncated = build_findings(slots, opts.max_findings)
    return AnalysisResult(
        findings=findings,
        findings_truncated=truncated,
        queue=build_queue(slots),
        stats=slot_stats(slots),
        root_element=prefixed_element_name(doc.root),
    )


def free_text_candidates(slots: list[Slot]) -> list[Slot]:
    """Slots worth sending to the LLM for entity search."""
    out: list[Slot] = []
    for slot in slots:
        if slot.action == "replace" and slot.category == "free_text":
            out.append(slot)
        elif (
            slot.action == "review"
            and slot.suspicious
            and len(slot.value.split()) >= 3
            and len(slot.value) >= 20
            and re.search(r"[А-Яа-яЁё]", slot.value)
        ):
            out.append(slot)
    return out


def collect_free_text(xml_text: str, rules: RuleSet, opts: Options) -> list[str]:
    """Distinct free-text values (stripped) the LLM should inspect."""
    doc = parse_document(xml_text)
    slots = scan_slots(doc.root, rules, opts)
    seen: dict[str, None] = {}
    for slot in free_text_candidates(slots):
        seen.setdefault(slot.value.strip(), None)
    return list(seen)


@dataclass
class ApplyResult:
    xml_text: str
    body_text: str
    original_body: str
    report: dict[str, Any]
    queue: list[QueueItem]


def _initials_last(slot: Slot) -> int:
    """Sort key: full names with initials go last so they can reuse registered persons."""
    if slot.category != "person_full":
        return 0
    return 1 if re.search(r"(?<!\w)[А-ЯЁA-Z]\.", slot.value) else 0


def _bic_hint(slot: Slot, by_attr: dict[tuple[int, str], Slot], gen: FakeFactory) -> str | None:
    if slot.kind != "attr" or slot.category != "account_number":
        return None
    for raw in slot.el.attrib:
        if raw.lower() in ("bic", "bik"):
            sibling = by_attr.get((id(slot.el), raw))
            if sibling is None:
                return slot.el.get(raw)
            if sibling.action == "replace" and sibling.category == "bic":
                return gen.fake("bic", sibling.value.strip())
            return sibling.value
    return None


def apply_anonymization(xml_text: str, rules: RuleSet, opts: Options) -> ApplyResult:
    doc = parse_document(xml_text)
    original_full, original_body = serialize_document(doc, strip_comments=opts.strip_comments)
    slots = scan_slots(doc.root, rules, opts)
    gen = FakeFactory(opts.key)
    maps = SweepMaps(gen)
    by_attr = {(id(s.el), s.raw_attr): s for s in slots if s.kind == "attr"}

    counts: Counter[str] = Counter()
    unchanged = 0

    replace_slots = [s for s in slots if s.action == "replace" and s.category != "free_text"]
    replace_slots.sort(key=_initials_last)
    for slot in replace_slots:
        stripped = slot.value.strip()
        lead = slot.value[: len(slot.value) - len(slot.value.lstrip())]
        trail = slot.value[len(slot.value.rstrip()) :]
        assert slot.category is not None
        fake = gen.fake(slot.category, stripped, bic_hint=_bic_hint(slot, by_attr, gen))
        if fake == stripped:
            unchanged += 1
            continue
        _write_slot(slot, lead + fake + trail)
        counts[slot.category] += 1
        maps.register(slot.category, stripped, fake)

    for text, category in opts.extra_entities:
        if category in CATEGORY_IDS and category != "free_text" and text.strip():
            maps.register(category, text.strip(), gen.fake(category, text.strip()))
    maps.compile()

    hits: Counter[str] = Counter()
    sweep_targets = [
        s for s in slots
        if s.action == "review" or (s.action == "replace" and s.category == "free_text")
    ]
    swept_values = 0
    for slot in sweep_targets:
        current = slot.value
        new = maps.sweep(current, hits)
        if new != current:
            _write_slot(slot, new)
            swept_values += 1

    comments_removed = 0
    top_level_comments = [
        n for n in (*doc.root.itersiblings(preceding=True), *doc.root.itersiblings())
        if n.tag is etree.Comment or n.tag is etree.ProcessingInstruction
    ]
    if opts.strip_comments:
        comments_removed = sum(
            1 for _ in doc.root.iter(etree.Comment, etree.ProcessingInstruction)
        ) + len(top_level_comments)
        etree.strip_tags(doc.root, etree.Comment, etree.ProcessingInstruction)
    else:
        for node in (*doc.root.iter(etree.Comment), *top_level_comments):
            if node.text:
                node.text = maps.sweep(node.text, hits)

    # Leak check: originals that survived in fields we deliberately left alone.
    leaks: list[dict[str, Any]] = []
    for slot in slots:
        if slot.action not in ("keep", "skip", "disabled"):
            continue
        category = maps.find_leak(slot.value)
        if category is None:
            continue
        if len(leaks) < 50:
            leaks.append(
                {
                    "path": element_dot_path(slot.el),
                    "attr": slot.attr,
                    "line": slot.line,
                    "category": category or None,
                    "action": slot.action,
                }
            )

    result_full, result_body = serialize_document(doc, strip_comments=opts.strip_comments)
    queue = build_queue(slots)
    stats = slot_stats(slots)

    warnings: list[str] = []
    if unchanged:
        warnings.append(
            f"{unchanged} значен. не удалось изменить (формат не распознан для выбранной категории)"
        )
    if leaks:
        warnings.append(
            f"Найдено {len(leaks)} значен. в полях «оставить/пропустить», совпадающих с заменёнными данными"
        )

    report = {
        "root_element": prefixed_element_name(doc.root),
        "replaced": sum(counts.values()),
        "by_category": [
            {"category": cat, "label": category_label(cat), "count": n}
            for cat, n in sorted(counts.items(), key=lambda kv: -kv[1])
        ],
        "stats": stats,
        "sweep": {
            "values_changed": swept_values,
            "replacements": sum(hits.values()),
            "by_type": dict(hits),
        },
        "comments_removed": comments_removed,
        "unclassified": [queue_to_dict(i) for i in queue],
        "unresolved_suspicious": sum(1 for i in queue if i.suspicious),
        "status": "needs_review" if any(i.suspicious for i in queue) else "clean",
        "leak_check": {"ok": not leaks, "items": leaks},
        "warnings": warnings,
    }
    return ApplyResult(
        xml_text=result_full,
        body_text=result_body,
        original_body=original_body,
        report=report,
        queue=queue,
    )
