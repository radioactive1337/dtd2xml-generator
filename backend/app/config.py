"""Application configuration loaded from connections.json only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Project root: xml-generator/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class AppSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    default_llm_alias: str | None = None


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


def _load_raw_connections() -> dict[str, Any]:
    path = _find_connections_file()
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_connections() -> ConnectionsConfig:
    """Load connections.json; returns empty config if file is missing."""
    raw = _load_raw_connections()

    databases: dict[str, DatabaseConfig] = {}
    for alias, cfg in raw.get("databases", {}).items():
        databases[alias] = DatabaseConfig(alias=alias, **cfg)

    llm: dict[str, LLMConfig] = {}
    for alias, cfg in raw.get("llm", {}).items():
        llm[alias] = LLMConfig(alias=alias, **cfg)

    return ConnectionsConfig(databases=databases, llm=llm)


def get_default_llm_alias() -> str | None:
    """Return the configured default LLM alias, or None when no LLM is configured."""
    connections = load_connections()
    if not connections.llm:
        return None

    raw = _load_raw_connections()
    configured = str(raw.get("app", {}).get("default_llm_alias", "")).strip()
    if configured:
        if configured in connections.llm:
            return configured
        available = ", ".join(sorted(connections.llm))
        raise ValueError(
            f"app.default_llm_alias '{configured}' is not defined in llm section. "
            f"Available: {available}"
        )

    if "default" in connections.llm:
        return "default"

    if len(connections.llm) == 1:
        return next(iter(connections.llm))

    available = ", ".join(sorted(connections.llm))
    raise ValueError(
        f"Multiple LLM aliases configured ({available}). "
        "Set app.default_llm_alias in connections.json."
    )


def resolve_llm_alias(alias: str | None = None) -> str:
    """Resolve an explicit LLM alias or fall back to the configured default."""
    connections = load_connections()
    requested = (alias or "").strip()

    if requested and requested in connections.llm:
        return requested

    if requested and requested != "default":
        available = ", ".join(sorted(connections.llm)) or "(none)"
        raise ValueError(
            f"LLM alias '{requested}' is not configured. Available: {available}"
        )

    default = get_default_llm_alias()
    if default is None:
        raise ValueError("No LLM aliases configured in connections.json")
    return default


def get_llm_api_key(alias: str = "default") -> str:
    """Return LLM API key from connections.json (server-side only)."""
    resolved = resolve_llm_alias(alias)
    raw = _load_raw_connections()
    return raw.get("llm", {}).get(resolved, {}).get("api_key", "")


def get_db_password(alias: str) -> str:
    """Return DB password from connections.json (server-side only)."""
    raw = _load_raw_connections()
    return raw.get("databases", {}).get(alias, {}).get("password", "")


def has_oracle_databases() -> bool:
    """Return True when connections.json contains at least one Oracle alias."""
    connections = load_connections()
    return any(
        cfg.driver.lower() in {"oracle", "oracledb"}
        for cfg in connections.databases.values()
    )


def get_oracle_client_lib_dir() -> str | None:
    """Return Oracle client library directory from connections.json."""
    raw = _load_raw_connections()

    lib_dir = str(raw.get("oracle_client_lib_dir", "")).strip()
    if lib_dir:
        return lib_dir

    oracle_home = str(raw.get("oracle_home", "")).strip()
    if oracle_home:
        bin_dir = Path(oracle_home) / "bin"
        if (bin_dir / "oci.dll").is_file():
            return str(bin_dir)

    return None


def get_ora_tzfile() -> str | None:
    """Return optional ORA_TZFILE value from connections.json."""
    raw = _load_raw_connections()
    value = raw.get("ora_tzfile")
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def get_app_settings() -> AppSettings:
    raw = _load_raw_connections()
    app = raw.get("app", {})
    default_llm_alias = app.get("default_llm_alias")
    return AppSettings(
        host=app.get("host", "0.0.0.0"),
        port=int(app.get("port", 8080)),
        log_level=str(app.get("log_level", "INFO")),
        default_llm_alias=str(default_llm_alias).strip() or None
        if default_llm_alias is not None
        else None,
    )


def get_connection_aliases() -> dict[str, list[str] | str | None]:
    """Return only aliases safe to expose in the UI."""
    connections = load_connections()
    default_llm: str | None = None
    try:
        default_llm = get_default_llm_alias()
    except ValueError:
        default_llm = None

    return {
        "databases": list(connections.databases.keys()),
        "llm": list(connections.llm.keys()),
        "default_llm": default_llm,
    }


def set_default_llm_alias(alias: str) -> str:
    """Persist app.default_llm_alias in connections.json."""
    requested = alias.strip()
    if not requested:
        raise ValueError("LLM alias is required")

    connections = load_connections()
    if len(connections.llm) < 2:
        raise ValueError(
            "Default LLM alias can only be set when multiple LLM aliases are configured"
        )

    if requested not in connections.llm:
        available = ", ".join(sorted(connections.llm)) or "(none)"
        raise ValueError(
            f"LLM alias '{requested}' is not configured. Available: {available}"
        )

    path = _find_connections_file()
    if path is None:
        raise ValueError("connections.json not found")

    raw = json.loads(path.read_text(encoding="utf-8"))
    app = raw.setdefault("app", {})
    app["default_llm_alias"] = requested
    path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return requested
