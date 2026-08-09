"""SIP 设备注册认证诊断脚本。

针对日志中出现 "Auth failed for <gb_id>: Response mismatch" 的设备，深度诊断：

1. 数据库记录匹配情况（assets / parent_platforms 三类记录）
2. FIELD_ENCRYPTION_KEY 是否能解密已有记录的 password 密文
3. 设备实际配置的密码（如已知）是否与 DB 记录的明文密码一致
4. SIP_DEFAULT_PASSWORD 候选密码与设备本地密码是否一致
5. 输出可执行的修复方案（添加设备 / 修正密码 / 重新加密字段）

用法：
    # 诊断单个设备（默认读取 .env 中的 SIP_DEFAULT_PASSWORD 作为对比）
    python scripts/diagnose_sip_device.py 34020000002000000002

    # 同时指定设备本地真实密码（用于比对 DB / 默认密码是否一致）
    python scripts/diagnose_sip_device.py 34020000002000000002 --device-password <明文密码>

    # 列出所有 assets / parent_platforms 中的国标 ID（不带 gb_id 参数）
    python scripts/diagnose_sip_device.py --list

    # 修复模式：在 DB 中添加缺失的设备记录（使用 SIP_DEFAULT_PASSWORD 加密）
    python scripts/diagnose_sip_device.py 34020000002000000002 --fix-add-device

    # 修复模式：将设备本地密码写入已存在的 Asset 记录（自动加密）
    python scripts/diagnose_sip_device.py 34020000002000000002 --fix-set-password <明文密码>

    # 清理 IP 黑名单和认证失败计数（不带参数清理全部，带 IP 仅清理指定 IP）
    python scripts/diagnose_sip_device.py --clear-blacklist
    python scripts/diagnose_sip_device.py --clear-blacklist 36.34.0.68

    # 验证服务器实际加载的 SIP 配置（检查空格/不可见字符/环境变量覆盖）
    python scripts/diagnose_sip_device.py --verify-config

    # 用给定密码模拟 SIP Digest 计算（验证算法正确性）
    python scripts/diagnose_sip_device.py --simulate-digest <密码>

注意：
    1. 运行前请停止后端服务，避免并发写入。
    2. --fix-* 选项会修改数据库，请先备份。
    3. 修复后请重启后端服务使变更生效。
    4. --clear-blacklist 和 --verify-config 可在服务运行时执行（只读或仅清理黑名单）。
"""
import argparse
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

# 添加 backend 目录到 sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from loguru import logger
from sqlalchemy import select, text


def _mask(s: str | None, keep: int = 4) -> str:
    """简单脱敏：保留前 keep 个字符，其余用 * 替代。"""
    if not s:
        return "(empty)"
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep)


async def list_all_devices() -> None:
    """列出所有 assets / parent_platforms 中的国标 ID。"""
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from app.models.platform import ParentPlatform

    print("=" * 70)
    print("所有已注册的设备 / 平台国标 ID")
    print("=" * 70)
    print(f"数据库 URI: {settings.SQLALCHEMY_DATABASE_URI}")
    print()

    async with AsyncSessionLocal() as session:
        # Assets
        print("[Assets 表] 设备列表:")
        try:
            assets = (await session.execute(select(Asset))).scalars().all()
            if not assets:
                print("  (空)")
            else:
                print(f"  共 {len(assets)} 条记录:")
                for a in assets:
                    print(f"    - gb_id={a.gb_id}, name={a.name or '(unnamed)'}, status={'online' if a.status == 1 else 'offline'}, password={'set' if a.password else '(empty)'}")
        except Exception as e:
            print(f"  [ERROR] 查询 assets 失败: {e}")

        # ParentPlatforms
        print()
        print("[ParentPlatforms 表] 上级平台列表:")
        try:
            platforms = (await session.execute(select(ParentPlatform))).scalars().all()
            if not platforms:
                print("  (空)")
            else:
                print(f"  共 {len(platforms)} 条记录:")
                for p in platforms:
                    print(f"    - id={p.id}")
                    print(f"        server_gb_id={p.server_gb_id} (上级平台国标 ID)")
                    print(f"        client_gb_id={p.client_gb_id} (本平台在上级处的国标 ID)")
                    print(f"        server_ip={p.server_ip}:{p.server_port}, transport={p.transport}, enable={p.enable}")
                    print(f"        password={'set' if p.password else '(empty)'}")
        except Exception as e:
            print(f"  [ERROR] 查询 parent_platforms 失败: {e}")

    print()
    print("=" * 70)


async def diagnose(gb_id: str, device_password: str | None = None) -> dict:
    """诊断单个 gb_id 的认证失败根因。

    返回诊断结果 dict，包含：
      - matched_records: 数据库中匹配的记录列表
      - decrypt_results: 每条记录的解密结果
      - default_password: SIP_DEFAULT_PASSWORD 值
      - device_password_provided: 用户提供的设备本地密码
      - recommendations: 修复建议列表
    """
    from app.core.config import settings
    from app.core.field_crypto import decrypt_field, encrypt_field
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from app.models.platform import ParentPlatform

    result = {
        "gb_id": gb_id,
        "matched_records": [],
        "decrypt_results": [],
        "default_password": settings.SIP_DEFAULT_PASSWORD,
        "device_password_provided": device_password,
        "recommendations": [],
    }

    print("=" * 70)
    print(f"诊断设备 / 平台: {gb_id}")
    print("=" * 70)
    print(f"数据库 URI: {settings.SQLALCHEMY_DATABASE_URI}")
    print(f"FIELD_ENCRYPTION_KEY: {_mask(settings.FIELD_ENCRYPTION_KEY)}")
    print(f"SIP_DEFAULT_PASSWORD: {_mask(settings.SIP_DEFAULT_PASSWORD)}")
    print(f"SIP_DOMAIN: {settings.SIP_DOMAIN}")
    print()

    # 验证 FIELD_ENCRYPTION_KEY 是否可解密已加密的测试向量
    print("[1/4] FIELD_ENCRYPTION_KEY 完整性自检...")
    try:
        test_plain = "diagnose_sip_device_selftest"
        encrypted = encrypt_field(test_plain, purpose="sip_password")
        decrypted = decrypt_field(encrypted, purpose="sip_password", allow_plaintext=False)
        if decrypted == test_plain:
            print(f"  [OK] FIELD_ENCRYPTION_KEY 可正常加解密字段 (round-trip 成功)")
        else:
            print(f"  [FAIL] FIELD_ENCRYPTION_KEY round-trip 失败：期望 {test_plain!r}, 实际 {decrypted!r}")
            result["recommendations"].append(
                "FIELD_ENCRYPTION_KEY 自检失败 — 请检查 .env 中的 FIELD_ENCRYPTION_KEY 是否完整、是否为 64 位十六进制字符串"
            )
    except Exception as e:
        print(f"  [FAIL] FIELD_ENCRYPTION_KEY 自检异常: {e}")
        result["recommendations"].append(
            f"FIELD_ENCRYPTION_KEY 自检异常: {e} — 请检查 .env 中的 FIELD_ENCRYPTION_KEY 配置"
        )
    print()

    # 2. 查询三类记录
    print("[2/4] 数据库记录匹配...")
    async with AsyncSessionLocal() as session:
        # Asset match
        asset = None
        try:
            asset = (await session.execute(
                select(Asset).where(Asset.gb_id == gb_id)
            )).scalars().first()
        except Exception as e:
            print(f"  [ERROR] 查询 assets 失败: {e}")

        if asset:
            print(f"  [Asset] 匹配成功: id={asset.id}, name={asset.name or '(unnamed)'}, status={'online' if asset.status == 1 else 'offline'}")
            print(f"          password={'set' if asset.password else '(empty)'}, ip_addr={asset.ip_addr}, port={asset.port}")
            result["matched_records"].append({"table": "assets", "record": asset})
        else:
            print(f"  [Asset] 未匹配 — assets 表中无 gb_id={gb_id} 的记录")

        # ParentPlatform client match (本平台作为下级)
        pf_client = None
        try:
            pf_client = (await session.execute(
                select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id)
            )).scalars().first()
        except Exception as e:
            print(f"  [ERROR] 查询 parent_platforms (client_gb_id) 失败: {e}")

        if pf_client:
            print(f"  [ParentPlatform.client_gb_id] 匹配成功: id={pf_client.id}, server_gb_id={pf_client.server_gb_id}")
            print(f"          password={'set' if pf_client.password else '(empty)'}, server_ip={pf_client.server_ip}:{pf_client.server_port}")
            result["matched_records"].append({"table": "parent_platforms_client", "record": pf_client})
        else:
            print(f"  [ParentPlatform.client_gb_id] 未匹配")

        # ParentPlatform server match (本平台作为上级)
        pf_server = None
        try:
            pf_server = (await session.execute(
                select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
            )).scalars().first()
        except Exception as e:
            print(f"  [ERROR] 查询 parent_platforms (server_gb_id) 失败: {e}")

        if pf_server:
            print(f"  [ParentPlatform.server_gb_id] 匹配成功: id={pf_server.id}, client_gb_id={pf_server.client_gb_id}")
            print(f"          password={'set' if pf_server.password else '(empty)'}, server_ip={pf_server.server_ip}:{pf_server.server_port}")
            result["matched_records"].append({"table": "parent_platforms_server", "record": pf_server})
        else:
            print(f"  [ParentPlatform.server_gb_id] 未匹配")
    print()

    # 3. 解密所有匹配记录的 password
    print("[3/4] 解密匹配记录的 password 字段...")
    for entry in result["matched_records"]:
        rec = entry["record"]
        table = entry["table"]
        try:
            if not rec.password:
                print(f"  [{table}] password 字段为空 — 设备需用空密码或默认密码认证")
                result["decrypt_results"].append({"table": table, "status": "empty", "plaintext": None})
                continue
            plaintext = decrypt_field(rec.password, purpose="sip_password", allow_plaintext=False)
            if plaintext is None:
                print(f"  [{table}] 解密失败 — FIELD_ENCRYPTION_KEY 与加密时不一致，或数据损坏")
                result["decrypt_results"].append({"table": table, "status": "decrypt_failed", "plaintext": None})
            else:
                print(f"  [{table}] 解密成功 — 明文密码: {_mask(plaintext)}")
                result["decrypt_results"].append({"table": table, "status": "ok", "plaintext": plaintext})
        except Exception as e:
            print(f"  [{table}] 解密异常: {e}")
            result["decrypt_results"].append({"table": table, "status": "exception", "plaintext": None, "error": str(e)})
    print()

    # 4. 比对密码一致性
    print("[4/4] 密码一致性比对...")
    default_pwd = settings.SIP_DEFAULT_PASSWORD
    device_provided = device_password

    # 收集所有已解密明文密码
    db_plaintexts = [r["plaintext"] for r in result["decrypt_results"] if r.get("plaintext")]

    if device_provided:
        if device_provided == default_pwd:
            print(f"  [INFO] 设备本地密码 == SIP_DEFAULT_PASSWORD ({_mask(default_pwd)})")
        else:
            print(f"  [WARN] 设备本地密码 ({_mask(device_provided)}) != SIP_DEFAULT_PASSWORD ({_mask(default_pwd)})")

        if db_plaintexts:
            if any(p == device_provided for p in db_plaintexts):
                print(f"  [OK] 设备本地密码与 DB 中至少一条记录的明文密码一致")
            else:
                print(f"  [FAIL] 设备本地密码与 DB 所有记录的明文密码都不一致 — 需修正 DB 密码")
                result["recommendations"].append(
                    f"使用 --fix-set-password 修正 DB 中 {gb_id} 的密码为设备本地真实密码"
                )
        else:
            print(f"  [INFO] DB 中无可解密的明文密码 — 无法比对，但设备本地密码已提供")
    else:
        print(f"  [INFO] 未提供 --device-password 参数，跳过设备本地密码比对")
        print(f"         提示: 如已知设备本地密码，可加上 --device-password <密码> 进行精确比对")
    print()

    # 综合诊断结论
    print("=" * 70)
    print("诊断结论与修复建议")
    print("=" * 70)

    if not result["matched_records"]:
        print(f"[根因] 数据库中没有 gb_id={gb_id} 的任何记录 (assets / parent_platforms 三类全部未匹配)")
        print(f"       日志中 candidates=1 表示系统只能用 SIP_DEFAULT_PASSWORD={_mask(default_pwd)} 作为候选密码")
        print(f"       但设备本地配置的密码与默认密码不一致，导致 Response mismatch")
        print()
        print("[方案 A] 在后台「设备管理」页面添加该设备，并填入设备本地真实密码 (推荐)")
        print("        1) 登录 PyGBSentry 后台 → 设备管理 → 新增设备")
        print(f"        2) 国标 ID 填: {gb_id}")
        print("        3) 密码 填: 设备本地真实密码 (注意：不是 SIP_DEFAULT_PASSWORD，除非设备确实用的默认密码)")
        print("        4) 保存后设备下一次 REGISTER 即可通过认证")
        print()
        print("[方案 B] 修改设备本地密码为 SIP_DEFAULT_PASSWORD (适合设备密码可改的场景)")
        print(f"        1) 登录设备 Web 后台 → SIP/平台设置 → 把密码改为 {default_pwd}")
        print("        2) 保存并重启设备")
        print("        3) 设备下次 REGISTER 会使用默认密码，与系统候选密码一致 → 认证通过")
        print()
        print("[方案 C] 使用本脚本的 --fix-add-device 命令直接添加设备记录 (使用 SIP_DEFAULT_PASSWORD 加密)")
        print(f"        命令: python scripts/diagnose_sip_device.py {gb_id} --fix-add-device")
        print("        注意: 该方案假设设备本地密码与 SIP_DEFAULT_PASSWORD 一致，如不一致仍会失败")
        result["recommendations"].append("DB 中无设备记录 → 在后台添加设备 或 用 --fix-add-device 命令添加 或 修改设备密码为默认密码")
    else:
        has_decrypt_fail = any(r["status"] == "decrypt_failed" for r in result["decrypt_results"])
        if has_decrypt_fail:
            print(f"[根因] DB 中存在 {gb_id} 的记录，但 password 字段无法解密")
            print("       原因: FIELD_ENCRYPTION_KEY 与加密时不一致，或密文数据损坏")
            print()
            print("[方案] 使用 scripts/reencrypt_fields.py 工具用旧密钥重新加密:")
            print("       1) 停止后端服务")
            print("       2) OLD_FIELD_ENCRYPTION_KEY=<旧密钥> python scripts/reencrypt_fields.py")
            print("       3) 重启后端服务")
            print()
            print("[方案] 如已知设备本地密码，可直接使用本脚本 --fix-set-password 命令覆盖写入:")
            print(f"       python scripts/diagnose_sip_device.py {gb_id} --fix-set-password <设备真实密码>")
            result["recommendations"].append("FIELD_ENCRYPTION_KEY 不匹配 → 用 reencrypt_fields.py 重新加密 或 --fix-set-password 覆盖")
        else:
            # DB 记录存在且可解密，但日志仍显示认证失败 → 设备本地密码与 DB 明文密码不一致
            print(f"[根因] DB 中存在 {gb_id} 的记录且 password 可解密，但设备本地密码与 DB 明文密码不一致")
            print("       日志显示 Response mismatch = 设备计算的 digest 与服务端计算的 digest 不同")
            print()
            print("[方案] 确认设备本地真实密码后，使用本脚本覆盖写入 DB:")
            print(f"       python scripts/diagnose_sip_device.py {gb_id} --fix-set-password <设备真实密码>")
            print()
            print("[方案] 或修改设备本地密码为 DB 中的明文密码 (DB 中已解密的明文见上方输出)")
            result["recommendations"].append("设备本地密码与 DB 不一致 → --fix-set-password 覆盖 或 修改设备本地密码")
    print()
    print("=" * 70)
    return result


async def fix_add_device(gb_id: str) -> None:
    """在 assets 表中添加缺失的设备记录，password 用 SIP_DEFAULT_PASSWORD 加密。"""
    from app.core.config import settings
    from app.core.field_crypto import encrypt_field
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from sqlalchemy import select

    print("=" * 70)
    print(f"[FIX] 添加设备 {gb_id} 到 assets 表 (使用 SIP_DEFAULT_PASSWORD 加密)")
    print("=" * 70)
    print(f"SIP_DEFAULT_PASSWORD: {_mask(settings.SIP_DEFAULT_PASSWORD)}")
    print()

    async with AsyncSessionLocal() as session:
        # 检查是否已存在
        existing = (await session.execute(
            select(Asset).where(Asset.gb_id == gb_id)
        )).scalars().first()
        if existing:
            print(f"[SKIP] 设备 {gb_id} 已存在于 assets 表 (id={existing.id}) — 无需重复添加")
            print("       如需更新密码，请使用 --fix-set-password 命令")
            return

        # 创建新记录
        encrypted_pwd = encrypt_field(settings.SIP_DEFAULT_PASSWORD, purpose="sip_password")
        new_asset = Asset(
            id=uuid.uuid4().hex,
            gb_id=gb_id,
            name=f"Auto-added {gb_id}",
            password=encrypted_pwd,
            status=0,
        )
        session.add(new_asset)
        await session.commit()
        print(f"[OK] 已添加设备 {gb_id} (id={new_asset.id})")
        print(f"     password 已用 SIP_DEFAULT_PASSWORD 加密写入")
        print()
        print("[注意] 请确认设备本地配置的密码确实是 SIP_DEFAULT_PASSWORD，否则仍会认证失败")
        print("       如设备使用其他密码，请改用 --fix-set-password <真实密码> 命令")
        print()
        print("[下一步] 重启后端服务，观察设备 REGISTER 是否成功")
    print("=" * 70)


async def fix_set_password(gb_id: str, plaintext_password: str) -> None:
    """将设备本地密码写入 DB 中已存在的 Asset 记录 (自动加密)。

    如果 DB 中无任何记录，会自动创建 Asset 记录。
    """
    from app.core.field_crypto import encrypt_field
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from app.models.platform import ParentPlatform
    from sqlalchemy import select

    print("=" * 70)
    print(f"[FIX] 将设备 {gb_id} 的本地密码写入 DB")
    print("=" * 70)
    print(f"明文密码: {_mask(plaintext_password)}")
    print()

    encrypted_pwd = encrypt_field(plaintext_password, purpose="sip_password")
    updated_count = 0

    async with AsyncSessionLocal() as session:
        # 1. Asset
        asset = (await session.execute(
            select(Asset).where(Asset.gb_id == gb_id)
        )).scalars().first()
        if asset:
            asset.password = encrypted_pwd
            updated_count += 1
            print(f"[OK] 已更新 assets 表记录 (id={asset.id}, gb_id={asset.gb_id}) 的 password")
        else:
            # 自动创建 Asset 记录
            new_asset = Asset(
                id=uuid.uuid4().hex,
                gb_id=gb_id,
                name=f"Auto-added {gb_id}",
                password=encrypted_pwd,
                status=0,
            )
            session.add(new_asset)
            updated_count += 1
            print(f"[OK] assets 表无记录，已自动创建 (id={new_asset.id}, gb_id={gb_id})")

        # 2. ParentPlatform client_gb_id
        pf_client = (await session.execute(
            select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id)
        )).scalars().first()
        if pf_client:
            pf_client.password = encrypted_pwd
            updated_count += 1
            print(f"[OK] 已更新 parent_platforms (client_gb_id={gb_id}) 记录的 password")

        # 3. ParentPlatform server_gb_id
        pf_server = (await session.execute(
            select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
        )).scalars().first()
        if pf_server:
            pf_server.password = encrypted_pwd
            updated_count += 1
            print(f"[OK] 已更新 parent_platforms (server_gb_id={gb_id}) 记录的 password")

        await session.commit()
    print()
    print(f"[汇总] 共更新/创建 {updated_count} 条记录")
    print()
    print("[下一步] 重启后端服务，观察设备 REGISTER 是否成功")
    print("=" * 70)


async def clear_blacklist(ip: str | None = None) -> None:
    """清理 IP 黑名单和认证失败计数。

    不带参数时清理全部黑名单；带 IP 时仅清理指定 IP。
    同时清理内存中的认证失败计数（Redis / 本地后端）。
    """
    from app.db.session import AsyncSessionLocal
    from app.models.ip_blacklist import IpBlacklist
    from sqlalchemy import delete, select

    print("=" * 70)
    print(f"[CLEAR] 清理 IP 黑名单 {'(IP=' + ip + ')' if ip else '(全部)'}")
    print("=" * 70)

    async with AsyncSessionLocal() as session:
        if ip:
            # 查询是否存在
            existing = (await session.execute(
                select(IpBlacklist).where(IpBlacklist.ip == ip)
            )).scalars().first()
            if existing:
                print(f"  [FOUND] 黑名单中存在 IP {ip}: reason={existing.reason}")
                await session.execute(delete(IpBlacklist).where(IpBlacklist.ip == ip))
                await session.commit()
                print(f"  [OK] 已从 DB 黑名单表中删除 IP {ip}")
            else:
                print(f"  [INFO] DB 黑名单表中无 IP {ip} 的记录")
        else:
            count = (await session.execute(select(IpBlacklist))).scalars().all()
            if count:
                print(f"  [FOUND] DB 黑名单中共 {len(count)} 条记录:")
                for item in count:
                    print(f"    - ip={item.ip}, reason={item.reason}")
                await session.execute(delete(IpBlacklist))
                await session.commit()
                print(f"  [OK] 已清空 DB 黑名单表 ({len(count)} 条)")
            else:
                print(f"  [INFO] DB 黑名单表为空")

    # 清理内存中的认证失败计数（Redis 或本地后端）
    try:
        from app.sip.state_backend import get_sip_state_backend
        backend = get_sip_state_backend()
        if ip:
            await backend.clear_auth_failure(ip)
            print(f"  [OK] 已清理认证失败计数: IP {ip}")
        else:
            cleaned = await backend.cleanup_auth_failures()
            if cleaned is not None:
                print(f"  [OK] 已清理全部认证失败计数 ({cleaned} 条)")
            else:
                print(f"  [OK] 已调用 cleanup_auth_failures")
    except Exception as e:
        print(f"  [WARN] 清理认证失败计数异常 (非致命): {e}")

    # 重新加载 SIP 服务器的黑名单缓存
    try:
        from app.sip.server import sip_server
        if hasattr(sip_server, "reload_ip_blacklist"):
            await sip_server.reload_ip_blacklist()
            print(f"  [OK] 已重新加载 SIP 服务器黑名单缓存")
        else:
            print(f"  [INFO] SIP 服务器无 reload_ip_blacklist 方法，重启后端以刷新缓存")
    except Exception as e:
        print(f"  [WARN] 重新加载黑名单缓存异常 (非致命): {e}")
        print(f"         重启后端服务可强制刷新缓存")

    print()
    print("[下一步] 设备下一次 REGISTER 不会被黑名单拦截，可正常走认证流程")
    print("=" * 70)


async def verify_config() -> None:
    """验证服务器实际加载的 SIP 配置（byte-for-byte）。

    用于排查 .env 中的密码与 settings 实际加载的密码不一致的问题
    （如环境变量覆盖、空格、不可见字符等）。
    """
    from app.core.config import settings

    print("=" * 70)
    print("[VERIFY] 服务器实际加载的 SIP 配置")
    print("=" * 70)
    print(f"APP_ENV: {settings.APP_ENV!r}")
    print(f"SIP_IP: {settings.SIP_IP!r}")
    print(f"SIP_PORT: {settings.SIP_PORT!r}")
    print(f"SIP_ID: {settings.SIP_ID!r}")
    print(f"SIP_DOMAIN: {settings.SIP_DOMAIN!r}")
    print()
    print(f"SIP_DEFAULT_PASSWORD (repr): {settings.SIP_DEFAULT_PASSWORD!r}")
    print(f"SIP_DEFAULT_PASSWORD (len):  {len(settings.SIP_DEFAULT_PASSWORD)}")
    print(f"SIP_DEFAULT_PASSWORD (hex):  {settings.SIP_DEFAULT_PASSWORD.encode('utf-8').hex()}")
    print()
    print(f"FIELD_ENCRYPTION_KEY (repr): {settings.FIELD_ENCRYPTION_KEY!r}")
    print(f"FIELD_ENCRYPTION_KEY (len):  {len(settings.FIELD_ENCRYPTION_KEY)}")
    print()

    # 验证密码是否有可疑的空格或不可见字符
    pwd = settings.SIP_DEFAULT_PASSWORD
    suspicious = []
    if pwd != pwd.strip():
        suspicious.append("首尾有空格")
    if "\n" in pwd or "\r" in pwd:
        suspicious.append("包含换行符")
    if "\t" in pwd:
        suspicious.append("包含制表符")
    if any(ord(c) < 32 or ord(c) > 126 for c in pwd):
        suspicious.append("包含非 ASCII 可打印字符")
    if suspicious:
        print(f"[WARN] SIP_DEFAULT_PASSWORD 存在可疑字符: {', '.join(suspicious)}")
        print("       这可能导致 Digest 计算时密码不一致 → Response mismatch")
    else:
        print("[OK] SIP_DEFAULT_PASSWORD 无可疑字符 (纯 ASCII 可打印)")

    # 检查是否被环境变量覆盖
    import os
    env_pwd = os.environ.get("SIP_DEFAULT_PASSWORD")
    if env_pwd is not None:
        print()
        print(f"[INFO] 检测到环境变量 SIP_DEFAULT_PASSWORD 已设置:")
        print(f"       环境变量值 (repr): {env_pwd!r}")
        if env_pwd == pwd:
            print(f"       [OK] 环境变量与 .env 一致")
        else:
            print(f"       [WARN] 环境变量与 .env 不一致！环境变量会覆盖 .env")
            print(f"              .env 加载值: {pwd!r}")
            print(f"              环境变量值:   {env_pwd!r}")
    else:
        print("[INFO] 未检测到环境变量 SIP_DEFAULT_PASSWORD，使用 .env 中的值")

    print()
    print("=" * 70)


async def simulate_digest(password: str) -> None:
    """用给定密码模拟 SIP Digest 计算，验证算法正确性。

    用户可对比模拟结果与日志中实际 Authorization 头的 response 字段，
    判断密码是否一致。
    """
    from app.sip.auth import DigestAuth

    print("=" * 70)
    print("[SIMULATE] SIP Digest 计算模拟")
    print("=" * 70)
    print(f"测试密码 (repr): {password!r}")
    print()

    # 模拟一组典型的 Digest 参数
    test_params = {
        "username": "34020000002000000002",
        "realm": "3402000000",
        "method": "REGISTER",
        "uri": "sip:3402000000:15060",
        "nonce": "test_nonce_for_verification",
        "nc": "00000001",
        "cnonce": "test_cnonce",
        "qop": "auth",
    }

    print("测试参数:")
    for k, v in test_params.items():
        print(f"  {k}: {v!r}")
    print()

    # 分别用 MD5 和 SHA-256 计算
    for algo in ["MD5", "SHA-256"]:
        expected = DigestAuth.calculate_response(
            username=test_params["username"],
            password=password,
            realm=test_params["realm"],
            method=test_params["method"],
            uri=test_params["uri"],
            nonce=test_params["nonce"],
            nc=test_params["nc"],
            cnonce=test_params["cnonce"],
            qop=test_params["qop"],
            algorithm=algo,
            entity_body="",
        )
        print(f"  [{algo}] expected response: {expected}")

    print()
    print("[提示] 若要精确比对设备实际发送的 response，请:")
    print("       1) 在 .env 中设置 SIP_DEBUG_TRACE_ENABLED=true")
    print("       2) 重启后端")
    print("       3) 等待设备 REGISTER 失败后，在 logs/app.log 中搜索 'SIP_TRACE'")
    print("       4) SIP_TRACE 日志会包含 authorization 字段（已脱敏 cnonce）")
    print("       5) 将 SIP_TRACE 日志内容发给开发者进行精确分析")
    print("=" * 70)


# 正则：解析 [AUTH_DEBUG] 中的 key=value 字段
# 形如 auth.username='34020000002000000002', auth.realm='', auth.algorithm='SHA-256'
_AUTH_DEBUG_FIELD_RE = re.compile(
    r"(?P<key>[a-zA-Z_.]+)\s*=\s*(?P<value>'[^']*'|[^\s,]+(?:\.\.\.)?)"
)


def _parse_auth_debug_line(line: str) -> dict:
    """从 [AUTH_DEBUG] 日志行中解析出所有 key=value 字段。

    返回 dict，例如：
        {
            'auth.username': '34020000002000000002',
            'auth.realm': '',
            'auth.algorithm': 'SHA-256',
            ...
            'server.expected_resp_with_default_pwd': 'b26xxxxxxx1af',
            'server.expected_resp_match_default_pwd': 'False',
        }
    """
    # 截取 [AUTH_DEBUG] 之后的内容
    marker = "[AUTH_DEBUG] "
    idx = line.find(marker)
    if idx < 0:
        return {}
    raw = line[idx + len(marker):]
    result: dict = {}
    for m in _AUTH_DEBUG_FIELD_RE.finditer(raw):
        key = m.group("key")
        value = m.group("value")
        # 去掉单引号
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        result[key] = value
    return result


def _find_latest_auth_debug(log_path: Path) -> str | None:
    """从日志文件中找到最后一条 [AUTH_DEBUG] 行。

    逐块从文件末尾向前扫描，避免读取整个大文件。
    """
    if not log_path.exists():
        return None
    # 简单做法：从末尾按块向前扫描
    BLOCK = 65536
    file_size = log_path.stat().st_size
    with open(log_path, "rb") as f:
        # 读最后一块
        offset = max(0, file_size - BLOCK * 8)  # 最后 512KB
        f.seek(offset)
        data = f.read()
    text = data.decode("utf-8", errors="ignore")
    # 找到最后一个 [AUTH_DEBUG] 的位置
    idx = text.rfind("[AUTH_DEBUG]")
    if idx < 0:
        return None
    # 从该位置向后找行尾
    end = text.find("\n", idx)
    if end < 0:
        end = len(text)
    return text[idx:end]


async def verify_against_log(passwords: list[str], log_path: Path | None = None) -> None:
    """从日志中读取最新一条 [AUTH_DEBUG] 行，用给定密码列表计算 expected_response 对比。

    用法：
        python scripts/diagnose_sip_device.py --verify-against-log <密码1> <密码2> ...

    说明：
        1. 自动读取 logs/app.log 中最新一条 [AUTH_DEBUG] 行
        2. 解析出完整的 auth.* 和 server.* 字段（包括 nonce/cnonce/response）
        3. 用每个密码 + client_realm 和 server_realm 分别计算 expected_response
        4. 与设备实际 auth.response 对比，输出匹配结果
        5. 同时验证 server 计算的 expected_resp_with_default_pwd 是否正确

    前提：
        - handlers.py 已部署修复版本（移除 nonce/cnonce/response 脱敏）
        - 日志中已有最新一次 REGISTER 失败的 [AUTH_DEBUG] 行
    """
    from app.sip.auth import DigestAuth

    if log_path is None:
        log_path = Path(__file__).resolve().parent.parent / "logs" / "app.log"

    print("=" * 70)
    print("[VERIFY] 从日志中读取最新 [AUTH_DEBUG] 行进行精确对比")
    print("=" * 70)
    print(f"日志文件: {log_path}")
    print(f"候选密码数: {len(passwords)}")
    for i, pw in enumerate(passwords, 1):
        print(f"  [{i}] {pw!r} (len={len(pw)})")
    print()

    latest_line = _find_latest_auth_debug(log_path)
    if not latest_line:
        print(f"[ERROR] 在 {log_path} 中未找到 [AUTH_DEBUG] 行")
        print()
        print("[提示] 请确保：")
        print("  1) handlers.py 已部署包含 [AUTH_DEBUG] 输出的版本")
        print("  2) EasyGBS 已尝试 REGISTER 且失败 (产生 AUTH_DEBUG 日志)")
        print("  3) handlers.py 已部署移除脱敏的版本 (nonce/cnonce/response 完整输出)")
        return

    fields = _parse_auth_debug_line(latest_line)
    if not fields:
        print("[ERROR] 解析 [AUTH_DEBUG] 字段失败")
        print(f"原始行: {latest_line[:200]}...")
        return

    print("-" * 70)
    print("[1] 从日志解析出的字段:")
    print("-" * 70)
    for k in sorted(fields.keys()):
        v = fields[k]
        # 脱敏 SIP_DEFAULT_PASSWORD 显示
        if "DEFAULT_PASSWORD" in k and v not in ("", "None"):
            v_display = f"{v[:3]}***{v[-3:]}" if len(v) > 6 else "*" * len(v)
            print(f"  {k} = {v_display}")
        else:
            print(f"  {k} = {v!r}")
    print()

    # 提取关键字段
    auth_username = fields.get("auth.username", "")
    auth_realm = fields.get("auth.realm", "")
    auth_uri = fields.get("auth.uri", "")
    auth_algorithm = fields.get("auth.algorithm", "MD5")
    auth_qop = fields.get("auth.qop", "")
    auth_nc = fields.get("auth.nc", "")
    auth_cnonce = fields.get("auth.cnonce", "")
    auth_nonce = fields.get("auth.nonce", "")
    auth_response = fields.get("auth.response", "")
    server_realm = fields.get("server.realm_used_in_challenge", "")
    server_expected_default = fields.get("server.expected_resp_with_default_pwd", "")
    server_expected_default_server_realm = fields.get(
        "server.expected_resp_with_default_pwd_using_server_realm", ""
    )

    # 校验关键字段是否完整
    missing = []
    if not auth_nonce or "***" in auth_nonce:
        missing.append("auth.nonce")
    if not auth_cnonce:
        missing.append("auth.cnonce")
    if not auth_response or "***" in auth_response:
        missing.append("auth.response")
    if missing:
        print(f"[ERROR] 关键字段未完整解析或仍被脱敏: {missing}")
        print()
        print("[提示] 这些字段是设备发送的，不是敏感数据，应该完整输出。")
        print("       请确保 handlers.py 已部署修复版本（移除 nonce/cnonce/response 脱敏）。")
        print("       修复后的 handlers.py 中 [AUTH_DEBUG] 输出应包含:")
        print("         auth.nonce='完整nonce值', auth.response='完整response值'")
        return

    # 检查 nonce 是否含 *** （脱敏标志）
    if "***" in auth_nonce:
        print(f"[ERROR] auth.nonce 仍被脱敏: {auth_nonce!r}")
        print("        请部署修复后的 handlers.py（移除 nonce 脱敏），等下次 REGISTER 失败后重试。")
        return

    print("-" * 70)
    print("[2] 验证服务器计算结果是否正确（用 SIP_DEFAULT_PASSWORD + 日志参数复算）:")
    print("-" * 70)
    # 如果 server.expected_resp_with_default_pwd 字段存在，验证服务器计算是否正确
    if server_expected_default and server_expected_default not in ("", "None"):
        # 用 auth.realm（client_realm）计算
        recalc_client = DigestAuth.calculate_response(
            username=auth_username,
            password="",  # 用空密码，仅用于检查算法路径
            realm=auth_realm,
            method="REGISTER",
            uri=auth_uri,
            nonce=auth_nonce,
            nc=auth_nc,
            cnonce=auth_cnonce,
            qop=auth_qop,
            algorithm=auth_algorithm,
            entity_body="",
        )
        # 这里只能验证算法路径，无法验证密码（因为我们不知道 SIP_DEFAULT_PASSWORD 的完整值）
        print(f"  服务器计算 expected_resp_with_default_pwd = {server_expected_default}")
        print(f"  设备实际 auth.response                    = {auth_response}")
        print(f"  匹配: {'YES' if server_expected_default == auth_response else 'NO'}")
        print()
    if server_expected_default_server_realm and server_expected_default_server_realm not in ("", "None"):
        print(f"  服务器计算 expected_resp_with_default_pwd_using_server_realm = {server_expected_default_server_realm}")
        print(f"  设备实际 auth.response                                       = {auth_response}")
        print(f"  匹配: {'YES' if server_expected_default_server_realm == auth_response else 'NO'}")
        print()

    print("-" * 70)
    print("[3] 用候选密码列表计算 expected_response 并与 auth.response 对比:")
    print("-" * 70)

    realms_to_try = []
    if auth_realm:
        realms_to_try.append(("client_realm", auth_realm))
    if server_realm and server_realm != auth_realm:
        realms_to_try.append(("server_realm", server_realm))
    if not auth_realm and not server_realm:
        realms_to_try.append(("empty_realm", ""))

    found_match = False
    for pw in passwords:
        for realm_label, realm_value in realms_to_try:
            expected = DigestAuth.calculate_response(
                username=auth_username,
                password=pw,
                realm=realm_value,
                method="REGISTER",
                uri=auth_uri,
                nonce=auth_nonce,
                nc=auth_nc,
                cnonce=auth_cnonce,
                qop=auth_qop,
                algorithm=auth_algorithm,
                entity_body="",
            )
            match = (expected == auth_response)
            mark = "✓ MATCH" if match else "  no"
            print(f"  {mark}  password={pw!r} (len={len(pw)}), realm={realm_label}={realm_value!r}")
            if not match:
                print(f"           calculated = {expected}")
                print(f"           actual     = {auth_response}")
            else:
                found_match = True
                print()
                print(f"  *** 找到匹配！密码 {pw!r} + {realm_label} 计算结果与设备 response 一致 ***")

    print()
    if found_match:
        print("[结论] 候选密码中存在匹配项。请将该密码配置到 EasyGBS 或 PyGBSentry 中。")
    else:
        print("[结论] 候选密码中没有匹配项。可能原因：")
        print("  1) 设备实际密码不在候选列表中 → 请确认 EasyGBS 实际填写的密码（每个字符）")
        print("  2) 设备用了不同的 algorithm/qop → 检查日志 auth.algorithm 和 auth.qop")
        print("  3) 设备用了不同的 uri → 检查日志 auth.uri")
        print("  4) 设备用了 SESS 算法 → 检查日志 auth.algorithm 是否为 SHA-256-SESS 或 MD5-SESS")
        print()
        print("[建议] 在 EasyGBS 平台界面中重新查看实际填写的密码，特别注意：")
        print("  - 末尾是否有空格或换行符")
        print("  - 是否包含中文字符或全角字符")
        print("  - 大小写是否正确")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SIP 设备注册认证诊断脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("gb_id", nargs="?", help="待诊断的设备/平台国标 ID (20 位)")
    parser.add_argument("--list", action="store_true", help="列出所有 assets / parent_platforms 中的国标 ID")
    parser.add_argument("--device-password", help="设备本地真实密码 (用于精确比对 DB 与设备是否一致)")
    parser.add_argument("--fix-add-device", action="store_true", help="修复模式: 在 assets 表添加缺失的设备 (使用 SIP_DEFAULT_PASSWORD 加密)")
    parser.add_argument("--fix-set-password", metavar="PASSWORD", help="修复模式: 将设备真实密码写入已存在的 DB 记录 (自动加密)")
    parser.add_argument("--clear-blacklist", nargs="?", const="ALL", metavar="IP",
                        help="清理 IP 黑名单和认证失败计数。不带参数时清理全部；带 IP 时仅清理指定 IP")
    parser.add_argument("--verify-config", action="store_true",
                        help="验证服务器实际加载的 SIP 配置 (打印 repr 检查空格/不可见字符)")
    parser.add_argument("--simulate-digest", metavar="PASSWORD",
                        help="用给定密码模拟 SIP Digest 计算，验证算法正确性")
    parser.add_argument("--verify-against-log", nargs="+", metavar="PASSWORD",
                        help="从 logs/app.log 读取最新 [AUTH_DEBUG] 行，用给定候选密码列表 "
                             "(可多个) 计算 expected_response 与 auth.response 对比，定位密码不一致根因")
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_all_devices())
        return 0

    if args.verify_config:
        asyncio.run(verify_config())
        return 0

    if args.simulate_digest:
        asyncio.run(simulate_digest(args.simulate_digest))
        return 0

    if args.verify_against_log:
        asyncio.run(verify_against_log(args.verify_against_log))
        return 0

    if args.clear_blacklist:
        ip = None if args.clear_blacklist == "ALL" else args.clear_blacklist
        asyncio.run(clear_blacklist(ip))
        return 0

    if not args.gb_id:
        parser.error("必须提供 gb_id 参数，或使用 --list / --clear-blacklist / --verify-config / --simulate-digest / --verify-against-log")

    if len(args.gb_id) != 20:
        # 国标 ID 应为 20 位，但部分平台可能使用其他长度，仅警告不阻断
        print(f"[WARN] gb_id={args.gb_id} 长度 {len(args.gb_id)} != 20，仍继续诊断")

    if args.fix_add_device and args.fix_set_password:
        parser.error("--fix-add-device 与 --fix-set-password 互斥，请二选一")

    if args.fix_add_device:
        asyncio.run(fix_add_device(args.gb_id))
        return 0

    if args.fix_set_password:
        asyncio.run(fix_set_password(args.gb_id, args.fix_set_password))
        return 0

    asyncio.run(diagnose(args.gb_id, device_password=args.device_password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
