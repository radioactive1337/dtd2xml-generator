"""Fill XML attributes from the Git reference library (copy or AI-varied).

Policy summary
--------------
For each fillable attribute that has data in the Git reference corpus for the
same root element:

- ``deny_copy`` attributes (PII-ish, e.g. passport/account numbers) are never
  sourced from the corpus at all -- not copied, and not sent to the LLM as
  few-shot examples either. They're left for the normal Faker/AI stage that
  follows, which only ever sees the attribute *name*, never real corpus values.
- Enum-like / low-cardinality attributes (few distinct values relative to the
  number of reference documents) are copied from the corpus.
- High-cardinality / free-text attributes are handed to the LLM as a "vary
  this" task, seeded with a few corpus examples, then re-validated with
  ``attribute_rules_service`` before being accepted.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from lxml import etree

from app.core.dtd_models import AttributeDef, DTDSchema
from app.core.xml_tree import (
    ElementPath,
    ProtectedAttrs,
    element_dot_path,
    element_path,
    is_fillable_attribute_value,
)
from app.services import attribute_rules_service as rules_svc
from app.services import reference_xml_service as ref_service

logger = logging.getLogger(__name__)

FillMode = Literal["copy", "ai", "skip"]

# Below this many reference documents we don't trust the diversity ratio
# enough to pick "ai" -- too little data to tell an enum from free text.
_MIN_DOCS_FOR_AI_POLICY = 3
# If (distinct values / documents) is at or above this ratio, treat the
# attribute as free-text/identifier-like rather than enum-like.
_HIGH_DIVERSITY_RATIO = 0.6
_AI_FEW_SHOT_MAX = 10
_AI_MAX_ATTEMPTS = 2
_AI_MAX_CONCURRENT = 4

ProgressCallback = Callable[[str, str, int], Awaitable[None]]


class ChatCompleter(Protocol):
    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        cancel_event: asyncio.Event | None = None,
    ) -> str: ...


@dataclass
class AttributeCorpusStats:
    values: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # parallel to values: "category/filename"
    frequency: float = 0.0
    diversity: int = 0
    doc_count: int = 0
    filled_count: int = 0


@dataclass
class _AiFillJob:
    element: etree._Element
    attr_name: str
    attr_def: AttributeDef | None
    stats: AttributeCorpusStats
    dot: str
    tree_path: ElementPath


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _normalize_value(value: str) -> str:
    return (value or "").strip()


def _normalize_element_key(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", (text or "").lower())


def _iter_reference_docs(root: Path, root_element: str, category: str | None = None):
    """Yield reference entries for *root_element*, or from a specific *category*."""
    if category is not None:
        category_names = [category]
    else:
        category_names = [
            c.name for c in ref_service.list_categories(root, root_element=root_element)
        ]

    for name in category_names:
        try:
            docs = ref_service.list_documents(root, name)
        except Exception:
            continue
        for doc in docs:
            try:
                yield ref_service.load_document(root, name, doc.doc_id)
            except Exception:
                continue


def build_corpus(
    root: Path,
    root_element: str,
    *,
    category: str | None = None,
) -> dict[tuple[str, str], AttributeCorpusStats]:
    """Aggregate attribute values from reference docs sharing *root_element*.

    Returns a mapping ``(element_local_name, attr_name) -> AttributeCorpusStats``.
    Synchronous and does file I/O -- call via ``asyncio.to_thread`` from async code.
    """
    per_key_values: dict[tuple[str, str], list[str]] = defaultdict(list)
    per_key_sources: dict[tuple[str, str], list[str]] = defaultdict(list)
    per_key_filled_docs: dict[tuple[str, str], int] = defaultdict(int)
    doc_count = 0
    root_key = _normalize_element_key(root_element)

    for entry in _iter_reference_docs(root, root_element, category=category):
        try:
            tree_root = etree.fromstring(entry.xml_text.encode("utf-8"))
        except etree.XMLSyntaxError:
            continue
        if not isinstance(tree_root.tag, str):
            continue
        if category is None:
            # No explicit category: trust the root_element filter used to pick
            # categories, but double-check per-document since list_categories
            # only peeks the *first* file in each category.
            peeked = _local_name(tree_root.tag)
            if peeked != root_element and _normalize_element_key(peeked) != root_key:
                continue

        doc_count += 1
        source = f"{entry.category}/{entry.filename}"
        seen_keys: set[tuple[str, str]] = set()

        for el in tree_root.iter():
            if not isinstance(el.tag, str):
                continue
            elem_name = _local_name(el.tag)
            for attr_name, attr_value in el.attrib.items():
                if attr_name == "xmlns" or attr_name.startswith("xmlns:"):
                    continue
                normalized = _normalize_value(attr_value)
                if not normalized:
                    continue
                key = (elem_name, attr_name)
                per_key_values[key].append(normalized)
                per_key_sources[key].append(source)
                seen_keys.add(key)

        for key in seen_keys:
            per_key_filled_docs[key] += 1

    corpus: dict[tuple[str, str], AttributeCorpusStats] = {}
    for key, values in per_key_values.items():
        unique = set(values)
        filled = per_key_filled_docs.get(key, 0)
        corpus[key] = AttributeCorpusStats(
            values=values,
            sources=per_key_sources.get(key, []),
            frequency=(filled / doc_count) if doc_count else 0.0,
            diversity=len(unique),
            doc_count=doc_count,
            filled_count=filled,
        )
    return corpus


def choose_fill_mode(
    attr_def: AttributeDef | None,
    stats: AttributeCorpusStats | None,
    *,
    deny_copy: bool = False,
) -> FillMode:
    """Decide copy vs AI vs skip for a single attribute.

    ``deny_copy`` is the caller's single source of truth (from
    ``attribute_rules_service.is_deny_copy``) -- this function does not
    re-derive it, so it stays pure and easy to unit test.
    """
    if deny_copy:
        return "skip"
    if stats is None or not stats.values:
        return "skip"

    if attr_def is not None:
        if attr_def.attr_type == "ENUM" and attr_def.allowed_values:
            return "copy"
        if attr_def.dtd_default_value() is not None and len(attr_def.allowed_values) <= 1:
            return "copy"

    if stats.doc_count < _MIN_DOCS_FOR_AI_POLICY:
        # Too little data in the corpus to trust a diversity ratio; copying a
        # real (if possibly non-representative) sample beats guessing via AI.
        return "copy"

    diversity_ratio = stats.diversity / stats.doc_count
    if diversity_ratio >= _HIGH_DIVERSITY_RATIO:
        return "ai"
    return "copy"


def _pick_copy_value(stats: AttributeCorpusStats, *, seed: str | None = None) -> tuple[str, str]:
    """Return (value, source_label).

    Without a seed, picks randomly (default -- keeps generated documents
    varied across repeated fills). Pass an explicit seed only when
    reproducibility is required (e.g. debugging a specific bug report).
    """
    if not stats.values:
        raise ValueError("empty corpus stats")
    if seed:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % len(stats.values)
    else:
        index = random.randrange(len(stats.values))
    value = stats.values[index]
    source = stats.sources[index] if index < len(stats.sources) else "git"
    return value, f"git:{source}"


_GIT_AI_SYSTEM_PROMPT = (
    "You generate a single realistic alternative attribute value for QA test XML. "
    "Match the style and format of the provided examples. "
    "Return only the bare value, no quotes, no explanation, no XML."
)


def _clean_ai_value(content: str) -> str:
    value = (content or "").strip()
    fence = re.search(r"```(?:\w+)?\s*([\s\S]*?)```", value)
    if fence:
        value = fence.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value.splitlines()[0].strip() if value else ""


def _raise_if_cancelled(cancel_event: asyncio.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError("Git AI fill cancelled")


async def _generate_ai_value(
    llm: ChatCompleter,
    *,
    element: str,
    attr: str,
    examples: list[str],
    cancel_event: asyncio.Event | None = None,
) -> str:
    unique_examples: list[str] = []
    seen: set[str] = set()
    for value in examples:
        if value in seen:
            continue
        seen.add(value)
        unique_examples.append(value)
        if len(unique_examples) >= _AI_FEW_SHOT_MAX:
            break

    examples_block = "\n".join(f"- {ex}" for ex in unique_examples) or "(none)"
    user_message = (
        f"Element: {element}\n"
        f"Attribute: {attr}\n"
        f"Example values from reference corpus:\n{examples_block}\n\n"
        "Generate one alternative value that fits the same pattern but is not an "
        "exact copy of the examples when possible."
    )
    _raise_if_cancelled(cancel_event)
    content = await llm.complete_text(
        system_prompt=_GIT_AI_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.6,
        cancel_event=cancel_event,
    )
    return _clean_ai_value(content)


async def _generate_validated_ai_value(
    llm: ChatCompleter,
    *,
    element: str,
    attr: str,
    examples: list[str],
    attr_def,
    dot_path: str,
    ruleset,
    cancel_event: asyncio.Event | None = None,
) -> str | None:
    """Ask the LLM for a value and validate it, retrying on failure or error."""
    for attempt in range(_AI_MAX_ATTEMPTS):
        _raise_if_cancelled(cancel_event)
        try:
            candidate = await _generate_ai_value(
                llm,
                element=element,
                attr=attr,
                examples=examples,
                cancel_event=cancel_event,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Git AI fill request failed for %s@%s (attempt %d/%d): %s",
                element,
                attr,
                attempt + 1,
                _AI_MAX_ATTEMPTS,
                exc,
            )
            continue
        if not candidate:
            continue
        violations = rules_svc.validate_attribute(
            element,
            attr,
            candidate,
            context="git_ai_fill",
            path=dot_path,
            attr_def=attr_def,
            ruleset=ruleset,
        )
        if not any(v.severity == "error" for v in violations):
            return candidate
    return None


def _apply_ai_or_copy(
    job: _AiFillJob,
    validated: str | None,
    *,
    seed: str | None,
    newly_protected: set[tuple[tuple[tuple[str, int], ...], str]],
    provenance: dict[str, str],
    warnings: list[str],
) -> None:
    if validated is not None:
        applied_value = validated
        applied_source = f"git-ai:corpus(n={len(set(job.stats.values))})"
    else:
        applied_value, applied_source = _pick_copy_value(job.stats, seed=seed)
        warnings.append(f"Git AI fill fell back to copy for {job.dot}@{job.attr_name}")
    job.element.set(job.attr_name, applied_value)
    newly_protected.add((job.tree_path, job.attr_name))
    provenance[f"{job.dot}@{job.attr_name}"] = applied_source


async def _run_ai_fill_jobs(
    jobs: list[_AiFillJob],
    llm: ChatCompleter,
    *,
    seed: str | None,
    ruleset,
    newly_protected: set[tuple[tuple[tuple[str, int], ...], str]],
    provenance: dict[str, str],
    warnings: list[str],
    on_progress: ProgressCallback | None,
    cancel_event: asyncio.Event | None,
) -> None:
    """Generate Git-AI values concurrently and emit stream progress as they finish."""
    total = len(jobs)
    if on_progress:
        await on_progress(
            "git_ai",
            f"Generating {total} Git-based values via LLM...",
            41,
        )

    semaphore = asyncio.Semaphore(_AI_MAX_CONCURRENT)
    completed = 0
    progress_lock = asyncio.Lock()

    async def run_one(job: _AiFillJob) -> tuple[_AiFillJob, str | None]:
        nonlocal completed
        _raise_if_cancelled(cancel_event)
        async with semaphore:
            _raise_if_cancelled(cancel_event)
            try:
                validated = await _generate_validated_ai_value(
                    llm,
                    element=job.element.tag,
                    attr=job.attr_name,
                    examples=job.stats.values,
                    attr_def=job.attr_def,
                    dot_path=job.dot,
                    ruleset=ruleset,
                    cancel_event=cancel_event,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Git AI fill job failed for %s@%s: %s",
                    job.element.tag,
                    job.attr_name,
                    exc,
                )
                validated = None
        async with progress_lock:
            completed += 1
            if on_progress:
                percent = 41 + int((completed / total) * 3)
                await on_progress(
                    "git_ai",
                    f"Git AI fill {completed}/{total}",
                    min(percent, 44),
                )
        return job, validated

    results = await asyncio.gather(*(run_one(job) for job in jobs))
    for job, validated in results:
        _apply_ai_or_copy(
            job,
            validated,
            seed=seed,
            newly_protected=newly_protected,
            provenance=provenance,
            warnings=warnings,
        )


async def populate_from_git(
    xml_text: str,
    schema: DTDSchema,
    *,
    root: Path,
    root_element: str,
    fill_empty_only: bool = True,
    protected_attrs: ProtectedAttrs = frozenset(),
    llm: ChatCompleter | None = None,
    seed: str | None = None,
    allow_ai: bool = True,
    category: str | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> tuple[str, ProtectedAttrs, list[str], dict[str, str]]:
    """Fill attributes from the Git reference corpus.

    Returns ``(xml_text, newly_protected, warnings, provenance)``.
    Provenance keys are ``dotPath@attr``.
    """
    warnings: list[str] = []
    provenance: dict[str, str] = {}

    if not root.is_dir():
        warnings.append("Git reference library is not available; skipped git fill stage")
        return xml_text, frozenset(), warnings, provenance

    corpus = await asyncio.to_thread(build_corpus, root, root_element, category=category)
    if not corpus:
        warnings.append(
            f"No reference documents found for root element '{root_element}'; skipped git fill"
        )
        return xml_text, frozenset(), warnings, provenance

    try:
        tree = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        warnings.append(f"Git fill skipped: XML parse error: {exc}")
        return xml_text, frozenset(), warnings, provenance

    newly_protected: set[tuple[tuple[tuple[str, int], ...], str]] = set()
    ruleset = rules_svc.load_attribute_rules()
    skipped_denied: set[str] = set()
    ai_jobs: list[_AiFillJob] = []

    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        elem_def = schema.elements.get(el.tag)
        tree_path = element_path(el)
        dot = element_dot_path(el)

        for attr_name, attr_value in list(el.attrib.items()):
            if attr_name == "xmlns" or attr_name.startswith("xmlns:"):
                continue
            if (tree_path, attr_name) in protected_attrs or (tree_path, attr_name) in newly_protected:
                continue

            attr_def = elem_def.attributes.get(attr_name) if elem_def else None
            if fill_empty_only and not is_fillable_attribute_value(attr_value, attr_def=attr_def):
                continue

            stats = corpus.get((el.tag, attr_name)) or corpus.get((_local_name(el.tag), attr_name))
            deny = rules_svc.is_deny_copy(attr_name, ruleset)
            mode = choose_fill_mode(attr_def, stats, deny_copy=deny)

            if mode == "skip":
                if deny and stats is not None:
                    skipped_denied.add(attr_name)
                continue

            assert stats is not None
            if mode == "copy" or not allow_ai or llm is None:
                applied_value, applied_source = _pick_copy_value(stats, seed=seed)
                el.set(attr_name, applied_value)
                newly_protected.add((tree_path, attr_name))
                provenance[f"{dot}@{attr_name}"] = applied_source
            else:
                ai_jobs.append(
                    _AiFillJob(
                        element=el,
                        attr_name=attr_name,
                        attr_def=attr_def,
                        stats=stats,
                        dot=dot,
                        tree_path=tree_path,
                    )
                )

    if ai_jobs and llm is not None:
        await _run_ai_fill_jobs(
            ai_jobs,
            llm,
            seed=seed,
            ruleset=ruleset,
            newly_protected=newly_protected,
            provenance=provenance,
            warnings=warnings,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )

    if skipped_denied:
        warnings.append(
            "Git fill skipped for privacy-sensitive attributes (left for Faker/AI): "
            + ", ".join(sorted(skipped_denied))
        )

    xml_out = etree.tostring(
        tree,
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=False,
    ).decode("UTF-8")
    return xml_out, frozenset(newly_protected), warnings, provenance
