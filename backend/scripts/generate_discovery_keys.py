#!/usr/bin/env python3
"""
generate_discovery_keys.py — 生成发现服务 Ed25519 密钥对

用法：
  pip install nacl
  python generate_discovery_keys.py

输出：
  - .discovery_ed25519_key  — 私钥（Base64，仅服务端使用）
  - .discovery_ed25519_pub  — 公钥（Base64，需填入 market_builtin.py）
"""

from __future__ import annotations

import base64
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent


def main():
    try:
        from nacl.signing import SigningKey
    except ImportError:
        print("ERROR: PyNaCl not installed. Run: pip install nacl")
        return

    # 生成密钥对
    signing_key = SigningKey.generate()
    private_key_b64 = base64.b64encode(bytes(signing_key)).decode("ascii")
    public_key_b64 = base64.b64encode(
        bytes(signing_key.verify_key)
    ).decode("ascii")

    # 写入文件
    (OUTPUT_DIR / ".discovery_ed25519_key").write_text(private_key_b64)
    (OUTPUT_DIR / ".discovery_ed25519_pub").write_text(public_key_b64)

    print("=" * 60)
    print("Ed25519 key pair generated successfully!")
    print("=" * 60)
    print()
    print(f"Private key (saved to .discovery_ed25519_key):")
    print(f"  {private_key_b64}")
    print()
    print(f"Public key (saved to .discovery_ed25519_pub):")
    print(f"  {public_key_b64}")
    print()
    print("Next steps:")
    print("  1. Copy the public key to market_builtin.py:")
    print(f'     _BUILTIN_ED25519_PUBLIC_KEY = "{public_key_b64}"')
    print()
    print("  2. Set the private key as env var for discovery server:")
    print(f'     ED25519_PRIVATE_KEY="{private_key_b64}"')
    print()
    print("  3. NEVER commit .discovery_ed25519_key to version control!")
    print("     Add it to .gitignore.")


if __name__ == "__main__":
    main()
