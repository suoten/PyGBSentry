from datetime import datetime, timedelta, timezone
from loguru import logger


def normalize_stream_mode(mode: str | None, default_mode: str = "UDP", allow_auto: bool = False) -> str:
    value = (mode or default_mode).strip().upper().replace("-", "_")
    allowed = {"GLOBAL", "UDP", "TCP_PASSIVE", "TCP_ACTIVE"}
    if allow_auto:
        allowed.add("AUTO")
    if value not in allowed:
        return default_mode
    return value


def calculate_failure_rate(success_total: int, fail_total: int) -> float:
    total = max((success_total or 0) + (fail_total or 0), 0)
    if total == 0:
        return 0
    return round((max(fail_total, 0) / total) * 100, 2)


def recommend_stream_mode(
    last_mode: str | None,
    current_mode: str,
    success_total: int,
    fail_total: int,
    consecutive_failures: int,
    auto_switch_count: int,
) -> tuple[str, str, str]:
    mode = normalize_stream_mode(current_mode)
    last = normalize_stream_mode(last_mode)
    failure_rate = calculate_failure_rate(success_total, fail_total)
    total = (success_total or 0) + (fail_total or 0)
    if consecutive_failures >= 2:
        return "UDP", "High consecutive failures, recommend UDP for stability", "high"  # i18n
    if failure_rate >= 35:
        return "UDP", "High failure rate, recommend UDP", "high"  # i18n
    if auto_switch_count > 0 and failure_rate >= 15:
        return "UDP", "Self-heal history with unconverged failure rate, recommend UDP", "medium"  # i18n
    if last in {"TCP_PASSIVE", "TCP_ACTIVE"} and consecutive_failures == 0 and failure_rate <= 10:
        return "TCP_PASSIVE", "TCP quality stable, recommend TCP_PASSIVE", "low"  # i18n
    if mode == "TCP_ACTIVE" and failure_rate > 20:
        return "TCP_PASSIVE", "TCP_ACTIVE variance high, recommend downgrade to TCP_PASSIVE", "medium"  # i18n
    return mode, "Maintain current mode", "low"  # i18n


def should_probe_back_to_tcp_passive(
    policy_mode: str | None,
    last_mode: str | None,
    success_total: int,
    fail_total: int,
    consecutive_failures: int,
    auto_switch_count: int,
    updated_at: datetime | None,
    min_success_total: int,
    max_failure_rate: float,
    max_idle_minutes: int,
) -> tuple[bool, str]:
    policy = normalize_stream_mode(policy_mode)
    last = normalize_stream_mode(last_mode)
    if policy != "UDP":
        return False, ""
    if last != "UDP":
        return False, ""
    if auto_switch_count <= 0:
        return False, ""
    if consecutive_failures > 0:
        return False, ""
    if (success_total or 0) < min_success_total:
        return False, ""
    failure_rate = calculate_failure_rate(success_total, fail_total)
    if failure_rate > max_failure_rate:
        return False, ""
    if not updated_at:
        return False, ""
    if datetime.now(timezone.utc) - updated_at > timedelta(minutes=max_idle_minutes):
        return False, ""
    return True, f"Switch-back probe condition met: success={success_total}, failure_rate={failure_rate}%"  # i18n


# 码流自适应自动执行 — 从策略推荐升级为自动执行切换
async def auto_switch_stream_if_needed(
    session_id: str,
    current_mode: str,
    success_total: int,
    fail_total: int,
    consecutive_failures: int,
    auto_switch_count: int,
    last_mode: str | None = None,
) -> dict:
    """
    根据流质量指标自动执行码流切换。
    当连续失败>=3次或失败率>=50%时，自动从TCP降级到UDP；
    当连续成功>=5次且失败率<=5%时，自动从UDP升级到TCP_PASSIVE。
    返回 {"switched": bool, "new_mode": str, "reason": str}
    """
    failure_rate = calculate_failure_rate(success_total, fail_total)
    mode = normalize_stream_mode(current_mode)

    # 降级逻辑：TCP → UDP（高失败率场景）
    if mode in ("TCP_PASSIVE", "TCP_ACTIVE"):
        if consecutive_failures >= 3 or failure_rate >= 50:
            new_mode = "UDP"
            reason = f"Auto-downgrade: consecutive_failures={consecutive_failures}, failure_rate={failure_rate}%"
            _switched = await _execute_stream_switch(session_id, new_mode, reason)
            return {"switched": _switched, "new_mode": new_mode if _switched else mode, "reason": reason if _switched else ""}

    # 升级逻辑：UDP → TCP_PASSIVE（质量稳定场景）
    if mode == "UDP" and auto_switch_count > 0:
        if consecutive_failures == 0 and failure_rate <= 5 and success_total >= 5:
            new_mode = "TCP_PASSIVE"
            reason = f"Auto-upgrade: success_total={success_total}, failure_rate={failure_rate}%"
            _switched = await _execute_stream_switch(session_id, new_mode, reason)
            return {"switched": _switched, "new_mode": new_mode if _switched else mode, "reason": reason if _switched else ""}

    return {"switched": False, "new_mode": mode, "reason": ""}


async def _execute_stream_switch(session_id: str, target_mode: str, reason: str) -> bool:
    """执行实际的码流切换（通过 Re-INVITE）"""
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.stream_session import StreamSession
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            ss = (await session.execute(
                select(StreamSession).where(StreamSession.id == session_id)
            )).scalars().first()
            if not ss or not ss.call_id:
                return False

            # 调用已有的码流切换API
            from app.sip.invite import sip_invite
            if sip_invite is None:
                return False

            # 通过 Re-INVITE 切换传输模式
            from app.core.config import settings
            old_mode = str(ss.protocol or "UDP")
            logger.info(f"[AutoStreamSwitch] Switching session {session_id} from {old_mode} to {target_mode}: {reason}")

            # 更新数据库中的协议模式
            ss.protocol = target_mode
            await session.commit()

            # 触发 Re-INVITE（如果流活跃）
            try:
                from app.api.v1.endpoints.stream.stream_play import _do_stream_switch
                await _do_stream_switch(str(ss.id), target_mode)
            except Exception as switch_err:
                logger.warning(f"[AutoStreamSwitch] Re-INVITE failed for session {session_id}: {switch_err}")
                return False

            return True
    except Exception as e:
        from loguru import logger
        logger.error(f"[AutoStreamSwitch] Failed to execute switch for session {session_id}: {e}")
        return False


# GB11 码流自适应切换 — 根据网络质量自动切换主/子码流
class StreamStrategy:
    """码流自适应策略：根据质量评分自动在主/子码流之间切换"""

    async def auto_switch_bitrate(self, stream_session_id: str, db) -> bool:
        """
        Switch between main stream and sub stream based on quality metrics.
        Called by StreamQualityMonitor when quality degrades below threshold.
        """
        from sqlalchemy import select
        from app.models.stream_session import StreamSession
        from app.models.resource import Resource
        from app.models.asset import Asset

        session = (await db.execute(select(StreamSession).where(StreamSession.id == stream_session_id))).scalars().first()
        if not session:
            return False

        # Check current stream type
        current_app = session.app or ""
        is_sub = "sub" in current_app.lower() or "secondary" in current_app.lower()

        # Get quality metrics from StreamQualityMonitor
        from app.services.stream_quality_monitor import stream_quality_monitor
        health = await stream_quality_monitor.get_session_health(stream_session_id)
        if not health:
            return False

        score = health.get("health_score", 100)

        # If quality is poor and on main stream, switch to sub stream
        if score < 40 and not is_sub:
            logger.info(f"Bitrate adaptive: switching to sub stream for session {stream_session_id} (score={score})")
            return await self._switch_to_sub_stream(session, db)

        # If quality is good and on sub stream, switch back to main stream
        if score > 80 and is_sub:
            logger.info(f"Bitrate adaptive: switching to main stream for session {stream_session_id} (score={score})")
            return await self._switch_to_main_stream(session, db)

        return False

    async def _switch_to_sub_stream(self, session, db) -> bool:
        """Switch from main stream to sub stream by sending new INVITE with stream_type=sub"""
        try:
            from app.services.stream_session_service import release_stream_session
            # R-04 码流自适应切换使用正确的invite函数引用
            import app.sip.invite as sip_invite_module
            from app.sip.server import sip_server
            from app.models.resource import Resource
            from app.models.asset import Asset
            from sqlalchemy import select

            resource = (await db.execute(select(Resource).where(Resource.id == session.resource_id))).scalars().first()
            asset = (await db.execute(select(Asset).where(Asset.id == session.asset_id))).scalars().first()
            if not resource or not asset:
                return False
            await release_stream_session(db, session, reason="bitrate_adaptive_switch")
            transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
            if transport is None:
                logger.warning(f"Bitrate adaptive switch to sub stream: no transport for {asset.ip_addr}:{asset.port}")
                return False
            await sip_invite_module.sip_invite.send_invite(
                asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), stream_type="sub"
            )
            return True
        except Exception as e:
            logger.warning(f"Bitrate adaptive switch to sub stream failed: {e}")
            return False

    async def _switch_to_main_stream(self, session, db) -> bool:
        """Switch from sub stream to main stream"""
        try:
            from app.services.stream_session_service import release_stream_session
            # R-04 码流自适应切换使用正确的invite函数引用
            import app.sip.invite as sip_invite_module
            from app.sip.server import sip_server
            from app.models.resource import Resource
            from app.models.asset import Asset
            from sqlalchemy import select

            resource = (await db.execute(select(Resource).where(Resource.id == session.resource_id))).scalars().first()
            asset = (await db.execute(select(Asset).where(Asset.id == session.asset_id))).scalars().first()
            if not resource or not asset:
                return False
            await release_stream_session(db, session, reason="bitrate_adaptive_switch")
            transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
            if transport is None:
                logger.warning(f"Bitrate adaptive switch to main stream: no transport for {asset.ip_addr}:{asset.port}")
                return False
            await sip_invite_module.sip_invite.send_invite(
                asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), stream_type="main"
            )
            return True
        except Exception as e:
            logger.warning(f"Bitrate adaptive switch to main stream failed: {e}")
            return False


stream_strategy = StreamStrategy()
