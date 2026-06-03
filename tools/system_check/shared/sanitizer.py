from __future__ import annotations

import re

_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|access_key|private_key|credential)",
    re.IGNORECASE,
)


class Sanitizer:
    @classmethod
    def is_sensitive_key(cls, key: str) -> bool:
        return bool(_SENSITIVE_KEY_PATTERNS.search(key))

    @classmethod
    def mask_value(cls, value: str, visible_prefix: int = 3, visible_suffix: int = 3) -> str:
        if len(value) <= visible_prefix + visible_suffix:
            return "***"
        return f"{value[:visible_prefix]}***{value[-visible_suffix:]}"

    @classmethod
    def sanitize_dict(cls, data: dict) -> dict:
        result: dict = {}
        for key, value in data.items():
            if cls.is_sensitive_key(key) and isinstance(value, str):
                result[key] = cls.mask_value(value)
            elif isinstance(value, dict):
                result[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    cls.sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
