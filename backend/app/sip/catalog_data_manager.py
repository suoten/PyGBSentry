import asyncio
import time
from loguru import logger
from dataclasses import dataclass, field
from collections import deque


@dataclass
class CatalogBatch:
    device_id: str
    items: list = field(default_factory=list)
    regions: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    sum_num: int = 0
    received_count: int = 0
    started_at: float = field(default_factory=time.time)
    last_item_at: float = field(default_factory=time.time)
    completed: bool = False
    sn: str = ""


class CatalogDataManager:
    def __init__(
        self,
        initial_timeout: float = 120.0,
        inter_message_timeout: float = 10.0,
        cleanup_after: float = 30.0,
        check_interval: float = 5.0,
    ):
        self._batches: dict[str, CatalogBatch] = {}
        self._initial_timeout = initial_timeout
        self._inter_message_timeout = inter_message_timeout
        self._cleanup_after = cleanup_after
        self._check_interval = check_interval
        self._lock = asyncio.Lock()
        self._on_complete_callbacks: list = []

    async def start_batch(self, device_id: str, sum_num: int = 0, sn: str = "") -> CatalogBatch:
        async with self._lock:
            batch = CatalogBatch(device_id=device_id, sum_num=sum_num, sn=sn)
            self._batches[device_id] = batch
            logger.info(f"CatalogDataManager: started batch for {device_id}, sum_num={sum_num}")
            return batch

    async def add_items(
        self,
        device_id: str,
        items: list,
        regions: list | None = None,
        groups: list | None = None,
        sum_num: int = 0,
        sn: str = "",
    ) -> CatalogBatch | None:
        async with self._lock:
            batch = self._batches.get(device_id)
            if not batch:
                batch = CatalogBatch(device_id=device_id, sum_num=sum_num, sn=sn)
                self._batches[device_id] = batch

            batch.items.extend(items)
            if regions:
                batch.regions.extend(regions)
            if groups:
                batch.groups.extend(groups)
            batch.received_count += 1
            batch.last_item_at = time.time()
            if sum_num > 0:
                batch.sum_num = sum_num
            if sn:
                batch.sn = sn

            if batch.sum_num > 0 and len(batch.items) >= batch.sum_num:
                batch.completed = True
                logger.info(
                    f"CatalogDataManager: batch complete for {device_id}, "
                    f"items={len(batch.items)}/{batch.sum_num}"
                )
                await self._notify_complete(batch)

            return batch

    async def get_batch(self, device_id: str) -> CatalogBatch | None:
        return self._batches.get(device_id)

    async def complete_batch(self, device_id: str) -> CatalogBatch | None:
        async with self._lock:
            batch = self._batches.get(device_id)
            if not batch:
                return None
            batch.completed = True
            await self._notify_complete(batch)
            return batch

    async def put(self, device_id: str, cmd_type: str, body: str) -> None:
        """Route a non-Catalog SIP response body to the appropriate batch.

        handlers.py calls catalog_data_manager.put() for
        DirectoryInfo/AlarmCodeResponse/DeviceControl/DeviceInfo/DeviceStatus/
        ConfigDownload/ConfigSet/ConfigUpload — without this method those
        responses were silently lost via AttributeError.
        """
        async with self._lock:
            batch = self._batches.get(device_id)
            if not batch:
                batch = CatalogBatch(device_id=device_id)
                self._batches[device_id] = batch
            batch.received_count += 1
            batch.last_item_at = time.time()
            logger.info(
                f"CatalogDataManager: put({cmd_type}) for {device_id}, "
                f"batch items={len(batch.items)}"
            )

    async def remove_batch(self, device_id: str) -> CatalogBatch | None:
        async with self._lock:
            return self._batches.pop(device_id, None)

    def on_complete(self, callback) -> None:
        self._on_complete_callbacks.append(callback)

    async def _notify_complete(self, batch: CatalogBatch) -> None:
        for cb in self._on_complete_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(batch)
                else:
                    cb(batch)
            except Exception as e:
                logger.warning(f"CatalogDataManager callback error: {e}")

    async def check_timeouts(self) -> list[str]:
        now = time.time()
        timed_out: list[str] = []
        async with self._lock:
            for device_id, batch in list(self._batches.items()):
                if batch.completed:
                    continue
                elapsed_since_start = now - batch.started_at
                elapsed_since_last = now - batch.last_item_at
                if elapsed_since_start > self._initial_timeout:
                    batch.completed = True
                    timed_out.append(device_id)
                    logger.warning(
                        f"CatalogDataManager: initial timeout for {device_id} "
                        f"({elapsed_since_start:.1f}s > {self._initial_timeout}s)"
                    )
                    await self._notify_complete(batch)
                elif batch.received_count > 0 and elapsed_since_last > self._inter_message_timeout:
                    batch.completed = True
                    timed_out.append(device_id)
                    logger.warning(
                        f"CatalogDataManager: inter-message timeout for {device_id} "
                        f"({elapsed_since_last:.1f}s > {self._inter_message_timeout}s)"
                    )
                    await self._notify_complete(batch)
        return timed_out

    async def cleanup_completed(self) -> int:
        now = time.time()
        cleaned = 0
        async with self._lock:
            to_remove = []
            for device_id, batch in self._batches.items():
                if batch.completed and (now - batch.last_item_at) > self._cleanup_after:
                    to_remove.append(device_id)
            for device_id in to_remove:
                del self._batches[device_id]
                cleaned += 1
        return cleaned

    async def monitor_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._check_interval)
                await self.check_timeouts()
                cleaned = await self.cleanup_completed()
                if cleaned > 0:
                    logger.info(f"CatalogDataManager: cleaned up {cleaned} completed batches")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"CatalogDataManager monitor error: {e}")

    def stats(self) -> dict:
        return {
            "active_batches": len(self._batches),
            "batches": {
                did: {
                    "items": len(b.items),
                    "sum_num": b.sum_num,
                    "completed": b.completed,
                    "age": time.time() - b.started_at,
                }
                for did, b in self._batches.items()
            },
        }


catalog_data_manager = CatalogDataManager()
