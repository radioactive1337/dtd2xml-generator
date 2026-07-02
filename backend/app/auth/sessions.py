"""Signed cookie session helpers."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, HTTPException, Request
from starlette.middleware.sessions import SessionMiddleware

from app.auth.users import UserRecord, get_user_by_id, touch_user
from app.config import get_session_secret, is_auth_disabled
from app.user_context import UserContext, dev_user_context, get_user_context_for_session

SESSION_USER_ID = "user_id"
SESSION_DISPLAY_NAME = "display_name"


def install_session_middleware(app) -> None:
    app.add_middleware(
        SessionMiddleware,
        secret_key=get_session_secret(),
        session_cookie="xmlgen_session",
        max_age=60 * 60 * 24 * 30,
        same_site="lax",
        https_only=os.getenv("SESSION_SECURE", "").lower() in {"1", "true", "yes"},
    )


def set_session_user(request: Request, user: UserRecord) -> None:
    request.session[SESSION_USER_ID] = user.id
    request.session[SESSION_DISPLAY_NAME] = user.display_name
    touch_user(user.id)


def clear_session(request: Request) -> None:
    request.session.clear()


def get_session_user_id(request: Request) -> str | None:
    value = request.session.get(SESSION_USER_ID)
    if not value:
        return None
    return str(value)


async def get_current_user(request: Request) -> UserContext:
    if is_auth_disabled():
        return dev_user_context()

    user_id = get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    record = get_user_by_id(user_id)
    if record is None:
        clear_session(request)
        raise HTTPException(status_code=401, detail="Session expired")

    return get_user_context_for_session(record.id, record.display_name)


async def get_optional_user(request: Request) -> UserContext | None:
    if is_auth_disabled():
        return dev_user_context()
    user_id = get_session_user_id(request)
    if not user_id:
        return None
    record = get_user_by_id(user_id)
    if record is None:
        return None
    return get_user_context_for_session(record.id, record.display_name)


CurrentUser = Depends(get_current_user)
