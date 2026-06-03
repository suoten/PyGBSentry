import asyncio
import secrets
import time
from loguru import logger


class SsrcManager:
    def __init__(
        self,
        live_range: tuple[int, int] = (1, 999999999),
        playback_range: tuple[int, int] = (1000000001, 1999999999),
    ):
        self._lock = asyncio.Lock()
        self._live_allocated: set[int] = set()
        self._playback_allocated: set[int] = set()
        self._live_range = live_range
        self._playback_range = playback_range
        self._ssrc_to_stream: dict[int, str] = {}
        self._stream_to_ssrc: dict[str, int] = {}
        self._ssrc_timestamps: dict[int, float] = {}
        self._max_ssrc = 999999999
        self._live_counter = secrets.randbelow(100000000) + 1
        self._playback_counter = secrets.randbelow(100000000) + 1

    # 启动时从DB StreamSession恢复活跃SSRC，防止进程重启后SSRC冲突
    async def restore_from_db(self) -> int:
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.stream_session import StreamSession
            from sqlalchemy import select
            restored = 0
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(StreamSession.ssrc, StreamSession.stream, StreamSession.app).where(
                        StreamSession.ssrc.isnot(None),
                        StreamSession.ssrc != "",
                    )
                )
                rows = result.all()
                for ssrc_str, stream_id, app in rows:
                    if not ssrc_str:
                        continue
                    try:
                        ssrc_int = int(ssrc_str)
                    except (ValueError, TypeError):
                        continue
                    is_playback = (app or "").lower() in ("playback", "download")
                    allocated = self._playback_allocated if is_playback else self._live_allocated
                    if ssrc_int not in allocated:
                        allocated.add(ssrc_int)
                        self._ssrc_timestamps[ssrc_int] = time.time()
                        if stream_id:
                            self._ssrc_to_stream[ssrc_int] = stream_id
                            self._stream_to_ssrc[stream_id] = ssrc_int
                        restored += 1
            if restored > 0:
                logger.info(f"SSRC Manager restored {restored} active SSRC allocations from DB")
            return restored
        except Exception as e:
            logger.warning(f"SSRC Manager DB restore failed (non-fatal): {e}")
            return 0

    def _next_live_value(self) -> int:
        self._live_counter += 1
        if self._live_counter > self._max_ssrc:
            self._live_counter = 1
        # GB28181协议 — SSRC后缀不超过9位
        return min(self._live_counter, self._max_ssrc)

    def _next_playback_value(self) -> int:
        self._playback_counter += 1
        if self._playback_counter > self._max_ssrc:
            self._playback_counter = 1
        # GB28181协议 — SSRC后缀不超过9位
        return min(self._playback_counter, self._max_ssrc)

    async def allocate(self, is_playback: bool = False, stream_id: str = "") -> str:
        async with self._lock:
            allocated = self._playback_allocated if is_playback else self._live_allocated
            prefix = "1" if is_playback else "0"

            for _ in range(100):
                if is_playback:
                    suffix = self._next_playback_value()
                else:
                    suffix = self._next_live_value()
                ssrc_int = int(f"{prefix}{suffix:09d}")
                if ssrc_int not in allocated:
                    allocated.add(ssrc_int)
                    ssrc_str = f"{prefix}{suffix:09d}"
                    self._ssrc_timestamps[ssrc_int] = time.time()
                    if stream_id:
                        self._ssrc_to_stream[ssrc_int] = stream_id
                        self._stream_to_ssrc[stream_id] = ssrc_int
                    return ssrc_str

            logger.error("SSRC allocation exhausted all attempts, using timestamp fallback")
            for _attempt in range(10):
                fallback = int(time.time() * 1000 + _attempt) % 1000000000
                fallback_ssrc = f"{prefix}{fallback:09d}"
                fallback_int = int(fallback_ssrc)
                if fallback_int not in allocated:
                    allocated.add(fallback_int)
                    self._ssrc_timestamps[fallback_int] = time.time()
                    if stream_id:
                        self._ssrc_to_stream[fallback_int] = stream_id
                        self._stream_to_ssrc[stream_id] = fallback_int
                    return fallback_ssrc
            logger.critical("SSRC allocation completely exhausted, returning empty SSRC")
            return ""

    async def release(self, ssrc: str) -> None:
        async with self._lock:
            try:
                ssrc_int = int(ssrc)
            except (ValueError, TypeError):
                return
            self._live_allocated.discard(ssrc_int)
            self._playback_allocated.discard(ssrc_int)
            stream_id = self._ssrc_to_stream.pop(ssrc_int, None)
            if stream_id:
                self._stream_to_ssrc.pop(stream_id, None)
            self._ssrc_timestamps.pop(ssrc_int, None)

    async def allocate_specific_ssrc(self, ssrc: str, is_playback: bool = False) -> bool:
        """Allocate a specific SSRC value (used when device modifies SSRC in 200 OK)."""
        # allocate_specific_ssrc — 设备在200 OK中修改SSRC时需要注册新SSRC
        async with self._lock:
            try:
                ssrc_int = int(ssrc)
            except (ValueError, TypeError):
                return False
            # GB10 SSRC跨集合冲突检查 — 确保SSRC不在另一集合中已分配
            if ssrc_int in self._live_allocated and not is_playback:
                return True  # Already in live set, idempotent
            if ssrc_int in self._playback_allocated and is_playback:
                return True  # Already in playback set, idempotent
            # Check cross-set conflict
            if ssrc_int in self._live_allocated and is_playback:
                logger.warning(f"SSRC {ssrc} conflict: already allocated in live set, cannot allocate as playback")
                return False
            if ssrc_int in self._playback_allocated and not is_playback:
                logger.warning(f"SSRC {ssrc} conflict: already allocated in playback set, cannot allocate as live")
                return False
            # 仅使用is_playback参数决定集合，不根据SSRC首字符推断
            # 之前：is_playback=False但SSRC以"1"开头时错误分配到playback集合，可能导致SSRC冲突
            if is_playback:
                allocated = self._playback_allocated
            else:
                allocated = self._live_allocated
            allocated.add(ssrc_int)
            self._ssrc_timestamps[ssrc_int] = time.time()
            return True

    # release_ssrc — alias for release() to fix method name mismatch in response_handler.py
    async def release_ssrc(self, ssrc: str) -> None:
        await self.release(ssrc)

    async def bind_stream(self, ssrc: str, stream_id: str) -> None:
        async with self._lock:
            try:
                ssrc_int = int(ssrc)
            except (ValueError, TypeError):
                return
            self._ssrc_to_stream[ssrc_int] = stream_id
            self._stream_to_ssrc[stream_id] = ssrc_int

    async def lookup_stream_by_ssrc(self, ssrc: str) -> str | None:
        try:
            ssrc_int = int(ssrc)
        except (ValueError, TypeError):
            return None
        return self._ssrc_to_stream.get(ssrc_int)

    async def lookup_ssrc_by_stream(self, stream_id: str) -> str | None:
        ssrc_int = self._stream_to_ssrc.get(stream_id)
        if ssrc_int is not None:
            return str(ssrc_int)
        return None

    async def is_allocated(self, ssrc: str) -> bool:
        try:
            ssrc_int = int(ssrc)
        except (ValueError, TypeError):
            return False
        return ssrc_int in self._live_allocated or ssrc_int in self._playback_allocated

    async def cleanup_stale(self, max_age_seconds: int = 3600) -> int:
        # cleanup_stale now checks DB StreamSession activity instead of allocation time alone
        # Default max_age raised to 86400 (24h) to avoid killing active long-running streams
        async with self._lock:
            active_ssrcs: set[int] = set()
            try:
                from app.db.session import AsyncSessionLocal
                from app.models.stream_session import StreamSession as DBStreamSession
                from sqlalchemy import select
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(DBStreamSession.ssrc).where(
                            DBStreamSession.ssrc.isnot(None),
                            DBStreamSession.ssrc != "",
                        )
                    )
                    for (ssrc_val,) in result.all():
                        try:
                            active_ssrcs.add(int(ssrc_val))
                        except (ValueError, TypeError):
                            pass
            except Exception as e:
                logger.warning(f"SSRC cleanup_stale DB check failed, skipping cleanup to avoid clearing active SSRCs: {e}")
                return 0  # DB不可用时跳过清理，避免误清活跃流的SSRC

            now = time.time()
            stale_ssrcs = []
            for ssrc_int, ts in list(self._ssrc_timestamps.items()):
                if ssrc_int in active_ssrcs:
                    continue
                if (now - ts) > max_age_seconds:
                    stale_ssrcs.append(ssrc_int)

            for ssrc_int in stale_ssrcs:
                self._live_allocated.discard(ssrc_int)
                self._playback_allocated.discard(ssrc_int)
                stream_id = self._ssrc_to_stream.pop(ssrc_int, None)
                if stream_id:
                    self._stream_to_ssrc.pop(stream_id, None)
                self._ssrc_timestamps.pop(ssrc_int, None)
            return len(stale_ssrcs)

    async def cleanup_loop(self, interval: int = 300, max_age_seconds: int = 86400) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                cleaned = await self.cleanup_stale(max_age_seconds)
                if cleaned > 0:
                    logger.info(f"SSRC Manager cleaned up {cleaned} stale entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"SSRC Manager cleanup error: {e}")

    def stats(self) -> dict:
        return {
            "live_allocated": len(self._live_allocated),
            "playback_allocated": len(self._playback_allocated),
            "stream_bindings": len(self._ssrc_to_stream),
        }


ssrc_manager = SsrcManager()
