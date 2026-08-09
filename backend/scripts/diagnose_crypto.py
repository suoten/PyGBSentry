"""诊断 FIELD_ENCRYPTION_KEY 和 MediaNode.secret 的实际状态。

直接查询数据库，输出：
1. FIELD_ENCRYPTION_KEY / MEDIA_SERVER_SECRET 配置
2. MediaNode 表所有记录的 secret 列实际值（脱敏）
3. 尝试用当前密钥加密+解密一个测试值
4. 尝试解密数据库中的实际 secret

用法：python3 scripts/diagnose_crypto.py
"""
import asyncio
import sys
import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))


async def main():
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.core.field_crypto import encrypt_field, decrypt_field
    from sqlalchemy import select, text

    print("=" * 70)
    print("PyGBSentry 加密诊断工具")
    print("=" * 70)

    # 1. 配置检查
    print("\n[1] 配置检查")
    print(f"  FIELD_ENCRYPTION_KEY: {(settings.FIELD_ENCRYPTION_KEY or '')[:12]}... (长度={len(settings.FIELD_ENCRYPTION_KEY or '')})")
    print(f"  MEDIA_SERVER_SECRET:  {(settings.MEDIA_SERVER_SECRET or '')[:12]}... (长度={len(settings.MEDIA_SERVER_SECRET or '')})")
    print(f"  SECRET_KEY:           {(settings.SECRET_KEY or '')[:12]}... (长度={len(settings.SECRET_KEY or '')})")
    print(f"  DATABASE_TYPE:         {settings.DATABASE_TYPE}")

    # 2. 加解密自测
    print("\n[2] 加解密自测（用当前 FIELD_ENCRYPTION_KEY）")
    try:
        test_plain = "diagnostic_test_value_12345"
        test_cipher = encrypt_field(test_plain, purpose="media_secret")
        test_dec = decrypt_field(test_cipher, purpose="media_secret")
        if test_dec == test_plain:
            print(f"  ✓ 加解密正常（加密后长度={len(test_cipher)}, 解密成功）")
        else:
            print(f"  ✗ 解密结果不匹配: expected={test_plain}, got={test_dec}")
    except Exception as e:
        print(f"  ✗ 加解密异常: {type(e).__name__}: {e}")

    # 3. 数据库实际状态
    print("\n[3] 数据库 MediaNode 表实际状态")
    async with AsyncSessionLocal() as session:
        # 直接用 SQL 查询，避免 ORM 的 decrypted_secret 属性干扰
        result = await session.execute(text("SELECT id, ip, http_port, is_embedded, is_online, secret, last_probe_error FROM media_nodes"))
        rows = result.fetchall()

        if not rows:
            print("  ⚠ media_nodes 表为空（没有任何节点记录）")
            print("  → 这就是问题！ensure_embedded_media_node 没有创建内置节点。")
            print("  → 检查 ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP 配置和启动日志")
            return

        print(f"  共 {len(rows)} 条记录：")
        for row in rows:
            row_id, ip, http_port, is_embedded, is_online, secret, last_probe_error = row
            secret_len = len(secret) if secret else 0
            secret_is_null = secret is None
            secret_is_empty = secret == ""
            secret_preview = (secret[:20] + "...") if secret and len(secret) > 20 else (secret or "")

            print(f"\n  节点 {row_id}:")
            print(f"    ip={ip}, http_port={http_port}, is_embedded={is_embedded}, is_online={is_online}")
            print(f"    secret 列: is_null={secret_is_null}, is_empty={secret_is_empty}, length={secret_len}")
            print(f"    secret 预览: {secret_preview!r}")
            print(f"    last_probe_error: {last_probe_error!r}")

            # 4. 尝试解密这个 secret
            if secret and not secret_is_empty:
                print(f"    尝试解密 secret...")
                try:
                    # FIX [2026-07-19]: 严格模式——明文 secret 不应被误判为"解密成功"
                    plaintext = decrypt_field(secret, purpose="media_secret", allow_plaintext=False)
                    if plaintext is not None:
                        print(f"    ✓ 解密成功！明文={plaintext[:8]}... (长度={len(plaintext)})")
                    else:
                        print(f"    ✗ 解密失败（返回 None）— 这就是 'Field decryption failed' 的原因")
                        print(f"    → secret 列有值但用当前 FIELD_ENCRYPTION_KEY 解不开")
                        print(f"    → 说明这个 secret 是用不同的密钥加密的，或仍是明文未加密")
                except Exception as e:
                    print(f"    ✗ 解密异常: {type(e).__name__}: {e}")
            else:
                if secret_is_null:
                    print(f"    → secret 列为 NULL（未设置）")
                    print(f"    → health_service 应报 'ZLM secret not configured'")
                    print(f"    → 如果仍报 'Field decryption failed'，说明代码未更新")
                elif secret_is_empty:
                    print(f"    → secret 列为空字符串")
                    print(f"    → health_service 应报 'ZLM secret not configured'")
                    print(f"    → 如果仍报 'Field decryption failed'，说明代码未更新")

    # 5. 其他表的加密字段
    print("\n[4] 其他表的加密字段状态")
    tables_to_check = [
        ("parent_platforms", "password"),
        ("assets", "password"),
        ("access_sources", "password"),
    ]
    for table_name, field in tables_to_check:
        try:
            result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE {field} IS NOT NULL AND {field} != ''"))
            count = result.scalar()
            print(f"  {table_name}.{field}: {count} 条有值")
        except Exception as e:
            print(f"  {table_name}.{field}: 查询失败 - {e}")

    # 6. 诊断结论
    print("\n" + "=" * 70)
    print("[5] 诊断结论")
    print("=" * 70)

    # 重新查询判断
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT secret FROM media_nodes WHERE is_embedded = true LIMIT 1"))
        row = result.fetchone()
        if row:
            embedded_secret = row[0]
            if not embedded_secret:
                print("\n  根因: MediaNode.secret 列为空（NULL 或空字符串）")
                print("  这不是 FIELD_ENCRYPTION_KEY 的问题！")
                print("  真正原因: MEDIA_SERVER_SECRET 未配置，或节点创建时加密失败")
                print("\n  修复方法:")
                print("  1. 确认 .env 中 MEDIA_SERVER_SECRET 已设置（与 ZLM config.ini 的 api.secret 一致）")
                print("  2. 确认 .env 中 FIELD_ENCRYPTION_KEY 已设置（任意随机字符串）")
                print("  3. 确保已部署修复后的 app/core/media_nodes_db.py")
                print("  4. 重启后端，日志应出现 'refilled empty secret with current MEDIA_SERVER_SECRET'")
            else:
                # 尝试解密
                # FIX [2026-07-19]: 严格模式——明文 secret 不应被误判为"解密成功"
                plaintext = decrypt_field(embedded_secret, purpose="media_secret", allow_plaintext=False)
                if plaintext is None:
                    print("\n  根因: MediaNode.secret 列有值但无法用当前 FIELD_ENCRYPTION_KEY 解密")
                    print("  说明 secret 是用不同的密钥加密的，或仍是明文未加密")
                    print("\n  修复方法:")
                    print("  选项 A: 找回旧密钥（检查 .env 备份、git 历史）")
                    print("  选项 B: 清空 secret 列，让 ensure_embedded_media_node 重新填充：")
                    print("    psql -U postgres -d pygb28181 -c \"UPDATE media_nodes SET secret = NULL WHERE is_embedded = true;\"")
                    print("  选项 C: 用修复后的 media_nodes_db.py，它会自动检测空 secret 并重新填充")
                else:
                    print("\n  ✓ secret 解密正常，问题可能在其他地方")
        else:
            print("\n  根因: 数据库中没有内置 ZLM 节点记录")
            print("  修复方法: 检查 ENSURE_EMBEDDED_MEDIA_NODE_ON_STARTUP=true，重启后端")


if __name__ == "__main__":
    asyncio.run(main())
