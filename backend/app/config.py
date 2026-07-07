"""Application configuration: global app.json and per-user connections."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Project root: xml-generator/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
APP_CONFIG_FILE = CONFIG_DIR / "app.json"
APP_CONFIG_EXAMPLE = CONFIG_DIR / "app.json.example"
USER_CONNECTIONS_TEMPLATE = CONFIG_DIR / "connections.json.example"

DEV_USER_ID = "dev-local"


class AppSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    session_secret: str | None = None
    allow_self_registration: bool = True


class LLMConfig(BaseModel):
    alias: str
    base_url: str
    model: str
    timeout: float = 120.0


class DatabaseConfig(BaseModel):
    alias: str
    driver: str
    host: str
    port: int
    database: str
    user: str
    sid: str | None = None


class ConnectionsConfig(BaseModel):
    databases: dict[str, DatabaseConfig] = Field(default_factory=dict)
    llm: dict[str, LLMConfig] = Field(default_factory=dict)


class ReferenceXmlSettings(BaseModel):
    enabled: bool = False
    repo_url: str = ""
    branch: str = "main"
    subdir: str = "xml-library"
    cache_dir: str = "data/reference-xml"
    push_enabled: bool = False
    push_cache_dir: str = "data/reference-xml-push"
    push_author_name: str = "XML Generator"
    push_author_email: str = "xmlgenerator@noreply"


def is_auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").strip().lower() in {"1", "true", "yes"}


def is_allow_self_registration() -> bool:
    env = os.getenv("ALLOW_SELF_REGISTRATION", "").strip().lower()
    if env in {"0", "false", "no"}:
        return False
    if env in {"1", "true", "yes"}:
        return True
    return load_app_settings().allow_self_registration


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _find_legacy_connections_file() -> Path | None:
    candidates = [
        CONFIG_DIR / "connections.json",
        PROJECT_ROOT / "connections.json",
        BACKEND_ROOT / "connections.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _connections_path_for_user(user: "UserContext") -> Path:
    if is_auth_disabled() and user.user_id == DEV_USER_ID:
        legacy = _find_legacy_connections_file()
        if legacy is not None:
            return legacy
    return user.connections_path


def _load_raw_user_connections(user: "UserContext") -> dict[str, Any]:
    path = _connections_path_for_user(user)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw_user_connections(user: "UserContext", raw: dict[str, Any]) -> None:
    path = _connections_path_for_user(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_raw_app_config() -> dict[str, Any]:
    raw = _load_json_file(APP_CONFIG_FILE)
    if raw:
        return raw

    legacy = _find_legacy_connections_file()
    if legacy is not None:
        legacy_raw = _load_json_file(legacy)
        merged: dict[str, Any] = {"app": legacy_raw.get("app", {})}
        for key in ("oracle_client_lib_dir", "oracle_home", "ora_tzfile"):
            if key in legacy_raw:
                merged[key] = legacy_raw[key]
        return merged
    return {}


def load_app_settings() -> AppSettings:
    raw = _load_raw_app_config()
    app = raw.get("app", {})
    env_secret = os.getenv("SESSION_SECRET", "").strip()
    session_secret = env_secret or str(app.get("session_secret", "")).strip() or None
    allow_reg = app.get("allow_self_registration", True)
    if isinstance(allow_reg, str):
        allow_reg = allow_reg.lower() not in {"0", "false", "no"}
    return AppSettings(
        host=str(app.get("host", "0.0.0.0")),
        port=int(app.get("port", 8080)),
        log_level=str(app.get("log_level", "INFO")),
        session_secret=session_secret,
        allow_self_registration=bool(allow_reg),
    )


def get_app_settings() -> AppSettings:
    """Backward-compatible alias."""
    return load_app_settings()


def get_session_secret() -> str:
    settings = load_app_settings()
    if settings.session_secret:
        return settings.session_secret
    env = os.getenv("SESSION_SECRET", "").strip()
    if env:
        return env
    return "dev-insecure-session-secret-change-me"


def ensure_app_config() -> None:
    """Create app.json from example and generate session secret if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not APP_CONFIG_FILE.is_file():
        if APP_CONFIG_EXAMPLE.is_file():
            APP_CONFIG_FILE.write_text(
                APP_CONFIG_EXAMPLE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            APP_CONFIG_FILE.write_text(
                json.dumps(
                    {
                        "app": {
                            "host": "0.0.0.0",
                            "port": 8080,
                            "log_level": "INFO",
                            "allow_self_registration": True,
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    raw = _load_raw_app_config()
    app = raw.setdefault("app", {})
    if not str(app.get("session_secret", "")).strip() and not os.getenv("SESSION_SECRET"):
        app["session_secret"] = secrets.token_urlsafe(32)
        APP_CONFIG_FILE.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def load_connections(user: "UserContext") -> ConnectionsConfig:
    raw = _load_raw_user_connections(user)
    databases: dict[str, DatabaseConfig] = {}
    for alias, cfg in raw.get("databases", {}).items():
        databases[alias] = DatabaseConfig(alias=alias, **cfg)
    llm: dict[str, LLMConfig] = {}
    for alias, cfg in raw.get("llm", {}).items():
        llm[alias] = LLMConfig(alias=alias, **cfg)
    return ConnectionsConfig(databases=databases, llm=llm)


def get_default_llm_alias(user: "UserContext") -> str | None:
    connections = load_connections(user)
    if not connections.llm:
        return None

    raw = _load_raw_user_connections(user)
    configured_raw = raw.get("app", {}).get("default_llm_alias")
    configured = (
        str(configured_raw).strip()
        if configured_raw is not None and str(configured_raw).strip()
        else ""
    )
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
        "Set app.default_llm_alias in connections."
    )


def resolve_llm_alias(user: "UserContext", alias: str | None = None) -> str:
    connections = load_connections(user)
    requested = (alias or "").strip()

    if requested and requested in connections.llm:
        return requested

    if requested and requested != "default":
        available = ", ".join(sorted(connections.llm)) or "(none)"
        raise ValueError(
            f"LLM alias '{requested}' is not configured. Available: {available}"
        )

    default = get_default_llm_alias(user)
    if default is None:
        raise ValueError("No LLM aliases configured")
    return default


def get_llm_api_key(user: "UserContext", alias: str = "default") -> str:
    resolved = resolve_llm_alias(user, alias)
    raw = _load_raw_user_connections(user)
    return raw.get("llm", {}).get(resolved, {}).get("api_key", "")


def get_db_password(user: "UserContext", alias: str) -> str:
    raw = _load_raw_user_connections(user)
    return raw.get("databases", {}).get(alias, {}).get("password", "")


def has_oracle_databases(user: "UserContext") -> bool:
    connections = load_connections(user)
    return any(
        cfg.driver.lower() in {"oracle", "oracledb"}
        for cfg in connections.databases.values()
    )


def _optional_config_str(value: Any) -> str | None:
    """Normalize optional JSON config values; treat null and empty as unset."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def _dir_has_oracle_client_lib(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    for name in ("oci.dll", "libclntsh.so"):
        if (directory / name).is_file():
            return True
    return any(directory.glob("libclntsh.so*"))


def get_oracle_client_lib_dir() -> str | None:
    raw = _load_raw_app_config()
    lib_dir = _optional_config_str(raw.get("oracle_client_lib_dir"))
    if lib_dir:
        return lib_dir

    oracle_home = _optional_config_str(raw.get("oracle_home"))
    if oracle_home:
        home = Path(oracle_home)
        for candidate in (home, home / "bin"):
            if _dir_has_oracle_client_lib(candidate):
                return str(candidate)

    return None


def get_ora_tzfile() -> str | None:
    raw = _load_raw_app_config()
    value = raw.get("ora_tzfile")
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def get_connection_aliases(user: "UserContext") -> dict[str, list[str] | str | None]:
    connections = load_connections(user)
    default_llm: str | None = None
    try:
        default_llm = get_default_llm_alias(user)
    except ValueError:
        default_llm = None

    return {
        "databases": list(connections.databases.keys()),
        "llm": list(connections.llm.keys()),
        "default_llm": default_llm,
    }


def set_default_llm_alias(user: "UserContext", alias: str) -> str:
    requested = alias.strip()
    if not requested:
        raise ValueError("LLM alias is required")

    connections = load_connections(user)
    if len(connections.llm) < 2:
        raise ValueError(
            "Default LLM alias can only be set when multiple LLM aliases are configured"
        )

    if requested not in connections.llm:
        available = ", ".join(sorted(connections.llm)) or "(none)"
        raise ValueError(
            f"LLM alias '{requested}' is not configured. Available: {available}"
        )

    raw = _load_raw_user_connections(user)
    app = raw.setdefault("app", {})
    app["default_llm_alias"] = requested
    _save_raw_user_connections(user, raw)
    return requested


def save_user_connections_raw(user: "UserContext", raw: dict[str, Any]) -> None:
    _save_raw_user_connections(user, raw)


def get_reference_xml_settings() -> ReferenceXmlSettings | None:
    raw = _load_raw_app_config()
    ref = raw.get("reference_xml")
    if not ref or not isinstance(ref, dict):
        return None
    settings = ReferenceXmlSettings(**ref)
    if not settings.enabled:
        return None
    return settings


def reference_xml_root() -> Path | None:
    settings = get_reference_xml_settings()
    if settings is None:
        return None
    cache = Path(settings.cache_dir)
    if not cache.is_absolute():
        cache = PROJECT_ROOT / cache
    return cache / settings.subdir


def reference_xml_cache_dir() -> Path | None:
    settings = get_reference_xml_settings()
    if settings is None:
        return None
    cache = Path(settings.cache_dir)
    if not cache.is_absolute():
        cache = PROJECT_ROOT / cache
    return cache


def reference_xml_push_cache_dir() -> Path | None:
    settings = get_reference_xml_settings()
    if settings is None:
        return None
    cache = Path(settings.push_cache_dir)
    if not cache.is_absolute():
        cache = PROJECT_ROOT / cache
    return cache


# Legacy helpers for tests that patch _find_connections_file
def _find_connections_file() -> Path | None:
    return _find_legacy_connections_file()
