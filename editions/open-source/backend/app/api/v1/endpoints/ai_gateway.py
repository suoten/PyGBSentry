from __future__ import annotations

import asyncio
import base64
from loguru import logger
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request, Depends

from app.core.config import settings
from app.core.http_client import get_http_client
from app.api import deps
from app.models.user import User

router = APIRouter()



def _safe_str(v: Any) -> str:
    s = str(v or "").strip()
    # 防止目录穿越：只允许替换常见分隔符
    return s.replace("/", "_").replace("\\", "_").replace("..", "_")


def _extract_base64_str(raw: str) -> str:
    """
    支持：
    - 纯 base64
    - data:image/jpeg;base64,xxxx...
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    if "base64," in s:
        return s.split("base64,", 1)[1].strip()
    return s


def _maybe_save_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    b64_raw = payload.get("snapshot_image_base64")
    if not b64_raw:
        return {"saved": False}

    algo = _safe_str(payload.get("algorithm_type") or "unknown")
    device_id = _safe_str(payload.get("device_id") or "unknown_device")
    channel_id = _safe_str(payload.get("channel_id") or "unknown_channel")

    snap_dir = _safe_str(getattr(settings, "AI_GATEWAY_SNAPSHOT_DIR", "ai_gateway_snapshots") or "ai_gateway_snapshots")
    max_kb = int(getattr(settings, "AI_GATEWAY_MAX_SNAPSHOT_KB", 512) or 512)
    max_bytes = max_kb * 1024

    b64 = _extract_base64_str(str(b64_raw))
    if not b64:
        return {"saved": False}

    try:
        img_bytes = base64.b64decode(b64, validate=False)
    except Exception:
        return {"saved": False, "error": "invalid_base64"}

    if len(img_bytes) > max_bytes:
        return {"saved": False, "error": "snapshot_too_large"}

    dt = datetime.now(timezone.utc)
    date_dir = dt.strftime("%Y%m%d")
    out_dir = os.path.join(snap_dir, algo, device_id, channel_id, date_dir)
    os.makedirs(out_dir, exist_ok=True)

    mime = str(payload.get("snapshot_mime") or "image/jpeg").lower()
    ext = "jpg"
    if "png" in mime:
        ext = "png"

    fname = f"{dt.strftime('%H%M%S')}_{int(time.time() * 1000)}.{ext}"
    path = os.path.join(out_dir, fname)

    try:
        with open(path, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        return {"saved": False, "error": f"write_failed:{e}"}

    return {"saved": True, "path": path}


async def _forward_to_upstream(payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, str]:
    url = str(getattr(settings, "AI_GATEWAY_FORWARD_UPSTREAM_URL", "") or "").strip()
    if not url:
        return 204, "no_upstream_config"
    timeout = int(getattr(settings, "AI_GATEWAY_FORWARD_TIMEOUT_SECONDS", 10) or 10)

    try:
        resp = await (await get_http_client()).post(url, json=payload, headers=headers, timeout=timeout)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
        return int(getattr(resp, "status_code", 0) or 0), (getattr(resp, "text", "") or "")[:2000]
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning("AI gateway upstream request failed: %s", e)
        return 0, f"upstream_error:{type(e).__name__}"
    # FIXED: requests.post无try-catch，网络异常导致未捕获异常


@router.post("/analyze")
async def analyze_ai_callback(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "detail": "invalid_json"}
    if not isinstance(payload, dict):
        return {"ok": False, "detail": "payload_must_be_object"}

    snapshot_result = _maybe_save_snapshot(payload)

    forward_url = str(getattr(settings, "AI_GATEWAY_FORWARD_UPSTREAM_URL", "") or "").strip()
    forward_status: Optional[int] = None
    forward_text: Optional[str] = None

    if forward_url:
        # 插件会通过 auth_header 传 Authorization，这里原样转发给上游（如果上游需要）
        auth = request.headers.get("Authorization")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = auth

        try:
            forward_status, forward_text = await _forward_to_upstream(payload, headers)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
        except Exception as e:
            logger.warning("AI gateway upstream forward failed: %s", e)
            forward_status, forward_text = None, None

    return {
        "ok": True,
        "algorithm_type": payload.get("algorithm_type"),
        "snapshot": snapshot_result,
        "forward_status": forward_status,
        "forward_text_prefix": (forward_text[:200] if forward_text else None),
    }

