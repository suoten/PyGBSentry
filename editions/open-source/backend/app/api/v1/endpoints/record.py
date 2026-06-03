from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.db.session import get_db
from app.models.record import Record
from app.models.resource import Resource
from app.models.asset import Asset
from app.models.operation_audit import OperationAudit
from app.models.user import User
from app.api import deps
from app.api.deps import get_or_404
from datetime import datetime, timedelta
from fastapi.responses import StreamingResponse, RedirectResponse
from app.core.http_client import get_http_client
import httpx
import urllib.parse
from pathlib import Path
from datetime import timezone
from app.core.media_nodes_db import get_db_media_node_by_id
from app.services.auth_audit import safe_auth_audit
from app.core.config import settings
import time
import hmac
import hashlib
from typing import Any

router = APIRouter()

def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


async def _record_query_audit(
    db: AsyncSession,
    user: User,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    await safe_auth_audit(
        db,
        module="record",
        action=action,
        source="record_query",
        operator=user.username or "unknown",
        result=result,
        tenant_id=_audit_tid(user),
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


async def _record_public_download_audit(
    db: AsyncSession,
    *,
    tenant_id: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    await safe_auth_audit(
        db,
        module="record",
        action="download_record_public",
        source="signed_url",
        operator="signed_url",
        result=result,
        tenant_id=(tenant_id or "default").strip() or "default",
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


def _parse_summary_kv(summary: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for seg in str(summary or "").split(";"):
        text = str(seg or "").strip()
        if not text or "=" not in text:
            continue
        k, v = text.split("=", 1)
        key = str(k or "").strip()
        if not key:
            continue
        out[key] = str(v or "").strip()
    return out


async def _verify_url_or_path(url: str, zlm_file_path: str | None) -> tuple[bool, int | None, str]:
    value = (url or "").strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"}:
        try:
            resp = await (await get_http_client()).head(value, timeout=5, follow_redirects=True)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
            code = int(resp.status_code)
            ok = 200 <= code < 400
            return ok, code, "" if ok else f"http={code}"
        except Exception as e:
            return False, None, str(e)[:200]
    p = Path(value)
    if (not p.is_absolute()) and zlm_file_path:
        p = Path(str(zlm_file_path))
    ok = p.exists() and p.is_file()
    return ok, None, "" if ok else "file_missing"


def _join_public_base(public_host: str, public_http_port: int) -> str:
    host = (public_host or "").strip()
    port = int(public_http_port or 0)
    if not host:
        return ""
    if port in {0, 80}:
        return f"http://{host}"
    return f"http://{host}:{port}"


def _derive_record_path(file_path: str, zlm_file_path: str | None) -> str:
    url = (file_path or "").strip()
    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in {"http", "https"}:
            path = parsed.path or ""
            q = parsed.query or ""
            return f"{path}?{q}" if q else path
        if "/record/" in url:
            idx = url.find("/record/")
            return url[idx:]
    fp = (str(zlm_file_path or "")).strip()
    if fp and "/record/" in fp:
        idx = fp.find("/record/")
        return fp[idx:]
    return ""


async def _build_repaired_url(db: AsyncSession, record: Record) -> str | None:
    node_id = str(getattr(record, "media_node_id", "") or "").strip()
    if not node_id:
        return None
    node = await get_db_media_node_by_id(db, node_id)
    if not node:
        return None
    base = _join_public_base(node.public_host, node.public_http_port)
    if not base:
        return None
    path = _derive_record_path(str(record.file_path or ""), getattr(record, "zlm_file_path", None))
    if not path:
        return None
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _record_download_sign_secret() -> str:
    secret = str(getattr(settings, "RECORD_DOWNLOAD_SIGN_SECRET", "") or "").strip()
    if secret:
        return secret
    return str(getattr(settings, "SECRET_KEY", "") or "").strip()


def _record_download_signature(record_id: str, tenant_id: str, exp: int, inline: bool) -> str:
    payload = f"{record_id}|{tenant_id}|{int(exp)}|{1 if inline else 0}"
    return hmac.new(
        _record_download_sign_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_record_download_signature(record_id: str, tenant_id: str, exp: int, inline: bool, sig: str) -> bool:
    if int(exp or 0) <= int(time.time()):
        return False
    expected = _record_download_signature(record_id=record_id, tenant_id=tenant_id, exp=int(exp), inline=inline)
    return hmac.compare_digest(expected, str(sig or "").strip().lower())


async def _stream_record_download(
    db: AsyncSession,
    row: Record,
    res: Resource,
    inline: bool = False,
):
    url = str(row.file_path or "").strip()
    filename = "record.mp4"
    if row.start_time:
        filename = f"{res.gb_id}_{row.start_time.strftime('%Y%m%d%H%M%S')}.mp4"
    disposition = "inline" if inline else "attachment"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in {"http", "https"}:
        target_url = url
        try:
            upstream = await (await get_http_client()).get(target_url, timeout=5, follow_redirects=True)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
        except Exception as e:
            repaired = await _build_repaired_url(db, row)
            if repaired and repaired != target_url:
                try:
                    upstream = await (await get_http_client()).get(repaired, timeout=5, follow_redirects=True)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
                    target_url = repaired
                except Exception:
                    raise HTTPException(status_code=502, detail=f"Recording download link unreachable: {str(e)[:200]}")
            else:
                raise HTTPException(status_code=502, detail=f"Recording download link unreachable: {str(e)[:200]}")

        status_code = int(getattr(upstream, "status_code", 0) or 0)
        content_type = str(upstream.headers.get("Content-Type", "") or "").lower()
        up_len_raw = str(upstream.headers.get("Content-Length", "") or "").strip()
        up_len_num = int(up_len_raw) if up_len_raw.isdigit() else 0
        html_like_small = ("text/html" in content_type) and (0 < up_len_num <= 64 * 1024)
        if not (status_code < 400 and not html_like_small):
            upstream.close()
            repaired = await _build_repaired_url(db, row)
            if repaired and repaired != target_url:
                try:
                    retry = await (await get_http_client()).get(repaired, timeout=5, follow_redirects=True)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
                except Exception as e:
                    raise HTTPException(status_code=502, detail=f"Recording download link unreachable: {str(e)[:200]}")
                retry_status = int(getattr(retry, "status_code", 0) or 0)
                retry_type = str(retry.headers.get("Content-Type", "") or "").lower()
                retry_len_raw = str(retry.headers.get("Content-Length", "") or "").strip()
                retry_len_num = int(retry_len_raw) if retry_len_raw.isdigit() else 0
                retry_html_like_small = ("text/html" in retry_type) and (0 < retry_len_num <= 64 * 1024)
                if retry_status < 400 and not retry_html_like_small:
                    upstream = retry
                    content_type = retry_type
                else:
                    retry.close()
                    err_msg = f"录像下载失败，上游返回异常: {retry_status or status_code}"
                    if retry_status == 200 or status_code == 200:
                        err_msg += " (返回了网页而非视频，请检查 Nginx 是否正确代理了 /record/ 目录到 ZLM)"
                    raise HTTPException(status_code=502, detail=err_msg)
            else:
                err_msg = f"录像下载失败，上游返回异常: {status_code}"
                if status_code == 200:
                    err_msg += " (返回了网页而非视频，请检查 Nginx 是否正确代理了 /record/ 目录到 ZLM)"
                raise HTTPException(status_code=502, detail=err_msg)

        def _iter_remote():
            try:
                for chunk in upstream.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        headers = {"Content-Disposition": f"{disposition}; filename={filename}", "Accept-Ranges": "bytes"}
        up_len = str(upstream.headers.get("Content-Length", "") or "").strip()
        if up_len.isdigit():
            headers["Content-Length"] = up_len
        media_type = content_type.split(";")[0].strip() if content_type else "application/octet-stream"
        if not media_type:
            media_type = "application/octet-stream"
        return StreamingResponse(_iter_remote(), media_type=media_type, headers=headers)

    local_path = Path(url)
    if not local_path.is_absolute() and getattr(row, "zlm_file_path", None):
        local_path = Path(str(row.zlm_file_path))
    if not local_path.exists() or not local_path.is_file():
        repaired = await _build_repaired_url(db, row)
        if repaired:
            return RedirectResponse(repaired)
        raise HTTPException(status_code=404, detail="Record file not found (may be on external media node or already cleaned)")  # FIXED: 硬编码中文→英文

    def _iter_file():
        try:
            with open(local_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 256)
                    if not chunk:
                        break
                    yield chunk
        except (FileNotFoundError, IOError) as e:
            raise HTTPException(status_code=404, detail="Record file not found") from e  # FIXED: 文件I/O异常保护

    headers = {"Content-Disposition": f"{disposition}; filename={filename}", "Accept-Ranges": "bytes"}
    if local_path.exists():
        headers["Content-Length"] = str(local_path.stat().st_size)
    return StreamingResponse(_iter_file(), media_type="video/mp4", headers=headers)

@router.get("/device-record")
async def query_device_record(
    device_id: str,
    channel_id: str,
    start_time: str,
    end_time: str,
    record_type: str = "all",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    发送 RecordInfo 信令到设备端，查询设备本地(NVR/IPC SD卡)的录像文件列表。
    由于是异步响应，这里先返回查询已下发的确认信息。前端需要通过 WebSocket 或轮询获取最终的查询结果。
    """
    stmt = select(Asset, Resource).join(Resource, Resource.asset_id == Asset.id).where(
        Asset.gb_id == device_id,
        Resource.gb_id == channel_id
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        await _record_query_audit(
            db,
            current_user,
            action="query_device_record",
            result="failed",
            status_code=404,
            detail="Device or channel not found or permission denied",  # FIXED: 硬编码中文→英文
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found or permission denied")  # FIXED: 硬编码中文→英文

    asset, resource = row

    if not asset.ip_addr:
        await _record_query_audit(
            db,
            current_user,
            action="query_device_record",
            result="failed",
            status_code=500,
            detail="Device network information missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    import app.sip.commander as sip_commander_module
    if not sip_commander_module.sip_commander:
        await _record_query_audit(
            db,
            current_user,
            action="query_device_record",
            result="failed",
            status_code=500,
            detail="SIP Commander not ready",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="SIP Commander not ready")

    from app.sip.server import sip_server
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _record_query_audit(
            db,
            current_user,
            action="query_device_record",
            result="failed",
            status_code=503,
            detail="Device signaling transport unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    # convert times to ISO8601 or required format if needed
    # GB28181 expects time format like "2023-10-01T00:00:00"
    if " " in start_time:
        start_time = start_time.replace(" ", "T")
    if " " in end_time:
        end_time = end_time.replace(" ", "T")

    try:
        sn = await sip_commander_module.sip_commander.send_record_info_query(
            device_id=asset.gb_id,
            channel_id=resource.gb_id,
            transport_info=((asset.ip_addr, asset.port), asset.transport or "UDP", transport),
            start_time=start_time,
            end_time=end_time,
            record_type=record_type,
            wait_response=True,
        )
    except HTTPException as he:
        await _record_query_audit(
            db,
            current_user,
            action="query_device_record",
            result="failed",
            status_code=he.status_code,
            detail=str(he.detail),
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise
    except Exception as e:
        await _record_query_audit(
            db,
            current_user,
            action="query_device_record",
            result="failed",
            status_code=500,
            detail="record_info_query_dispatch_error",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}; err={str(e)[:200]}",
        )
        raise HTTPException(status_code=500, detail="record_info_query dispatch failed")

    await _record_query_audit(
        db,
        current_user,
        action="query_device_record",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; sn={str(sn)[:16]}",
    )
    return {
        "status": "ok",
        "msg": "Recording query sent, waiting for device response",  # FIXED: hardcoded Chinese → English
        "sn": sn,
        "device_id": device_id,
        "channel_id": channel_id
    }


@router.get("/query")
async def query_records(
    device_id: str,
    channel_id: str,
    start_time: datetime,
    end_time: datetime,
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Query cloud records
    """
    limit = max(1, min(int(limit or 5000), 5000))
    skip = max(0, int(skip or 0))
    if start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    if (end_time - start_time) > timedelta(days=7):
        raise HTTPException(status_code=400, detail="Time range too large, please limit to 7 days")

    # Find Resource ID first
    stmt = select(Resource.id).join(Asset).where(
        Asset.gb_id == device_id,
        Resource.gb_id == channel_id
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    resource_id = result.scalars().first()

    if not resource_id:
        return []

    # FIXED-P2: M-09 添加Record级租户隔离
    stmt = select(Record).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Resource.asset_id).where(
        and_(
            Record.resource_id == resource_id,
            Record.start_time >= start_time,
            Record.end_time <= end_time,
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    ).order_by(Record.start_time.asc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    records = result.scalars().all()

    # 记录列表前端需要的是 JSON 可序列化对象（不要直接返回 SQLAlchemy model）
    return [
        {
            "id": str(r.id),
            "start_time": (r.start_time.isoformat() if r.start_time else None),
            "end_time": (r.end_time.isoformat() if r.end_time else None),
            "duration": r.duration,
            "file_size": r.file_size,
            "file_path": r.file_path,
            "record_app": getattr(r, "record_app", None),
            "media_node_id": getattr(r, "media_node_id", None),
            "url_ok": bool(getattr(r, "url_ok", True)),
            "url_checked_at": (getattr(r, "url_checked_at", None).isoformat() if getattr(r, "url_checked_at", None) else None),
            "url_status_code": getattr(r, "url_status_code", None),
            "url_error": getattr(r, "url_error", None) or "",
        }
        for r in records
    ]


@router.get("/search")
async def search_records(
    resource_id: str | None = None,
    device_id: str | None = None,
    channel_id: str | None = None,
    channel_ids: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = Query(0, ge=0),  # FIXED
    limit: int = Query(200, ge=1, le=10000),  # FIXED
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    limit = max(1, min(int(limit or 200), 1000))
    skip = max(0, int(skip or 0))
    tenant_id = current_user.tenant_id or "default"
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    target_channel_ids: list[str] = []
    if channel_id:
        cid = str(channel_id).strip()
        if cid:
            target_channel_ids.append(cid)
    if channel_ids:
        for item in str(channel_ids).split(","):
            cid = item.strip()
            if cid:
                target_channel_ids.append(cid)
    if target_channel_ids:
        target_channel_ids = list(dict.fromkeys(target_channel_ids))

    if not resource_id and target_channel_ids:
        stmt = select(Resource.id).join(Asset).where(Resource.gb_id.in_(target_channel_ids))
        if device_id:
            stmt = stmt.where(Asset.gb_id == device_id)
        if not current_user.is_superuser:
            stmt = stmt.where(Asset.tenant_id == tenant_id)
        result = await db.execute(stmt)
        resource_ids = result.scalars().all()
    else:
        resource_ids = []

    # 如果有传递 channel_id 或 channel_ids 参数，但查不到对应的 resource_ids，则直接返回空，避免全量查询
    has_channel_param = (channel_id is not None) or (channel_ids is not None)
    if has_channel_param and not resource_ids and not resource_id:
        return {"items": [], "total": 0, "page": skip // limit + 1, "page_size": limit}

    # Base query for all records with eager loading of relations
    stmt = select(Record, Resource, Asset).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Record.asset_id)

    # Filter by resource_id if provided (when a specific channel is clicked)
    if resource_id:
        stmt = stmt.where(Record.resource_id == resource_id)
    elif resource_ids:
        stmt = stmt.where(Record.resource_id.in_(resource_ids))
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    if start_time:
        stmt = stmt.where(Record.start_time >= start_time)
    if end_time:
        stmt = stmt.where(Record.end_time <= end_time)

    # 查总数
    count_stmt = select(func.count(Record.id)).join(Resource, Resource.id == Record.resource_id).join(Asset, Asset.id == Record.asset_id)
    if resource_id:
        count_stmt = count_stmt.where(Record.resource_id == resource_id)
    elif resource_ids:
        count_stmt = count_stmt.where(Record.resource_id.in_(resource_ids))
    if not current_user.is_superuser:
        count_stmt = count_stmt.where(Asset.tenant_id == tenant_id)
    if start_time:
        count_stmt = count_stmt.where(Record.start_time >= start_time)
    if end_time:
        count_stmt = count_stmt.where(Record.end_time <= end_time)

    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Record.start_time.asc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()
    items = [
        {
            "id": r.id,
            "device_id": a.gb_id,
            "device_name": a.name,
            "channel_id": res.gb_id,
            "channel_name": res.name,
            "resource_id": res.id,
            "start_time": (r.start_time.isoformat() if r.start_time else None),
            "end_time": (r.end_time.isoformat() if r.end_time else None),
            "duration": r.duration,
            "file_size": r.file_size,
            "file_path": r.file_path,
            "record_app": getattr(r, "record_app", None),
            "media_node_id": getattr(r, "media_node_id", None),
            "url_ok": bool(getattr(r, "url_ok", True)),
            "url_checked_at": (getattr(r, "url_checked_at", None).isoformat() if getattr(r, "url_checked_at", None) else None),
            "url_status_code": getattr(r, "url_status_code", None),
            "url_error": getattr(r, "url_error", None) or "",
        }
        for (r, res, a) in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit
    }


@router.get("/download/{record_id}")
async def download_record(
    record_id: str,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    row = get_or_404(await db.execute(select(Record).where(Record.id == record_id)), detail="Record not found")  # FIXED: ORM查询结果空值判断
    res = get_or_404(await db.execute(select(Resource).where(Resource.id == row.resource_id)), detail="Resource not found")  # FIXED: ORM查询结果空值判断
    asset = get_or_404(await db.execute(select(Asset).where(Asset.id == row.asset_id)), detail="Asset not found")  # FIXED: ORM查询结果空值判断
    if (not current_user.is_superuser) and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return await _stream_record_download(db=db, row=row, res=res, inline=inline)


@router.get("/download/sign/{record_id}")
async def sign_record_download_url(
    record_id: str,
    request: Request,
    inline: bool = False,
    ttl_seconds: int = Query(900, ge=60, le=86400),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if not bool(getattr(settings, "RECORD_DOWNLOAD_SIGN_ENABLED", True)):
        await _record_query_audit(
            db,
            current_user,
            action="sign_record_download_url",
            result="failed",
            status_code=403,
            detail="sign_disabled",
            extra_summary=f"record_id={record_id}",
        )
        raise HTTPException(status_code=403, detail="Download signature feature is disabled")
    row = (await db.execute(select(Record).where(Record.id == record_id))).scalars().first()
    if not row:
        await _record_query_audit(
            db,
            current_user,
            action="sign_record_download_url",
            result="failed",
            status_code=404,
            detail="record_not_found",
            extra_summary=f"record_id={record_id}",
        )
        raise HTTPException(status_code=404, detail="Recording not found")
    asset = (await db.execute(select(Asset).where(Asset.id == row.asset_id))).scalars().first()
    if not asset:
        await _record_query_audit(
            db,
            current_user,
            action="sign_record_download_url",
            result="failed",
            status_code=404,
            detail="asset_not_found",
            extra_summary=f"record_id={record_id}",
        )
        raise HTTPException(status_code=404, detail="Device not found")
    if (not current_user.is_superuser) and asset.tenant_id != (current_user.tenant_id or "default"):
        await _record_query_audit(
            db,
            current_user,
            action="sign_record_download_url",
            result="failed",
            status_code=403,
            detail="forbidden",
            extra_summary=f"record_id={record_id}; asset_tenant={asset.tenant_id}",
        )
        raise HTTPException(status_code=403, detail="Permission denied")
    exp = int(time.time()) + int(ttl_seconds or int(getattr(settings, "RECORD_DOWNLOAD_SIGN_TTL_SECONDS", 900) or 900))
    tenant_id = str(asset.tenant_id or "default").strip() or "default"
    sig = _record_download_signature(record_id=record_id, tenant_id=tenant_id, exp=exp, inline=inline)
    base = str(request.base_url).rstrip("/")
    path = f"{settings.API_V1_STR}/record/download/public/{record_id}"
    qs = urllib.parse.urlencode({"exp": exp, "sig": sig, "inline": "true" if inline else "false"})
    await _record_query_audit(
        db,
        current_user,
        action="sign_record_download_url",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"record_id={record_id}; expires_at={exp}; inline={inline}",
    )
    return {"url": f"{base}{path}?{qs}", "expires_at": exp, "record_id": record_id}


@router.get("/download/public/{record_id}")
async def download_record_public(
    request: Request,
    record_id: str,
    exp: int,
    sig: str,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
):
    if not bool(getattr(settings, "RECORD_DOWNLOAD_SIGN_ENABLED", True)):
        await _record_public_download_audit(
            db,
            tenant_id="default",
            result="failed",
            status_code=403,
            detail="sign_disabled",
            extra_summary=f"record_id={record_id}; client_ip={getattr(request.client, 'host', '')}",
        )
        raise HTTPException(status_code=403, detail="Download signature feature is disabled")
    row = (await db.execute(select(Record).where(Record.id == record_id))).scalars().first()
    if not row:
        await _record_public_download_audit(
            db,
            tenant_id="default",
            result="failed",
            status_code=404,
            detail="record_not_found",
            extra_summary=f"record_id={record_id}; client_ip={getattr(request.client, 'host', '')}",
        )
        raise HTTPException(status_code=404, detail="Recording not found")
    res = (await db.execute(select(Resource).where(Resource.id == row.resource_id))).scalars().first()
    if not res:
        await _record_public_download_audit(
            db,
            tenant_id="default",
            result="failed",
            status_code=404,
            detail="resource_not_found",
            extra_summary=f"record_id={record_id}; client_ip={getattr(request.client, 'host', '')}",
        )
        raise HTTPException(status_code=404, detail="Channel not found")
    asset = (await db.execute(select(Asset).where(Asset.id == row.asset_id))).scalars().first()
    if not asset:
        await _record_public_download_audit(
            db,
            tenant_id="default",
            result="failed",
            status_code=404,
            detail="asset_not_found",
            extra_summary=f"record_id={record_id}; client_ip={getattr(request.client, 'host', '')}",
        )
        raise HTTPException(status_code=404, detail="Device not found")
    tenant_id = str(asset.tenant_id or "default").strip() or "default"
    if not _verify_record_download_signature(record_id=record_id, tenant_id=tenant_id, exp=int(exp or 0), inline=inline, sig=sig):
        await _record_public_download_audit(
            db,
            tenant_id=tenant_id,
            result="failed",
            status_code=403,
            detail="invalid_signature",
            extra_summary=f"record_id={record_id}; exp={exp}; inline={inline}; client_ip={getattr(request.client, 'host', '')}",
        )
        raise HTTPException(status_code=403, detail="Download signature invalid or expired")
    await _record_public_download_audit(
        db,
        tenant_id=tenant_id,
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"record_id={record_id}; inline={inline}; client_ip={getattr(request.client, 'host', '')}",
    )
    return await _stream_record_download(db=db, row=row, res=res, inline=inline)


@router.get("/download/audit/summary")
async def get_record_public_download_audit_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
    record_id: str | None = Query(None),
    client_ip: str | None = Query(None),
    result: str | None = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_at = now - timedelta(hours=int(hours or 24))
    stmt = (
        select(OperationAudit)
        .where(
            OperationAudit.module == "record",
            OperationAudit.action == "download_record_public",
            OperationAudit.created_at >= start_at,
        )
        .order_by(OperationAudit.created_at.desc())
        .limit(int(limit or 100))
    )
    if result:
        stmt = stmt.where(OperationAudit.result == str(result).strip())
    rows = (await db.execute(stmt)).scalars().all()
    items: list[dict[str, Any]] = []
    agg = {"success": 0, "failed": 0}
    by_record: dict[str, int] = {}
    by_ip: dict[str, int] = {}
    filter_record = str(record_id or "").strip()
    filter_ip = str(client_ip or "").strip()
    for row in rows:
        parsed = _parse_summary_kv(getattr(row, "summary", "") or "")
        rid = str(parsed.get("record_id") or "").strip()
        ip = str(parsed.get("client_ip") or "").strip()
        if filter_record and rid != filter_record:
            continue
        if filter_ip and ip != filter_ip:
            continue
        rs = str(getattr(row, "result", "") or "").strip().lower()
        if rs == "success":
            agg["success"] += 1
        else:
            agg["failed"] += 1
        if rid:
            by_record[rid] = int(by_record.get(rid, 0) or 0) + 1
        if ip:
            by_ip[ip] = int(by_ip.get(ip, 0) or 0) + 1
        items.append(
            {
                "id": str(getattr(row, "id", "") or ""),
                "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
                "result": rs,
                "detail": str(parsed.get("detail") or ""),
                "record_id": rid,
                "client_ip": ip,
                "tenant_id": str(parsed.get("tenant_id") or ""),
                "status_code": str(parsed.get("status_code") or ""),
                "inline": str(parsed.get("inline") or ""),
                "exp": str(parsed.get("exp") or ""),
            }
        )
    top_records = sorted(by_record.items(), key=lambda x: x[1], reverse=True)[:20]
    top_ips = sorted(by_ip.items(), key=lambda x: x[1], reverse=True)[:20]
    return {
        "time_window_hours": int(hours or 24),
        "count": len(items),
        "success": int(agg["success"]),
        "failed": int(agg["failed"]),
        "top_records": [{"record_id": k, "count": v} for k, v in top_records],
        "top_client_ips": [{"client_ip": k, "count": v} for k, v in top_ips],
        "items": items,
    }


@router.get("/play-url/{record_id}")
async def get_record_play_url(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    row = get_or_404(await db.execute(select(Record).where(Record.id == record_id)), detail="Record not found")  # FIXED: ORM查询结果空值判断
    asset = get_or_404(await db.execute(select(Asset).where(Asset.id == row.asset_id)), detail="Asset not found")  # FIXED: ORM查询结果空值判断
    if (not current_user.is_superuser) and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")

    url = str(row.file_path or "").strip()

    # 拦截 S3/MinIO 存储，动态生成预签名 URL
    if url.startswith("s3://"):
        try:
            import boto3
            from botocore.config import Config
            s3_bucket = getattr(settings, "S3_BUCKET", "")
            s3_endpoint = getattr(settings, "S3_ENDPOINT", "")
            s3_access_key = getattr(settings, "S3_ACCESS_KEY", "")
            s3_secret_key = getattr(settings, "S3_SECRET_KEY", "")

            if not all([s3_bucket, s3_endpoint, s3_access_key, s3_secret_key]):
                raise HTTPException(status_code=500, detail="Server S3 config missing")

            # 解析 s3://bucket/key
            path_parts = url.replace("s3://", "").split("/", 1)
            if len(path_parts) != 2:
                raise HTTPException(status_code=500, detail="Cloud recording path format error")

            bucket, key = path_parts

            s3_client = boto3.client(
                's3',
                endpoint_url=s3_endpoint,
                aws_access_key_id=s3_access_key,
                aws_secret_access_key=s3_secret_key,
                config=Config(signature_version='s3v4')
            )

            # 生成预签名 URL (默认过期时间 1 小时)
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=3600
            )
            return {"url": presigned_url}
        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to generate S3 presigned URL: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate cloud recording playback URL")  # FIXED: 硬编码中文→英文

    if url.startswith("http://") or url.startswith("https://"):
        return {"url": url}
    repaired = await _build_repaired_url(db, row)
    if repaired:
        return {"url": repaired}
    raise HTTPException(status_code=400, detail="Cannot parse playable URL")  # FIXED: 硬编码中文→英文



@router.post("/verify/{record_id}")
async def verify_record_url(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    row = get_or_404(await db.execute(select(Record).where(Record.id == record_id)), detail="Record not found")  # FIXED: ORM查询结果空值判断
    asset = get_or_404(await db.execute(select(Asset).where(Asset.id == row.asset_id)), detail="Asset not found")  # FIXED: ORM查询结果空值判断
    if (not current_user.is_superuser) and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")

    url = str(row.file_path or "").strip()
    ok, status_code, error = await _verify_url_or_path(url, getattr(row, "zlm_file_path", None))  # FIXED: 同步requests→异步httpx，避免阻塞事件循环

    row.url_checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.url_ok = bool(ok)
    row.url_status_code = status_code
    row.url_error = error
    try:
        await db.commit()
    except Exception:
        await db.rollback()
    return {"ok": bool(ok), "status_code": status_code, "error": error, "checked_at": row.url_checked_at.isoformat() if row.url_checked_at else None}


class VerifyBatchPayload(BaseModel):
    ids: list[str]


@router.post("/verify-batch")
async def verify_records_batch(
    payload: VerifyBatchPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    ids = [str(x) for x in (payload.ids or []) if str(x)]
    ids = ids[:200]
    if not ids:
        raise HTTPException(status_code=400, detail="ids cannot be empty")  # FIXED: 硬编码中文→英文
    tenant_id = current_user.tenant_id or "default"
    rows = (await db.execute(select(Record).where(Record.id.in_(ids)))).scalars().all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ok_count = 0
    fail_count = 0
    updated = 0
    for r in rows:
        asset = (await db.execute(select(Asset).where(Asset.id == r.asset_id))).scalars().first()
        if not asset:
            continue
        if (not current_user.is_superuser) and asset.tenant_id != tenant_id:
            continue
        url = str(r.file_path or "").strip()
        ok, status_code, error = await _verify_url_or_path(url, getattr(r, "zlm_file_path", None))  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
        r.url_checked_at = now
        r.url_ok = bool(ok)
        r.url_status_code = status_code
        r.url_error = error
        updated += 1
        if ok:
            ok_count += 1
        else:
            fail_count += 1
    try:
        await db.commit()
    except Exception:
        await db.rollback()
    return {"total": len(rows), "updated": updated, "ok": ok_count, "failed": fail_count}


class DeleteBatchPayload(BaseModel):
    ids: list[str]


@router.post("/delete-batch")
async def delete_records_batch(
    payload: DeleteBatchPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    ids = [str(x) for x in (payload.ids or []) if str(x)]
    ids = ids[:500]
    if not ids:
        raise HTTPException(status_code=400, detail="ids cannot be empty")  # FIXED: hardcoded Chinese → English
    tenant_id = current_user.tenant_id or "default"
    rows = (await db.execute(select(Record).where(Record.id.in_(ids)))).scalars().all()
    deleted = 0
    for r in rows:
        asset = (await db.execute(select(Asset).where(Asset.id == r.asset_id))).scalars().first()
        if not asset:
            continue
        if (not current_user.is_superuser) and asset.tenant_id != tenant_id:
            continue
        await db.delete(r)
        deleted += 1
    await db.commit()
    return {"deleted": deleted}


class RepairUrlBatchPayload(BaseModel):
    ids: list[str]


@router.post("/repair-url/{record_id}")
async def repair_record_url(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    row = get_or_404(await db.execute(select(Record).where(Record.id == record_id)), detail="Record not found")  # FIXED: ORM查询结果空值判断
    asset = get_or_404(await db.execute(select(Asset).where(Asset.id == row.asset_id)), detail="Asset not found")  # FIXED: ORM查询结果空值判断
    if (not current_user.is_superuser) and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")
    new_url = await _build_repaired_url(db, row)
    if not new_url:
        raise HTTPException(status_code=400, detail="Cannot repair: missing media_node_id or cannot deduce path")  # FIXED: 硬编码中文→英文
    old = str(row.file_path or "")
    row.file_path = new_url
    row.url_checked_at = None
    row.url_ok = False
    row.url_status_code = None
    row.url_error = "repaired_pending_verify"
    await db.commit()
    return {"ok": True, "old": old, "new": new_url}


@router.post("/repair-url-batch")
async def repair_records_batch(
    payload: RepairUrlBatchPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    ids = [str(x) for x in (payload.ids or []) if str(x)]
    ids = ids[:200]
    if not ids:
        raise HTTPException(status_code=400, detail="ids cannot be empty")  # FIXED: 硬编码中文→英文
    tenant_id = current_user.tenant_id or "default"
    rows = (await db.execute(select(Record).where(Record.id.in_(ids)))).scalars().all()
    repaired = 0
    for r in rows:
        asset = (await db.execute(select(Asset).where(Asset.id == r.asset_id))).scalars().first()
        if not asset:
            continue
        if (not current_user.is_superuser) and asset.tenant_id != tenant_id:
            continue
        new_url = await _build_repaired_url(db, r)
        if not new_url:
            continue
        r.file_path = new_url
        r.url_checked_at = None
        r.url_ok = False
        r.url_status_code = None
        r.url_error = "repaired_pending_verify"
        repaired += 1
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Save failed")  # FIXED: hardcoded Chinese → English
    return {"repaired": repaired}


@router.delete("/{record_id}")
async def delete_record_index(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    row = get_or_404(await db.execute(select(Record).where(Record.id == record_id)), detail="Record not found")  # FIXED: ORM查询结果空值判断
    asset = get_or_404(await db.execute(select(Asset).where(Asset.id == row.asset_id)), detail="Asset not found")  # FIXED: ORM查询结果空值判断
    if (not current_user.is_superuser) and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")
    await db.delete(row)
    await db.commit()
    return {"ok": True}
