"""批量重新加密所有字段加密的敏感数据。

当 FIELD_ENCRYPTION_KEY 被修改后，数据库中已加密的字段（sip_password、media_secret 等）
无法用新密钥解密。此脚本用旧密钥解密后用新密钥重新加密。

用法：
    # 方式 1：通过环境变量传递旧密钥
    OLD_FIELD_ENCRYPTION_KEY=<old_key> python scripts/reencrypt_fields.py

    # 方式 2：交互式输入（不回显）
    python scripts/reencrypt_fields.py

    # 方式 3：dry-run 模式（只检查哪些字段解密失败，不实际修改）
    python scripts/reencrypt_fields.py --dry-run

注意：
    1. 运行前请停止后端服务，避免并发写入。
    2. 运行前请确保 .env 中的 FIELD_ENCRYPTION_KEY 已改为新值。
    3. 运行后重启后端服务。
"""
import asyncio
import os
import sys
import getpass
from pathlib import Path

# 添加 backend 目录到 sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from loguru import logger
from sqlalchemy import select

# 必须在导入 settings 之前设置旧密钥环境变量
_OLD_KEY_ENV = "OLD_FIELD_ENCRYPTION_KEY"


async def reencrypt_all(*, dry_run: bool = False) -> None:
    """用旧密钥解密所有加密字段，用新密钥重新加密。"""
    from app.core.config import settings
    from app.core.field_crypto import decrypt_field, encrypt_field
    from app.db.session import AsyncSessionLocal

    # 旧密钥优先从环境变量读取，否则交互式输入
    old_key = os.environ.get(_OLD_KEY_ENV, "").strip()
    if not old_key:
        print("当前 .env 中的 FIELD_ENCRYPTION_KEY (新密钥):", settings.FIELD_ENCRYPTION_KEY[:8] + "..." if settings.FIELD_ENCRYPTION_KEY else "(empty)")
        old_key = getpass.getpass("请输入旧的 FIELD_ENCRYPTION_KEY (不回显): ").strip()
        if not old_key:
            print("ERROR: 未提供旧密钥，退出。")
            return

    # 临时 monkey-patch settings.FIELD_ENCRYPTION_KEY 为旧密钥，用于解密
    original_key = settings.FIELD_ENCRYPTION_KEY
    settings.FIELD_ENCRYPTION_KEY = old_key

    stats = {
        "media_nodes": {"success": 0, "failed": 0, "skipped": 0},
        "parent_platforms": {"success": 0, "failed": 0, "skipped": 0},
        "assets": {"success": 0, "failed": 0, "skipped": 0},
        "access_sources": {"success": 0, "failed": 0, "skipped": 0},
        "resources": {"success": 0, "failed": 0, "skipped": 0},
    }

    # 恢复新密钥，用于重新加密
    settings.FIELD_ENCRYPTION_KEY = original_key

    print(f"\n开始 {'dry-run 检查' if dry_run else '重新加密'}...")
    print(f"新密钥: {original_key[:8]}..." if original_key else "新密钥: (empty)")
    print()

    # 1. MediaNode.secret (purpose=media_secret)
    try:
        from app.models.media_node import MediaNode
        settings.FIELD_ENCRYPTION_KEY = old_key  # 用旧密钥解密
        async with AsyncSessionLocal() as session:
            nodes = (await session.execute(select(MediaNode))).scalars().all()
            settings.FIELD_ENCRYPTION_KEY = original_key  # 恢复新密钥
            for node in nodes:
                if not node.secret:
                    stats["media_nodes"]["skipped"] += 1
                    continue
                plaintext = decrypt_field(node.secret, purpose="media_secret", allow_plaintext=False)
                if plaintext is None:
                    stats["media_nodes"]["failed"] += 1
                    print(f"  [FAIL] MediaNode {node.id} ({node.ip}:{node.http_port}) - 无法解密 secret")
                else:
                    stats["media_nodes"]["success"] += 1
                    if not dry_run:
                        node.secret = encrypt_field(plaintext, purpose="media_secret")
            if not dry_run:
                await session.commit()
    except Exception as e:
        print(f"  [ERROR] MediaNode 处理异常: {e}")
        settings.FIELD_ENCRYPTION_KEY = original_key

    # 2. ParentPlatform.password (purpose=sip_password)
    try:
        from app.models.platform import ParentPlatform
        settings.FIELD_ENCRYPTION_KEY = old_key
        async with AsyncSessionLocal() as session:
            platforms = (await session.execute(select(ParentPlatform))).scalars().all()
            settings.FIELD_ENCRYPTION_KEY = original_key
            for pf in platforms:
                if not pf.password:
                    stats["parent_platforms"]["skipped"] += 1
                    continue
                plaintext = decrypt_field(pf.password, purpose="sip_password", allow_plaintext=False)
                if plaintext is None:
                    stats["parent_platforms"]["failed"] += 1
                    print(f"  [FAIL] ParentPlatform {pf.id} ({pf.server_gb_id}) - 无法解密 password")
                else:
                    stats["parent_platforms"]["success"] += 1
                    if not dry_run:
                        pf.password = encrypt_field(plaintext, purpose="sip_password")
            if not dry_run:
                await session.commit()
    except Exception as e:
        print(f"  [ERROR] ParentPlatform 处理异常: {e}")
        settings.FIELD_ENCRYPTION_KEY = original_key

    # 3. Asset.password (purpose=sip_password)
    try:
        from app.models.asset import Asset
        settings.FIELD_ENCRYPTION_KEY = old_key
        async with AsyncSessionLocal() as session:
            assets = (await session.execute(select(Asset))).scalars().all()
            settings.FIELD_ENCRYPTION_KEY = original_key
            for asset in assets:
                if not asset.password:
                    stats["assets"]["skipped"] += 1
                    continue
                plaintext = decrypt_field(asset.password, purpose="sip_password", allow_plaintext=False)
                if plaintext is None:
                    stats["assets"]["failed"] += 1
                    print(f"  [FAIL] Asset {asset.id} ({asset.gb_id}) - 无法解密 password")
                else:
                    stats["assets"]["success"] += 1
                    if not dry_run:
                        asset.password = encrypt_field(plaintext, purpose="sip_password")
            if not dry_run:
                await session.commit()
    except Exception as e:
        print(f"  [ERROR] Asset 处理异常: {e}")
        settings.FIELD_ENCRYPTION_KEY = original_key

    # 4. AccessSource.password (purpose=sip_password)
    try:
        from app.models.access_source import AccessSource
        settings.FIELD_ENCRYPTION_KEY = old_key
        async with AsyncSessionLocal() as session:
            sources = (await session.execute(select(AccessSource))).scalars().all()
            settings.FIELD_ENCRYPTION_KEY = original_key
            for src in sources:
                if not src.password:
                    stats["access_sources"]["skipped"] += 1
                    continue
                plaintext = decrypt_field(src.password, purpose="sip_password", allow_plaintext=False)
                if plaintext is None:
                    stats["access_sources"]["failed"] += 1
                    print(f"  [FAIL] AccessSource {src.id} - 无法解密 password")
                else:
                    stats["access_sources"]["success"] += 1
                    if not dry_run:
                        src.password = encrypt_field(plaintext, purpose="sip_password")
            if not dry_run:
                await session.commit()
    except Exception as e:
        print(f"  [ERROR] AccessSource 处理异常: {e}")
        settings.FIELD_ENCRYPTION_KEY = original_key

    # 5. Resource.password (purpose=sip_password) - 如果存在
    try:
        from app.models.resource import Resource
        settings.FIELD_ENCRYPTION_KEY = old_key
        async with AsyncSessionLocal() as session:
            resources = (await session.execute(select(Resource))).scalars().all()
            settings.FIELD_ENCRYPTION_KEY = original_key
            for res in resources:
                # Resource 表的密码字段名可能不同，动态检查
                pwd = getattr(res, "password", None) or getattr(res, "stream_password", None)
                if not pwd:
                    stats["resources"]["skipped"] += 1
                    continue
                plaintext = decrypt_field(pwd, purpose="sip_password", allow_plaintext=False)
                if plaintext is None:
                    stats["resources"]["failed"] += 1
                    print(f"  [FAIL] Resource {res.id} - 无法解密 password")
                else:
                    stats["resources"]["success"] += 1
                    if not dry_run:
                        if hasattr(res, "password"):
                            res.password = encrypt_field(plaintext, purpose="sip_password")
                        elif hasattr(res, "stream_password"):
                            res.stream_password = encrypt_field(plaintext, purpose="sip_password")
            if not dry_run:
                await session.commit()
    except Exception as e:
        print(f"  [ERROR] Resource 处理异常: {e}")
        settings.FIELD_ENCRYPTION_KEY = original_key

    # 恢复新密钥
    settings.FIELD_ENCRYPTION_KEY = original_key

    # 打印统计
    print("\n" + "=" * 60)
    print(f"{'DRY-RUN 结果' if dry_run else '重新加密完成'}")
    print("=" * 60)
    total_success = 0
    total_failed = 0
    total_skipped = 0
    for table, counts in stats.items():
        print(f"  {table:20s}: 成功={counts['success']:3d}  失败={counts['failed']:3d}  跳过={counts['skipped']:3d}")
        total_success += counts["success"]
        total_failed += counts["failed"]
        total_skipped += counts["skipped"]
    print(f"  {'合计':20s}: 成功={total_success:3d}  失败={total_failed:3d}  跳过={total_skipped:3d}")
    print("=" * 60)

    if total_failed > 0:
        print(f"\nWARNING: {total_failed} 个字段无法用旧密钥解密。")
        print("可能原因：")
        print("  1. 旧密钥输入错误")
        print("  2. 该字段是用更早的另一个密钥加密的")
        print("  3. 该字段数据损坏")
        print("\n建议：对失败的字段，在管理后台重新设置密码/密钥。")

    if not dry_run and total_success > 0:
        print(f"\n成功重新加密 {total_success} 个字段。请重启后端服务。")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(reencrypt_all(dry_run=dry_run))
