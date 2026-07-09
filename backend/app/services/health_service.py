import asyncio
from loguru import logger
import time
import datetime
import smtplib
import os
import shutil
from email.message import EmailMessage
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
from app.models.asset import Asset
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.asset_stream_health import AssetStreamHealth
from app.models.alarm import Alarm
from app.models.alarm_escalation import AlarmEscalation
from app.models.billing import TenantSubscription
from app.services.media_manager import media_manager
from app.services.stream_strategy import should_probe_back_to_tcp_passive, recommend_stream_mode, normalize_stream_mode
from app.services.commercial_guard import is_subscription_near_expiry
from app.services.notification_template_service import render_webhook_payload, render_email
# FIX: [2026-07-03] 引入 plugin_manager 用于磁盘空间告警事件发射 [可靠性工程师]
from app.core.plugin_manager import plugin_manager
from app.models.media_node import MediaNode
from app.models.platform import ParentPlatform
from sqlalchemy import select, update  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from app.models.stream_session import StreamSession
from app.models.resource import Resource
from app.core.media_nodes import get_all_media_from_nodes_async
from app.core.media_nodes_db import list_db_media_nodes
from app.core.media_nodes_db import get_all_media_from_nodes as get_all_media_from_db_nodes
from app.services.stream_session_service import release_stream_session
from app.core.timezone import now_in_app_timezone

# FIXED-P0: 删除 logger = logging.getLogger(__name__)，该行覆盖了第2行 from loguru import logger，
# 且 logging 未在模块级导入，导致 NameError: name 'logging' is not defined，应用无法启动

def _ensure_aware(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt

class HealthService:
    def __init__(self):
        self.running = False
        self.check_interval = 30
        self._task = None
        self._last_media_nodes_probe_at: datetime.datetime | None = None
        self._high_risk_since: datetime.datetime | None = None
        self._alert_cooldown_until: datetime.datetime | None = None
        self._last_daily_report_date: datetime.date | None = None
        self._sla_breach_streak = 0
        self._last_sla_notify_at: datetime.datetime | None = None
        self._last_stream_session_cleanup_at: datetime.datetime | None = None
        # 定时自动备份
        self._last_auto_backup_date: datetime.date | None = None
        # Readiness state: tracks degraded conditions for k8s/docker health probes
        self._degraded_reasons: list[str] = []
        # FIX: [2026-07-03] 系统资源监控状态 — 内存增长追踪和磁盘空间告警 [可靠性工程师]
        self._memory_baseline_mb: float = 0.0
        self._memory_last_mb: float = 0.0
        self._memory_check_history: list[tuple[float, float]] = []  # (timestamp, memory_mb)
        self._disk_alert_cooldown_until: datetime.datetime | None = None
        self._disk_recording_stopped: bool = False

    @property
    def is_ready(self) -> bool:
        """Whether the service is ready to serve traffic (no critical degraded conditions)."""
        return len(self._degraded_reasons) == 0

    @property
    def degraded_reasons(self) -> list[str]:
        """List of current degraded conditions."""
        return list(self._degraded_reasons)

    def mark_degraded(self, reason: str):
        """Mark a degraded condition that should fail readiness probes."""
        if reason not in self._degraded_reasons:
            self._degraded_reasons.append(reason)
            logger.error(f"Readiness DEGRADED: {reason}")

    def clear_degraded(self, reason: str):
        """Clear a previously set degraded condition."""
        if reason in self._degraded_reasons:
            self._degraded_reasons.remove(reason)
            logger.info(f"Readiness RESTORED: {reason}")

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Health Service started")

    async def stop(self):
        self.running = False
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError as e:
            logger.warning(f"asyncio.CancelledError: {e}")
        self._task = None

    async def _run_loop(self):
        while self.running:
            try:
                # FIX: [2026-07-03] DB 连接健康检查，断开时指数退避重连 [可靠性工程师]
                from app.db.session import _db_health_check_failed
                if _db_health_check_failed:
                    from app.db.session import ensure_db_connection_with_retry
                    reconnected = await ensure_db_connection_with_retry()
                    if reconnected:
                        self.clear_degraded("db_disconnected")
                    else:
                        self.mark_degraded("db_disconnected")
                await self._check_device_expiration()
                await self._check_parent_platform_expiration()
                await self._check_zlm_health()
                await self._probe_media_nodes()
                await self._reconcile_stream_policy()
                await self._check_health_alert()
                await self._check_daily_report_push()
                await self._auto_escalate_alarms()
                await self._check_sla_breach_notify()
                await self._check_subscription_expiry_reminder()
                await self._cleanup_zombie_stream_sessions()
                await self._cleanup_stale_media_port_leases()
                await self._cleanup_sip_tx_cache()
                await self._auto_backup_check()
                # FIX: [2026-07-03] 系统资源监控 — 内存增长检测和磁盘空间告警 [可靠性工程师]
                await self._check_memory_growth()
                await self._check_disk_space()
                # FIX: [2026-07-04] 清理已关闭的 per-node HTTP 客户端，防止媒体节点移除后客户端残留 [可靠性工程师]
                try:
                    from app.services.zlm_rtp_server_service import cleanup_stale_node_clients
                    await cleanup_stale_node_clients()
                except Exception as e:
                    logger.debug(f"Stale node clients cleanup error: {e}")
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _cleanup_sip_tx_cache(self):
        """定期清理 SIP 事务缓存和陈旧的 Response 缓存"""
        from app.sip.transactions import tx_manager
        from app.sip.server import sip_server

        # Clean SipServer response cache
        now = time.time()
        expired_keys = []
        for key, (msg, ts) in sip_server._response_cache.items():
            if now - ts > sip_server._response_cache_ttl:
                expired_keys.append(key)
        for key in expired_keys:
            sip_server._response_cache.pop(key, None)

        # tx_manager cleanup is handled by its own timers, but we can do a sweep here just in case
        # of memory leaks.
        async with tx_manager._lock:
            stale_tx = []
            for key, tx in tx_manager._tx.items():
                if now - tx.created_at > 60: # Force clean after 60s
                    stale_tx.append(key)
            for key in stale_tx:
                tx = tx_manager._tx.pop(key, None)
                if tx and tx.timers:
                    for h in tx.timers:
                        h.cancel()
                if tx and not tx.future.done():
                    tx.future.cancel()

    async def _cleanup_stale_media_port_leases(self):
        """自动在后台清理孤儿租约和无效的绑定租约，避免端口长期占用无法分配"""
        from app.core.media_nodes_db import cleanup_stale_leases, cleanup_invalid_bound_leases
        try:
            async with AsyncSessionLocal() as session:
                # FIX: [2026-07-03] 孤儿租约清理延迟从 300s 降至 120s，避免端口假性耗尽 [全栈工程师]
                cleaned_stale = await cleanup_stale_leases(session, max_age_seconds=120, limit=settings.HEALTH_CHECK_LIMIT)
                cleaned_invalid = await cleanup_invalid_bound_leases(session, limit=settings.HEALTH_CHECK_LIMIT)
                if cleaned_stale or cleaned_invalid:
                    logger.info(f"Auto-cleaned media port leases: {cleaned_stale} stale, {cleaned_invalid} invalid")
                    await session.commit()
        except Exception as e:
            logger.error(f"Error auto-cleaning media port leases: {e}")

    async def _cleanup_zombie_stream_sessions(self):
        if not bool(getattr(settings, "STREAM_SESSION_CLEANUP_ENABLED", True)):
            return
        # Reduce interval and zombie age to clean up stuck sessions faster
        interval = int(getattr(settings, "STREAM_SESSION_CLEANUP_INTERVAL_SECONDS", 15) or 15)
        zombie_age = int(getattr(settings, "STREAM_SESSION_ZOMBIE_AGE_SECONDS", 30) or 30)
        now = datetime.datetime.now(datetime.timezone.utc)
        if interval > 0 and self._last_stream_session_cleanup_at:
            elapsed = (now - self._last_stream_session_cleanup_at).total_seconds()
            if elapsed < interval:
                return
        self._last_stream_session_cleanup_at = now

        active: set[tuple[str, str]] = set()
        try:
            async with AsyncSessionLocal() as db:
                db_nodes = await list_db_media_nodes(db)
            if db_nodes:
                media_list = await get_all_media_from_db_nodes(db_nodes)
            else:
                media_list = await get_all_media_from_nodes_async()
            for item in media_list:
                if not isinstance(item, dict):
                    continue
                app = str(item.get("app") or "")
                stream = str(item.get("stream") or "")

                # Active streaming means it's producing bytes
                bytes_speed = int(item.get("bytesSpeed") or 0)
                if app and stream and bytes_speed > 0:
                    active.add((app, stream))
        except Exception:
            active = set()

        zombie_sessions = []
        async with AsyncSessionLocal() as session:
            cutoff = now - datetime.timedelta(seconds=zombie_age)
            # N-10 添加LIMIT防止全量加载
            rows = (await session.execute(
                select(StreamSession).where(StreamSession.start_time <= cutoff).limit(500)
            )).scalars().all()
            for ss in rows:
                app = str(getattr(ss, "app", "") or "")
                stream = str(getattr(ss, "stream", "") or "")
                if (app, stream) in active:
                    continue
                zombie_sessions.append(ss)

        cleaned = 0
        if zombie_sessions:
            async with AsyncSessionLocal() as session:
                for ss in zombie_sessions:
                    try:
                        merged = await session.merge(ss)
                        logger.warning(f"Active probe detected zombie session: app={getattr(ss, 'app', '')}, stream={getattr(ss, 'stream', '')}. Force cleaning.")
                        await release_stream_session(session, merged, reason="zombie_session_cleanup")
                        cleaned += 1
                    except Exception:
                        continue
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} zombie stream sessions (age>{zombie_age}s)")

    async def _probe_media_nodes(self):
        """
        主动探测 DB media_nodes 的 ZLM HTTP API，刷新 last_seen_at/is_online。
        目的：即使 Hook 链路异常，也能“自动监测节点状态”。
        """
        if not bool(getattr(settings, "MEDIA_NODES_ACTIVE_PROBE_ENABLED", True)):
            return
        interval = int(getattr(settings, "MEDIA_NODES_ACTIVE_PROBE_INTERVAL_SECONDS", 30) or 30)
        now = datetime.datetime.now(datetime.timezone.utc)
        if interval > 0 and self._last_media_nodes_probe_at:
            elapsed = (now - self._last_media_nodes_probe_at).total_seconds()
            if elapsed < interval:
                return
        self._last_media_nodes_probe_at = now

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MediaNode))
            nodes = result.scalars().all()
            if not nodes:
                return
            changed = 0
            for n in nodes:
                host = (getattr(n, "ip", None) or "").strip()
                if getattr(n, "is_embedded", False):
                    host = str(getattr(settings, "MEDIA_SERVER_HOST", "") or "").strip()  # I3 回退值不再硬编码127.0.0.1，避免配置缺失时静默使用错误地址
                port = int(getattr(n, "http_port", 0) or 0)
                # P0-02: n 是 ORM MediaNode，secret 列存储密文，须用 decrypted_secret 取明文
                secret = getattr(n, "decrypted_secret", None)
                if not host or port <= 0 or not secret:
                    continue
                ok = False
                probe_error = None
                try:
                    url = f"http://{host}:{port}/index/api/getServerConfig"
                    from app.core.http_client import get_http_client
                    client = await get_http_client()
                    # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
                    r = await client.post(url, data={"secret": secret}, timeout=2.0)
                    if r.status_code == 200:
                        data = r.json() or {}
                        ok = data.get("code") in {0, "0"}
                        if not ok:
                            probe_error = f"api_code={data.get('code')}, msg={data.get('msg')}"
                    else:
                        probe_error = f"http_status={r.status_code}"
                except Exception as e:
                    ok = False
                    probe_error = str(e)[:500] or "connect_failed"

                # 仅在状态变化/首次写入时更新，减少 DB 写放大
                prev_online = bool(getattr(n, "is_online", False))
                if ok:
                    n.is_online = True
                    n.last_seen_at = now
                    if getattr(n, "last_probe_error", None):
                        n.last_probe_error = None
                    changed += 1
                else:
                    # 记录最近探测失败原因，便于前端可视化排障
                    if (getattr(n, "last_probe_error", None) or "") != (probe_error or ""):
                        n.last_probe_error = probe_error
                        changed += 1
                    # 不强制写 last_seen_at；离线由 integrations.py 的 offline_seconds/last_seen_at 计算兜底
                    if prev_online:
                        n.is_online = False
                        changed += 1
            if changed > 0:
                await session.commit()

    async def _check_device_expiration(self):
        """
        Check for devices that haven't sent keepalive for more than 3x keepalive_interval.
        If device has no keepalive_interval set, fallback to default 60s -> 3 * 60 = 180s.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        changed = 0
        async with AsyncSessionLocal() as session:
            # 查出当前标记为在线的设备
            result = await session.execute(select(Asset).where(Asset.status == 1))
            devices = result.scalars().all()

            # N-11 并发探测设备，减少总等待时间
            expired_devices = []
            for dev in devices:
                last = dev.last_keepalive or dev.created_at
                last = _ensure_aware(last)
                interval = int(getattr(dev, "keepalive_interval", 60) or 60)
                timeout_sec = max(180, interval * 3)
                if (now - last).total_seconds() > timeout_sec:
                    expired_devices.append(dev)

            if expired_devices:
                _probe_sem = asyncio.Semaphore(5)

                async def _probe_with_sem(device):
                    async with _probe_sem:
                        return device, await self._probe_device_before_offline(device)

                probe_results = await asyncio.gather(
                    *[_probe_with_sem(dev) for dev in expired_devices],
                    return_exceptions=True,
                )

                for item in probe_results:
                    if isinstance(item, Exception):
                        logger.warning(f"Probe task exception: {item}")
                        continue
                    dev, probe_ok = item
                    if probe_ok:
                        dev.last_keepalive = now
                        logger.info(f"Device {dev.gb_id} keepalive expired but probe succeeded, keeping online")
                        continue
                    dev.status = 0
                    changed += 1
                    # 级联更新该设备下的所有通道（Resource）状态为离线
                    await session.execute(
                        update(Resource).where(Resource.asset_id == dev.id).values(status=0)
                    )

            if changed > 0:
                await session.commit()
                logger.info(f"Marked {changed} expired devices as offline (strict keepalive policy applied)")
                try:
                    from app.sip.subscribe_manager import subscribe_manager
                    for dev in devices:
                        if dev.status == 0 and dev.gb_id:
                            await subscribe_manager.remove_all_for_device(dev.gb_id)
                except Exception as e:
                    logger.warning(f"Failed to cleanup subscriptions for offline devices: {e}")
                try:
                    from app.core.plugin_manager import plugin_manager, HOOK_ON_DEVICE_OFFLINE
                    for dev in devices:
                        if dev.status == 0 and dev.gb_id:
                            fire_and_forget(plugin_manager.emit(HOOK_ON_DEVICE_OFFLINE, dev.gb_id))  # P0-16: 保存引用防 GC + 异常日志
                except Exception as e:
                    logger.warning(f"Failed to emit HOOK_ON_DEVICE_OFFLINE: {e}")

    async def _check_parent_platform_expiration(self):
        """
        按 keepalive_interval 检查平台在线状态：
        如果 last_keepalive 超过 3 倍心跳周期则标记离线。
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        changed = 0
        offline_ids: list[tuple[str, str]] = []
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(
                select(ParentPlatform).where(ParentPlatform.is_online)
            )).scalars().all()
            for p in rows:
                last = getattr(p, "last_keepalive", None)
                if not last:
                    continue
                last = _ensure_aware(last)
                interval = int(getattr(p, "keepalive_interval", 60) or 60)
                timeout_sec = max(60, interval * 3)
                if (now - last).total_seconds() > timeout_sec:
                    p.is_online = False
                    changed += 1
                    offline_ids.append((p.id, p.tenant_id or "default"))
            if changed > 0:
                await session.commit()
                logger.info(f"Marked {changed} expired parent platforms as offline")
        if offline_ids:
            import app.services.platform_service as platform_service_mod
            svc = getattr(platform_service_mod, "platform_service", None)
            if svc and getattr(svc, "running", False):
                for pid, _ in offline_ids:
                    fire_and_forget(svc.handle_platform_offline(pid, reason="health_expiration"))  # P0-16: 保存引用防 GC + 异常日志

    async def _probe_device_before_offline(self, device) -> bool:
        try:
            from app.sip.server import sip_server
            from app.sip.message import SipMessage
            from app.sip.send import send_sip_bytes
            from app.core.config import settings, sip_host_for_contact
            import secrets as _secrets

            addr = (str(device.ip_addr or ""), int(device.port or 5060))
            proto = str(getattr(device, "transport", "UDP") or "UDP")
            transport = sip_server.get_transport(addr[0], addr[1], proto)
            if not transport:
                logger.debug(f"Transport unavailable for probe to {device.gb_id}, skipping probe")
                return True

            domain = str(getattr(settings, "SIP_DOMAIN", sip_host_for_contact()))
            device_id = str(device.gb_id or "")
            sn = int(time.time() * 1000) % 100000 # __import__ 反模式改为标准 import

            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>DeviceStatus</CmdType>
<SN>{sn}</SN>
<DeviceID>{device_id}</DeviceID>
</Query>
"""
            req = SipMessage()
            req.method = "MESSAGE"
            req.uri = f"sip:{device_id}@{domain}"
            req.version = "SIP/2.0"
            branch = f"z9hG4bK{_secrets.token_hex(6)}"
            req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
            req.headers["From"] = f"<sip:{settings.SIP_ID}@{domain}>;tag={_secrets.token_hex(4)}"
            req.headers["To"] = f"<sip:{device_id}@{domain}>"
            req.headers["Call-ID"] = f"probe_{sn}@{sip_host_for_contact()}"
            req.headers["CSeq"] = "1 MESSAGE"
            req.headers["Content-Type"] = "Application/MANSCDP+xml"
            req.headers["Max-Forwards"] = "70"
            req.headers["User-Agent"] = settings.PROJECT_NAME
            req.body = xml_body

            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            # N-11 并发探测设备，减少总等待时间
            await asyncio.sleep(1.5)

            async with AsyncSessionLocal() as session:
                fresh = (await session.execute(
                    select(Asset).where(Asset.id == device.id)
                )).scalars().first()
                if fresh and fresh.status == 1:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Probe device {getattr(device, 'gb_id', '?')} before offline failed: {e}")
            return False

    async def _check_zlm_health(self):
        # 生产体验：若用户选择外置/禁用内置 ZLM，则不应反复尝试拉起内置进程
        try:
            if not bool(getattr(settings, "EMBEDDED_ZLM_ENABLED", True)):
                self.clear_degraded("zlm_down")
                return
            if bool(getattr(settings, "ZLM_PREFER_EXTERNAL_NODES", True)):
                try:
                    hit = await media_manager._detect_external_media_nodes_configured()
                    if bool(hit.get("has_external")):
                        self.clear_degraded("zlm_down")
                        return
                except Exception as e:
                    logger.warning(f"Error detecting external media nodes: {e}")
        except Exception as e:
            logger.warning(f"Error in ZLM health check pre-conditions: {e}")
        if not await media_manager.is_running():
            if media_manager.embedded_deploy_known_failed():
                self.mark_degraded("zlm_down")
                return
            # FIXED: 避免每 30 秒重复尝试重启和刷屏警告
            # 5 分钟内只尝试重启一次，避免资源浪费
            now = datetime.datetime.now(datetime.timezone.utc)
            _restart_cooldown = getattr(self, "_zlm_last_restart_at", None)
            if _restart_cooldown and (now - _restart_cooldown).total_seconds() < 300:
                self.mark_degraded("zlm_down")
                return
            self._zlm_last_restart_at = now
            logger.warning("ZLMediaKit is not running! Attempting restart...")
            self.mark_degraded("zlm_down")
            try:
                await media_manager.start()
            except Exception as e:
                logger.error(f"ZLMediaKit restart failed: {e}")
            # Re-check after restart attempt
            if await media_manager.is_running():
                self.clear_degraded("zlm_down")
        else:
            self.clear_degraded("zlm_down")

    async def _reconcile_stream_policy(self):
        if not settings.STREAM_SELF_HEAL_PROBE_ENABLED:
            return
        async with AsyncSessionLocal() as session:
            stmt = select(AssetStreamPolicy, AssetStreamHealth).join(
                AssetStreamHealth, AssetStreamPolicy.asset_id == AssetStreamHealth.asset_id
            ).where(AssetStreamPolicy.stream_mode == "UDP")
            result = await session.execute(stmt)
            rows = result.all()
            switched = 0
            for policy, health in rows:
                should_probe, reason = should_probe_back_to_tcp_passive(
                    policy_mode=policy.stream_mode,
                    last_mode=health.last_mode,
                    success_total=health.success_total,
                    fail_total=health.fail_total,
                    consecutive_failures=health.consecutive_failures,
                    auto_switch_count=health.auto_switch_count,
                    updated_at=health.updated_at,
                    min_success_total=settings.STREAM_SELF_HEAL_PROBE_MIN_SUCCESS_TOTAL,
                    max_failure_rate=settings.STREAM_SELF_HEAL_PROBE_MAX_FAILURE_RATE,
                    max_idle_minutes=settings.STREAM_SELF_HEAL_PROBE_MAX_IDLE_MINUTES,
                )
                if not should_probe:
                    continue
                policy.stream_mode = "TCP_PASSIVE"
                switched += 1
                logger.info(f"Auto probe switched policy to TCP_PASSIVE for asset={policy.asset_id}: {reason}")
            if switched > 0:
                await session.commit()

    async def _check_health_alert(self):
        if not settings.HEALTH_ALERT_WEBHOOK_URL:
            return
        async with AsyncSessionLocal() as session:
            stmt = select(AssetStreamHealth, AssetStreamPolicy).outerjoin(
                AssetStreamPolicy, AssetStreamHealth.asset_id == AssetStreamPolicy.asset_id
            )
            result = await session.execute(stmt)
            rows = result.all()
            high_risk = 0
            max_failure_rate = 0.0
            for health, policy in rows:
                policy_mode = normalize_stream_mode(policy.stream_mode if policy else "GLOBAL", default_mode="GLOBAL", allow_auto=True)
                current_mode = normalize_stream_mode(policy_mode if policy_mode != "GLOBAL" else "UDP")
                _, _, risk_level = recommend_stream_mode(
                    last_mode=health.last_mode,
                    current_mode=current_mode,
                    success_total=health.success_total,
                    fail_total=health.fail_total,
                    consecutive_failures=health.consecutive_failures,
                    auto_switch_count=health.auto_switch_count,
                )
                if risk_level == "high":
                    high_risk += 1
                total = max(health.success_total + health.fail_total, 0)
                failure_rate = round((health.fail_total / total) * 100, 2) if total > 0 else 0
                if failure_rate > max_failure_rate:
                    max_failure_rate = failure_rate
        now = datetime.datetime.now(datetime.timezone.utc)
        if high_risk < settings.HEALTH_ALERT_MIN_HIGH_RISK:
            self._high_risk_since = None
            return
        if self._high_risk_since is None:
            self._high_risk_since = now
            return
        if now - self._high_risk_since < datetime.timedelta(minutes=settings.HEALTH_ALERT_HOLD_MINUTES):
            return
        if self._alert_cooldown_until and now < self._alert_cooldown_until:
            return
        self._alert_cooldown_until = now + datetime.timedelta(minutes=settings.HEALTH_ALERT_COOLDOWN_MINUTES)
        payload = {
            "event": "health_high_risk_persistent",
            "high_risk_count": high_risk,
            "max_failure_rate": max_failure_rate,
            "threshold": settings.HEALTH_ALERT_MIN_HIGH_RISK,
            "hold_minutes": settings.HEALTH_ALERT_HOLD_MINUTES,
            "timestamp": now.isoformat(),
        }
        try:
            from app.core.http_client import get_http_client
            client = await get_http_client()
            await client.post(settings.HEALTH_ALERT_WEBHOOK_URL, json=payload, timeout=3.0)
            logger.warning(f"Health high-risk alert pushed to webhook: high_risk={high_risk}")
        except Exception as e:
            logger.error(f"Failed to push health alert webhook: {e}")

    async def _auto_escalate_alarms(self):
        if not settings.ALARM_ESCALATION_ENABLED:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        async with AsyncSessionLocal() as session:
            stmt = select(Alarm, AlarmEscalation).join(
                AlarmEscalation, Alarm.id == AlarmEscalation.alarm_id
            ).where(
                Alarm.status == 0,
                AlarmEscalation.state != "acknowledged",
            )
            result = await session.execute(stmt)
            rows = result.all()
            if not rows:
                return
            changed = 0
            first_minutes = max(settings.ALARM_ESCALATION_FIRST_MINUTES, 1)
            max_level = max(settings.ALARM_ESCALATION_MAX_LEVEL, 1)
            tier_minutes = self._parse_priority_minutes(first_minutes)
            for alarm, escalation in rows:
                if not alarm.time:
                    continue
                alarm_time = _ensure_aware(alarm.time)
                base_minutes = tier_minutes.get(str(alarm.priority or "4"), first_minutes)
                elapsed_minutes = max((now - alarm_time).total_seconds(), 0) / 60
                target_level = min(int(elapsed_minutes // max(base_minutes, 1)), max_level)
                if target_level <= escalation.escalation_level:
                    continue
                escalation.escalation_level = target_level
                escalation.escalation_count = max(escalation.escalation_count, target_level)
                escalation.last_escalated_at = now
                escalation.state = "open"
                changed += 1
            if changed > 0:
                await session.commit()
                logger.warning(f"Auto escalated alarms: {changed}")

    def _parse_priority_minutes(self, default_minutes: int) -> dict[str, int]:
        result: dict[str, int] = {}
        raw = settings.ALARM_ESCALATION_PRIORITY_MINUTES or ""
        for item in raw.split(","):
            pair = item.strip()
            if not pair or ":" not in pair:
                continue
            key, value = pair.split(":", 1)
            key = key.strip()
            try:
                result[key] = max(int(value.strip()), 1)
            except Exception:
                continue
        if not result:
            result = {"1": max(default_minutes // 2, 1), "2": default_minutes, "3": default_minutes * 2, "4": default_minutes * 3}
        return result

    async def _post_webhook(self, url: str | None, event: str, payload: dict, platform: str = "generic", max_retries: int = 2):
        if not url:
            return
        import asyncio
        send_payload = render_webhook_payload(event, platform, payload)
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                from app.core.http_client import get_http_client
                from loguru import logger
                client = await get_http_client()
                await client.post(url, json=send_payload, timeout=5.0)
                return
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
        logger.error(f"Webhook 投递失败（已重试{max_retries}次）: {event}: {last_err}")

    async def _send_email(self, event: str, payload: dict, to_addr: str | None):
        if not to_addr or not settings.SMTP_HOST:
            return
        subject, body = render_email(event, payload)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME or "noreply@pygbsentry.local"
        msg["To"] = to_addr
        msg.set_content(body)
        port = int(settings.SMTP_PORT or 25)
        use_tls = bool(settings.SMTP_USE_TLS)
        def _send():
            if use_tls:
                with smtplib.SMTP(settings.SMTP_HOST, port, timeout=8) as smtp:
                    smtp.starttls()
                    if settings.SMTP_USERNAME:
                        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, port, timeout=8) as smtp:
                    if settings.SMTP_USERNAME:
                        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
                    smtp.send_message(msg)
        await asyncio.to_thread(_send)

    async def _build_daily_summary(self) -> dict:
        async with AsyncSessionLocal() as session:
            stmt = select(Asset, AssetStreamHealth, AssetStreamPolicy).outerjoin(
                AssetStreamHealth, Asset.id == AssetStreamHealth.asset_id
            ).outerjoin(
                AssetStreamPolicy, Asset.id == AssetStreamPolicy.asset_id
            )
            result = await session.execute(stmt)
            rows = result.all()
        total_devices = len(rows)
        high_risk = 0
        medium_risk = 0
        low_risk = 0
        risky_rows: list[tuple[str, str, float, int]] = []
        for asset, health, policy in rows:
            if not health:
                risk_level = "low"
                failure_rate = 0
                consecutive_failures = 0
            else:
                policy_mode = normalize_stream_mode(policy.stream_mode if policy else "GLOBAL", default_mode="GLOBAL", allow_auto=True)
                current_mode = normalize_stream_mode(policy_mode if policy_mode != "GLOBAL" else "UDP")
                _, _, risk_level = recommend_stream_mode(
                    last_mode=health.last_mode,
                    current_mode=current_mode,
                    success_total=health.success_total,
                    fail_total=health.fail_total,
                    consecutive_failures=health.consecutive_failures,
                    auto_switch_count=health.auto_switch_count,
                )
                total = max(health.success_total + health.fail_total, 0)
                failure_rate = round((health.fail_total / total) * 100, 2) if total > 0 else 0
                consecutive_failures = health.consecutive_failures
            if risk_level == "high":
                high_risk += 1
            elif risk_level == "medium":
                medium_risk += 1
            else:
                low_risk += 1
            risky_rows.append((asset.gb_id, risk_level, failure_rate, consecutive_failures))
        risky_rows.sort(key=lambda item: ((item[1] == "high"), item[2], item[3]), reverse=True)
        top_risky = [
            {"device_id": item[0], "risk_level": item[1], "failure_rate": item[2], "consecutive_failures": item[3]}
            for item in risky_rows[:10]
        ]
        summary = {
            "event": "daily_health_report",
            "timestamp": now_in_app_timezone().isoformat(),
            "total_devices": total_devices,
            "high_risk": high_risk,
            "medium_risk": medium_risk,
            "low_risk": low_risk,
            "top_risky": top_risky,
        }
        return summary

    async def _check_daily_report_push(self):
        if not settings.REPORT_DAILY_SEND_ENABLED:
            return
        now = now_in_app_timezone()
        parts = (settings.REPORT_DAILY_SEND_TIME_UTC or "01:00").split(":")
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            hour, minute = 1, 0
        if now.hour != hour or now.minute != minute:
            return
        if self._last_daily_report_date == now.date():
            return
        self._last_daily_report_date = now.date()
        summary = await self._build_daily_summary()
        try:
            await self._post_webhook(settings.REPORT_DAILY_WEBHOOK_URL, "daily_health_report", summary)
            await self._send_email("daily_health_report", summary, settings.REPORT_DAILY_EMAIL_TO)
            logger.warning("Daily health report pushed")
        except Exception as e:
            logger.error(f"Daily health report push failed: {e}")

    async def _check_sla_breach_notify(self):
        if not settings.SLA_BREACH_NOTIFY_ENABLED:
            return
        async with AsyncSessionLocal() as session:
            stmt = select(Alarm, AlarmEscalation).join(
                AlarmEscalation, Alarm.id == AlarmEscalation.alarm_id
            ).where(
                Alarm.status == 0,
                AlarmEscalation.state != "acknowledged",
                AlarmEscalation.escalation_level >= max(settings.ALARM_ESCALATION_MAX_LEVEL - 1, 1),
            )
            result = await session.execute(stmt)
            rows = result.all()
        if not rows:
            self._sla_breach_streak = 0
            return
        self._sla_breach_streak += 1
        if self._sla_breach_streak < max(settings.SLA_BREACH_CONSECUTIVE_CYCLES, 1):
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        if self._last_sla_notify_at and (now - self._last_sla_notify_at) < datetime.timedelta(minutes=10):
            return
        self._last_sla_notify_at = now
        top_items = [
            {
                "alarm_id": alarm.id,
                "device_id": alarm.device_id,
                "priority": alarm.priority,
                "escalation_level": escalation.escalation_level,
                "time": alarm.time.isoformat() if alarm.time else None,
            }
            for alarm, escalation in rows[:20]
        ]
        payload = {
            "event": "sla_breach_alert",
            "timestamp": now.isoformat(),
            "count": len(rows),
            "consecutive_cycles": self._sla_breach_streak,
            "items": top_items,
        }
        try:
            await self._post_webhook(settings.SLA_BREACH_WECHAT_WEBHOOK_URL, "sla_breach_alert", payload, platform="wechat")
            await self._post_webhook(settings.SLA_BREACH_FEISHU_WEBHOOK_URL, "sla_breach_alert", payload, platform="feishu")
            logger.warning(f"SLA breach alert pushed: count={len(rows)}")
        except Exception as e:
            logger.error(f"SLA breach notify failed: {e}")

    async def _check_subscription_expiry_reminder(self):
        if not settings.SUBSCRIPTION_REMINDER_WEBHOOK_URL and not settings.REPORT_DAILY_EMAIL_TO:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        days = int(getattr(settings, "SUBSCRIPTION_REMINDER_DAYS", None) or settings.TRIAL_REMINDER_DAYS or 7)
        async with AsyncSessionLocal() as session:
            stmt = select(TenantSubscription).where(TenantSubscription.status == "active")
            result = await session.execute(stmt)
            subs = result.scalars().all()
            changed = 0
            for sub in subs:
                near, reminder_type = is_subscription_near_expiry(sub, days)
                if not near:
                    continue
                if sub.reminder_sent_at and (now - _ensure_aware(sub.reminder_sent_at)) < datetime.timedelta(hours=24):
                    continue
                payload = {
                    "event": "subscription_expiry_reminder",
                    "tenant_id": sub.tenant_id,
                    "plan_code": sub.plan_code,
                    "reminder_type": reminder_type,
                    "ends_at": sub.ends_at.isoformat() if sub.ends_at else None,
                    "timestamp": now.isoformat(),
                }
                await self._post_webhook(settings.SUBSCRIPTION_REMINDER_WEBHOOK_URL, "subscription_expiry_reminder", payload)
                await self._send_email("subscription_expiry_reminder", payload, settings.REPORT_DAILY_EMAIL_TO)
                sub.reminder_sent_at = now
                changed += 1
            if changed > 0:
                await session.commit()

    # 定时自动备份 + 备份加密 + 旧备份清理
    async def _auto_backup_check(self):
        """每日自动备份：凌晨2点(本地时区)执行一次，加密存储，保留最近30天"""
        auto_backup_enabled = bool(getattr(settings, "AUTO_BACKUP_ENABLED", False))
        if not auto_backup_enabled:
            return
        now = now_in_app_timezone()
        target_hour = int(getattr(settings, "AUTO_BACKUP_HOUR", 2))
        if now.hour != target_hour:
            return
        today = now.date()
        if self._last_auto_backup_date == today:
            return
        self._last_auto_backup_date = today
        try:
            await self._execute_auto_backup(now)
            await self._cleanup_old_backups()
        except Exception as e:
            logger.error(f"Auto backup failed: {e}")

    async def _execute_auto_backup(self, now: datetime.datetime):
        """执行自动备份并加密"""
        import json as _json
        import os as _os
        from sqlalchemy import text as _text
        from app.core.field_crypto import encrypt_field

        async with AsyncSessionLocal() as db:
            tables_to_backup = [
                "users", "assets", "resources", "alarms", "regions",
                "organizations", "media_nodes", "billing_plans",
                "tenant_subscriptions", "tenant_branding", "plugin_orders",
                "roles", "push_channels", "platforms", "system_settings",
            ]
            sensitive_fields = {"users": {"hashed_password", "totp_secret"}}
            backup_data = {}
            for table in tables_to_backup:
                try:
                    safe_table = table.replace('"', '""')
                    result = await db.execute(_text(f'SELECT * FROM "{safe_table}"'))
                    rows = result.mappings().all()
                    backup_data[table] = [dict(row) for row in rows]
                except Exception as e:
                    logger.warning(f"Auto backup table {table} failed: {e}")
                    backup_data[table] = []

            for key in backup_data:
                redact_fields = sensitive_fields.get(key, set())
                for row in backup_data[key]:
                    for k in list(row.keys()):
                        v = row[k]
                        if k in redact_fields:
                            row[k] = "***REDACTED***"
                        elif isinstance(v, (datetime.datetime, datetime.date)):
                            row[k] = v.isoformat()
                        elif isinstance(v, bytes):
                            row[k] = v.hex()

            backup_dir = _os.path.join(_os.getcwd(), "data", "backups")
            _os.makedirs(backup_dir, exist_ok=True)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            backup_filename = f"pygbsentry_autobackup_{timestamp}.json"
            backup_path = _os.path.join(backup_dir, backup_filename)

            raw_json = _json.dumps(backup_data, ensure_ascii=False, indent=2, default=str)

            # 备份加密 — 使用AES-256-GCM加密备份文件
            encrypt_backups = bool(getattr(settings, "BACKUP_ENCRYPTION_ENABLED", True))
            if encrypt_backups:
                encrypted = encrypt_field(raw_json, purpose="backup")
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(encrypted)
                logger.info(f"Auto backup created (encrypted): {backup_filename}")
            else:
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(raw_json)
                logger.info(f"Auto backup created (plaintext): {backup_filename}")

    async def _cleanup_old_backups(self):
        """清理超过保留天数的自动备份文件"""
        import os as _os
        retention_days = int(getattr(settings, "AUTO_BACKUP_RETENTION_DAYS", 30))
        backup_dir = _os.path.join(_os.getcwd(), "data", "backups")
        if not _os.path.isdir(backup_dir):
            return
        cutoff = time.time() - retention_days * 86400
        removed = 0
        for f in _os.listdir(backup_dir):
            if not f.startswith("pygbsentry_autobackup_"):
                continue
            fp = _os.path.join(backup_dir, f)
            try:
                if _os.path.getmtime(fp) < cutoff:
                    _os.remove(fp)
                    removed += 1
            except OSError:
                logger.debug("swallowed_exception", exc_info=True)
        if removed > 0:
            logger.info(f"Cleaned up {removed} old auto backup(s)")

    # FIX: [2026-07-03] 内存增长检测 — 追踪进程内存使用，持续增长时告警并清理缓存 [可靠性工程师]
    async def _check_memory_growth(self):
        """检测进程内存增长趋势。

        策略：
        1. 每 30 秒采样一次进程 RSS 内存
        2. 保留最近 120 个采样点（约 1 小时）
        3. 若内存持续增长超过阈值（默认 500MB 增量），触发缓存清理和 WARNING 日志
        """
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = round(process.memory_info().rss / 1024 / 1024, 1)
        except Exception:
            return

        now_ts = time.time()
        self._memory_last_mb = mem_mb
        if self._memory_baseline_mb == 0.0:
            self._memory_baseline_mb = mem_mb
        self._memory_check_history.append((now_ts, mem_mb))
        # 保留最近 120 个采样点（约 1 小时，每 30 秒一次）
        if len(self._memory_check_history) > 120:
            self._memory_check_history = self._memory_check_history[-120:]

        # 检查内存增长阈值
        growth_threshold_mb = int(getattr(settings, "MEMORY_GROWTH_ALERT_THRESHOLD_MB", 500) or 500)
        growth = mem_mb - self._memory_baseline_mb
        if growth > growth_threshold_mb:
            logger.warning(
                f"Memory growth alert: current={mem_mb}MB, baseline={self._memory_baseline_mb}MB, "
                f"growth={growth:.1f}MB (threshold={growth_threshold_mb}MB). Triggering cache cleanup."
            )
            # 清理各模块缓存
            try:
                from app.core.settings_cache import invalidate as invalidate_settings_cache
                invalidate_settings_cache()
            except Exception as e:
                logger.warning(f"Memory cleanup: settings cache invalidation failed: {e}")
            try:
                from app.sip.catalog_data_manager import catalog_data_manager
                if hasattr(catalog_data_manager, '_cache'):
                    catalog_data_manager._cache.clear()
            except Exception as e:
                logger.warning(f"Memory cleanup: catalog data cache clear failed: {e}")
            try:
                from app.sip.sip_trace_store import sip_trace_store
                if hasattr(sip_trace_store, 'clear'):
                    sip_trace_store.clear()
            except Exception as e:
                logger.warning(f"Memory cleanup: sip trace store clear failed: {e}")
            # 重置基线，避免重复告警
            self._memory_baseline_mb = mem_mb

        # 内存绝对阈值告警
        absolute_threshold_mb = int(getattr(settings, "MEMORY_ABSOLUTE_ALERT_THRESHOLD_MB", 2048) or 2048)
        if mem_mb > absolute_threshold_mb:
            self.mark_degraded("memory_high")
        else:
            self.clear_degraded("memory_high")

    # FIX: [2026-07-03] 磁盘空间监控 — 磁盘空间不足时停止录像并告警 [可靠性工程师]
    async def _check_disk_space(self):
        """检测录像存储磁盘空间，不足时停止录像并发送告警。

        策略：
        1. 检查录像存储路径所在磁盘的使用率
        2. 超过 DISK_SPACE_CRITICAL_THRESHOLD（默认 95%）时停止录像并告警
        3. 超过 DISK_SPACE_WARNING_THRESHOLD（默认 85%）时发出告警
        4. 恢复到 DISK_SPACE_RECOVERY_THRESHOLD（默认 80%）以下时恢复录像
        """
        disk_check_enabled = bool(getattr(settings, "DISK_SPACE_MONITOR_ENABLED", True))
        if not disk_check_enabled:
            return

        # 获取录像存储路径
        record_path = ""
        try:
            async with AsyncSessionLocal() as session:
                from app.models.system_setting import SystemSetting
                from sqlalchemy import select as _sel
                result = await session.execute(_sel(SystemSetting).where(SystemSetting.setting_key == "record_storage_root"))
                row = result.scalars().first()
                record_path = (row.setting_value if row else "").strip()
        except Exception as e:
            logger.debug(f"Disk space check: failed to load record_storage_root from DB: {e}")

        if not record_path:
            record_path = os.path.join(os.getcwd(), "data", "record")

        try:
            disk_usage = shutil.disk_usage(record_path)
            used_percent = (disk_usage.used / disk_usage.total) * 100
        except Exception as e:
            logger.debug(f"Disk space check failed for path {record_path}: {e}")
            return

        critical_threshold = int(getattr(settings, "DISK_SPACE_CRITICAL_THRESHOLD", 95) or 95)
        warning_threshold = int(getattr(settings, "DISK_SPACE_WARNING_THRESHOLD", 85) or 85)
        recovery_threshold = int(getattr(settings, "DISK_SPACE_RECOVERY_THRESHOLD", 80) or 80)

        now = datetime.datetime.now(datetime.timezone.utc)

        if used_percent >= critical_threshold:
            if not self._disk_recording_stopped:
                logger.error(
                    f"Disk space critical: {used_percent:.1f}% used (threshold={critical_threshold}%). "
                    f"Stopping recording to prevent disk full."
                )
                self._disk_recording_stopped = True
                self.mark_degraded("disk_space_critical")
                # 通过插件事件通知录像模块停止
                fire_and_forget(
                    plugin_manager.emit("ON_DISK_SPACE_CRITICAL", {
                        "path": record_path,
                        "used_percent": round(used_percent, 1),
                        "action": "stop_recording",
                    })
                )
            # 告警冷却 30 分钟
            if not self._disk_alert_cooldown_until or now > self._disk_alert_cooldown_until:
                self._disk_alert_cooldown_until = now + datetime.timedelta(minutes=30)
                await self._post_webhook(
                    settings.HEALTH_ALERT_WEBHOOK_URL,
                    "disk_space_critical",
                    {
                        "event": "disk_space_critical",
                        "path": record_path,
                        "used_percent": round(used_percent, 1),
                        "threshold": critical_threshold,
                        "timestamp": now.isoformat(),
                    },
                )
        elif used_percent >= warning_threshold:
            if not self._disk_alert_cooldown_until or now > self._disk_alert_cooldown_until:
                self._disk_alert_cooldown_until = now + datetime.timedelta(minutes=30)
                logger.warning(
                    f"Disk space warning: {used_percent:.1f}% used (threshold={warning_threshold}%)"
                )
        else:
            # 恢复
            if self._disk_recording_stopped and used_percent < recovery_threshold:
                logger.info(
                    f"Disk space recovered: {used_percent:.1f}% used (below recovery threshold {recovery_threshold}%). "
                    f"Resuming recording."
                )
                self._disk_recording_stopped = False
                self.clear_degraded("disk_space_critical")
                fire_and_forget(
                    plugin_manager.emit("ON_DISK_SPACE_RECOVERED", {
                        "path": record_path,
                        "used_percent": round(used_percent, 1),
                        "action": "resume_recording",
                    })
                )

health_service = HealthService()
