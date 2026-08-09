"""手动初始化数据库 schema + 管理员账号。

绕过后端启动逻辑，直接调用 create_all + init_db。
"""
import asyncio
import sys
import os

# 设置 Windows 事件循环策略（SIP UDP 需要）
if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

# 确保在 backend 目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.db.base import Base
from app.db.model_registry import ensure_model_registry_loaded
from app.db.session import engine
from app.core.config import settings

async def main():
    print(f"DB URL: {settings.DATABASE_URL if hasattr(settings, 'DATABASE_URL') else 'N/A'}")
    print(f"USE_ALEMBIC: {settings.USE_ALEMBIC}")

    # 1. 注册所有模型
    print("\n[1] ensure_model_registry_loaded...")
    ensure_model_registry_loaded()
    table_names = sorted(Base.metadata.tables.keys())
    print(f"    Registered tables: {len(table_names)}")
    print(f"    Sample: {table_names[:10]}")

    # 2. create_all
    print("\n[2] create_all...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("    create_all done.")

    # 3. 验证表
    import sqlite3
    db_path = settings.DATABASE_SQLITE_PATH if hasattr(settings, 'DATABASE_SQLITE_PATH') else './pygbsentry_dev.db'
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    print(f"\n[3] Tables in DB: {len(tables)}")
    critical = ['assets', 'users', 'config_drafts', 'media_port_leases', 'alarms']
    for t in critical:
        print(f"    {'OK' if t in tables else 'MISSING'}: {t}")
    conn.close()

    # 4. init_db (创建管理员)
    print("\n[4] init_db...")
    from app.initial_data import init_db
    await init_db()
    print("    init_db done.")

    # 5. 验证 config_drafts 列
    conn = sqlite3.connect(db_path)
    if 'config_drafts' in [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(config_drafts)").fetchall()]
        print(f"\n[5] config_drafts columns: {cols}")
        print(f"    has created_at: {'created_at' in cols}")
    conn.close()

    print("\n=== DB initialization complete ===")

if __name__ == "__main__":
    asyncio.run(main())
