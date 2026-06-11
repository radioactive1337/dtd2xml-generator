"""Oracle Instant Client initialization for thick mode."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import oracledb

from app.config import get_oracle_thick_mode_settings

_init_lock = threading.Lock()
_client_initialized = False


def derive_oracle_home(lib_dir: str) -> str:
    """Return ORACLE_HOME for a client library directory."""
    path = Path(lib_dir)
    if path.name.lower() == "bin":
        return str(path.parent)
    return str(path)


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


def _apply_oracle_environment(lib_dir: str | None) -> None:
    """Set ORACLE_HOME and ORA_TZFILE before loading the client libraries."""
    if lib_dir:
        lib_path = Path(lib_dir)
        if not lib_path.is_dir():
            raise ValueError(f"ORACLE_CLIENT_LIB_DIR does not exist: {lib_dir}")
        if not (lib_path / "oci.dll").is_file() and lib_path.name.lower() == "bin":
            raise ValueError(f"oci.dll was not found in ORACLE_CLIENT_LIB_DIR: {lib_dir}")

        oracle_home = derive_oracle_home(lib_dir)
        os.environ["ORACLE_HOME"] = oracle_home
    else:
        oracle_home = os.getenv("ORACLE_HOME", "").strip()

    if not oracle_home:
        return

    oracle_home_path = Path(oracle_home)
    if not oracle_home_path.is_dir():
        raise ValueError(f"ORACLE_HOME does not exist: {oracle_home}")

    ora_tzfile = os.getenv("ORA_TZFILE", "").strip() or None
    resolved_tzfile = resolve_ora_tzfile(oracle_home_path, ora_tzfile)
    if resolved_tzfile:
        os.environ["ORA_TZFILE"] = resolved_tzfile
    else:
        os.environ.pop("ORA_TZFILE", None)


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
        _apply_oracle_environment(lib_dir)
        if lib_dir:
            oracledb.init_oracle_client(lib_dir=lib_dir)
        else:
            oracledb.init_oracle_client()
        _client_initialized = True


def map_oracle_client_error(exc: Exception) -> ValueError | None:
    """Return a clearer error for common Oracle client configuration issues."""
    message = str(exc)

    if "DPY-3010" in message and oracledb.is_thin_mode():
        return ValueError(
            "Oracle Database 11.2 or earlier requires thick mode. "
            "Install Oracle Client 19+ and configure ORACLE_CLIENT_LIB_DIR in .env, "
            "then restart the backend. "
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
