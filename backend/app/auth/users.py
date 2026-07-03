"""SQLite-backed user store."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import get_close_matches
from pathlib import Path

from app.config import DATA_DIR

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,64}$")


def _db_path() -> Path:
    return DATA_DIR / "users.db"


@dataclass(frozen=True)
class UserRecord:
    id: str
    username_norm: str
    display_name: str
    created_at: str
    last_seen: str


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> str:
    """Return display name after validation."""
    display = username.strip()
    if not display:
        raise ValueError("Username is required")
    if not _USERNAME_RE.match(display):
        raise ValueError(
            "Username may only contain letters, digits, underscore, hyphen, and dot (2-64 chars)"
        )
    return display


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username_norm TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        conn.commit()


def list_display_names() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT display_name FROM users ORDER BY display_name COLLATE NOCASE"
        ).fetchall()
    return [str(row["display_name"]) for row in rows]


def suggest_similar_usernames(username: str, *, limit: int = 5) -> list[str]:
    display = username.strip()
    if not display:
        return []
    names = list_display_names()
    if not names:
        return []
    matches = get_close_matches(display, names, n=limit, cutoff=0.6)
    return matches


def get_user_by_norm(username_norm: str) -> UserRecord | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username_norm = ?",
            (username_norm,),
        ).fetchone()
    if row is None:
        return None
    return UserRecord(
        id=str(row["id"]),
        username_norm=str(row["username_norm"]),
        display_name=str(row["display_name"]),
        created_at=str(row["created_at"]),
        last_seen=str(row["last_seen"]),
    )


def get_user_by_id(user_id: str) -> UserRecord | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return UserRecord(
        id=str(row["id"]),
        username_norm=str(row["username_norm"]),
        display_name=str(row["display_name"]),
        created_at=str(row["created_at"]),
        last_seen=str(row["last_seen"]),
    )


def touch_user(user_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_seen = ? WHERE id = ?",
            (now, user_id),
        )
        conn.commit()


def create_user(display_name: str) -> UserRecord:
    display = validate_username(display_name)
    norm = normalize_username(display)
    existing = get_user_by_norm(norm)
    if existing is not None:
        raise ValueError(f"User '{display}' already exists")

    now = datetime.now(UTC).isoformat()
    user_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username_norm, display_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, norm, display, now, now),
        )
        conn.commit()
    return UserRecord(
        id=user_id,
        username_norm=norm,
        display_name=display,
        created_at=now,
        last_seen=now,
    )


def user_data_root(user_id: str) -> Path:
    return DATA_DIR / "users" / user_id
