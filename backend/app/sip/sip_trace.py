"""SIP 信令追踪日志（共享层）。

为 ``app.sip.commander``、``app.sip.catalog``、``app.sip.handlers`` 等模块提供
统一的 SIP 信令追踪能力：

- :func:`sip_trace_should_log` —— 根据 ``SIP_DEBUG_TRACE_ENABLED`` 开关与
  ``SIP_TRACE_SAMPLE_RATE`` 采样率判断是否记录本次追踪。
- :func:`sip_trace_log` —— 记录一条 SIP 追踪事件，输出到 loguru 并异步持久化到
  ``sip_trace_store``（fire-and-forget，永不抛异常）。

此前该逻辑在 ``app/sip/ptz.py`` 与 ``app/services/platform_service.py`` 中各有一份
重复实现，本模块将其抽为共享层，保持行为一致。
"""
from __future__ import annotations

import random

from loguru import logger

from app.core.config import settings
from app.services.sip_trace_store import schedule_store_sip_trace
from app.sip.trace_events import should_warn_unknown_event_once


def sip_trace_should_log() -> bool:
    """判断当前是否应当记录一条 SIP 追踪日志。

    判定规则：
        1. ``settings.SIP_DEBUG_TRACE_ENABLED`` 必须为真，否则直接返回 False。
        2. 解析 ``settings.SIP_TRACE_SAMPLE_RATE``（0.0~1.0），按概率采样。
           解析失败时回退为 1.0（全量）。``>=1.0`` 视为全量，``<=0.0`` 视为关闭。

    返回 True 表示调用方应继续记录追踪。
    """
    if not settings.SIP_DEBUG_TRACE_ENABLED:
        return False
    try:
        rate = settings.SIP_TRACE_SAMPLE_RATE
    except Exception:
        logger.warning("SIP_TRACE_SAMPLE_RATE config parse failed")  # 国际化
        rate = 1.0
    # 钳制到 [0.0, 1.0]
    rate = max(0.0, min(1.0, rate))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def sip_trace_log(event: str, **fields) -> None:
    """记录一条 SIP 追踪事件。

    - 若事件名未在 ``trace_events.py`` 中注册，仅警告一次（便于发现遗漏的事件名）。
    - 将 ``event`` 与所有 ``fields`` 合并为 payload，输出 ``SIP_TRACE {payload}`` 到
      loguru ``info`` 级别。
    - 通过 ``schedule_store_sip_trace`` 异步落库（fire-and-forget，永不抛异常）。

    本函数永不抛异常，调用方无需 try/except。
    """
    if not sip_trace_should_log():
        return
    try:
        if should_warn_unknown_event_once(event):
            logger.warning(f"SIP_TRACE event not registered in trace_events.py: {event}")
        payload: dict = {"event": event}
        payload.update(fields)
        logger.info(f"SIP_TRACE {payload}")
        schedule_store_sip_trace(payload)
    except Exception as e:
        logger.debug(f"sip_trace_log failed (ignored): {e}")
