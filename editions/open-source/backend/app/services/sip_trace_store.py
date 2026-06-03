import asyncio
import json
import random
from datetime import datetime, timezone

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.sip_trace_event import SipTraceEvent
from app.models.platform import ParentPlatform
from app.models.asset import Asset


def _should_store() -> bool:
    if not bool(getattr(settings, "SIP_TRACE_STORE_ENABLED", True)):
        return False
    try:
        rate = float(getattr(settings, "SIP_TRACE_STORE_SAMPLE_RATE", 1.0) or 1.0)
    except Exception:
        rate = 1.0
    rate = max(0.0, min(1.0, rate))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


async def _resolve_tenant_id(fields: dict) -> str:
    tenant_id = str(fields.get("tenant_id") or "").strip() or "default"
    if tenant_id != "default":
        return tenant_id
    platform_id = fields.get("platform_id")
    device_id = fields.get("device_id")
    try:
        async with AsyncSessionLocal() as session:
            if platform_id:
                p = (await session.execute(select(ParentPlatform).where(ParentPlatform.id == str(platform_id)))).scalars().first()
                if p and p.tenant_id:
                    return str(p.tenant_id)
            if device_id:
                a = (await session.execute(select(Asset).where(Asset.gb_id == str(device_id)))).scalars().first()
                if a and a.tenant_id:
                    return str(a.tenant_id)
    except Exception:
        return "default"
    return "default"


async def store_sip_trace_event(payload: dict) -> None:
    if not payload:
        return
    if not _should_store():
        return
    event = str(payload.get("event") or "").strip()
    if not event:
        return
    trace_id = str(payload.get("trace_id") or payload.get("call_id") or payload.get("X-Trace-ID") or "").strip() or None
    platform_id = payload.get("platform_id")
    device_id = payload.get("device_id")
    channel_id = payload.get("channel_id")

    tenant_id = await _resolve_tenant_id(payload)
    max_len = int(getattr(settings, "SIP_TRACE_STORE_MAX_PAYLOAD_LEN", 20000) or 20000)
    try:
        payload_str = json.dumps(payload, ensure_ascii=False)
    except Exception:
        payload_str = str(payload)
    payload_str = payload_str[:max(0, max_len)]

    row = SipTraceEvent(
        tenant_id=tenant_id,
        trace_id=trace_id,
        event=event,
        platform_id=(str(platform_id) if platform_id else None),
        device_id=(str(device_id) if device_id else None),
        channel_id=(str(channel_id) if channel_id else None),
        payload=payload_str,
        created_at=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as session:
        session.add(row)
        try:
            await session.commit()
        except Exception:
            await session.rollback()


def schedule_store_sip_trace(payload: dict) -> None:
    if not payload:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(store_sip_trace_event(payload))

