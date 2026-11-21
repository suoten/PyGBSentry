"""按通道流量账单采样任务(ROADMAP Phase3:流量账单统计)。

周期(默认 60s)聚合 ZLM ``getMediaList`` 的每路流 ``bytesSpeed``(字节/秒),
按采样间隔折算增量字节,累计进 ``traffic_daily`` 汇总表:

    * 流名 → 通道映射:GB 点播流名 ``{channel_id}_{ssrc}`` 提取通道前缀
      (与 recording_guard 同规则:后缀必须纯数字);无法映射的流按 ZLM 原始
      流名记账(resource_id 为空),不丢数据;
    * 日期键用 UTC 当天(跨零点自然切日);
    * 每轮批量预查通道归属(Resource/Asset),避免 N+1;
    * upsert 语义:先查现有行(total_bytes 累加 / peak 取 max),无则插入——
      唯一键 (tenant_id, channel_gb_id, day) 兜底并发。

多节点:聚合的是全部节点(ENV + DB)的 mediaList,单节点部署行为一致。
"""

import asyncio
import datetime

from loguru import logger
from sqlalchemy import select

from app.core.config import settings

_task: asyncio.Task | None = None


def _channel_prefix(stream_name: str) -> str:
    """提取流名对应的通道标识(与 recording_guard 匹配规则一致)。

    GB 点播流名 ``{channel_id}_{ssrc}`` → 通道前缀;其余原样返回。
    """
    s = str(stream_name or "").strip()
    if "_" in s:
        ch, rest = s.rsplit("_", 1)
        if ch and rest.isdigit():
            return ch
    return s


def _today_utc() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


async def _sample_media_items() -> list[dict]:
    """聚合 ENV + DB 节点的 getMediaList,仅保留有正向 bytesSpeed 的流。"""
    from app.db.session import AsyncSessionLocal

    items: list[dict] = []
    try:
        from app.core.media_nodes import get_all_media_from_nodes_async

        for it in await get_all_media_from_nodes_async() or []:
            if isinstance(it, dict) and it.get("bytesSpeed") is not None:
                items.append(it)
    except Exception as e:
        logger.debug(f"[TrafficMeter] ENV node enumeration failed: {e}")
    try:
        from app.core.media_nodes_db import get_all_media_from_nodes as _db_media_list, list_db_media_nodes

        async with AsyncSessionLocal() as db:
            db_nodes = await list_db_media_nodes(db)
        if db_nodes:
            for it in await _db_media_list(db_nodes) or []:
                if isinstance(it, dict) and it.get("bytesSpeed") is not None:
                    items.append(it)
    except Exception as e:
        logger.debug(f"[TrafficMeter] DB node enumeration failed: {e}")
    return items


async def _accumulate(items: list[dict], interval_seconds: int) -> int:
    """把本轮采样折算为增量并累计进 traffic_daily。返回更新的行数。"""
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from app.models.resource import Resource
    from app.models.traffic_daily import TrafficDaily
    from sqlalchemy import or_

    now = datetime.datetime.now(datetime.timezone.utc)
    day = _today_utc()

    # 流名 → 采样速率:同通道多路流(如 live+playback 并存)按原始流名分别记账
    samples: dict[tuple[str, str], int] = {}  # (stream_name, channel_prefix) -> speed
    for it in items:
        try:
            speed = int(it.get("bytesSpeed") or 0)
        except (TypeError, ValueError):
            continue
        if speed <= 0:
            continue
        stream_name = str(it.get("stream") or "")
        if not stream_name:
            continue
        samples[(stream_name, _channel_prefix(stream_name))] = speed

    if not samples:
        return 0

    prefixes = sorted({p for (_sn, p) in samples})
    async with AsyncSessionLocal() as db:
        # 批量预查通道归属(tenant/resource/asset)
        res_rows = (
            (await db.execute(select(Resource.id, Resource.gb_id, Resource.tenant_id, Resource.asset_id).where(Resource.gb_id.in_(prefixes)))).all()
        )
        res_by_gb = {str(gb): (str(rid), str(t or "default"), str(a) if a else None) for rid, gb, t, a in res_rows}
        asset_names: dict[str, str] = {}
        asset_ids = {a for (_rid, _t, a) in res_by_gb.values() if a}
        if asset_ids:
            for aid, gb in (await db.execute(select(Asset.id, Asset.gb_id).where(Asset.id.in_(asset_ids)))).all():
                asset_names[str(aid)] = str(gb or "")

        touched = 0
        seen_keys: set[tuple[str, str, datetime.date]] = set()
        for (stream_name, prefix), speed in samples.items():
            delta = int(speed * interval_seconds)
            rid, tenant, asset_id = res_by_gb.get(prefix, (None, "default", None))
            channel_key = prefix if prefix in res_by_gb else stream_name  # 未映射流按 ZLM 流名记账
            key = (tenant, channel_key, day)
            if key in seen_keys:
                # 同通道同日多路流(罕见)合并进同一行
                pass
            seen_keys.add(key)

            row = (
                # 注意:await 的操作数是完整属性链,必须显式括号包住 execute 调用,
                # 否则 .scalars()/.first() 会被解析进 await 表达式(对 coroutine 取属性)
                (await db.execute(
                    select(TrafficDaily).where(
                        TrafficDaily.tenant_id == tenant,
                        TrafficDaily.channel_gb_id == channel_key,
                        TrafficDaily.day == day,
                    )
                ))
                .scalars()
                .first()
            )
            if row is None:
                row = TrafficDaily(
                    tenant_id=tenant,
                    channel_gb_id=channel_key,
                    resource_id=rid,
                    asset_id=asset_id,
                    day=day,
                    total_bytes=delta,
                    peak_bps=speed,
                )
                db.add(row)
            else:
                row.total_bytes = int(row.total_bytes or 0) + delta
                if speed > int(row.peak_bps or 0):
                    row.peak_bps = speed
            touched += 1
        await db.commit()
    return touched


async def _run_loop() -> None:
    interval = max(10, int(settings.TRAFFIC_METER_INTERVAL_SECONDS))
    while True:
        if not settings.TRAFFIC_METER_ENABLED:
            await asyncio.sleep(interval)
            continue
        try:
            items = await _sample_media_items()
            touched = await _accumulate(items, interval)
            if items:
                logger.debug(f"[TrafficMeter] sampled {len(items)} stream(s), updated {touched} row(s)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[TrafficMeter] sample pass failed: {e}")
        await asyncio.sleep(interval)


async def start() -> None:
    global _task
    if _task and not _task.done():
        return
    if not settings.TRAFFIC_METER_ENABLED:
        logger.info("[TrafficMeter] disabled by config, not started")
        return
    _task = asyncio.create_task(_run_loop())
    logger.info("[TrafficMeter] per-channel traffic metering started")


async def stop() -> None:
    global _task
    if not _task:
        return
    _task.cancel()
    try:
        await asyncio.wait_for(_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        logger.warning("[TrafficMeter] stop cancelled/timeout")
    except Exception as e:
        logger.warning(f"[TrafficMeter] stop error: {e}")
    _task = None
