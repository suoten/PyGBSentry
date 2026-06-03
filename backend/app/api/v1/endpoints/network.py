"""网络管理：流量/带宽/拓扑与流媒体概况。"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.db.session import get_db
from app.models.asset import Asset
from app.models.stream_session import StreamSession
from app.models.network_metric import NetworkMetric
from app.models.media_node import MediaNode
from app.models.platform import ParentPlatform
from app.models.user import User
from app.api import deps
from app.core.config import settings
from app.core.http_client import get_http_client
from loguru import logger

router = APIRouter()


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception as e:
        logger.debug(f"操作失败,返回默认值: {e}")
        return default


def _calc_zlm_bandwidth_mbps(media_list: list[dict]) -> float:
    total_bytes_per_sec = 0.0
    for item in media_list:
        if not isinstance(item, dict):
            continue
        bytes_speed = _safe_float(item.get("bytesSpeed"), 0.0)
        if bytes_speed <= 0:
            bytes_speed = _safe_float(item.get("bytes_speed"), 0.0)
        if bytes_speed <= 0:
            bytes_speed = _safe_float(item.get("speed"), 0.0)
        total_bytes_per_sec += max(bytes_speed, 0.0)
    if total_bytes_per_sec <= 0:
        return 0.0
    return (total_bytes_per_sec * 8.0) / 1_000_000.0


@router.get("/summary")
async def network_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """网络/流媒体概况：在线设备数、当前流数、可选 ZLM 统计。"""
    # W-11 network_summary使用COUNT聚合查询替代全量加载，避免OOM
    tenant_filter = (current_user.tenant_id or "default") if not current_user.is_superuser else None

    device_total_stmt = select(func.count(Asset.id))
    if tenant_filter:
        device_total_stmt = device_total_stmt.where(Asset.tenant_id == tenant_filter)
    device_total = (await db.execute(device_total_stmt)).scalar() or 0

    device_online_stmt = select(func.count(Asset.id)).where(Asset.status == 1)
    if tenant_filter:
        device_online_stmt = device_online_stmt.where(Asset.tenant_id == tenant_filter)
    device_online = (await db.execute(device_online_stmt)).scalar() or 0

    stream_count_stmt = select(func.count(StreamSession.id))
    if tenant_filter:
        stream_count_stmt = (
            select(func.count(StreamSession.id))
            .select_from(StreamSession)
            .join(Asset, StreamSession.asset_id == Asset.id)
            .where(Asset.tenant_id == tenant_filter)
        )
    stream_count = (await db.execute(stream_count_stmt)).scalar() or 0
    stream_count_zlm = stream_count
    zlm_bandwidth_mbps = 0.0
    try:
        url = f"http://{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}/index/api/getMediaList"
        r = await (await get_http_client()).get(url, params={"secret": settings.MEDIA_SERVER_SECRET}, timeout=2)  # 同步requests→异步httpx，避免阻塞事件循环
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                media_list = data.get("data", [])
                stream_count_zlm = len(media_list)
                zlm_bandwidth_mbps = _calc_zlm_bandwidth_mbps(media_list)
    except Exception as e:
        logger.debug(f"非关键操作失败: {e}")
    return {
        "device_total": device_total,
        "device_online": device_online,
        "stream_count": stream_count,
        "stream_count_zlm": stream_count_zlm,
        "zlm_bandwidth_mbps": round(zlm_bandwidth_mbps, 3),
        "description": "网络拓扑、活跃流趋势与ZLM实时带宽已联动展示。",
    }


@router.get("/topology")
async def network_topology(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    网络拓扑数据：
    - 核心平台节点
    - 媒体服务器节点 (MediaNode)
    - 上级级联平台 (ParentPlatform)
    - 下级租户节点 (Tenant Aggregation)
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # 1. Core Platform Node
    platform_id = "platform"
    nodes.append({
        "id": platform_id,
        "type": "platform",
        "label": settings.PROJECT_NAME or "PyGBSentry",
        "status": "online"
    })

    # 2. Media Server Nodes
    stmt_media = select(MediaNode)
    media_nodes = (await db.execute(stmt_media)).scalars().all()

    # If no media nodes in DB, check settings for default one
    if not media_nodes and settings.MEDIA_SERVER_HOST:
        # Default single node from settings
        media_id = "media_default"
        nodes.append({
            "id": media_id,
            "type": "media_server",
            "label": f"{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}",
            "status": "online" # Assumed online if not checked
        })
        edges.append({
            "source": platform_id,
            "target": media_id,
            "type": "control"
        })
    else:
        for mn in media_nodes:
            nodes.append({
                "id": mn.id,
                "type": "media_server",
                "label": f"{mn.ip}:{mn.http_port}",
                "status": "online" if mn.is_online else "offline"
            })
            edges.append({
                "source": platform_id,
                "target": mn.id,
                "type": "control"
            })

    # 3. Cascade Parent Platforms (Upstream)
    if current_user.is_superuser:
        stmt_platforms = select(ParentPlatform)
        platforms = (await db.execute(stmt_platforms)).scalars().all()
        for p in platforms:
            nodes.append({
                "id": p.id,
                "type": "cascade_platform",
                "label": p.name,
                "status": "online" if p.is_online else "offline"
            })
            # Upstream means Platform -> Parent
            edges.append({
                "source": platform_id,
                "target": p.id,
                "type": "cascade_up"
            })

    # 4. Tenant Nodes (Downstream Devices)
    stmt = select(
        Asset.tenant_id,
        func.count(Asset.id),
        func.sum(case((Asset.status == 1, 1), else_=0)),
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    stmt = stmt.group_by(Asset.tenant_id)
    result = await db.execute(stmt)
    tenant_rows = result.all()

    for tenant_id, total_count, online_sum in tenant_rows:
        tid = tenant_id or "default"
        node_id = f"tenant_{tid}"
        nodes.append({
            "id": node_id,
            "type": "tenant",
            "label": f"租户 {tid}",
            "metrics": {
                "device_total": int(total_count or 0),
                "device_online": int(online_sum or 0),
            },
        })
        edges.append({
            "source": platform_id,
            "target": node_id,
            "type": "tenant_link"
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bandwidth")
async def network_bandwidth(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    range: str = "1h",
):
    """
    带宽/流量监控：
    - 当前活跃流数量
    - 估算带宽 (Mbps)
    - 支持 range=1h|24h 返回近一段时间的历史序列（按分钟粒度近似）
    """
    # 计算当前活跃流
    stmt = select(func.count(StreamSession.id))
    if not current_user.is_superuser:
        stmt = (
            select(func.count(StreamSession.id))
            .select_from(StreamSession)
            .join(Asset, StreamSession.asset_id == Asset.id)
            .where(Asset.tenant_id == (current_user.tenant_id or "default"))
        )
    active_streams = (await db.execute(stmt)).scalar() or 0

    estimated_mbps = active_streams * 2.0
    zlm_bandwidth_mbps = 0.0
    try:
        url = f"http://{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}/index/api/getMediaList"
        r = await (await get_http_client()).get(url, params={"secret": settings.MEDIA_SERVER_SECRET}, timeout=2)  # 同步requests→异步httpx，避免阻塞事件循环
        if r.status_code == 200 and r.json().get("code") == 0:
            zlm_bandwidth_mbps = _calc_zlm_bandwidth_mbps(r.json().get("data", []))
    except Exception as e:
        logger.debug(f"操作失败,返回默认值: {e}")
        zlm_bandwidth_mbps = 0.0
    zlm_bandwidth_kbps = int(round(zlm_bandwidth_mbps * 1000))

    # 写入当前点到历史表
    try:
        tenant = current_user.tenant_id or "default"
        db.add(NetworkMetric(tenant_id=tenant, metric="active_streams", value=int(active_streams)))
        db.add(NetworkMetric(tenant_id=tenant, metric="zlm_bandwidth_kbps", value=zlm_bandwidth_kbps))
        await db.commit()
    except Exception:
        # 历史写入失败不影响接口返回
        await db.rollback()

    # 解析时间范围
    now = datetime.now(timezone.utc)
    if range not in ("1h", "24h"):
        raise HTTPException(status_code=400, detail="range only supports 1h or 24h")
    delta = timedelta(hours=1) if range == "1h" else timedelta(hours=24)
    start_time = now - delta

    # 查询历史序列
    conditions = [NetworkMetric.metric.in_(["active_streams", "zlm_bandwidth_kbps"]), NetworkMetric.created_at >= start_time]
    if not current_user.is_superuser:
        conditions.append(NetworkMetric.tenant_id == (current_user.tenant_id or "default"))

    stmt_hist = (
        select(NetworkMetric)
        .where(*conditions)
        .order_by(NetworkMetric.created_at.asc())
    )
    result = await db.execute(stmt_hist)
    rows = result.scalars().all()

    points_streams = []
    points_bandwidth = []
    for row in rows:
        point = {
            "t": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
            "value": int(row.value),
        }
        if row.metric == "active_streams":
            points_streams.append(point)
        elif row.metric == "zlm_bandwidth_kbps":
            points_bandwidth.append(
                {
                    "t": point["t"],
                    "value": round(int(row.value) / 1000.0, 3),
                }
            )

    now_iso = now.isoformat()
    if not points_streams:
        points_streams.append({"t": now_iso, "value": int(active_streams)})
    if not points_bandwidth:
        points_bandwidth.append({"t": now_iso, "value": float(zlm_bandwidth_mbps)})

    return {
        "series": [
            {
                "name": "active_streams",
                "unit": "count",
                "points": points_streams,
            },
            {
                "name": "estimated_bandwidth",
                "unit": "Mbps",
                "points": [
                    {
                        "t": now_iso,
                        "value": float(estimated_mbps),
                    }
                ],
            },
            {
                "name": "zlm_bandwidth",
                "unit": "Mbps",
                "points": points_bandwidth,
            }
        ],
        "generated_at": now_iso,
    }
