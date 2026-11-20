"""录制相关的流名匹配与录制中守卫辅助。

FIX [2026-11-20 P1]:GB 点播在 ZLM 的流名是 ``{channel_id}_{ssrc}``
（invite.py:2320-2323，live 与 playback 同规则），而录制计划执行器/自动录制/
手动强制录制此前一律用 ``Resource.gb_id`` 去匹配 ``getMediaList`` 与调用
``startRecord/stopRecord/isRecording`` —— 永远匹配不到、永远打不到真实流。

这里提供统一的:
    * :func:`channel_stream_matches` —— 流名是否属于某通道（全等或 {gb_id}_{ssrc} 前缀）
    * :func:`find_channel_live_stream` —— 解析通道当前在 ZLM 上的真实流名
    * :func:`recording_channel_prefixes` / :func:`is_stream_recording`
      —— H4 守卫:无人观看断流(hook)与空闲流回收(stream_idle)豁免正在录制计划内的流，
      避免"观众退出 → 断流 → MP4 提前收尾"（wvp #1943/#1744 短文件同款）。
"""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import select

STREAM_LIVE_APP = "live"


def channel_stream_matches(stream_name: str, channel_gb_id: str) -> bool:
    """ZLM 流名是否属于该通道：全等，或 GB 点播命名 ``{gb_id}_{ssrc}`` 形态。

    前缀匹配要求下划线后的剩余部分为纯数字（SSRC），避免 ``cam`` 误匹配
    ``cam_1_push`` 这类下划线命名的非 GB 流。
    """
    s = str(stream_name or "").strip()
    g = str(channel_gb_id or "").strip()
    if not s or not g:
        return False
    if s == g:
        return True
    if not s.startswith(g + "_"):
        return False
    return s[len(g) + 1 :].isdigit()


async def find_channel_live_stream(channel_gb_id: str) -> str | None:
    """解析通道当前在 ZLM(app=live)上的真实流名;无在线流返回 None。"""
    if not channel_gb_id:
        return None
    try:
        from app.core.media_nodes import get_all_media_from_nodes

        media = await asyncio.to_thread(get_all_media_from_nodes)
    except Exception as e:
        logger.debug(f"[RecordingGuard] getMediaList failed: {e}")
        return None
    for item in media or []:
        try:
            if str(item.get("app") or "") != STREAM_LIVE_APP:
                continue
            s = str(item.get("stream") or "")
            if channel_stream_matches(s, channel_gb_id):
                return s
        except Exception:
            continue
    return None


async def recording_channel_prefixes() -> set[str]:
    """当前处于录制计划内的通道 gb_id 集合(desired_recording 或 is_recording 任一为真)。"""
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.record_schedule_runtime import RecordScheduleRuntime
        from app.models.resource import Resource

        async with AsyncSessionLocal() as session:
            resource_ids = (
                (
                    await session.execute(
                        select(RecordScheduleRuntime.resource_id).where(
                            (RecordScheduleRuntime.is_recording == True)  # noqa: E712
                            | (RecordScheduleRuntime.desired_recording == True)  # noqa: E712
                        )
                    )
                )
                .scalars()
                .all()
            )
            ids = [r for r in resource_ids if r]
            if not ids:
                return set()
            gids = (
                (await session.execute(select(Resource.gb_id).where(Resource.id.in_(ids)))).scalars().all()
            )
        return {str(g).strip() for g in gids if g}
    except Exception as e:
        logger.debug(f"[RecordingGuard] recording prefixes query failed: {e}")
        return set()


async def is_stream_recording(app: str, stream: str) -> bool:
    """该 ZLM 流是否属于录制计划执行中的通道(供 hook/stream_idle 豁免判断)。"""
    if str(app or "") != STREAM_LIVE_APP or not stream:
        return False
    prefixes = await recording_channel_prefixes()
    if not prefixes:
        return False
    return any(channel_stream_matches(stream, p) for p in prefixes)
