from loguru import logger
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.alarm import Alarm
from app.models.alarm_notification import AlarmNotification




class AlarmNotificationService:
    async def log_notification(
        self,
        *,
        channel: str,
        status: str,
        alarm_id: Optional[str] = None,
        device_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        description: Optional[str] = None,
        error_message: Optional[str] = None,
        tenant_id: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> None:
        """
        记录一条告警通知发送日志：
        - channel: sms / wecom / feishu / webhook 等
        - status: success / fail
        """
        try:
            async with AsyncSessionLocal() as session:
                await self._log_notification_with_session(
                    session=session,
                    channel=channel,
                    status=status,
                    alarm_id=alarm_id,
                    device_id=device_id,
                    channel_id=channel_id,
                    description=description,
                    error_message=error_message,
                    tenant_id=tenant_id,
                    sent_at=sent_at,
                )
        except Exception as e:
            logger.error(f"Failed to log alarm notification: {e}")

    async def _log_notification_with_session(
        self,
        *,
        session: AsyncSession,
        channel: str,
        status: str,
        alarm_id: Optional[str],
        device_id: Optional[str],
        channel_id: Optional[str],
        description: Optional[str],
        error_message: Optional[str],
        tenant_id: Optional[str],
        sent_at: Optional[datetime],
    ) -> None:
        tid = tenant_id or "default"
        dev_id = device_id
        ch_id = channel_id
        desc = description

        if alarm_id and (not dev_id or not desc):
            stmt = select(Alarm).where(Alarm.id == alarm_id)
            result = await session.execute(stmt)
            alarm = result.scalars().first()
            if alarm:
                if not dev_id:
                    dev_id = alarm.device_id
                if not ch_id:
                    ch_id = alarm.channel_id
                if not desc:
                    desc = alarm.description
                if not tenant_id:
                    tid = alarm.tenant_id or tid

        item = AlarmNotification(
            tenant_id=tid,
            alarm_id=alarm_id,
            device_id=dev_id,
            channel_id=ch_id,
            channel=channel,
            status=status,
            error_message=error_message[:1000] if error_message else None,
            description=desc[:255] if desc else None,
            sent_at=sent_at or datetime.now(timezone.utc),
        )
        session.add(item)
        await session.commit()


alarm_notification_service = AlarmNotificationService()

