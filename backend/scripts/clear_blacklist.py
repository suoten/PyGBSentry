"""清除 IP 黑名单中的误拉黑条目。

用法：
    python3 scripts/clear_blacklist.py              # 列出所有黑名单条目
    python3 scripts/clear_blacklist.py --clear-all   # 清空所有黑名单
    python3 scripts/clear_blacklist.py --ip 198.27.80.75  # 只清除指定 IP
"""
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))


async def main():
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select, delete, text

    clear_all = "--clear-all" in sys.argv
    target_ip = None
    for arg in sys.argv[1:]:
        if arg.startswith("--ip="):
            target_ip = arg.split("=", 1)[1]
        elif arg == "--ip" and sys.argv.index(arg) + 1 < len(sys.argv):
            target_ip = sys.argv[sys.argv.index(arg) + 1]

    async with AsyncSessionLocal() as session:
        # 查询所有黑名单
        result = await session.execute(text("SELECT id, ip, reason, created_at FROM ip_blacklist ORDER BY created_at DESC"))
        rows = result.fetchall()

        print("=" * 60)
        print("IP 黑名单当前状态")
        print("=" * 60)

        if not rows:
            print("黑名单为空")
            return

        print(f"共 {len(rows)} 条记录：\n")
        for row in rows:
            row_id, ip, reason, created_at = row
            print(f"  ID: {row_id}")
            print(f"  IP: {ip}")
            print(f"  原因: {reason}")
            print(f"  时间: {created_at}")
            print()

        if not clear_all and not target_ip:
            print("=" * 60)
            print("如需清除，运行：")
            print("  清空所有: python3 scripts/clear_blacklist.py --clear-all")
            print("  清除指定: python3 scripts/clear_blacklist.py --ip 198.27.80.75")
            return

        if clear_all:
            await session.execute(text("DELETE FROM ip_blacklist"))
            await session.commit()
            print(f"✓ 已清空所有 {len(rows)} 条黑名单记录")
            print("\n请重启后端服务使黑名单缓存生效：")
            print("  systemctl restart pygbsentry")
        elif target_ip:
            await session.execute(text(f"DELETE FROM ip_blacklist WHERE ip = '{target_ip}'"))
            await session.commit()
            print(f"✓ 已清除 IP {target_ip} 的黑名单记录")
            print("\n请重启后端服务使黑名单缓存生效：")
            print("  systemctl restart pygbsentry")


if __name__ == "__main__":
    asyncio.run(main())
