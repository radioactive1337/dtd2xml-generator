"""Authentication API routes (passwordless username login)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth.sessions import clear_session, get_current_user, set_session_user
from app.auth.users import (
    create_user,
    get_user_by_norm,
    normalize_username,
    search_usernames,
    suggest_similar_usernames,
    validate_username,
)
from app.config import is_allow_self_registration
from app.legacy_migration import migrate_legacy_data_to_user
from app.user_context import UserContext, user_context_from_record

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    create: bool = False


class UserResponse(BaseModel):
    id: str
    display_name: str
    is_admin: bool = False


class ExistsResponse(BaseModel):
    exists: bool
    suggestions: list[str]


class UserSearchResponse(BaseModel):
    exact_match: bool
    matches: list[str]


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


@router.get("/users/search", response_model=UserSearchResponse)
async def search_users(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=8, ge=1, le=20),
    user: UserContext = Depends(get_current_user),
) -> UserSearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query is required")

    norm = normalize_username(query)
    exact_match = get_user_by_norm(norm) is not None
    if exact_match:
        record = get_user_by_norm(norm)
        if record is not None and record.id == user.user_id:
            exact_match = False

    matches = search_usernames(query, limit=limit, exclude_user_id=user.user_id)
    return UserSearchResponse(exact_match=exact_match, matches=matches)


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
    return UserResponse(
        id=record.id,
        display_name=record.display_name,
        is_admin=record.is_admin,
    )


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
    return UserResponse(
        id=record.id,
        display_name=record.display_name,
        is_admin=record.is_admin,
    )
