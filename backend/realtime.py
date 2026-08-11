"""WebSocket hub for realtime chat, typing indicators and presence."""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger("buddilio.ws")


class Hub:
    def __init__(self):
        self.sockets: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.sockets[user_id].add(ws)

    async def disconnect(self, user_id: str, ws: WebSocket):
        async with self.lock:
            self.sockets[user_id].discard(ws)
            if not self.sockets[user_id]:
                self.sockets.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return bool(self.sockets.get(user_id))

    def online_among(self, user_ids) -> list:
        return [u for u in user_ids if self.is_online(u)]

    async def send_to(self, user_ids, message: dict):
        dead = []
        for uid in set(user_ids):
            for ws in list(self.sockets.get(uid, [])):
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append((uid, ws))
        for uid, ws in dead:
            await self.disconnect(uid, ws)


hub = Hub()
