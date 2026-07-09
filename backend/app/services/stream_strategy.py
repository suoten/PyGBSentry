"""流媒体传输模式策略（UDP / TCP_PASSIVE / TCP_ACTIVE）。

提供：
- ``normalize_stream_mode``：将各种别名归一化为标准模式字符串。
- ``recommend_stream_mode``：基于历史成功率给出推荐模式与风险等级。
- ``should_probe_back_to_tcp_passive``：判断是否应将 UDP 资产自动回切到 TCP 被动。
- ``calculate_failure_rate``：计算失败率百分比。

标准模式取值：``UDP`` / ``TCP_PASSIVE`` / ``TCP_ACTIVE``。
策略元模式（仅出现在 AssetStreamPolicy.stream_mode）：``GLOBAL``（跟随全局）、``AUTO``（自适应）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

# 标准模式常量
MODE_UDP = "UDP"
MODE_TCP_PASSIVE = "TCP_PASSIVE"
MODE_TCP_ACTIVE = "TCP_ACTIVE"

# 策略元模式
MODE_GLOBAL = "GLOBAL"
MODE_AUTO = "AUTO"

_CANONICAL_MODES = {MODE_UDP, MODE_TCP_PASSIVE, MODE_TCP_ACTIVE, MODE_GLOBAL, MODE_AUTO}

# 别名 → 标准模式（小写归一化后匹配）
_ALIAS_MAP: dict[str, str] = {
    "udp": MODE_UDP,
    "udp_passive": MODE_UDP,
    "tcp": MODE_TCP_PASSIVE,
    "tcp_passive": MODE_TCP_PASSIVE,
    "passive": MODE_TCP_PASSIVE,
    "tcp-passive": MODE_TCP_PASSIVE,
    "tcp_active": MODE_TCP_ACTIVE,
    "tcp-active": MODE_TCP_ACTIVE,
    "active": MODE_TCP_ACTIVE,
    "global": MODE_GLOBAL,
    "auto": MODE_AUTO,
}


def normalize_stream_mode(
    mode: Optional[str],
    default_mode: str = MODE_UDP,
    allow_auto: bool = False,
) -> str:
    """将流模式别名归一化为标准模式字符串。

    - 接受 ``udp`` / ``tcp`` / ``tcp-passive`` / ``TCP_PASSIVE`` 等各种写法。
    - 空值或未知值返回 ``default_mode``（默认 ``UDP``）。
    - ``allow_auto=True`` 时允许返回 ``GLOBAL`` / ``AUTO`` 元模式（用于策略配置读取），
      否则把 ``GLOBAL`` / ``AUTO`` 折叠回 ``default_mode``。
    """
    if not mode:
        return default_mode
    raw = str(mode).strip()
    if not raw:
        return default_mode
    key = raw.lower().replace("-", "_")
    canonical = _ALIAS_MAP.get(key)
    if canonical is None:
        # 大小写敏感的精确匹配（如原样已是 TCP_PASSIVE）
        if raw in _CANONICAL_MODES:
            canonical = raw
        else:
            logger.debug(f"normalize_stream_mode: unknown mode '{raw}', falling back to {default_mode}")
            return default_mode

    if canonical in (MODE_GLOBAL, MODE_AUTO) and not allow_auto:
        return default_mode
    return canonical


def calculate_failure_rate(success_total: int, fail_total: int) -> float:
    """计算失败率百分比（0-100），总样本为 0 时返回 0.0。"""
    try:
        s = int(success_total or 0)
        f = int(fail_total or 0)
    except (TypeError, ValueError):
        return 0.0
    total = s + f
    if total <= 0:
        return 0.0
    return round((f / total) * 100.0, 2)


def _risk_level_from_stats(
    failure_rate: float,
    consecutive_failures: int,
    auto_switch_count: int,
) -> str:
    """根据失败率/连续失败/自动切换次数返回 'low' / 'medium' / 'high'。"""
    if failure_rate >= 30.0 or consecutive_failures >= 5 or auto_switch_count >= 3:
        return "high"
    if failure_rate >= 10.0 or consecutive_failures >= 3 or auto_switch_count >= 1:
        return "medium"
    return "low"


def recommend_stream_mode(
    last_mode: Optional[str] = None,
    current_mode: Optional[str] = None,
    success_total: int = 0,
    fail_total: int = 0,
    consecutive_failures: int = 0,
    auto_switch_count: int = 0,
    **_: Any,
) -> tuple[str, str, str]:
    """基于历史统计推荐流模式。

    返回三元组 ``(recommended_mode, recommend_reason, risk_level)``：
    - ``recommended_mode``：``UDP`` / ``TCP_PASSIVE`` / ``TCP_ACTIVE``
    - ``recommend_reason``：人类可读的推荐理由
    - ``risk_level``：``low`` / ``medium`` / ``high``

    策略：
    - 当前已是 TCP 且高风险 → 维持 TCP（避免再次抖动）
    - 高风险且当前为 UDP → 推荐 TCP_PASSIVE（GB28181 设备普遍兼容）
    - 中风险 → 跟随当前模式
    - 低风险 → 推荐 UDP（最高吞吐、最低延迟）
    """
    try:
        s = int(success_total or 0)
        f = int(fail_total or 0)
        cf = int(consecutive_failures or 0)
        asc = int(auto_switch_count or 0)
    except (TypeError, ValueError):
        s = f = cf = asc = 0

    failure_rate = calculate_failure_rate(s, f)
    risk_level = _risk_level_from_stats(failure_rate, cf, asc)

    cur_norm = normalize_stream_mode(current_mode, default_mode=MODE_UDP)
    if cur_norm in (MODE_GLOBAL, MODE_AUTO):
        cur_norm = MODE_UDP

    if risk_level == "high":
        if cur_norm in (MODE_TCP_PASSIVE, MODE_TCP_ACTIVE):
            reason = f"high risk (rate={failure_rate}%, cf={cf}), keep current TCP mode"
            return cur_norm, reason, risk_level
        reason = f"high risk (rate={failure_rate}%, cf={cf}), switch UDP -> TCP_PASSIVE"
        return MODE_TCP_PASSIVE, reason, risk_level

    if risk_level == "medium":
        reason = f"medium risk (rate={failure_rate}%, cf={cf}), keep current mode {cur_norm}"
        return cur_norm, reason, risk_level

    # low risk：优先 UDP
    if cur_norm == MODE_UDP:
        reason = f"low risk (rate={failure_rate}%, cf={cf}), keep UDP"
        return MODE_UDP, reason, risk_level
    reason = f"low risk (rate={failure_rate}%, cf={cf}), recommend UDP"
    return MODE_UDP, reason, risk_level


def should_probe_back_to_tcp_passive(
    policy_mode: Optional[str] = None,
    last_mode: Optional[str] = None,
    success_total: int = 0,
    fail_total: int = 0,
    consecutive_failures: int = 0,
    auto_switch_count: int = 0,
    updated_at: Any = None,
    min_success_total: int = 20,
    max_failure_rate: float = 10.0,
    max_idle_minutes: int = 60,
    **_: Any,
) -> tuple[bool, str]:
    """判断是否应将 UDP 资产自动回切到 TCP_PASSIVE（自愈探针）。

    触发条件（全部满足）：
    - 当前策略模式为 ``UDP``
    - 累计成功样本 >= ``min_success_total``（避免新接入资产误判）
    - 失败率 >= ``max_failure_rate``（百分比）
    - 最近 ``updated_at`` 在 ``max_idle_minutes`` 内（避免对长期离线资产触发）
    - 自动切换次数未超上限（避免抖动循环）

    返回 ``(should_probe: bool, reason: str)``。
    """
    pm = normalize_stream_mode(policy_mode, default_mode=MODE_UDP)
    if pm != MODE_UDP:
        return False, f"policy_mode={pm}, not UDP, skip"

    try:
        s = int(success_total or 0)
        f = int(fail_total or 0)
    except (TypeError, ValueError):
        s = f = 0
    if s < int(min_success_total or 0):
        return False, f"success_total={s} < min_success_total={min_success_total}, insufficient samples"

    rate = calculate_failure_rate(s, f)
    threshold = float(max_failure_rate or 0.0)
    if rate < threshold:
        return False, f"failure_rate={rate}% < threshold={threshold}%, healthy"

    # updated_at 空闲检查
    if updated_at is not None and max_idle_minutes and int(max_idle_minutes or 0) > 0:
        try:
            if isinstance(updated_at, datetime):
                ts = updated_at
            else:
                # 兼容字符串/数字时间戳
                ts = datetime.fromisoformat(str(updated_at))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            idle_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
            idle_minutes = idle_seconds / 60.0
            if idle_minutes > float(max_idle_minutes):
                return False, f"idle {idle_minutes:.1f}min > {max_idle_minutes}min, skip stale asset"
        except Exception as e:
            logger.warning(f"should_probe_back_to_tcp_passive: updated_at parse failed: {e}")
            # 解析失败不阻断，继续判断

    try:
        asc = int(auto_switch_count or 0)
    except (TypeError, ValueError):
        asc = 0
    if asc >= 5:
        return False, f"auto_switch_count={asc} >= 5, avoid flapping"

    reason = (
        f"UDP unhealthy: failure_rate={rate}% >= {threshold}%, "
        f"success_total={s}, consecutive_failures={consecutive_failures}"
    )
    return True, reason
