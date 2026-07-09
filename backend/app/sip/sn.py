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


def next_sn() -> int:
    """Return the next monotonic SN value (starts at 1)."""
    global _counter
    with _lock:
        _counter += 1
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
