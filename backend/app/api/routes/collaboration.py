"""WebSocket endpoint for collaborative XML editing via Yjs."""

from __future__ import annotations

import logging

from anyio import Lock
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.auth.sessions import SESSION_USER_ID
from app.auth.users import get_user_by_id
from app.config import is_auth_disabled
from app.services.collaboration_service import room_manager
from app.user_context import UserContext, dev_user_context, get_user_context_for_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collab", tags=["collaboration"])


class FastAPIWebsocket:
    """Adapter between FastAPI WebSocket and pycrdt-websocket protocol."""

    def __init__(self, websocket: WebSocket, path: str) -> None:
        self._websocket = websocket
        self._path = path
        self._send_lock = Lock()

    @property
    def path(self) -> str:
        return self._path

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except StopAsyncIteration:
            raise
        except Exception:
            raise StopAsyncIteration() from None

    async def send(self, message: bytes) -> None:
        if self._websocket.client_state != WebSocketState.CONNECTED:
            return
        async with self._send_lock:
            await self._websocket.send_bytes(message)

    async def recv(self) -> bytes:
        message = await self._websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise StopAsyncIteration()
        data = message.get("bytes")
        if data is None:
            text = message.get("text")
            if text is not None:
                return text.encode("utf-8")
            raise StopAsyncIteration()
        return bytes(data)


async def _authenticate_ws(websocket: WebSocket) -> UserContext | None:
    if is_auth_disabled():
        return dev_user_context()

    session = websocket.scope.get("session", {})
    user_id = session.get(SESSION_USER_ID)
    if not user_id:
        return None

    record = get_user_by_id(str(user_id))
    if record is None:
        return None
    return get_user_context_for_session(record.id, record.display_name)


@router.websocket("/{session_id}")
async def collaboration_ws(websocket: WebSocket, session_id: str) -> None:
    user = await _authenticate_ws(websocket)
    if user is None:
        await websocket.close(code=1008, reason="Not authenticated")
        return

    await websocket.accept()

    room = room_manager.get_or_create_room(session_id)
    await room_manager.ensure_room_started(room)
    room_manager.add_participant(session_id, user.user_id)

    adapter = FastAPIWebsocket(websocket, f"/api/collab/{session_id}")
    try:
        await room.serve(adapter)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Collaboration WebSocket error for session %s", session_id)
    finally:
        room_manager.remove_participant(session_id, user.user_id)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
