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


def _apply_oracle_environment(lib_dir: str | None) -> None:
    """Set ORACLE_HOME so the client can locate timezone and NLS files."""
    if lib_dir:
        os.environ.setdefault("ORACLE_HOME", derive_oracle_home(lib_dir))

    oracle_home = os.getenv("ORACLE_HOME", "").strip()
    if oracle_home:
        os.environ.setdefault("ORACLE_HOME", oracle_home)

    ora_tzfile = os.getenv("ORA_TZFILE", "").strip()
    if ora_tzfile:
        os.environ["ORA_TZFILE"] = ora_tzfile


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
        return ValueError(
            "Oracle Client cannot load timezone files (ORA-01804). "
            "Set ORACLE_HOME to the client home directory (parent of bin, not bin itself), "
            "ensure oracore\\zoneinfo contains timezlrg_*.dat, and if needed set ORA_TZFILE "
            "to match the database timezone file from: SELECT * FROM v$timezone_file. "
            "Restart the backend after changing environment variables. "
            f"Original error: {message}"
        )

    return None
