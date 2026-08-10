import asyncio
import datetime
from loguru import logger
import os
import time
import json
import urllib.parse


from app.core.zlm_target import resolve_zlm_api_target
from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting
from app.models.network_metric import NetworkMetric
from app.models.media_node import MediaNode
from app.models.stream_session import StreamSession
from sqlalchemy import select
from app.core.media_nodes_db import _to_runtime



_task: asyncio.Task | None = None

PLUGIN_ID = "stream_health"

_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "zlm_api": "",
    "zlm_secret": "",
    "check_interval": 60,
    "sla_log_file": "logs/stream_health.log",
    "quality_diag_enabled": True,
    "signal_loss_threshold_seconds": 300,
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


async def _get_runtime_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl_sec:
        return _cfg_cache

    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()

    merged = dict(_DEFAULT_BASE_CONFIG)
    any_enabled = False
    interval_max: int | None = None

    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if not isinstance(parsed, dict):
                continue
            if bool(parsed.get("enabled", False)):
                any_enabled = True
            if "check_interval" in parsed:
                ci = int(parsed.get("check_interval") or 0)
                if ci > 0:
                    interval_max = ci if interval_max is None else max(interval_max, ci)

            # 其它字段：取第一个有效配置
            for k in ("zlm_api", "zlm_secret", "sla_log_file"):
                if (merged.get(k) in ("", None)) and parsed.get(k) not in ("", None):
                    merged[k] = parsed.get(k)
        except Exception:
            continue

    merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
    if interval_max is not None:
        merged["check_interval"] = interval_max

    _cfg_cache = merged
    _cfg_ts = now
    return _cfg_cache


async def _resolve_zlm_target_from_cfg(cfg: dict):
    """
    如果配置了 zlm_api/zlm_secret，则优先从配置取；否则走 resolve_zlm_api_target。
    """
    zlm_api = str(cfg.get("zlm_api") or "").strip()
    zlm_secret = str(cfg.get("zlm_secret") or "").strip()

    if zlm_api:
        try:
            parsed = urllib.parse.urlparse(zlm_api)
            host = parsed.hostname or ""
            port = parsed.port or 80
            if host:
                return host, int(port), zlm_secret
        except Exception as e:
            logger.warning(f"Error: {e}")

    zlm_host, zlm_port, resolved_secret, _, _ = await resolve_zlm_api_target()
    return zlm_host, zlm_port, (zlm_secret or resolved_secret)


# ============ 视频质量诊断 ============

# 内存态：记录每个流的最后活跃时间，key = f"{app}/{stream_id}"
_stream_last_seen: dict[str, float] = {}
# 诊断事件缓存（避免重复告警），key = f"{app}/{stream_id}:{issue}"
_diag_cooldown: dict[str, float] = {}
_DIAG_COOLDOWN_SEC = 3600
_last_cooldown_cleanup_ts: float = 0.0  # 同类诊断至少间隔 1 小时


def _run_quality_diag(streams: list[dict], check_interval: int, signal_loss_threshold: int, cfg: dict) -> None:
    """
    基于 ZLM 流列表做视频质量诊断：
    1. 信号丢失检测：流在 ZLM 上消失超过阈值时间，触发报警
    2. 低码率检测：有人观看但码率为 0（画面黑/无视频）
    3. 码率异常检测：码率波动超过 10x 或低于 10kbps（有视频但异常）
    """
    now_ts = time.time()
    current_keys = set()
    sla_log_file = str(cfg.get("sla_log_file") or "logs/stream_health.log")
    os.makedirs(os.path.dirname(sla_log_file) or ".", exist_ok=True)

    def _log_diag(stream_key: str, issue: str, detail: str):
        cooldown_key = f"{stream_key}:{issue}"
        last = _diag_cooldown.get(cooldown_key, 0)
        if now_ts - last < _DIAG_COOLDOWN_SEC:
            return
        _diag_cooldown[cooldown_key] = now_ts
        ts = datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{issue}] {stream_key} - {detail}\n"
        logger.warning("[QualityDiag] %s %s: %s", issue, stream_key, detail)
        try:
            with open(sla_log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning(f"Error: {e}")

    for s in streams:
        app = s.get("app", "")
        stream_id = s.get("stream", "")
        key = f"{app}/{stream_id}"
        current_keys.add(key)

        # 更新最后活跃时间
        _stream_last_seen[key] = now_ts

        bytes_speed = float(s.get("bytesSpeed") or s.get("bytes_speed") or s.get("speed") or 0)
        total_readers = int(s.get("totalReaderCount") or s.get("total_reader_count") or 0)

        # 1. 低码率（有人看但无码率）
        if bytes_speed < 1024 and total_readers > 0:
            _log_diag(key, "LOW_BITRATE", f"bytesSpeed={bytes_speed:.0f} readers={total_readers}")

        # 2. 码率异常（极低或极高）
        if bytes_speed > 0 and bytes_speed < 10000:
            _log_diag(key, "BITRATE_ANOMALY", f"very_low_bitrate={bytes_speed:.0f} bytes/s")
        # 注：极高码率（> 100 Mbps）通常意味着异常数据，zlm 层面直接过滤即可

        # 3. 无码率但有人在看（信号丢失前兆）
        if bytes_speed <= 0 and total_readers > 0:
            _log_diag(key, "NO_VIDEO_SIGNAL", f"bytesSpeed=0 readers={total_readers}")

    # 4. 信号丢失检测（流消失）
    #    遍历之前记录过的流，若超过阈值时间没再出现，则认为是信号丢失
    threshold = max(60, signal_loss_threshold)
    gone_keys = [
        k for k, last_ts in list(_stream_last_seen.items())
        if k not in current_keys and (now_ts - last_ts) >= threshold
    ]
    for gone_key in gone_keys:
        _log_diag(gone_key, "SIGNAL_LOST", f"stream_missing_since={int(now_ts - _stream_last_seen[gone_key])}s")
        del _stream_last_seen[gone_key]

    # 清理过老的 cooldown 缓存（每小时清理一次）
    if int(now_ts) - _last_cooldown_cleanup_ts >= 3600:  # noqa: F823
        expired = [k for k, ts in _diag_cooldown.items() if now_ts - ts > _DIAG_COOLDOWN_SEC * 2]
        for k in expired:
            del _diag_cooldown[k]
        _last_cooldown_cleanup_ts = now_ts


async def monitor_health():
    """
    Periodically check stream bitrate and status from ZLM
    """
    _node_offline_counts: dict[str, int] = {}
    _OFFLINE_THRESHOLD_COUNT = 2
    while True:
        try:
            cfg = await _get_runtime_cfg()
            if not cfg or not cfg.get("enabled", True):
                await asyncio.sleep(int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"]))
                continue

            check_interval = int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"])
            check_interval = max(10, min(3600, check_interval))

            zlm_host, zlm_port, zlm_secret = await _resolve_zlm_target_from_cfg(cfg)

            data = {}
            try:
                from app.services.zlm_stream_control import _get_zlm_client
                _client = await _get_zlm_client()
                # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
                res = await _client.post(
                    f"http://{zlm_host}:{zlm_port}/index/api/getMediaList",
                    data={"secret": zlm_secret},
                    timeout=5.0,
                )
                if res.status_code == 200:
                    data = res.json()
            except Exception as req_exc:
                logger.debug(f"[Health] Failed to get media list from ZLM ({zlm_host}:{zlm_port}): {req_exc}")
            # -----------------------------
            # ZLM HA Failover Check Logic
            # -----------------------------

            try:
                async with AsyncSessionLocal() as session:
                    # 查找所有媒体节点
                    stmt = select(MediaNode)
                    result = await session.execute(stmt)
                    nodes = result.scalars().all()

                    if not nodes:
                        _node_offline_counts.clear()

                    offline_nodes = []
                    healthy_nodes = []
                    now_ts = int(time.time())

                    for node in nodes:
                        node_key = f"{node.ip}:{node.http_port}"
                        if node.is_online == 1:
                            last_heartbeat = int(node.last_seen_at.timestamp() if node.last_seen_at else 0)
                            # 放宽超时：默认 60 秒（兼容 ZLM 心跳间隔 30s + 网络抖动）
                            timeout_sec = max(60, int(cfg.get("zlm_keepalive_timeout", 60)))
                            if now_ts - last_heartbeat > timeout_sec:
                                # 记录连续离线次数
                                _node_offline_counts[node_key] = _node_offline_counts.get(node_key, 0) + 1
                                if _node_offline_counts[node_key] >= _OFFLINE_THRESHOLD_COUNT:
                                    logger.warning(f"[HA Failover] Media node {node.ip}:{node.http_port} heartbeat timeout ({now_ts - last_heartbeat}s > {timeout_sec}s), marking OFFLINE.")
                                    node.is_online = 0
                                    offline_nodes.append(node)
                                else:
                                    logger.debug(f"[HA Failover] Media node {node.ip}:{node.http_port} heartbeat delayed ({_node_offline_counts[node_key]}/{_OFFLINE_THRESHOLD_COUNT}), waiting...")
                            else:
                                _node_offline_counts.pop(node_key, None)
                                healthy_nodes.append(node)
                        else:
                            _node_offline_counts.pop(node_key, None)

                    if offline_nodes and healthy_nodes:
                        from app.core.media_nodes_db import select_best_db_node
                        try:
                            async with AsyncSessionLocal() as sel_session:
                                best_node = await select_best_db_node(sel_session, exclude_node_ids=[n.id for n in offline_nodes])
                            if best_node:
                                target_node = best_node
                            else:
                                target_node = healthy_nodes[0]
                        except Exception:
                            target_node = healthy_nodes[0]
                        target_runtime = _to_runtime(target_node)

                        _ha_semaphore = asyncio.Semaphore(5)

                        async def _safe_reinvite(ds_item, tgt_rt):
                            async with _ha_semaphore:
                                try:
                                    import app.sip.invite as sip_invite_module
                                    if sip_invite_module.sip_invite:
                                        await sip_invite_module.sip_invite.send_reinvite(ds_item, tgt_rt)
                                except Exception as reinvite_err:
                                    logger.warning(f"[HA Failover] reinvite failed for {ds_item.app}/{ds_item.stream}: {reinvite_err}")

                        reinvite_tasks = []
                        for off_node in offline_nodes:
                            sess_stmt = select(StreamSession).where(StreamSession.media_server_id == off_node.id)
                            sess_res = await session.execute(sess_stmt)
                            dead_sessions = sess_res.scalars().all()

                            for ds in dead_sessions:
                                logger.info(f"[HA Failover] Moving stream {ds.app}/{ds.stream} from {off_node.ip} to {target_node.ip}")
                                reinvite_tasks.append(asyncio.create_task(_safe_reinvite(ds, target_runtime)))

                        if reinvite_tasks:
                            results = await asyncio.gather(*reinvite_tasks, return_exceptions=True)
                            fail_count = sum(1 for r in results if isinstance(r, Exception))
                            if fail_count:
                                logger.warning(f"[HA Failover] {fail_count}/{len(results)} reinvite tasks failed")

                    await session.commit()
            except Exception as e:
                logger.error(f"[HA Failover] Error during node health check: {e}")
            streams = data.get("data") or []

            # -------------------
            # 视频质量诊断
            # -------------------
            quality_diag_enabled = bool(cfg.get("quality_diag_enabled", True))
            signal_loss_threshold = int(cfg.get("signal_loss_threshold_seconds", 300))
            if quality_diag_enabled:
                try:
                    # S-20 使用asyncio.to_thread将同步文件I/O移出事件循环，避免阻塞
                    await asyncio.to_thread(_run_quality_diag, streams, check_interval, signal_loss_threshold, cfg)
                except Exception as e:
                    logger.error("[Health] Quality diag error: %s", e)

            # 统计并发流数与总带宽，写入 network_metrics 表
            total_bytes_per_sec = 0.0
            for s in streams:
                bs = s.get("bytesSpeed") or s.get("bytes_speed") or s.get("speed") or 0
                total_bytes_per_sec += max(float(bs), 0.0)
            bandwidth_kbps = int(round((total_bytes_per_sec * 8.0) / 1000.0))
            active_count = len(streams)
            try:
                async with AsyncSessionLocal() as metric_session:
                    metric_session.add(NetworkMetric(
                        tenant_id="default",
                        metric="active_streams",
                        value=int(active_count),
                    ))
                    metric_session.add(NetworkMetric(
                        tenant_id="default",
                        metric="zlm_bandwidth_kbps",
                        value=bandwidth_kbps,
                    ))
                    await metric_session.commit()
            except Exception as e:
                logger.warning(f"Error: {e}")

            for s in streams:
                app = s["app"]
                stream_id = s["stream"]
                bytes_speed = s.get("bytesSpeed", 0)
                total_readers = s.get("totalReaderCount", 0)

                if bytes_speed < 1024 and total_readers > 0:
                    logger.warning(
                        f"[Health] Low bitrate detected on {app}/{stream_id}: {bytes_speed / 1024:.2f} KB/s"
                    )
                    sla_log_file = str(cfg.get("sla_log_file") or _DEFAULT_BASE_CONFIG["sla_log_file"])
                    try:
                        os.makedirs(os.path.dirname(sla_log_file) or ".", exist_ok=True)
                        with open(sla_log_file, "a", encoding="utf-8") as f:
                            f.write(f"{time.ctime()} - {app}/{stream_id} - Low Bitrate: {bytes_speed}\n")
                    except Exception as e:
                        logger.warning(f"Error: {e}")

        except Exception as e:
            logger.error(f"[Health] Monitor error: {e}")

        try:
            cfg = await _get_runtime_cfg()
            interval = int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"])
        except Exception:
            interval = _DEFAULT_BASE_CONFIG["check_interval"]
        interval = max(10, min(3600, interval))
        await asyncio.sleep(interval)


async def start():
    global _task
    logger.info("[Health] Plugin started")
    _task = asyncio.create_task(monitor_health())


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.warning("(asyncio.CancelledError, asyncio.TimeoutError) occurred")
        except Exception as e:
            logger.warning(f"Error: {e}")
    _task = None
