"""
plugins_market — 插件市场/购买相关端点。
"""

import httpx

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.api import deps
from app.models.user import User
from app.core.config import settings
from app.core.http_client import get_http_client


class PurchaseConfirmPayload(BaseModel):
    order_id: str
    # dict→Pydantic schema，支付确认接口无类型校验可注入任意字段

from .plugins_common import (
    _authorization_for_server_proxy,
    _normalize_marketplace_base,
    _read_marketplace_catalog,
    _fetch_marketplace_items,
    _is_version_lt,
    get_purchased_plugin_ids_cached,
    _invalidate_purchased_plugin_ids_cache_for_user,
    EmbeddedPurchaseRequest,
)

router = APIRouter()


@router.get("/marketplace/public")
async def marketplace_public():
    if (settings.APP_EDITION or "oss").lower() != "server":
        raise HTTPException(status_code=404, detail="Not found")
    return _read_marketplace_catalog()


@router.get("/marketplace")
async def marketplace_proxy(
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    代理服务器版插件市场列表。服务器版不可用时直接报错，不回退到本地 marketplace.json。
    所有插件均从服务器版购买。
    """
    if (settings.APP_EDITION or "oss").lower() == "server":
        return _read_marketplace_catalog()
    return await _fetch_marketplace_items()  # 同步requests→异步httpx，避免阻塞事件循环


@router.get("/marketplace/update-summary")
async def marketplace_update_summary(
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    对比已加载插件的 version 与市场 catalog version，供前端展示「可更新」。
    服务器版不可用时直接报错，不回退到本地 marketplace.json。
    所有插件均从服务器版购买。
    """
    from .plugins_common import plugin_manager

    if (settings.APP_EDITION or "oss").lower() == "server":
        market_items = _read_marketplace_catalog()
    else:
        market_items = await _fetch_marketplace_items()  # 同步requests→异步httpx，避免阻塞事件循环
    by_id = {
        str(x.get("id")): x
        for x in market_items
        if isinstance(x, dict) and x.get("id") is not None
    }
    items_out: list[dict] = []
    for pid in sorted(plugin_manager.metadata.keys()):
        cur = str((plugin_manager.metadata.get(pid) or {}).get("version") or "").strip()
        mp = by_id.get(str(pid)) or {}
        latest = str(mp.get("version") or "").strip()
        has_update = bool(latest and cur and _is_version_lt(cur, latest))
        items_out.append({
            "plugin_id": pid,
            "installed_version": cur,
            "marketplace_version": latest,
            "has_update": has_update,
        })
    return {"items": items_out}


@router.get("/purchased")
async def list_purchased_plugins_proxy(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    代理请求服务器版 GET /api/v1/plugins/purchased，返回当前用户已购买插件 ID 列表。
    用于「已购买未安装」时仅显示安装按钮、隐藏购买按钮。配置了 PLUGIN_SERVER_RECORD_URL 或
    PLUGIN_MARKETPLACE_BASE_URL 时才会请求服务器，否则返回空列表。
    """
    from .plugins_common import _purchased_proxy_base_url

    base_url = _purchased_proxy_base_url()
    if not base_url:
        return {"plugin_ids": []}
    ids_set = await get_purchased_plugin_ids_cached(request, current_user)
    plugin_ids = sorted(ids_set)

    # 服务器版可能只返回 ids；开源端用 marketplace catalog 补齐 name/title 供界面展示
    catalog = _read_marketplace_catalog() or []
    mapping = {str(it.get("id") or ""): it for it in catalog if isinstance(it, dict)}

    plugins: list[dict] = []
    for pid in plugin_ids:
        meta = mapping.get(pid) or {}
        pname = str(meta.get("name") or meta.get("title") or pid)
        plugins.append({
            "id": pid,
            "name": pname,
            "type": str(meta.get("type") or "unknown"),
        })

    plugin_id_to_name = {p["id"]: p.get("name") for p in plugins if isinstance(p, dict) and p.get("id")}
    return {"plugin_ids": plugin_ids, "plugins": plugins, "plugin_id_to_name": plugin_id_to_name}


@router.get("/marketplace-shop-url")
async def get_marketplace_shop_url(
    current_user: User = Depends(deps.get_current_active_user),
):
    """返回服务器版插件商城地址，供前端「购买」按钮新窗口打开。"""
    base = (settings.PLUGIN_MARKETPLACE_BASE_URL or "").rstrip("/")
    shop = (settings.PLUGIN_MARKETPLACE_SHOP_URL or "").strip()
    url = shop if shop else base
    return {"url": url or base}


@router.post("/marketplace/purchase")
async def embedded_purchase(
    request: Request,
    payload: EmbeddedPurchaseRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    内嵌购买代理：在开源版内直接发起购买，代理到服务器版创建订单。
    简化用户流程：无需跳转到服务器版，一键完成购买。
    """
    base_url = _normalize_marketplace_base()
    if not base_url:
        raise HTTPException(status_code=503, detail="Plugin marketplace not configured, cannot purchase")
    auth_header = _authorization_for_server_proxy(request)
    if not auth_header:
        raise HTTPException(status_code=401, detail="Please login before purchasing")
    create_url = f"{base_url}/api/v1/billing/orders"
    order_body = {
        "plugin_id": payload.plugin_id,
        "billing_period": payload.billing_period,
        "quantity": 1,
        "source": "oss_embedded",
    }
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "X-Forwarded-For": request.client.host if request.client else "",
    }
    try:
        resp = await (await get_http_client()).post(create_url, json=order_body, headers=headers, timeout=15)  # 同步requests→异步httpx，避免阻塞事件循环
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Cannot connect to plugin marketplace：{exc}")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    order_data = resp.json()
    await _invalidate_purchased_plugin_ids_cache_for_user(str(current_user.id))
    return order_data


@router.post("/marketplace/purchase/confirm")
async def embedded_purchase_confirm(
    request: Request,
    payload: PurchaseConfirmPayload,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    内嵌购买确认：支付回调后确认订单并自动安装插件。
    一键购买安装流程：支付确认 → 自动安装 → 自动激活。
    """
    base_url = _normalize_marketplace_base()
    if not base_url:
        raise HTTPException(status_code=503, detail="Plugin marketplace not configured")
    auth_header = _authorization_for_server_proxy(request)
    if not auth_header:
        raise HTTPException(status_code=401, detail="Please login first")
    order_id = payload.order_id
    confirm_url = f"{base_url}/api/v1/billing/orders/{order_id}/confirm-embedded"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    try:
        resp = await (await get_http_client()).post(confirm_url, json=payload.model_dump(), headers=headers, timeout=15)  # 同步requests→异步httpx，避免阻塞事件循环
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Cannot connect to plugin marketplace：{exc}")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    await _invalidate_purchased_plugin_ids_cache_for_user(str(current_user.id))
    return resp.json()
