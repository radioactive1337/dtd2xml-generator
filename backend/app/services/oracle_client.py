"""Oracle Instant Client initialization for thick mode."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

import oracledb

from app.config import get_ora_tzfile, get_oracle_client_lib_dir, has_oracle_databases

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_client_initialized = False


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
        f"oci.dll was not found under oracle_client_lib_dir: {lib_dir}. "
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
        "Remove ora_tzfile from connections.json to use the client default timezone file, "
        "or copy the file from the DB server into oracore\\zoneinfo."
    )
    if available:
        hint += f" Available client files: {', '.join(available)}."
    else:
        hint += f" Directory {zoneinfo_dir(oracle_home)} is missing or empty."

    raise ValueError(
        f"ORA_TZFILE={ora_tzfile!r} was not found at {candidate}. {hint}"
    )


def _missing_client_config_error() -> ValueError:
    return ValueError(
        "Oracle thick mode is required for Oracle 11g. "
        "Set oracle_client_lib_dir in connections.json."
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

    ora_tzfile = get_ora_tzfile()
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
        logger.debug("Oracle client already initialized: %s", exc)


def ensure_oracle_thick_mode(*, required: bool = False) -> None:
    """Enable python-oracledb thick mode when configured.

    Required for Oracle Database 11.2 and earlier (thin mode supports 12.1+).
    """
    global _client_initialized

    if not oracledb.is_thin_mode():
        _client_initialized = True
        return

    lib_dir = get_oracle_client_lib_dir()
    if required and not lib_dir:
        logger.error("Oracle thick mode required but oracle_client_lib_dir is not set")
        raise _missing_client_config_error()
    if not lib_dir:
        return

    with _init_lock:
        if _client_initialized or not oracledb.is_thin_mode():
            _client_initialized = True
            return

        resolved_lib_dir = _apply_oracle_environment(lib_dir)
        logger.info("Initializing Oracle thick mode with lib_dir=%s", resolved_lib_dir)
        _init_oracle_client_library(resolved_lib_dir)
        _client_initialized = True

    if oracledb.is_thin_mode():
        logger.error(
            "Oracle thick mode failed to initialize [lib_dir=%s]",
            lib_dir,
        )
        raise RuntimeError(
            "Oracle thick mode failed to initialize. "
            f"Check oracle_client_lib_dir={lib_dir!r} in connections.json and restart backend."
        )


def bootstrap_oracle_client() -> None:
    """Initialize Oracle thick mode at application startup when needed."""
    if not has_oracle_databases():
        return

    if not get_oracle_client_lib_dir():
        logger.error("Oracle databases configured but client lib dir is missing")
        raise RuntimeError(str(_missing_client_config_error()))

    ensure_oracle_thick_mode(required=True)


def map_oracle_client_error(exc: Exception) -> ValueError | None:
    """Return a clearer error for common Oracle client configuration issues."""
    message = str(exc)

    if "DPY-3010" in message:
        if oracledb.is_thin_mode():
            return ValueError(
                "Oracle 11g requires thick mode. "
                "Set oracle_client_lib_dir in connections.json "
                "and restart backend. "
                f"Original error: {message}"
            )
        return ValueError(f"Oracle connection failed: {message}")

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
            "Try removing ora_tzfile from connections.json first."
            f"{available_hint} "
            f"Original error: {message}"
        )

    return None
