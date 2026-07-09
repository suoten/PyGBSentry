"""GB28181 SSRC 分配与管理器。

GB28181 协议规定 SSRC（同步源标识）为 10 位十进制数字，编码规则如下：

    位 1        : 流类型，0=实时流（点播/直播），1=回放流
    位 2-6      : 域编码前缀（5 位，取自 SIP 域/行政区域码前 5 位）
    位 7-10     : 序号（4 位，0000-9999，进程内递增并去重）

本模块提供进程级单例 :data:`ssrc_manager`，负责：
    * :meth:`allocate` —— 分配一个新的 SSRC
    * :meth:`allocate_specific_ssrc` —— 预占设备指定的 SSRC（级联/设备主动指定）
    * :meth:`release` / :meth:`release_ssrc` —— 释放 SSRC
    * :meth:`bind_stream` / :meth:`lookup_ssrc_by_stream` —— SSRC 与流ID双向绑定
    * :meth:`cleanup_loop` —— 周期清理过期/泄漏的 SSRC
    * :meth:`restore_from_db` —— 启动时从 ``stream_sessions`` 表恢复在用 SSRC

线程安全：所有公开方法均为 ``async``，内部用 :class:`asyncio.Lock` 保护。
模块导入绝不抛异常 —— DB 模型在方法内延迟导入。
"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.core.config import settings


# SSRC 编码位数
_SSRC_LEN = 10
_SERIAL_MAX = 10000  # 4 位序号上限（0000-9999）
_DOMAIN_PREFIX_LEN = 5


def _domain_prefix(domain: str | None) -> str:
    """从 SIP 域 / 行政区域码提取 5 位前缀。

    GB28181 设备 ID 前 6 位为行政区域码（如 ``340200``），SSRC 取前 5 位。
    若域过长取前 5 位数字；过短则右补 0；完全无数字则回退 ``"00000"``。
    """
    raw = (domain or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return "00000"
    if len(digits) >= _DOMAIN_PREFIX_LEN:
        return digits[:_DOMAIN_PREFIX_LEN]
    return digits.ljust(_DOMAIN_PREFIX_LEN, "0")


def _is_valid_ssrc(ssrc: str) -> bool:
    """校验 SSRC 是否为 10 位纯数字。"""
    if not ssrc:
        return False
    s = str(ssrc).strip()
    if len(s) != _SSRC_LEN:
        return False
    return s.isdigit()


def _ssrc_stream_type(ssrc: str) -> int:
    """返回 SSRC 首位（0=实时, 1=回放）；非法返回 -1。"""
    if not _is_valid_ssrc(ssrc):
        return -1
    return int(str(ssrc)[0])


class SsrcManager:
    """SSRC 分配与管理器（进程级单例 :data:`ssrc_manager`）。"""

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self._lock = asyncio.Lock()
        # 已分配的 SSRC 集合（按流类型分桶，便于按桶统计/去重）
        self._live_allocated: set[str] = set()
        self._playback_allocated: set[str] = set()
        # 序号计数器：外部可在 restore_from_db 失败时设置为 secrets.randbelow(500000000)+1
        # 以降低与历史 SSRC 冲突概率（见 server.py / invite.py 中的恢复逻辑）
        self._live_counter: int = 1
        self._playback_counter: int = 1
        # 流绑定：stream_id -> ssrc，及反向 ssrc -> stream_id
        self._stream_to_ssrc: dict[str, str] = {}
        self._ssrc_to_stream: dict[str, str] = {}
        # SSRC 分配时间（用于 cleanup_loop 清理泄漏）
        self._alloc_time: dict[str, float] = {}
        # cleanup_loop 控制位
        self._cleanup_running: bool = False
        # 默认清理周期与过期阈值（秒）
        self._cleanup_interval = float(getattr(settings, "SSRC_CLEANUP_INTERVAL_SECONDS", 300.0) or 300.0)
        self._stale_threshold = float(getattr(settings, "SSRC_STALE_THRESHOLD_SECONDS", 3600.0) or 3600.0)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _bucket(self, is_playback: bool) -> set[str]:
        """Internal helper:  bucket."""
        return self._playback_allocated if is_playback else self._live_allocated

    def _next_serial(self, is_playback: bool) -> int:
        """取下一个 4 位序号（0-9999），并在 10000 范围内去重。"""
        bucket = self._bucket(is_playback)
        counter_attr = "_playback_counter" if is_playback else "_live_counter"
        # 最多尝试 10000 次（覆盖全部序号空间）
        for _ in range(_SERIAL_MAX):
            serial = getattr(self, counter_attr) % _SERIAL_MAX
            setattr(self, counter_attr, getattr(self, counter_attr) + 1)
            candidate = self._assemble(serial, is_playback)
            if candidate not in bucket:
                return serial
        # 序号空间耗尽
        return -1

    def _assemble(self, serial: int, is_playback: bool) -> str:
        """Internal helper:  assemble."""
        type_digit = "1" if is_playback else "0"
        prefix = _domain_prefix(getattr(settings, "SIP_DOMAIN", "") or "")
        return f"{type_digit}{prefix}{serial:04d}"

    # ------------------------------------------------------------------
    # 分配
    # ------------------------------------------------------------------

    async def allocate(self, is_playback: bool = False) -> str:
        """分配一个新的 SSRC。

        Returns:
            10 位 SSRC 字符串；序号空间耗尽时返回空串（调用方需容忍并报错）。
        """
        import time as _time
        async with self._lock:
            serial = self._next_serial(is_playback)
            if serial < 0:
                logger.error(
                    f"SSRC allocation exhausted: is_playback={is_playback}, "
                    f"allocated={len(self._bucket(is_playback))}"
                )
                return ""
            ssrc = self._assemble(serial, is_playback)
            self._bucket(is_playback).add(ssrc)
            self._alloc_time[ssrc] = _time.monotonic()
            return ssrc

    async def allocate_specific_ssrc(self, ssrc: str, is_playback: bool = False) -> bool:
        """预占设备/级联指定的 SSRC。

        若该 SSRC 已被占用则返回 ``False``（调用方应回滚 DB 引用）。
        ``is_playback`` 由调用方根据 SSRC 首位推断或显式传入。
        """
        if not _is_valid_ssrc(ssrc):
            logger.warning(f"allocate_specific_ssrc: invalid SSRC '{ssrc}'")
            return False
        import time as _time
        async with self._lock:
            # 校验流类型一致性：若显式传入的 is_playback 与 SSRC 首位不符，按 SSRC 首位归桶
            inferred = (_ssrc_stream_type(ssrc) == 1)
            bucket = self._bucket(inferred)
            other = self._bucket(not inferred)
            if ssrc in bucket or ssrc in other:
                logger.warning(f"allocate_specific_ssrc: SSRC {ssrc} already allocated")
                return False
            bucket.add(ssrc)
            self._alloc_time[ssrc] = _time.monotonic()
            return True

    # ------------------------------------------------------------------
    # 释放
    # ------------------------------------------------------------------

    async def release(self, ssrc: str) -> None:
        """释放一个 SSRC（同时清除流绑定）。"""
        if not ssrc:
            return
        async with self._lock:
            self._live_allocated.discard(ssrc)
            self._playback_allocated.discard(ssrc)
            self._alloc_time.pop(ssrc, None)
            stream_id = self._ssrc_to_stream.pop(ssrc, None)
            if stream_id:
                self._stream_to_ssrc.pop(stream_id, None)

    async def release_ssrc(self, ssrc: str) -> None:
        """``release`` 的别名，保持与现有调用方命名一致。"""
        await self.release(ssrc)

    # ------------------------------------------------------------------
    # 流绑定
    # ------------------------------------------------------------------

    async def bind_stream(self, ssrc: str, stream_id: str) -> None:
        """将 SSRC 与流ID双向绑定。

        若该 stream_id 之前绑定了别的 SSRC，旧绑定会被清除。
        """
        if not ssrc or not stream_id:
            return
        async with self._lock:
            # 清除该 stream_id 的旧绑定
            old_ssrc = self._stream_to_ssrc.get(stream_id)
            if old_ssrc and old_ssrc != ssrc:
                self._ssrc_to_stream.pop(old_ssrc, None)
            self._stream_to_ssrc[stream_id] = ssrc
            self._ssrc_to_stream[ssrc] = stream_id

    async def lookup_ssrc_by_stream(self, stream_id: str) -> str:
        """按流ID查 SSRC；未绑定返回空串。"""
        if not stream_id:
            return ""
        async with self._lock:
            return self._stream_to_ssrc.get(stream_id, "")

    # ------------------------------------------------------------------
    # 恢复与清理
    # ------------------------------------------------------------------

    async def restore_from_db(self) -> int:
        """启动时从 ``stream_sessions`` 表恢复在用 SSRC。

        扫描所有非 ``_ssrc_reserve`` 且 ssrc 非空的会话，将其 SSRC 重新标记为已分配，
        并重建 stream 绑定。同时将计数器推进到避免与历史 SSRC 冲突的位置。

        Returns:
            恢复的 SSRC 数量。失败时返回 0（调用方通常会回退到随机大计数器）。
        """
        restored = 0
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.stream_session import StreamSession
            from sqlalchemy import select
        except Exception as e:
            logger.warning(f"restore_from_db: import failed: {e}")
            return 0

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(StreamSession.id, StreamSession.stream, StreamSession.ssrc).where(
                    StreamSession.ssrc.is_not(None),
                    StreamSession.ssrc != "",
                    StreamSession.app != "_ssrc_reserve",
                )
                result = await session.execute(stmt)
                rows = result.all()
        except Exception as e:
            logger.error(f"restore_from_db: query failed: {e}")
            return 0

        async with self._lock:
            import time as _time
            now = _time.monotonic()
            for row in rows:
                stream_session_id, stream_name, ssrc = row
                if not _is_valid_ssrc(ssrc):
                    continue
                inferred = (_ssrc_stream_type(ssrc) == 1)
                bucket = self._bucket(inferred)
                bucket.add(ssrc)
                self._alloc_time[ssrc] = now
                # 重建流绑定：优先用 stream_session.id，回退 stream 字段
                sid = stream_session_id or stream_name
                if sid:
                    self._stream_to_ssrc[sid] = ssrc
                    self._ssrc_to_stream[ssrc] = sid
                restored += 1
            # 推进计数器，避免新分配的序号与已恢复的 SSRC 冲突
            self._bump_counters_above_restored()

        if restored:
            logger.info(f"SSRC manager restored {restored} in-use SSRCs from DB")
        return restored

    def _bump_counters_above_restored(self) -> None:
        """将 live/playback 计数器推进到超过已恢复 SSRC 的最大序号。"""
        for is_playback, counter_attr in ((False, "_live_counter"), (True, "_playback_counter")):
            bucket = self._bucket(is_playback)
            max_serial = -1
            prefix = _domain_prefix(getattr(settings, "SIP_DOMAIN", "") or "")
            type_digit = "1" if is_playback else "0"
            for ssrc in bucket:
                # 仅统计与本进程域前缀一致的 SSRC
                if len(ssrc) == _SSRC_LEN and ssrc[0] == type_digit and ssrc[1:6] == prefix:
                    try:
                        serial = int(ssrc[6:10])
                        if serial > max_serial:
                            max_serial = serial
                    except ValueError:
                        logger.debug("swallowed_exception", exc_info=True)
            if max_serial >= 0:
                cur = getattr(self, counter_attr)
                if cur <= max_serial:
                    setattr(self, counter_attr, max_serial + 1)

    async def cleanup_loop(self) -> None:
        """周期清理过期/泄漏的 SSRC。

        - 清理已分配但超过 ``SSRC_STALE_THRESHOLD_SECONDS`` 未绑定流且未释放的 SSRC。
        - 由 server.py 在启动时通过 fire_and_forget 调度。
        """
        if self._cleanup_running:
            return
        self._cleanup_running = True
        logger.info(f"SSRC cleanup loop started: interval={self._cleanup_interval}s stale={self._stale_threshold}s")
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                try:
                    await self._cleanup_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"SSRC cleanup loop error: {e}")
        except asyncio.CancelledError:
            logger.info("SSRC cleanup loop cancelled")
        finally:
            self._cleanup_running = False

    async def _cleanup_once(self) -> int:
        """执行一次清理，返回清理的 SSRC 数量。"""
        import time as _time
        released = 0
        async with self._lock:
            now = _time.monotonic()
            stale: list[str] = []
            for ssrc, alloc_at in list(self._alloc_time.items()):
                # 已绑定流的 SSRC 不清理（仍在用）
                if ssrc in self._ssrc_to_stream:
                    continue
                if (now - alloc_at) > self._stale_threshold:
                    stale.append(ssrc)
            for ssrc in stale:
                self._live_allocated.discard(ssrc)
                self._playback_allocated.discard(ssrc)
                self._alloc_time.pop(ssrc, None)
                released += 1
        if released:
            logger.info(f"SSRC cleanup released {released} stale entries")
        return released

    # ------------------------------------------------------------------
    # 调试 / 状态
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """返回当前 SSRC 使用统计（调试用，非 async）。"""
        return {
            "live_allocated": len(self._live_allocated),
            "playback_allocated": len(self._playback_allocated),
            "live_counter": self._live_counter,
            "playback_counter": self._playback_counter,
            "stream_bindings": len(self._stream_to_ssrc),
            "cleanup_running": self._cleanup_running,
        }


# 进程级单例
ssrc_manager = SsrcManager()
