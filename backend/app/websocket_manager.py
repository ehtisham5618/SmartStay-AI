"""Concurrency-safe registry of active WebSocket sessions."""

import asyncio
from typing import Dict

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket, accept: bool = True) -> None:
        if accept:
            await websocket.accept()
        async with self._lock:
            self.active_connections[session_id] = websocket

    async def disconnect(self, session_id: str, close_socket: bool = True) -> None:
        async with self._lock:
            websocket = self.active_connections.pop(session_id, None)
        if close_socket and websocket:
            try:
                await websocket.close()
            except RuntimeError:
                pass

    def get_connection_count(self) -> int:
        return len(self.active_connections)

