#!/usr/bin/env python3
"""
离线执行业务/行政区 parent 字段拆分迁移（与启动时的 split_migrations 相同逻辑）。

适用：从旧版本升级、resources 表已有数据，且已在 .env 关闭 RUN_SPLIT_CATALOG_MIGRATIONS_ON_STARTUP 时。

用法（在 backend 目录）:
  python scripts/run_split_catalog_migrations.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main() -> None:
    from app.db.session import AsyncSessionLocal
    from app.services.channel_placement_migration import ensure_split_channel_region_parents
    from app.services.region_directory_split_migration import ensure_split_region_directory_parents

    async with AsyncSessionLocal() as db:
        n = await ensure_split_channel_region_parents(db)
        print(f"ensure_split_channel_region_parents => {n}")
        d = await ensure_split_region_directory_parents(db)
        print(f"ensure_split_region_directory_parents => {d}")
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
