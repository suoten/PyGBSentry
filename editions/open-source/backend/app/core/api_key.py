import hashlib
import hmac
import secrets


def generate_api_key(prefix_len: int = 8) -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    prefix = raw[:prefix_len].lower()
    full = f"pgs_{prefix}.{raw}"
    return full, prefix


def hash_api_key(raw: str, secret_salt: str) -> str:
    msg = f"{secret_salt}:{raw}".encode("utf-8")
    return hashlib.sha256(msg).hexdigest()


def parse_api_key(value: str) -> tuple[str, str] | None:
    if not value:
        return None
    v = value.strip()
    if not v.startswith("pgs_"):
        return None
    rest = v[4:]
    if "." not in rest:
        return None
    prefix, raw = rest.split(".", 1)
    prefix = prefix.strip().lower()
    raw = raw.strip()
    if not prefix or not raw:
        return None
    return prefix, raw


def secure_compare(a: str, b: str) -> bool:
    try:
        return hmac.compare_digest(str(a), str(b))
    except Exception:
        return False

