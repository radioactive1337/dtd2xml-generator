"""Authentication API routes (passwordless username login)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth.sessions import clear_session, set_session_user
from app.auth.users import (
    create_user,
    get_user_by_norm,
    normalize_username,
    suggest_similar_usernames,
    validate_username,
)
from app.config import is_allow_self_registration
from app.legacy_migration import migrate_legacy_data_to_user
from app.user_context import user_context_from_record

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    create: bool = False


class UserResponse(BaseModel):
    id: str
    display_name: str


class ExistsResponse(BaseModel):
    exists: bool
    suggestions: list[str]


class LoginConflictResponse(BaseModel):
    detail: str
    suggestions: list[str]


@router.get("/exists", response_model=ExistsResponse)
async def check_username_exists(username: str = Query(..., min_length=1)) -> ExistsResponse:
    try:
        display = validate_username(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    norm = normalize_username(display)
    exists = get_user_by_norm(norm) is not None
    suggestions: list[str] = []
    if not exists:
        suggestions = suggest_similar_usernames(display)
    return ExistsResponse(exists=exists, suggestions=suggestions)


@router.post("/login", response_model=UserResponse)
async def login(request: Request, body: LoginRequest) -> UserResponse:
    try:
        display = validate_username(body.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    norm = normalize_username(display)
    record = get_user_by_norm(norm)

    if record is None:
        if not body.create:
            suggestions = suggest_similar_usernames(display)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"User '{display}' not found. Confirm creation or fix the username.",
                    "suggestions": suggestions,
                },
            )
        if not is_allow_self_registration():
            raise HTTPException(status_code=403, detail="Self-registration is disabled")
        record = create_user(display)
        ctx = user_context_from_record(record)
        migrate_legacy_data_to_user(ctx)

    set_session_user(request, record)
    return UserResponse(id=record.id, display_name=record.display_name)


@router.post("/logout")
async def logout(request: Request) -> dict[str, str]:
    clear_session(request)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(request: Request) -> UserResponse:
    from app.auth.sessions import get_session_user_id

    user_id = get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from app.auth.users import get_user_by_id

    record = get_user_by_id(user_id)
    if record is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return UserResponse(id=record.id, display_name=record.display_name)
