import hmac
import hashlib
import base64
import time
from loguru import logger
from app.core.config import settings
from app.core.api_key import secure_compare



DEFAULT_TOKEN_TTL = 300
MIN_TOKEN_TTL = 60
HMAC_SIG_BYTES = 16


def _get_secret_key() -> bytes:
    key = (settings.SECRET_KEY or "").strip()
    if not key:
        raise RuntimeError(
            "SECRET_KEY is not configured. Play token signing requires SECRET_KEY. "
            "Set it in your .env file to enable stream playback."
        )  # FIXED: removed random fallback secret that broke multi-process deployments
    return key.encode("utf-8")


def generate_play_token(app: str, stream: str, expire_seconds: int = DEFAULT_TOKEN_TTL) -> str:
    expire_seconds = max(MIN_TOKEN_TTL, expire_seconds)
    expire_ts = int(time.time()) + expire_seconds
    raw = f"{app}|{stream}|{expire_ts}"
    sig = hmac.new(
        _get_secret_key(),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig[:HMAC_SIG_BYTES] + raw.encode("utf-8")).decode().rstrip("=")


def _decode_play_token(token: str) -> tuple[bytes, str] | None:
    if not token:
        return None
    try:
        padding = 4 - len(token) % 4
        if padding != 4:
            token += "=" * padding
        decoded = base64.urlsafe_b64decode(token)
        if len(decoded) <= HMAC_SIG_BYTES:
            return None
        sig_bytes = decoded[:HMAC_SIG_BYTES]
        payload_str = decoded[HMAC_SIG_BYTES:].decode("utf-8")
        return sig_bytes, payload_str
    except Exception:
        return None


def verify_play_token(token: str, app: str, stream: str) -> tuple[bool, str]:
    if not token:
        return False, "missing or invalid play token"
    decoded = _decode_play_token(token)
    if decoded is None:
        return False, "missing or invalid play token"
    sig_bytes, payload_str = decoded
    expected_sig = hmac.new(
        _get_secret_key(),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()[:HMAC_SIG_BYTES]
    if not secure_compare(sig_bytes.hex(), expected_sig.hex()):
        return False, "invalid play token"
    parts = payload_str.split("|")
    if len(parts) != 3:
        return False, "invalid play token"
    token_app, token_stream, expire_ts_str = parts
    try:
        expire_ts = int(expire_ts_str)
    except ValueError:
        return False, "invalid play token"
    if expire_ts < int(time.time()):
        return False, "expired play token"
    if token_app != app or token_stream != stream:
        return False, "token stream mismatch"
    return True, ""


def extract_token_from_params(params: str | dict | None) -> str:
    if params is None:
        return ""
    if isinstance(params, dict):
        return str(params.get("token") or "").strip()
    if isinstance(params, str):
        raw = params.strip().lstrip("?")
        for part in raw.split("&"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k.strip() == "token":
                return v.strip()
    return ""


def should_allow_no_token() -> bool:
    return bool(getattr(settings, "PLAY_ALLOW_NO_TOKEN", False))
