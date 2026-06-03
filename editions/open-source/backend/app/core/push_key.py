import secrets

from app.core.api_key import hash_api_key


def generate_push_key(prefix_len: int = 8) -> tuple[str, str]:
    raw = secrets.token_urlsafe(24)
    prefix = raw[:prefix_len].lower()
    full = f"push_{prefix}.{raw}"
    return full, prefix


def hash_push_key(raw: str, secret_salt: str) -> str:
    return hash_api_key(raw=raw, secret_salt=secret_salt)


def parse_push_key(value: str) -> tuple[str, str] | None:
    if not value:
        return None
    v = value.strip()
    if not v.startswith("push_"):
        return None
    rest = v[5:]
    if "." not in rest:
        return None
    prefix, raw = rest.split(".", 1)
    prefix = prefix.strip().lower()
    raw = raw.strip()
    if not prefix or not raw:
        return None
    return prefix, raw

