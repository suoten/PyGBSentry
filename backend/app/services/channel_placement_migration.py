"""通道挂载位置拆分迁移（一次性）。

历史 schema 曾将「行政区域父级」与「通道父级」合并写入 ``resources.parent_gb_id``。
新 schema 拆分为两个字段：

- ``parent_gb_id``：通道父级国标 ID（20 位 GB28181 编码，指向另一个通道/设备）
- ``region_parent_gb_id``：行政区域父级编码（行政区划 code，6~12 位数字）

本迁移扫描所有 ``node_type='channel'`` 的 Resource，若 ``region_parent_gb_id`` 为空
而 ``parent_gb_id`` 中存放的并非 20 位国标 ID（即疑似行政区域编码），则将其搬迁到
``region_parent_gb_id`` 并清空 ``parent_gb_id``。

幂等：仅当 ``region_parent_gb_id`` 为空时处理，迁移后该字段被填充，再次运行不会
重复处理。永不抛异常。
"""
from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource import Resource

# GB28181 通道/设备国标 ID 为 20 位数字；行政区域编码通常 6~12 位数字。
_GB_ID_20_RE = re.compile(r"^\d{20}$")


async def ensure_split_channel_region_parents(db: AsyncSession) -> int:
    """拆分通道的 region_parent_gb_id / parent_gb_id 字段。

    返回被更新的行数。幂等、永不抛异常。
    """
    try:
        # 查找需要迁移的行：channel 节点，region_parent_gb_id 为空，
        # parent_gb_id 非空且不是 20 位国标 ID（疑似行政区域编码）。
        stmt = select(Resource).where(
            Resource.node_type == "channel",
            (Resource.region_parent_gb_id.is_(None))
            | (Resource.region_parent_gb_id == ""),
            Resource.parent_gb_id.isnot(None),
            Resource.parent_gb_id != "",
        )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            logger.info("channel_placement_migration: no-op (already applied / nothing to migrate)")
            return 0

        updated = 0
        for res in rows:
            parent_gb = str(res.parent_gb_id or "").strip()
            if not parent_gb:
                continue
            # 20 位国标 ID 视为合法的通道父级，不迁移
            if _GB_ID_20_RE.match(parent_gb):
                continue
            # 否则视为行政区域编码，搬迁到 region_parent_gb_id
            res.region_parent_gb_id = parent_gb
            res.parent_gb_id = None
            updated += 1

        if updated:
            await db.commit()
        logger.info("channel_placement_migration: split {} channel region parents", updated)
        return updated
    except Exception as e:
        logger.warning("channel_placement_migration failed (non-fatal): {}", e)
        try:
            await db.rollback()
        except Exception:
            logger.warning("silently_swallowed_exception", exc_info=True)
        return 0
