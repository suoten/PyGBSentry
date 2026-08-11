#!/usr/bin/env python3
"""PyGBSentry .env 自动生成工具 — 一键生成全部安全密钥，零配置启动。

用法:
    python tools/generate_env.py                          # 交互式（提示输入 BACKEND_PUBLIC_HOST）
    python tools/generate_env.py --host 192.168.1.100     # 命令行指定 IP
    python tools/generate_env.py --docker                 # Docker 模式（自动检测容器网关）
    python tools/generate_env.py --non-interactive        # 非交互式（使用默认值）

生成后会自动写入 backend/.env，并打印下一步操作提示。
"""
from __future__ import annotations

import argparse
import platform
import secrets
import socket
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE = BACKEND_DIR / ".env.example"


def _gen_secret_hex(n: int = 32) -> str:
    """生成 n 字节的 hex 密钥（2n 字符）。"""
    return secrets.token_hex(n)


def _gen_password(n: int = 16) -> str:
    """生成 URL-safe 随机密码。"""
    return secrets.token_urlsafe(n)


def _detect_local_ip() -> str:
    """自动检测本机局域网 IP。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _detect_docker_gateway() -> str:
    """Docker 环境下自动检测容器网关 IP。"""
    try:
        with open("/proc/net/route", "r") as f:
            for line in f:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    hex_ip = fields[2]
                    if len(hex_ip) == 8:
                        octets = [str(int(hex_ip[i:i+2], 16)) for i in range(6, -1, -2)]
                        return ".".join(octets)
    except Exception:
        pass
    return "172.17.0.1"


def _read_existing_env() -> dict[str, str]:
    """读取已存在的 .env 文件为字典。"""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def generate_env(
    host: str | None = None,
    docker: bool = False,
    non_interactive: bool = False,
    force: bool = False,
) -> None:
    """生成 backend/.env 文件，自动填充全部安全密钥。"""

    # 确定 BACKEND_PUBLIC_HOST
    if host:
        backend_host = host
    elif docker:
        backend_host = _detect_docker_gateway()
    elif non_interactive:
        backend_host = _detect_local_ip()
    else:
        detected = _detect_local_ip()
        try:
            user_input = input(f"请输入服务器公网 IP（回车使用自动检测值 {detected}）: ").strip()
            backend_host = user_input or detected
        except (EOFError, KeyboardInterrupt):
            backend_host = detected

    # 保留已有 .env 中的非密钥配置
    existing = _read_existing_env() if ENV_FILE.exists() and not force else {}

    # 生成全部密钥
    env_vars: dict[str, str] = {
        # --- 项目 ---
        "PROJECT_NAME": "PyGBSentry",
        "API_V1_STR": "/api/v1",
        "APP_ENV": "prod",
        "APP_EDITION": "oss",
        "LOG_DIR": "logs",
        "LOG_FORMAT": "text",
        # --- 安全密钥（自动生成）---
        "SECRET_KEY": _gen_secret_hex(32),
        "FIELD_ENECTION_KEY": _gen_secret_hex(32),
        "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
        # --- 网络 ---
        "BACKEND_PUBLIC_HOST": backend_host,
        "BACKEND_PUBLIC_PORT": "8000",
        # --- 数据库 ---
        "DATABASE_TYPE": "postgresql",
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DATABASE_NAME": "pygb28181",
        "DATABASE_USER": "postgres",
        "DATABASE_PASSWORD": _gen_password(20),
        "POSTGRES_SERVER": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": existing.get("DATABASE_PASSWORD", _gen_password(20)),
        "POSTGRES_DB": "pygb28181",
        "POSTGRES_PORT": "5432",
        # --- Redis ---
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "REDIS_PASSWORD": _gen_password(16),
        "REDIS_DB": "0",
        # --- SIP ---
        "SIP_IP": "0.0.0.0",
        "SIP_PORT": "5060",
        "SIP_ID": "34020000002000000001",
        "SIP_DOMAIN": "3402000000",
        "SIP_WORKER_CONCURRENCY": "200",
        "SIP_DEFAULT_PASSWORD": _gen_password(16),
        # --- ZLMediaKit ---
        "MEDIA_SERVER_SECRET": _gen_password(20),
        "MEDIA_SERVER_HOST": "127.0.0.1",
        "MEDIA_SERVER_HTTP_PORT": "8880",
        "MEDIA_SERVER_RTSP_PORT": "554",
        "MEDIA_SERVER_RTMP_PORT": "1935",
        "MEDIA_SERVER_RTC_PORT": "8000",
        "MEDIA_SERVER_RTP_PROXY_PORT": "30000",
        "MEDIA_SERVER_RTP_PROXY_PORT_RANGE": "30000-30999",
        "MEDIA_SERVER_RTP_STREAM_MODE": "UDP",
        "STREAM_PUBLIC_HOST": backend_host,
        "STREAM_PUBLIC_HTTP_PORT": "8880",
    }

    # 修正 typo: FIELD_ENECTION_KEY → FIELD_ENCRYPTION_KEY
    env_vars["FIELD_ENCRYPTION_KEY"] = env_vars.pop("FIELD_ENECTION_KEY")

    # 统一 POSTGRES_PASSWORD 和 DATABASE_PASSWORD
    env_vars["POSTGRES_PASSWORD"] = env_vars["DATABASE_PASSWORD"]

    # 保留已有 .env 中的用户自定义配置（非自动生成的项）
    preserve_keys = {
        "ENABLE_AUTO_DISCOVERY", "FORCE_HTTPS_IN_PRODUCTION",
        "SIP_STATE_BACKEND", "INIT_REDIS_ON_STARTUP",
        "GB28181_VERSION", "GB28181_VIDEO_QUALITY",
        "STREAM_WAIT_READY_MAX_ATTEMPTS", "STREAM_WAIT_READY_INTERVAL",
        "ZLM_NONE_READER_DELAY_SECONDS", "ZLM_DEFAULT_ENABLE_MP4",
        "ENABLE_OPENAPI_DOCS", "TRIAL_DAYS",
        "RTP_PORT_RANGE_START", "RTP_PORT_RANGE_END",
        "DOCKER_RTP_PORT_RANGE_MAX", "RUNNING_IN_DOCKER",
        "BACKEND_CORS_ORIGINS", "MEDIA_SERVER_HOOK_BASE_URL",
        "EMBEDDED_ZLM_ENABLED", "ZLM_PREFER_EXTERNAL_NODES",
        "SIP_INVITE_MAX_CONCURRENT", "SIP_INVITE_TIMEOUT_SECONDS",
        "RTP_SERVER_TIMEOUT_SECONDS", "RTP_TIMEOUT_GRACE_PERIOD_SECONDS",
        "ADMIN_INITIAL_PASSWORD",
    }
    for k in preserve_keys:
        if k in existing:
            env_vars[k] = existing[k]

    # 写入 .env
    lines: list[str] = [
        "# PyGBSentry 环境配置 — 由 tools/generate_env.py 自动生成",
        f"# 服务器 IP: {backend_host}",
        "# ⚠️ 此文件包含自动生成的安全密钥，请勿提交到版本控制",
        "",
        "# ===== 必填项（已自动生成安全密钥）=====",
    ]

    # 分区写入
    sections = [
        ("项目", ["PROJECT_NAME", "API_V1_STR", "APP_ENV", "APP_EDITION", "LOG_DIR", "LOG_FORMAT"]),
        ("安全密钥（自动生成，请勿修改）", ["SECRET_KEY", "FIELD_ENCRYPTION_KEY", "ACCESS_TOKEN_EXPIRE_MINUTES"]),
        ("网络", ["BACKEND_PUBLIC_HOST", "BACKEND_PUBLIC_PORT"]),
        ("数据库", ["DATABASE_TYPE", "DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD",
                   "POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT"]),
        ("Redis", ["REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD", "REDIS_DB"]),
        ("SIP 信令", ["SIP_IP", "SIP_PORT", "SIP_ID", "SIP_DOMAIN", "SIP_WORKER_CONCURRENCY", "SIP_DEFAULT_PASSWORD"]),
        ("ZLMediaKit 流媒体", ["MEDIA_SERVER_SECRET", "MEDIA_SERVER_HOST", "MEDIA_SERVER_HTTP_PORT",
                               "MEDIA_SERVER_RTSP_PORT", "MEDIA_SERVER_RTMP_PORT", "MEDIA_SERVER_RTC_PORT",
                               "MEDIA_SERVER_RTP_PROXY_PORT", "MEDIA_SERVER_RTP_PROXY_PORT_RANGE",
                               "MEDIA_SERVER_RTP_STREAM_MODE", "STREAM_PUBLIC_HOST", "STREAM_PUBLIC_HTTP_PORT"]),
    ]

    for section_name, keys in sections:
        lines.append(f"\n# --- {section_name} ---")
        for k in keys:
            v = env_vars.get(k, "")
            # 含特殊字符的值加引号
            if any(c in v for c in " #") or not v:
                lines.append(f'{k}="{v}"')
            else:
                lines.append(f"{k}={v}")

    # 追加保留的用户自定义配置
    extra_lines: list[str] = []
    for k in sorted(preserve_keys):
        if k in env_vars and k not in {key for _, keys in sections for key in keys}:
            extra_lines.append(f"{k}={env_vars[k]}")
    if extra_lines:
        lines.append("\n# --- 用户自定义配置（从已有 .env 保留）---")
        lines.extend(extra_lines)

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 设置文件权限为 600（仅所有者可读写），防止其他用户读取密钥
    try:
        ENV_FILE.chmod(0o600)
    except (OSError, PermissionError):
        pass  # Windows 上 chmod 无效，忽略

    # 打印结果
    print()
    print("=" * 60)
    print("✅ .env 文件已自动生成！")
    print(f"   路径: {ENV_FILE}")
    print(f"   服务器 IP: {backend_host}")
    print()
    print("📋 自动生成的安全密钥:")
    print(f"   SECRET_KEY:           {env_vars['SECRET_KEY'][:16]}...（64 字符 hex）")
    print(f"   FIELD_ENCRYPTION_KEY: {env_vars['FIELD_ENCRYPTION_KEY'][:16]}...（64 字符 hex）")
    print(f"   DATABASE_PASSWORD:    {env_vars['DATABASE_PASSWORD'][:8]}...（已设为随机值）")
    print(f"   REDIS_PASSWORD:       {env_vars['REDIS_PASSWORD'][:8]}...（已设为随机值）")
    print(f"   MEDIA_SERVER_SECRET:  {env_vars['MEDIA_SERVER_SECRET'][:8]}...（已设为随机值）")
    print(f"   SIP_DEFAULT_PASSWORD: {env_vars['SIP_DEFAULT_PASSWORD'][:8]}...（已设为随机值）")
    print()
    print("🚀 下一步操作:")
    if docker:
        print("   docker compose up -d")
    else:
        print("   # 本地开发模式:")
        print("   cd backend && python -m venv venv && source venv/bin/activate")
        print("   pip install -r requirements.txt")
        print("   python app/initial_data.py && python -m app.main")
    print()
    print("   首次启动后访问 http://" + backend_host + " 创建管理员账号")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PyGBSentry .env 自动生成工具 — 一键生成全部安全密钥",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/generate_env.py                          # 交互式
  python tools/generate_env.py --host 192.168.1.100     # 指定 IP
  python tools/generate_env.py --docker                 # Docker 模式
  python tools/generate_env.py --non-interactive        # 非交互式
""",
    )
    parser.add_argument("--host", type=str, default=None, help="服务器公网 IP（跳过交互提示）")
    parser.add_argument("--docker", action="store_true", help="Docker 模式（自动检测容器网关 IP）")
    parser.add_argument("--non-interactive", "-y", action="store_true", help="非交互式（使用默认值）")
    parser.add_argument("--force", "-f", action="store_true", help="覆盖已存在的 .env 文件")
    args = parser.parse_args()

    if ENV_FILE.exists() and not args.force:
        if not args.non_interactive:
            try:
                resp = input(f"⚠️  {ENV_FILE} 已存在，是否覆盖？[y/N] ").strip().lower()
                if resp not in ("y", "yes"):
                    print("已取消。")
                    sys.exit(0)
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")
                sys.exit(0)
        else:
            print(f"⚠️  {ENV_FILE} 已存在，使用 --force 覆盖。")
            sys.exit(1)

    generate_env(host=args.host, docker=args.docker, non_interactive=args.non_interactive, force=args.force)


if __name__ == "__main__":
    main()
