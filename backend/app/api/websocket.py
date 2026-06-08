from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

logger = logging.getLogger("hireflow.ws")

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WS connected: {session_id}")

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)
        logger.info(f"WS disconnected: {session_id}")

    async def send_json(self, session_id: str, data: dict):
        ws = self.active_connections.get(session_id)
        if ws:
            await ws.send_json(data)


manager = ConnectionManager()


@router.websocket("/interview/{session_id}")
async def interview_ws(session_id: str, websocket: WebSocket):
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Milestone 4: route to AI interview agent
            await websocket.send_json({
                "type": "ack",
                "session_id": session_id,
                "message": "WebSocket connected — AI pipeline in Milestone 4",
                "received": data,
            })
    except WebSocketDisconnect:
        manager.disconnect(session_id)
