import hashlib
import hmac
from loguru import logger
import re
import secrets
import time
import uuid

from app.core.config import settings

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

_md5_warned = False
_secret_key_warned = False

class DigestAuth:
    @staticmethod
    def generate_nonce():
        global _secret_key_warned
        ts = int(time.time())
        rnd = secrets.token_hex(8)
        secret = (getattr(settings, "SIP_NONCE_SECRET", "") or "").encode("utf-8", errors="ignore")
        if not secret:
            secret = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8", errors="ignore")
        if not secret or secret == b"":
            if not _secret_key_warned:
                _secret_key_warned = True
                _app_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
                if _app_env in ("prod", "production"):
                    logger.error("SECURITY: SECRET_KEY is empty in production! All SIP nonces will be invalidated on process restart. Set SECRET_KEY in .env immediately.")
                else:
                    logger.warning("SECURITY: SECRET_KEY is empty, SIP nonce HMAC is insecure and nonces will be invalidated on process restart. Set SECRET_KEY in .env for production use.")
            secret = secrets.token_bytes(32)
        msg = f"{ts}:{rnd}".encode("utf-8")
        sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return f"{ts}:{rnd}:{sig}"

    @staticmethod
    def calculate_response(username, password, realm, method, uri, nonce, nc=None, cnonce=None, qop=None, algorithm="MD5"):
        global _md5_warned
        effective_algo = algorithm.upper() if algorithm else "MD5"
        if effective_algo == "MD5" and not _md5_warned:
            logger.warning(
                "SIP digest auth using MD5 algorithm. "
                "MD5 is cryptographically broken. Consider enabling SHA-256 when devices support it."
            )
            _md5_warned = True
        hash_func = hashlib.sha256 if effective_algo == "SHA-256" else hashlib.md5
        ha1_str = f"{username}:{realm}:{password}"
        ha1 = hash_func(ha1_str.encode()).hexdigest()

        ha2_str = f"{method}:{uri}"
        ha2 = hash_func(ha2_str.encode()).hexdigest()

        if qop:
            response_str = f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}"
        else:
            response_str = f"{ha1}:{nonce}:{ha2}"
            
        return hash_func(response_str.encode()).hexdigest()

    @staticmethod
    def select_preferred_algorithm(auth_params: dict) -> str:
        algo = (auth_params.get("algorithm") or "").strip().upper()
        if algo == "SHA-256":
            return "SHA-256"
        if algo == "MD5":
            return "MD5"
        return "MD5"

    @staticmethod
    def parse_auth_header(header_value: str) -> dict:
        """
        Parse Authorization header value into a dictionary.
        Example: Digest username="admin", realm="3402000000", nonce="...", ...
        Handles quoted-string values that may contain commas (RFC 2616 / RFC 8760).
        """
        if not header_value.lower().startswith("digest"):
            return {}

        params = {}
        remaining = header_value[7:].strip()
        pattern = re.compile(r'(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^,\s]*))')
        while remaining:
            m = pattern.search(remaining)
            if not m:
                break
            key, val_quoted, val_unquoted = m.group(1), m.group(2), m.group(3)
            params[key] = val_quoted if val_quoted is not None else val_unquoted.strip()
            remaining = remaining[m.end():]
            remaining = remaining.lstrip(", \t")
        return params
