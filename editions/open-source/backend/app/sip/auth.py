import hashlib
import hmac
import logging
import re
import secrets
import time
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

class DigestAuth:
    @staticmethod
    def generate_nonce():
        ts = int(time.time())
        rnd = secrets.token_hex(8)
        secret = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8", errors="ignore")
        if not secret or secret == b"":
            logger.warning("SECURITY: SECRET_KEY is empty, SIP nonce HMAC is insecure. Set SECRET_KEY in .env.")
            # FIXED: fallback密钥使用secrets.token_bytes替代可预测的ts+rnd，降低nonce伪造风险
            secret = secrets.token_bytes(32)
        msg = f"{ts}:{rnd}".encode("utf-8")
        sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return f"{ts}:{rnd}:{sig}"

    @staticmethod
    def calculate_response(username, password, realm, method, uri, nonce, nc=None, cnonce=None, qop=None, algorithm="MD5"):
        # FIXED: added SHA-256 algorithm support alongside MD5 for stronger security
        hash_func = hashlib.sha256 if algorithm.upper() == "SHA-256" else hashlib.md5
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
    def parse_auth_header(header_value: str) -> dict:
        """
        Parse Authorization header value into a dictionary.
        Example: Digest username="admin", realm="3402000000", nonce="...", ...
        """
        if not header_value.lower().startswith("digest"):
            return {}
            
        params = {}
        pattern = re.compile(r'(\w+)=(?:"([^"]*)"|([^,]*))')
        matches = pattern.findall(header_value[7:])
        for key, val1, val2 in matches:
            params[key] = val1 if val1 else val2.strip()
        return params
