import asyncio
from loguru import logger
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from app.sip.invite import sip_invite

# FIXED-P2: S-13 保存prefetch task引用，以便回放停止时取消
_prefetch_tasks: dict[str, asyncio.Task] = {}



async def _prefetch_worker(
    asset_id: str,
    resource_id: str,
    start_time: int,
    end_time: int,
    used_target: tuple,
    stream_id: str,
    tenant_id: str
):
    """
    后台任务：监控当前回放会话。
    由于录像通常有物理文件分段（如每小时一个），跨文件播放时摄像机会发送 BYE 断流。
    我们在预测物理文件即将结束前 10 秒，提前向摄像机发起针对下一个时间段的 SIP INVITE，
    使用相同的目标端口和 SSRC，实现“无缝预加载拼接”。
    """
    logger.info(f"[Timeline] Started prefetch task for {stream_id} range {start_time}-{end_time}")
    try:
        # 这里假设录像文件的最大物理分段为 1 小时 (3600秒)
        # 如果播放时间超过 1 小时，我们将时间轴切分为多个 1 小时的片段
        segment_duration = 3600
        current_start = start_time

        while current_start + segment_duration < end_time:
            # 等待当前片段播放到倒数 10 秒
            # （注意：如果是 4 倍速播放，等待时间应缩短，此处为简化版实现，按 1 倍速计算）
            wait_time = segment_duration - 10
            await asyncio.sleep(wait_time)

            async with AsyncSessionLocal() as db:
                # 检查会话是否仍然存活
                stmt = select(StreamSession).where(StreamSession.stream == stream_id, StreamSession.app == "playback")
                ss = (await db.execute(stmt)).scalars().first()
                if not ss:
                    logger.info(f"[Timeline] Session {stream_id} stopped. Pre-fetching aborted.")
                    break

                asset = (await db.execute(select(Asset).where(Asset.id == asset_id))).scalars().first()
                resource = (await db.execute(select(Resource).where(Resource.id == resource_id))).scalars().first()
                if not asset or not resource:
                    break

                next_start = current_start + segment_duration
                next_end = min(next_start + segment_duration, end_time)

                logger.info(f"[Timeline] Pre-fetching next segment: {next_start}-{next_end} for {stream_id}")

                # 发起预加载 INVITE
                try:
                    target_ip, target_port, transport_proto = used_target
                    from app.sip.server import sip_server
                    transport = sip_server.get_transport(target_ip, target_port, transport_proto)
                    if transport:
                        # 复用同一个 ZLM 端口和 SSRC 进行预加载，在内存中完成 RTP 流拼接
                        await sip_invite.send_playback_invite(
                            asset, resource, ((target_ip, target_port), transport_proto, transport),
                            next_start, next_end, media_mode_override=None,
                            reuse_stream_session_id=ss.id
                        )
                        logger.info(f"[Timeline] Pre-fetched segment successfully. Seamless transition to {next_start}.")
                except Exception as e:
                    logger.warning(f"[Timeline] Pre-fetch INVITE failed: {e}")

            current_start += segment_duration

    except asyncio.CancelledError:
        logger.info(f"[Timeline] Pre-fetch task for {stream_id} cancelled.")
    except Exception as e:
        logger.error(f"[Timeline] Error in prefetch task: {e}")

def start_prefetch_task(
    asset_id: str,
    resource_id: str,
    start_time: int,
    end_time: int,
    used_target: tuple,
    stream_id: str,
    tenant_id: str
):
    # FIXED-P2: S-13 保存task引用，以便回放停止时取消
    task = asyncio.create_task(_prefetch_worker(asset_id, resource_id, start_time, end_time, used_target, stream_id, tenant_id))
    _prefetch_tasks[stream_id] = task
    task.add_done_callback(lambda t: _prefetch_tasks.pop(stream_id, None))


def cancel_prefetch_task(stream_id: str):
    # FIXED-P2: S-13 取消指定stream_id的预加载任务
    task = _prefetch_tasks.pop(stream_id, None)
    if task and not task.done():
        task.cancel()
