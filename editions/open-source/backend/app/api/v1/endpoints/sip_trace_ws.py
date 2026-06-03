from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.plugin_manager import plugin_manager
from app.core.security import decode_token
import json
from loguru import logger

router = APIRouter()

class SipTraceManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send recent traces
        if plugin_manager.recent_sip_traces:
            await websocket.send_text(json.dumps({"type": "init", "data": plugin_manager.recent_sip_traces}))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_trace(self, trace_data: dict):
        if not self.active_connections:
            return
        msg = json.dumps({"type": "trace", "data": trace_data})
        for connection in list(self.active_connections):
            try:
                await connection.send_text(msg)
            except Exception as e:
                logger.warning(f"Error: {e}")

sip_trace_manager = SipTraceManager()

@router.websocket("/ws/sip-trace")
async def websocket_sip_trace(websocket: WebSocket, token: str = ""):
    # WebSocket 鉴权：验证 token 有效性
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        payload = decode_token(token)
        if not payload or not payload.get("sub"):
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await sip_trace_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        sip_trace_manager.disconnect(websocket)