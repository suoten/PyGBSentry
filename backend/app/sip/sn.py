"""Unified SIP CSeq/sequence-number (SN) generator.

GB28181 SIP messages carry a ``SN`` element used by devices to correlate
requests/responses. This module provides a process-wide monotonically
increasing counter so SN values are predictable and collision-free within
a single process lifetime (P2-2 统一 SN 生成策略).
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_counter: int = 0

# FIX [2026-07-22 P2]: SN 上限回绕。SN 同时用作 CSeq（RFC 3261 §22.2 规定 CSeq
# 为 32 位无符号整数），Python int 无上限，长跑数年超过 2^31-1 后不合规，
# 严格设备可能拒绝。回绕到 1（跳过 0，0 在部分设备上被视为非法 SN）。
_SN_MAX = 2**31 - 1


def next_sn() -> int:
    """Return the next monotonic SN value (starts at 1, wraps to 1 after 2^31-1)."""
    global _counter
    with _lock:
        _counter += 1
        if _counter > _SN_MAX:
            _counter = 1
        return _counter


def current_sn() -> int:
    """Return the current SN value without advancing it."""
    with _lock:
        return _counter


def reset_sn(start: int = 0) -> None:
    """Reset the counter — intended for tests only."""
    global _counter
    with _lock:
        _counter = int(start)
