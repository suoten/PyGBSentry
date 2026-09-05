#!/usr/bin/env python3
"""
补全/创建内置 ZLM 媒体节点记录（与启动时 ensure_embedded_media_node 相同）。

适用：未执行 initial_data、或关闭了 ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP 后需补库。

用法（在 backend 目录）:
  python scripts/ensure_embedded_media_node.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main() -> None:
    from sqlalchemy import text

    from app.core.config import settings
    from app.core.media_nodes_db import ensure_embedded_media_node
    from app.db.session import AsyncSessionLocal, engine

    async def _call(db):
        if (getattr(engine.dialect, "name", None) or "").lower() == "sqlite":
            await db.execute(text(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}"))
        return await ensure_embedded_media_node(db)

    async with AsyncSessionLocal() as db:
        rid = await _call(db)
        print({"embedded_media_node_id": rid})


if __name__ == "__main__":
    asyncio.run(main())
