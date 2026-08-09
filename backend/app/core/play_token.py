"""Play-token verification for ZLM on_play authentication.

A play token is a signed JWT-like token issued by the backend when a client
requests to play a stream. ZLM forwards it back via the ``on_play`` hook so
the backend can authorise the viewer. Tokens are HMAC-SHA256 signed with the
platform SECRET_KEY and bind the (app, stream) pair.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from loguru import logger

from app.core.config import settings

# P2-fix [2026-07-17]: 统一 TTL 默认值与 _shared.py 的 _get_play_token_ttl() 一致（300 秒）。
# 原值 7200 秒（2 小时）与实际调用方传入的 300 秒不一致，且 token 通过 URL 查询参数暴露，
# 过长 TTL 增加重放风险。300 秒足够覆盖播放建立时间。
_TTL_SECONDS = 300


def _secret() -> bytes:
    return str(settings.SECRET_KEY or "").encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def issue_play_token(app: str, stream: str, ttl: int = _TTL_SECONDS) -> str:
    """Issue a signed play token bound to ``(app, stream)``."""
    body = {"app": app, "stream": stream, "exp": int(time.time()) + int(ttl)}
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_b64 = _b64url(raw)
    sig = _b64url(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())
    return f"{payload_b64}.{sig}"


def generate_play_token(app: str, stream: str, expire_seconds: int = _TTL_SECONDS) -> str:
    """Alias for :func:`issue_play_token` — 2ad636a API compatibility.

    stream/_shared.py (restored from 2ad636a) uses the original name
    ``generate_play_token`` with ``expire_seconds`` parameter.

    FIX: [2026-07-13] 恢复 channel.py / stream/_shared.py 后需要此函数。
    """
    return issue_play_token(app, stream, ttl=expire_seconds)


def extract_token_from_params(params: Any) -> str:
    """Pull a ``playToken`` value out of ZLM hook params (dict or query string)."""
    if not params:
        return ""
    if isinstance(params, dict):
        return str(params.get("playToken") or params.get("token") or "").strip()
    if isinstance(params, str):
        raw = params.strip().lstrip("?")
        for part in raw.split("&"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k.strip() in ("playToken", "token"):
                return v.strip()
    return ""


def should_allow_no_token() -> bool:
    """Return True when the platform is configured to allow playback without a token."""
    return settings.PLAY_ALLOW_NO_TOKEN


def verify_play_token(token: str, app: str, stream: str) -> tuple[bool, str]:
    """Verify a play token; return ``(is_valid, error_message)``."""
    if not token:
        return False, "missing play token"
    if "." not in token:
        return False, "malformed play token"
    payload_b64, _, sig = token.rpartition(".")
    if not payload_b64 or not sig:
        return False, "malformed play token"
    expected = _b64url(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return False, "invalid play token signature"
    try:
        body = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as e:
        logger.debug(f"play_token: decode failed: {e}")
        return False, "malformed play token payload"
    if int(body.get("exp", 0)) < int(time.time()):
        return False, "play token expired"
    if str(body.get("app", "")) != str(app) or str(body.get("stream", "")) != str(stream):
        return False, "play token does not match stream"
    return True, ""
