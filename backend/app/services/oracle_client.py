"""Oracle Instant Client initialization for thick mode."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

import oracledb

from app.config import get_oracle_client_lib_dir, get_oracle_env_diagnostics, has_oracle_databases

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_client_initialized = False
_init_lib_dir: str | None = None


def derive_oracle_home(lib_dir: str) -> str:
    """Return ORACLE_HOME for a client library directory."""
    path = Path(lib_dir)
    if path.name.lower() == "bin":
        return str(path.parent)
    return str(path)


def resolve_client_lib_dir(lib_dir: str) -> str:
    """Return the directory that actually contains oci.dll."""
    path = Path(lib_dir)
    if (path / "oci.dll").is_file():
        return str(path)
    if path.name.lower() != "bin" and (path / "bin" / "oci.dll").is_file():
        return str(path / "bin")
    raise ValueError(
        f"oci.dll was not found under ORACLE_CLIENT_LIB_DIR: {lib_dir}. "
        "Point it to the folder that contains oci.dll, usually ...\\client_1\\bin."
    )


def zoneinfo_dir(oracle_home: Path) -> Path:
    return oracle_home / "oracore" / "zoneinfo"


def list_timezone_files(oracle_home: Path) -> list[str]:
    directory = zoneinfo_dir(oracle_home)
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.glob("*.dat"))


def resolve_ora_tzfile(oracle_home: Path, ora_tzfile: str | None) -> str | None:
    """Resolve ORA_TZFILE to an existing absolute path, or None for client default."""
    if not ora_tzfile:
        return None

    requested = Path(ora_tzfile)
    if requested.is_absolute():
        if requested.is_file():
            return str(requested)
        raise ValueError(
            f"ORA_TZFILE points to a missing file: {requested}. "
            "Use an absolute path to an existing .dat file, or put the file into "
            f"{zoneinfo_dir(oracle_home)}."
        )

    candidate = zoneinfo_dir(oracle_home) / ora_tzfile
    if candidate.is_file():
        return str(candidate)

    available = list_timezone_files(oracle_home)
    hint = (
        "Remove ORA_TZFILE from .env to use the client default timezone file, "
        "or copy the file from the DB server into oracore\\zoneinfo."
    )
    if available:
        hint += f" Available client files: {', '.join(available)}."
    else:
        hint += f" Directory {zoneinfo_dir(oracle_home)} is missing or empty."

    raise ValueError(
        f"ORA_TZFILE={ora_tzfile!r} was not found at {candidate}. {hint}"
    )


def is_thick_mode_active() -> bool:
    return not oracledb.is_thin_mode()


def get_oracle_runtime_status() -> dict[str, object]:
    return {
        "thin_mode": oracledb.is_thin_mode(),
        "client_initialized": _client_initialized,
        "init_lib_dir": _init_lib_dir,
    }


def _missing_client_config_error() -> ValueError:
    diagnostics = get_oracle_env_diagnostics()
    return ValueError(
        "Oracle thick mode is required for Oracle 11g, but the client path is not configured. "
        "Set ORACLE_CLIENT_LIB_DIR in xml-generator/.env or oracle_client_lib_dir in connections.json. "
        f"Diagnostics: {diagnostics}"
    )


def _prepare_windows_dll_path(lib_dir: str) -> None:
    """Ensure dependent Oracle DLLs can be resolved on Windows."""
    if sys.platform != "win32":
        return

    os.add_dll_directory(lib_dir)
    path = os.environ.get("PATH", "")
    if lib_dir.lower() not in path.lower():
        os.environ["PATH"] = lib_dir + os.pathsep + path


def _apply_oracle_environment(lib_dir: str) -> str:
    """Set ORACLE_HOME and ORA_TZFILE before loading the client libraries."""
    resolved_lib_dir = resolve_client_lib_dir(lib_dir)
    oracle_home = derive_oracle_home(resolved_lib_dir)
    os.environ["ORACLE_HOME"] = oracle_home

    oracle_home_path = Path(oracle_home)
    if not oracle_home_path.is_dir():
        raise ValueError(f"ORACLE_HOME does not exist: {oracle_home}")

    ora_tzfile = os.getenv("ORA_TZFILE", "").strip() or None
    resolved_tzfile = resolve_ora_tzfile(oracle_home_path, ora_tzfile)
    if resolved_tzfile:
        os.environ["ORA_TZFILE"] = resolved_tzfile
    else:
        os.environ.pop("ORA_TZFILE", None)

    _prepare_windows_dll_path(resolved_lib_dir)
    return resolved_lib_dir


def _init_oracle_client_library(resolved_lib_dir: str) -> None:
    try:
        oracledb.init_oracle_client(lib_dir=resolved_lib_dir)
    except oracledb.ProgrammingError as exc:
        message = str(exc).lower()
        if "already been initialized" not in message:
            raise
        logger.info("Oracle client already initialized: %s", exc)


def ensure_oracle_thick_mode(*, required: bool = False) -> None:
    """Enable python-oracledb thick mode when configured.

    Required for Oracle Database 11.2 and earlier (thin mode supports 12.1+).
    """
    global _client_initialized, _init_lib_dir

    if is_thick_mode_active():
        _client_initialized = True
        return

    lib_dir = get_oracle_client_lib_dir()
    if required and not lib_dir:
        raise _missing_client_config_error()
    if not lib_dir:
        return

    with _init_lock:
        if is_thick_mode_active():
            _client_initialized = True
            return

        resolved_lib_dir = _apply_oracle_environment(lib_dir)
        logger.info("Initializing Oracle thick mode with lib_dir=%s", resolved_lib_dir)
        _init_oracle_client_library(resolved_lib_dir)
        _client_initialized = True
        _init_lib_dir = resolved_lib_dir

    if oracledb.is_thin_mode():
        diagnostics = {**get_oracle_env_diagnostics(), **get_oracle_runtime_status()}
        raise RuntimeError(
            "Oracle thick mode failed to initialize and driver is still in thin mode. "
            f"Diagnostics: {diagnostics}"
        )


def bootstrap_oracle_client() -> None:
    """Initialize Oracle thick mode at application startup when needed."""
    if not has_oracle_databases():
        return

    lib_dir = get_oracle_client_lib_dir()
    if not lib_dir:
        raise RuntimeError(str(_missing_client_config_error()))

    ensure_oracle_thick_mode(required=True)
    logger.info(
        "Oracle thick mode ready (thin_mode=%s, lib_dir=%s)",
        oracledb.is_thin_mode(),
        _init_lib_dir,
    )


def map_oracle_client_error(exc: Exception) -> ValueError | None:
    """Return a clearer error for common Oracle client configuration issues."""
    message = str(exc)
    diagnostics = {**get_oracle_env_diagnostics(), **get_oracle_runtime_status()}

    if "DPY-3010" in message and oracledb.is_thin_mode():
        return ValueError(
            "Oracle is still running in thin mode, so Oracle 11g cannot be used. "
            "Open /api/health/oracle and verify thin_mode=false. "
            "If thin_mode=true, fully stop all python/uvicorn processes and restart backend. "
            f"Diagnostics: {diagnostics}. Original error: {message}"
        )

    if "ORA-01804" in message:
        oracle_home = os.getenv("ORACLE_HOME", "")
        ora_tzfile = os.getenv("ORA_TZFILE", "")
        available = list_timezone_files(Path(oracle_home)) if oracle_home else []
        available_hint = (
            f" Available client files: {', '.join(available)}."
            if available
            else " Client oracore\\zoneinfo is missing or empty."
        )
        return ValueError(
            "Oracle Client cannot load timezone files (ORA-01804). "
            f"ORACLE_HOME={oracle_home or '(not set)'}, ORA_TZFILE={ora_tzfile or '(not set)'}. "
            "Try removing ORA_TZFILE from .env first."
            f"{available_hint} "
            f"Original error: {message}"
        )

    return None
