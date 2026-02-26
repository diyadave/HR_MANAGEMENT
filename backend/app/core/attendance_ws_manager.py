import asyncio
from threading import Lock
from typing import Dict, Optional

from fastapi import WebSocket


class AttendanceConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}
        self.stream_connections: Dict[int, WebSocket] = {}
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

    async def connect_stream(self, websocket: WebSocket):
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self.stream_connections[id(websocket)] = websocket

    def disconnect_stream(self, websocket: WebSocket):
        with self._lock:
            self.stream_connections.pop(id(websocket), None)

    async def notify(self, user_id: int):
        with self._lock:
            websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json({"type": "attendance_update"})
            except Exception:
                self.disconnect(user_id)

    async def notify_streams(self):
        with self._lock:
            sockets = list(self.stream_connections.values())
        stale = []
        for websocket in sockets:
            try:
                await websocket.send_json({"type": "attendance_update"})
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect_stream(websocket)

    async def notify_attendance_change(self, user_id: int):
        await self.notify(user_id)
        await self.notify_streams()

    def notify_attendance_change_threadsafe(self, user_id: int):
        loop = self._loop
        if not loop or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.notify_attendance_change(user_id), loop)


attendance_ws_manager = AttendanceConnectionManager()
