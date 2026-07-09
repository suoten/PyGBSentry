"""Fire-and-forget SIP trace storage.

SIP signalling traces are persisted asynchronously so the SIP message loop
is never blocked by DB writes. :func:`schedule_store_sip_trace` is safe to
call from both sync and async contexts; it never raises.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger

from app.core.async_utils import fire_and_forget
from app.core.timezone import now_in_app_timezone


def schedule_store_sip_trace(payload: Any) -> None:
    """Persist a SIP trace record asynchronously.

    ``payload`` may be a dict or any JSON-serialisable object. Failures are
    logged at DEBUG level and swallowed — trace storage must never break
    signalling.
    """
    if payload is None:
        return
    try:
        record = _normalise_payload(payload)
    except Exception as e:
        logger.debug(f"sip_trace_store: failed to normalise payload: {e}")
        return
    try:
        fire_and_forget(_persist(record))
    except Exception as e:
        logger.debug(f"sip_trace_store: schedule failed: {e}")


def _normalise_payload(payload: Any) -> dict:
    if isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {"raw": str(payload)}
    data.setdefault("stored_at", now_in_app_timezone().isoformat())
    return data


async def _persist(record: dict) -> None:
    try:
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO sip_traces (payload, created_at) VALUES (:payload, :created_at)"
                ),
                {"payload": json.dumps(record, ensure_ascii=False, default=str),
                 "created_at": datetime.utcnow()},
            )
            await db.commit()
    except Exception as e:
        # Table may not exist in OSS; trace storage is best-effort.
        logger.debug(f"sip_trace_store: persist skipped ({e})")
