from __future__ import annotations
from loguru import logger

import asyncio
from dataclasses import dataclass
from app.services.zlm_stream_control import _get_zlm_client
from typing import Any

from datetime import datetime, timedelta, timezone
import socket
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.media_node import MediaNode

from app.models.platform import ParentPlatform
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
        or (getattr(settings, "STREAM_PUBLIC_HOST", "") or "").strip()
        or (node.ip or "").strip()
    )
    if not public_host:
        public_host = node.ip
    public_http_port = int(getattr(settings, "STREAM_PUBLIC_HTTP_PORT", 0) or 0) or int(node.http_port or 0)
    # secret 为空时回退全局密钥，避免 getMediaList?secret= 刷屏与探测失败
    node_secret = (str(node.secret or "").strip() or str(getattr(settings, "MEDIA_SERVER_SECRET", "") or "").strip())
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
    except Exception:
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
                logger.debug(f"socket close error: {e}")
    except Exception:
        return None
    return None


async def _detect_public_ip() -> str | None:
    if not bool(getattr(settings, "AUTO_DETECT_PUBLIC_IP", False)):
        return None
    url = str(getattr(settings, "PUBLIC_IP_LOOKUP_URL", "") or "").strip()
    if not url:
        return None
    timeout_s = float(getattr(settings, "PUBLIC_IP_LOOKUP_TIMEOUT_SECONDS", 2.0) or 2.0)
    try:
        client = await _get_zlm_client()
        r = await client.get(url, timeout=timeout_s)
        if r.status_code >= 400:
            return None
        ip = (r.text or "").strip()
        if ip and not _is_local_host(ip):
            return ip
    except Exception:
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
            getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT_RANGE", "")
        )
        # 计算更合理的“对外可达地址”默认值：优先 STREAM_PUBLIC_HOST，其次 BACKEND_PUBLIC_HOST；
        # 若仍是 localhost/127.0.0.1，则不写入（留给用户在运维中心手工填）。
        # W-19 MEDIA_SERVER_HOST回退值改为空字符串，非本地部署时显式报错
        media_host = str(getattr(settings, "MEDIA_SERVER_HOST", "") or "").strip()
        # 强制使用环境配置里的 IP，如果它是 127.0.0.1 则让 ZLM 无法正确把 hook 连上来（或者它就是本地调试用）
        # 这里移除自动探测局域网 IP，保证和 .env 里的一致，或者确保不污染 DB
        stream_public = str(getattr(settings, "STREAM_PUBLIC_HOST", "") or "").strip()
        backend_public = str(getattr(settings, "BACKEND_PUBLIC_HOST", "") or "").strip()
        preferred_public = stream_public or backend_public
        if preferred_public.lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
            preferred_public = ""
        if not preferred_public:
            preferred_public = (await _detect_public_ip()) or ""
        preferred_public = preferred_public or None
        backend_public_port = int(getattr(settings, "BACKEND_PUBLIC_PORT", 8000) or 8000)
        api_v1_str = str(getattr(settings, "API_V1_STR", "/api/v1") or "/api/v1")
        force_single = bool(getattr(settings, "FORCE_SINGLE_PORT_MULTIPLEXING", True))

        if existed:
            changed = False
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
            global_hook_base = str(getattr(settings, "MEDIA_SERVER_HOOK_BASE_URL", "") or "").strip()
            if global_hook_base:
                if current_hook_base != global_hook_base:
                    existed.hook_base_url = global_hook_base
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
            http_port=int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 8880) or 8880),
            rtsp_port=int(getattr(settings, "MEDIA_SERVER_RTSP_PORT", 554) or 554),
            rtmp_port=int(getattr(settings, "MEDIA_SERVER_RTMP_PORT", 1935) or 1935),
            rtp_proxy_port=int(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT", 30000) or 30000),
            rtp_port_mode=range_mode,
            rtp_port_range_start=int(range_start),
            rtp_port_range_end=int(range_end),
            secret=str(getattr(settings, "MEDIA_SERVER_SECRET", "") or ""),
            is_embedded=True,
            # 内置节点默认允许自动下发配置（由 media_manager 生成 config.ini）
            auto_config_enabled=True,
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)
        return node.id
    except Exception:
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
            r = await client.get(url, params={"secret": node.secret}, timeout=2.0)
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

    results = await asyncio.gather(*[_fetch(n) for n in nodes])
    for batch in results:
        out.extend(batch)
    return out


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
        r_list = await client.get(url_list, params={"secret": node.secret}, timeout=2.0)
        if r_list.status_code < 400:
            data = r_list.json()
            if data.get("code") in (0, "0"):
                media_list = data.get("data")
                count = len(media_list) if isinstance(media_list, list) else 0
                is_alive = True
        
        if is_alive:
            try:
                r_sys = await client.get(url_sys, params={"secret": node.secret}, timeout=2.0)
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
                logger.debug(f"getStatistic failed for node {node.id} ({node.host}:{node.http_port}): {e}")

        return node, count, is_alive, cpu, mem, net_mbps
    except Exception:
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
        logger.debug(f"select_best_db_node: failed to query non-embedded nodes: {e}")

    if exclude_node_ids:
        nodes = [n for n in nodes if n.id not in exclude_node_ids]

    if not nodes:
        return None

    tasks = [_async_get_stream_count(n) for n in nodes]
    results = await asyncio.gather(*tasks)
    
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
            fallback_results = await asyncio.gather(*fallback_tasks)
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
    alive_nodes.sort(key=lambda x: x[1])
    best_node = alive_nodes[0][0]
    
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
    for port in range(begin, end + 1):
        if port in excluded or port in occupied:
            continue
        try:
            async with db.begin_nested():
                lease = MediaPortLease(media_server_id=node.id, port=port)
                db.add(lease)
                await db.flush()
            return port, lease.id
        except IntegrityError:
            continue
        except Exception as e:
            logger.error(f"allocate_rtp_port_with_lease unexpected error for port {port}: {e}")
            raise
    logger.error(f"allocate_rtp_port_with_lease: all ports in range [{begin},{end}] occupied for node {node.id}")
    return 0, None


async def cleanup_stale_leases(db: AsyncSession, max_age_seconds: int = 600, limit: int = 500) -> int:
    """
    清理“孤儿租约”：未绑定 stream_session 且超过 max_age_seconds 的租约。
    用于兜底：进程崩溃/异常导致租约创建成功但 session 未落库，端口长期被占用。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(60, int(max_age_seconds or 600)))
        # 查询租约时同时获取关联的媒体节点信息，用于关闭ZLM RTP Server
        stmt = (
            select(MediaPortLease.id, MediaPortLease.port, MediaPortLease.media_node_id)
            .where(MediaPortLease.stream_session_id.is_(None), MediaPortLease.leased_at < cutoff)
            .limit(max(1, int(limit or 500)))
        )
        result = await db.execute(stmt)
        rows = [(row[0], row[1], row[2]) for row in result.all() if row and row[0]]
        if not rows:
            return 0
        ids = [r[0] for r in rows]
        await db.execute(delete(MediaPortLease).where(MediaPortLease.id.in_(ids)))
        await db.flush()
        # 同步关闭ZLM侧RTP Server，防止端口被二次分配冲突
        try:
            from app.services.zlm_stream_control import close_zlm_stream
            node_ids = set(r[2] for r in rows if r[2])
            for _nid in node_ids:
                try:
                    await close_zlm_stream(app="rtp", stream="", node_id=_nid)
                except Exception as _zlm_err:
                    logger.debug(f"cleanup_stale_leases: failed to close ZLM stream on node {_nid}: {_zlm_err}")
        except Exception as _outer_err:
            logger.warning(f"cleanup_stale_leases: error during ZLM cleanup: {_outer_err}")
            pass
        return len(ids)
    except Exception:
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
    except Exception:
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
    except Exception:
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