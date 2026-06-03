import random
from loguru import logger  # FIXED: 统一使用 loguru 替代 logging
from app.core.config import settings


_warned_unknown_events: set[str] = set()


def sip_trace_should_log() -> bool:
    if not bool(getattr(settings, "SIP_DEBUG_TRACE_ENABLED", False)):
        return False
    try:
        rate = float(getattr(settings, "SIP_TRACE_SAMPLE_RATE", 1.0) or 1.0)
    except Exception:
        rate = 1.0
    rate = max(0.0, min(1.0, rate))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def should_warn_unknown_event_once(event: str) -> bool:
    if event in _warned_unknown_events:
        return False
    _warned_unknown_events.add(event)
    return True


def sip_trace_log(event: str, **fields):
    if not sip_trace_should_log():
        return
    if should_warn_unknown_event_once(event):
        logger.warning(f"SIP_TRACE event not registered in trace_events.py: {event}")
    payload = {"event": event}
    payload.update(fields)
    logger.info(f"SIP_TRACE {payload}")
    try:
        from app.services.sip_trace_store import schedule_store_sip_trace
        schedule_store_sip_trace(payload)
    except Exception as e:
        logger.warning(f"Error: {e}")  # FIXED: 移除内部 loguru import，统一使用模块级 logger
