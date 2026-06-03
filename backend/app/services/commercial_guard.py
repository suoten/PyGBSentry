from sqlalchemy import select, func  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.billing import BillingPlan, TenantSubscription
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.device_record_download_task import DeviceRecordDownloadTask
from app.core.config import settings
import datetime
import json

async def get_subscription(db: AsyncSession, tenant_id: str) -> TenantSubscription | None:
    stmt = select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    result = await db.execute(stmt)
    return result.scalars().first()

async def get_plan(db: AsyncSession, plan_code: str) -> BillingPlan | None:
    stmt = select(BillingPlan).where(BillingPlan.code == plan_code)
    result = await db.execute(stmt)
    return result.scalars().first()

async def get_effective_limits(db: AsyncSession, tenant_id: str) -> tuple[int, int]:
    if (settings.APP_EDITION or "oss").lower() != "server":
        return 0, 0
    sub = await get_subscription(db, tenant_id)
    plan_code = (sub.plan_code if sub else settings.COMMUNITY_PLAN_CODE) or settings.COMMUNITY_PLAN_CODE
    plan = await get_plan(db, plan_code)
    if not plan:
        return 0, 0
    return max(plan.max_devices or 0, 0), max(plan.max_channels or 0, 0)

async def check_device_quota(db: AsyncSession, tenant_id: str) -> tuple[bool, int, int]:
    limit, _ = await get_effective_limits(db, tenant_id)
    stmt = select(func.count(Asset.id)).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    current = int(result.scalar() or 0)
    if limit <= 0:
        return True, limit, current
    return current < limit, limit, current

async def check_channel_quota(db: AsyncSession, tenant_id: str) -> tuple[bool, int, int]:
    _, limit = await get_effective_limits(db, tenant_id)
    stmt = select(func.count(Resource.id)).where(Resource.tenant_id == tenant_id)
    result = await db.execute(stmt)
    current = int(result.scalar() or 0)
    if limit <= 0:
        return True, limit, current
    return current < limit, limit, current


def _safe_int(value: object, default_value: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return int(default_value)


def _default_record_limits(plan_code: str) -> dict[str, int]:
    # NOTE: 仅 server 版调用；开源版 get_record_limits 直接返回 enforced=False，不走此函数
    code = str(plan_code or "").strip().lower()
    if code in {"enterprise", "pro_plus", "ultimate"}:
        return {
            "max_query_hours": 168,
            "max_concurrent_downloads": 8,
            "max_download_speed": 8,
        }
    if code in {"pro", "professional", "business"}:
        return {
            "max_query_hours": 72,
            "max_concurrent_downloads": 3,
            "max_download_speed": 4,
        }
    return {
        "max_query_hours": 24,
        "max_concurrent_downloads": 1,
        "max_download_speed": 2,
    }


def _parse_record_limits_from_entitlements(entitlements: str | None, defaults: dict[str, int]) -> dict[str, int]:
    # NOTE: 仅 server 版调用；开源版 get_record_limits 直接返回 enforced=False，不走此函数
    if not entitlements:
        return dict(defaults)
    text = str(entitlements or "").strip()
    if not text:
        return dict(defaults)
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            rec = obj.get("record") if isinstance(obj, dict) else None
            if isinstance(rec, dict):
                return {
                    "max_query_hours": max(0, _safe_int(rec.get("max_query_hours"), defaults["max_query_hours"])),
                    "max_concurrent_downloads": max(0, _safe_int(rec.get("max_concurrent_downloads"), defaults["max_concurrent_downloads"])),
                    "max_download_speed": max(0, _safe_int(rec.get("max_download_speed"), defaults["max_download_speed"])),
                }
        except Exception:
            return dict(defaults)
    return dict(defaults)


async def get_record_limits(db: AsyncSession, tenant_id: str) -> dict[str, object]:
    # 开源版永久免费，不限制并发、网速或时长
    return {
        "edition": "oss",
        "plan_code": "oss_free",
        "enforced": False,
        "max_query_hours": 0,
        "max_concurrent_downloads": 0,
        "max_download_speed": 0,
    }


async def get_active_record_download_count(db: AsyncSession, tenant_id: str) -> int:
    stmt = select(func.count(DeviceRecordDownloadTask.id)).where(
        DeviceRecordDownloadTask.tenant_id == tenant_id,
        DeviceRecordDownloadTask.status.in_(["pending", "running"]),
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)

def is_subscription_near_expiry(sub: TenantSubscription | None, days: int) -> tuple[bool, str]:
    if (settings.APP_EDITION or "oss").lower() != "server":
        return False, ""
    if not sub:
        return False, ""
    now = datetime.datetime.now(datetime.timezone.utc)
    if sub.ends_at and sub.ends_at >= now:
        if (sub.ends_at - now).days <= days:
            return True, "subscription"
    return False, ""
