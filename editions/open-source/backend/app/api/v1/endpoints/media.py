from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.media_nodes import get_all_media_from_nodes_async
from app.core.media_nodes_db import get_all_media_from_nodes as get_all_media_from_db_nodes, list_db_media_nodes
from app.db.session import get_db
from app.models.user import User

router = APIRouter()


def _to_int(value, default=0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _pick_track(tracks: list, kind: str):
    for t in tracks:
        if not isinstance(t, dict):
            continue
        t_type = str(t.get("type") or t.get("codec_type") or "").lower()
        if kind == "video" and t_type in {"video"}:
            return t
        if kind == "audio" and t_type in {"audio"}:
            return t
    return {}


def _extract_codec_payload(item: dict) -> dict:
    tracks = item.get("tracks")
    if not isinstance(tracks, list):
        tracks = []
    video_track = _pick_track(tracks, "video")
    audio_track = _pick_track(tracks, "audio")

    width = _to_int(video_track.get("width") or item.get("width"), 0)
    height = _to_int(video_track.get("height") or item.get("height"), 0)
    resolution = f"{width}x{height}" if width > 0 and height > 0 else ""

    video_bitrate = _to_int(
        video_track.get("bit_rate")
        or video_track.get("bitrate")
        or item.get("vBitRate")
        or item.get("vbitrate"),
        0,
    )
    audio_bitrate = _to_int(
        audio_track.get("bit_rate")
        or audio_track.get("bitrate")
        or item.get("aBitRate")
        or item.get("abitrate"),
        0,
    )
    total_bitrate = _to_int(item.get("bytesSpeed"), 0) * 8
    if total_bitrate <= 0:
        total_bitrate = video_bitrate + audio_bitrate

    return {
        "videoCodec": str(video_track.get("codec") or item.get("vhost") or item.get("vcodec") or "").lower(),
        "audioCodec": str(audio_track.get("codec") or item.get("acodec") or "").lower(),
        "resolution": resolution,
        "fps": _to_int(video_track.get("fps") or item.get("fps"), 0),
        "bitrate": total_bitrate,
        "videoBitrate": video_bitrate,
        "audioBitrate": audio_bitrate,
        "sampleRate": _to_int(audio_track.get("sample_rate") or audio_track.get("sampleRate"), 0),
        "channels": _to_int(audio_track.get("channels"), 0),
        "duration": _to_int(item.get("aliveSecond"), 0),
        "bufferFrames": _to_int(item.get("readerCount"), 0),
        "readerCount": _to_int(item.get("readerCount"), 0),
        "originType": item.get("originType"),
        "originUrl": item.get("originUrl"),
        "nodeId": item.get("node_id"),
    }


@router.get("/info")
async def media_info(
    app: str,
    stream: str,
    media_server_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    查询流媒体编码与统计信息（用于通道播放页“编码信息”Tab）。
    """
    _ = current_user
    db_nodes = await list_db_media_nodes(db)
    if db_nodes:
        media_list = await get_all_media_from_db_nodes(db_nodes)
    else:
        media_list = await get_all_media_from_nodes_async()

    target = None
    for item in media_list:
        if not isinstance(item, dict):
            continue
        if str(item.get("app") or "") != str(app):
            continue
        if str(item.get("stream") or "") != str(stream):
            continue
        if media_server_id and str(item.get("node_id") or "") != str(media_server_id):
            continue
        target = item
        break

    if not target:
        return {
            "app": app,
            "stream": stream,
            "mediaServerId": media_server_id or "",
            "online": False,
        }

    payload = _extract_codec_payload(target)
    payload.update(
        {
            "app": app,
            "stream": stream,
            "mediaServerId": str(target.get("node_id") or media_server_id or ""),
            "online": True,
        }
    )
    return payload
