import asyncio
import datetime
from copy import deepcopy
from loguru import logger

# P0-16 [2026-07-17]: 使用项目统一的 fire_and_forget 替代裸 create_task
from app.core.async_utils import fire_and_forget


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


# FIX R23-SEVERE: 周期性清理 catalog_runtime 内存缓存，避免 _RUNTIME_STATE 无限增长
_cleanup_loop_task: asyncio.Task | None = None
_CLEANUP_INTERVAL_SECONDS = 300  # 5 分钟


async def _cleanup_stale_runtime_loop():
    """后台循环：每 5 分钟调用 _cleanup_stale_runtime 清理过期条目。"""
    from loguru import logger
    try:
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
            try:
                removed = await _cleanup_stale_runtime()
                if removed > 0:
                    logger.info(f"[catalog_runtime] Cleaned up {removed} stale runtime entries")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[catalog_runtime] cleanup_stale_runtime error: {e}")
    except asyncio.CancelledError:
        logger.debug("task_cancelled")


def start_catalog_runtime_cleanup():
    """启动周期性清理 _RUNTIME_STATE 的后台任务。"""
    global _cleanup_loop_task
    if _cleanup_loop_task is None or _cleanup_loop_task.done():
        # P0-16 [2026-07-17]: 使用 fire_and_forget 替代裸 create_task，带异常回调和任务名
        _cleanup_loop_task = fire_and_forget(
            _cleanup_stale_runtime_loop(),
            name="catalog_runtime_cleanup_loop",
        )


def stop_catalog_runtime_cleanup():
    """停止周期性清理后台任务。"""
    global _cleanup_loop_task
    if _cleanup_loop_task is not None and not _cleanup_loop_task.done():
        _cleanup_loop_task.cancel()


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
    """R24-05: 处理 Catalog NOTIFY 增量变更（ADD/UPDATE/DEL/OFF/VLOST/ON）。

    修复前：将通道写入 Asset 表（错误，Asset 是设备表，且 Asset 无 parent_id 列）。
    修复后：将通道写入 Resource 表，与 handle_catalog_response 全量同步保持一致。
    """
    from loguru import logger
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from app.models.resource import Resource
    from sqlalchemy import select

    if not device_id or not items:
        return

    async with AsyncSessionLocal() as session:
        # Phase1: 查询父设备 Asset（获取 asset_id + tenant_id）
        parent_asset = (
            await session.execute(select(Asset).where(Asset.gb_id == device_id))
        ).scalars().first()
        if not parent_asset:
            logger.warning(f"[catalog_notify] Parent device {device_id} not found, skipping notify")
            return

        # W-12 Catalog Notify 批量查询替代 N+1
        all_item_ids = [
            ((item.findtext("DeviceID") or "").strip())
            for item in items
            if (item.findtext("DeviceID") or "").strip()
        ]
        if all_item_ids:
            existing_resources = {
                r.gb_id: r
                for r in (await session.execute(
                    select(Resource).where(Resource.gb_id.in_(all_item_ids))
                )).scalars().all()
            }
        else:
            existing_resources = {}

        for item in items:
            try:
                item_id = (item.findtext("DeviceID") or "").strip()
                if not item_id:
                    continue
                event_type = (item.findtext("Event") or "").strip().upper()
                name = (item.findtext("Name") or "").strip()
                status_val = (item.findtext("Status") or "").strip().upper()

                if event_type in ("ADD", "UPDATE", "ON"):
                    resource = existing_resources.get(item_id)
                    is_online = 1 if status_val in ("ON", "OK", "ONLINE") else 0
                    if resource:
                        # 更新已有 Resource
                        if name:
                            resource.name = name
                        resource.status = is_online
                        # 确保关联到正确的父设备
                        resource.asset_id = parent_asset.id
                    elif event_type == "ADD":
                        # 新增 Resource（通道）
                        new_resource = Resource(
                            tenant_id=parent_asset.tenant_id or "default",
                            asset_id=parent_asset.id,
                            gb_id=item_id,
                            name=name or item_id,
                            status=is_online,
                            parent_gb_id=device_id,
                            node_type="channel",
                        )
                        session.add(new_resource)
                        existing_resources[item_id] = new_resource
                elif event_type in ("DEL", "OFF", "VLOST"):
                    resource = existing_resources.get(item_id)
                    if resource:
                        if event_type == "DEL":
                            await session.delete(resource)
                            existing_resources.pop(item_id, None)
                        else:
                            # OFF / VLOST: 标记离线
                            resource.status = 0
            except Exception as e:
                logger.warning(f"[catalog_notify] Failed to process item: {e}")
                continue

        try:
            await session.commit()
        except Exception as e:
            logger.warning(f"[catalog_notify] Failed to commit catalog notify updates: {e}")
            return

        # 更新 runtime 状态
        try:
            await patch_device_catalog_runtime(device_id, {
                "catalog.notify_last_at": utc_now_iso(),
                "catalog.notify_item_count": len(items),
            })
        except Exception as e:
            logger.warning(f"[catalog_notify] Failed to update runtime state: {e}")

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
            logger.warning(f"[catalog_notify] Failed to notify catalog change to subscribers: {e}")

