from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.plugin_manager import plugin_manager
import json
import asyncio
from loguru import logger

router = APIRouter()

_ALLOWED_SIP_TRACE_ROLES = {"admin", "owner"}


class SipTraceManager:
    def __init__(self):
        self.active_connections: list[tuple[WebSocket, str]] = []

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        self.active_connections.append((websocket, tenant_id))
        if plugin_manager.recent_sip_traces:
            await websocket.send_text(json.dumps({"type": "init", "data": plugin_manager.recent_sip_traces}))

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [(ws, tid) for ws, tid in self.active_connections if ws is not websocket]

    async def broadcast_trace(self, trace_data: dict, tenant_id: str):
        if not self.active_connections:
            return
        msg = json.dumps({"type": "trace", "data": trace_data})
        # FIX: [2026-07-03] 广播时清理已断开的连接，防止 WebSocket 连接泄漏 [可靠性工程师]
        dead_connections: list[WebSocket] = []
        for connection, conn_tid in list(self.active_connections):
            if conn_tid != tenant_id:
                continue
            try:
                await connection.send_text(msg)
            except (RuntimeError, ConnectionError, OSError):
                dead_connections.append(connection)
        if dead_connections:
            self.active_connections = [
                (ws, tid) for ws, tid in self.active_connections if ws not in dead_connections
            ]
            logger.debug(f"Cleaned up {len(dead_connections)} dead SIP trace WebSocket connections")

sip_trace_manager = SipTraceManager()

@router.websocket("/ws/sip-trace")
async def websocket_sip_trace(websocket: WebSocket, ticket: str = ""):
    # P0-6: 改用短期一次性 ws-ticket 认证，消除 URL 暴露 JWT token
    if not ticket:
        await websocket.close(code=4001, reason="Missing ticket")
        return
    from app.core.ws_ticket import consume_ws_ticket
    payload = await consume_ws_ticket(ticket)
    if not payload or not payload.get("sub"):
        await websocket.close(code=4001, reason="Invalid or expired ticket")
        return

    user_role = (payload.get("role") or "").strip().lower()
    is_superuser = payload.get("is_superuser", False)
    if not is_superuser and user_role not in _ALLOWED_SIP_TRACE_ROLES:
        await websocket.close(code=4003, reason="Insufficient permissions")
        return

    tenant_id = (payload.get("tenant_id") or "default").strip() or "default"

    await sip_trace_manager.connect(websocket, tenant_id)
    try:
        async def _heartbeat():
            while True:
                await asyncio.sleep(30)
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.debug("swallowed_exception", exc_info=True)
        finally:
            heartbeat_task.cancel()
    finally:
        sip_trace_manager.disconnect(websocket)
