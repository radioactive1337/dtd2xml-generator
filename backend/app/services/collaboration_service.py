"""In-memory Yjs room management for collaborative XML editing."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack

from anyio import create_task_group
from pycrdt import Doc
from pycrdt_websocket import YRoom

logger = logging.getLogger(__name__)

EMPTY_ROOM_TTL_SEC = 60


class RoomManager:
    """Manages collaborative editing rooms keyed by session id."""

    def __init__(self) -> None:
        self.rooms: dict[str, YRoom] = {}
        self.participants: dict[str, set[str]] = {}
        self._empty_since: dict[str, float] = {}
        self._task_group = None
        self._exit_stack: AsyncExitStack | None = None
        self._cleanup_scheduled = False

    async def start(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._task_group = await self._exit_stack.enter_async_context(create_task_group())
        self._task_group.start_soon(self._cleanup_loop)

    async def stop(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._task_group = None

    def get_or_create_room(self, session_id: str) -> YRoom:
        room = self.rooms.get(session_id)
        if room is None:
            room = YRoom(ready=True, ydoc=Doc())
            self.rooms[session_id] = room
            self.participants.setdefault(session_id, set())
            self._empty_since.pop(session_id, None)
        return room

    def get_doc(self, session_id: str) -> Doc:
        return self.get_or_create_room(session_id).ydoc

    async def ensure_room_started(self, room: YRoom) -> None:
        if self._task_group is None:
            raise RuntimeError("RoomManager is not running")
        if not room.started.is_set():
            await self._task_group.start(room.start)

    def add_participant(self, session_id: str, user_id: str) -> None:
        self.participants.setdefault(session_id, set()).add(user_id)
        self._empty_since.pop(session_id, None)

    def remove_participant(self, session_id: str, user_id: str) -> None:
        participants = self.participants.get(session_id)
        if participants is None:
            return
        participants.discard(user_id)
        if not participants:
            self._empty_since.setdefault(session_id, time.monotonic())
            self.schedule_cleanup()

    async def remove_room(self, session_id: str) -> None:
        room = self.rooms.pop(session_id, None)
        self.participants.pop(session_id, None)
        self._empty_since.pop(session_id, None)
        if room is not None:
            await room.stop()

    def schedule_cleanup(self) -> None:
        if self._cleanup_scheduled or self._task_group is None:
            return
        self._cleanup_scheduled = True
        self._task_group.start_soon(self._run_cleanup)

    async def cleanup_empty_rooms(self) -> None:
        now = time.monotonic()
        to_remove = [
            session_id
            for session_id, since in list(self._empty_since.items())
            if now - since >= EMPTY_ROOM_TTL_SEC
            and not self.participants.get(session_id)
        ]
        for session_id in to_remove:
            logger.info("Removing empty collaboration room: %s", session_id)
            await self.remove_room(session_id)

    async def _run_cleanup(self) -> None:
        try:
            await asyncio.sleep(EMPTY_ROOM_TTL_SEC)
            await self.cleanup_empty_rooms()
        finally:
            self._cleanup_scheduled = False

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(EMPTY_ROOM_TTL_SEC)
            await self.cleanup_empty_rooms()


room_manager = RoomManager()
