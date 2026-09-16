import uuid
from collections import defaultdict

from fastapi import WebSocket


class QueueConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[tuple[uuid.UUID, str], set[WebSocket]] = defaultdict(set)

    def _channel(self, restaurant_id: uuid.UUID, queue_type: str) -> tuple[uuid.UUID, str]:
        return (restaurant_id, queue_type)

    async def connect(self, websocket: WebSocket, restaurant_id: uuid.UUID, queue_type: str) -> None:
        await websocket.accept()
        self._connections[self._channel(restaurant_id, queue_type)].add(websocket)

    def disconnect(self, websocket: WebSocket, restaurant_id: uuid.UUID, queue_type: str) -> None:
        self._connections[self._channel(restaurant_id, queue_type)].discard(websocket)

    async def broadcast(self, restaurant_id: uuid.UUID, queue_type: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections[self._channel(restaurant_id, queue_type)]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, restaurant_id, queue_type)


queue_manager = QueueConnectionManager()
