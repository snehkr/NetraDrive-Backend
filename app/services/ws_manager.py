# app/services/ws_manager.py
from typing import Dict, List
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(ws)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_to_user(self, user_id: str, message: str):
        """Send message to all WS clients of a user"""
        if user_id in self.active_connections:
            to_remove = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    to_remove.append(ws)
            for ws in to_remove:
                self.disconnect(user_id, ws)


ws_manager = WebSocketManager()
