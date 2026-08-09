"""自动探测旧 FIELD_ENCRYPTION_KEY 并重新加密所有字段。

当用户忘记旧密钥时，此脚本会自动从以下来源尝试：
  1. .env 的备份文件（.env.bak / .env.old / .env.backup / .env.*.bak 等）
  2. git 历史中的 .env 变更记录
  3. 当前 SECRET_KEY（早期版本可能用 SECRET_KEY 派生）
  4. 空字符串、常见默认值

找到能成功解密的旧密钥后，自动完成全量重新加密。
如果所有来源都失败，可选择清空所有加密字段（需在后台重新设置密码）。

用法：
    python3 scripts/auto_reencrypt.py              # 自动探测 + 重新加密
    python3 scripts/auto_reencrypt.py --dry-run    # 只探测，不修改
    python3 scripts/auto_reencrypt.py --reset      # 探测失败则清空所有加密字段

注意：运行前请停止后端服务。
"""
import asyncio
import os
import sys
import subprocess
import glob
from pathlib import Path

# 添加 backend 目录到 sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))


def _collect_candidate_keys() -> list[str]:
    """从多个来源收集候选旧密钥。"""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(key: str, source: str):
        key = (key or "").strip()
        if key and key not in seen:
            seen.add(key)
            candidates.append(key)
            print(f"  [候选] 来源={source}  密钥={key[:8]}... (长度={len(key)})")

    env_dir = _BACKEND_DIR

    # 1. 扫描 .env 备份文件（覆盖各种命名约定）
    print("\n[1/5] 扫描 .env 备份文件...")
    backup_patterns = [
        ".env.bak", ".env.old", ".env.backup", ".env.orig",
        ".env.production", ".env.production.bak", ".env.production.old",
        ".env.dev", ".env.dev.bak",
        ".env.local", ".env.local.bak",
        ".env.*", ".env.bak.*", ".env.old.*",
    ]
    found_env_files = set()
    for pattern in backup_patterns:
        for f in glob.glob(str(env_dir / pattern)):
            if os.path.basename(f) == ".env":
                continue
            found_env_files.add(f)
    # 也扫描上级目录（部署时 .env 可能在项目根目录）
    for pattern in [".env", ".env.bak", ".env.old", ".env.production", ".env.production.bak"]:
        for f in glob.glob(str(env_dir.parent / pattern)):
            found_env_files.add(f)

    for f in sorted(found_env_files):
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("FIELD_ENCRYPTION_KEY") and "=" in line:
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            _add(val, f"备份文件 {os.path.relpath(f, env_dir.parent) if os.path.exists(env_dir.parent / os.path.basename(f)) else os.path.basename(f)}")
                    # 同时收集 SECRET_KEY（旧版回退用）
                    if line.startswith("SECRET_KEY") and "=" in line:
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            _add(val, f"备份文件 SECRET_KEY {os.path.basename(f)}")
        except Exception:
            pass

    # 2. 从 git 历史提取
    print("\n[2/5] 扫描 git 历史中的 .env 变更...")
    try:
        # 获取 .env 文件的所有历史版本
        result = subprocess.run(
            ["git", "log", "--all", "--pretty=format:%H", "--", ".env"],
            cwd=str(env_dir),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            commits = result.stdout.strip().split("\n")
            print(f"  发现 {len(commits)} 个 .env 历史提交")
            for commit in commits[:50]:
                try:
                    show = subprocess.run(
                        ["git", "show", f"{commit}:.env"],
                        cwd=str(env_dir),
                        capture_output=True, text=True, timeout=5,
                    )
                    if show.returncode == 0:
                        for line in show.stdout.splitlines():
                            line = line.strip()
                            if line.startswith("FIELD_ENCRYPTION_KEY") and "=" in line:
                                val = line.split("=", 1)[1].strip().strip("'\"")
                                if val:
                                    _add(val, f"git FIELD_ENCRYPTION_KEY {commit[:8]}")
                            if line.startswith("SECRET_KEY") and "=" in line:
                                val = line.split("=", 1)[1].strip().strip("'\"")
                                if val:
                                    _add(val, f"git SECRET_KEY {commit[:8]}")
                except Exception:
                    pass
        else:
            print("  未找到 .env 的 git 历史（可能未纳入版本控制）")
    except Exception as e:
        print(f"  git 扫描失败: {e}")

    # 3. 扫描 docker-compose / systemd 等配置文件
    print("\n[3/5] 扫描 docker-compose / systemd 配置...")
    config_patterns = [
        "docker-compose.yml", "docker-compose.yaml",
        "docker-compose.override.yml", "docker-compose.override.yaml",
        "docker-compose.prod.yml", "docker-compose.prod.yaml",
        "../docker-compose.yml", "../docker-compose.yaml",
        "/etc/systemd/system/pygbsentry.service",
        "/etc/systemd/system/pygbsentry*.service",
    ]
    for pattern in config_patterns:
        for f in glob.glob(str(env_dir / pattern)):
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    # 在 docker-compose 中查找 FIELD_ENCRYPTION_KEY 或 SECRET_KEY
                    import re
                    for match in re.finditer(r'(?:FIELD_ENCRYPTION_KEY|SECRET_KEY)[\s:=]+([^\s\n]+)', content):
                        val = match.group(1).strip().strip("'\"")
                        if val and not val.startswith("$"):
                            _add(val, f"配置文件 {os.path.basename(f)}")
            except Exception:
                pass

    # 4. 尝试当前 SECRET_KEY（早期版本可能用 SECRET_KEY 派生）
    print("\n[4/5] 尝试当前 SECRET_KEY 作为候选...")
    try:
        from app.core.config import settings
        if settings.SECRET_KEY:
            _add(settings.SECRET_KEY, "当前 SECRET_KEY")
        # 也尝试当前 FIELD_ENCRYPTION_KEY（可能数据库密文就是用当前密钥加密的，只是派生算法变了）
        if settings.FIELD_ENCRYPTION_KEY:
            _add(settings.FIELD_ENCRYPTION_KEY, "当前 FIELD_ENCRYPTION_KEY")
    except Exception:
        pass

    # 5. 常见默认值
    print("\n[5/5] 尝试常见默认值...")
    common_defaults = [
        "PyGBSentry", "pygbsentry", "PyGBSentry2024", "PyGBSentry2025",
        "changeme", "default", "secret", "password",
        "suoten", "jjtt", "jjtt.net",
    ]
    for val in common_defaults:
        _add(val, "默认值")

    print(f"\n共收集到 {len(candidates)} 个候选密钥")
    return candidates


async def _test_key_on_sample(old_key: str) -> tuple[bool, str]:
    """用候选密钥尝试解密一条真实记录，验证密钥是否正确。

    测试两种模式：
    1. 当前版本：FIELD_ENCRYPTION_KEY = old_key
    2. 旧版回退：FIELD_ENCRYPTION_KEY = "" + SECRET_KEY = old_key（旧版回退到 SECRET_KEY）

    返回: (是否成功, 详细信息)
    """
    from app.core.config import settings
    from app.core.field_crypto import decrypt_field
    from app.db.session import AsyncSessionLocal

    original_field_key = settings.FIELD_ENCRYPTION_KEY
    original_secret_key = settings.SECRET_KEY

    try:
        # 尝试从 MediaNode 表取一条有 secret 的记录
        from app.models.media_node import MediaNode
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MediaNode).where(MediaNode.secret.isnot(None)).limit(1)
            )
            node = result.scalars().first()

            # 尝试 ParentPlatform
            from app.models.platform import ParentPlatform
            result = await session.execute(
                select(ParentPlatform).where(ParentPlatform.password.isnot(None)).limit(1)
            )
            pf = result.scalars().first()

            # 尝试 Asset
            from app.models.asset import Asset
            result = await session.execute(
                select(Asset).where(Asset.password.isnot(None)).limit(1)
            )
            asset = result.scalars().first()

        if not (node and node.secret) and not (pf and pf.password) and not (asset and asset.password):
            return False, "数据库中没有可测试的加密记录"

        # 模式 1：当前版本 — FIELD_ENCRYPTION_KEY = old_key
        settings.FIELD_ENCRYPTION_KEY = old_key
        settings.SECRET_KEY = original_secret_key

        if node and node.secret:
            plaintext = decrypt_field(node.secret, purpose="media_secret", allow_plaintext=False)
            if plaintext is not None:
                return True, f"模式1(当前) MediaNode {node.ip}:{node.http_port} secret 解密成功"
        if pf and pf.password:
            plaintext = decrypt_field(pf.password, purpose="sip_password", allow_plaintext=False)
            if plaintext is not None:
                return True, f"模式1(当前) ParentPlatform {pf.server_gb_id} password 解密成功"
        if asset and asset.password:
            plaintext = decrypt_field(asset.password, purpose="sip_password", allow_plaintext=False)
            if plaintext is not None:
                return True, f"模式1(当前) Asset {asset.gb_id} password 解密成功"

        # 模式 2：旧版回退 — FIELD_ENCRYPTION_KEY = "" + SECRET_KEY = old_key
        # 旧版 field_crypto.py 在 FIELD_ENCRYPTION_KEY 为空时回退到 SECRET_KEY
        settings.FIELD_ENCRYPTION_KEY = ""
        settings.SECRET_KEY = old_key

        if node and node.secret:
            plaintext = decrypt_field(node.secret, purpose="media_secret", allow_plaintext=False)
            if plaintext is not None:
                return True, f"模式2(旧版回退SECRET_KEY) MediaNode {node.ip}:{node.http_port} secret 解密成功"
        if pf and pf.password:
            plaintext = decrypt_field(pf.password, purpose="sip_password", allow_plaintext=False)
            if plaintext is not None:
                return True, f"模式2(旧版回退SECRET_KEY) ParentPlatform {pf.server_gb_id} password 解密成功"
        if asset and asset.password:
            plaintext = decrypt_field(asset.password, purpose="sip_password", allow_plaintext=False)
            if plaintext is not None:
                return True, f"模式2(旧版回退SECRET_KEY) Asset {asset.gb_id} password 解密成功"

        return False, "密钥不匹配（两种模式都失败）"
    finally:
        settings.FIELD_ENCRYPTION_KEY = original_field_key
        settings.SECRET_KEY = original_secret_key


async def _do_reencrypt_with_key(old_key: str, dry_run: bool = False, use_legacy_fallback: bool = False) -> dict:
    """用找到的旧密钥完成全量重新加密。

    Args:
        old_key: 旧密钥
        dry_run: True=只模拟不修改
        use_legacy_fallback: True=使用旧版回退模式（FIELD_ENCRYPTION_KEY="" + SECRET_KEY=old_key）
    """
    from app.core.config import settings
    from app.core.field_crypto import decrypt_field, encrypt_field
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select

    original_field_key = settings.FIELD_ENCRYPTION_KEY
    original_secret_key = settings.SECRET_KEY
    stats = {"success": 0, "failed": 0, "skipped": 0, "details": []}

    tables = [
        ("MediaNode", "app.models.media_node", "MediaNode", "secret", "media_secret"),
        ("ParentPlatform", "app.models.platform", "ParentPlatform", "password", "sip_password"),
        ("Asset", "app.models.asset", "Asset", "password", "sip_password"),
        ("AccessSource", "app.models.access_source", "AccessSource", "password", "sip_password"),
    ]

    for table_label, module_path, class_name, field_name, purpose in tables:
        try:
            module = __import__(module_path, fromlist=[class_name])
            model_cls = getattr(module, class_name)

            # 设置旧密钥用于解密
            if use_legacy_fallback:
                # 旧版回退模式：FIELD_ENCRYPTION_KEY="" + SECRET_KEY=old_key
                settings.FIELD_ENCRYPTION_KEY = ""
                settings.SECRET_KEY = old_key
            else:
                # 当前版本模式：FIELD_ENCRYPTION_KEY=old_key
                settings.FIELD_ENCRYPTION_KEY = old_key
                settings.SECRET_KEY = original_secret_key

            async with AsyncSessionLocal() as session:
                records = (await session.execute(select(model_cls))).scalars().all()

                # 恢复新密钥用于重新加密
                settings.FIELD_ENCRYPTION_KEY = original_field_key
                settings.SECRET_KEY = original_secret_key

                for rec in records:
                    ciphertext = getattr(rec, field_name, None)
                    if not ciphertext:
                        stats["skipped"] += 1
                        continue

                    plaintext = decrypt_field(ciphertext, purpose=purpose, allow_plaintext=False)
                    if plaintext is None:
                        stats["failed"] += 1
                        stats["details"].append(f"[FAIL] {table_label} #{getattr(rec, 'id', '?')} - 无法解密")
                    else:
                        stats["success"] += 1
                        if not dry_run:
                            setattr(rec, field_name, encrypt_field(plaintext, purpose=purpose))

                if not dry_run:
                    await session.commit()
        except ImportError:
            stats["skipped"] += 0  # 表不存在，跳过
        except Exception as e:
            stats["details"].append(f"[ERROR] {table_label}: {e}")
            settings.FIELD_ENCRYPTION_KEY = original_field_key
            settings.SECRET_KEY = original_secret_key

    settings.FIELD_ENCRYPTION_KEY = original_field_key
    settings.SECRET_KEY = original_secret_key
    return stats


async def _reset_all_encrypted_fields() -> dict:
    """清空所有加密字段（最后手段，需在后台重新设置密码）。"""
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select

    stats = {"cleared": 0, "tables": []}

    tables = [
        ("MediaNode", "app.models.media_node", "MediaNode", "secret"),
        ("ParentPlatform", "app.models.platform", "ParentPlatform", "password"),
        ("Asset", "app.models.asset", "Asset", "password"),
        ("AccessSource", "app.models.access_source", "AccessSource", "password"),
    ]

    for table_label, module_path, class_name, field_name in tables:
        try:
            module = __import__(module_path, fromlist=[class_name])
            model_cls = getattr(module, class_name)
            async with AsyncSessionLocal() as session:
                records = (await session.execute(select(model_cls))).scalars().all()
                count = 0
                for rec in records:
                    if getattr(rec, field_name, None):
                        setattr(rec, field_name, "")
                        count += 1
                await session.commit()
                if count > 0:
                    stats["tables"].append(f"{table_label}.{field_name}: 清空 {count} 条")
                    stats["cleared"] += count
        except ImportError:
            pass
        except Exception as e:
            stats["tables"].append(f"{table_label}: ERROR - {e}")

    return stats


async def main():
    dry_run = "--dry-run" in sys.argv
    reset_mode = "--reset" in sys.argv

    from app.core.config import settings

    new_key = settings.FIELD_ENCRYPTION_KEY
    if not new_key:
        print("ERROR: 当前 .env 中的 FIELD_ENCRYPTION_KEY 为空，请先在 .env 中设置新密钥")
        return

    print("=" * 60)
    print("PyGBSentry 自动密钥探测 + 重新加密工具")
    print("=" * 60)
    print(f"新密钥（当前 .env）: {new_key[:8]}...")
    print(f"模式: {'dry-run（只探测不修改）' if dry_run else '正式执行'}")
    print()

    # 第一步：收集候选密钥
    candidates = _collect_candidate_keys()

    if not candidates:
        print("\n未找到任何候选密钥。")
        if reset_mode:
            print("\n进入重置模式：清空所有加密字段...")
            stats = await _reset_all_encrypted_fields()
            print(f"\n已清空 {stats['cleared']} 个字段：")
            for t in stats["tables"]:
                print(f"  {t}")
            print("\n请在管理后台重新设置所有密码：")
            print("  1. 媒体节点 → 编辑 → 重新填写 ZLM secret")
            print("  2. 级联平台 → 编辑 → 重新填写下级平台密码")
            print("  3. 设备管理 → 编辑 → 重新填写 SIP 密码")
        else:
            print("\n建议：")
            print("  1. 运行 `python3 scripts/auto_reencrypt.py --reset` 清空所有加密字段")
            print("  2. 然后在管理后台重新设置所有密码")
        return

    # 第二步：逐个测试候选密钥
    print("\n" + "=" * 60)
    print("测试候选密钥...")
    print("=" * 60)

    found_key = None
    found_legacy_fallback = False  # 是否使用旧版回退模式
    for i, key in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] 测试密钥 {key[:8]}...")
        success, detail = await _test_key_on_sample(key)
        if success:
            print(f"  ✓ 成功！{detail}")
            found_key = key
            found_legacy_fallback = "模式2" in detail or "旧版回退" in detail
            break
        else:
            print(f"  ✗ 失败 - {detail}")

    if not found_key:
        print("\n" + "=" * 60)
        print("所有候选密钥都无法解密数据库中的加密字段。")
        print("=" * 60)
        if reset_mode:
            print("\n进入重置模式：清空所有加密字段...")
            stats = await _reset_all_encrypted_fields()
            print(f"\n已清空 {stats['cleared']} 个字段：")
            for t in stats["tables"]:
                print(f"  {t}")
        else:
            print("\n可能原因：")
            print("  1. 旧密钥不在任何备份/git历史中")
            print("  2. 数据库中的密文是用非常早的版本加密的")
            print("\n建议：")
            print("  1. 运行 `python3 scripts/auto_reencrypt.py --reset` 清空所有加密字段")
            print("  2. 然后在管理后台重新设置所有密码")
        return

    # 第三步：用找到的旧密钥重新加密
    print("\n" + "=" * 60)
    mode_desc = "旧版回退模式(SECRET_KEY)" if found_legacy_fallback else "当前模式(FIELD_ENCRYPTION_KEY)"
    print(f"找到旧密钥！模式: {mode_desc}")
    print(f"开始{'模拟' if dry_run else '正式'}重新加密...")
    print("=" * 60)

    stats = await _do_reencrypt_with_key(found_key, dry_run=dry_run, use_legacy_fallback=found_legacy_fallback)

    print(f"\n{'DRY-RUN' if dry_run else '重新加密'}结果：")
    print(f"  成功解密并{'模拟' if dry_run else ''}重加密: {stats['success']} 条")
    print(f"  无法解密（可能用其他密钥）: {stats['failed']} 条")
    print(f"  跳过（空字段）: {stats['skipped']} 条")

    if stats["details"]:
        print("\n详细信息：")
        for d in stats["details"][:20]:
            print(f"  {d}")
        if len(stats["details"]) > 20:
            print(f"  ... 还有 {len(stats['details']) - 20} 条")

    if not dry_run and stats["success"] > 0:
        print(f"\n✓ 成功重新加密 {stats['success']} 个字段。请重启后端服务。")
        if stats["failed"] > 0:
            print(f"\n⚠ 有 {stats['failed']} 个字段无法用旧密钥解密。")
            print("这些字段可能用更早的密钥加密，请在管理后台重新设置对应密码。")

    if dry_run:
        print("\n这是 dry-run 模式，未实际修改数据。")
        print("确认无误后去掉 --dry-run 参数正式执行。")


if __name__ == "__main__":
    asyncio.run(main())
