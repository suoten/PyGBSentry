import os
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import FileResponse
import asyncio
import logging  # FIXED-P0: logging.Handler 基类需要导入 logging 模块
from loguru import logger
from collections import deque
from app.api import deps  # S-06-03 日志HTTP接口添加认证依赖


router = APIRouter()

LOGS_DIR = Path("logs").resolve()

# 全量读取日志文件到内存 → 从文件末尾反向读取，使用 deque 限制最大行数
_MAX_LOG_LINES = 10000
_MAX_LOG_FILE_SIZE = 50 * 1024 * 1024  # 50MB

@router.get("/files")
def list_log_files(current_user=Depends(deps.get_current_active_user)):  # S-06-03 添加认证
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
def get_log_lines(filepath: str, keyword: str = "", page: int = 1, page_size: int = 1000, current_user=Depends(deps.get_current_active_user)):  # S-06-03 添加认证
    target = (LOGS_DIR / filepath).resolve()
    if not str(target).startswith(str(LOGS_DIR)):
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
            block_size = 8192
            remaining = b""
            pos = file_end

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
                except Exception:
                    pass

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
def download_log_file(filepath: str, current_user=Depends(deps.get_current_active_user)):  # S-06-03 添加认证
    target = (LOGS_DIR / filepath).resolve()
    if not str(target).startswith(str(LOGS_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(target, filename=target.name)

class LogManager:
    def __init__(self):
        self.active_connections: list[tuple[WebSocket, dict]] = []
        self.log_queue: asyncio.Queue = None  # type: ignore

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
                logger.warning("(RuntimeError, ConnectionError, OSError) occurred")

    async def drain_queue(self):
        while True:
            try:
                log_entry = await self.log_queue.get()
                await self.broadcast_log(log_entry)
            except Exception:
                await asyncio.sleep(0.1)

log_manager = LogManager()

# Thread-safe queue shared between sync log handler and async drainer
_log_queue: asyncio.Queue = None  # type: ignore
_log_queue_ref: list = []  # 惰性初始化

def _get_log_queue() -> asyncio.Queue:
    global _log_queue, _log_queue_ref
    if _log_queue is None:
        _log_queue = asyncio.Queue()
        log_manager.set_queue(_log_queue)
    return _log_queue

# Custom Log Handler to push logs to WebSocket
class WebSocketLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        try:
            q = _get_log_queue()
            q.put_nowait(log_entry)
        except Exception as e:
            logger.warning(f"Error: {e}")

# Add handler to root logger
ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(ws_handler)


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, token: str = ""):
    # R-03 日志WebSocket添加token认证，防止未授权读取系统日志
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        from app.core import security
        payload = security.verify_token(token)
        if not payload or not payload.get("sub"):
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    await log_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)