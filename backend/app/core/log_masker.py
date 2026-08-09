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
# FIX: [2026-07-16 P0] 扩展规则覆盖 api_key/access_token/refresh_token/private_key/JWT
_DEFAULT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(password\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(token\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(secret\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(Authorization\s*[:=]\s*Bearer\s+)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "***PHONE***"),  # CN mobile
    # FIX [2026-07-29 P1]: 原 \b\d{15,18}[Xx]?\b 范围过宽（15-18位），
    # 会误匹配 GB28181 设备 ID（20位数字）中的子串以及非标准长度的数字 ID。
    # CN 身份证固定为 18 位（17 位数字 + 1 位数字或 X），收紧为精确 18 位匹配。
    # 这避免将 GB28181 的 20 位国标 ID（如 34020000002000000001）误脱敏为 ***IDCARD***。
    (re.compile(r"\b\d{17}[\dXx]\b"), "***IDCARD***"),  # CN ID card (exactly 18 digits)
    # FIX: [2026-07-16 P0] 新增敏感字段脱敏
    (re.compile(r"(api_?key\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(access_?token\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(refresh_?token\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    (re.compile(r"(private_?key\s*[:=]\s*)\S+", re.IGNORECASE), r"\1****"),
    # JWT token 形式 eyJxxx.yyy.zzz
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "****JWT****"),
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


def mask_log_filter(record: dict) -> bool:
    """FIX: [2026-07-16 P0-D] Loguru sink filter that masks sensitive data in-place.

    Apply this as the ``filter`` parameter to ``logger.add()``. It modifies
    ``record["message"]`` to redact passwords, tokens, phone numbers, and ID
    card numbers BEFORE the log is written to stderr / file / audit sink.

    Without this filter, sensitive information (e.g. ``password=abc123``) is
    written in plaintext to log files, violating 等保 2.0 requirements.
    """
    try:
        _msg = record.get("message")
        if isinstance(_msg, str) and _msg:
            record["message"] = mask_text(_msg)
        # FIX: [2026-07-16 P0] 同时处理异常堆栈中的敏感参数
        _exc = record.get("exception")
        if _exc is not None:
            import traceback as _tb
            try:
                _exc_str = "".join(_tb.format_exception(_exc.type, _exc.value, _exc.traceback))
                _masked_exc = mask_text(_exc_str)
                if _masked_exc != _exc_str:
                    # 覆盖 message 包含脱敏后的异常信息提示
                    # 注意：loguru 不允许直接替换 traceback 对象，此处仅追加到 message
                    if isinstance(_msg, str) and _msg:
                        record["message"] = record["message"] + "\n[masked-traceback]\n" + _masked_exc
            except Exception as _tb_err:
                logger.error(f"log_masker: exception traceback masking failed: {_tb_err}")
    except Exception as _mask_err:
        # FIX: [2026-07-16 P0] 原异常被 pass 静默吞掉，脱敏器失效时无告警，
        # 敏感信息（密码/Token/手机号）未脱敏直接写入日志文件，违反等保 2.0。
        # 改为 error 级别日志（不使用 mask_text 避免递归）。
        import sys
        sys.stderr.write(f"[log_masker] CRITICAL: mask_log_filter failed, sensitive data may be leaked: {_mask_err}\n")
    return True


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
