"""Field-level encryption for sensitive database columns.

SIP设备/平台密码应用层加密存储，防止数据库泄露后密码直接暴露。
使用AES-256-GCM加密，密钥从SECRET_KEY派生。
"""
import base64
import hashlib
from loguru import logger
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _derive_key(purpose: str) -> bytes:
    """Derive a 256-bit encryption key from FIELD_ENCRYPTION_KEY or SECRET_KEY + purpose salt."""
    # 优先使用FIELD_ENCRYPTION_KEY独立密钥，回退到SECRET_KEY
    secret = (getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "").encode("utf-8", errors="ignore")
    if not secret:
        secret = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8", errors="ignore")
    if not secret:
        raise ValueError("SECRET_KEY is not configured; cannot encrypt/decrypt field")
    return hashlib.pbkdf2_hmac("sha256", secret, purpose.encode("utf-8"), 100_000)


def encrypt_field(plaintext: str, purpose: str = "sip_password") -> str:
    """Encrypt a string field value. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    key = _derive_key(purpose)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), purpose.encode("utf-8"))
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(ciphertext: str, purpose: str = "sip_password") -> str | None:
    """Decrypt a string field value.

    Returns:
        Plaintext string on success, or None on decryption failure or empty input.
    """
    if not ciphertext:
        return None
    try:
        key = _derive_key(purpose)
        raw = base64.b64decode(ciphertext)
        nonce = raw[:12]
        ct = raw[12:]
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(nonce, ct, purpose.encode("utf-8")).decode("utf-8")
        except Exception:
            try:
                return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
            except Exception:
                pass
    except Exception:
        pass
    logger.warning("Field decryption failed. Returning None on decryption failure. "
                   "Check if SECRET_KEY or FIELD_ENCRYPTION_KEY has changed.")
    return None
