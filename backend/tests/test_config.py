"""Tests for connections.json configuration loading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import (
    _find_connections_file,
    get_app_settings,
    get_connection_aliases,
    get_db_password,
    get_default_llm_alias,
    get_llm_api_key,
    get_ora_tzfile,
    get_oracle_client_lib_dir,
    load_connections,
    resolve_llm_alias,
    set_default_llm_alias,
)
from app.user_context import UserContext


@pytest.fixture
def connections_file(tmp_path: Path):
    config = {
        "app": {"default_llm_alias": None},
        "databases": {
            "PGSQL_DB": {
                "driver": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "qa_auto",
                "user": "qa_user",
                "password": "db-secret",
            }
        },
        "llm": {
            "default": {
                "base_url": "http://localhost:11434/v1",
                "api_key": "llm-secret",
                "model": "gpt-4o-mini",
            }
        },
    }
    path = tmp_path / "connections.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.fixture
def user_with_connections(tmp_path: Path, connections_file: Path) -> UserContext:
    root = tmp_path / "user"
    root.mkdir(parents=True, exist_ok=True)
    target = root / "connections.json"
    target.write_text(connections_file.read_text(encoding="utf-8"), encoding="utf-8")
    return UserContext(user_id="cfg-user", display_name="cfg", root=root)


@pytest.fixture
def app_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app_json = {
        "app": {
            "host": "127.0.0.1",
            "port": 9000,
            "log_level": "DEBUG",
            "allow_self_registration": True,
        },
        "oracle_client_lib_dir": "C:\\Oracle\\client19_64\\bin",
        "oracle_home": "C:\\Oracle\\client19_64",
        "ora_tzfile": "timezlrg_1.dat",
    }
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "app.json"
    path.write_text(json.dumps(app_json), encoding="utf-8")
    monkeypatch.setattr("app.config.APP_CONFIG_FILE", path)
    monkeypatch.setattr("app.config.CONFIG_DIR", config_dir)
    return path


def test_find_connections_file_prefers_config_directory(tmp_path: Path, monkeypatch):
    project_root = tmp_path
    config_file = project_root / "config" / "connections.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"databases": {}, "llm": {}}', encoding="utf-8")
    (project_root / "connections.json").write_text(
        '{"databases": {"OTHER": {}}, "llm": {}}',
        encoding="utf-8",
    )

    monkeypatch.setattr("app.config.PROJECT_ROOT", project_root)
    monkeypatch.setattr("app.config.CONFIG_DIR", project_root / "config")

    assert _find_connections_file() == config_file


def test_find_connections_file_skips_directory(tmp_path: Path, monkeypatch):
    project_root = tmp_path
    (project_root / "connections.json").mkdir()
    monkeypatch.setattr("app.config.PROJECT_ROOT", project_root)
    monkeypatch.setattr("app.config.BACKEND_ROOT", project_root / "backend")
    monkeypatch.setattr("app.config.CONFIG_DIR", project_root / "config")

    assert _find_connections_file() is None


def test_load_connections_reads_aliases(user_with_connections: UserContext):
    connections = load_connections(user_with_connections)

    assert list(connections.databases) == ["PGSQL_DB"]
    assert connections.databases["PGSQL_DB"].user == "qa_user"
    assert list(connections.llm) == ["default"]
    assert connections.llm["default"].model == "gpt-4o-mini"
    assert connections.llm["default"].timeout == 120.0


def test_load_connections_reads_llm_timeout(user_with_connections: UserContext, tmp_path: Path):
    path = user_with_connections.connections_path
    config = json.loads(path.read_text(encoding="utf-8"))
    config["llm"]["default"]["timeout"] = 600
    path.write_text(json.dumps(config), encoding="utf-8")

    connections = load_connections(user_with_connections)
    assert connections.llm["default"].timeout == 600.0


def test_secrets_are_read_from_connections_file(user_with_connections: UserContext):
    assert get_db_password(user_with_connections, "PGSQL_DB") == "db-secret"
    assert get_llm_api_key(user_with_connections, "default") == "llm-secret"


def test_app_and_oracle_settings(app_config_file: Path):
    app = get_app_settings()
    assert app.host == "127.0.0.1"
    assert app.port == 9000
    assert app.log_level == "DEBUG"
    assert get_oracle_client_lib_dir() == "C:\\Oracle\\client19_64\\bin"
    assert get_ora_tzfile() == "timezlrg_1.dat"


def test_missing_connections_file_returns_defaults(test_user_ctx: UserContext):
    connections = load_connections(test_user_ctx)
    app = get_app_settings()

    assert connections.databases == {}
    assert connections.llm == {}
    assert app.host == "0.0.0.0"
    assert app.port == 8080


def test_get_default_llm_alias_uses_only_configured_alias(user_with_connections: UserContext):
    path = user_with_connections.connections_path
    config = json.loads(path.read_text(encoding="utf-8"))
    config["llm"] = {
        "OLLAMA": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "llm-secret",
            "model": "gpt-4o-mini",
        }
    }
    path.write_text(json.dumps(config), encoding="utf-8")

    assert get_default_llm_alias(user_with_connections) == "OLLAMA"
    assert resolve_llm_alias(user_with_connections, "default") == "OLLAMA"
    assert resolve_llm_alias(user_with_connections) == "OLLAMA"
    assert get_llm_api_key(user_with_connections, "default") == "llm-secret"


def test_get_default_llm_alias_honors_app_setting(user_with_connections: UserContext):
    path = user_with_connections.connections_path
    config = json.loads(path.read_text(encoding="utf-8"))
    config["app"] = {"default_llm_alias": "PROD_LLM"}
    config["llm"] = {
        "DEV_LLM": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "dev",
            "model": "gpt-4o-mini",
        },
        "PROD_LLM": {
            "base_url": "http://prod.example/v1",
            "api_key": "prod",
            "model": "gpt-4o",
        },
    }
    path.write_text(json.dumps(config), encoding="utf-8")

    assert get_default_llm_alias(user_with_connections) == "PROD_LLM"
    assert resolve_llm_alias(user_with_connections, "default") == "PROD_LLM"
    assert get_connection_aliases(user_with_connections)["default_llm"] == "PROD_LLM"


def test_resolve_llm_alias_rejects_unknown_alias(user_with_connections: UserContext):
    with pytest.raises(ValueError, match="LLM alias 'missing' is not configured"):
        resolve_llm_alias(user_with_connections, "missing")


def test_set_default_llm_alias_persists_in_connections_file(user_with_connections: UserContext):
    path = user_with_connections.connections_path
    config = json.loads(path.read_text(encoding="utf-8"))
    config["llm"] = {
        "DEV_LLM": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "dev",
            "model": "gpt-4o-mini",
        },
        "PROD_LLM": {
            "base_url": "http://prod.example/v1",
            "api_key": "prod",
            "model": "gpt-4o",
        },
    }
    path.write_text(json.dumps(config), encoding="utf-8")

    assert set_default_llm_alias(user_with_connections, "PROD_LLM") == "PROD_LLM"
    assert get_default_llm_alias(user_with_connections) == "PROD_LLM"

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["app"]["default_llm_alias"] == "PROD_LLM"


def test_set_default_llm_alias_requires_multiple_aliases(user_with_connections: UserContext):
    with pytest.raises(ValueError, match="multiple LLM aliases"):
        set_default_llm_alias(user_with_connections, "default")
