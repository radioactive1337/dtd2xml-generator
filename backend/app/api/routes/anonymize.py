"""XML anonymization endpoints: analyze, apply, rules, category suggestions.

Privacy: request bodies carry real personal data. Handlers never log values,
never write the XML to disk and never put it into the server-side XML cache
used by the fill pipeline.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.routes.dtd import get_merged_schema
from app.auth.sessions import get_current_user
from app.config import resolve_llm_alias
from app.core.dtd_models import DTDSchema
from app.core.dtd_validator import validate_xml
from app.services.anonymize import llm_assist
from app.services.anonymize.categories import CATEGORIES, CATEGORY_IDS
from app.services.anonymize.engine import (
    AnonymizeError,
    Options,
    Override,
    analyze_document,
    apply_anonymization,
    collect_free_text,
    queue_to_dict,
)
from app.services.anonymize.rules import (
    AnonRule,
    anonymize_dir,
    delete_global_rule,
    delete_user_rule,
    get_user_secret,
    load_effective_rules,
    load_global_rules,
    load_user_rules,
    parse_rules,
    promote_user_rule,
    save_user_rules,
    upsert_user_rules,
)
from app.services.attribute_rules_service import validate_document
from app.services.llm_service import LLMService
from app.user_context import UserContext

router = APIRouter(prefix="/anonymize", tags=["anonymize"])
logger = logging.getLogger(__name__)

MAX_XML_CHARS = 8_000_000

Consistency = Literal["document", "user", "project"]


class OverrideModel(BaseModel):
    key: str
    action: Literal["replace", "keep", "skip"]
    category: str | None = None


class AnonymizeBase(BaseModel):
    xml_text: str = Field(..., min_length=1, max_length=MAX_XML_CHARS)
    schema_id: str | None = None
    categories: list[str] | None = None
    strip_comments: bool = True
    overrides: list[OverrideModel] = Field(default_factory=list)


class AnalyzeRequest(AnonymizeBase):
    pass


class ApplyRequest(AnonymizeBase):
    consistency: Consistency = "document"
    seed: str | None = None
    use_llm: bool = False
    llm_alias: str | None = None
    validate_result: bool = True


class RulesBody(BaseModel):
    rules: list[AnonRule] = Field(default_factory=list)


class RulesImportBody(BaseModel):
    rules: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["merge", "replace"] = "merge"


class PromoteRuleBody(BaseModel):
    rule_id: str = Field(min_length=1, max_length=200)


class SuggestItem(BaseModel):
    key: str
    element: str = ""
    attr: str = ""
    name: str = ""
    doc: str = ""
    sample: str = ""


class SuggestRequest(BaseModel):
    items: list[SuggestItem] = Field(default_factory=list)
    schema_id: str | None = None
    include_samples: bool = False
    llm_alias: str | None = None
    limit: int = Field(default=300, ge=1, le=1000)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _load_schema(user: UserContext, schema_id: str | None) -> DTDSchema | None:
    if not schema_id:
        return None
    return get_merged_schema(user, schema_id)


def _build_options(request: AnonymizeBase, key: bytes, schema: DTDSchema | None) -> Options:
    if request.categories is not None:
        unknown = [c for c in request.categories if c not in CATEGORY_IDS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Неизвестные категории: {', '.join(unknown)}")
    overrides: dict[str, Override] = {}
    for item in request.overrides:
        if item.action == "replace" and item.category not in CATEGORY_IDS:
            raise HTTPException(
                status_code=400, detail=f"Для правила замены нужна категория (поле {item.key})"
            )
        overrides[item.key] = Override(action=item.action, category=item.category)
    return Options(
        key=key,
        enabled_categories=frozenset(request.categories) if request.categories is not None else None,
        strip_comments=request.strip_comments,
        overrides=overrides,
        schema=schema,
    )


def _derive_key(user: UserContext, consistency: Consistency, seed: str | None) -> bytes:
    if consistency == "project":
        if not seed or not seed.strip():
            raise HTTPException(status_code=400, detail="Для режима «общий seed» укажите seed проекта")
        return hashlib.sha256(("xmlgen-anon-seed:" + seed.strip()).encode("utf-8")).digest()
    if consistency == "user":
        return get_user_secret(user)
    return secrets.token_bytes(32)


def _suggestion_cache_path(user: UserContext):
    return anonymize_dir(user) / "suggestions.json"


def _load_suggestion_cache(user: UserContext) -> dict[str, dict[str, str]]:
    path = _suggestion_cache_path(user)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_suggestion_cache(user: UserContext, cache: dict[str, dict[str, str]]) -> None:
    _suggestion_cache_path(user).write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _rule_dict(rule: AnonRule, layer: str) -> dict[str, Any]:
    data = rule.model_dump(exclude_none=True)
    data["layer"] = layer
    return data


def _compare_validation(
    original_body: str, result_body: str, schema: DTDSchema
) -> dict[str, Any]:
    """Check the anonymized XML did not break attribute rules or the DTD."""
    before = validate_document(original_body, schema, context="post_fill")
    after = validate_document(result_body, schema, context="post_fill")

    def sig(v: Any) -> tuple[str, str, str]:
        return (v.rule_id, v.path, v.attr)

    seen = {sig(v) for v in before.errors}
    new_errors = [v for v in after.errors if sig(v) not in seen]

    dtd_before = validate_xml(original_body, schema)
    dtd_after = validate_xml(result_body, schema)
    return {
        "rules": {
            "errors_before": len(before.errors),
            "errors_after": len(after.errors),
            "new_errors": [
                {"path": v.path, "attr": v.attr, "message": v.message, "line": v.line}
                for v in new_errors[:20]
            ],
        },
        "dtd": {
            "valid_before": dtd_before.valid,
            "valid_after": dtd_after.valid,
            "errors_after": [
                {"line": e.line, "message": e.message} for e in dtd_after.errors[:10]
            ],
        },
    }


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@router.get("/categories")
async def list_categories(_user: UserContext = Depends(get_current_user)) -> dict[str, Any]:
    return {"categories": [{"id": c.id, "label": c.label, "group": c.group} for c in CATEGORIES]}


@router.post("/analyze")
async def analyze(
    request: AnalyzeRequest,
    user: UserContext = Depends(get_current_user),
) -> dict[str, Any]:
    schema = _load_schema(user, request.schema_id)
    opts = _build_options(request, b"analyze-only", schema)
    rules = load_effective_rules(user)
    try:
        result = await asyncio.to_thread(analyze_document, request.xml_text, rules, opts)
    except AnonymizeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cache = _load_suggestion_cache(user).get(request.schema_id or "", {})
    queue = []
    for item in result.queue:
        data = queue_to_dict(item)
        llm_category = cache.get(f"{item.element}|{item.attr}|")
        data["llm_category"] = None if llm_category in (None, "none") else llm_category
        queue.append(data)

    logger.info(
        "Anonymize analyze [user=%s values=%d replace=%d unclassified=%d]",
        user.display_name,
        result.stats["total_values"],
        result.stats["replace"],
        result.stats["unclassified"],
    )
    return {
        "root_element": result.root_element,
        "findings": result.findings,
        "findings_truncated": result.findings_truncated,
        "unclassified": queue,
        "stats": result.stats,
    }


@router.post("/apply")
async def apply(
    request: ApplyRequest,
    user: UserContext = Depends(get_current_user),
) -> dict[str, Any]:
    schema = _load_schema(user, request.schema_id)
    key = _derive_key(user, request.consistency, request.seed)
    opts = _build_options(request, key, schema)
    rules = load_effective_rules(user)
    warnings: list[str] = []
    llm_info: dict[str, Any] = {"used": False}

    if request.use_llm:
        try:
            alias = resolve_llm_alias(user, request.llm_alias)
            texts = await asyncio.to_thread(collect_free_text, request.xml_text, rules, opts)
        except AnonymizeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            warnings.append(f"ИИ-поиск пропущен: {exc}")
            alias, texts = "", []
        if texts:
            llm_info = {"used": True, "alias": alias, "texts_sent": len(texts)}
            entities, llm_warnings = await llm_assist.find_entities(
                LLMService(user, alias=alias), texts
            )
            opts.extra_entities = entities
            llm_info["entities_found"] = len(entities)
            warnings.extend(llm_warnings)

    try:
        result = await asyncio.to_thread(apply_anonymization, request.xml_text, rules, opts)
    except AnonymizeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report = result.report
    report["warnings"] = [*report.get("warnings", []), *warnings]
    report["llm"] = llm_info
    report["consistency"] = request.consistency
    if schema is not None and request.validate_result:
        try:
            report["validation"] = await asyncio.to_thread(
                _compare_validation, result.original_body, result.body_text, schema
            )
        except Exception as exc:  # noqa: BLE001 - validation is advisory
            logger.warning("Anonymize post-validation failed: %s", type(exc).__name__)
            report["warnings"].append("Не удалось проверить результат по правилам/DTD")

    logger.info(
        "Anonymize apply [user=%s replaced=%d unclassified=%d sweep=%d llm=%s]",
        user.display_name,
        report["replaced"],
        report["stats"]["unclassified"],
        report["sweep"]["replacements"],
        llm_info["used"],
    )
    return {"xml_text": result.xml_text, "report": report}


# -- rules -------------------------------------------------------------------


@router.get("/rules")
async def get_rules(user: UserContext = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "global": [_rule_dict(r, "global") for r in load_global_rules()],
        "user": [_rule_dict(r, "user") for r in load_user_rules(user)],
    }


@router.put("/rules")
async def put_rules(body: RulesBody, user: UserContext = Depends(get_current_user)) -> dict[str, Any]:
    merged = upsert_user_rules(user, list(body.rules), replace_all=True)
    return {"user": [_rule_dict(r, "user") for r in merged]}


@router.post("/rules/upsert")
async def upsert_rules(body: RulesBody, user: UserContext = Depends(get_current_user)) -> dict[str, Any]:
    merged = upsert_user_rules(user, list(body.rules))
    return {"user": [_rule_dict(r, "user") for r in merged]}


@router.post("/rules/promote")
async def promote_rule(
    body: PromoteRuleBody, user: UserContext = Depends(get_current_user)
) -> dict[str, Any]:
    """Move one personal rule into the shared ``config/anonymize_rules.json``."""
    try:
        promote_user_rule(user, body.rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Правило не найдено в личных правилах") from None
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("Failed to write shared anonymize rules")
        raise HTTPException(status_code=500, detail="Не удалось записать общие правила") from None
    logger.info("Promoted anonymize rule %s to shared [user=%s]", body.rule_id, user.display_name)
    return {
        "global": [_rule_dict(r, "global") for r in load_global_rules()],
        "user": [_rule_dict(r, "user") for r in load_user_rules(user)],
    }


@router.delete("/rules/global/{rule_id}")
async def remove_global_rule(
    rule_id: str, user: UserContext = Depends(get_current_user)
) -> dict[str, Any]:
    try:
        removed = delete_global_rule(rule_id)
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("Failed to write shared anonymize rules")
        raise HTTPException(status_code=500, detail="Не удалось записать общие правила") from None
    if not removed:
        raise HTTPException(status_code=404, detail="Общее правило не найдено")
    logger.info("Deleted shared anonymize rule %s [user=%s]", rule_id, user.display_name)
    return {"global": [_rule_dict(r, "global") for r in load_global_rules()]}


@router.delete("/rules/{rule_id}")
async def remove_rule(rule_id: str, user: UserContext = Depends(get_current_user)) -> dict[str, str]:
    if not delete_user_rule(user, rule_id):
        raise HTTPException(status_code=404, detail="Правило не найдено в личных правилах")
    return {"status": "ok"}


@router.post("/rules/import")
async def import_rules(
    body: RulesImportBody, user: UserContext = Depends(get_current_user)
) -> dict[str, Any]:
    parsed = parse_rules(body.rules, source="import", layer="user")
    skipped = len(body.rules) - len(parsed)
    for rule in parsed:
        # Imported ids belong to someone else's file; assign our own.
        rule.id = ""
        rule.created_by = ""
        rule.created_at = ""
    merged = upsert_user_rules(user, parsed, replace_all=body.mode == "replace")
    return {
        "imported": len(parsed),
        "skipped": skipped,
        "user": [_rule_dict(r, "user") for r in merged],
    }


@router.get("/rules/export")
async def export_rules(
    layer: Literal["user", "all"] = Query("user"),
    user: UserContext = Depends(get_current_user),
) -> JSONResponse:
    rules = load_user_rules(user)
    if layer == "all":
        rules = [*load_global_rules(), *rules]
    payload = {"version": 1, "rules": [r.model_dump(exclude_none=True) for r in rules]}
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="anonymize_rules.json"'},
    )


@router.delete("/rules")
async def clear_user_rules(user: UserContext = Depends(get_current_user)) -> dict[str, str]:
    save_user_rules(user, [])
    return {"status": "ok"}


# -- LLM category suggestions ---------------------------------------------------


@router.post("/suggest-categories")
async def suggest_categories_route(
    request: SuggestRequest,
    user: UserContext = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        alias = resolve_llm_alias(user, request.llm_alias)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    llm = LLMService(user, alias=alias)

    items = [i.model_dump() for i in request.items]
    remaining = 0
    schema_cache: dict[str, dict[str, str]] = {}

    if not items and request.schema_id:
        schema = _load_schema(user, request.schema_id)
        assert schema is not None
        rules = load_effective_rules(user)
        schema_cache = _load_suggestion_cache(user)
        known = schema_cache.setdefault(request.schema_id, {})
        pending: list[dict[str, Any]] = []
        for elem in schema.elements.values():
            for attr in elem.attributes.values():
                if attr.allowed_values or attr.is_declared_default():
                    continue
                key = f"{elem.name}|{attr.name}|"
                if key in known or rules.match(elem.name, attr.name, {}) is not None:
                    continue
                pending.append(
                    {"key": key, "element": elem.name, "attr": attr.name, "doc": attr.doc}
                )
        remaining = max(0, len(pending) - request.limit)
        items = pending[: request.limit]

    if not items:
        return {"suggestions": {}, "processed": 0, "remaining": remaining, "warnings": []}

    suggestions, warnings = await llm_assist.suggest_categories(
        llm, items, include_samples=request.include_samples
    )

    if request.schema_id and schema_cache:
        known = schema_cache.setdefault(request.schema_id, {})
        for key, category in suggestions.items():
            known[key] = category or "none"
        _save_suggestion_cache(user, schema_cache)
        remaining += len(items) - len(suggestions)

    return {
        "suggestions": suggestions,
        "processed": len(suggestions),
        "remaining": remaining,
        "warnings": warnings,
        "alias": alias,
    }
