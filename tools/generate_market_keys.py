#!/usr/bin/env python3
"""
generate_market_keys.py — 生成市场签名 Ed25519 密钥对

Task 5: 替换安全占位符 — 提供密钥生成脚本

用法：
  python tools/generate_market_keys.py

输出：
  1. 控制台打印公钥（需硬编码到 backend/app/core/market_builtin.py）
  2. 控制台打印私钥（仅服务端使用，不要提交到代码仓库）
  3. 生成 .market_ed25519_pub 和 .market_ed25519_key 文件

公钥轮换：
  1. 运行此脚本生成新密钥对
  2. 将新公钥设置到 _BUILTIN_ED25519_PUBLIC_KEY
  3. 将旧公钥添加到 _BUILTIN_ED25519_PUBLIC_KEY_HISTORY 列表
  4. 旧公钥仍可验证已签名的旧插件包
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent


def generate_with_cryptography() -> tuple[str, str]:
    """使用 cryptography 库生成 Ed25519 密钥对"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    pub_bytes = pub.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    priv_bytes = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    return base64.b64encode(pub_bytes).decode(), base64.b64encode(priv_bytes).decode()


def generate_with_nacl() -> tuple[str, str]:
    """使用 PyNaCl 库生成 Ed25519 密钥对"""
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    private_key_b64 = base64.b64encode(bytes(signing_key)).decode()
    public_key_b64 = base64.b64encode(bytes(signing_key.verify_key)).decode()
    return public_key_b64, private_key_b64


def main():
    print("=" * 60)
    print("  PyGBSentry 市场签名 Ed25519 密钥生成工具")
    print("=" * 60)

    # 优先使用 cryptography，回退到 PyNaCl
    pub_key = ""
    priv_key = ""
    try:
        pub_key, priv_key = generate_with_cryptography()
        print("[INFO] 使用 cryptography 库生成密钥对")
    except ImportError:
        try:
            pub_key, priv_key = generate_with_nacl()
            print("[INFO] 使用 PyNaCl 库生成密钥对")
        except ImportError:
            print("ERROR: 需要 cryptography 或 PyNaCl 库")
            print("  pip install cryptography")
            print("  或")
            print("  pip install nacl")
            sys.exit(1)

    # 写入文件
    pub_file = OUTPUT_DIR / ".market_ed25519_pub"
    key_file = OUTPUT_DIR / ".market_ed25519_key"
    pub_file.write_text(pub_key)
    key_file.write_text(priv_key)

    print()
    print("-" * 60)
    print("公钥（Base64）— 硬编码到 market_builtin.py:")
    print(f"  _BUILTIN_ED25519_PUBLIC_KEY = \"{pub_key}\"")
    print()
    print("私钥（Base64）— 仅服务端使用，不要提交到代码仓库:")
    print(f"  {priv_key}")
    print()
    print(f"公钥已写入: {pub_file}")
    print(f"私钥已写入: {key_file}")
    print()
    print("下一步:")
    print("  1. 将公钥复制到 backend/app/core/market_builtin.py 的 _BUILTIN_ED25519_PUBLIC_KEY")
    print("  2. 私钥仅用于服务端签名，妥善保管")
    print("  3. 轮换密钥时，将旧公钥添加到 _BUILTIN_ED25519_PUBLIC_KEY_HISTORY")
    print("=" * 60)


if __name__ == "__main__":
    main()
