"""行政区域目录拆分迁移（一次性）。

与 ``channel_placement_migration`` 配套，针对 ``node_type='directory'`` 的目录
节点 Resource。历史 schema 曾将「行政区域父级」与「目录父级」合并写入
``resources.parent_gb_id``，新 schema 拆分为：

- ``parent_gb_id``：目录父级国标 ID（20 位 GB28181 编码，指向另一个目录节点）
- ``region_parent_gb_id``：行政区域父级编码（行政区划 code，6~12 位数字）

本迁移扫描所有 ``node_type='directory'`` 的 Resource，若 ``region_parent_gb_id``
为空而 ``parent_gb_id`` 中存放的并非 20 位国标 ID（即疑似行政区域编码），则将其
搬迁到 ``region_parent_gb_id`` 并清空 ``parent_gb_id``。

幂等、永不抛异常。
"""
from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource import Resource

# GB28181 目录/设备国标 ID 为 20 位数字；行政区域编码通常 6~12 位数字。
_GB_ID_20_RE = re.compile(r"^\d{20}$")


async def ensure_split_region_directory_parents(db: AsyncSession) -> int:
    """拆分目录节点的 region_parent_gb_id / parent_gb_id 字段。

    返回被更新的行数。幂等、永不抛异常。
    """
    try:
        stmt = select(Resource).where(
            Resource.node_type == "directory",
            (Resource.region_parent_gb_id.is_(None))
            | (Resource.region_parent_gb_id == ""),
            Resource.parent_gb_id.isnot(None),
            Resource.parent_gb_id != "",
        )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            logger.info("region_directory_split_migration: no-op (already applied / nothing to migrate)")
            return 0

        updated = 0
        for res in rows:
            parent_gb = str(res.parent_gb_id or "").strip()
            if not parent_gb:
                continue
            if _GB_ID_20_RE.match(parent_gb):
                # 20 位国标 ID 视为合法的目录父级，不迁移
                continue
            # 否则视为行政区域编码，搬迁到 region_parent_gb_id
            res.region_parent_gb_id = parent_gb
            res.parent_gb_id = None
            updated += 1

        if updated:
            await db.commit()
        logger.info("region_directory_split_migration: split {} directory region parents", updated)
        return updated
    except Exception as e:
        logger.warning("region_directory_split_migration failed (non-fatal): {}", e)
        try:
            await db.rollback()
        except Exception:
            logger.warning("silently_swallowed_exception", exc_info=True)
        return 0
