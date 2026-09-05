from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import hmac
import hashlib
import json
import os
from app.db.session import get_db
from app.models.billing import (
    BillingPlan, TenantSubscription, TenantBranding, PluginOrder,
    SubscriptionDowngradeLog,
)
from app.models.user import User
from app.api import deps
from app.api.deps import get_or_404
from app.core.config import settings
from app.services.auth_audit import safe_auth_audit
from loguru import logger

if (settings.APP_EDITION or "oss").lower() == "server":
    from app.services.license_service import sign_license_payload
else:
    sign_license_payload = None

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"
PLUGIN_DIR = "plugins"
MARKETPLACE_CATALOG_PATH = os.path.join(PLUGIN_DIR, "marketplace.json")

class BillingPlanCreate(BaseModel):
    code: str
    name: str
    price_monthly: int = 0
    max_devices: int = 0
    max_channels: int = 0
    plugin_entitlements: str = ""
    is_active: bool = True

class SubscriptionUpdate(BaseModel):
    tenant_id: str
    plan_code: str
    status: str = "active"
    trial_ends_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None

class BrandingUpdate(BaseModel):
    product_name: str = "PyGBSentry"
    logo_url: Optional[str] = None
    primary_color: str = "#1f2937"
    welcome_text: str = "Welcome to PyGBSentry"

class PluginOrderCreate(BaseModel):
    plugin_id: str
    months: int = 1
    pay_channel: str = ""

class PaymentCallbackPayload(BaseModel):
    order_no: str
    status: str
    paid_amount: int = 0
    paid_at: Optional[datetime] = None
    provider_trade_no: Optional[str] = None
    signature: str

def _load_marketplace_catalog() -> list[dict]:
    if not os.path.exists(MARKETPLACE_CATALOG_PATH):
        return []
    try:
        with open(MARKETPLACE_CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Marketplace catalog load failed: {e}")
        data = {}  # 文件I/O异常保护
    if not isinstance(data, list):
        return []
    items = [item for item in data if isinstance(item, dict)]
    # 商业策略：不透出 trial_days 字段
    for it in items:
        if isinstance(it, dict) and "trial_days" in it:
            it.pop("trial_days", None)
    return items


async def _fetch_server_trial_config() -> dict | None:
    base_url = (settings.PLUGIN_MARKETPLACE_BASE_URL or "").rstrip("/")
    record_url = (settings.PLUGIN_SERVER_RECORD_URL or "").strip()
    if record_url:
        from urllib.parse import urlparse
        parsed = urlparse(record_url)
        if parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
    if not base_url:
        return None
    try:
        from app.core.http_client import get_http_client
        client = await get_http_client()
        resp = await client.get(f"{base_url}/api/v1/plugins/trial-config", timeout=8.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    return None


@router.get("/trial/status")
async def get_trial_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    server_config = await _fetch_server_trial_config()
    if server_config:
        enable_trial = bool(server_config.get("enable_trial", False))
        default_trial_days = int(server_config.get("default_trial_days", 7) or 7)
        plugin_trial_days = server_config.get("plugin_trial_days") or {}
    else:
        enable_trial = settings.TRIAL_DAYS > 0
        default_trial_days = settings.TRIAL_DAYS
        plugin_trial_days = {}

    tenant_id = current_user.tenant_id or "default"
    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    result = await db.execute(stmt)
    sub = result.scalars().first()

    if not sub:
        return {
            "status": "none",
            "enable_trial": enable_trial,
            "trial_available": enable_trial,
            "trial_days": default_trial_days,
            "trial_ends_at": None,
            "days_remaining": 0,
            "plugin_trial_days": plugin_trial_days,
        }

    now = datetime.now(timezone.utc)
    trial_ends_at = sub.trial_ends_at
    if trial_ends_at and trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)

    is_trial = sub.status == "trial"
    is_expired = is_trial and trial_ends_at and now > trial_ends_at
    days_remaining = 0
    if is_trial and trial_ends_at and not is_expired:
        delta = trial_ends_at - now
        days_remaining = max(0, delta.days)

    return {
        "status": "expired" if is_expired else (sub.status or "active"),
        "enable_trial": enable_trial,
        "trial_available": enable_trial and not is_trial,
        "trial_days": default_trial_days,
        "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
        "days_remaining": days_remaining,
        "plan_code": sub.plan_code,
        "plugin_trial_days": plugin_trial_days,
    }


class TrialActivateRequest(BaseModel):
    plugin_id: str


@router.post("/trial/activate")
async def activate_trial(
    payload: TrialActivateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    server_config = await _fetch_server_trial_config()
    if server_config:
        enable_trial = bool(server_config.get("enable_trial", False))
        default_trial_days = int(server_config.get("default_trial_days", 7) or 7)
        plugin_trial_days = server_config.get("plugin_trial_days") or {}
    else:
        enable_trial = settings.TRIAL_DAYS > 0
        default_trial_days = settings.TRIAL_DAYS
        plugin_trial_days = {}

    if not enable_trial:
        raise HTTPException(status_code=403, detail="Trial feature not enabled, please contact server admin")

    tenant_id = current_user.tenant_id or "default"
    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    result = await db.execute(stmt)
    sub = result.scalars().first()

    if sub and sub.status == "trial":
        now = datetime.now(timezone.utc)
        trial_end = sub.trial_ends_at
        if trial_end and trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        if trial_end and trial_end > now:
            raise HTTPException(status_code=409, detail="Trial already activated, no need to activate again")

    trial_days = int(plugin_trial_days.get(payload.plugin_id, default_trial_days) or default_trial_days)
    trial_days = max(1, min(trial_days, 365))
    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=trial_days)

    if not sub:
        sub = TenantSubscription(
            tenant_id=tenant_id,
            plan_code="community",
            status="trial",
            trial_ends_at=trial_ends_at,
        )
        db.add(sub)
    else:
        sub.status = "trial"
        sub.trial_ends_at = trial_ends_at

    await db.commit()
    await db.refresh(sub)

    await safe_auth_audit(
        db,
        module="billing",
        action="trial_activate",
        source="trial_api",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tenant_id,
        status_code=200,
        detail="ok",
        extra_summary=f"plugin_id={payload.plugin_id}; trial_days={trial_days}",
    )

    return {
        "status": "trial",
        "trial_days": trial_days,
        "trial_ends_at": trial_ends_at.isoformat(),
        "plugin_id": payload.plugin_id,
    }


def _sign_callback(order_no: str, status: str, paid_amount: int, provider_trade_no: str | None) -> str:
    secret = settings.PAYMENT_CALLBACK_SECRET or settings.SECRET_KEY
    payload = f"{order_no}|{status}|{paid_amount}|{provider_trade_no or ''}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def _verify_callback_signature(payload: PaymentCallbackPayload) -> bool:
    expected = _sign_callback(payload.order_no, payload.status, payload.paid_amount, payload.provider_trade_no)
    return hmac.compare_digest(expected, payload.signature)

def _build_plugin_license(order: PluginOrder) -> dict:
    if sign_license_payload is None:
        raise HTTPException(status_code=403, detail="License signing not available in this edition")
    expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    unsigned = {
        "license_mode": "online",
        "tenant_id": order.tenant_id,
        "plugin_id": order.plugin_id,
        "feature_codes": [order.plugin_id],
        "expires_at": expires_at.isoformat() + "Z",
    }
    signed = sign_license_payload(unsigned, settings.LICENSE_ED25519_PRIVATE_KEY)
    order.expires_at = expires_at
    order.license_data = json.dumps(signed, ensure_ascii=False)
    return signed


@router.get("/plans")
async def list_plans(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    返回所有可订阅套餐列表。
    - 服务器版（APP_EDITION=server）：从数据库 BillingPlan 表查询
    - 开源版：从配置文件读取或返回 community 套餐兜底
    """
    is_server = (settings.APP_EDITION or "oss").lower() == "server"
    if is_server:
        stmt = select(BillingPlan).where(BillingPlan.is_active)
        if current_user.is_superuser:
            stmt = select(BillingPlan)
        result = await db.execute(stmt)
        return result.scalars().all()

    # 开源版：从配置文件读取
    plans_from_config = settings.LOCAL_BILLING_PLANS
    if plans_from_config and isinstance(plans_from_config, list):
        return plans_from_config

    # 降级兜底：返回 community 基础套餐
    return [{
        "code": "community",
        "name": "Community",  # i18n
        "price_monthly": 0,
        "max_devices": 5,
        "max_channels": 20,
        "plugin_entitlements": "",
        "is_active": True,
    }]

@router.post("/plans")
async def create_plan(
    payload: BillingPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
    _: None = Depends(deps.require_server_edition),
):
    stmt = select(BillingPlan).where(BillingPlan.code == payload.code)
    result = await db.execute(stmt)
    if result.scalars().first():
        await safe_auth_audit(
            db,
            module="billing",
            action="create_plan",
            source="billing_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="duplicate_plan_code",
            extra_summary=f"code={payload.code}",
        )
        raise HTTPException(status_code=400, detail="Plan code already exists")
    item = BillingPlan(**payload.dict())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await safe_auth_audit(
        db,
        module="billing",
        action="create_plan",
        source="billing_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"plan_code={item.code}; plan_id={item.id}",
    )
    return item


@router.get("/plugins")
async def list_plugins_for_billing(
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(deps.require_server_edition),
):
    return _load_marketplace_catalog()

@router.post("/orders")
async def create_plugin_order(
    payload: PluginOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(deps.require_server_edition),
):
    catalog = _load_marketplace_catalog()
    plugin = next((item for item in catalog if str(item.get("id")) == payload.plugin_id), None)
    if not plugin:
        await safe_auth_audit(
            db,
            module="billing",
            action="create_plugin_order",
            source="billing_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="plugin_not_found",
            extra_summary=f"plugin_id={payload.plugin_id}",
        )
        raise HTTPException(status_code=404, detail="Plugin not found")
    months = max(1, min(payload.months, 36))
    unit_price = int(plugin.get("price_monthly") or 0)
    amount = unit_price * months
    order_no = f"PO{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    order = PluginOrder(
        order_no=order_no,
        tenant_id=current_user.tenant_id or "default",
        user_id=current_user.id,
        plugin_id=payload.plugin_id,
        plugin_name=str(plugin.get("name") or payload.plugin_id),
        amount=amount,
        currency="CNY",
        status="pending",
        pay_channel=payload.pay_channel or "embedded",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    await safe_auth_audit(
        db,
        module="billing",
        action="create_plugin_order",
        source="billing_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"order_no={order.order_no}; plugin_id={order.plugin_id}; "
            f"amount={order.amount}; pay_channel={order.pay_channel or ''}"
        ),
    )
    return {
        "order_no": order.order_no,
        "status": order.status,
        "amount": order.amount,
        "currency": order.currency,
        "pay_channel": order.pay_channel,
        # FIX: [2026-07-16 P0] 移除 callback_sign_example 字段——原返回值是
        # 对真实订单号、金额、"paid" 状态计算的完全有效 HMAC-SHA256 签名，
        # 攻击者可直接用于 POST /billing/payment/callback 伪造支付完成，
        # 免费获取付费插件 license。
        "return_url": settings.PAYMENT_SUCCESS_RETURN_URL,
    }

@router.get("/orders/me")
async def list_my_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(deps.require_server_edition),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(PluginOrder).where(PluginOrder.tenant_id == tenant_id).order_by(desc(PluginOrder.created_at))
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/orders/{order_no}")
async def get_order_status(
    order_no: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    _: None = Depends(deps.require_server_edition),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(PluginOrder).where(
        PluginOrder.order_no == order_no,
        PluginOrder.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    order = get_or_404(result, detail="Order not found")  # ORM查询结果空值判断
    return order

@router.post("/payment/callback")
async def payment_callback(
    payload: PaymentCallbackPayload,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(deps.require_server_edition),
):
    if not _verify_callback_signature(payload):
        await safe_auth_audit(
            db,
            module="billing",
            action="payment_callback",
            source="payment_callback",
            operator="external",
            result="failed",
            tenant_id="unknown",
            status_code=403,
            detail="invalid_signature",
            extra_summary=f"order_no={payload.order_no}",
        )
        raise HTTPException(status_code=403, detail="Callback signature invalid")
    stmt = select(PluginOrder).where(PluginOrder.order_no == payload.order_no)
    result = await db.execute(stmt)
    order = result.scalars().first()
    if not order:
        await safe_auth_audit(
            db,
            module="billing",
            action="payment_callback",
            source="payment_callback",
            operator="external",
            result="failed",
            tenant_id="unknown",
            status_code=404,
            detail="order_not_found",
            extra_summary=f"order_no={payload.order_no}",
        )
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == "paid":
        tid_dup = (order.tenant_id or "default").strip() or "default"
        await safe_auth_audit(
            db,
            module="billing",
            action="payment_callback",
            source="payment_callback",
            operator="external",
            result="success",
            tenant_id=tid_dup,
            status_code=200,
            detail="already_paid",
            extra_summary=f"order_no={order.order_no}",
        )
        return {"status": "ok", "order_no": order.order_no, "order_status": order.status}
    normalized = (payload.status or "").lower()
    if normalized not in {"paid", "failed"}:
        tid_cb = (order.tenant_id or "default").strip() or "default"
        await safe_auth_audit(
            db,
            module="billing",
            action="payment_callback",
            source="payment_callback",
            operator="external",
            result="failed",
            tenant_id=tid_cb,
            status_code=400,
            detail="unsupported_status",
            extra_summary=f"order_no={payload.order_no}; status={normalized}",
        )
        raise HTTPException(status_code=400, detail="Unsupported payment status")
    order.status = normalized
    order.callback_payload = json.dumps(payload.dict(), ensure_ascii=False, default=str)
    if normalized == "paid":
        if payload.paid_amount and payload.paid_amount != order.amount:
            tid_cb = (order.tenant_id or "default").strip() or "default"
            await safe_auth_audit(
                db,
                module="billing",
                action="payment_callback",
                source="payment_callback",
                operator="external",
                result="failed",
                tenant_id=tid_cb,
                status_code=400,
                detail="amount_mismatch",
                extra_summary=f"order_no={payload.order_no}; expected={order.amount}; got={payload.paid_amount}",
            )
            raise HTTPException(status_code=400, detail="Payment amount mismatch")
        order.paid_at = payload.paid_at or datetime.now(timezone.utc)
        _build_plugin_license(order)
    await db.commit()
    await db.refresh(order)
    tid_ok = (order.tenant_id or "default").strip() or "default"
    await safe_auth_audit(
        db,
        module="billing",
        action="payment_callback",
        source="payment_callback",
        operator="external",
        result="success",
        tenant_id=tid_ok,
        status_code=200,
        detail="ok",
        extra_summary=f"order_no={order.order_no}; order_status={order.status}; plugin_id={order.plugin_id}",
    )
    return {"status": "ok", "order_no": order.order_no, "order_status": order.status}

@router.get("/licenses/me")
async def list_my_licenses(
    request: Request,
    effective_only: bool = False,
    expiring_within_days: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    开源版：返回当前租户的授权列表。
    - 若配置了服务器版地址（PLUGIN_MARKETPLACE_BASE_URL / PLUGIN_SERVER_RECORD_URL），则优先代理服务器版 billing/licenses/me
    - 否则回退到本地数据库中已支付订单生成的授权列表
    """
    # 1) 尝试代理服务器版（用于真实购买/授权场景）
    base_url = (settings.PLUGIN_MARKETPLACE_BASE_URL or "").rstrip("/")
    record_url = (settings.PLUGIN_SERVER_RECORD_URL or "").strip()
    if record_url:
        from urllib.parse import urlparse
        parsed = urlparse(record_url)
        if parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
    if base_url:
        url = f"{base_url}/api/v1/billing/licenses/me"
        try:
            headers = {"Content-Type": "application/json"}
            auth_header = request.headers.get("Authorization")
            if auth_header:
                headers["Authorization"] = auth_header
            params: dict[str, object] = {"effective_only": bool(effective_only)}
            if expiring_within_days is not None:
                params["expiring_within_days"] = int(expiring_within_days)
            from app.core.http_client import get_http_client
            client = await get_http_client()
            resp = await client.get(url, headers=headers, params=params, timeout=8.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"非关键操作失败: {e}")

    # 2) 本地回退（用于离线/演示等场景）
    tenant_id = current_user.tenant_id or "default"
    stmt = select(PluginOrder).where(
        PluginOrder.tenant_id == tenant_id,
        PluginOrder.status == "paid"
    ).order_by(desc(PluginOrder.paid_at))
    result = await db.execute(stmt)
    orders = result.scalars().all()
    rows = [
        {
            "order_no": item.order_no,
            "plugin_id": item.plugin_id,
            "plugin_name": item.plugin_name,
            "paid_at": item.paid_at,
            "expires_at": item.expires_at,
            "license_data": json.loads(item.license_data) if item.license_data else None
        }
        for item in orders
    ]
    # 过期天数过滤（本地回退同样支持）
    if expiring_within_days is not None:
        days = max(1, min(int(expiring_within_days or 0), 3650))
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=days)
        filtered = []
        for r in rows:
            exp = r.get("expires_at")
            if not exp:
                continue
            try:
                if isinstance(exp, datetime):
                    t = exp
                else:
                    # 兼容 ISO 字符串
                    t = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            except Exception as e:
                logger.debug(f"跳过: {e}")
                continue
            # FIX: [2026-08-22 PN] 统一时区：原实现将 t 强制转为 naive 与 aware 的
            # now/threshold 比较 → TypeError → /licenses/me?expiring_within_days 500
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t > now and t <= threshold:
                filtered.append(r)
        rows = filtered

    if not effective_only:
        return rows
    latest: dict[str, dict] = {}
    for r in rows:
        pid = str(r.get("plugin_id") or "")
        if pid and pid not in latest:
            latest[pid] = r
    return list(latest.values())

@router.get("/subscription/me")
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    返回当前租户的订阅信息。
    开源版和服务器版均可用。
    """
    tenant_id = current_user.tenant_id or "default"
    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    result = await db.execute(stmt)
    sub = result.scalars().first()
    if sub:
        return sub
    default_sub = TenantSubscription(tenant_id=tenant_id, plan_code="community", status="active")
    db.add(default_sub)
    await db.commit()
    await db.refresh(default_sub)
    return default_sub

@router.put("/subscription")
async def update_subscription(
    payload: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
    _: None = Depends(deps.require_server_edition),
):
    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == payload.tenant_id)
    result = await db.execute(stmt)
    item = result.scalars().first()
    if not item:
        item = TenantSubscription(
            tenant_id=payload.tenant_id,
            plan_code=payload.plan_code,
            status=payload.status,
            trial_ends_at=payload.trial_ends_at,
            ends_at=payload.ends_at,
        )
        db.add(item)
    else:
        item.plan_code = payload.plan_code
        item.status = payload.status
        item.trial_ends_at = payload.trial_ends_at
        item.ends_at = payload.ends_at
    await db.commit()
    await db.refresh(item)
    await safe_auth_audit(
        db,
        module="billing",
        action="update_subscription",
        source="billing_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"target_tenant_id={payload.tenant_id}; plan_code={payload.plan_code}; status={payload.status}",
    )
    return item

@router.get("/branding/me")
async def get_my_branding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
    result = await db.execute(stmt)
    item = result.scalars().first()
    if item:
        return item
    item = TenantBranding(tenant_id=tenant_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

@router.put("/branding/me")
async def update_my_branding(
    payload: BrandingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
    result = await db.execute(stmt)
    item = result.scalars().first()
    if not item:
        item = TenantBranding(tenant_id=tenant_id)
        db.add(item)
    item.product_name = payload.product_name
    item.logo_url = payload.logo_url
    item.primary_color = payload.primary_color
    item.welcome_text = payload.welcome_text
    await db.commit()
    await db.refresh(item)
    await safe_auth_audit(
        db,
        module="billing",
        action="update_branding",
        source="billing_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"product_name={(payload.product_name or '').replace(';', '.')[:80]}",
    )
    return item


# ── 降级预览 ────────────────────────────────────────────────────────────────


class DowngradePreviewRequest(BaseModel):
    plan_id: str


@router.post("/subscription/downgrade-preview")
async def subscription_downgrade_preview(
    payload: DowngradePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    降级预览：计算当前套餐降级到目标套餐的差价退款金额。

    计算公式（prorated 按比例模式）：
    - refund_ratio = remaining_days / 30（粗略月估算）
    - refund = max(0, (old_price_monthly - new_price_monthly) * refund_ratio)
    """
    tid = current_user.tenant_id or "default"

    # 查询当前订阅
    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == tid)
    result = await db.execute(stmt)
    sub = result.scalars().first()
    if not sub or not sub.plan_code:
        raise HTTPException(status_code=400, detail="No active subscription, cannot preview downgrade")

    old_plan_code = sub.plan_code
    if old_plan_code == payload.plan_id:
        raise HTTPException(status_code=400, detail="Target plan is same as current, no downgrade needed")

    # 查询新旧套餐信息
    old_plan_stmt = select(BillingPlan).where(BillingPlan.code == old_plan_code)
    old_plan_result = await db.execute(old_plan_stmt)
    old_plan = old_plan_result.scalars().first()

    new_plan_stmt = select(BillingPlan).where(BillingPlan.code == payload.plan_id, BillingPlan.is_active)
    new_plan_result = await db.execute(new_plan_stmt)
    new_plan = get_or_404(new_plan_result, detail=f"BillingPlan '{payload.plan_id}' not found or inactive")  # ORM查询结果空值判断

    if not old_plan:
        raise HTTPException(status_code=400, detail=f"Current plan '{old_plan_code}' does not exist")  # i18n

    # 禁止升级
    if (old_plan.price_monthly or 0) < (new_plan.price_monthly or 0):
        raise HTTPException(status_code=400, detail="This is upgrade not downgrade, please use upgrade API")

    # prorated 退款计算
    now = datetime.now(timezone.utc)
    remaining_days = 0
    refund_amount = 0
    current_price = old_plan.price_monthly or 0
    new_price = new_plan.price_monthly or 0

    if sub.ends_at:
        if sub.ends_at.tzinfo is None:
            ends_at_aware = sub.ends_at.replace(tzinfo=timezone.utc)
        else:
            ends_at_aware = sub.ends_at
        remaining = ends_at_aware - now
        remaining_days = max(0, remaining.days)
        refund_ratio = remaining_days / 30
        refund_amount = int((current_price - new_price) * refund_ratio)
    else:
        # 永久订阅：按月均摊计算（最多退一个月）
        refund_ratio = 1.0
        refund_amount = max(0, current_price - new_price)

    # 降级受影响的插件
    affected_plugins: list[str] = []
    if old_plan.plugin_entitlements and new_plan.plugin_entitlements:
        try:
            raw_old = old_plan.plugin_entitlements
            raw_new = new_plan.plugin_entitlements
            old_ids = set(json.loads(raw_old)) if raw_old.startswith("[") else set(p.strip() for p in raw_old.split(",") if p.strip())
            new_ids = set(json.loads(raw_new)) if raw_new.startswith("[") else set(p.strip() for p in raw_new.split(",") if p.strip())
            affected_plugins = sorted(old_ids - new_ids)
        except Exception:
            logger.warning("Failed to compute affected_plugins for downgrade preview")

    await safe_auth_audit(
        db,
        module="billing",
        action="downgrade_preview",
        source="billing_api",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tid,
        status_code=200,
        detail="ok",
        extra_summary=f"old_plan={old_plan_code}; new_plan={payload.plan_id}; refund={refund_amount}; affected={affected_plugins}",
    )

    return {
        "current_plan_code": old_plan_code,
        "current_plan_name": old_plan.name,
        "current_price": current_price,
        "new_plan_code": payload.plan_id,
        "new_plan_name": new_plan.name,
        "new_price": new_price,
        "refund_amount": max(0, refund_amount),
        "effective_date": now.isoformat(),
        "affected_plugins": affected_plugins,
        "remaining_days": remaining_days if sub.ends_at else None,
    }


# ── 自助降级 ────────────────────────────────────────────────────────────────


class SelfDowngradeRequest(BaseModel):
    plan_id: str
    confirm_downgrade: bool = False


@router.post("/subscription/self-downgrade")
async def subscription_self_downgrade(
    payload: SelfDowngradeRequest,
    db: AsyncSession = Depends(get_db),
    # FIX: [2026-07-16 P1] 原仅 get_current_active_user，viewer 角色即可降级整个租户套餐
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """
    自助降级：用户确认后执行套餐降级。
    需先调用 downgrade-preview 预览差价并确认（confirm_downgrade=True）。
    """
    if not payload.confirm_downgrade:
        raise HTTPException(status_code=400, detail="Please confirm downgrade first (confirm_downgrade=true)")

    tid = current_user.tenant_id or "default"

    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == tid)
    result = await db.execute(stmt)
    sub = result.scalars().first()
    if not sub:
        raise HTTPException(status_code=400, detail="No active subscription, cannot downgrade")

    old_plan_code = sub.plan_code
    if old_plan_code == payload.plan_id:
        raise HTTPException(status_code=400, detail="Target plan is same as current")

    # 验证目标套餐
    new_plan_stmt = select(BillingPlan).where(BillingPlan.code == payload.plan_id, BillingPlan.is_active)
    new_plan_result = await db.execute(new_plan_stmt)
    new_plan = new_plan_result.scalars().first()
    if not new_plan:
        raise HTTPException(status_code=404, detail="Target plan not found or delisted")

    old_plan_stmt = select(BillingPlan).where(BillingPlan.code == old_plan_code)
    old_plan_result = await db.execute(old_plan_stmt)
    old_plan = old_plan_result.scalars().first()

    if old_plan and (old_plan.price_monthly or 0) < (new_plan.price_monthly or 0):
        raise HTTPException(status_code=400, detail="This is upgrade not downgrade")

    # 计算退款
    now = datetime.now(timezone.utc)
    refund_amount = 0
    remaining_days = 0
    if sub.ends_at and old_plan:
        if sub.ends_at.tzinfo is None:
            ends_at_aware = sub.ends_at.replace(tzinfo=timezone.utc)
        else:
            ends_at_aware = sub.ends_at
        remaining = ends_at_aware - now
        remaining_days = max(0, remaining.days)
        refund_ratio = remaining_days / 30
        refund_amount = int(((old_plan.price_monthly or 0) - (new_plan.price_monthly or 0)) * refund_ratio)

    # 受影响插件
    affected_plugins: list[str] = []
    if old_plan and old_plan.plugin_entitlements and new_plan.plugin_entitlements:
        try:
            raw_old = old_plan.plugin_entitlements
            raw_new = new_plan.plugin_entitlements
            old_ids = set(json.loads(raw_old)) if raw_old.startswith("[") else set(p.strip() for p in raw_old.split(",") if p.strip())
            new_ids = set(json.loads(raw_new)) if raw_new.startswith("[") else set(p.strip() for p in raw_new.split(",") if p.strip())
            affected_plugins = sorted(old_ids - new_ids)
        except Exception:
            logger.warning("Failed to compute affected_plugins for self-serve downgrade")

    # 执行降级
    sub.plan_code = payload.plan_id
    sub.status = "active"
    sub.updated_at = now

    log_entry = SubscriptionDowngradeLog(
        tenant_id=tid,
        old_plan_code=old_plan_code,
        new_plan_code=payload.plan_id,
        affected_plugins=json.dumps(affected_plugins),
        retains_single=json.dumps([]),
        operator_id=str(current_user.id),
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(sub)

    await safe_auth_audit(
        db,
        module="billing",
        action="self_downgrade",
        source="billing_api",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tid,
        status_code=200,
        detail="ok",
        extra_summary=f"old_plan={old_plan_code}; new_plan={payload.plan_id}; refund={refund_amount}; affected={affected_plugins}",
    )

    return {
        "ok": True,
        "old_plan_code": old_plan_code,
        "new_plan_code": payload.plan_id,
        "refund_amount": max(0, refund_amount),
        "effective_date": now.isoformat(),
        "affected_plugins": affected_plugins,
    }
