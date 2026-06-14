"""Tests for connections.json configuration loading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import (
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


@pytest.fixture
def connections_file(tmp_path: Path):
    config = {
        "app": {"host": "127.0.0.1", "port": 9000, "log_level": "DEBUG"},
        "oracle_client_lib_dir": "C:\\Oracle\\client19_64\\bin",
        "oracle_home": "C:\\Oracle\\client19_64",
        "ora_tzfile": "timezlrg_1.dat",
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


def test_load_connections_reads_aliases(connections_file: Path):
    with patch("app.config._find_connections_file", return_value=connections_file):
        connections = load_connections()

    assert list(connections.databases) == ["PGSQL_DB"]
    assert connections.databases["PGSQL_DB"].user == "qa_user"
    assert list(connections.llm) == ["default"]
    assert connections.llm["default"].model == "gpt-4o-mini"
    assert connections.llm["default"].timeout == 120.0


def test_load_connections_reads_llm_timeout(connections_file: Path):
    config = json.loads(connections_file.read_text(encoding="utf-8"))
    config["llm"]["default"]["timeout"] = 600
    connections_file.write_text(json.dumps(config), encoding="utf-8")

    with patch("app.config._find_connections_file", return_value=connections_file):
        connections = load_connections()

    assert connections.llm["default"].timeout == 600.0


def test_secrets_are_read_from_connections_file(connections_file: Path):
    with patch("app.config._find_connections_file", return_value=connections_file):
        assert get_db_password("PGSQL_DB") == "db-secret"
        assert get_llm_api_key("default") == "llm-secret"


def test_app_and_oracle_settings(connections_file: Path):
    with patch("app.config._find_connections_file", return_value=connections_file):
        app = get_app_settings()
        assert app.host == "127.0.0.1"
        assert app.port == 9000
        assert app.log_level == "DEBUG"
        assert get_oracle_client_lib_dir() == "C:\\Oracle\\client19_64\\bin"
        assert get_ora_tzfile() == "timezlrg_1.dat"


def test_missing_connections_file_returns_defaults():
    with patch("app.config._find_connections_file", return_value=None):
        connections = load_connections()
        app = get_app_settings()

    assert connections.databases == {}
    assert connections.llm == {}
    assert app.host == "0.0.0.0"
    assert app.port == 8080


def test_get_default_llm_alias_uses_only_configured_alias(connections_file: Path):
    config = json.loads(connections_file.read_text(encoding="utf-8"))
    config["llm"] = {
        "OLLAMA": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "llm-secret",
            "model": "gpt-4o-mini",
        }
    }
    connections_file.write_text(json.dumps(config), encoding="utf-8")

    with patch("app.config._find_connections_file", return_value=connections_file):
        assert get_default_llm_alias() == "OLLAMA"
        assert resolve_llm_alias("default") == "OLLAMA"
        assert resolve_llm_alias() == "OLLAMA"
        assert get_llm_api_key("default") == "llm-secret"


def test_get_default_llm_alias_honors_app_setting(connections_file: Path):
    config = json.loads(connections_file.read_text(encoding="utf-8"))
    config["app"]["default_llm_alias"] = "PROD_LLM"
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
    connections_file.write_text(json.dumps(config), encoding="utf-8")

    with patch("app.config._find_connections_file", return_value=connections_file):
        assert get_default_llm_alias() == "PROD_LLM"
        assert resolve_llm_alias("default") == "PROD_LLM"
        assert get_connection_aliases()["default_llm"] == "PROD_LLM"


def test_resolve_llm_alias_rejects_unknown_alias(connections_file: Path):
    with patch("app.config._find_connections_file", return_value=connections_file):
        with pytest.raises(ValueError, match="LLM alias 'missing' is not configured"):
            resolve_llm_alias("missing")


def test_set_default_llm_alias_persists_in_connections_file(connections_file: Path):
    config = json.loads(connections_file.read_text(encoding="utf-8"))
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
    connections_file.write_text(json.dumps(config), encoding="utf-8")

    with patch("app.config._find_connections_file", return_value=connections_file):
        assert set_default_llm_alias("PROD_LLM") == "PROD_LLM"
        assert get_default_llm_alias() == "PROD_LLM"

    saved = json.loads(connections_file.read_text(encoding="utf-8"))
    assert saved["app"]["default_llm_alias"] == "PROD_LLM"


def test_set_default_llm_alias_requires_multiple_aliases(connections_file: Path):
    with patch("app.config._find_connections_file", return_value=connections_file):
        with pytest.raises(ValueError, match="multiple LLM aliases"):
            set_default_llm_alias("default")
