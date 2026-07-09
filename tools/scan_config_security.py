#!/usr/bin/env python
"""配置安全扫描脚本。

扫描 .env 文件和项目源码，检测：
1. 默认密码/密钥占位符（YOUR_STRONG_PASSWORD_HERE、YOUR_SECRET_KEY_HERE 等）
2. 弱密码黑名单
3. placeholder_replace_with_real_* 占位符
4. 密钥/密码长度不足
5. 示例文件中的真实密钥泄露

用法：
    python tools/scan_config_security.py [--env-file .env] [--strict]

退出码：
    0: 扫描通过，无安全问题
    1: 发现安全问题（--strict 模式下任何警告都返回 1）
"""
import os
import re
import sys
import argparse
from pathlib import Path
from typing import NamedTuple


class SecurityIssue(NamedTuple):
    severity: str  # CRITICAL / WARNING / INFO
    file: str
    line: int
    field: str
    message: str


# 已知占位符值
PLACEHOLDER_VALUES = {
    "YOUR_SECRET_KEY_HERE",
    "YOUR_STRONG_PASSWORD_HERE",
    "CHANGE_ME_GENERATE_A_RANDOM_64_CHAR_HEX_STRING",
    "CHANGE_ME_GENERATE_A_RANDOM_SECRET",
    "CHANGE_ME_STRONG_DB_PASSWORD",
    "CHANGE_ME_STRONG_REDIS_PASSWORD",
    # 旧占位符（保留兼容，便于扫描历史 .env 文件）
    "replace-with-strong-db-password",
    "replace-with-strong-redis-password",
    "replace-with-a-random-64-char-hex-string",
    "replace-with-zlm-secret",
}

# 弱密码黑名单
WEAK_PASSWORDS = {
    "password", "123456", "admin", "root", "postgres",
    "abc123", "111111", "000000", "qwerty", "pass123",
    "password123", "admin123", "test", "guest", "user",
    "changeme", "secret", "default", "welcome", "letmein",
}

# 敏感字段名
SENSITIVE_FIELDS = {
    "SECRET_KEY", "DATABASE_PASSWORD", "POSTGRES_PASSWORD", "REDIS_PASSWORD",
    "MEDIA_SERVER_SECRET", "SIP_DEFAULT_PASSWORD", "ADMIN_INITIAL_PASSWORD",
    "LICENSE_SIGNING_SECRET", "PAYMENT_CALLBACK_SECRET", "SMTP_PASSWORD",
    "SIP_NONCE_SECRET", "FIELD_ENCRYPTION_KEY", "ZLM_API_SECRET",
    "REDIS_SENTINEL_PASSWORD", "TURN_PASSWORD", "CUSTOM_MARKET_TOKEN",
    "RECORD_DOWNLOAD_SIGN_SECRET",
}

# 占位符模式
PLACEHOLDER_PATTERN = re.compile(r"placeholder_replace_with_real_\w+")


def parse_env_file(env_path: Path) -> list[tuple[int, str, str]]:
    """解析 .env 文件，返回 [(line_num, key, value), ...]"""
    entries = []
    if not env_path.exists():
        return entries
    with open(env_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # P1-50: 先移除行内注释，再去除引号
            # 避免 `"value"  # comment` 解析后残留尾部引号导致占位符匹配失败
            if " #" in value:
                value = value.split(" #")[0].strip()
            value = value.strip('"').strip("'")
            entries.append((i, key, value))
    return entries


def scan_env_file(env_path: Path) -> list[SecurityIssue]:
    """扫描 .env 文件中的安全问题。"""
    issues = []
    entries = parse_env_file(env_path)

    for line_num, key, value in entries:
        if key not in SENSITIVE_FIELDS:
            continue

        if not value:
            continue

        # 检测占位符
        if value in PLACEHOLDER_VALUES:
            issues.append(SecurityIssue(
                "CRITICAL", str(env_path), line_num, key,
                f"使用占位符值 '{value}'，必须替换为真实值"
            ))
            continue

        # 检测弱密码
        if value.lower() in WEAK_PASSWORDS:
            issues.append(SecurityIssue(
                "CRITICAL", str(env_path), line_num, key,
                f"使用弱密码 '{value}'，必须替换为强密码"
            ))
            continue

        # 检测长度
        if key == "SECRET_KEY" and len(value) < 32:
            issues.append(SecurityIssue(
                "WARNING", str(env_path), line_num, key,
                f"SECRET_KEY 长度不足 ({len(value)} < 32 字符)"
            ))
        elif key in {"DATABASE_PASSWORD", "POSTGRES_PASSWORD", "REDIS_PASSWORD"} and len(value) < 12:
            issues.append(SecurityIssue(
                "WARNING", str(env_path), line_num, key,
                f"{key} 长度不足 ({len(value)} < 12 字符)"
            ))
        elif key == "ADMIN_INITIAL_PASSWORD" and len(value) < 8:
            issues.append(SecurityIssue(
                "WARNING", str(env_path), line_num, key,
                f"ADMIN_INITIAL_PASSWORD 长度不足 ({len(value)} < 8 字符)"
            ))

    return issues


def scan_example_file(example_path: Path) -> list[SecurityIssue]:
    """扫描 .env.example 文件，确保使用占位符而非真实密钥。"""
    issues = []
    if not example_path.exists():
        return issues

    entries = parse_env_file(example_path)
    for line_num, key, value in entries:
        if key not in SENSITIVE_FIELDS:
            continue
        if not value:
            continue

        # 示例文件中应该使用占位符，不应包含真实密钥
        if value not in PLACEHOLDER_VALUES and value not in WEAK_PASSWORDS:
            # 检查是否看起来像真实密钥（长度足够且非占位符）
            if len(value) >= 16 and not value.startswith("YOUR_") and not value.startswith("CHANGE_ME"):
                issues.append(SecurityIssue(
                    "WARNING", str(example_path), line_num, key,
                    f"示例文件中可能包含真实密钥 (长度 {len(value)})，建议使用占位符"
                ))

    return issues


def scan_source_placeholders(root_dir: Path) -> list[SecurityIssue]:
    """扫描源码中的 placeholder_replace_with_real_* 占位符。"""
    issues = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", "logs"}

    for filepath in root_dir.rglob("*"):
        if not filepath.is_file():
            continue
        if any(part in skip_dirs for part in filepath.parts):
            continue
        if filepath.suffix not in {".py", ".yml", ".yaml", ".json", ".env", ".ini", ".conf", ".toml"}:
            continue

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if PLACEHOLDER_PATTERN.search(line):
                        issues.append(SecurityIssue(
                            "CRITICAL", str(filepath), i, "PLACEHOLDER",
                            f"发现占位符: {PLACEHOLDER_PATTERN.search(line).group()}"
                        ))
        except Exception:
            continue

    return issues


def print_issues(issues: list[SecurityIssue]) -> None:
    """打印安全问题列表。"""
    if not issues:
        print("[OK] 未发现配置安全问题")
        return

    critical = [i for i in issues if i.severity == "CRITICAL"]
    warnings = [i for i in issues if i.severity == "WARNING"]
    info = [i for i in issues if i.severity == "INFO"]

    print(f"\n{'='*70}")
    print(f"配置安全扫描结果: {len(critical)} CRITICAL / {len(warnings)} WARNING / {len(info)} INFO")
    print(f"{'='*70}\n")

    for issue in issues:
        icon = {"CRITICAL": "[!]", "WARNING": "[~]", "INFO": "[i]"}.get(issue.severity, "[?]")
        print(f"{icon} {issue.severity} {issue.file}:{issue.line}")
        print(f"   字段: {issue.field}")
        print(f"   问题: {issue.message}")
        print()


def main():
    parser = argparse.ArgumentParser(description="配置安全扫描脚本")
    parser.add_argument("--env-file", default=".env", help="要扫描的 .env 文件路径")
    parser.add_argument("--strict", action="store_true", help="严格模式：任何警告都返回退出码 1")
    parser.add_argument("--root", default=".", help="项目根目录（用于扫描源码占位符）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    all_issues = []

    # 1. 扫描 .env 文件
    env_path = Path(args.env_file)
    if env_path.exists():
        print(f"扫描 .env 文件: {env_path}")
        all_issues.extend(scan_env_file(env_path))
    else:
        print(f"[INFO] .env 文件不存在: {env_path}（跳过）")

    # 2. 扫描 .env.example 文件
    for example_name in [".env.example", ".env.dev.example", ".env.prod.example"]:
        example_path = root / "backend" / example_name
        if example_path.exists():
            print(f"扫描示例文件: {example_path}")
            all_issues.extend(scan_example_file(example_path))

    # 3. 扫描源码占位符
    print(f"扫描源码占位符: {root}")
    all_issues.extend(scan_source_placeholders(root))

    # 4. 输出结果
    print_issues(all_issues)

    # 5. 返回退出码
    has_critical = any(i.severity == "CRITICAL" for i in all_issues)
    has_warning = any(i.severity == "WARNING" for i in all_issues)

    if has_critical:
        sys.exit(1)
    if args.strict and has_warning:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
