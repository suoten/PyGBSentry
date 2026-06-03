"""
将历史目录数据中“业务/行政区挂载字段混用”的情况纠正：
- 行政区树的目录节点应通过 `region_parent_gb_id` 挂载（值形如 `region:xxxxxx`），同时 `parent_gb_id` 应为空或不参与 region tree。
- 业务树的目录节点应只通过 `parent_gb_id` 挂载（根资源组/目录 gb_id），不应带 `region_parent_gb_id`。

此迁移只修正目录（node_type=directory），不修正通道。
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession

async def ensure_split_region_directory_parents(db: AsyncSession) -> int:
    total_r = await db.execute(text("SELECT COUNT(1) FROM resources"))
    total = int(total_r.scalar() or 0)
    if total == 0:
        logger.info("Split migration skipped: resources table is empty")
        return 0

    logger.info("Split migration(directory) start, resources={}", total)
    # 1) 历史兼容：directory 的 parent_gb_id 是 region:*，搬迁到 region_parent_gb_id
    logger.info("Split migration(directory) phase-1 start")
    r1 = await db.execute(
        text(
            """
            UPDATE resources
            SET region_parent_gb_id = parent_gb_id,
                parent_gb_id = NULL
            WHERE lower(COALESCE(node_type, '')) = 'directory'
              AND parent_gb_id IS NOT NULL
              AND trim(parent_gb_id) LIKE 'region:%'
              AND (region_parent_gb_id IS NULL OR trim(region_parent_gb_id) = '')
            """
        )
    )
    changed_1 = int(getattr(r1, "rowcount", 0) or 0)
    logger.info("Split migration(directory) phase-1 done, changed={}", changed_1)

    # 2) 清理混用：directory 同时带 region_parent + 非 region parent_gb_id => 清空 region_parent_gb_id
    logger.info("Split migration(directory) phase-2 start")
    r2 = await db.execute(
        text(
            """
            UPDATE resources
            SET region_parent_gb_id = NULL
            WHERE lower(COALESCE(node_type, '')) = 'directory'
              AND region_parent_gb_id IS NOT NULL
              AND trim(region_parent_gb_id) != ''
              AND parent_gb_id IS NOT NULL
              AND trim(parent_gb_id) != ''
              AND trim(parent_gb_id) NOT LIKE 'region:%'
            """
        )
    )
    changed_2 = int(getattr(r2, "rowcount", 0) or 0)
    logger.info("Split migration(directory) phase-2 done, changed={}", changed_2)

    changed = changed_1 + changed_2
    if changed:
        await db.commit()
        logger.info("Migrated {} directory(s) to split region_parent_gb_id", changed)
    return changed

