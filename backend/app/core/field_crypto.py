"""Field-level encryption for sensitive database columns.

SIP设备/平台密码应用层加密存储，防止数据库泄露后密码直接暴露。
使用AES-256-GCM加密，密钥从SECRET_KEY派生。
"""
import base64
import hashlib
import re
from loguru import logger
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _derive_key(purpose: str) -> bytes:
    """Derive a 256-bit encryption key from FIELD_ENCRYPTION_KEY + purpose salt.

    SECURITY: 字段加密要求专用的 FIELD_ENCRYPTION_KEY，不再回退到 SECRET_KEY。
    密钥缺失时立即抛出配置错误，防止静默降级到共享密钥导致密钥隔离失效。
    """
    secret = (settings.FIELD_ENCRYPTION_KEY or "").encode("utf-8", errors="ignore")
    if not secret:
        raise ValueError(
            "FIELD_ENCRYPTION_KEY is not configured; cannot encrypt/decrypt field. "
            "Set FIELD_ENCRYPTION_KEY in .env — do not rely on SECRET_KEY for field encryption."
        )
    return hashlib.pbkdf2_hmac("sha256", secret, purpose.encode("utf-8"), 100_000)


def _looks_like_ciphertext(s: str) -> bool:
    """判断字符串是否可能是 AES-GCM 密文（base64 编码）。

    AES-256-GCM 密文格式：base64(nonce(12B) + ciphertext + tag(16B))
    最小密文长度：12 + 16 + 1 = 29 字节 → base64 编码后至少 40 字符。
    如果字符串长度 < 40 或不是合法 base64，大概率是明文（加密功能启用前的旧数据）。
    """
    if not s or len(s) < 40:
        return False
    try:
        # 标准 base64 字符集 + URL-safe 变体
        if not re.match(r'^[A-Za-z0-9+/=_-]+$', s):
            return False
        # 尝试 base64 解码，检查解码后长度是否 >= 28 字节（12 nonce + 16 tag）
        decoded = base64.b64decode(s, validate=True)
        return len(decoded) >= 28
    except (ValueError, TypeError):
        return False


def encrypt_field(plaintext: str, purpose: str = "sip_password") -> str:
    """Encrypt a string field value. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    key = _derive_key(purpose)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), purpose.encode("utf-8"))
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(ciphertext: str, purpose: str = "sip_password", allow_plaintext: bool = True) -> str | None:
    """Decrypt a string field value.

    Args:
        ciphertext: 要解密的值（可能是密文或明文旧数据）
        purpose: 加密用途（作为 AAD 和密钥派生盐）
        allow_plaintext: 是否允许将明文作为有效值返回。
            True（默认）：解密失败时返回原始字符串（明文兼容，用于认证场景）
            False：解密失败时返回 None（严格模式，用于迁移脚本判断是否已加密）

    Returns:
        Plaintext string on success, or None on decryption failure or empty input.

    FIX [2026-07-18 P0]: 向后兼容加密功能启用前的明文数据。
    原问题：启用字段加密后，数据库中已有的明文密码（如 sip_password、media_secret）
    调用 decrypt_field 时解密失败返回 None，导致 SIP Digest 认证无候选密码可用，
    已知设备认证失败 5 次后被自动拉黑，所有 SIP 设备无法注册。
    修复：allow_plaintext=True 时，解密失败返回原始字符串（明文兼容）；
    allow_plaintext=False 时，解密失败返回 None（严格模式，用于迁移判断）。
    """
    if not ciphertext:
        return None

    # 快速路径：如果字符串明显不是密文格式
    if not _looks_like_ciphertext(ciphertext):
        if allow_plaintext:
            # 明文旧数据，直接返回
            logger.debug(
                f"decrypt_field: value does not look like ciphertext (len={len(ciphertext)}), "
                f"treating as plaintext for purpose={purpose}. "
                f"Consider re-encrypting via scripts/reencrypt_fields.py"
            )
            return ciphertext
        else:
            # 严格模式：明文不是有效的已加密值
            return None

    try:
        key = _derive_key(purpose)
        raw = base64.b64decode(ciphertext)
        nonce = raw[:12]
        ct = raw[12:]
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(nonce, ct, purpose.encode("utf-8")).decode("utf-8")
        except Exception as e1:
            # P1-7: 首次解密失败（带 purpose AAD），尝试旧格式（无 AAD）兼容
            try:
                plaintext = aesgcm.decrypt(nonce, ct, None).decode("utf-8")
                logger.warning(
                    "Field decryption succeeded with legacy format (no AAD). "
                    "purpose={}, first_error={}. Consider re-encrypting this field.",
                    purpose, e1,
                )
                return plaintext
            except Exception as e2:
                # 解密失败但字符串看起来像密文格式
                if allow_plaintext:
                    # FIX [2026-07-18 P0]: 返回原始字符串作为候选——
                    # 如果是明文则 Digest 认证成功，
                    # 如果是密钥变更的密文则 Digest 认证失败（但不会锁死所有设备）。
                    logger.warning(
                        "Field decryption failed for purpose={}: primary_error={}, legacy_error={}. "
                        "Returning original value as fallback (may be plaintext or key-changed ciphertext).",
                        purpose, e1, e2,
                    )
                    return ciphertext
                else:
                    logger.warning(
                        "Field decryption failed for purpose={}: primary_error={}, legacy_error={}. "
                        "Returning None (strict mode).",
                        purpose, e1, e2,
                    )
                    return None
    except Exception as e:
        # base64 解码失败
        if allow_plaintext:
            logger.debug(
                f"decrypt_field: base64 decode failed for purpose={purpose}, "
                f"treating as plaintext. error={e}"
            )
            return ciphertext
        else:
            return None


