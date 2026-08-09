"""
实时预览流媒体优化 API 端点 - Stream Optimization Endpoints

专门优化实时预览，解决抖动、花屏问题。
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User
from app.api import deps
from app.services.stream_quality_monitor import stream_quality_monitor, StreamQualitySample
from loguru import logger

router = APIRouter()


class StreamPlayRequest(BaseModel):
    """实时预览播放请求"""
    device_id: str = Field(..., description="设备ID")
    channel_id: str = Field(..., description="通道ID")
    protocol_preference: str = Field("auto", description="协议偏好: auto, flv, hls, webrtc")
    quality_mode: str = Field("balance", description="画质模式: high, balance, stable")
    enable_tcp_fallback: bool = Field(True, description="启用TCP降级")
    preferred_line: str = Field("auto", description="线路偏好: auto, main, sub")


class StreamQualityReport(BaseModel):
    """质量上报"""
    session_id: str
    fps: float = 0
    bitrate_kbps: float = 0
    video_width: int = 0
    video_height: int = 0
    codec: str = ""
    latency_ms: float = 0
    jitter_ms: float = 0
    packet_loss_rate: float = 0
    buffer_ms: float = 0
    dropped_frames: int = 0
    error_count: int = 0


class StreamHealthResponse(BaseModel):
    """流健康状态"""
    session_id: str
    status: str
    health_score: float
    health_level: str
    fps: float
    bitrate_kbps: float
    packet_loss_rate: float
    buffer_ms: float
    resolution: str
    recommendations: list[str]


@router.get("/play/{device_id}/{channel_id}")
async def optimized_stream_play(
    device_id: str,
    channel_id: str,
    protocol_preference: str = Query("auto", description="协议偏好"),
    quality_mode: str = Query("balance", description="画质模式"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    优化的实时预览播放
    
    特性：
    - 智能协议选择（FLV > HLS > WebRTC）
    - 画质模式选择（高清/均衡/稳定）
    - 自动降级（UDP > TCP）
    - 质量监控集成
    """
    # 查询设备
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    # 查询通道
    stmt = select(Resource).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    result = await db.execute(stmt)
    resource = result.scalars().first()

    if not resource:
        raise HTTPException(status_code=404, detail="Channel not found")

    # 检查设备状态
    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")

    # 生成会话ID
    import uuid
    session_id = str(uuid.uuid4())[:16]

    # 选择最优协议
    recommended_protocol = _select_best_protocol(protocol_preference, quality_mode)

    # 创建质量监控会话
    await stream_quality_monitor.create_session(
        session_id=session_id,
        device_id=device_id,
        channel_id=channel_id,
        protocol=recommended_protocol,
        transport="TCP"  # 默认使用 TCP 更稳定
    )

    # 返回播放信息（实际播放逻辑由前端调用 play_stream API）
    return {
        "session_id": session_id,
        "device_id": device_id,
        "channel_id": channel_id,
        "recommended_protocol": recommended_protocol,
        "quality_mode": quality_mode,
        "play_url": None,  # 前端需要调用 play_stream 获取实际 URL
        "stats_url": f"/api/v1/stream-opt/health/{session_id}",
        "quality_report_url": "/api/v1/stream-opt/quality-report"
    }


@router.post("/quality-report")
async def report_stream_quality(
    report: StreamQualityReport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        sample = StreamQualitySample(
            stream_id=report.session_id,
            ssrc="",
            fps=report.fps,
            bitrate_kbps=report.bitrate_kbps,
            video_width=report.video_width,
            video_height=report.video_height,
            codec=report.codec,
            latency_ms=report.latency_ms,
            jitter_ms=report.jitter_ms,
            packet_loss_rate=report.packet_loss_rate,
            buffer_ms=report.buffer_ms,
            dropped_frames=report.dropped_frames,
            error_count=report.error_count
        )
        await stream_quality_monitor.add_sample(report.session_id, sample)
        health = await stream_quality_monitor.get_session_health(report.session_id)
        return {"received": True, "health": health}
    except Exception as e:
        logger.warning(f"质量上报处理失败: {e}")
        return {"received": True, "health": None, "warning": "质量上报已记录但处理异常"}


@router.get("/health/{session_id}")
async def get_stream_health(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取流健康状态
    
    返回：
    - 健康评分 (0-100)
    - 健康等级 (excellent/healthy/degraded/poor/critical)
    - 各项指标
    - 优化建议
    """
    health = await stream_quality_monitor.get_session_health(session_id)

    if not health:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    return StreamHealthResponse(**health)


@router.get("/lines/{device_id}/{channel_id}")
async def get_stream_lines(
    device_id: str,
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取设备可用的播放线路列表
    
    返回：
    - 线路列表（主码流、子码流）
    - 各线路的预估质量
    - 推荐线路
    """
    # 查询通道
    stmt = select(Resource).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    result = await db.execute(stmt)
    resource = result.scalars().first()

    if not resource:
        raise HTTPException(status_code=404, detail="Channel not found")

    # 获取设备信息
    stmt = select(Asset).where(Asset.id == resource.asset_id)
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    # 构建线路信息
    lines = [
        {
            "id": "main",
            "name": "主码流",
            "description": "高清画质，适合带宽充足场景",
            "estimated_bitrate": 4000,  # kbps
            "estimated_quality": "high",
            "recommended": True
        },
        {
            "id": "sub",
            "name": "子码流",
            "description": "标清画质，适合低带宽场景",
            "estimated_bitrate": 1500,  # kbps
            "estimated_quality": "medium",
            "recommended": False
        }
    ]

    # 检查设备能力
    if hasattr(asset, 'stream_mode'):
        mode = str(asset.stream_mode or '').lower()
        if mode == 'main':
            lines = [l for l in lines if l['id'] == 'main']
        elif mode == 'sub':
            lines = [l for l in lines if l['id'] == 'sub']

    # 推荐线路
    recommended = next((l for l in lines if l.get('recommended')), lines[0] if lines else None)

    return {
        "device_id": device_id,
        "channel_id": channel_id,
        "lines": lines,
        "recommended": recommended
    }


@router.post("/reconnect/{session_id}")
async def reconnect_stream(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        await stream_quality_monitor.report_reconnect(session_id)
        health = await stream_quality_monitor.get_session_health(session_id)
        return {"reconnected": True, "health": health}
    except Exception as e:
        logger.warning(f"Reconnect processing failed session={session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Reconnect processing failed: {str(e)}")


@router.delete("/session/{session_id}")
async def close_stream_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        await stream_quality_monitor.close_session(session_id)
        await stream_quality_monitor.unregister_quality_callback(session_id)
        return {"closed": True}
    except Exception as e:
        logger.warning(f"Close session failed session={session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Close session failed: {str(e)}")


@router.get("/stats")
async def get_stream_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["admin", "owner"])),
):
    """
    获取流媒体统计信息
    
    需要管理员权限
    """
    stats = stream_quality_monitor.get_stats()

    return stats


def _select_best_protocol(
    preference: str,
    quality_mode: str
) -> str:
    """
    选择最优协议
    
    协议优先级（实时预览）：
    1. HTTP-FLV：延迟低，兼容性好，推荐
    2. HLS：兼容性最好，但延迟稍高
    3. WebRTC：延迟最低，但需要 HTTPS
    """
    if preference != "auto":
        return preference

    # 根据画质模式选择
    if quality_mode == "high":
        # 高清模式：优先 FLV
        return "http_flv"
    elif quality_mode == "stable":
        # 稳定模式：优先 HLS
        return "hls"
    else:
        # 均衡模式：FLV 优先
        return "http_flv"


@router.get("/protocol-info")
async def get_protocol_info():
    """
    获取支持的协议信息
    """
    protocols = [
        {
            "id": "http_flv",
            "name": "HTTP-FLV",
            "description": "HTTP over FLV封装，延迟低(1-3s)，兼容性好，推荐",
            "latency": "低",
            "compatibility": "高",
            "quality": "无损",
            "requires_https": False,
            "buffer_recommend": "500-1000ms"
        },
        {
            "id": "hls",
            "name": "HLS",
            "description": "Apple推的流媒体协议，延迟较高(3-10s)，兼容性最好",
            "latency": "中",
            "compatibility": "极高",
            "quality": "可分段自适应",
            "requires_https": False,
            "buffer_recommend": "1000-3000ms"
        },
        {
            "id": "webrtc",
            "name": "WebRTC",
            "description": "实时通信协议，延迟极低(<1s)，但需要HTTPS环境",
            "latency": "极低",
            "compatibility": "中",
            "quality": "中等",
            "requires_https": True,
            "buffer_recommend": "200-500ms"
        }
    ]

    return {
        "protocols": protocols,
        "recommended": "http_flv",
        "recommendation": "对于大多数实时预览场景，推荐使用 HTTP-FLV 协议，延迟低且稳定"
    }


@router.get("/optimization-tips")
async def get_optimization_tips():
    """
    获取播放优化建议
    """
    tips = [
        {
            "category": "网络优化",
            "items": [
                {
                    "title": "优先使用 TCP 协议",
                    "description": "UDP 在不稳定网络下容易丢包导致花屏，TCP 有重传机制更稳定",
                    "applicable": "所有网络环境"
                },
                {
                    "title": "内网优先直连",
                    "description": "内网设备直连可获得最低延迟，避免经过公网中转",
                    "applicable": "局域网场景"
                },
                {
                    "title": "选择合适码率",
                    "description": "主码流适合带宽充足场景，子码流适合移动网络",
                    "applicable": "所有网络环境"
                }
            ]
        },
        {
            "category": "播放器优化",
            "items": [
                {
                    "title": "合理设置缓冲时间",
                    "description": "实时预览建议 500-1000ms，录像回放可更长(2-5s)",
                    "applicable": "bufferTime 参数调整"
                },
                {
                    "title": "启用自动重连",
                    "description": "网络波动时自动重连，保持观看连续性",
                    "applicable": "所有场景"
                },
                {
                    "title": "禁用低延迟模式",
                    "description": "HLS 播放器的 lowLatencyMode 会增加卡顿，点播场景建议关闭",
                    "applicable": "HLS 协议"
                }
            ]
        },
        {
            "category": "花屏解决",
            "items": [
                {
                    "title": "检查 GOP 配置",
                    "description": "设备编码器 GOP 过大会导致花屏恢复慢，建议 1-2 秒",
                    "applicable": "设备端配置"
                },
                {
                    "title": "增加关键帧间隔容忍度",
                    "description": "部分设备关键帧不标准，需要播放器有更好的容错",
                    "applicable": "播放器配置"
                },
                {
                    "title": "切换到 TCP 协议",
                    "description": "UDP 丢包是花屏主要原因，切换到 TCP 通常可以解决",
                    "applicable": "花屏问题"
                }
            ]
        }
    ]

    return {"tips": tips}
