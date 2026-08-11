"""Account lockout helpers — pure functions for testable lockout logic.

将账户锁定/解锁的核心判定逻辑从 ``api/v1/endpoints/login.py`` 中抽离为
纯函数，便于单元测试（无需数据库即可测试锁定/解锁/自动重置行为）。

设计要点
--------
- 所有函数仅修改传入的 ``User`` 对象的内存状态（``failed_login_attempts``
  与 ``locked_until``），不触碰数据库；持久化由调用方负责。
- ``check_lockout_status`` 在锁定期满时**就地重置**失败计数与锁定时间戳，
  修复此前“锁过期后计数仍为 5，下一次失败立即重新锁定”的缺陷。
- 时区处理：SQLite 返回 naive datetime，所有比较前统一加上 UTC tzinfo。

与 ``login.py`` 的协作契约
--------------------------
1. 加载 user 后调用 :func:`check_lockout_status`：
   - 返回 ``is_locked=True`` → 返回 423，写 ``account_locked`` 审计。
   - 返回 ``was_auto_unlocked=True`` → 写 ``account_auto_unlocked`` 审计后继续登录流程。
2. 凭证校验失败时调用 :func:`record_failed_attempt`：
   - 返回 ``just_locked=True`` → 返回 423，写 ``account_locked_after_attempts`` 审计。
3. 登录成功时调用 :func:`reset_login_failures` 重置计数。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

# 锁定阈值与时长（与 login.py 中原常量保持一致，作为单一事实来源）
MAX_FAILED_ATTEMPTS: int = 5
LOCKOUT_MINUTES: int = 30


def _now(now: Optional[datetime]) -> datetime:
    """返回 UTC 当前时间；允许测试注入固定时间。"""
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _normalize_locked_until(locked_until: Any) -> Optional[datetime]:
    """将 locked_until 规范化为 tz-aware UTC datetime；None 透传。"""
    if locked_until is None:
        return None
    if isinstance(locked_until, datetime):
        if locked_until.tzinfo is None:
            return locked_until.replace(tzinfo=timezone.utc)
        return locked_until
    return None


def check_lockout_status(user: Any, now: Optional[datetime] = None) -> Tuple[bool, bool]:
    """检查账户锁定状态，必要时就地自动解锁。

    Args:
        user: ``User`` 模型实例（需有 ``locked_until`` 与 ``failed_login_attempts`` 属性）。
        now: 可选的当前时间（用于测试注入）。

    Returns:
        ``(is_locked, was_auto_unlocked)``

        - ``(True, False)`` — 账户仍处于锁定状态，登录应被拒绝（返回 423）。
        - ``(False, True)`` — 锁定已过期，**已就地重置计数与锁定时间戳**，
          调用方应写 ``account_auto_unlocked`` 审计后继续登录流程。
        - ``(False, False)`` — 账户未被锁定，正常进行登录。

    关键修复：当 ``locked_until <= now`` 时，将 ``failed_login_attempts`` 重置为 0、
    ``locked_until`` 重置为 None，避免锁过期后第一次失败就立即重新锁定。
    """
    current = _now(now)
    locked_until = _normalize_locked_until(getattr(user, "locked_until", None))
    if locked_until is None:
        return False, False
    if locked_until > current:
        # 仍在锁定期内
        return True, False
    # 锁已过期 — 就地重置，避免“下次失败即重锁”缺陷
    user.failed_login_attempts = 0
    user.locked_until = None
    return False, True


def record_failed_attempt(user: Any, now: Optional[datetime] = None) -> bool:
    """记录一次失败登录尝试，达到阈值时锁定账户。

    Args:
        user: ``User`` 模型实例。调用方应仅在用户存在且凭证错误时调用本函数。
        now: 可选的当前时间（用于测试注入）。

    Returns:
        ``just_locked`` — 本次失败是否触发锁定。为 ``True`` 时调用方应返回 423
        并写 ``account_locked_after_attempts`` 审计。
    """
    current = _now(now)
    current_count = int(getattr(user, "failed_login_attempts", 0) or 0)
    new_count = current_count + 1
    user.failed_login_attempts = new_count
    if new_count >= MAX_FAILED_ATTEMPTS:
        user.locked_until = current + timedelta(minutes=LOCKOUT_MINUTES)
        return True
    return False


def reset_login_failures(user: Any) -> None:
    """登录成功时重置失败计数与锁定状态。

    幂等：即使原本计数为 0 也可安全调用。
    """
    user.failed_login_attempts = 0
    user.locked_until = None


def remaining_lock_seconds(user: Any, now: Optional[datetime] = None) -> int:
    """返回账户剩余锁定秒数（未锁定返回 0）。

    供 ``Retry-After`` 响应头使用：取整秒，最小 1（避免 0 触发客户端立即重试）。
    """
    current = _now(now)
    locked_until = _normalize_locked_until(getattr(user, "locked_until", None))
    if locked_until is None or locked_until <= current:
        return 0
    delta = (locked_until - current).total_seconds()
    return max(1, int(delta))
