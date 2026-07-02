"""One-time migration of legacy single-tenant data to the first new user."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import DATA_DIR, PROJECT_ROOT
from app.user_context import UserContext

logger = logging.getLogger(__name__)

_MIGRATION_FLAG = DATA_DIR / ".legacy_migrated"

_LEGACY_CONNECTIONS = [
    PROJECT_ROOT / "config" / "connections.json",
    PROJECT_ROOT / "connections.json",
]
_LEGACY_DIR_MAP = {
    "dtd_schemas": lambda user: user.dtd_dir,
    "presets": lambda user: user.presets_dir,
    "mapping_presets": lambda user: user.mapping_presets_dir,
}


def _has_legacy_data() -> bool:
    for path in _LEGACY_CONNECTIONS:
        if path.is_file() and path.stat().st_size > 10:
            return True
    for name in _LEGACY_DIR_MAP:
        src = PROJECT_ROOT / name
        if src.is_dir() and any(src.iterdir()):
            return True
    return False


def migrate_legacy_data_to_user(user: UserContext) -> bool:
    """Copy legacy shared data into a new user's workspace once."""
    if _MIGRATION_FLAG.is_file():
        return False
    if not _has_legacy_data():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _MIGRATION_FLAG.write_text("skipped\n", encoding="utf-8")
        return False

    user.ensure_workspace()

    if not user.connections_path.is_file() or user.connections_path.stat().st_size <= 10:
        for src in _LEGACY_CONNECTIONS:
            if src.is_file():
                shutil.copy2(src, user.connections_path)
                logger.info("Migrated legacy connections from %s", src)
                break

    for name, dst_fn in _LEGACY_DIR_MAP.items():
        src_dir = PROJECT_ROOT / name
        dst_dir = dst_fn(user)
        if src_dir.is_dir() and any(src_dir.iterdir()):
            dst_dir.mkdir(parents=True, exist_ok=True)
            for item in src_dir.iterdir():
                target = dst_dir / item.name
                if item.is_file() and not target.exists():
                    shutil.copy2(item, target)
            logger.info("Migrated legacy %s -> %s", name, dst_dir)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _MIGRATION_FLAG.write_text(f"migrated_to={user.user_id}\n", encoding="utf-8")
    logger.info("Legacy data migrated to user %s", user.display_name)
    return True
