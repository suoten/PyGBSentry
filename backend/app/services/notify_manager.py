import asyncio
from loguru import logger
import datetime
import time
from app.core.plugin_manager import (
    plugin_manager,
    HOOK_ON_ALARM,
    HOOK_ON_DEVICE_REGISTER,
    HOOK_ON_DEVICE_OFFLINE,
    HOOK_ON_MOBILE_POSITION,
    HOOK_ON_DEVICE_ALARM,
)
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
from app.services.platform_subscription_service import platform_subscription_service
from app.services.platform_service import platform_service
from app.models.alarm import Alarm
from app.core.config import settings


async def _send_webhook(url: str, payload: dict, max_retries: int = 2):
    if not url:
        return
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            from app.core.http_client import get_http_client

            client = await get_http_client()
            if "dingtalk.com" in url or "weixin.qq.com" in url:
                msg = payload.get("text", str(payload))
                wechat_payload = {"msgtype": "text", "text": {"content": msg}}
                await client.post(url, json=wechat_payload, timeout=float(settings.NOTIFY_REQUEST_TIMEOUT))
            else:
                await client.post(url, json=payload, timeout=float(settings.NOTIFY_REQUEST_TIMEOUT))
            return
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))
    logger.warning(f"Webhook 投递失败（已重试{max_retries}次）: {url}: {last_err}")


async def _on_device_alarm_hook(alarm_data: dict):
    """处理我们刚刚在 handlers.py 里解析抛出的设备报警事件"""
    msg = (
        f"【设备报警】设备: {alarm_data.get('device_id')} / 通道: {alarm_data.get('channel_id')} 发生报警！\n"
        f"类型: {alarm_data.get('alarm_type')}\n"
        f"描述: {alarm_data.get('alarm_description')}\n"
        f"时间: {alarm_data.get('alarm_time')}"
    )

    logger.info(f"Webhook Trigger: {msg}")

    if settings.WEBHOOK_ALARM_URL:
        fire_and_forget(_send_webhook(settings.WEBHOOK_ALARM_URL, {"text": msg, "data": alarm_data}))  # P0-16: 保存引用防 GC + 异常日志


async def _on_mobile_position(device_id: str, longitude: float, latitude: float, speed, direction, altitude, pos_time):
    try:
        subs = await platform_subscription_service.get_active_subscriptions("MobilePosition")
        if not subs:
            return

        time_str = pos_time.strftime("%Y-%m-%dT%H:%M:%S") if pos_time else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        sn = int(time.time()) % 100000

        for sub in subs:
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>MobilePosition</CmdType>
<SN>{sn}</SN>
<DeviceID>{device_id}</DeviceID>
<Time>{time_str}</Time>
<Longitude>{longitude}</Longitude>
<Latitude>{latitude}</Latitude>
<Speed>{speed or 0}</Speed>
<Direction>{direction or 0}</Direction>
<Altitude>{altitude or 0}</Altitude>
</Notify>
"""
            await platform_service.trigger_notify(sub.platform_id, "MobilePosition", xml_body)
    except Exception as e:
        logger.error(f"Error pushing MobilePosition NOTIFY: {e}")


async def _on_alarm(alarm: Alarm):
    try:
        subs = await platform_subscription_service.get_active_subscriptions("Alarm")
        if not subs:
            return

        time_str = (
            alarm.time.strftime("%Y-%m-%dT%H:%M:%S") if alarm.time else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        )
        sn = int(time.time()) % 100000

        for sub in subs:
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Alarm</CmdType>
<SN>{sn}</SN>
<DeviceID>{alarm.device_id}</DeviceID>
<AlarmPriority>{alarm.priority or "4"}</AlarmPriority>
<AlarmMethod>{alarm.method or "0"}</AlarmMethod>
<AlarmTime>{time_str}</AlarmTime>
<AlarmDescription>{alarm.description or ""}</AlarmDescription>
</Notify>
"""
            await platform_service.trigger_notify(sub.platform_id, "Alarm", xml_body)
    except Exception as e:
        logger.error(f"Error pushing Alarm NOTIFY: {e}")


class _CatalogChangeDebouncer:
    """级联目录变更防抖聚合器。

    FIX [2026-11-20 P0] (wvp #2246 同款修复):设备闪断/反复重注册时,原实现对每个
    订阅上级全量重推目录,形成"批量离线 + 全量同步风暴"。现把变更按
    CATALOG_NOTIFY_DEBOUNCE_SECONDS 窗口聚合(同通道后到覆盖先到),窗口结束后对每个
    活跃 Catalog 订阅上级做一次增量 NOTIFY(Add/Update/Del/ON/OFF)。
    """

    def __init__(self, delay_seconds: float):
        self._delay = max(0.0, float(delay_seconds))
        self._pending: dict[tuple[str, str], dict] = {}  # (tenant_id, gb_id) -> change dict,后者覆盖前者
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

    async def report(self, changes: list[dict]) -> None:
        if not changes:
            return
        if self._delay <= 0:
            await self._flush(list(changes))
            return
        async with self._lock:
            for ch in changes:
                key = (str(ch.get("tenant_id") or "default"), str(ch.get("gb_id") or ""))
                if not key[1]:
                    continue
                self._pending[key] = ch
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        async with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        if pending:
            await self._flush(pending)

    async def _flush(self, changes: list[dict]) -> None:
        if not changes:
            return
        try:
            subs = await platform_subscription_service.get_active_subscriptions("Catalog")
            if not subs:
                return
            for sub in subs:
                try:
                    await platform_service.push_catalog_incremental(
                        tenant_id="default",
                        platform_id=sub.platform_id,
                        changed_resources=changes,
                    )
                except Exception as e:
                    logger.error(f"Error pushing incremental catalog to platform {sub.platform_id}: {e}")
        except Exception as e:
            logger.error(f"Error flushing catalog changes notify: {e}")


_catalog_debouncer = _CatalogChangeDebouncer(float(getattr(settings, "CATALOG_NOTIFY_DEBOUNCE_SECONDS", 15.0)))


async def report_catalog_changes(changes: list[dict]) -> None:
    """对外入口:目录同步(Add/Update/Del)与设备上下线(ON/OFF)变更统一走防抖增量通知。

    change dict 约定:{"gb_id": 必填, "tenant_id": 可选, "resource_id"/"name"/
    "status"/"parent_gb_id": 可选, "event_type": Add/Del/Update/ON/OFF}
    """
    await _catalog_debouncer.report(changes)


async def _on_device_register(gb_id: str):
    if settings.WEBHOOK_DEVICE_STATUS_URL:
        msg = f"【设备上线】设备 {gb_id} 已注册上线"
        fire_and_forget(
            _send_webhook(settings.WEBHOOK_DEVICE_STATUS_URL, {"text": msg, "device_id": gb_id, "status": "online"})
        )  # P0-16: 保存引用防 GC + 异常日志

    try:
        # FIX [2026-11-20 P0] (wvp #2246 同款修复):原先每次设备注册都对每个订阅上级
        # trigger_push_catalog 全量重推目录,设备闪断重连即触发全量同步风暴。
        # 改为防抖聚合的增量 ON 通知;全量推送仍保留在手动"推送目录"入口(trigger_push_catalog)。
        subs = await platform_subscription_service.get_active_subscriptions("Catalog")
        if not subs:
            return

        await report_catalog_changes([{"gb_id": str(gb_id or ""), "event_type": "ON"}])

    except Exception as e:
        logger.error(f"Error pushing Catalog NOTIFY on register: {e}")


async def _on_device_offline(gb_id: str):
    if settings.WEBHOOK_DEVICE_STATUS_URL:
        msg = f"【设备离线】设备 {gb_id} 心跳超时，已离线"
        fire_and_forget(
            _send_webhook(settings.WEBHOOK_DEVICE_STATUS_URL, {"text": msg, "device_id": gb_id, "status": "offline"})
        )  # P0-16: 保存引用防 GC + 异常日志

    # FIX [2026-11-20 P0] (wvp #1779/#2246 同款修复):原先设备离线完全不通知上级,
    # 上级侧通道状态滞留为 ON。改为防抖聚合的增量 OFF 通知。
    try:
        subs = await platform_subscription_service.get_active_subscriptions("Catalog")
        if not subs:
            return

        await report_catalog_changes([{"gb_id": str(gb_id or ""), "event_type": "OFF"}])

    except Exception as e:
        logger.error(f"Error pushing Catalog NOTIFY on offline: {e}")


def init_notify_manager():
    plugin_manager.register_hook(HOOK_ON_ALARM, _on_alarm)
    plugin_manager.register_hook(HOOK_ON_DEVICE_ALARM, _on_device_alarm_hook)
    plugin_manager.register_hook(HOOK_ON_DEVICE_REGISTER, _on_device_register)
    plugin_manager.register_hook(HOOK_ON_DEVICE_OFFLINE, _on_device_offline)
    plugin_manager.register_hook(HOOK_ON_MOBILE_POSITION, _on_mobile_position)
    logger.info("NotifyManager initialized")
