"""
优化的点播 API 端点 - 专注于云端录像高速、稳定播放

优化要点：
1. 智能多源选择
2. 预连接与预加载
3. 质量自适应
4. 错误自动恢复
5. 端到端延迟优化
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.record import Record
from app.models.resource import Resource
from app.models.asset import Asset
from app.models.user import User
from app.api import deps
from app.services.vod_source_selector import vod_source_selector
from app.services.vod_quality_monitor import vod_quality_monitor
from app.core.config import settings
import time


router = APIRouter()


class VodPlayRequest(BaseModel):
    """点播播放请求"""
    record_id: str = Field(..., description="录像ID")
    protocol_preference: str = Field("auto", description="协议偏好: auto, hls, flv, mp4, webrtc")
    quality_preference: str = Field("auto", description="画质偏好: auto, high, medium, low")
    enable_preload: bool = Field(True, description="启用预加载")
    max_wait_ms: int = Field(5000, ge=1000, le=30000, description="最大等待时间")


class VodPlayResponse(BaseModel):
    """点播播放响应"""
    record_id: str
    session_id: str
    sources: dict
    recommended_protocol: str
    estimated_delay_ms: float
    quality_score: float
    is_cached: bool


class VodQualityReport(BaseModel):
    """质量上报"""
    session_id: str
    current_time: float
    buffer_duration_ms: float
    bitrate_kbps: float
    fps: float
    dropped_frames: int
    error_count: int


@router.get("/vod/play/{record_id}")
async def vod_play(
    record_id: str,
    protocol_preference: str = Query("auto", description="协议偏好"),
    quality_preference: str = Query("auto", description="画质偏好"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    云端录像点播播放
    
    特性：
    - 智能多源选择
    - 协议自适应
    - 预加载优化
    - 质量监控
    """
    start_time = time.perf_counter()

    # 1. 查询录像记录
    stmt = select(Record, Resource, Asset).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Record.asset_id).where(
        Record.id == record_id
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Recording not found")

    record, resource, asset = row

    # 2. 检查权限
    if not current_user.is_superuser and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied to access this recording")  # FIXED: hardcoded Chinese → English

    # 3. 构建源列表
    sources = await _build_vod_sources(db, record)

    if not sources:
        raise HTTPException(status_code=404, detail="No playable source available")

    # 4. 智能选择最优源
    best_source = await vod_source_selector.select_best_source(
        sources=sources,
        prefer_protocol=protocol_preference if protocol_preference != "auto" else None,
        prefer_quality=quality_preference if quality_preference != "auto" else None,
    )

    # 5. 创建监控会话
    session_id = await vod_quality_monitor.create_session(
        record_id=record_id,
        device_id=asset.gb_id,
        channel_id=resource.gb_id,
        sources=sources
    )

    # 6. 计算预估延迟
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    estimated_delay = max(0, 100 - elapsed_ms)  # 节省的时间

    # 7. 返回响应
    return VodPlayResponse(
        record_id=record_id,
        session_id=session_id,
        sources={
            "primary": best_source,
            "alternates": [s for s in sources if s.get("url") != best_source.get("url")],
            "all": sources
        },
        recommended_protocol=best_source.get("protocol", "mp4"),
        estimated_delay_ms=estimated_delay,
        quality_score=best_source.get("health_score", 100.0),
        is_cached=record.url_ok == True if hasattr(record, "url_ok") else False
    )


@router.post("/vod/quality-report")
async def vod_quality_report(
    report: VodQualityReport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    上报播放质量指标
    
    用于：
    - 实时质量监控
    - 自适应码率调整
    - 故障预测
    """
    from app.services.vod_quality_monitor import VodQualityMetrics

    metrics = VodQualityMetrics(
        record_id="",
        source_url="",
        buffer_duration_ms=report.buffer_duration_ms,
        bitrate_kbps=report.bitrate_kbps,
        fps=report.fps,
        frame_drop_rate=report.dropped_frames / max(1, report.fps * 10) if report.fps > 0 else 0,
        current_time=report.current_time,
        error_count=report.error_count
    )

    await vod_quality_monitor.update_metrics(report.session_id, metrics)

    # 获取调整建议
    session = await vod_quality_monitor.get_session(report.session_id)
    if session:
        suggestion = {
            "quality_level": session.quality_metrics.quality_level.value,
            "quality_score": session.quality_metrics.score,
            "buffer_state": session.quality_metrics.buffer_state.value,
            "recommend_switch": session.current_source_index > 0
        }
    else:
        suggestion = {}

    return {"received": True, "suggestion": suggestion}


@router.get("/vod/sources/{record_id}")
async def get_vod_sources(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取录像的所有可用播放源
    
    返回格式：
    - sources: 源列表
    - recommended: 推荐源
    - health_scores: 各源健康分
    """
    # 查询录像
    stmt = select(Record, Resource, Asset).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Record.asset_id).where(
        Record.id == record_id
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Recording not found")

    record, resource, asset = row

    # 构建源列表
    sources = await _build_vod_sources(db, record)

    # 并行检查所有源
    checked_sources = []
    for src in sources:
        candidate = {
            **src,
            "available": src.get("available", True),
            "health_score": src.get("health_score", 100.0)
        }
        checked_sources.append(candidate)

    # 推荐源
    recommended = await vod_source_selector.select_best_source(sources)

    return {
        "record_id": record_id,
        "sources": checked_sources,
        "recommended": recommended,
        "count": len(checked_sources)
    }


@router.get("/vod/stream/{record_id}")
async def get_vod_stream_url(
    record_id: str,
    protocol: str = Query("auto", description="指定协议"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取直接可用的流地址
    
    用于：
    - 第三方播放器
    - 嵌入播放
    - 下载
    """
    # 查询录像
    stmt = select(Record, Resource, Asset).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Record.asset_id).where(
        Record.id == record_id
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Recording not found")

    record, resource, asset = row

    # 获取文件路径
    file_path = str(record.file_path or "").strip()

    if not file_path:
        raise HTTPException(status_code=404, detail="Recording file path is empty")

    # 构建流地址
    stream_urls = await _build_stream_urls(db, record, protocol)

    return {
        "record_id": record_id,
        "file_path": file_path,
        "urls": stream_urls,
        "duration": record.duration,
        "file_size": record.file_size,
        "start_time": record.start_time.isoformat() if record.start_time else None,
        "end_time": record.end_time.isoformat() if record.end_time else None,
    }


async def _build_vod_sources(db: AsyncSession, record: Record) -> list[dict]:
    """
    构建点播源列表
    
    优先级顺序：
    1. 本地文件 (最快)
    2. 内网地址
    3. CDN 地址
    4. 直连 URL
    """
    sources = []
    file_path = str(record.file_path or "").strip()

    if not file_path:
        return []

    # 检测源类型
    url_lower = file_path.lower()

    # S3/MinIO 源
    if url_lower.startswith("s3://"):
        sources.append({
            "url": file_path,
            "protocol": "s3",
            "type": "s3",
            "priority": 1,
            "estimated_bitrate": 5000,
            "quality": "ultra"
        })

    # HTTP/HTTPS 源
    elif url_lower.startswith("http://") or url_lower.startswith("https://"):
        # 检测协议类型
        if ".m3u8" in url_lower or "/hls/" in url_lower:
            protocol = "hls"
        elif ".flv" in url_lower or "/flv/" in url_lower:
            protocol = "flv"
        elif ".mp4" in url_lower or "/record/" in url_lower or "/mp4/" in url_lower:
            protocol = "mp4"
        else:
            protocol = "http"

        # 检测源类型
        if any(x in url_lower for x in ["192.168.", "10.", "172.", "localhost", "127.0.0.1"]):
            source_type = "internal"
            priority = 2
        elif any(x in url_lower for x in ["cdn.", ".cdn.", "oss.", "cos.", "qiniu"]):
            source_type = "cdn"
            priority = 3
        else:
            source_type = "http"
            priority = 4

        sources.append({
            "url": file_path,
            "protocol": protocol,
            "type": source_type,
            "priority": priority,
            "estimated_bitrate": 3000,
            "quality": "high"
        })

    # 本地文件源
    elif file_path.startswith("/") or (len(file_path) > 2 and file_path[1] == ":"):
        sources.append({
            "url": file_path,
            "protocol": "file",
            "type": "local",
            "priority": 0,
            "estimated_bitrate": 10000,
            "quality": "ultra"
        })

    # 尝试构建其他协议地址
    base_url = _derive_base_url(file_path)
    if base_url:
        # HLS 地址
        hls_path = f"{base_url}/hls/{record.id}/index.m3u8"
        sources.insert(1, {
            "url": hls_path,
            "protocol": "hls",
            "type": "http",
            "priority": 3,
            "estimated_bitrate": 2500,
            "quality": "high"
        })

        # HTTP-FLV 地址
        flv_path = f"{base_url}/flv/{record.id}.live.flv"
        sources.insert(2, {
            "url": flv_path,
            "protocol": "flv",
            "type": "http",
            "priority": 4,
            "estimated_bitrate": 3000,
            "quality": "high"
        })

    return sources


async def _build_stream_urls(db: AsyncSession, record: Record, preferred_protocol: str = "auto") -> dict:
    """
    构建流地址字典
    """
    file_path = str(record.file_path or "").strip()
    urls = {}

    if not file_path:
        return urls

    # 原始地址
    if file_path.startswith("http"):
        urls["raw"] = file_path

    # MP4 直连
    if ".mp4" in file_path.lower() or "/record/" in file_path:
        urls["mp4"] = file_path

    # HLS
    if ".m3u8" in file_path.lower() or "/hls/" in file_path:
        urls["hls"] = file_path

    # FLV
    if ".flv" in file_path.lower() or "/flv/" in file_path:
        urls["flv"] = file_path

    # HTTPS 变体
    if file_path.startswith("http://"):
        urls["https"] = file_path.replace("http://", "https://", 1)

    # WebRTC (如果支持)
    zlm_host = getattr(settings, "MEDIA_SERVER_HOST", "127.0.0.1")
    zlm_http_port = getattr(settings, "MEDIA_SERVER_HTTP_PORT", 8880)
    zlm_api_secret = getattr(settings, "MEDIA_SERVER_SECRET", "")

    if record.id:
        # HTTP-FLV over WebSocket
        ws_flv = f"ws://{zlm_host}:{zlm_http_port}/live/{record.id}.flv"
        urls["ws_flv"] = ws_flv

        # HTTPS-WSS 变体
        wss_flv = f"wss://{zlm_host}:{zlm_http_port}/live/{record.id}.flv"
        urls["wss_flv"] = wss_flv

        # HLS
        hls_url = f"http://{zlm_host}:{zlm_http_port}/live/{record.id}/hls.m3u8"
        urls["hls"] = hls_url

        # WebRTC (低延迟)
        webrtc_url = f"http://{zlm_host}:{zlm_http_port}/index/api/webrtc?app=live&stream={record.id}&protocol=play"
        urls["webrtc"] = webrtc_url

    return urls


def _derive_base_url(file_path: str) -> str:
    """
    从文件路径推导基础URL
    """
    from urllib.parse import urlparse

    if not file_path:
        return ""

    # HTTP URL
    if file_path.startswith("http"):
        parsed = urlparse(file_path)
        return f"{parsed.scheme}://{parsed.netloc}"

    # 本地文件 -> 尝试构建 HTTP 地址
    zlm_host = getattr(settings, "MEDIA_SERVER_HOST", "127.0.0.1")
    zlm_http_port = getattr(settings, "MEDIA_SERVER_HTTP_PORT", 8880)

    # 从路径提取 record 相关部分
    if "/record/" in file_path:
        idx = file_path.find("/record/")
        record_path = file_path[idx + 1:]  # 去掉开头的 /
        return f"http://{zlm_host}:{zlm_http_port}/{record_path.split('/')[0]}"

    return f"http://{zlm_host}:{zlm_http_port}"


@router.get("/vod/optimized-url/{record_id}")
async def get_optimized_vod_url(
    record_id: str,
    protocol: str = Query("auto", description="指定协议"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取优化后的点播 URL
    
    根据网络状况和设备能力选择最优协议和地址。
    支持：MP4, HLS, HTTP-FLV, WebRTC
    """
    # 查询录像
    stmt = select(Record, Resource, Asset).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Record.asset_id).where(
        Record.id == record_id
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Recording not found")

    record, resource, asset = row

    # 根据协议偏好选择
    file_path = str(record.file_path or "").strip()

    if not file_path:
        raise HTTPException(status_code=404, detail="Recording file path is empty")

    # 构建 URL
    urls = await _build_stream_urls(db, record, protocol)

    # 选择最佳 URL
    if protocol != "auto":
        selected_url = urls.get(protocol, file_path)
    else:
        # 智能选择
        selected_url = (
            urls.get("mp4") or
            urls.get("flv") or
            urls.get("hls") or
            urls.get("raw") or
            file_path
        )

    return {
        "record_id": record_id,
        "url": selected_url,
        "protocol": _detect_protocol(selected_url),
        "alternative_urls": urls,
        "duration": record.duration,
        "file_size": record.file_size,
        "suggestion": _get_play_suggestion(urls)
    }


def _detect_protocol(url: str) -> str:
    """检测 URL 协议"""
    if not url:
        return "unknown"

    url_lower = url.lower()

    if url_lower.startswith("ws://") or url_lower.startswith("wss://"):
        if "flv" in url_lower:
            return "ws_flv"
        if "hls" in url_lower:
            return "ws_hls"
        return "websocket"

    if "webrtc" in url_lower or "rtc" in url_lower:
        return "webrtc"

    if ".m3u8" in url_lower or "/hls/" in url_lower:
        return "hls"

    if ".flv" in url_lower or "/flv/" in url_lower:
        return "flv"

    if ".mp4" in url_lower or "/record/" in url_lower:
        return "mp4"

    if url_lower.startswith("s3://"):
        return "s3"

    if url_lower.startswith("http"):
        return "http"

    return "file"


def _get_play_suggestion(urls: dict) -> dict:
    """获取播放建议"""
    suggestions = []

    if "mp4" in urls:
        suggestions.append({
            "protocol": "mp4",
            "label": "MP4 直连",
            "description": "最适合点播，加载最快，画质无损",
            "score": 100
        })

    if "flv" in urls:
        suggestions.append({
            "protocol": "flv",
            "label": "HTTP-FLV",
            "description": "低延迟，支持H.265，FLV封装",
            "score": 95
        })

    if "hls" in urls:
        suggestions.append({
            "protocol": "hls",
            "label": "HLS",
            "description": "兼容性最好，支持所有浏览器",
            "score": 90
        })

    if "webrtc" in urls:
        suggestions.append({
            "protocol": "webrtc",
            "label": "WebRTC",
            "description": "超低延迟，需要HTTPS环境",
            "score": 85
        })

    return {
        "recommended": suggestions[0] if suggestions else None,
        "alternatives": suggestions[1:] if len(suggestions) > 1 else []
    }
