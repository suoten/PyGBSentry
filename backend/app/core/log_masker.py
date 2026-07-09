"""Log redaction / masking rules.

Provides a small rule engine that replaces sensitive substrings (passwords,
tokens, phone numbers) in log lines. Rules can be loaded from Redis at
runtime so operators can add masks without redeploying. The OSS edition
ships built-in defaults and a best-effort Redis loader.
"""
from __future__ import annotations

import re

from loguru import logger

# Built-in mask rules: (compiled_pattern, replacement)
_DEFAULT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(password\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(token\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(secret\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(Authorization\s*[:=]\s*Bearer\s+)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "***PHONE***"),  # CN mobile
    (re.compile(r"\b\d{15,18}[Xx]?\b"), "***IDCARD***"),  # CN ID card
]

_custom_rules: list[tuple[re.Pattern, str]] = []


def get_rules() -> list[tuple[re.Pattern, str]]:
    return _DEFAULT_RULES + _custom_rules


def mask_text(text: str) -> str:
    """Apply all mask rules to ``text`` and return the redacted result."""
    if not text:
        return text
    out = text
    for pattern, repl in get_rules():
        try:
            out = pattern.sub(repl, out)
        except Exception as e:
            logger.warning(f"log_masker: regex substitution failed: {e}")
    return out


async def load_custom_rules_from_redis() -> int:
    """Load custom mask rules from Redis (JSON list of {pattern, repl}).

    Returns the number of rules loaded. Failures are logged and swallowed.
    """
    global _custom_rules
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis is None:
            return 0
        raw = await redis.get("log_masker:rules")
        if not raw:
            return 0
        import json
        rules_data = json.loads(raw)
        loaded: list[tuple[re.Pattern, str]] = []
        for item in rules_data if isinstance(rules_data, list) else []:
            try:
                pat = re.compile(str(item.get("pattern", "")))
                repl = str(item.get("repl", "****"))
                loaded.append((pat, repl))
            except Exception:
                continue
        _custom_rules = loaded
        logger.info(f"log_masker: loaded {len(_custom_rules)} custom rules from Redis")
        return len(_custom_rules)
    except Exception as e:
        logger.debug(f"log_masker: load_custom_rules_from_redis failed: {e}")
        return 0
