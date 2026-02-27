import asyncio
from threading import Lock
from typing import Dict, Optional

from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        with self._lock:
            self.active_connections.pop(user_id, None)

    async def notify(self, user_id: int, payload: dict):
        with self._lock:
            websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(user_id)

    def notify_threadsafe(self, user_id: int, payload: dict):
        loop = self._loop
        if not loop or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.notify(user_id, payload), loop)


notification_ws_manager = NotificationConnectionManager()

