"""Oracle Instant Client initialization for thick mode."""

from __future__ import annotations

import threading

import oracledb

from app.config import get_oracle_thick_mode_settings

_init_lock = threading.Lock()
_client_initialized = False


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
        if lib_dir:
            oracledb.init_oracle_client(lib_dir=lib_dir)
        else:
            oracledb.init_oracle_client()
        _client_initialized = True


def oracle_thick_mode_error(exc: Exception) -> ValueError | None:
    """Return a clearer error when thin mode cannot reach an old Oracle server."""
    message = str(exc)
    if "DPY-3010" not in message or not oracledb.is_thin_mode():
        return None

    return ValueError(
        "Oracle Database 11.2 or earlier requires thick mode. "
        "Install Oracle Instant Client 19+ and configure either "
        "ORACLE_CLIENT_LIB_DIR in .env or oracle_client_lib_dir / "
        "oracle_thick_mode in connections.json, then restart the backend. "
        f"Original error: {message}"
    )
