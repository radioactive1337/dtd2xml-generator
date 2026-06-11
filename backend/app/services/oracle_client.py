"""Oracle Instant Client initialization for thick mode."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import oracledb

from app.config import get_oracle_thick_mode_settings, has_oracle_databases

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


def _apply_oracle_environment(lib_dir: str | None) -> str | None:
    """Set ORACLE_HOME and ORA_TZFILE before loading the client libraries."""
    if not lib_dir:
        return None

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

    return resolved_lib_dir


def ensure_oracle_thick_mode() -> None:
    """Enable python-oracledb thick mode when configured.

    Required for Oracle Database 11.2 and earlier (thin mode supports 12.1+).
    """
    global _client_initialized

    if not oracledb.is_thin_mode():
        return

    use_thick, lib_dir = get_oracle_thick_mode_settings()
    if not use_thick:
        return

    with _init_lock:
        if _client_initialized or not oracledb.is_thin_mode():
            return

        if not lib_dir:
            raise ValueError(
                "Oracle thick mode is required but ORACLE_CLIENT_LIB_DIR is not set. "
                "Add it to .env in the project root (xml-generator/.env) and restart backend."
            )

        resolved_lib_dir = _apply_oracle_environment(lib_dir)
        oracledb.init_oracle_client(lib_dir=resolved_lib_dir)
        _client_initialized = True


def bootstrap_oracle_client() -> None:
    """Initialize Oracle thick mode at application startup when needed."""
    if not has_oracle_databases():
        return

    use_thick, lib_dir = get_oracle_thick_mode_settings()
    if not use_thick:
        raise RuntimeError(
            "connections.json contains an Oracle database, but thick mode is not configured. "
            "Set ORACLE_CLIENT_LIB_DIR in xml-generator/.env and restart backend."
        )

    ensure_oracle_thick_mode()
    if oracledb.is_thin_mode():
        raise RuntimeError(
            "Oracle thick mode failed to initialize. "
            f"ORACLE_CLIENT_LIB_DIR={lib_dir or '(not set)'}. "
            "Verify the path to oci.dll and fully restart backend (stop uvicorn, start again)."
        )


def map_oracle_client_error(exc: Exception) -> ValueError | None:
    """Return a clearer error for common Oracle client configuration issues."""
    message = str(exc)

    if "DPY-3010" in message and oracledb.is_thin_mode():
        use_thick, lib_dir = get_oracle_thick_mode_settings()
        if use_thick:
            return ValueError(
                "Oracle is still running in thin mode even though thick mode is configured. "
                f"ORACLE_CLIENT_LIB_DIR={lib_dir or '(not set)'}. "
                "Put .env in the project root (xml-generator/.env), verify the path to oci.dll, "
                "and fully restart backend (stop uvicorn completely, then start again). "
                f"Original error: {message}"
            )
        return ValueError(
            "Oracle Database 11.2 or earlier requires thick mode. "
            "Install Oracle Client 19+ and set ORACLE_CLIENT_LIB_DIR in xml-generator/.env, "
            "then restart backend. "
            f"Original error: {message}"
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
            "The filename from v$timezone_file must exist on the client machine, not only on the DB server. "
            "Try removing ORA_TZFILE from .env first."
            f"{available_hint} "
            f"Original error: {message}"
        )

    return None
