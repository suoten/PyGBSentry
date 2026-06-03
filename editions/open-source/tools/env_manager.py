from __future__ import annotations

import argparse
import pathlib
import shutil
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

ENV_MAP = {
    "dev": {
        "backend_template": BACKEND_DIR / ".env.dev.example",
        "backend_target": BACKEND_DIR / ".env",
        "frontend_template": FRONTEND_DIR / ".env.development.example",
        "frontend_target": FRONTEND_DIR / ".env.development",
    },
    "prod": {
        "backend_template": BACKEND_DIR / ".env.prod.example",
        "backend_target": BACKEND_DIR / ".env",
        "frontend_template": FRONTEND_DIR / ".env.production.example",
        "frontend_target": FRONTEND_DIR / ".env.production",
    },
}

BACKEND_REQUIRED = {
    "PROJECT_NAME",
    "API_V1_STR",
    "SECRET_KEY",
    "BACKEND_PUBLIC_HOST",
    "BACKEND_PUBLIC_PORT",
    "DATABASE_TYPE",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "POSTGRES_SERVER",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "REDIS_HOST",
    "REDIS_PORT",
    "SIP_IP",
    "SIP_PORT",
    "SIP_ID",
    "SIP_DOMAIN",
    "MEDIA_SERVER_SECRET",
    "MEDIA_SERVER_HOST",
    "MEDIA_SERVER_HTTP_PORT",
    "MEDIA_SERVER_RTSP_PORT",
    "MEDIA_SERVER_RTMP_PORT",
    "MEDIA_SERVER_RTP_PROXY_PORT",
    "MEDIA_SERVER_RTP_PROXY_PORT_RANGE",
    "STREAM_PUBLIC_HOST",
    "STREAM_PUBLIC_HTTP_PORT",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "APP_EDITION",
    "MEDIA_SERVER_RTP_STREAM_MODE",
    "MEDIA_SERVER_HOOK_BASE_URL",
}

BACKEND_PROD_REQUIRED = {
    "SECRET_KEY",
    "DATABASE_PASSWORD",
    "MEDIA_SERVER_SECRET",
    "REDIS_PASSWORD",
}

FRONTEND_REQUIRED = {"VITE_DEV_API_TARGET", "VITE_APP_EDITION"}


def read_env_file(path: pathlib.Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def validate_required(path: pathlib.Path, required: set[str]) -> list[str]:
    env = read_env_file(path)
    return sorted([key for key in required if key not in env or env[key] == ""])


def validate_prod_values(path: pathlib.Path) -> list[str]:
    env = read_env_file(path)
    bad: list[str] = []
    for key, value in env.items():
        lowered = value.lower()
        if "replace-with" in lowered or "change-me" in lowered or "your-" in lowered:
            bad.append(key)
    return sorted(bad)


def switch_env(target_env: str) -> int:
    conf = ENV_MAP[target_env]
    for template_key, target_key in [("backend_template", "backend_target"), ("frontend_template", "frontend_target")]:
        template = conf[template_key]
        target = conf[target_key]
        if not template.exists():
            print(f"[ERROR] 模板不存在: {template}")
            return 1
        shutil.copyfile(template, target)
        print(f"[OK] 已生成: {target.relative_to(ROOT)}")
    print(f"[DONE] 已切换到 {target_env} 环境模板")
    return 0


def validate_env(target_env: str) -> int:
    conf = ENV_MAP[target_env]
    backend_target = conf["backend_target"]
    frontend_target = conf["frontend_target"]

    missing_backend = validate_required(backend_target, BACKEND_REQUIRED)
    missing_frontend = validate_required(frontend_target, FRONTEND_REQUIRED)

    has_error = False
    if not backend_target.exists():
        print(f"[ERROR] 缺少文件: {backend_target.relative_to(ROOT)}")
        has_error = True
    if not frontend_target.exists():
        print(f"[ERROR] 缺少文件: {frontend_target.relative_to(ROOT)}")
        has_error = True
    if has_error:
        return 1

    if missing_backend:
        has_error = True
        print("[ERROR] 后端缺少必填项:")
        for key in missing_backend:
            print(f"  - {key}")
    if missing_frontend:
        has_error = True
        print("[ERROR] 前端缺少必填项:")
        for key in missing_frontend:
            print(f"  - {key}")

    if target_env == "prod":
        placeholders = validate_prod_values(backend_target)
        if placeholders:
            has_error = True
            print("[ERROR] 生产配置仍包含占位值:")
            for key in placeholders:
                print(f"  - {key}")
        prod_missing = validate_required(backend_target, BACKEND_PROD_REQUIRED)
        if prod_missing:
            has_error = True
            print("[ERROR] 生产环境缺少关键安全配置:")
            for key in prod_missing:
                print(f"  - {key}")

    if has_error:
        return 1
    print(f"[DONE] {target_env} 环境配置校验通过")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    switch_parser = subparsers.add_parser("switch")
    switch_parser.add_argument("--env", choices=["dev", "prod"], required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--env", choices=["dev", "prod"], required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "switch":
        return switch_env(args.env)
    if args.command == "validate":
        return validate_env(args.env)
    return 1


if __name__ == "__main__":
    sys.exit(main())
