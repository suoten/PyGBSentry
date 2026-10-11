"""
plugins_official_account — 开源版插件中心「官网账户」代理端点。

双版账户打通（2026-10-10）：
开源版用户在插件中心登录自己的 PyGBSentry 官网账户（服务器版
/api/v1/oss/login 签发含 oss_auth 声明的 JWT），此后所有跨版操作
（市场目录浏览、插件包下载、购买、支付确认、安装上报）都携带该
官方 token，服务器版可直接验证身份与购买权益。

本模块只做转发，不保存官方 token——token 由前端保管并在后续请求中
通过 X-Official-Token 头携带。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.http_client import get_http_client

from .plugins_common import _normalize_marketplace_base

router = APIRouter()


class OfficialLoginRequest(BaseModel):
    username: str
    password: str


class OfficialRegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class OfficialVerifyRequest(BaseModel):
    token: str


def _require_marketplace_base() -> str:
    base = _normalize_marketplace_base()
    if not base:
        raise HTTPException(
            status_code=503,
            detail="Plugin marketplace is not configured. Set PLUGIN_MARKETPLACE_BASE_URL to the server edition address.",
        )
    return base


async def _proxy_to_server(path: str, json_body: dict) -> dict:
    import httpx

    base = _require_marketplace_base()
    url = f"{base}{path}"
    try:
        resp = await (await get_http_client()).post(url, json=json_body, timeout=15)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Cannot connect to plugin marketplace: {exc}")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    try:
        return resp.json()
    except Exception:
        return {}


@router.get("/official-account/status")
async def official_account_status():
    """插件中心据此决定是否展示官网账户登录入口。"""
    base = _normalize_marketplace_base()
    return {
        "marketplace_configured": bool(base),
        "marketplace_enabled": bool(settings.PLUGIN_MARKETPLACE_ENABLED),
        # 只回传主机名给前端展示，避免泄露内部配置细节
        "marketplace_host": _safe_host(base),
    }


def _safe_host(base: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(base).hostname or ""
    except Exception:
        return ""


@router.post("/official-account/login")
async def official_account_login(payload: OfficialLoginRequest):
    """登录官网账户（转发服务器版 /api/v1/oss/login）。"""
    return await _proxy_to_server(
        "/api/v1/oss/login",
        {"username": payload.username, "password": payload.password},
    )


@router.post("/official-account/register")
async def official_account_register(payload: OfficialRegisterRequest):
    """注册官网账户（转发服务器版 /api/v1/oss/register）。"""
    body: dict = {"username": payload.username, "password": payload.password}
    if payload.email:
        body["email"] = payload.email
    return await _proxy_to_server("/api/v1/oss/register", body)


@router.post("/official-account/verify")
async def official_account_verify(payload: OfficialVerifyRequest):
    """校验官方 token 是否有效（转发服务器版 /api/v1/oss/verify-token）。"""
    return await _proxy_to_server("/api/v1/oss/verify-token", {"token": payload.token})
