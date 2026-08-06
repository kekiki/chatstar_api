"""
WebSocket connection manager for chat messages and notifications.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage active WebSocket connections keyed by user_id (multi-device supported)."""

    def __init__(self):
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: int, event: str, data: Any) -> int:
        """Send an event payload to all sockets of a user. Returns delivered socket count."""
        sockets = list(self._connections.get(user_id) or ())
        if not sockets:
            return 0
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        delivered = 0
        stale = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception as e:
                logger.warning("ws send failed user_id=%s err=%s", user_id, e)
                stale.append(ws)
        if stale:
            async with self._lock:
                user_sockets = self._connections.get(user_id)
                if user_sockets:
                    for ws in stale:
                        user_sockets.discard(ws)
                    if not user_sockets:
                        self._connections.pop(user_id, None)
        return delivered


ws_manager = ConnectionManager()
