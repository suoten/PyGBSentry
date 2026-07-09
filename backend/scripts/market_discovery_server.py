#!/usr/bin/env python3
"""
market_discovery_server.py — PyGBSentry 插件市场发现服务

极简独立服务端，可部署为：
  - 独立 Python 服务（uvicorn）
  - Cloudflare Worker（需适配 WSGI）
  - Docker 容器

接口：
  GET /api/v1/market/endpoints  →  返回当前可用的官方市场 endpoint 列表（含签名）

启动：
  pip install fastapi uvicorn nacl
  python market_discovery_server.py
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
#  配置 — 从环境变量或本地文件加载
# ---------------------------------------------------------------------------

PRIMARY_ENDPOINT = os.environ.get(
    "PRIMARY_ENDPOINT", "https://pygb.jjtt.net"
)
BACKUP_ENDPOINTS = json.loads(
    os.environ.get(
        "BACKUP_ENDPOINTS",
        '["https://www.pygbsentry.cn", '
        '"https://pygb.ppuu.net"]',
    )
)
RESPONSE_TTL = int(os.environ.get("RESPONSE_TTL", "86400"))

# Ed25519 私钥（Base64 编码）— 从环境变量或文件加载
_PRIVATE_KEY_B64 = os.environ.get("ED25519_PRIVATE_KEY", "")
_PRIVATE_KEY_FILE = Path(__file__).parent / ".discovery_ed25519_key"

# ---------------------------------------------------------------------------
#  签名工具
# ---------------------------------------------------------------------------


def _load_private_key() -> bytes:
    """加载 Ed25519 私钥（Base64）。"""
    if _PRIVATE_KEY_B64:
        return base64.b64decode(_PRIVATE_KEY_B64)

    if _PRIVATE_KEY_FILE.exists():
        return base64.b64decode(_PRIVATE_KEY_FILE.read_text().strip())

    raise RuntimeError(
        "Ed25519 private key not found. "
        "Set ED25519_PRIVATE_KEY env var or run generate_discovery_keys.py first."
    )


def _sign_payload(payload: dict) -> str:
    """对 payload 签名，返回 Base64 编码的签名。"""
    try:
        from nacl.signing import SigningKey

        private_key_bytes = _load_private_key()
        signing_key = SigningKey(private_key_bytes)
        message = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signed = signing_key.sign(message.encode("utf-8"))
        return base64.b64encode(signed.signature).decode("ascii")
    except ImportError:
        # PyNaCl 未安装时返回空签名
        return ""


# ---------------------------------------------------------------------------
#  FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="PyGBSentry Market Discovery Service", version="1.0.0")


@app.get("/api/v1/market/endpoints")
async def get_endpoint():
    """返回当前可用的官方市场 endpoint 列表。"""
    payload = {
        "primary": PRIMARY_ENDPOINT,
        "backup": BACKUP_ENDPOINTS,
        "ttl": RESPONSE_TTL,
    }
    signature = _sign_payload(payload)
    if signature:
        payload["_signature"] = signature

    return JSONResponse(content=payload)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
#  入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
