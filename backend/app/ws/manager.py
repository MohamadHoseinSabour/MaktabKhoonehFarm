from collections import defaultdict

from fastapi import WebSocket


class LiveLogManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, course_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[course_id].add(websocket)

    def disconnect(self, course_id: str, websocket: WebSocket) -> None:
        if course_id in self.connections:
            self.connections[course_id].discard(websocket)
            if not self.connections[course_id]:
                self.connections.pop(course_id, None)

    async def broadcast(self, course_id: str, payload: dict) -> None:
        for socket in list(self.connections.get(course_id, set())):
            await socket.send_json(payload)


live_log_manager = LiveLogManager()