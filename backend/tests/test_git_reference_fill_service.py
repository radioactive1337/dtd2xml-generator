"""Tests for Git reference fill: corpus building, fill-mode policy, copy/AI application."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from app.core.attribute_rules_models import AttributeRuleSet
from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef
from app.services import attribute_rules_service as rules_svc
from app.services import git_reference_fill_service as git_fill


def _schema() -> DTDSchema:
    return DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={
                    "id": AttributeDef(name="id", attr_type="ID", default_decl="#REQUIRED"),
                    "status": AttributeDef(
                        name="status",
                        attr_type="ENUM",
                        default_decl="#IMPLIED",
                        allowed_values=["NEW", "ACTIVE", "CLOSED"],
                    ),
                    "kladr": AttributeDef(name="kladr", attr_type="CDATA", default_decl="#REQUIRED"),
                    "inn": AttributeDef(name="inn", attr_type="CDATA", default_decl="#IMPLIED"),
                },
            )
        }
    )


def _write_ref(root: Path, category: str, filename: str, xml: str) -> None:
    cat = root / category
    cat.mkdir(parents=True, exist_ok=True)
    (cat / filename).write_text(xml, encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_rules_cache():
    rules_svc.clear_attribute_rules_cache()
    yield
    rules_svc.clear_attribute_rules_cache()


# --- build_corpus ---------------------------------------------------------


def test_build_corpus_aggregates_values(tmp_path: Path):
    _write_ref(tmp_path, "PayDoc", "PayDoc_one.xml", '<PayDoc id="a1" status="NEW" kladr="12345678901"/>')
    _write_ref(tmp_path, "PayDoc", "PayDoc_two.xml", '<PayDoc id="a2" status="NEW" kladr="98765432109"/>')

    corpus = git_fill.build_corpus(tmp_path, "PayDoc")

    assert ("PayDoc", "status") in corpus
    stats = corpus[("PayDoc", "status")]
    assert stats.diversity == 1
    assert stats.frequency == 1.0
    assert set(stats.values) == {"NEW"}

    kladr = corpus[("PayDoc", "kladr")]
    assert kladr.diversity == 2
    assert kladr.doc_count == 2


def test_build_corpus_with_explicit_category_bypasses_root_filter(tmp_path: Path):
    """Explicit category name trusts the caller and skips the root_element peek filter."""
    _write_ref(tmp_path, "OtherDoc", "OtherDoc_one.xml", '<OtherDoc code="X1"/>')

    corpus = git_fill.build_corpus(tmp_path, "PayDoc", category="OtherDoc")
    assert ("OtherDoc", "code") in corpus


def test_build_corpus_empty_when_no_matching_docs(tmp_path: Path):
    assert git_fill.build_corpus(tmp_path, "PayDoc") == {}


# --- choose_fill_mode -------------------------------------------------------


def test_choose_fill_mode_is_pure_and_ignores_global_config():
    """deny_copy is the caller's responsibility; the function must not re-derive it."""
    enum_def = AttributeDef(name="status", attr_type="ENUM", default_decl="#IMPLIED", allowed_values=["NEW", "ACTIVE"])
    stats = git_fill.AttributeCorpusStats(values=["NEW", "NEW", "ACTIVE"], diversity=2, doc_count=5)

    assert git_fill.choose_fill_mode(enum_def, stats) == "copy"
    # Even though attr looks harmless, an explicit deny_copy=True always wins.
    assert git_fill.choose_fill_mode(enum_def, stats, deny_copy=True) == "skip"
    assert git_fill.choose_fill_mode(None, None) == "skip"


def test_choose_fill_mode_uses_diversity_ratio_not_absolute_count():
    # Small corpus (2 docs) -> not enough data to trust a ratio, always copy.
    small = git_fill.AttributeCorpusStats(values=["a", "b"], diversity=2, doc_count=2)
    assert git_fill.choose_fill_mode(None, small) == "copy"

    # Larger corpus, low diversity ratio (2/10) -> enum-like -> copy.
    low_ratio = git_fill.AttributeCorpusStats(values=["a"] * 8 + ["b"] * 2, diversity=2, doc_count=10)
    assert git_fill.choose_fill_mode(None, low_ratio) == "copy"

    # Larger corpus, high diversity ratio (9/10) -> free-text/identifier-like -> ai.
    high_ratio = git_fill.AttributeCorpusStats(values=[f"v{i}" for i in range(9)] + ["v0"], diversity=9, doc_count=10)
    assert git_fill.choose_fill_mode(None, high_ratio) == "ai"


# --- populate_from_git: copy mode ------------------------------------------


@pytest.mark.asyncio
async def test_populate_from_git_copy_mode_fills_empty_attrs(tmp_path: Path):
    _write_ref(tmp_path, "PayDoc", "PayDoc_ref.xml", '<PayDoc id="ref-99" status="ACTIVE" kladr="11122233344"/>')

    xml = '<PayDoc id="" status="" kladr=""/>'
    result, protected, warnings, provenance = await git_fill.populate_from_git(
        xml,
        _schema(),
        root=tmp_path,
        root_element="PayDoc",
        fill_empty_only=True,
        allow_ai=False,
    )

    assert 'status="ACTIVE"' in result
    assert 'kladr="11122233344"' in result
    assert protected
    assert provenance
    assert all(v.startswith("git:") for v in provenance.values())
    assert warnings == []


@pytest.mark.asyncio
async def test_populate_from_git_seed_is_deterministic_when_provided(tmp_path: Path):
    _write_ref(tmp_path, "PayDoc", "a.xml", '<PayDoc kladr="11111111111"/>')
    _write_ref(tmp_path, "PayDoc", "b.xml", '<PayDoc kladr="22222222222"/>')
    _write_ref(tmp_path, "PayDoc", "c.xml", '<PayDoc kladr="33333333333"/>')

    xml = '<PayDoc kladr=""/>'
    result_a, *_ = await git_fill.populate_from_git(
        xml, _schema(), root=tmp_path, root_element="PayDoc", allow_ai=False, seed="fixed-seed"
    )
    result_b, *_ = await git_fill.populate_from_git(
        xml, _schema(), root=tmp_path, root_element="PayDoc", allow_ai=False, seed="fixed-seed"
    )
    assert result_a == result_b


# --- populate_from_git: deny_copy never sources from the corpus ------------


@pytest.mark.asyncio
async def test_populate_from_git_never_copies_or_ai_fills_deny_listed_attrs(tmp_path: Path, monkeypatch):
    _write_ref(tmp_path, "PayDoc", "PayDoc_ref.xml", '<PayDoc id="ref-1" inn="7707083893" status="NEW"/>')
    ruleset = AttributeRuleSet.model_validate({"deny_copy": ["inn"], "rules": []})
    monkeypatch.setattr(rules_svc, "load_attribute_rules", lambda **_kw: ruleset)

    class RecordingLlm:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def complete_text(self, *, system_prompt: str, user_message: str, temperature: float = 0.7, **_kwargs) -> str:
            self.calls.append(user_message)
            return "generated-value"

    llm = RecordingLlm()
    xml = '<PayDoc id="" inn="" status=""/>'
    result, protected, warnings, provenance = await git_fill.populate_from_git(
        xml,
        _schema(),
        root=tmp_path,
        root_element="PayDoc",
        fill_empty_only=True,
        allow_ai=True,
        llm=llm,
    )

    assert 'inn="7707083893"' not in result
    assert not any(k.endswith("@inn") for k in provenance)
    # The real inn value must never be sent to the LLM as a few-shot example either.
    assert not any("7707083893" in call for call in llm.calls)
    assert any("privacy-sensitive" in w for w in warnings)


# --- populate_from_git: AI mode with validation + fallback -----------------


@pytest.mark.asyncio
async def test_populate_from_git_ai_fallback_on_validation_failure(tmp_path: Path, monkeypatch):
    _write_ref(tmp_path, "PayDoc", "PayDoc_ref.xml", '<PayDoc id="ref-1" kladr="12345678901"/>')

    def force_ai(attr_def, stats, **kwargs):
        if stats and stats.values and not kwargs.get("deny_copy"):
            return "ai"
        return "skip"

    monkeypatch.setattr(git_fill, "choose_fill_mode", force_ai)

    class AlwaysInvalidLlm:
        async def complete_text(self, *, system_prompt: str, user_message: str, temperature: float = 0.7, **_kwargs) -> str:
            return "not-digits"

    ruleset = AttributeRuleSet.model_validate(
        {
            "rules": [
                {
                    "id": "kladr",
                    "element": "PayDoc",
                    "attr": "kladr",
                    "severity": "error",
                    "applies_to": ["git_ai_fill"],
                    "checks": [{"type": "regex", "pattern": "^[0-9]{11}$"}],
                    "message": "bad",
                }
            ]
        }
    )
    monkeypatch.setattr(rules_svc, "load_attribute_rules", lambda **_kw: ruleset)

    xml = '<PayDoc id="" kladr=""/>'
    result, protected, warnings, provenance = await git_fill.populate_from_git(
        xml,
        _schema(),
        root=tmp_path,
        root_element="PayDoc",
        fill_empty_only=True,
        allow_ai=True,
        llm=AlwaysInvalidLlm(),
    )

    assert "12345678901" in result  # fell back to copy
    assert any("fell back to copy" in w for w in warnings)
    assert any(v.startswith("git:") for v in provenance.values())


@pytest.mark.asyncio
async def test_populate_from_git_ai_retries_after_transient_exception(tmp_path: Path, monkeypatch):
    _write_ref(tmp_path, "PayDoc", "PayDoc_ref.xml", '<PayDoc id="ref-1" kladr="12345678901"/>')

    def force_ai(attr_def, stats, **kwargs):
        if stats and stats.values and not kwargs.get("deny_copy"):
            return "ai"
        return "skip"

    monkeypatch.setattr(git_fill, "choose_fill_mode", force_ai)

    class FlakyLlm:
        def __init__(self) -> None:
            self.attempts = 0

        async def complete_text(self, *, system_prompt: str, user_message: str, temperature: float = 0.7, **_kwargs) -> str:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("network blip")
            indexes = [int(match) for match in re.findall(r"\[(\d+)\] Path:", user_message)]
            if not indexes:
                indexes = [0]
            return json.dumps({"values": [{"i": i, "v": "12345678901"} for i in indexes]})

    xml = '<PayDoc id="" kladr=""/>'
    result, protected, warnings, provenance = await git_fill.populate_from_git(
        xml,
        _schema(),
        root=tmp_path,
        root_element="PayDoc",
        fill_empty_only=True,
        allow_ai=True,
        llm=FlakyLlm(),
    )
    assert "12345678901" in result
    assert any(v.startswith("git-ai:") for v in provenance.values())


@pytest.mark.asyncio
async def test_populate_from_git_empty_corpus_returns_warning(tmp_path: Path):
    xml = '<PayDoc id="" status=""/>'
    result, protected, warnings, provenance = await git_fill.populate_from_git(
        xml, _schema(), root=tmp_path, root_element="PayDoc"
    )
    assert "<PayDoc" in result
    assert not protected
    assert not provenance
    assert warnings


class _CountingLlm:
    def __init__(self, value: str = "44444444444") -> None:
        self.value = value
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        **_kwargs,
    ) -> str:
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        indexes = [int(match) for match in re.findall(r"\[(\d+)\] Path:", user_message)]
        if not indexes:
            indexes = [0]
        return json.dumps({"values": [{"i": i, "v": self.value} for i in indexes]})


@pytest.mark.asyncio
async def test_two_reference_docs_copy_without_calling_llm(tmp_path: Path):
    """Fewer than _MIN_DOCS_FOR_AI_POLICY docs must copy, not wait on LLM."""
    _write_ref(tmp_path, "PayDoc", "a.xml", '<PayDoc kladr="11111111111"/>')
    _write_ref(tmp_path, "PayDoc", "b.xml", '<PayDoc kladr="22222222222"/>')

    llm = _CountingLlm()
    result, _protected, _warnings, provenance = await git_fill.populate_from_git(
        '<PayDoc kladr=""/>',
        _schema(),
        root=tmp_path,
        root_element="PayDoc",
        allow_ai=True,
        llm=llm,
    )

    assert llm.calls == 0
    assert 'kladr="' in result
    assert all(v.startswith("git:") for v in provenance.values())


@pytest.mark.asyncio
async def test_three_reference_docs_use_ai_and_emit_progress(tmp_path: Path):
    """3+ diverse docs trigger Git AI; progress events must fire before LLM returns."""
    _write_ref(tmp_path, "PayDoc", "a.xml", '<PayDoc kladr="11111111111"/>')
    _write_ref(tmp_path, "PayDoc", "b.xml", '<PayDoc kladr="22222222222"/>')
    _write_ref(tmp_path, "PayDoc", "c.xml", '<PayDoc kladr="33333333333"/>')

    progress: list[tuple[str, str, int]] = []

    async def on_progress(step: str, message: str, percent: int) -> None:
        progress.append((step, message, percent))

    llm = _CountingLlm()
    result, _protected, _warnings, provenance = await git_fill.populate_from_git(
        '<PayDoc kladr=""/>',
        _schema(),
        root=tmp_path,
        root_element="PayDoc",
        allow_ai=True,
        llm=llm,
        on_progress=on_progress,
    )

    assert llm.calls >= 1
    assert any(v.startswith("git-ai:") for v in provenance.values())
    assert 'kladr="44444444444"' in result
    assert progress
    assert progress[0][0] == "git_ai"
    assert any("batch" in message.lower() or "1/" in message for _step, message, _percent in progress)


@pytest.mark.asyncio
async def test_git_ai_batches_multiple_fields_in_one_call(tmp_path: Path):
    schema = DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={
                    "kladr": AttributeDef(name="kladr", attr_type="CDATA", default_decl="#REQUIRED"),
                    "purpose": AttributeDef(
                        name="purpose", attr_type="CDATA", default_decl="#IMPLIED"
                    ),
                },
            )
        }
    )
    _write_ref(tmp_path, "PayDoc", "a.xml", '<PayDoc kladr="11111111111" purpose="alpha"/>')
    _write_ref(tmp_path, "PayDoc", "b.xml", '<PayDoc kladr="22222222222" purpose="bravo"/>')
    _write_ref(tmp_path, "PayDoc", "c.xml", '<PayDoc kladr="33333333333" purpose="charlie"/>')

    llm = _CountingLlm()
    result, _protected, _warnings, provenance = await git_fill.populate_from_git(
        '<PayDoc kladr="" purpose=""/>',
        schema,
        root=tmp_path,
        root_element="PayDoc",
        allow_ai=True,
        llm=llm,
    )
    assert llm.calls == 1
    assert any(v.startswith("git-ai:") for v in provenance.values())
    assert 'kladr="44444444444"' in result
    assert 'purpose="44444444444"' in result


@pytest.mark.asyncio
async def test_git_ai_batches_run_concurrently(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(git_fill, "_AI_BATCH_SIZE", 1)
    schema = DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={
                    "kladr": AttributeDef(name="kladr", attr_type="CDATA", default_decl="#REQUIRED"),
                    "purpose": AttributeDef(
                        name="purpose", attr_type="CDATA", default_decl="#IMPLIED"
                    ),
                },
            )
        }
    )
    _write_ref(tmp_path, "PayDoc", "a.xml", '<PayDoc kladr="11111111111" purpose="alpha"/>')
    _write_ref(tmp_path, "PayDoc", "b.xml", '<PayDoc kladr="22222222222" purpose="bravo"/>')
    _write_ref(tmp_path, "PayDoc", "c.xml", '<PayDoc kladr="33333333333" purpose="charlie"/>')

    class SlowLlm(_CountingLlm):
        async def complete_text(self, *, system_prompt: str, user_message: str, temperature: float = 0.7, **_kwargs) -> str:
            self.calls += 1
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            await asyncio.sleep(0.05)
            self.in_flight -= 1
            indexes = [int(match) for match in re.findall(r"\[(\d+)\] Path:", user_message)]
            if not indexes:
                indexes = [0]
            return json.dumps({"values": [{"i": i, "v": self.value} for i in indexes]})

    llm = SlowLlm()
    await git_fill.populate_from_git(
        '<PayDoc kladr="" purpose=""/>',
        schema,
        root=tmp_path,
        root_element="PayDoc",
        allow_ai=True,
        llm=llm,
    )
    assert llm.calls == 2
    assert llm.max_in_flight == 2


def test_parse_batch_ai_values_accepts_fenced_json():
    payload = '```json\n{"values": [{"i": 1, "v": "EUR"}, {"i": 0, "v": "USD"}]}\n```'
    assert git_fill._parse_batch_ai_values(payload) == {0: "USD", 1: "EUR"}
