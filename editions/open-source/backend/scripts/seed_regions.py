#!/usr/bin/env python3
"""
从 backend/data/region.sql 导入行政区划（与启动时 ensure_regions_seeded_from_sql 相同逻辑）。

用法（在 backend 目录）:
  python scripts/seed_regions.py
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
    from app.services.region_import_service import ensure_regions_seeded_from_sql

    async with AsyncSessionLocal() as db:
        r = await ensure_regions_seeded_from_sql(db)
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
