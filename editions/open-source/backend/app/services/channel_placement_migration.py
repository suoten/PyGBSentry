"""
将历史上挂在行政区划侧的 parent_gb_id（region:* 或行政区目录下）迁移到 region_parent_gb_id，
使业务分组(parent_gb_id)与行政区划(region_parent_gb_id)可独立挂载通道。
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession

async def ensure_split_channel_region_parents(db: AsyncSession) -> int:
    total_r = await db.execute(text("SELECT COUNT(1) FROM resources"))
    total = int(total_r.scalar() or 0)
    if total == 0:
        logger.info("Split migration skipped: resources table is empty")
        return 0

    logger.info("Split migration(channel) start, resources={}", total)
    # 1) parent_gb_id 直接挂 region:* 的通道，直接迁移到 region_parent_gb_id
    logger.info("Split migration(channel) phase-1 start")
    r1 = await db.execute(
        text(
            """
            UPDATE resources
            SET region_parent_gb_id = parent_gb_id,
                parent_gb_id = NULL
            WHERE (node_type IS NULL OR lower(node_type) != 'directory')
              AND parent_gb_id IS NOT NULL
              AND trim(parent_gb_id) LIKE 'region:%'
              AND (region_parent_gb_id IS NULL OR trim(region_parent_gb_id) = '')
            """
        )
    )
    changed_1 = int(getattr(r1, "rowcount", 0) or 0)
    logger.info("Split migration(channel) phase-1 done, changed={}", changed_1)

    # 2) parent_gb_id 指向“行政区目录”的通道：目录自身 parent_gb_id 为 region:*。
    # 优先用 SQLite 3.33+ 的 UPDATE...FROM（比相关 EXISTS 全表嵌套更快）；老版本再回退。
    logger.info("Split migration(channel) phase-2 start")
    phase2_sql = """
            UPDATE resources AS c
            SET region_parent_gb_id = c.parent_gb_id,
                parent_gb_id = NULL
            FROM resources AS p
            WHERE (c.node_type IS NULL OR lower(c.node_type) != 'directory')
              AND c.parent_gb_id IS NOT NULL
              AND (c.region_parent_gb_id IS NULL OR trim(c.region_parent_gb_id) = '')
              AND p.gb_id = c.parent_gb_id
              AND lower(COALESCE(p.node_type, '')) = 'directory'
              AND p.parent_gb_id LIKE 'region:%'
            """
    try:
        r2 = await db.execute(text(phase2_sql))
        changed_2 = int(getattr(r2, "rowcount", 0) or 0)
    except Exception as e:
        logger.warning(
            "Split migration(channel) phase-2 UPDATE FROM failed, fallback to EXISTS: {}",
            e,
        )
        r2 = await db.execute(
            text(
                """
                UPDATE resources AS c
                SET region_parent_gb_id = c.parent_gb_id,
                    parent_gb_id = NULL
                WHERE (c.node_type IS NULL OR lower(c.node_type) != 'directory')
                  AND c.parent_gb_id IS NOT NULL
                  AND (c.region_parent_gb_id IS NULL OR trim(c.region_parent_gb_id) = '')
                  AND EXISTS (
                        SELECT 1
                        FROM resources AS p
                        WHERE p.gb_id = c.parent_gb_id
                          AND lower(COALESCE(p.node_type, '')) = 'directory'
                          AND p.parent_gb_id LIKE 'region:%'
                  )
                """
            )
        )
        changed_2 = int(getattr(r2, "rowcount", 0) or 0)
    logger.info("Split migration(channel) phase-2 done, changed={}", changed_2)

    changed = changed_1 + changed_2
    if changed:
        await db.commit()
        logger.info("Migrated {} channel(s) to region_parent_gb_id for split catalog placement", changed)
    return changed
