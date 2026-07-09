import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time

from app.core.config import settings

_logger = logging.getLogger(__name__)


def _get_totp_cipher():
    from cryptography.fernet import Fernet
    key_material = settings.SECRET_KEY
    if not key_material:
        raise RuntimeError("TOTP 加密需要 SECRET_KEY，请在环境变量中设置")
    key_material = key_material.encode("utf-8")
    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    return Fernet(fernet_key)


def encrypt_totp_secret(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    cipher = _get_totp_cipher()
    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_totp_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    try:
        cipher = _get_totp_cipher()
        return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        _logger.warning("TOTP 密钥解密失败，可能由 SECRET_KEY 变更导致")
        raise ValueError("TOTP secret decryption failed, SECRET_KEY may have changed")


def generate_base32_secret(bytes_len: int = 20) -> str:
    raw = secrets.token_bytes(max(10, int(bytes_len or 20)))
    return base64.b32encode(raw).decode("utf-8").replace("=", "")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8))
    msg = struct.pack(">Q", int(counter))
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** int(digits))).zfill(int(digits))


def totp_now(secret_b32: str, step: int = 30, digits: int = 6, t: int | None = None) -> str:
    ts = int(t if t is not None else time.time())
    counter = ts // int(step)
    return _hotp(secret_b32, counter, digits=digits)


def verify_totp(code: str, secret_b32: str, window: int = 1, step: int = 30, digits: int = 6) -> bool:
    c = str(code or "").strip()
    if not c.isdigit():
        return False
    if len(c) != int(digits):
        return False
    now = int(time.time())
    base_counter = now // int(step)
    for i in range(-int(window), int(window) + 1):
        if _hotp(secret_b32, base_counter + i, digits=digits) == c:
            return True
    return False
