from loguru import logger
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alarm import Alarm
from app.models.alarm_link_rule import AlarmLinkRule
from app.models.asset import Asset
from app.services.health_service import HealthService  # 仅重用其 webhook/email 辅助方法



NotificationChannel = Literal["sms", "wecom", "feishu", "webhook"]


class NotificationService:
    """
    统一告警通知服务：
    - 从 Alarm + AlarmLinkRule 计算是否需要通知。
    - 通过 webhook/邮件等方式发送通用通知。
    - 预留与短信/企微/飞书插件的联动（当前通过插件 HOOK_ON_ALARM 实现，后续可加入更细粒度路由）。
    """

    def __init__(self) -> None:
        # 复用 HealthService 中的 webhook/email 发送逻辑，避免重复造轮子
        self._helper = HealthService()

    async def _get_alarm_with_asset(
        self, alarm_id: str, db: AsyncSession
    ) -> tuple[Alarm | None, Asset | None]:
        from app.models.asset import Asset  # 延迟导入避免循环

        stmt = select(Alarm, Asset).outerjoin(
            Asset, Asset.gb_id == Alarm.device_id
        ).where(Alarm.id == alarm_id)
        result = await db.execute(stmt)
        row = result.first()
        if not row:
            return None, None
        alarm, asset = row
        return alarm, asset

    async def _match_notify_rules(
        self, alarm: Alarm, db: AsyncSession
    ) -> list[AlarmLinkRule]:
        """复用现有联动规则，只挑出 link_notify=True 且匹配的规则。"""
        from datetime import datetime, timezone

        tenant_id = alarm.tenant_id or "default"
        stmt = select(AlarmLinkRule).where(
            AlarmLinkRule.tenant_id == tenant_id,
            AlarmLinkRule.enabled.is_(True),
            AlarmLinkRule.link_notify.is_(True),
        )
        result = await db.execute(stmt)
        rules = result.scalars().all()
        if not rules:
            return []

        now = alarm.time or datetime.now(timezone.utc)
        try:
            priority = int(alarm.priority or "4")
        except Exception:
            priority = 4

        matched: list[AlarmLinkRule] = []

        for rule in rules:
            # 优先级范围
            if rule.min_priority is not None and priority < rule.min_priority:
                continue
            if rule.max_priority is not None and priority > rule.max_priority:
                continue

            # 星期
            if rule.days:
                try:
                    day = now.weekday()  # 0=周一
                    allowed_days = {
                        int(x) for x in str(rule.days).split(",") if x.strip()
                    }
                    if allowed_days and day not in allowed_days:
                        continue
                except Exception as e:
                    logger.warning(f"Error: {e}")

            # 时间段（HH:MM）
            try:
                if rule.start_time and rule.end_time:
                    t_str = now.strftime("%H:%M")
                    if not (rule.start_time <= t_str <= rule.end_time):
                        continue
            except Exception as e:
                logger.warning(f"Error: {e}")

            matched.append(rule)

        return matched

    def _build_alarm_payload(self, alarm: Alarm, asset: Asset | None) -> dict:
        return {
            "event": "alarm_notify",
            "alarm_id": alarm.id,
            "tenant_id": alarm.tenant_id,
            "device_id": alarm.device_id,
            "channel_id": alarm.channel_id,
            "priority": alarm.priority,
            "method": alarm.method,
            "time": alarm.time.isoformat() if alarm.time else None,
            "description": alarm.description,
            "alarm_type": alarm.alarm_type,
            "asset_name": getattr(asset, "name", None),
            "asset_gb_id": getattr(asset, "gb_id", None),
        }

    async def notify_alarm(self, alarm_id: str) -> None:
        """
        按规则与全局配置，对单条报警执行通知：
        - 当前实现：如果存在至少一条 link_notify 规则，则：
          - 通过 REPORT_DAILY_WEBHOOK_URL 发送一条通用 webhook（event=alarm_notify）
          - 如配置了 REPORT_DAILY_EMAIL_TO，则发送一封邮件
        - 后续可在此处细化为不同级别路由到不同渠道。
        """
        async with AsyncSessionLocal() as session:
            alarm, asset = await self._get_alarm_with_asset(alarm_id, session)
            if not alarm:
                logger.debug("NotificationService: alarm not found, id=%s", alarm_id)
                return

            matched = await self._match_notify_rules(alarm, session)
            if not matched:
                return

            payload = self._build_alarm_payload(alarm, asset)

        # 发送 webhook / email（健康服务里已有通用封装）
        try:
            await self._helper._post_webhook(
                settings.REPORT_DAILY_WEBHOOK_URL,
                "alarm_notify",
                payload,
            )
        except Exception as e:
            logger.error("NotificationService webhook failed: %s", e)

        try:
            await self._helper._send_email(
                "alarm_notify",
                payload,
                settings.REPORT_DAILY_EMAIL_TO,
            )
        except Exception as e:
            logger.error("NotificationService email failed: %s", e)


notification_service = NotificationService()
