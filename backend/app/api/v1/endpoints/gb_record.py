"""GB28181 设备录像兼容端点。

提供 GB28181 标准风格的设备录像查询/下载/进度/停止接口，
内部转发到 device_record 端点的实际实现，做参数与响应格式转换。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import device_record as device_record_ep
from app.api.v1.endpoints.device_record import DeviceRecordDownloadStart
from app.models.device_record_download_task import DeviceRecordDownloadTask

router = APIRouter()


def _parse_gb_time(raw: str) -> datetime:
    """Parse GB28181-style time string ('YYYY-MM-DD HH:MM:SS' or ISO 8601) to UTC datetime."""
    if not raw:
        return datetime.now(timezone.utc)
    # Try ISO 8601 first (e.g., "2026-04-01T01:00:00+00:00")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    # Fallback: "YYYY-MM-DD HH:MM:SS"
    try:
        dt = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


async def _find_download_task_by_stream(db: AsyncSession, *, stream: str = "", **kwargs: Any) -> Any:
    """Find a DeviceRecordDownloadTask by its stream identifier."""
    if not stream:
        return None
    try:
        result = await db.execute(
            select(DeviceRecordDownloadTask).where(DeviceRecordDownloadTask.stream == stream)
        )
        return result.scalars().first()
    except Exception:
        return None


async def query_record_compat(
    *,
    device_id: str,
    channel_id: str,
    startTime: str,
    endTime: str,
    db: AsyncSession,
    current_user: Any,
) -> dict[str, Any]:
    """GB28181-compatible device record query.

    Accepts camelCase parameters (startTime/endTime as strings) and returns
    a ``{code, data: {sumNum, recordList}}`` envelope.
    """
    start_dt = _parse_gb_time(startTime)
    end_dt = _parse_gb_time(endTime)

    records = await device_record_ep.query_device_records(
        device_id=device_id,
        channel_id=channel_id,
        start_time=start_dt,
        end_time=end_dt,
        db=db,
        current_user=current_user,
    )

    record_list = list(records) if records else []
    return {
        "code": 0,
        "data": {
            "sumNum": len(record_list),
            "recordList": record_list,
        },
    }


async def start_download_compat(
    *,
    device_id: str,
    channel_id: str,
    startTime: str,
    endTime: str,
    downloadSpeed: int = 1,
    db: AsyncSession,
    current_user: Any,
) -> dict[str, Any]:
    """GB28181-compatible device record download start.

    Creates a ``DeviceRecordDownloadStart`` payload and forwards to the actual
    download endpoint, returning a ``{code, data: {stream, downloadSpeed}}`` envelope.
    """
    payload = DeviceRecordDownloadStart(
        device_id=device_id,
        channel_id=channel_id,
        start_time=startTime,
        end_time=endTime,
        download_speed=float(downloadSpeed),
    )

    result = await device_record_ep.start_device_record_download(
        payload=payload,
        db=db,
        current_user=current_user,
    )

    stream = ""
    if isinstance(result, dict):
        stream = str(result.get("stream", "") or "")

    return {
        "code": 0,
        "data": {
            "stream": stream,
            "downloadSpeed": downloadSpeed,
        },
    }


async def progress_download_compat(
    *,
    device_id: str,
    channel_id: str,
    stream: str,
    db: AsyncSession,
    current_user: Any,
) -> dict[str, Any]:
    """GB28181-compatible download progress query.

    Looks up the task by stream, then forwards to the actual progress endpoint,
    returning a ``{code, data: {progress, records}}`` envelope.
    """
    task = await _find_download_task_by_stream(db, stream=stream)
    task_id = str(getattr(task, "id", "") or "")

    result = await device_record_ep.get_device_record_download_progress(
        task_id=task_id,
        auto_stop=True,
        db=db,
        current_user=current_user,
    )

    if not isinstance(result, dict):
        result = {}

    return {
        "code": 0,
        "data": {
            "progress": int(result.get("percent", 0) or 0),
            "records": result.get("records", []),
        },
    }


async def stop_download_compat(
    *,
    device_id: str,
    channel_id: str,
    stream: str,
    db: AsyncSession,
    current_user: Any,
) -> dict[str, Any]:
    """GB28181-compatible download stop.

    Looks up the task by stream, then forwards to the actual stop endpoint,
    returning a ``{code, data: {status}}`` envelope.
    """
    task = await _find_download_task_by_stream(db, stream=stream)
    task_id = str(getattr(task, "id", "") or "")

    result = await device_record_ep.stop_device_record_download(
        task_id=task_id,
        db=db,
        current_user=current_user,
    )

    if not isinstance(result, dict):
        result = {}

    return {
        "code": 0,
        "data": {
            "status": str(result.get("status", "") or ""),
        },
    }
