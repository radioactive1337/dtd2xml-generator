"""Resolve Git commit author identity from GitLab/GitHub APIs."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app.config import (
    ReferenceXmlSettings,
    get_user_git_author_email,
    get_user_git_author_name,
    resolve_git_auth,
    save_user_git_settings,
)
from app.user_context import UserContext

logger = logging.getLogger(__name__)


def _provider_api_base(repo_url: str) -> tuple[str, str] | None:
    url = repo_url.strip()
    host = ""
    if url.startswith("git@"):
        match = re.match(r"git@([^:]+):", url)
        host = match.group(1) if match else ""
    else:
        host = (urlparse(url).hostname or "").lower()

    if not host:
        return None
    if "gitlab" in host:
        return "gitlab", f"https://{host}"
    if host in {"github.com", "www.github.com"}:
        return "github", "https://api.github.com"
    return None


def _pick_gitlab_email(data: dict) -> str:
    for key in ("commit_email", "public_email", "email"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    user_id = data.get("id")
    username = str(data.get("username") or "").strip()
    if user_id and username:
        return f"{user_id}+{username}@users.noreply.gitlab.com"
    return ""


def _fetch_gitlab_identity(api_base: str, token: str) -> tuple[str, str] | None:
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                f"{api_base.rstrip('/')}/api/v4/user",
                headers={"PRIVATE-TOKEN": token},
            )
        if response.status_code != 200:
            logger.warning("GitLab user API returned %s", response.status_code)
            return None
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GitLab user API failed: %s", exc)
        return None

    name = str(data.get("name") or data.get("username") or "").strip()
    email = _pick_gitlab_email(data)
    if not name or not email:
        return None
    return name, email


def _fetch_github_identity(token: str) -> tuple[str, str] | None:
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code != 200:
            logger.warning("GitHub user API returned %s", response.status_code)
            return None
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GitHub user API failed: %s", exc)
        return None

    name = str(data.get("name") or data.get("login") or "").strip()
    email = str(data.get("email") or "").strip()
    if not email:
        user_id = data.get("id")
        login = str(data.get("login") or "").strip()
        if user_id and login:
            email = f"{user_id}+{login}@users.noreply.github.com"
    if not name or not email:
        return None
    return name, email


def fetch_git_author_identity(repo_url: str, token: str) -> tuple[str, str] | None:
    """Return (author_name, author_email) for the token owner, if the host is supported."""
    provider_info = _provider_api_base(repo_url)
    if provider_info is None:
        return None
    provider, api_base = provider_info
    if provider == "gitlab":
        return _fetch_gitlab_identity(api_base, token)
    if provider == "github":
        return _fetch_github_identity(token)
    return None


def ensure_git_commit_author(
    user: UserContext,
    settings: ReferenceXmlSettings,
) -> tuple[str, str]:
    name = get_user_git_author_name(user)
    email = get_user_git_author_email(user)
    if name and email:
        return name, email

    token, _ = resolve_git_auth(user)
    if token:
        identity = fetch_git_author_identity(settings.repo_url, token)
        if identity:
            save_user_git_settings(
                user,
                author_name=identity[0],
                author_email=identity[1],
            )
            return identity

    raise HTTPException(
        status_code=400,
        detail=(
            "Укажите имя и email автора коммитов в настройках Git. "
            "Email должен совпадать с email в вашем GitLab/GitHub аккаунте."
        ),
    )
