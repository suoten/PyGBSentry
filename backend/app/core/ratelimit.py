import json
from pathlib import Path
from urllib.parse import parse_qs
from loguru import logger

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# --- 编码兼容修复：强制 starlette.config 以 UTF-8 读取配置文件 ---
# 详见 REQ-3.1 设计说明。
import starlette.config as _starlette_config_mod

def _utf8_read_file(self, file_name):
    file_values = {}
    try:
        with open(file_name, encoding="utf-8") as input_file:
            for line in input_file.readlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    file_values[key] = value
    except (OSError, IOError) as e:
        logger.warning(f"Failed to read rate limit config file: {e}")
    return file_values

_starlette_config_mod.Config._read_file = _utf8_read_file
# --- 编码兼容修复结束 ---

_config_file = str(Path(__file__).with_name(".env.slowapi"))
limiter = Limiter(key_func=get_remote_address, config_filename=_config_file)


# P2-5: tenant 维度限流 — 组合 tenant_id + IP 作为限流 key
def get_tenant_remote_address(request: Request) -> str:
    """组合 tenant_id + IP 作为限流 key。

    从 Authorization 头或 access_token cookie 中提取 JWT payload 的 tenant_id，
    组合 IP 生成限流 key。未认证或提取失败时仅用 IP（与 get_remote_address 等价）。

    注意：此函数仅用于限流 key 生成，不做 JWT 签名验证（认证由 deps.py 负责）。
    用法：``@limiter.limit("10/minute", key_func=get_tenant_remote_address)``
    """
    ip = get_remote_address(request)
    try:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token:
            token = request.cookies.get("access_token", "")
        if not token:
            return ip
        # 仅解码 payload（不验证签名）— 限流 key 用途，认证由 deps.py 负责
        import jwt as _jwt
        payload = _jwt.decode(token, options={"verify_signature": False})
        tenant_id = str(payload.get("tenant_id") or "").strip()
        if tenant_id:
            return f"t:{tenant_id}:{ip}"
    except Exception:
        logger.warning("silently_swallowed_exception", exc_info=True)
    return ip


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """与 slowapi 默认行为一致，并对登录/注册限流写审计（失败不阻断 429 响应）。"""
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.services.auth_audit import safe_auth_audit

    api = (settings.API_V1_STR or "/api/v1").rstrip("/")
    norm = (request.url.path or "").rstrip("/") or "/"
    reg_path = f"{api}/register"
    login_path = f"{api}/login/access-token"

    if norm == reg_path or norm == login_path:
        try:
            ip = get_remote_address(request) or "unknown"
            lim_safe = str(exc.detail).replace(";", ".").strip()[:240]
            if norm == reg_path:
                action, source = "register", "register"
                attempted = "unknown"
                try:
                    body = await request.body()
                    if body:
                        data = json.loads(body.decode("utf-8", errors="replace"))
                        if isinstance(data, dict):
                            attempted = (str(data.get("username") or "").strip() or "unknown")
                except Exception as e:
                    logger.warning(f"Error: {e}")
            else:
                action, source = "login", "login"
                attempted = "unknown"
                try:
                    body = await request.body()
                    if body:
                        q = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
                        u = (q.get("username") or [None])[0]
                        attempted = (u or "").strip() or "unknown"
                except Exception as e:
                    logger.warning(f"Error: {e}")
            async with AsyncSessionLocal() as db:
                await safe_auth_audit(
                    db,
                    module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
                    action=action,
                    source=source,
                    operator=attempted,
                    result="failed",
                    tenant_id="unknown",
                    status_code=429,
                    detail="rate_limited",
                    extra_summary=f"client_ip={ip}; limit={lim_safe}",
                )
        except Exception as e:
            logger.warning(f"Error: {e}")

    response = JSONResponse(
        {"error": f"Rate limit exceeded: {exc.detail}"}, status_code=429
    )
    response = request.app.state.limiter._inject_headers(
        response, request.state.view_rate_limit
    )
    return response


def init_rate_limiter(app):
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
