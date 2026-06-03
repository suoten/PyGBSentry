from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.v1.endpoints import device_record as device_record_ep
from app.db.session import get_db
from app.models.asset import Asset
from app.models.device_record_download_task import DeviceRecordDownloadTask
from app.models.organization import Organization
from app.models.resource import Resource
from app.models.user import User

router = APIRouter()


def _parse_record_time(value: str, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")  # i18n
    normalized = text.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(normalized)
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field_name} format error, expected yyyy-MM-dd HH:mm:ss or ISO8601")  # i18n
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_record_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _find_download_task_by_stream(
    db: AsyncSession,
    *,
    device_id: str,
    channel_id: str,
    stream: str,
    current_user: User,
) -> DeviceRecordDownloadTask | None:
    stmt = (
        select(DeviceRecordDownloadTask)
        .join(Asset, Asset.id == DeviceRecordDownloadTask.asset_id)
        .join(Resource, Resource.id == DeviceRecordDownloadTask.resource_id)
        .where(
            Asset.gb_id == device_id,
            Resource.gb_id == channel_id,
            DeviceRecordDownloadTask.stream == stream,
        )
        .order_by(DeviceRecordDownloadTask.created_at.desc())
    )
    if not current_user.is_superuser:
        stmt = stmt.where(DeviceRecordDownloadTask.tenant_id == (current_user.tenant_id or "default"))
    return (await db.execute(stmt)).scalars().first()


async def _friendly_asset_channel_not_found_detail(
    db: AsyncSession,
    *,
    device_id: str,
    channel_id: str,
    current_user: User,
) -> dict:
    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset = (await db.execute(asset_stmt)).scalars().first()

    if not asset:
        return {
            "message": "Device not found. Please verify the device ID or check if the device has been deleted.",  # i18n
            "suggestion": "请在“设备管理”中搜索该设备后重试。",
            "reason_code": "asset_not_found",
            "retryable": False,
            "diagnostics": {
                "device_id": device_id,
                "channel_id": channel_id,
            },
        }

    if asset.status == 0:
        return {
            "message": f"Device {asset.name or asset.gb_id} is offline, cannot query recordings.",  # i18n
            "suggestion": "请检查设备网络连接及注册状态后重试。",
            "reason_code": "device_offline",
            "retryable": True,
            "diagnostics": {
                "device_id": device_id,
                "channel_id": channel_id,
                "asset_name": str(getattr(asset, "name", "") or ""),
            },
        }

    org_name = ""
    if getattr(asset, "organization_id", None):
        try:
            org_row = (await db.execute(select(Organization).where(Organization.id == asset.organization_id))).scalars().first()
            if org_row and getattr(org_row, "name", None):
                org_name = str(org_row.name)
        except Exception:
            org_name = ""

    channel_stmt = select(Resource).where(Resource.gb_id == channel_id, Resource.asset_id == asset.id)
    channel = (await db.execute(channel_stmt)).scalars().first()
    if not channel:
        return {
            "message": "Device exists but the channel does not belong to it. Device or channel not found.",  # i18n
            "suggestion": "请在该设备下重新选择通道后重试。",
            "reason_code": "channel_not_found_under_device",
            "retryable": False,
            "diagnostics": {
                "device_id": device_id,
                "channel_id": channel_id,
                "asset_gb_id": str(getattr(asset, "gb_id", "") or ""),
                "asset_name": str(getattr(asset, "name", "") or ""),
                "organization": org_name,
            },
        }
    return {
        "message": "Device or channel status has changed, please refresh and retry.",  # i18n
        "suggestion": "请刷新设备与通道列表。",
        "reason_code": "asset_channel_changed",
        "retryable": True,
        "diagnostics": {
            "device_id": device_id,
            "channel_id": channel_id,
        },
    }


@router.get("/query/{device_id}/{channel_id}")
async def query_record_compat(
    device_id: str,
    channel_id: str,
    startTime: str = Query(...),
    endTime: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    start_dt = _parse_record_time(startTime, "startTime")
    end_dt = _parse_record_time(endTime, "endTime")
    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="startTime cannot be greater than endTime")  # i18n

    try:
        records = await device_record_ep.query_device_records(
            device_id=device_id,
            channel_id=channel_id,
            start_time=start_dt,
            end_time=end_dt,
            db=db,
            current_user=current_user,
            timeout_seconds=20,
        )
    except HTTPException as exc:
        if int(exc.status_code) == 404:
            detail = await _friendly_asset_channel_not_found_detail(
                db,
                device_id=device_id,
                channel_id=channel_id,
                current_user=current_user,
            )
            raise HTTPException(status_code=404, detail=detail)
        raise
    record_list = [
        {
            "name": f"record_{idx + 1}",
            "deviceId": device_id,
            "channelId": channel_id,
            "startTime": _fmt_record_time(item.get("start_time")),
            "endTime": _fmt_record_time(item.get("end_time")),
            "secrecy": "0",
            "type": str(item.get("type") or "all"),
        }
        for idx, item in enumerate(records or [])
    ]
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "deviceId": device_id,
            "channelId": channel_id,
            "sumNum": len(record_list),
            "recordList": record_list,
        },
    }


@router.get("/download/start/{device_id}/{channel_id}")
async def start_download_compat(
    device_id: str,
    channel_id: str,
    startTime: str = Query(...),
    endTime: str = Query(...),
    downloadSpeed: int = Query(4, ge=1, le=16),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    start_dt = _parse_record_time(startTime, "startTime")
    end_dt = _parse_record_time(endTime, "endTime")
    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="startTime cannot be greater than endTime")  # i18n
    effective_speed = int(downloadSpeed)

    payload = device_record_ep.DeviceRecordDownloadStart(
        device_id=device_id,
        channel_id=channel_id,
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        download_speed=float(effective_speed),
    )
    try:
        result = await device_record_ep.start_device_record_download(payload=payload, db=db, current_user=current_user)
    except HTTPException as exc:
        if int(exc.status_code) == 404:
            detail = await _friendly_asset_channel_not_found_detail(
                db,
                device_id=device_id,
                channel_id=channel_id,
                current_user=current_user,
            )
            raise HTTPException(status_code=404, detail=detail)
        raise
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "taskId": result.get("task_id"),
            "status": result.get("status"),
            "app": result.get("app"),
            "stream": result.get("stream"),
            "downloadSpeed": int(effective_speed),
        },
    }


@router.get("/download/stop/{device_id}/{channel_id}/{stream}")
async def stop_download_compat(
    device_id: str,
    channel_id: str,
    stream: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    task = await _find_download_task_by_stream(
        db,
        device_id=device_id,
        channel_id=channel_id,
        stream=stream,
        current_user=current_user,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Download task not found")  # i18n
    result = await device_record_ep.stop_device_record_download(
        task_id=str(task.id),
        db=db,
        current_user=current_user,
    )
    return {"code": 0, "msg": "success", "data": result}


@router.get("/download/progress/{device_id}/{channel_id}/{stream}")
async def progress_download_compat(
    device_id: str,
    channel_id: str,
    stream: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    task = await _find_download_task_by_stream(
        db,
        device_id=device_id,
        channel_id=channel_id,
        stream=stream,
        current_user=current_user,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Download task not found")  # i18n
    progress = await device_record_ep.get_device_record_download_progress(
        task_id=str(task.id),
        auto_stop=True,
        db=db,
        current_user=current_user,
    )
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "taskId": progress.get("task_id"),
            "status": progress.get("status"),
            "app": progress.get("app"),
            "stream": progress.get("stream"),
            "progress": progress.get("percent"),
            "records": progress.get("records", []),
            "recordedSeconds": progress.get("recorded_seconds"),
            "totalSeconds": progress.get("total_seconds"),
            "lastError": progress.get("last_error", ""),
        },
    }
