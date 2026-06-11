"""Application configuration loaded from local files only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Project root: xml-generator/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")


class AppSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class LLMConfig(BaseModel):
    alias: str
    base_url: str
    model: str
    # api_key is never exposed to the frontend


class DatabaseConfig(BaseModel):
    alias: str
    driver: str
    host: str
    port: int
    database: str
    user: str
    sid: str | None = None  # Oracle SID; if set, used instead of database (service name)
    # password is never exposed to the frontend


class ConnectionsConfig(BaseModel):
    databases: dict[str, DatabaseConfig] = Field(default_factory=dict)
    llm: dict[str, LLMConfig] = Field(default_factory=dict)


def _find_connections_file() -> Path | None:
    candidates = [
        PROJECT_ROOT / "connections.json",
        BACKEND_ROOT / "connections.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_connections() -> ConnectionsConfig:
    """Load connections.json; returns empty config if file is missing."""
    path = _find_connections_file()
    if path is None:
        return ConnectionsConfig()

    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    databases: dict[str, DatabaseConfig] = {}
    for alias, cfg in raw.get("databases", {}).items():
        databases[alias] = DatabaseConfig(alias=alias, **cfg)

    llm: dict[str, LLMConfig] = {}
    for alias, cfg in raw.get("llm", {}).items():
        llm[alias] = LLMConfig(alias=alias, **cfg)

    return ConnectionsConfig(databases=databases, llm=llm)


def get_llm_api_key(alias: str = "default") -> str:
    """Return LLM API key from connections.json or .env (server-side only)."""
    connections = load_connections()
    if alias in connections.llm:
        path = _find_connections_file()
        if path:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw.get("llm", {}).get(alias, {}).get("api_key", "")
    return os.getenv("LLM_API_KEY", "")


def get_db_password(alias: str) -> str:
    """Return DB password from connections.json (server-side only)."""
    path = _find_connections_file()
    if path is None:
        return ""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("databases", {}).get(alias, {}).get("password", "")


def get_oracle_thick_mode_settings() -> tuple[bool, str | None]:
    """Return whether to use Oracle thick mode and the Instant Client library path."""
    lib_dir = os.getenv("ORACLE_CLIENT_LIB_DIR", "").strip() or None
    use_thick = os.getenv("ORACLE_USE_THICK_MODE", "").lower() in {"1", "true", "yes"}

    path = _find_connections_file()
    if path is not None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not lib_dir:
            lib_dir = raw.get("oracle_client_lib_dir", "").strip() or None
        use_thick = use_thick or bool(raw.get("oracle_thick_mode", False))

    if lib_dir:
        use_thick = True

    return use_thick, lib_dir


def get_app_settings() -> AppSettings:
    return AppSettings(
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8080")),
    )


def get_connection_aliases() -> dict[str, list[str]]:
    """Return only aliases safe to expose in the UI."""
    connections = load_connections()
    return {
        "databases": list(connections.databases.keys()),
        "llm": list(connections.llm.keys()),
    }
