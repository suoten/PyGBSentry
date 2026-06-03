import asyncio
import datetime
from copy import deepcopy


_RUNTIME_STATE: dict[str, dict] = {}
_RUNTIME_LOCK = asyncio.Lock()
_MAX_AGE_SECONDS = 3600  # 1小时后清理


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def _cleanup_stale_runtime() -> int:
    """
    清理 _RUNTIME_STATE 中过期的条目。
    返回清理的条目数量。
    """
    if not _RUNTIME_STATE:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_keys = []
    async with _RUNTIME_LOCK:
        for key, val in _RUNTIME_STATE.items():
            last_at = val.get("catalog.last_response_at") or val.get("catalog.last_keepalive_at")
            if not last_at:
                continue
            try:
                last_dt = datetime.datetime.fromisoformat(last_at.replace("Z", "+00:00"))
                age = (now - last_dt.replace(tzinfo=datetime.timezone.utc)).total_seconds()
                if age > _MAX_AGE_SECONDS:
                    expired_keys.append(key)
            except Exception:
                continue
        for k in expired_keys:
            _RUNTIME_STATE.pop(k, None)
    return len(expired_keys)


async def patch_device_catalog_runtime(device_id: str, patch: dict) -> dict:
    key = (device_id or "").strip()
    if not key:
        return {}
    async with _RUNTIME_LOCK:
        current = _RUNTIME_STATE.get(key, {})
        current = dict(current)
        for k, v in (patch or {}).items():
            name = str(k or "").strip()
            if name:
                current[name] = v
        _RUNTIME_STATE[key] = current
        return deepcopy(current)


async def get_device_catalog_runtime(device_id: str) -> dict:
    key = (device_id or "").strip()
    if not key:
        return {}
    async with _RUNTIME_LOCK:
        return deepcopy(_RUNTIME_STATE.get(key, {}))


async def get_device_catalog_runtime_batch(device_ids: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not device_ids:
        return result
    keys = [(did or "").strip() for did in device_ids]
    async with _RUNTIME_LOCK:
        for key in keys:
            if key:
                result[key] = deepcopy(_RUNTIME_STATE.get(key, {}))
    return result


async def handle_catalog_notify_items(device_id: str, items: list) -> None:
    from loguru import logger
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from sqlalchemy import select

    if not device_id or not items:
        return

    async with AsyncSessionLocal() as session:
        for item in items:
            try:
                item_id = (item.findtext("DeviceID") or "").strip()
                if not item_id:
                    continue
                event_type = (item.findtext("Event") or "").strip().upper()
                name = (item.findtext("Name") or "").strip()
                status_val = (item.findtext("Status") or "").strip()

                if event_type in ("ADD", "UPDATE", "ON"):
                    asset = (await session.execute(
                        select(Asset).where(Asset.gb_id == item_id)
                    )).scalars().first()
                    if asset:
                        if name:
                            asset.name = name
                        if status_val.upper() in ("ON", "OK", "ONLINE"):
                            asset.status = 1
                        elif status_val.upper() in ("OFF", "OFFLINE"):
                            asset.status = 0
                    elif event_type == "ADD":
                        new_asset = Asset(
                            gb_id=item_id,
                            name=name or item_id,
                            parent_id=device_id,
                            status=1 if status_val.upper() in ("ON", "OK", "ONLINE") else 0,
                        )
                        session.add(new_asset)
                elif event_type in ("DEL", "OFF", "VLOST"):
                    asset = (await session.execute(
                        select(Asset).where(Asset.gb_id == item_id)
                    )).scalars().first()
                    if asset:
                        if event_type == "DEL":
                            await session.delete(asset)
                        else:
                            asset.status = 0
            except Exception as e:
                logger.debug(f"[catalog_notify] Failed to process item: {e}")
                continue

        try:
            await session.commit()
        except Exception as e:
            logger.warning(f"[catalog_notify] Failed to commit catalog notify updates: {e}")
            return

        try:
            from app.sip.subscribe_manager import subscribe_manager
            changed_channels = []
            for item in items:
                item_id = (item.findtext("DeviceID") or "").strip()
                event_type = (item.findtext("Event") or "").strip().upper()
                if item_id and event_type:
                    changed_channels.append({"device_id": item_id, "event": event_type})
            if changed_channels:
                await subscribe_manager.notify_catalog_change(device_id, changed_channels)
        except Exception as e:
            logger.debug(f"[catalog_notify] Failed to notify catalog change to subscribers: {e}")

