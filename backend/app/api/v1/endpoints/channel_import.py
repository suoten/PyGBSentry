from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.api import deps
from app.models.user import User
from app.services.auth_audit import safe_auth_audit
import csv
import io
from typing import List, Dict
from openpyxl import load_workbook
import xlrd


router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


def _parse_rows_from_bytes(filename: str, data: bytes) -> List[Dict[str, str]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    if name.endswith(".xlsx"):
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            headers = [str(v).strip() if v is not None else "" for v in next(rows_iter)]
        except StopIteration:
            return []
        result: List[Dict[str, str]] = []
        for row in rows_iter:
            row_dict: Dict[str, str] = {}
            for idx, header in enumerate(headers):
                if not header:
                    continue
                value = row[idx] if idx < len(row) else None
                row_dict[header] = "" if value is None else str(value)
            if any(v.strip() for v in row_dict.values()):
                result.append(row_dict)
        return result

    if name.endswith(".xls"):
        book = xlrd.open_workbook(file_contents=data)
        sheet = book.sheet_by_index(0)
        if sheet.nrows == 0:
            return []
        headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
        result: List[Dict[str, str]] = []
        for r in range(1, sheet.nrows):
            row_dict: Dict[str, str] = {}
            empty = True
            for c, header in enumerate(headers):
                if not header:
                    continue
                value = sheet.cell_value(r, c)
                text = "" if value is None else str(value)
                if text.strip():
                    empty = False
                row_dict[header] = text
            if not empty:
                result.append(row_dict)
        return result

    raise HTTPException(status_code=400, detail="Only csv, xls, xlsx files are supported")


@router.post("/import")
async def import_channels(
    file: UploadFile = File(...),
    device_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    Import channels from CSV/XLS/XLSX.

    Expected header: gb_id,name,status,node_type,civil_code,parent_gb_id,device_gb_id
    - device_gb_id can be omitted if query parameter `device_id` is provided.
    """
    raw = await file.read()
    if not raw:
        await safe_auth_audit(
            db,
            module="channel_import",
            action="import_channels",
            source="channel_import",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="empty_file",
        )
        raise HTTPException(status_code=400, detail="File is empty")

    try:
        rows = _parse_rows_from_bytes(file.filename or "", raw)
    except HTTPException:
        await safe_auth_audit(
            db,
            module="channel_import",
            action="import_channels",
            source="channel_import",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="unsupported_file_type",
            extra_summary=(file.filename or "").replace(";", ".")[:120],
        )
        raise
    if not rows:
        await safe_auth_audit(
            db,
            module="channel_import",
            action="import_channels",
            source="channel_import",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="no_rows",
        )
        raise HTTPException(status_code=400, detail="No valid data rows in file")

    asset_stmt = select(Asset)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    asset_result = await db.execute(asset_stmt)
    assets = {asset.gb_id: asset for asset in asset_result.scalars().all()}

    created = 0
    updated = 0
    for row in rows:
        gb_id = (row.get("gb_id") or "").strip()
        if not gb_id:
            continue
        name = (row.get("name") or "").strip() or gb_id
        status_raw = (row.get("status") or "").strip()
        try:
            status = 1 if int(float(status_raw)) == 1 else 0
        except ValueError:
            status = 1
        node_type_raw = (row.get("node_type") or "channel").strip().lower()
        node_type = "directory" if node_type_raw == "directory" else "channel"
        civil_code = (row.get("civil_code") or "").strip() or None
        parent_gb_id = (row.get("parent_gb_id") or "").strip() or None
        device_gb_id = (row.get("device_gb_id") or "").strip() or (device_id or "").strip()

        if not device_gb_id:
            continue
        asset = assets.get(device_gb_id)
        if not asset:
            continue

        resource_stmt = select(Resource).where(
            Resource.asset_id == asset.id,
            Resource.gb_id == gb_id,
        )
        result = await db.execute(resource_stmt)
        resource = result.scalars().first()
        if resource:
            resource.name = name
            resource.status = status
            resource.node_type = node_type
            resource.civil_code = civil_code
            resource.parent_gb_id = parent_gb_id
            updated += 1
        else:
            resource = Resource(
                asset_id=asset.id,
                gb_id=gb_id,
                name=name,
                status=status,
                node_type=node_type,
                civil_code=civil_code,
                parent_gb_id=parent_gb_id,
            )
            db.add(resource)
            created += 1

    await db.commit()
    fn = (file.filename or "").replace(";", ".").strip()[:120]
    await safe_auth_audit(
        db,
        module="channel_import",
        action="import_channels",
        source="channel_import",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"created={created}; updated={updated}; row_count={len(rows)}; file={fn}",
    )
    return {"created": created, "updated": updated, "total": len(rows)}

