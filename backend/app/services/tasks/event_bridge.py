"""
事件流桥接服务：将系统事件（报警、设备上下线、流媒体状态）以标准化格式
发布到 Kafka 或 RabbitMQ，供下游数据平台消费。
配置项：
  targets: [{"type": "kafka"|"rabbitmq", "url": "...", "topic": "...", "exchange": "...", "routing_key": "...", "enabled": true}, ...]
"""
import datetime
import json
from loguru import logger
import os
import time
from typing import Any

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.plugin_manager import (
    HOOK_ON_ALARM, HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE,
    HOOK_ON_STREAM_START, HOOK_ON_STREAM_STOP,
)
from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting



PLUGIN_ID = "event_bridge"
LOG_DIR = "logs/event_bridge"

_DEFAULT_CONFIG = {
    "enabled": False,
    "targets": [],
    "include_alarms": True,
    "include_devices": True,
    "include_streams": True,
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl: float = 10.0

# Kafka / RabbitMQ 客户端（lazy init）
_kafka_producers: dict[str, Any] = {}
_rabbitmq_channels: dict[str, Any] = {}


def _append_log(msg: str, level: str = "info") -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"event_bridge_{today}.log")
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] [{level.upper()}] {msg}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"EventBridge 日志写入失败: {e}")


async def _get_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl:
        return _cfg_cache
    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()
    any_enabled = False
    cfg = dict(_DEFAULT_CONFIG)
    all_targets = []
    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if isinstance(parsed, dict) and bool(parsed.get("enabled")):
                any_enabled = True
            for k in _DEFAULT_CONFIG:
                v = parsed.get(k)
                if k == "targets" and isinstance(v, list):
                    all_targets.extend(v)
                elif v is not None:
                    cfg[k] = v
        except Exception:
            continue
    cfg["enabled"] = any_enabled or bool(cfg.get("enabled"))
    cfg["targets"] = all_targets if all_targets else cfg.get("targets", [])
    _cfg_cache = cfg
    _cfg_ts = now
    return cfg


def _build_event(event_type: str, data: dict) -> bytes:
    payload = {
        "event_type": event_type,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "PyGBSentry",
        "version": "1.0",
        **data,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


async def _publish(event_type: str, data: dict) -> None:
    cfg = await _get_cfg()
    if not cfg.get("enabled"):
        return
    if event_type == "alarm" and not cfg.get("include_alarms"):
        return
    if event_type in ("device_online", "device_offline") and not cfg.get("include_devices"):
        return
    if event_type in ("stream_start", "stream_stop") and not cfg.get("include_streams"):
        return

    msg_bytes = _build_event(event_type, data)
    targets: list[dict] = cfg.get("targets") or []

    for target in targets:
        if not bool(target.get("enabled", True)):
            continue
        t_type = str(target.get("type", "kafka")).lower()
        try:
            if t_type == "kafka":
                await _send_kafka(target, event_type, msg_bytes)
            elif t_type == "rabbitmq":
                await _send_rabbitmq(target, event_type, msg_bytes)
            else:
                logger.warning("[EventBridge] Unknown target type: %s", t_type)
        except Exception as e:
            logger.error("[EventBridge] Publish error (%s %s): %s", t_type, event_type, e)


async def _send_kafka(target: dict, event_type: str, msg_bytes: bytes) -> None:
    global _kafka_producers
    bootstrap_servers = str(target.get("url", "")).strip()
    if not bootstrap_servers:
        logger.warning("[EventBridge] Kafka 未配置 url，跳过")
        return
    topic = str(target.get("topic", "pygbsentry-events")).strip()

    producer = _kafka_producers.get(bootstrap_servers)
    if producer is None:
        try:
            from kafka import KafkaProducer
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: v,
                acks="all",
                retries=3,
                request_timeout_ms=5000,
            )
            _kafka_producers[bootstrap_servers] = producer
            _append_log(f"KafkaProducer connected: {bootstrap_servers}", "info")
        except ImportError:
            logger.warning("[EventBridge] kafka-python not installed")
            return
        except Exception as e:
            logger.error("[EventBridge] KafkaProducer init error: %s", e)
            return

    try:
        fut = producer.send(topic, value=msg_bytes)
        fut.get(timeout=3)
        _append_log(f"Kafka publish ok: topic={topic} event={event_type}", "debug")
    except Exception as e:
        logger.error("[EventBridge] Kafka send error: %s", e)


async def _send_rabbitmq(target: dict, event_type: str, msg_bytes: bytes) -> None:
    global _rabbitmq_channels
    url = str(target.get("url", "")).strip()
    if not url:
        logger.warning("[EventBridge] RabbitMQ 未配置 url，跳过")
        return
    exchange = str(target.get("exchange", "pygbsentry")).strip()
    routing_key = str(target.get("routing_key", event_type)).strip()

    channel = _rabbitmq_channels.get(url)
    if channel is None:
        try:
            import pika
            params = pika.URLParameters(url)
            conn = pika.BlockingConnection(params)
            channel = conn.channel()
            channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
            _rabbitmq_channels[url] = channel
            _append_log(f"RabbitMQ connected: {url}", "info")
        except ImportError:
            logger.warning("[EventBridge] pika not installed")
            return
        except Exception as e:
            logger.error("[EventBridge] RabbitMQ init error: %s", e)
            return

    try:
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=msg_bytes,
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )
        _append_log(f"RabbitMQ publish ok: exchange={exchange} key={routing_key}", "debug")
    except Exception as e:
        logger.error("[EventBridge] RabbitMQ send error: %s", e)
        # 重置连接
        _rabbitmq_channels.pop(url, None)


async def on_alarm(alarm) -> None:
    device_id = str(getattr(alarm, "device_id", "") or "")
    channel_id = str(getattr(alarm, "channel_id", "") or device_id)
    t = getattr(alarm, "time", None)
    await _publish("alarm", {
        "device_id": device_id,
        "channel_id": channel_id,
        "alarm_type": str(getattr(alarm, "alarm_type", "") or "Alarm"),
        "priority": str(getattr(alarm, "priority", "4") or "4"),
        "description": str(getattr(alarm, "description", "") or ""),
        "alarm_time": t.isoformat() if t and hasattr(t, "isoformat") else datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": str(getattr(alarm, "status", "") or "0"),
        "tenant_id": getattr(alarm, "tenant_id", "default") or "default",
    })


async def on_device_register(device_id) -> None:
    await _publish("device_online", {
        "device_id": str(device_id or "").strip(),
        "status": "online",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    })


async def on_device_offline(device_id) -> None:
    await _publish("device_offline", {
        "device_id": str(device_id or "").strip(),
        "status": "offline",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    })


async def on_stream_start(session) -> None:
    await _publish("stream_start", {
        "stream": str(getattr(session, "stream", "") or ""),
        "app": str(getattr(session, "app", "") or ""),
        "resource_id": str(getattr(session, "resource_id", "") or ""),
        "media_ip": str(getattr(session, "media_ip", "") or ""),
        "media_port": int(getattr(session, "media_port", 0) or 0),
        "ssrc": str(getattr(session, "ssrc", "") or ""),
        "start_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    })


async def on_stream_stop(session) -> None:
    await _publish("stream_stop", {
        "stream": str(getattr(session, "stream", "") or ""),
        "app": str(getattr(session, "app", "") or ""),
        "resource_id": str(getattr(session, "resource_id", "") or ""),
        "stop_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    })


async def start() -> None:
    logger.info("[EventBridge] Service started (Kafka/RabbitMQ event bridge)")


async def stop() -> None:
    global _kafka_producers, _rabbitmq_channels
    for p in _kafka_producers.values():
        try:
            p.close(timeout=2)
        except Exception as e:
            logger.warning(f"EventBridge Kafka 关闭失败: {e}")
    _kafka_producers = {}
    _rabbitmq_channels = {}


def register(pm) -> None:
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
    pm.register_hook(HOOK_ON_DEVICE_REGISTER, on_device_register)
    pm.register_hook(HOOK_ON_DEVICE_OFFLINE, on_device_offline)
    pm.register_hook(HOOK_ON_STREAM_START, on_stream_start)
    pm.register_hook(HOOK_ON_STREAM_STOP, on_stream_stop)
    logger.info("[EventBridge] Hooks registered: alarm, device_online, device_offline, stream_start, stream_stop")
