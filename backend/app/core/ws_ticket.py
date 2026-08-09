"""Short-lived, single-use WebSocket tickets.

A WS ticket is a signed token issued by an authenticated HTTP endpoint and
consumed once when the corresponding WebSocket connection opens. This bridges
the HTTP-authenticated world with WebSocket endpoints (logs, alarms, talk,
sip-trace) that cannot easily carry a JWT in query params without exposing it.

Ticket format: ``base64url(payload_json).signature`` where signature is
HMAC-SHA256(payload, SECRET_KEY). Tickets expire after ``_TTL_SECONDS`` and
are single-use (consumed tickets are tracked in a bounded LRU set).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import OrderedDict
from typing import Any, Optional

from loguru import logger

from app.core.config import settings

_TTL_SECONDS = 120
_REPLAY_CACHE_MAX = 1024
# FIX [2026-07-18 P1]: 允许同一 ticket 在 5 秒窗口内被多次验证（浏览器重试场景）。
# 原问题：浏览器在 WebSocket 连接失败时可能立即重试（如 nginx 暂时 502），
# 如果使用同一 ticket URL（如用户刷新页面），第二次连接会被判为 replay 而拒绝。
# 实际上 ws-ticket 已经过期检查（120s TTL），5 秒内的"重放"是合理的网络重试行为。
_REPLAY_GRACE_SECONDS = 5.0
_replay: "OrderedDict[str, float]" = OrderedDict()


def _secret() -> bytes:
    return str(settings.SECRET_KEY or "").encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _sign(payload_b64: str) -> str:
    return _b64encode(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())


async def issue_ws_ticket(payload: Any, ttl: int = _TTL_SECONDS) -> tuple[str, int]:
    """Issue a single-use WS ticket carrying ``payload`` (JSON-serialisable)."""
    body = {
        "payload": payload,
        "exp": int(time.time()) + int(ttl),
    }
    raw = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    payload_b64 = _b64encode(raw)
    sig = _sign(payload_b64)
    ticket = f"{payload_b64}.{sig}"
    return ticket, int(ttl)


async def consume_ws_ticket(ticket: str) -> Optional[Any]:
    """Validate and consume a WS ticket; return its payload or ``None``."""
    if not ticket or "." not in ticket:
        return None
    payload_b64, _, sig = ticket.rpartition(".")
    if not payload_b64 or not sig:
        return None
    expected = _sign(payload_b64)
    if not hmac.compare_digest(expected, sig):
        logger.warning("ws_ticket: invalid signature")
        return None
    # replay protection
    now = time.time()
    if payload_b64 in _replay:
        # FIX [2026-07-18 P1]: 5 秒内的"重放"视为合法重试（浏览器连接失败重连场景）
        _first_seen = _replay[payload_b64]
        if now - _first_seen > _REPLAY_GRACE_SECONDS:
            logger.warning("ws_ticket: replay detected")
            return None
        # 在 grace 窗口内，放行但不重新记录时间（防止无限重放）
        logger.debug(f"ws_ticket: replay within grace window ({now - _first_seen:.2f}s), allowing")
    try:
        raw = _b64decode(payload_b64)
        body = json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.warning(f"ws_ticket: decode failed: {e}")
        return None
    if int(body.get("exp", 0)) < now:
        logger.warning("ws_ticket: expired")
        return None
    # 只在首次成功验证时记录，grace 窗口内的重放不更新时间戳
    if payload_b64 not in _replay:
        _replay[payload_b64] = now
        if len(_replay) > _REPLAY_CACHE_MAX:
            _replay.popitem(last=False)
    return body.get("payload")
