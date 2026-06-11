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


def _load_env_files() -> None:
    """Load .env from cwd and known project locations."""
    candidates = [
        Path.cwd() / ".env",
        PROJECT_ROOT / ".env",
        BACKEND_ROOT / ".env",
    ]
    loaded: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in loaded or not path.exists():
            continue
        load_dotenv(path, override=True)
        loaded.add(resolved)


_load_env_files()


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


def has_oracle_databases() -> bool:
    """Return True when connections.json contains at least one Oracle alias."""
    connections = load_connections()
    return any(
        cfg.driver.lower() in {"oracle", "oracledb"}
        for cfg in connections.databases.values()
    )


def get_oracle_client_lib_dir() -> str | None:
    """Return Oracle client library directory from .env, connections.json, or ORACLE_HOME."""
    lib_dir = os.getenv("ORACLE_CLIENT_LIB_DIR", "").strip()
    if lib_dir:
        return lib_dir

    path = _find_connections_file()
    if path is not None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        lib_dir = raw.get("oracle_client_lib_dir", "").strip()
        if lib_dir:
            return lib_dir

    oracle_home = os.getenv("ORACLE_HOME", "").strip()
    if oracle_home:
        bin_dir = Path(oracle_home) / "bin"
        if (bin_dir / "oci.dll").is_file():
            return str(bin_dir)

    return None


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
