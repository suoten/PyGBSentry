import json
from typing import Iterable
from loguru import logger

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "viewer": ["dashboard.view", "monitor.view", "channels.view"],
    "operator": ["dashboard.view", "monitor.view", "channels.view", "records.view", "alarms.handle"],
    "admin": ["dashboard.view", "monitor.view", "channels.view", "records.view", "alarms.handle", "devices.manage", "config.manage", "audit.view", "users.manage", "roles.manage"],
    "owner": ["*"],
}


def normalize_permission_codes(codes: Iterable[str] | None) -> list[str]:
    if not codes:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in codes:
        code = str(item or "").strip().lower()
        if not code:
            continue
        if code == "*":
            return ["*"]
        if code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return normalized


def serialize_permission_codes(codes: Iterable[str] | None) -> str:
    return json.dumps(normalize_permission_codes(codes), ensure_ascii=False)


def parse_permission_codes(raw: str | None, role_code: str = "") -> list[str]:
    text = str(raw or "").strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return normalize_permission_codes(parsed)
        except Exception as e:
            logger.warning(f"Error: {e}")
        return normalize_permission_codes(text.split(","))
    return list(DEFAULT_ROLE_PERMISSIONS.get((role_code or "").lower(), []))