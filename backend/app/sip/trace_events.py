"""SIP trace event registry and one-shot warning deduplication.

Some GB28181 devices emit vendor-specific or future-version events that the
platform does not yet handle. Logging a warning on every occurrence would
flood the logs, so :func:`should_warn_unknown_event_once` returns ``True``
only the first time a given event key is seen within the process lifetime.

FIX: [2026-07-03] system_config.py 导入 SIP_TRACE_CONFIG_KEYS/SIP_TRACE_FIELDS/SIP_TRACE_EVENTS
     但本模块未定义这些常量，导致 system_config 模块加载失败、/system-config/* 路由全部 404。
     根因：refactoring 时遗漏了常量定义。修复：补充这三个常量。 [全栈工程师]
"""
from __future__ import annotations

import threading

# FIX: [2026-07-03] 补充 system_config.py 依赖的 SIP 追踪事件字典 [全栈工程师]

# SIP 追踪配置键（供前端展示与编辑）
SIP_TRACE_CONFIG_KEYS: list[dict] = [
    {"key": "SIP_DEBUG_TRACE_ENABLED", "label": "启用 SIP 追踪", "type": "bool", "default": "false"},
    {"key": "SIP_TRACE_SAMPLE_RATE", "label": "采样率 (0.0~1.0)", "type": "float", "default": "1.0"},
]

# SIP 追踪字段说明
SIP_TRACE_FIELDS: dict[str, str] = {
    "event": "事件名",
    "trace_id": "追踪 ID（优先使用 SIP Call-ID）",
    "gb_id": "设备国标 ID",
    "platform_id": "级联平台 ID",
    "proto": "传输协议 (UDP/TCP)",
    "addr": "信令地址",
    "batch_idx": "批次序号",
    "channel_id": "通道国标 ID",
    "call_id": "SIP Call-ID",
    "status_code": "SIP 响应状态码",
    "reason": "失败原因",
}

# SIP 追踪事件清单（按模块分组）
SIP_TRACE_EVENTS: dict[str, dict] = {
    # 接收侧 (app/sip/handlers.py)
    "register_received": {"module": "handlers", "desc": "收到 REGISTER 请求"},
    "register_401_challenge": {"module": "handlers", "desc": "返回 401 Digest challenge"},
    "register_auth_failed": {"module": "handlers", "desc": "Digest response 比对失败"},
    "register_ok_platform": {"module": "handlers", "desc": "识别为平台注册并返回 200"},
    "register_ok_device": {"module": "handlers", "desc": "识别为设备注册并返回 200"},
    "message_received": {"module": "handlers", "desc": "收到 MESSAGE 请求"},
    "message_keepalive_platform": {"module": "handlers", "desc": "收到平台 Keepalive 并更新在线时间"},
    "message_keepalive_unknown": {"module": "handlers", "desc": "收到未知来源 Keepalive"},
    "message_catalog_query_ack": {"module": "handlers", "desc": "收到 Catalog Query 并先回复 200"},
    "message_catalog_query_push": {"module": "handlers", "desc": "Catalog Query 命中平台后触发目录回推"},
    "message_catalog_response": {"module": "handlers", "desc": "收到 Catalog Response 并进入解析"},
    "message_record_info": {"module": "handlers", "desc": "收到 RecordInfo 并进入解析"},
    "message_alarm": {"module": "handlers", "desc": "收到 Alarm 并进入处理"},
    "message_mobile_position": {"module": "handlers", "desc": "收到 MobilePosition 并进入处理"},
    "message_fallback_200": {"module": "handlers", "desc": "其他 MESSAGE 分支统一回复 200"},
    "catalog_push_start": {"module": "handlers", "desc": "准备向平台注册方回推目录"},
    "catalog_push_message": {"module": "handlers", "desc": "回推目录的某个 MESSAGE 批次"},
    # 主动级联侧 (app/services/platform_service.py)
    "platform_response_received": {"module": "platform_service", "desc": "收到上级平台对 REGISTER 的响应"},
    "platform_register_sent": {"module": "platform_service", "desc": "向上级平台发送 REGISTER"},
    "platform_keepalive_sent": {"module": "platform_service", "desc": "向上级平台发送 Keepalive"},
    "platform_keepalive_ack": {"module": "platform_service", "desc": "收到上级平台对 Keepalive 的 200 响应"},
    "platform_keepalive_miss_re_register": {"module": "platform_service", "desc": "Keepalive 连续无 ACK 达阈值后触发重注册"},
    "platform_catalog_sent": {"module": "platform_service", "desc": "向上级平台发送 Catalog 批次"},
    # 设备命令侧 (app/sip/commander.py)
    "device_catalog_query_sent": {"module": "commander", "desc": "向设备发送 Catalog Query"},
    "device_mobile_position_subscribe_sent": {"module": "commander", "desc": "向设备发送 MobilePosition 订阅"},
}

_lock = threading.Lock()
_seen: set[str] = set()


def should_warn_unknown_event_once(event: str) -> bool:
    """Return ``True`` the first time ``event`` is observed, ``False`` after."""
    if not event:
        return False
    key = str(event)
    with _lock:
        if key in _seen:
            return False
        _seen.add(key)
        return True


def reset_seen() -> None:
    """Clear the seen set — intended for tests only."""
    with _lock:
        _seen.clear()
