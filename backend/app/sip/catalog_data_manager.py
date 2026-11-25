"""GB28181 设备目录/控制响应数据管理器。

GB28181 SIP 信令中，平台向下级设备发送的查询/控制命令（如目录查询、设备信息查询、
设备控制、配置下载等）通过 MESSAGE 携带 MANSCDP+xml 请求，设备异步以 MESSAGE 回送
响应。本管理器作为请求/响应的会合点（rendezvous）：

    1. 命令发送方调用 :meth:`wait_for` 等待响应（带超时）。
    2. handlers.py 收到响应报文后调用 :meth:`put` 存储并唤醒等待方。
    3. :meth:`monitor_loop` 周期清理过期条目，避免内存泄漏。

数据按 ``(gb_id, cmd_type)`` 二元组索引，``cmd_type`` 取自 MANSCDP 的 ``CmdType``
元素，例如：``Catalog``、``DirectoryInfo``、``DeviceInfo``、``DeviceStatus``、
``DeviceControl``、``ConfigDownload``、``ConfigSet``、``ConfigUpload``、
``PresetQuery``、``AlarmCodeResponse`` 等。

模块提供进程级单例 :data:`catalog_data_manager`。所有公开方法为 ``async``，
内部用 :class:`asyncio.Lock` 保护；模块导入绝不抛异常。
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from loguru import logger

from app.core.config import settings


def loop_time() -> float:
    """asyncio 单调时钟（wait_for 静止窗口用）。"""
    return asyncio.get_running_loop().time()


# 默认清理周期与条目过期阈值（秒）
_DEFAULT_MONITOR_INTERVAL = 60.0
_DEFAULT_ENTRY_TTL = 300.0
# wait_for 默认超时（秒）
_DEFAULT_WAIT_TIMEOUT = 10.0

# FIX [2026-11-20 P1] (wvp #1892 同款修复):这些查询的响应会被部分厂商（海康等）
# 拆成多个同 SN 的 SIP MESSAGE 分包发送。此前的 put() 后包覆盖前包、wait_for 首包
# 即返回，导致预置位列表不全。多包命令走"聚合 + 静止窗口"路径。
_MULTI_PACKET_CMDS = {"PresetQuery", "HomePosition"}
# 静止窗口：距最后一个分包超过该时长即视为收完
_MULTI_PACKET_SETTLE_SECONDS = 1.5


def _merge_preset_packets(packets: list[str]) -> str:
    """把同一查询的多个响应分包合并为单份 XML（按 PresetID 去重）。

    取首个含 PresetList 的分包作为模板，合并所有分包的 <Item>；无 PresetList 的
    分包（如错误响应）直接原样返回。
    """
    import copy
    import xml.etree.ElementTree as ET

    # FIX (bandit B314): 设备 XML 属网络输入，解析必须走 defusedxml 防 XXE；
    # defusedxml 不提供 tostring，序列化仍用 stdlib（无注入风险）
    from defusedxml import ElementTree as SafeET

    list_packets = [p for p in packets or [] if p]
    if not list_packets:
        return ""
    if len(list_packets) == 1:
        return list_packets[0]

    template = None
    seen_ids: set[str] = set()
    merged_items: list = []
    for pkt in list_packets:
        try:
            root = SafeET.fromstring(pkt)
        except Exception:
            continue
        plist = root.find(".//PresetList")
        if plist is None:
            continue
        if template is None:
            template = copy.deepcopy(root)
        for item in plist.findall("Item"):
            pid = (item.findtext("PresetID") or "").strip()
            dedupe_key = pid or ET.tostring(item, encoding="unicode")
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            merged_items.append(copy.deepcopy(item))
    if template is None:
        # 所有分包都无 PresetList:回退为最后一个分包（错误信息等）
        return list_packets[-1]

    plist = template.find(".//PresetList")
    if plist is not None:
        for child in list(plist.findall("Item")):
            plist.remove(child)
        for item in merged_items:
            plist.append(item)
        plist.set("Num", str(len(merged_items)))
    try:
        return ET.tostring(template, encoding="unicode")
    except Exception:
        return list_packets[0]


class _Entry:
    """单条响应缓存条目。"""

    __slots__ = ("body", "created_at", "event", "sn", "packets", "last_packet_mono", "complete")

    def __init__(self, body: str = "", sn: str = "") -> None:
        """Internal helper:   init  ."""
        self.body: str = body
        self.created_at: float = time.monotonic()
        # 等待方通过 event 被唤醒；put() 时 set()
        self.event: asyncio.Event = asyncio.Event()
        # 可选的 SN（MANSCDP 序号），用于精确匹配请求与响应
        self.sn: str = sn
        # FIX: 多包命令（PresetQuery/HomePosition）的分包缓存与静止窗口时间戳
        self.packets: list[str] = []
        self.last_packet_mono: float = 0.0
        # 收到无 PresetList 的终态分包（错误响应等）时直接置完成
        self.complete: bool = False

    def refresh(self, body: str, sn: str = "") -> None:
        """Refresh."""
        self.body = body
        self.created_at = time.monotonic()
        if sn:
            self.sn = sn
        self.event.set()


class CatalogDataManager:
    """设备目录/控制响应数据管理器（进程级单例 :data:`catalog_data_manager`）。"""

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self._lock = asyncio.Lock()
        # key: (gb_id, cmd_type) -> _Entry
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._monitor_running: bool = False
        self._monitor_interval = settings.CATALOG_MONITOR_INTERVAL_SECONDS
        self._entry_ttl = settings.CATALOG_ENTRY_TTL_SECONDS

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    async def put(self, gb_id: str, cmd_type: str, body: str, sn: str = "") -> None:
        """存储一条设备响应数据，并唤醒所有等待该 ``(gb_id, cmd_type)`` 的协程。

        若条目已存在则更新 body 并重新触发 event；若不存在则新建。

        FIX [2026-11-20 P1] (wvp #1892 同款修复):多包命令（PresetQuery/HomePosition）
        不再覆盖式写入——分包追加缓存,由 wait_for 按"静止窗口"聚合后返回完整列表。
        """
        if not gb_id or not cmd_type:
            return
        key = (str(gb_id), str(cmd_type))
        is_multi = str(cmd_type) in _MULTI_PACKET_CMDS
        async with self._lock:
            entry = self._entries.get(key)
            if is_multi:
                # 注意:必须复用已有条目对象（wait_for 会先创建占位条目并在其 event 上
                # 等待），整条替换会导致等待方永远等不到唤醒
                if entry is None:
                    entry = _Entry(sn=sn or "")
                    self._entries[key] = entry
                if not getattr(entry, "packets", None):
                    entry.packets = []
                entry.packets.append(body or "")
                entry.last_packet_mono = time.monotonic()
                # 合并结果写入 body,首个分包唤醒等待方进入静止窗口等待
                entry.body = _merge_preset_packets(entry.packets)
                if sn:
                    entry.sn = sn
                entry.event.set()
            else:
                if entry is None:
                    entry = _Entry(body=body or "", sn=sn or "")
                    self._entries[key] = entry
                else:
                    entry.refresh(body or "", sn or "")
        logger.debug(f"catalog_data_manager.put: gb_id={gb_id} cmd_type={cmd_type} sn={sn or '-'} body_len={len(body or '')}")

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    async def get(self, gb_id: str, cmd_type: str) -> str:
        """同步取已缓存的响应 body；不存在返回空串。"""
        if not gb_id or not cmd_type:
            return ""
        key = (str(gb_id), str(cmd_type))
        async with self._lock:
            entry = self._entries.get(key)
            return entry.body if entry is not None else ""

    async def wait_for(
        self,
        gb_id: str,
        cmd_type: str,
        timeout_seconds: float = _DEFAULT_WAIT_TIMEOUT,
        *,
        clear_on_read: bool = True,
    ) -> str:
        """等待 ``put(gb_id, cmd_type, ...)`` 被调用，返回响应 body。

        - 若已有缓存且 event 已 set，立即返回。
        - 否则阻塞最多 ``timeout_seconds`` 秒；超时返回空串。
        - ``clear_on_read=True``（默认）时，读取后清除条目并重置 event，
          避免同一响应被重复消费。

        典型用法::

            # 发送查询前确保条目干净
            await catalog_data_manager.invalidate(gb_id, "DeviceInfo")
            # ... 发送 SIP MESSAGE 查询 ...
            body = await catalog_data_manager.wait_for(gb_id, "DeviceInfo", timeout=10)
            if not body:
                raise TimeoutError("device did not respond")
        """
        if not gb_id or not cmd_type:
            return ""
        key = (str(gb_id), str(cmd_type))
        timeout = float(timeout_seconds or 0)
        if timeout <= 0:
            timeout = _DEFAULT_WAIT_TIMEOUT

        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _Entry()
                self._entries[key] = entry

        is_multi = str(cmd_type) in _MULTI_PACKET_CMDS
        try:
            await asyncio.wait_for(entry.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"catalog_data_manager.wait_for timeout: gb_id={gb_id} cmd_type={cmd_type} timeout={timeout}s")
            return ""

        if is_multi:
            # FIX [2026-11-20 P1]: 多包命令等待"静止窗口"聚合完所有分包再返回
            deadline = loop_time() + timeout
            while True:
                now_mono = loop_time()
                settled = (now_mono - entry.last_packet_mono) >= _MULTI_PACKET_SETTLE_SECONDS
                if settled or now_mono >= deadline or entry.complete:
                    break
                await asyncio.sleep(0.2)
            body = _merge_preset_packets(entry.packets) or (entry.body or "")
        else:
            body = entry.body or ""
        if clear_on_read:
            async with self._lock:
                # 仅在仍是同一个 entry 时清除（避免清掉更新的响应）
                cur = self._entries.get(key)
                if cur is entry:
                    self._entries.pop(key, None)
        return body

    # ------------------------------------------------------------------
    # 失效
    # ------------------------------------------------------------------

    async def invalidate(
        self,
        gb_id: Optional[str] = None,
        cmd_type: Optional[str] = None,
    ) -> int:
        """清除匹配的条目，返回清除数量。

        - ``gb_id=None, cmd_type=None``：清空全部。
        - 仅 ``gb_id``：清除该设备的所有 cmd_type 条目。
        - 仅 ``cmd_type``：清除所有设备的该 cmd_type 条目。
        - 两者都给：清除精确匹配的单一条目。
        """
        cleared = 0
        async with self._lock:
            if gb_id is None and cmd_type is None:
                cleared = len(self._entries)
                self._entries.clear()
                return cleared
            keys_to_remove: list[tuple[str, str]] = []
            for k in self._entries.keys():
                kg, kc = k
                if gb_id is not None and kg != str(gb_id):
                    continue
                if cmd_type is not None and kc != str(cmd_type):
                    continue
                keys_to_remove.append(k)
            for k in keys_to_remove:
                self._entries.pop(k, None)
                cleared += 1
        return cleared

    # ------------------------------------------------------------------
    # 监控循环
    # ------------------------------------------------------------------

    async def monitor_loop(self) -> None:
        """周期清理过期条目。

        清理超过 ``CATALOG_ENTRY_TTL_SECONDS``（默认 300s）未被消费/更新的条目。
        由 main.py / startup.py 在应用启动时通过 ``asyncio.create_task`` 调度，
        应用关闭时取消。
        """
        if self._monitor_running:
            return
        self._monitor_running = True
        logger.info(f"catalog_data_manager monitor_loop started: interval={self._monitor_interval}s ttl={self._entry_ttl}s")
        try:
            while True:
                await asyncio.sleep(self._monitor_interval)
                try:
                    await self._cleanup_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"catalog_data_manager monitor_loop error: {e}")
        except asyncio.CancelledError:
            logger.info("catalog_data_manager monitor_loop cancelled")
        finally:
            self._monitor_running = False

    async def _cleanup_once(self) -> int:
        """执行一次过期清理，返回清理数量。"""
        now = time.monotonic()
        cleared = 0
        async with self._lock:
            stale: list[tuple[str, str]] = []
            for key, entry in self._entries.items():
                # 仍在等待（event 未 set）的条目不清理，避免清掉尚未到达的响应
                if not entry.event.is_set():
                    continue
                if (now - entry.created_at) > self._entry_ttl:
                    stale.append(key)
            for key in stale:
                self._entries.pop(key, None)
                cleared += 1
        if cleared:
            logger.info(f"catalog_data_manager cleanup removed {cleared} stale entries")
        return cleared

    # ------------------------------------------------------------------
    # 调试 / 状态
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """返回当前缓存统计（调试用，非 async）。"""
        return {
            "entries": len(self._entries),
            "monitor_running": self._monitor_running,
            "entry_ttl": self._entry_ttl,
            "monitor_interval": self._monitor_interval,
        }


# 进程级单例
catalog_data_manager = CatalogDataManager()
