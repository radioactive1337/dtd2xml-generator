"""Per-user workspace paths and identity."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.auth.users import UserRecord, user_data_root
from app.config import (
    DATA_DIR,
    PROJECT_ROOT,
    USER_CONNECTIONS_TEMPLATE,
    is_auth_disabled,
)


@dataclass(frozen=True)
class UserContext:
    user_id: str
    display_name: str
    root: Path

    @property
    def connections_path(self) -> Path:
        return self.root / "connections.json"

    @property
    def dtd_dir(self) -> Path:
        return self.root / "dtd_schemas"

    @property
    def presets_dir(self) -> Path:
        return self.root / "presets"

    @property
    def mapping_presets_dir(self) -> Path:
        return self.root / "mapping_presets"

    def ensure_workspace(self) -> None:
        """Create user directories and seed connections.json if missing."""
        self.dtd_dir.mkdir(parents=True, exist_ok=True)
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        self.mapping_presets_dir.mkdir(parents=True, exist_ok=True)
        if not self.connections_path.is_file():
            if USER_CONNECTIONS_TEMPLATE.is_file():
                shutil.copyfile(USER_CONNECTIONS_TEMPLATE, self.connections_path)
            else:
                self.connections_path.write_text(
                    json.dumps({"databases": {}, "llm": {}, "app": {}}, indent=2)
                    + "\n",
                    encoding="utf-8",
                )


def user_context_from_record(record: UserRecord) -> UserContext:
    ctx = UserContext(
        user_id=record.id,
        display_name=record.display_name,
        root=user_data_root(record.id),
    )
    ctx.ensure_workspace()
    return ctx


def dev_user_context() -> UserContext:
    """Single-user fallback when AUTH_DISABLED=1 (legacy paths)."""
    legacy_connections = PROJECT_ROOT / "config" / "connections.json"
    if not legacy_connections.is_file():
        legacy_connections = PROJECT_ROOT / "connections.json"

    root = PROJECT_ROOT
    ctx = UserContext(
        user_id="dev-local",
        display_name="dev",
        root=root,
    )
    if not legacy_connections.is_file():
        ctx.ensure_workspace()
    return ctx


def get_user_context_for_session(user_id: str, display_name: str) -> UserContext:
    if is_auth_disabled():
        return dev_user_context()
    ctx = UserContext(
        user_id=user_id,
        display_name=display_name,
        root=user_data_root(user_id),
    )
    ctx.ensure_workspace()
    return ctx
