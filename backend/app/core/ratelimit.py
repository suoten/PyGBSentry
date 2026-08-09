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

def _utf8_read_file(self, file_name, *args, **kwargs):
    # FIX: [2026-07-13] 新版 Starlette 的 Config._read_file 可能传入额外参数
    # (如 _depth)，使用 *args/**kwargs 兼容所有版本，避免
    # "_utf8_read_file() takes 2 positional arguments but 3 were given" 错误
    # 导致 login/user_api_keys 等模块导入失败。[全栈工程师]
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

    FIX: [2026-07-16 P1] 改为使用 SECRET_KEY 验签 JWT，防止攻击者伪造任意 tenant_id
    绕过限流。验签失败时回退到纯 IP key。

    用法：``@limiter.limit("10/minute", key_func=get_tenant_remote_address)``
    """
    ip = get_remote_address(request)
    try:
        # 优先从 request.state.user 读取（已认证的请求）
        user = getattr(request.state, "user", None)
        if user is not None:
            tenant_id = str(getattr(user, "tenant_id", "") or "").strip()
            if tenant_id:
                return f"t:{tenant_id}:{ip}"
        # 回退：验签 JWT 提取 tenant_id（不依赖 deps 认证流程）
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token:
            token = request.cookies.get("access_token", "")
        if not token:
            return ip
        # FIX: [2026-07-16 P1] 使用 SECRET_KEY 验签，防止伪造 tenant_id 绕过限流
        import jwt as _jwt
        from app.core.config import settings
        secret = settings.SECRET_KEY
        if not secret:
            return ip
        try:
            payload = _jwt.decode(token, secret, algorithms=["HS256"])
        except Exception:
            # 验签失败：可能是伪造的 JWT，回退到纯 IP（更严格的限流）
            return ip
        tenant_id = str(payload.get("tenant_id") or "").strip()
        if tenant_id:
            return f"t:{tenant_id}:{ip}"
    except Exception as _jwt_err:
        # FIX [2026-07-17 P3-6]: 描述性日志替代 "silently_swallowed_exception"
        logger.warning(f"_get_rate_limit_key: JWT decode/tenant_id extraction failed, falling back to IP-only limiter: {_jwt_err}")
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
