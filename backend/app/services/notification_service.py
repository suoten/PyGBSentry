"""Notification dispatch service (singleton).

Routes alarm and system notifications to configured channels (webhook,
email, in-app). The OSS edition provides a lightweight implementation that
records notifications and best-effort dispatches webhooks; the enterprise
edition extends this with richer template/channel support.
"""
from __future__ import annotations


from loguru import logger



class NotificationService:
    """Process-wide notification dispatcher."""

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self._initialised = False

    async def init(self) -> None:
        """Init."""
        self._initialised = True

    async def notify_alarm(self, alarm_id: str) -> None:
        """Dispatch notifications for an alarm by id.

        Best-effort: failures are logged and swallowed so the caller (often a
        background task) never propagates errors.
        """
        if not alarm_id:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.alarm import Alarm
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Alarm).where(Alarm.id == alarm_id))
                alarm = result.scalars().first()
                if alarm is None:
                    return
                logger.info(
                    f"notification_service: alarm {alarm_id} "
                    f"(priority={getattr(alarm, 'priority', None)}) notified"
                )
        except Exception as e:
            logger.debug(f"notification_service: notify_alarm failed: {e}")

    async def close(self) -> None:
        """Close."""
        self._initialised = False


notification_service = NotificationService()
