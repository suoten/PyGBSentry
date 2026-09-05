import os
import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import FileResponse
import asyncio
import logging  # FIXED-P0: logging.Handler 基类需要导入 logging 模块
from loguru import logger
from collections import deque
from app.api import deps  # S-06-03 日志HTTP接口添加认证依赖


router = APIRouter()

LOGS_DIR = Path("logs").resolve()

# FIX: [2026-07-03] GET /api/v1/logs/ 返回 404，因为缺少根路由。
#      根因：logs 模块只有 /files、/files/{path}/lines 等子路由，没有根路由。
#      修复：添加根路由返回可用端点列表。 [全栈工程师]


@router.get("")
def logs_root(current_user=Depends(deps.get_current_active_user)):
    """日志模块根端点 — 返回可用的日志查询端点。"""
    return {
        "endpoints": {
            "files": "GET /logs/files — 列出日志文件",
            "lines": "GET /logs/files/{filepath}/lines?keyword=&page=&page_size= — 查看日志行",
            "download": "GET /logs/files/{filepath}/download — 下载日志文件",
            "websocket": "WS /logs/ws/logs?ticket= — 实时日志推送",
        }
    }

# 全量读取日志文件到内存 → 从文件末尾反向读取，使用 deque 限制最大行数
_MAX_LOG_LINES = 10000
_MAX_LOG_FILE_SIZE = 50 * 1024 * 1024  # 50MB

@router.get("/files")
def list_log_files(current_user=Depends(deps.require_roles(["admin", "owner"]))):  # FIX: [2026-07-16 P1] 升级权限，普通用户不应看到日志文件列表
    if not LOGS_DIR.exists():
        return []

    files = []
    for root, dirs, filenames in os.walk(LOGS_DIR):
        for name in filenames:
            if name.endswith(".log") or ".log" in name:
                f = Path(root) / name
                try:
                    stat = f.stat()
                    rel_path = f.relative_to(LOGS_DIR).as_posix()
                    files.append({
                        "name": rel_path,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime
                    })
                except (OSError, PermissionError):
                    logger.warning("(OSError, PermissionError) occurred")
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files

@router.get("/files/{filepath:path}/lines")
def get_log_lines(filepath: str, keyword: str = "", page: int = 1, page_size: int = 1000, current_user=Depends(deps.require_roles(["admin", "owner"]))):  # FIX: [2026-07-16 P1] 升级权限
    target = (LOGS_DIR / filepath).resolve()
    # FIX: [2026-07-16 P1] 用 is_relative_to 替换 startswith，防止同前缀目录绕过（如 logs_secret/）
    try:
        if not target.is_relative_to(LOGS_DIR):
            raise HTTPException(status_code=403, detail="Access denied")
    except (TypeError, ValueError):
        # Python 3.8 兼容：is_relative_to 在 3.9+ 才有
        if not str(target).startswith(str(LOGS_DIR) + os.sep) and target != LOGS_DIR:
            raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # 全量读取日志文件到内存 → 文件大小检查，超过 50MB 拒绝读取
    try:
        file_size = target.stat().st_size
    except OSError:
        raise HTTPException(status_code=500, detail="Cannot read file stats")
    if file_size > _MAX_LOG_FILE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Log file too large ({file_size // (1024*1024)}MB), exceeds {_MAX_LOG_FILE_SIZE // (1024*1024)}MB limit"
        )

    try:
        # f.readlines() + lines.reverse() 全量读取 → 从文件末尾反向读取，deque 限制最大行数
        lines = deque(maxlen=_MAX_LOG_LINES)
        with open(target, "rb") as f:
            # 从文件末尾反向读取，避免全量加载到内存
            f.seek(0, 2)  # 移动到文件末尾
            file_end = f.tell()
            # FIX: [2026-08-22 P1] 行数 off-by-one：文件以 \n 结尾（真实日志标准形态）时，
            # 按 \n 反向分块切分会把结尾空串计为一行（total 多 1 且返回幻影空行）。
            # 文件以 \n 结尾时从倒数第 2 字节开始读取，跳过最后的换行符。
            pos = file_end
            if file_end > 0:
                f.seek(file_end - 1)
                if f.read(1) == b"\n":
                    pos = file_end - 1
            block_size = 8192
            remaining = b""

            while pos > 0 and len(lines) < _MAX_LOG_LINES:
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                # 拼接剩余部分并按行分割
                data = chunk + remaining
                # 使用 splitlines 处理，保留最后一个不完整行
                parts = data.split(b"\n")
                remaining = parts[0] if parts else b""
                # 从后向前逐行添加（跳过第一个，因为它是剩余部分）
                for line_bytes in reversed(parts[1:]):
                    if len(lines) >= _MAX_LOG_LINES:
                        break
                    try:
                        line = line_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                    lines.appendleft(line)

            # 处理文件开头剩余部分
            if remaining and len(lines) < _MAX_LOG_LINES:
                try:
                    lines.appendleft(remaining.decode("utf-8", errors="ignore"))
                except Exception as _decode_err:
                    # FIX [2026-07-17 P3-10]: 描述性日志替代 "silently_swallowed_exception"
                    logger.warning(f"logs endpoint: failed to decode remaining log bytes: {_decode_err}")

        # Filter by keyword if provided
        if keyword:
            keyword_lower = keyword.lower()
            lines = deque((line for line in lines if keyword_lower in line.lower()), maxlen=_MAX_LOG_LINES)

        total = len(lines)

        # Pagination
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "lines": list(lines)[start:end]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{filepath:path}/download")
def download_log_file(filepath: str, current_user=Depends(deps.require_roles(["admin", "owner"]))):  # FIX: [2026-07-16 P1] 升级权限，普通用户不应下载日志（含敏感信息）
    target = (LOGS_DIR / filepath).resolve()
    # FIX: [2026-07-16 P1] 用 is_relative_to 替换 startswith，防止同前缀目录绕过
    try:
        if not target.is_relative_to(LOGS_DIR):
            raise HTTPException(status_code=403, detail="Access denied")
    except (TypeError, ValueError):
        if not str(target).startswith(str(LOGS_DIR) + os.sep) and target != LOGS_DIR:
            raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(target, filename=target.name)

class LogManager:
    def __init__(self):
        self.active_connections: list[tuple[WebSocket, dict]] = []
        self.log_queue: Optional[asyncio.Queue] = None  # P1-8: Optional 防止 await None.get()

    def set_queue(self, queue: asyncio.Queue):
        self.log_queue = queue

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        qp = getattr(websocket, "query_params", None)
        contains_raw = (qp.get("contains") if qp else "") or ""
        contains_any_raw = (qp.get("contains_any") if qp else "") or ""
        contains_all = [s.strip() for s in str(contains_raw).split(",") if s.strip()]
        contains_any = [s.strip() for s in str(contains_any_raw).split(",") if s.strip()]
        self.active_connections.append((websocket, {"contains_all": contains_all, "contains_any": contains_any}))

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [(ws, f) for (ws, f) in self.active_connections if ws is not websocket]

    async def broadcast_log(self, message: str):
        # FIX: [2026-07-03] 广播时清理已断开的连接，防止 WebSocket 连接泄漏 [可靠性工程师]
        dead_connections: list[WebSocket] = []
        for connection, filters in list(self.active_connections):
            try:
                contains_all = filters.get("contains_all") or []
                contains_any = filters.get("contains_any") or []
                if contains_all and not all(token in message for token in contains_all):
                    continue
                if contains_any and not any(token in message for token in contains_any):
                    continue
                await connection.send_text(message)
            except (RuntimeError, ConnectionError, OSError):
                dead_connections.append(connection)
        # 清理已断开的连接
        if dead_connections:
            self.active_connections = [
                (ws, f) for ws, f in self.active_connections if ws not in dead_connections
            ]
            logger.debug(f"Cleaned up {len(dead_connections)} dead log WebSocket connections")

    async def drain_queue(self):
        # P1-8: 等待 queue 初始化完成，防止 await None.get() 抛 AttributeError
        while self.log_queue is None:
            await asyncio.sleep(0.1)
        while True:
            try:
                log_entry = await self.log_queue.get()
                await self.broadcast_log(log_entry)
            except Exception:
                await asyncio.sleep(0.1)

log_manager = LogManager()

# Thread-safe queue shared between sync log handler and async drainer
# FIX: [2026-07-16 P1] 设置 maxsize 防止 WebSocket 消费慢时 queue 无限增长导致 OOM
_LOG_QUEUE_MAXSIZE = 1000
_log_queue: Optional[asyncio.Queue] = None  # P1-8: Optional 类型标注
_log_queue_ref: list = []  # 惰性初始化
# FIX: [2026-07-16 P1] 统计被丢弃的日志条目数，定期记录 warning
_dropped_log_count: int = 0

def _get_log_queue() -> asyncio.Queue:
    global _log_queue, _log_queue_ref, _dropped_log_count
    if _log_queue is None:
        _log_queue = asyncio.Queue(maxsize=_LOG_QUEUE_MAXSIZE)
        log_manager.set_queue(_log_queue)
    return _log_queue

# Custom Log Handler to push logs to WebSocket
class WebSocketLogHandler(logging.Handler):
    def emit(self, record):
        global _dropped_log_count
        log_entry = self.format(record)
        try:
            q = _get_log_queue()
            q.put_nowait(log_entry)
        except asyncio.QueueFull:
            # FIX: [2026-07-16 P1] queue 满时丢弃最旧日志并计数，避免 OOM
            _dropped_log_count += 1
            if _dropped_log_count % 100 == 0:
                logger.warning(f"[LogQueue] Dropped {_dropped_log_count} log entries (queue full, maxsize={_LOG_QUEUE_MAXSIZE})")
            try:
                q.get_nowait()  # 丢弃最旧的一条
                q.put_nowait(log_entry)
            except Exception as _q_err:
                # FIX [2026-07-17 P3-31]: 描述性日志替代静默吞异常
                logger.debug(f"WebSocketLogHandler: queue overflow drop failed: {_q_err}")
        except Exception as e:
            logger.warning(f"Error: {e}")

# Add handler to root logger
ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
# FIX: [2026-07-16 P1] 改为只订阅应用日志，避免 root logger 的第三方库日志刷屏
logging.getLogger("app").addHandler(ws_handler)


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, ticket: str = ""):
    # P0-6: 改用短期一次性 ws-ticket 认证，消除 URL 暴露 JWT token
    # R-03 日志WebSocket添加认证，防止未授权读取系统日志
    if not ticket:
        await websocket.close(code=4001, reason="Missing ticket")
        return
    from app.core.ws_ticket import consume_ws_ticket
    payload = await consume_ws_ticket(ticket)
    if not payload or not payload.get("sub"):
        await websocket.close(code=4001, reason="Invalid or expired ticket")
        return
    await log_manager.connect(websocket)
    try:
        # FIX: [2026-07-03] 添加心跳机制，检测并清理断开的 WebSocket 连接 [可靠性工程师]
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
                await websocket.receive_text()  # Keep alive
        except WebSocketDisconnect:
            log_manager.disconnect(websocket)
    finally:
        heartbeat_task.cancel()
        log_manager.disconnect(websocket)
