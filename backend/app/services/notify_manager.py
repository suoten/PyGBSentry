import asyncio
from loguru import logger
import datetime
import time
from app.core.plugin_manager import plugin_manager, HOOK_ON_ALARM, HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE, HOOK_ON_MOBILE_POSITION, HOOK_ON_DEVICE_ALARM
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
                wechat_payload = {
                    "msgtype": "text",
                    "text": {
                        "content": msg
                    }
                }
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
    msg = f"【设备报警】设备: {alarm_data.get('device_id')} / 通道: {alarm_data.get('channel_id')} 发生报警！\n" \
          f"类型: {alarm_data.get('alarm_type')}\n" \
          f"描述: {alarm_data.get('alarm_description')}\n" \
          f"时间: {alarm_data.get('alarm_time')}"

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

        time_str = alarm.time.strftime("%Y-%m-%dT%H:%M:%S") if alarm.time else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        sn = int(time.time()) % 100000

        for sub in subs:
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Alarm</CmdType>
<SN>{sn}</SN>
<DeviceID>{alarm.device_id}</DeviceID>
<AlarmPriority>{alarm.priority or '4'}</AlarmPriority>
<AlarmMethod>{alarm.method or '0'}</AlarmMethod>
<AlarmTime>{time_str}</AlarmTime>
<AlarmDescription>{alarm.description or ''}</AlarmDescription>
</Notify>
"""
            await platform_service.trigger_notify(sub.platform_id, "Alarm", xml_body)
    except Exception as e:
        logger.error(f"Error pushing Alarm NOTIFY: {e}")

async def _on_device_register(gb_id: str):
    if settings.WEBHOOK_DEVICE_STATUS_URL:
        msg = f"【设备上线】设备 {gb_id} 已注册上线"
        fire_and_forget(_send_webhook(settings.WEBHOOK_DEVICE_STATUS_URL, {"text": msg, "device_id": gb_id, "status": "online"}))  # P0-16: 保存引用防 GC + 异常日志

    try:
        subs = await platform_subscription_service.get_active_subscriptions("Catalog")
        if not subs:
            return

        for sub in subs:
            await platform_service.trigger_push_catalog(sub.platform_id)

    except Exception as e:
        logger.error(f"Error pushing Catalog NOTIFY on register: {e}")

async def _on_device_offline(gb_id: str):
    if settings.WEBHOOK_DEVICE_STATUS_URL:
        msg = f"【设备离线】设备 {gb_id} 心跳超时，已离线"
        fire_and_forget(_send_webhook(settings.WEBHOOK_DEVICE_STATUS_URL, {"text": msg, "device_id": gb_id, "status": "offline"}))  # P0-16: 保存引用防 GC + 异常日志

def init_notify_manager():
    plugin_manager.register_hook(HOOK_ON_ALARM, _on_alarm)
    plugin_manager.register_hook(HOOK_ON_DEVICE_ALARM, _on_device_alarm_hook)
    plugin_manager.register_hook(HOOK_ON_DEVICE_REGISTER, _on_device_register)
    plugin_manager.register_hook(HOOK_ON_DEVICE_OFFLINE, _on_device_offline)
    plugin_manager.register_hook(HOOK_ON_MOBILE_POSITION, _on_mobile_position)
    logger.info("NotifyManager initialized")
