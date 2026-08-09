from __future__ import annotations
from loguru import logger

import asyncio
import time
from dataclasses import dataclass
from app.services.zlm_stream_control import _get_zlm_client
from typing import Any

# 节点探测失败日志限速：同一节点 60 秒内只输出一次 WARNING
_NODE_FAIL_LOG_COOLDOWN: dict[str, float] = {}
_NODE_FAIL_LOG_COOLDOWN_SECONDS = 60.0

from datetime import datetime, timedelta, timezone
import socket
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.media_node import MediaNode

from app.models.system_setting import SystemSetting
from app.models.stream_session import StreamSession
from app.models.media_port_lease import MediaPortLease


@dataclass
class RuntimeMediaNode:
    id: str
    host: str
    http_port: int
    rtp_port: int
    public_host: str
    public_http_port: int
    secret: str
    # 可选扩展（路 B）
    hook_base_url: str | None = None
    hook_ip: str | None = None
    sdp_ip: str | None = None
    https_port: int = 0
    rtsp_port: int = 0
    rtsps_port: int = 0
    rtmp_port: int = 0
    rtmps_port: int = 0
    rtp_port_mode: str = "single"
    rtp_port_range_start: int = 0
    rtp_port_range_end: int = 0
    record_mgr_port: int = 0


def _to_runtime(node: MediaNode) -> RuntimeMediaNode:
    public_host = (
        (getattr(node, "stream_ip", None) or "").strip()
        or (node.public_ip or "").strip()
        or (settings.STREAM_PUBLIC_HOST or "").strip()
        or (node.ip or "").strip()
    )
    if not public_host:
        public_host = node.ip
    public_http_port = settings.STREAM_PUBLIC_HTTP_PORT or int(node.http_port or 0)
    # secret 为空时回退全局密钥，避免 getMediaList?secret= 刷屏与探测失败
    # P0-02: node 是 ORM MediaNode，secret 列存储密文，需通过 decrypted_secret 取明文
    _plain_secret = node.decrypted_secret
    node_secret = (str(_plain_secret or "").strip() or str(settings.MEDIA_SERVER_SECRET or "").strip())
    return RuntimeMediaNode(
        id=node.id,
        host=node.ip,
        http_port=int(node.http_port or 0),
        rtp_port=int(node.rtp_proxy_port or 0),
        public_host=public_host,
        public_http_port=public_http_port,
        secret=node_secret,
        hook_base_url=getattr(node, "hook_base_url", None),
        hook_ip=getattr(node, "hook_ip", None),
        sdp_ip=getattr(node, "sdp_ip", None),
        https_port=int(getattr(node, "https_port", 0) or 0),
        rtsp_port=int(getattr(node, "rtsp_port", 0) or 0),
        rtsps_port=int(getattr(node, "rtsps_port", 0) or 0),
        rtmp_port=int(getattr(node, "rtmp_port", 0) or 0),
        rtmps_port=int(getattr(node, "rtmps_port", 0) or 0),
        rtp_port_mode=str(getattr(node, "rtp_port_mode", "single") or "single").lower(),
        rtp_port_range_start=int(getattr(node, "rtp_port_range_start", 0) or 0),
        rtp_port_range_end=int(getattr(node, "rtp_port_range_end", 0) or 0),
        record_mgr_port=int(getattr(node, "record_mgr_port", 0) or 0),
    )


def _is_local_host(v: str | None) -> bool:
    s = (v or "").strip().lower()
    return s in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_local_url(v: str | None) -> bool:
    text = (v or "").strip()
    if not text:
        return False
    try:
        parsed = urlparse(text)
        host = (parsed.hostname or "").strip()
        return _is_local_host(host)
    except Exception as e:
        logger.warning(f"Failed to parse URL for local-host check '{text}': {e}")
        return False


def _parse_rtp_port_range(raw: str | None) -> tuple[str, int, int]:
    text = str(raw or "").strip()
    if "-" not in text:
        return "single", 0, 0
    try:
        left, right = text.split("-", 1)
        start = int(left.strip() or 0)
        end = int(right.strip() or 0)
        if start > 0 and end >= start:
            return "range", start, end
    except Exception as e:
        logger.warning(f"Error: {e}")
    return "single", 0, 0


def _detect_lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not _is_local_host(ip):
                return ip
        finally:
            try:
                s.close()
            except Exception as e:
                logger.warning(f"socket close error: {e}")
    except Exception as e:
        logger.warning(f"Failed to detect LAN IP: {e}")
        return None
    return None


async def _detect_public_ip() -> str | None:
    if not settings.AUTO_DETECT_PUBLIC_IP:
        return None
    url = str(settings.PUBLIC_IP_LOOKUP_URL or "").strip()
    if not url:
        return None
    timeout_s = settings.PUBLIC_IP_LOOKUP_TIMEOUT_SECONDS
    try:
        client = await _get_zlm_client()
        r = await client.get(url, timeout=timeout_s)
        if r.status_code >= 400:
            return None
        ip = (r.text or "").strip()
        if ip and not _is_local_host(ip):
            return ip
    except Exception as e:
        logger.warning(f"Failed to detect public IP via {url}: {e}")
        return None
    return None


async def get_active_media_node_id(db: AsyncSession) -> str | None:
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == "active_media_node_id"))
    setting = result.scalars().first()
    value = (setting.setting_value if setting else None) or None
    return (value or "").strip() or None


async def get_db_node_by_id(db: AsyncSession, node_id: str) -> MediaNode | None:
    if not node_id:
        return None
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    return result.scalars().first()


async def list_db_media_nodes(db: AsyncSession) -> list[RuntimeMediaNode]:
    result = await db.execute(select(MediaNode))
    nodes = result.scalars().all()
    return [_to_runtime(n) for n in nodes]


async def ensure_embedded_media_node(db: AsyncSession) -> str | None:
    """
    确保 DB 中存在一条“内置 ZLM”节点记录，用于运维中心展示与运维统一管理。
    - 仅当不存在 is_embedded=true 的记录时创建
    - 不强制设置为 active（避免干扰外置节点策略）
    """
    try:
        result = await db.execute(select(MediaNode).where(MediaNode.is_embedded.is_(True)).limit(1))
        existed = result.scalars().first()
        range_mode, range_start, range_end = _parse_rtp_port_range(
            settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE
        )
        # 计算更合理的“对外可达地址”默认值：优先 STREAM_PUBLIC_HOST，其次 BACKEND_PUBLIC_HOST；
        # 若仍是 localhost/127.0.0.1，则不写入（留给用户在运维中心手工填）。
        # W-19 MEDIA_SERVER_HOST回退值改为空字符串，非本地部署时显式报错
        media_host = str(settings.MEDIA_SERVER_HOST or "").strip()
        # 强制使用环境配置里的 IP，如果它是 127.0.0.1 则让 ZLM 无法正确把 hook 连上来（或者它就是本地调试用）
        # 这里移除自动探测局域网 IP，保证和 .env 里的一致，或者确保不污染 DB
        stream_public = str(settings.STREAM_PUBLIC_HOST or "").strip()
        backend_public = str(settings.BACKEND_PUBLIC_HOST or "").strip()
        preferred_public = stream_public or backend_public
        if preferred_public.lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
            preferred_public = ""
        if not preferred_public:
            preferred_public = (await _detect_public_ip()) or ""
        preferred_public = preferred_public or None
        backend_public_port = settings.BACKEND_PUBLIC_PORT
        api_v1_str = str(settings.API_V1_STR or "/api/v1")
        force_single = settings.FORCE_SINGLE_PORT_MULTIPLEXING

        if existed:
            changed = False
            # FIX: [2026-07-16] 节点已存在但 secret 为空或无法解密时，用当前 MEDIA_SERVER_SECRET 重新填充。
            # 根因 1: 首次创建节点时若 FIELD_ENCRYPTION_KEY 为空，encrypt_field 抛 ValueError 被外层
            #         except 捕获，导致 secret 列为 None。
            # 根因 2: 早期版本 MediaNode.secret 直接存明文（无 decrypted_secret 属性），
            #         后续版本加了加密层但旧数据没迁移，secret 列存的是明文而非密文。
            #         此时 decrypt_field(明文) 会失败（因为明文不是合法的 base64 密文格式）。
            # 根因 3: FIELD_ENCRYPTION_KEY 被修改后，旧密文无法用新密钥解密。
            # 这三种情况都会导致 health_service 误报 "Field decryption failed"。
            _current_secret = getattr(existed, "secret", None) or ""
            _need_refill = False
            if not _current_secret:
                _need_refill = True
            else:
                # secret 列有值，检查能否解密
                try:
                    from app.core.field_crypto import decrypt_field as _decrypt_check
                    _decrypted = _decrypt_check(_current_secret, purpose="media_secret")
                    if _decrypted is None:
                        _need_refill = True
                        logger.info(f"ensure_embedded_media_node: existing secret cannot be decrypted (likely plaintext from legacy version or key changed), will refill")
                except Exception:
                    _need_refill = True

            if _need_refill:
                _media_secret = str(settings.MEDIA_SERVER_SECRET or "").strip()
                if _media_secret:
                    existed.decrypted_secret = _media_secret  # setter 自动加密
                    changed = True
                    logger.info("ensure_embedded_media_node: refilled secret with current MEDIA_SERVER_SECRET (encrypted)")
            if (not (getattr(existed, "public_ip", None) or "").strip()) and preferred_public:
                existed.public_ip = preferred_public
                changed = True
            if (not (getattr(existed, "stream_ip", None) or "").strip()) and preferred_public:
                existed.stream_ip = preferred_public
                changed = True
            existed_ip = (getattr(existed, "ip", None) or "").strip()
            if ((not existed_ip) or _is_local_host(existed_ip)) and media_host:
                existed.ip = media_host
                changed = True
            if (not (getattr(existed, "hook_ip", None) or "").strip()) and (media_host and not _is_local_host(media_host)):
                existed.hook_ip = media_host
                changed = True
            current_hook_base = (getattr(existed, "hook_base_url", None) or "").strip()
            # FIXED-P0: 优先使用 MEDIA_SERVER_HOOK_BASE_URL 环境变量
            # ZLM 在本机时需要用 127.0.0.1 回调后端，不能用公网域名
            # FIX: [2026-07-16] 确保 hook_base_url 始终包含 /api/v1/hook 后缀，
            # 否则 _resolve_webhook_base 会判定为 loopback URL 跳过，回退到公网域名
            global_hook_base = str(settings.MEDIA_SERVER_HOOK_BASE_URL or "").strip()
            if global_hook_base:
                # 附加 /api/v1/hook 后缀（用户配置可能只给了 http://127.0.0.1:8000）
                _normalized_hook_base = global_hook_base.rstrip("/")
                if not _normalized_hook_base.endswith(f"{api_v1_str}/hook"):
                    _normalized_hook_base = f"{_normalized_hook_base}{api_v1_str}/hook"
                if current_hook_base != _normalized_hook_base:
                    existed.hook_base_url = _normalized_hook_base
                    changed = True
            elif not current_hook_base or _is_local_url(current_hook_base):
                hook_host = (getattr(existed, "hook_ip", None) or "").strip() or media_host
                if hook_host and not _is_local_host(hook_host):
                    existed.hook_base_url = f"http://{hook_host}:{backend_public_port}{api_v1_str}/hook"
                    changed = True
            if getattr(existed, "auto_config_enabled", None) is None:
                existed.auto_config_enabled = True
                changed = True

            existed_mode = str(getattr(existed, "rtp_port_mode", "single") or "single").lower()
            existed_start = int(getattr(existed, "rtp_port_range_start", 0) or 0)
            existed_end = int(getattr(existed, "rtp_port_range_end", 0) or 0)

            if range_mode == "range" and not force_single:
                if existed_mode != "range" or existed_start != range_start or existed_end != range_end:
                    existed.rtp_port_mode = "range"
                    existed.rtp_port_range_start = int(range_start)
                    existed.rtp_port_range_end = int(range_end)
                    changed = True
            elif force_single and existed_mode != "single":
                existed.rtp_port_mode = "single"
                changed = True

            if changed:
                await db.commit()
            return existed.id

        node = MediaNode(
            ip=media_host,
            public_ip=preferred_public,
            stream_ip=preferred_public,
            hook_base_url=(
                f"http://{media_host}:{backend_public_port}{api_v1_str}/hook"
                if media_host and not _is_local_host(media_host)
                else None
            ),
            hook_ip=(media_host if media_host and not _is_local_host(media_host) else None),
            http_port=settings.MEDIA_SERVER_HTTP_PORT,
            rtsp_port=settings.MEDIA_SERVER_RTSP_PORT,
            rtmp_port=settings.MEDIA_SERVER_RTMP_PORT,
            rtp_proxy_port=settings.MEDIA_SERVER_RTP_PROXY_PORT,
            rtp_port_mode=range_mode,
            rtp_port_range_start=int(range_start),
            rtp_port_range_end=int(range_end),
            decrypted_secret=str(settings.MEDIA_SERVER_SECRET or ""),  # P0-02: setter 自动加密后存入 secret 列
            is_embedded=True,
            # 内置节点默认允许自动下发配置（由 media_manager 生成 config.ini）
            auto_config_enabled=True,
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)
        return node.id
    except Exception as e:
        logger.warning(f"ensure_embedded_media_node failed: {e}")
        try:
            await db.rollback()
        except Exception as e:
            logger.warning(f"Error: {e}")
        return None


async def get_db_media_node_by_id(db: AsyncSession, node_id: str | None) -> RuntimeMediaNode | None:
    if not node_id:
        return None
    result = await db.execute(select(MediaNode).where(MediaNode.id == node_id))
    node = result.scalars().first()
    return _to_runtime(node) if node else None


async def get_all_media_from_nodes(nodes: list[RuntimeMediaNode]) -> list[dict[str, Any]]:
    """聚合指定节点列表的 getMediaList，返回带 node_id 的列表。"""
    out: list[dict[str, Any]] = []

    async def _fetch(node: RuntimeMediaNode) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url = f"http://{node.host}:{node.http_port}/index/api/getMediaList"
        try:
            client = await _get_zlm_client()
            # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
            r = await client.post(url, data={"secret": node.secret}, timeout=2.0)
            if r.status_code >= 400:
                return items
            data: Any = r.json()
            if data.get("code") not in (0, "0"):
                return items
            media_list = data.get("data")
            if not isinstance(media_list, list):
                return items
            for item in media_list:
                if isinstance(item, dict):
                    items.append({**item, "node_id": node.id})
        except Exception as e:
            # FIXED: 包含节点信息便于排障，降低为 debug 避免刷屏（ZLM 未启动时属预期情况）
            logger.debug(f"getMediaList failed for node {node.id} ({node.host}:{node.http_port}): {e}")
        return items

    # P1-fix: 添加 return_exceptions=True，单节点异常不会取消其他节点的并发查询
    # 原实现下若 _fetch 抛出未预期异常（如 AttributeError 编程错误），gather 会取消所有兄弟任务
    results = await asyncio.gather(*[_fetch(n) for n in nodes], return_exceptions=True)
    for batch in results:
        if isinstance(batch, Exception):
            # _fetch 内部已有 try/except 返回空列表，这里仅处理未预期的编程错误
            logger.warning(f"get_all_media_list _fetch unexpected error: {batch}")
            continue
        out.extend(batch)
    return out


# FIX R22-SEVERE: in-flight 节点计数跟踪
# 防止突发并发（如 10+ 路 INVITE 同时到达）全部命中同一节点：
#   - 10 路 gather 同时返回相同 count 快照，独立地都选出 alive_nodes[0][0] 同一节点
#   - 导致节点瞬时压力过大，ZLM 线程池打满、RTP 端口耗尽
# 解决方案：选中节点后追加 timestamp，下次排序时将 in-flight 计数加入实际 count
#   - 30s TTL 自动过期（与 INVITE 超时匹配），无需调用方显式释放
#   - 即使调用方异常未释放，30s 后自动失效，避免永久占用计数
_node_inflight: dict[str, list[float]] = {}
# FIX: [2026-07-16] 原 30s TTL 与 INVITE 同步等待 22s + ZLM 流就绪探测 10s（共 32s）不匹配，
# in-flight 计数过期后负载均衡可能再次选中该节点，导致节点过载。
# 提升到 60s 覆盖完整点播周期。
_INFLIGHT_TTL = 60.0


def _prune_inflight(node_id: str, now: float) -> int:
    """清理过期 in-flight 条目并返回当前有效计数。"""
    timestamps = _node_inflight.get(node_id)
    if not timestamps:
        return 0
    fresh = [t for t in timestamps if now - t < _INFLIGHT_TTL]
    if fresh:
        _node_inflight[node_id] = fresh
    else:
        _node_inflight.pop(node_id, None)
    return len(fresh)


def _add_inflight(node_id: str) -> None:
    """标记节点为 in-flight 分配状态。"""
    now = time.time()
    _prune_inflight(node_id, now)
    _node_inflight.setdefault(node_id, []).append(now)


def _decr_inflight(node_id: str) -> None:
    """显式释放 in-flight 计数（可选，TTL 兜底）。"""
    timestamps = _node_inflight.get(node_id)
    if not timestamps:
        return
    now = time.time()
    fresh = [t for t in timestamps if now - t < _INFLIGHT_TTL]
    if fresh:
        # 移除最早的一个 timestamp（FIFO）
        fresh.pop(0)
        if fresh:
            _node_inflight[node_id] = fresh
        else:
            _node_inflight.pop(node_id, None)
    else:
        _node_inflight.pop(node_id, None)


async def _async_get_stream_count(node: RuntimeMediaNode) -> tuple[RuntimeMediaNode, int, bool, float, float, float]:
    """异步并发获取节点的负载流数和系统负载，返回 (node, count, is_alive, cpu, mem, net_mbps)"""
    url_list = f"http://{node.host}:{node.http_port}/index/api/getMediaList"
    url_sys = f"http://{node.host}:{node.http_port}/index/api/getStatistic"

    count = 0
    is_alive = False
    cpu = 0.0
    mem = 0.0
    net_mbps = 0.0

    try:
        client = await _get_zlm_client()
        # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
        r_list = await client.post(url_list, data={"secret": node.secret}, timeout=2.0)
        if r_list.status_code < 400:
            data = r_list.json()
            if data.get("code") in (0, "0"):
                media_list = data.get("data")
                count = len(media_list) if isinstance(media_list, list) else 0
                is_alive = True

        if is_alive:
            try:
                # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
                r_sys = await client.post(url_sys, data={"secret": node.secret}, timeout=2.0)
                if r_sys.status_code < 400:
                    sys_data = r_sys.json()
                    if sys_data.get("code") in (0, "0"):
                        sys_info = sys_data.get("data", {})
                        cpu_raw = sys_info.get("CpuUsage")
                        if cpu_raw is not None:
                            try:
                                cpu = float(cpu_raw)
                            except (ValueError, TypeError):
                                cpu = 0.0
                        mem_info = sys_info.get("MemInfo", {}) or {}
                        if isinstance(mem_info, dict):
                            mem_used = float(mem_info.get("used") or 0) / (1024 * 1024)
                            mem_total = float(mem_info.get("total") or 1) / (1024 * 1024)
                            mem = (mem_used / mem_total * 100.0) if mem_total > 0 else 0.0
                        else:
                            mem_raw = sys_info.get("memUsage") or sys_info.get("MemoryUsage")
                            if mem_raw is not None:
                                try:
                                    mem = float(mem_raw)
                                except (ValueError, TypeError):
                                    mem = 0.0
                            else:
                                mem = 0.0
                        net_in = float(sys_info.get("NetTotalIn") or 0)
                        net_out = float(sys_info.get("NetTotalOut") or 0)
                        net_mbps = (net_in + net_out) / (1024 * 1024)
            except Exception as e:
                # FIX: [2026-07-14] 日志限速：同一节点 60 秒内只输出一次 WARNING，避免 ZLM 宕机时刷屏
                node_id_stat = str(node.id)
                now_ts_stat = time.time()
                last_ts_stat = _NODE_FAIL_LOG_COOLDOWN.get(node_id_stat, 0)
                if now_ts_stat - last_ts_stat >= _NODE_FAIL_LOG_COOLDOWN_SECONDS:
                    logger.warning(f"getStatistic failed for node {node_id_stat} ({node.host}:{node.http_port}): {e}")
                    _NODE_FAIL_LOG_COOLDOWN[node_id_stat] = now_ts_stat

        return node, count, is_alive, cpu, mem, net_mbps
    except Exception as e:
        # FIX: [2026-07-14] 日志限速：同一节点 60 秒内只输出一次 WARNING，避免 ZLM 宕机时刷屏
        node_id_outer = str(getattr(node, 'id', '?'))
        now_ts_outer = time.time()
        last_ts_outer = _NODE_FAIL_LOG_COOLDOWN.get(node_id_outer, 0)
        if now_ts_outer - last_ts_outer >= _NODE_FAIL_LOG_COOLDOWN_SECONDS:
            logger.warning(f"_async_get_stream_count failed for node {node_id_outer}: {e}")
            _NODE_FAIL_LOG_COOLDOWN[node_id_outer] = now_ts_outer
        return node, 999999, False, 0.0, 0.0, 0.0

async def select_best_db_node(db: AsyncSession, exclude_node_ids: list[str] = None) -> RuntimeMediaNode | None:
    """
    异步并发对所有 ZLM 节点进行健康检查与负载获取，采用 Least Connections (最小连接数) 算法选择最优节点。
    支持 Failover (故障转移)，自动剔除宕机节点。
    """
    nodes = await list_db_media_nodes(db)
    if not nodes:
        return None

    try:
        result = await db.execute(
            select(MediaNode).where(MediaNode.is_embedded.is_(False) | MediaNode.is_embedded.is_(None))
        )
        db_nodes = result.scalars().all()
        if db_nodes:
            nodes = [_to_runtime(n) for n in db_nodes]
    except Exception as e:
        logger.warning(f"select_best_db_node: failed to query non-embedded nodes: {e}")

    if exclude_node_ids:
        nodes = [n for n in nodes if n.id not in exclude_node_ids]

    if not nodes:
        return None

    tasks = [_async_get_stream_count(n) for n in nodes]
    # FIX [2026-07-17 P1-E2]: 启用 return_exceptions=True，单个节点探测失败不取消其他并发任务
    results = await asyncio.gather(*tasks, return_exceptions=True)

    alive_nodes: list[tuple[RuntimeMediaNode, int, float, float, float]] = []
    for item in results:
        if not isinstance(item, tuple):
            continue
        if len(item) >= 6:
            n, count, is_alive, cpu, mem, net = item[:6]
        elif len(item) == 3:
            n, count, is_alive = item
            cpu, mem, net = 0.0, 0.0, 0.0
        else:
            continue
        if is_alive:
            alive_nodes.append((n, int(count or 0), float(cpu or 0.0), float(mem or 0.0), float(net or 0.0)))

    if not alive_nodes:
        # 外置节点全部不可达时，回退到包含内置节点的完整列表重试
        all_nodes = await list_db_media_nodes(db)
        if all_nodes:
            fallback_tasks = [_async_get_stream_count(n) for n in all_nodes]
            # FIX [2026-07-17 P1-E2]: 启用 return_exceptions=True
            fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for item in fallback_results:
                if not isinstance(item, tuple):
                    continue
                if len(item) >= 6:
                    n, count, is_alive, cpu, mem, net = item[:6]
                elif len(item) == 3:
                    n, count, is_alive = item
                    cpu, mem, net = 0.0, 0.0, 0.0
                else:
                    continue
                if is_alive:
                    alive_nodes.append((n, int(count or 0), float(cpu or 0.0), float(mem or 0.0), float(net or 0.0)))
        if not alive_nodes:
            return None

    # 按当前流数量从小到大排序 (Least Connections)
    # 如果要加入权重： 可以按 count * 1.0 + cpu * 0.5 这样计算综合 load
    # FIX R22-SEVERE: 将 in-flight 计数加入实际 count，避免突发并发全部命中同一节点
    #   - 10 路 gather 同时返回相同 count 快照，独立地都选出 alive_nodes[0][0] 同一节点
    #   - 加入 in-flight 计数后，第 2~10 路会看到第 1 路的 in-flight 标记，从而分流到其他节点
    now = time.time()
    alive_nodes.sort(key=lambda x: x[1] + _prune_inflight(x[0].id, now))
    best_node = alive_nodes[0][0]
    _add_inflight(best_node.id)

    return best_node


async def allocate_rtp_port(db: AsyncSession, node: RuntimeMediaNode) -> int:
    mode = (node.rtp_port_mode or "single").lower()
    if mode != "range":
        return int(node.rtp_port or 0)
    start = int(node.rtp_port_range_start or 0)
    end = int(node.rtp_port_range_end or 0)
    if start <= 0 or end <= 0 or end < start:
        return int(node.rtp_port or 0)
    occupied = set()
    try:
        result = await db.execute(
            select(MediaPortLease.port).where(MediaPortLease.media_server_id == node.id)
        )
        occupied = {row[0] for row in result.all() if row and row[0]}
    except Exception as e:
        logger.warning(f"Error: {e}")
    for port in range(start, end + 1):
        if port in occupied:
            continue
        try:
            async with db.begin_nested():
                lease = MediaPortLease(media_server_id=node.id, port=port)
                db.add(lease)
                await db.flush()
            return port
        except IntegrityError:
            continue
        except Exception as e:
            logger.error(f"allocate_rtp_port unexpected error for port {port}: {e}")
            raise
    return int(node.rtp_port or 0)


async def allocate_rtp_port_with_lease(
    db: AsyncSession,
    node: RuntimeMediaNode,
    start_from: int | None = None,
    exclude_ports: set[int] | None = None,
    stream_id: str | None = None,
    app_name: str | None = None,
) -> tuple[int, str | None]:
    mode = (node.rtp_port_mode or "single").lower()
    if mode != "range":
        return int(node.rtp_port or 0), None
    start = int(node.rtp_port_range_start or 0)
    end = int(node.rtp_port_range_end or 0)
    if start <= 0 or end <= 0 or end < start:
        return int(node.rtp_port or 0), None
    begin = start
    if start_from and int(start_from) > begin:
        begin = int(start_from)
    if begin > end:
        return int(node.rtp_port or 0), None
    excluded = exclude_ports or set()
    occupied = set()
    try:
        result = await db.execute(
            select(MediaPortLease.port).where(MediaPortLease.media_server_id == node.id)
        )
        occupied = {row[0] for row in result.all() if row and row[0]}
    except Exception as e:
        logger.warning(f"Error: {e}")
    # FIX R22-SEVERE: 随机起点 + 最大尝试次数限制，避免并发风暴
    # 原实现问题：
    #   - 10 路并发都从 begin 开始顺序扫描
    #   - 都先尝试 begin，9 路命中 IntegrityError；再都尝试 begin+1，又 9 路命中...
    #   - 形成"并发风暴"：10 路 × N 端口 = 10N 次 DB 写入，9/10 都是 IntegrityError
    # 修复方案：
    #   - 在 [begin, end] 范围内随机选择起始端口，10 路并发各自从不同起点开始
    #   - 顺序扫描（环形），遇到 occupied/excluded 跳过
    #   - 最大尝试次数 = 端口范围大小，避免无意义循环
    import random
    range_size = end - begin + 1
    random_offset = random.randint(0, range_size - 1) if range_size > 1 else 0
    max_attempts = range_size  # 最多尝试整个范围一次
    attempts = 0
    for i in range(range_size):
        port = begin + ((random_offset + i) % range_size)
        attempts += 1
        if attempts > max_attempts:
            break
        if port in excluded or port in occupied:
            continue
        try:
            async with db.begin_nested():
                # FIX: [2026-07-03] 存储 stream_id/app_name，用于孤儿租约清理时关闭 ZLM RTP Server [全栈工程师]
                lease = MediaPortLease(media_server_id=node.id, port=port, stream_id=stream_id, app_name=app_name)
                db.add(lease)
                await db.flush()
            return port, lease.id
        except IntegrityError:
            # 其他并发请求已占用此端口，继续尝试下一个
            continue
        except Exception as e:
            logger.error(f"allocate_rtp_port_with_lease unexpected error for port {port}: {e}")
            raise
    logger.error(f"allocate_rtp_port_with_lease: all ports in range [{begin},{end}] occupied for node {node.id}")
    return 0, None


async def cleanup_stale_leases(db: AsyncSession, max_age_seconds: int = 600, limit: int = 500) -> int:
    """
    清理"孤儿租约"：未绑定 stream_session 且超过 max_age_seconds 的租约。
    用于兜底：进程崩溃/异常导致租约创建成功但 session 未落库，端口长期被占用。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(60, int(max_age_seconds or 600)))
        # FIX: [2026-07-03] 查询租约时获取 stream_id/app_name，用于精确关闭 ZLM RTP Server [全栈工程师]
        stmt = (
            select(MediaPortLease.id, MediaPortLease.port, MediaPortLease.media_server_id, MediaPortLease.stream_id, MediaPortLease.app_name)
            .where(MediaPortLease.stream_session_id.is_(None), MediaPortLease.leased_at < cutoff)
            .limit(max(1, int(limit or 500)))
        )
        result = await db.execute(stmt)
        rows = [(row[0], row[1], row[2], row[3], row[4]) for row in result.all() if row and row[0]]
        if not rows:
            return 0
        ids = [r[0] for r in rows]
        await db.execute(delete(MediaPortLease).where(MediaPortLease.id.in_(ids)))
        await db.flush()
        # 同步关闭ZLM侧RTP Server，防止端口被二次分配冲突
        # FIX: [2026-07-03] 使用租约中存储的 stream_id/app_name 精确关闭对应的 ZLM RTP Server [全栈工程师]
        try:
            from app.services.zlm_stream_control import close_zlm_stream
            for r in rows:
                _lease_id, _port, _node_id, _stream_id, _app_name = r
                if not _node_id:
                    continue
                _close_app = _app_name or "rtp"
                _close_stream = _stream_id or ""
                try:
                    await close_zlm_stream(app=_close_app, stream=_close_stream, node_id=_node_id)
                except Exception as _zlm_err:
                    logger.warning(f"cleanup_stale_leases: failed to close ZLM stream {_close_stream} on node {_node_id}: {_zlm_err}")
        except Exception as _outer_err:
            logger.warning(f"cleanup_stale_leases: error during ZLM cleanup: {_outer_err}")
            pass
        return len(ids)
    except Exception as e:
        logger.warning(f"cleanup_stale_leases failed: {e}")
        return 0


async def cleanup_invalid_bound_leases(db: AsyncSession, limit: int = 500) -> int:
    """
    清理"已绑定但无效"的租约：
    - stream_session_id 非空，但关联的 stream_sessions 已不存在
    常见于异常删除会话/删库重建后的残留租约，导致端口池被误占满。
    """
    try:
        stmt = (
            select(MediaPortLease.id)
            .outerjoin(StreamSession, MediaPortLease.stream_session_id == StreamSession.id)
            .where(
                MediaPortLease.stream_session_id.is_not(None),
                StreamSession.id.is_(None),
            )
            .limit(max(1, int(limit or 500)))
        )
        result = await db.execute(stmt)
        ids = [row[0] for row in result.all() if row and row[0]]
        if not ids:
            return 0
        await db.execute(delete(MediaPortLease).where(MediaPortLease.id.in_(ids)))
        await db.flush()
        return len(ids)
    except Exception as e:
        logger.warning(f"cleanup_invalid_bound_leases failed: {e}")
        return 0


async def attach_lease_to_session(db: AsyncSession, node_id: str, port: int, stream_session_id: str, lease_id_hint: str | None = None) -> str | None:
    """将已创建的租约绑定到 stream_session（便于释放）。"""
    try:
        if lease_id_hint:
            result = await db.execute(select(MediaPortLease).where(MediaPortLease.id == lease_id_hint))
            lease = result.scalars().first()
        else:
            result = await db.execute(
                select(MediaPortLease).where(
                    MediaPortLease.media_server_id == node_id,
                    MediaPortLease.port == port,
                    MediaPortLease.stream_session_id.is_(None),
                )
            )
            lease = result.scalars().first()
        if not lease:
            return None
        lease.stream_session_id = stream_session_id
        await db.flush()
        return lease.id
    except Exception as e:
        logger.warning(f"attach_lease_to_session failed for node {node_id} port {port}: {e}")
        return None


async def release_lease(db: AsyncSession, lease_id: str | None) -> None:
    if not lease_id:
        return
    try:
        result = await db.execute(select(MediaPortLease).where(MediaPortLease.id == lease_id))
        lease = result.scalars().first()
        if lease:
            await db.delete(lease)
            await db.flush()
    except Exception as e:
        logger.warning(f"[MediaNodesDB] release_lease failed for lease_id={lease_id}: {e}")


async def get_cluster_status(db: AsyncSession) -> dict[str, Any]:
    """Return a summary of the media node cluster status.

    Provides total/online/offline node counts, per-node health info, and
    aggregate stream count for dashboards and the ``/cluster-status`` API.
    """
    try:
        nodes = await list_db_media_nodes(db)
    except Exception as e:
        logger.warning(f"[MediaNodesDB] get_cluster_status: failed to list nodes: {e}")
        return {"total": 0, "online": 0, "offline": 0, "nodes": []}

    node_list: list[dict[str, Any]] = []
    online_count = 0
    total_streams = 0

    for node in nodes:
        is_online = bool(node.is_online)
        if is_online:
            online_count += 1
        stream_count = int(getattr(node, "stream_count", 0) or 0)
        total_streams += stream_count
        node_list.append({
            "id": str(node.id),
            "host": str(node.host),
            "http_port": int(node.http_port or 0),
            "is_online": is_online,
            "stream_count": stream_count,
            "is_embedded": bool(getattr(node, "is_embedded", False)),
        })

    return {
        "total": len(nodes),
        "online": online_count,
        "offline": len(nodes) - online_count,
        "total_streams": total_streams,
        "nodes": node_list,
    }
