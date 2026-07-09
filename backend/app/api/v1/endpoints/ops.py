"""运维监控 API 端点。

提供系统状态、数据库检查、诊断报告等运维监控功能。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.db.session import get_db
from app.core.config import settings
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api import deps
from loguru import logger
import psutil
import platform
import time
import os
from datetime import datetime, timezone
from typing import Any

router = APIRouter()

_start_time = time.time()


@router.get("/status")
async def get_ops_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """系统运维状态：CPU、内存、ZLM 状态、流数量等。"""
    # CPU & Memory
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
    except Exception:
        cpu_percent = 0
        memory_percent = 0

    # Disk
    try:
        disk = psutil.disk_usage("/")
        disk_percent = round(disk.used / disk.total * 100, 1) if disk.total > 0 else 0
    except Exception:
        disk_percent = 0

    # ZLM status
    zlm_status = "Offline"
    zlm_streams = 0
    zlm_target = ""
    zlm_error = ""
    zlm_node_id = ""
    zlm_select_reason = ""
    zlm_select_reason_label = ""
    try:
        from app.services.media_manager import get_media_server_info
        media_info = get_media_server_info()
        zlm_target = f"{media_info.get('host', '')}:{media_info.get('http_port', '')}"
        # Check ZLM connectivity
        from app.core.http_client import get_http_client
        client = await get_http_client()
        _url = f"http://{media_info.get('host', '127.0.0.1')}:{media_info.get('http_port', 8880)}/index/api/getServerConfig"
        _resp = await client.post(_url, data={"secret": media_info.get("secret", "")}, timeout=3.0)
        if _resp.status_code == 200:
            _data = _resp.json() or {}
            if _data.get("code") in (0, "0"):
                zlm_status = "Online"
    except Exception as e:
        zlm_error = str(e)[:200]

    # Stream count from DB
    try:
        stream_count_stmt = select(func.count(StreamSession.id)).where(StreamSession.status == 1)
        zlm_streams = int((await db.execute(stream_count_stmt)).scalar() or 0)
    except Exception:
        zlm_streams = 0

    # Uptime
    uptime_seconds = int(time.time() - _start_time)

    # Process info
    try:
        process = psutil.Process(os.getpid())
        process_memory_mb = round(process.memory_info().rss / 1024 / 1024, 1)
        process_threads = process.num_threads()
    except Exception:
        process_memory_mb = 0
        process_threads = 0

    return {
        "cpu": round(cpu_percent, 1),
        "memory_percent": round(memory_percent, 1),
        "disk_percent": disk_percent,
        "zlm_status": zlm_status,
        "zlm_streams": zlm_streams,
        "zlm_target": zlm_target,
        "zlm_error": zlm_error,
        "zlm_node_id": zlm_node_id,
        "zlm_select_reason": zlm_select_reason,
        "zlm_select_reason_label": zlm_select_reason_label,
        "uptime_seconds": uptime_seconds,
        "process_memory_mb": process_memory_mb,
        "process_threads": process_threads,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/db-check")
async def db_check(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """数据库连接检查（无需认证，用于健康探针）。"""
    try:
        result = await db.execute(text("SELECT 1"))
        _ = result.scalar()
        return {"connected": True, "database": getattr(settings, "DATABASE_TYPE", "unknown")}
    except Exception as e:
        logger.warning(f"DB check failed: {e}")
        return {"connected": False, "error": str(e)[:200], "database": getattr(settings, "DATABASE_TYPE", "unknown")}


@router.get("/diagnose")
async def diagnose(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """快速诊断报告。"""
    items: list[dict[str, Any]] = []

    # 1. Database
    try:
        await db.execute(text("SELECT 1"))
        items.append({"section": "database", "status": "ok", "text": "Database connection OK"})
    except Exception as e:
        items.append({"section": "database", "status": "error", "text": f"Database error: {e}"})

    # 2. ZLM
    try:
        from app.services.media_manager import get_media_server_info
        media_info = get_media_server_info()
        from app.core.http_client import get_http_client
        client = await get_http_client()
        _url = f"http://{media_info.get('host', '127.0.0.1')}:{media_info.get('http_port', 8880)}/index/api/getServerConfig"
        _resp = await client.post(_url, data={"secret": media_info.get("secret", "")}, timeout=3.0)
        if _resp.status_code == 200:
            items.append({"section": "zlm", "status": "ok", "text": f"ZLM Online at {media_info.get('host')}:{media_info.get('http_port')}"})
        else:
            items.append({"section": "zlm", "status": "error", "text": f"ZLM HTTP {_resp.status_code}"})
    except Exception as e:
        items.append({"section": "zlm", "status": "error", "text": f"ZLM unreachable: {e}"})

    # 3. SIP Server
    try:
        from app.sip.server import sip_server
        if sip_server and sip_server._running:
            items.append({"section": "sip", "status": "ok", "text": "SIP server running"})
        else:
            items.append({"section": "sip", "status": "warn", "text": "SIP server not running"})
    except Exception:
        items.append({"section": "sip", "status": "warn", "text": "SIP server status unknown"})

    # 4. Redis (optional)
    try:
        from app.core.redis import redis_client
        if redis_client:
            await redis_client.ping()
            items.append({"section": "redis", "status": "ok", "text": "Redis connected"})
        else:
            items.append({"section": "redis", "status": "ok", "text": "Redis not configured (optional)"})
    except Exception as e:
        items.append({"section": "redis", "status": "warn", "text": f"Redis: {e}"})

    # 5. System resources
    try:
        import psutil as _psutil
        _cpu = _psutil.cpu_percent(interval=0.5)
        _mem = _psutil.virtual_memory()
        _disk = _psutil.disk_usage("/")
        items.append({
            "section": "system",
            "status": "ok" if _cpu < 80 and _mem.percent < 80 else "warn",
            "text": f"CPU: {_cpu:.1f}%, Memory: {_mem.percent:.1f}%, Disk: {(_disk.used/_disk.total*100):.1f}%"
        })
    except Exception:
        items.append({"section": "system", "status": "ok", "text": "System metrics unavailable"})

    ok_count = sum(1 for x in items if x["status"] == "ok")
    error_count = sum(1 for x in items if x["status"] == "error")
    summary = "All systems operational" if error_count == 0 else f"{error_count} issue(s) detected"

    return {
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "ok_count": ok_count,
        "error_count": error_count,
    }


@router.get("/diagnose-report")
async def diagnose_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """完整诊断报告（与 /diagnose 相同，提供别名供前端使用）。"""
    return await diagnose(db=db, current_user=current_user)
