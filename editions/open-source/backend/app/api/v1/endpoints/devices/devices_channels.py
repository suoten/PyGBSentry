"""设备通道子资源端点（通道列表/通道详情/通道更新/批量操作/目录/树等）。"""

from fastapi import Query, APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, update
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User
from app.api import deps
from app.api.deps import get_or_404
from app.services.auth_audit import safe_auth_audit
from collections import defaultdict
from typing import Any
import time
from loguru import logger

from . _common import (
    _normalize_default_stream_type,
    _normalize_region_code,
    _build_region_chain,
    _resource_to_node,
    _get_effective_sip_id,
    _civil_code_from_sip_id,
    _tenant_id_for_user,
    _business_root_gb_id,
    _sort_tree_nodes,
    _ensure_business_root_resource,
    BatchChannelPlacementPayload,
    ChannelUpdatePayload,
    DirectoryCreatePayload,
    DirectoryDeletePayload,
    DirectoryRenamePayload,
    BatchUpdateCivilCodePayload,
)

router = APIRouter()


# FIXED: /tree 端点全量查询无缓存 → 添加内存缓存，TTL 30秒
_TREE_CACHE_TTL = 30
_tree_cache: dict[str, tuple[float, list]] = {}  # key: tenant_id, value: (timestamp, result)
# FIXED: /tree 端点结果无大小限制 → 添加最大节点数限制
_MAX_TREE_NODES = 50000
@router.get("/{device_id}/channels")
async def get_channels(
    device_id: str,
    online: bool | None = None,
    status: int | None = None,
    skip: int = Query(0, ge=0),  # FIXED
    limit: int = Query(50, ge=1, le=10000),  # FIXED
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    # 兼容：path 参数可能是 Asset.id 或 gb_id
    stmt_asset = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt_asset = stmt_asset.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    asset = (await db.execute(stmt_asset)).scalars().first()
    if not asset:
        stmt_asset2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt_asset2 = stmt_asset2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt_asset2)).scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    stmt = select(Resource).join(Asset).where(Asset.gb_id == asset.gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    if status is not None:
        stmt = stmt.where(Resource.status == (1 if int(status) == 1 else 0))
    if online is not None:
        stmt = stmt.where(Resource.status == (1 if bool(online) else 0))
    limit = max(1, min(int(limit or 50), 10000))
    skip = max(0, int(skip or 0))

    stmt = stmt.order_by(Resource.node_type.asc(), Resource.gb_id.asc(), Resource.id.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    resources = result.scalars().all()

    items: list[dict[str, Any]] = []
    for r in resources:
        caps = r.capabilities or {}
        default_stream_type = _normalize_default_stream_type(
            (caps.get("default_stream_type") if isinstance(caps, dict) else "main"),
            strict=False,
        )
        items.append(
            {
                "id": r.id,
                "gb_id": r.gb_id,
                "name": r.name,
                "status": r.status,
                "online": r.status == 1,
                "node_type": r.node_type or "channel",
                "civil_code": r.civil_code,
                "parent_gb_id": r.parent_gb_id,
                "region_parent_gb_id": getattr(r, "region_parent_gb_id", None),
                "resource_type": getattr(r, "type", None),
                "has_audio": bool(r.has_audio),
                "default_stream_type": default_stream_type,
                "address": r.address,
                "parental": r.parental,
                "safety_way": r.safety_way,
                "register_way": r.register_way,
                "secrecy": r.secrecy,
                "ip_address": r.ip_address,
                "port": r.port,
                "password": r.password,
                "ptz_type": r.ptz_type,
                "position_type": r.position_type,
                "room_type": r.room_type,
                "use_type": r.use_type,
                "supply_light_type": r.supply_light_type,
                "direction_type": r.direction_type,
                "resolution": r.resolution,
                "business_group_id": r.business_group_id,
            }
        )
    return items


@router.get("/{device_id}/channels/paged")
async def get_channels_paged(
    device_id: str,
    online: bool | None = None,
    status: int | None = None,
    skip: int = Query(0, ge=0),  # FIXED
    limit: int = Query(50, ge=1, le=10000),  # FIXED
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    分页通道列表（带 total），用于通道很多时的列表控件。
    """
    # 兼容：path 参数可能是 Asset.id 或 gb_id
    stmt_asset = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt_asset = stmt_asset.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    asset = (await db.execute(stmt_asset)).scalars().first()

    if not asset:
        stmt_asset2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt_asset2 = stmt_asset2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt_asset2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    stmt = select(Resource).join(Asset).where(Asset.gb_id == asset.gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    if status is not None:
        stmt = stmt.where(Resource.status == (1 if int(status) == 1 else 0))
    elif online is not None:
        stmt = stmt.where(Resource.status == (1 if bool(online) else 0))

    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))

    count_stmt = select(func.count()).select_from(Resource).join(Asset).where(Asset.gb_id == asset.gb_id)
    if not current_user.is_superuser:
        count_stmt = count_stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    if status is not None:
        count_stmt = count_stmt.where(Resource.status == (1 if int(status) == 1 else 0))
    elif online is not None:
        count_stmt = count_stmt.where(Resource.status == (1 if bool(online) else 0))

    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = stmt.order_by(Resource.node_type.asc(), Resource.gb_id.asc(), Resource.id.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    resources = result.scalars().all()

    items: list[dict[str, Any]] = []
    for r in resources:
        caps = r.capabilities or {}
        default_stream_type = _normalize_default_stream_type(
            (caps.get("default_stream_type") if isinstance(caps, dict) else "main"),
            strict=False,
        )
        items.append(
            {
                "id": r.id,
                "gb_id": r.gb_id,
                "name": r.name,
                "status": r.status,
                "online": r.status == 1,
                "node_type": r.node_type or "channel",
                "civil_code": r.civil_code,
                "parent_gb_id": r.parent_gb_id,
                "region_parent_gb_id": getattr(r, "region_parent_gb_id", None),
                "resource_type": getattr(r, "type", None),
                "has_audio": bool(r.has_audio),
                "default_stream_type": default_stream_type,
                "address": r.address,
                "parental": r.parental,
                "safety_way": r.safety_way,
                "register_way": r.register_way,
                "secrecy": r.secrecy,
                "ip_address": r.ip_address,
                "port": r.port,
                "password": r.password,
                "ptz_type": r.ptz_type,
                "position_type": r.position_type,
                "room_type": r.room_type,
                "use_type": r.use_type,
                "supply_light_type": r.supply_light_type,
                "direction_type": r.direction_type,
                "resolution": r.resolution,
                "business_group_id": r.business_group_id,
                "longitude": r.longitude,
                "latitude": r.latitude,
                "manufacturer": r.manufacturer,
                "model": r.model,
                "owner": r.owner,
            }
        )

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/channels/flat")
async def get_channels_flat(
    keyword: str = "",
    node_type: str = "",
    resource_type: int | None = None,
    camera_only: bool = False,
    status: int | None = None,
    device_id: str = "",
    parent_gb_id: str = "",
    not_parent_gb_id: str = "",
    added_status: str = "",
    civil_code_prefix: str = "",
    placement: str = "business",
    skip: int = Query(0, ge=0),  # FIXED
    limit: int = Query(50, ge=1, le=10000),  # FIXED
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))
    placement = (placement or "business").strip().lower()
    if placement not in ("business", "region"):
        placement = "business"

    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id)
    # 优化点：COUNT 语句如果不依赖 Asset 过滤，可以去掉 JOIN，提升百万级数据时的 count 性能
    count_stmt = select(func.count()).select_from(Resource)
    needs_asset_join_for_count = False

    conditions = []
    count_conditions = []

    if keyword:
        cond = or_(Resource.gb_id.ilike(f"%{keyword}%"), Resource.name.ilike(f"%{keyword}%"))
        conditions.append(cond)
        count_conditions.append(cond)
    if node_type:
        conditions.append(Resource.node_type == node_type)
        count_conditions.append(Resource.node_type == node_type)
    if resource_type is not None:
        conditions.append(Resource.type == int(resource_type))
        count_conditions.append(Resource.type == int(resource_type))
    if status is not None:
        conditions.append(Resource.status == status)
        count_conditions.append(Resource.status == status)
    if device_id:
        # 直接查出 asset_id，将 JOIN 转化为 IN 或 =，这对于 MySQL/PG 的索引命中率更高
        asset_stmt = select(Asset.id).where(Asset.gb_id == device_id)
        asset_id_val = (await db.execute(asset_stmt)).scalar()
        if asset_id_val:
            conditions.append(Resource.asset_id == asset_id_val)
            count_conditions.append(Resource.asset_id == asset_id_val)
        else:
            return {"total": 0, "items": [], "online_total": 0, "skip": skip, "limit": limit}
    if camera_only:
        nvr_like = or_(
            Asset.model.ilike("%nvr%"),
            Asset.name.ilike("%nvr%"),
            Asset.manufacturer.ilike("%nvr%"),
            Asset.model.ilike("%录像机%"),
            Asset.name.ilike("%录像机%"),
            Asset.manufacturer.ilike("%录像机%"),
            Asset.model.ilike("%录像%"),
            Asset.name.ilike("%录像%"),
            Asset.manufacturer.ilike("%录像%"),
        )
        conditions.append(~nvr_like)
        needs_asset_join_for_count = True
        count_conditions.append(~nvr_like)
    civil_code_prefix = "".join(ch for ch in (civil_code_prefix or "") if ch.isdigit())
    if civil_code_prefix:
        conditions.append(Resource.civil_code.like(f"{civil_code_prefix}%"))
        count_conditions.append(Resource.civil_code.like(f"{civil_code_prefix}%"))
    parent_gb_id = (parent_gb_id or "").strip()
    not_parent_gb_id = (not_parent_gb_id or "").strip()
    if placement == "region":
        if parent_gb_id:
            conditions.append(Resource.region_parent_gb_id == parent_gb_id)
            count_conditions.append(Resource.region_parent_gb_id == parent_gb_id)
        elif not_parent_gb_id:
            cond = or_(Resource.region_parent_gb_id.is_(None), Resource.region_parent_gb_id == "")
            conditions.append(cond)
            count_conditions.append(cond)
        else:
            added_status = (added_status or "").strip().lower()
            if added_status == "unadded":
                dir_stmt = select(Resource.gb_id).where(Resource.node_type == "directory")
                if not current_user.is_superuser:
                    dir_stmt = dir_stmt.where(Resource.tenant_id == current_user.tenant_id)
                directory_ids = {str(x).strip() for x in (await db.execute(dir_stmt)).scalars().all() if str(x).strip()}

                from sqlalchemy import text
                cond = or_(
                    Resource.region_parent_gb_id.is_(None),
                    Resource.region_parent_gb_id == "",
                    ~Resource.region_parent_gb_id.in_(directory_ids) if directory_ids else text("1=1")
                )
                conditions.append(cond)
                count_conditions.append(cond)
            elif added_status == "added":
                cond = and_(Resource.region_parent_gb_id.is_not(None), Resource.region_parent_gb_id != "")
                conditions.append(cond)
                count_conditions.append(cond)
    else:
        if parent_gb_id:
            conditions.append(Resource.parent_gb_id == parent_gb_id)
            count_conditions.append(Resource.parent_gb_id == parent_gb_id)
        elif not_parent_gb_id:
            cond = or_(Resource.parent_gb_id.is_(None), Resource.parent_gb_id == "")
            conditions.append(cond)
            count_conditions.append(cond)
        else:
            added_status = (added_status or "").strip().lower()
            if added_status == "unadded":
                # 修改未挂载过滤条件：同时满足 NULL 或 空字符串，或者是属于某个设备的 ID（未人为指定父节点时）
                # 为了简便起见，这里直接使用一个更好的判断：不是一个现存的目录节点
                dir_stmt = select(Resource.gb_id).where(Resource.node_type == "directory")
                if not current_user.is_superuser:
                    dir_stmt = dir_stmt.where(Resource.tenant_id == current_user.tenant_id)
                directory_ids = {str(x).strip() for x in (await db.execute(dir_stmt)).scalars().all() if str(x).strip()}

                from sqlalchemy import text
                cond = or_(
                    Resource.parent_gb_id.is_(None),
                    Resource.parent_gb_id == "",
                    ~Resource.parent_gb_id.in_(directory_ids) if directory_ids else text("1=1")
                )
                conditions.append(cond)
                count_conditions.append(cond)
            elif added_status == "added":
                cond = and_(Resource.parent_gb_id.is_not(None), Resource.parent_gb_id != "")
                conditions.append(cond)
                count_conditions.append(cond)
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        conditions.append(Resource.tenant_id == tenant_id)
        count_conditions.append(Resource.tenant_id == tenant_id)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    if needs_asset_join_for_count:
        count_stmt = count_stmt.join(Asset, Asset.id == Resource.asset_id)
    if count_conditions:
        count_stmt = count_stmt.where(and_(*count_conditions))

    # 优化点：当没有过滤条件时，或者在一些方言中直接执行全表 COUNT 很慢
    # 这里我们尝试异步执行，如果超过一定时间，或者在业务允许的情况下，其实不需要每次都精确计算总数
    # 但为了兼容前端的分页组件，我们仍保留 count，不过由于去掉了 JOIN 和简化了 WHERE，速度会快很多
    total = int((await db.execute(count_stmt)).scalar() or 0)
    online_count_stmt = select(func.count()).select_from(Resource).where(Resource.status == 1)
    if needs_asset_join_for_count:
        online_count_stmt = online_count_stmt.join(Asset, Asset.id == Resource.asset_id)
    if count_conditions:
        online_count_stmt = online_count_stmt.where(and_(*count_conditions))
    online_total = int((await db.execute(online_count_stmt)).scalar() or 0)

    # 优化点：避免三字段混合排序导致的 FileSort (Using temporary; Using filesort)
    # gb_id 是唯一且自带索引的，直接用 gb_id 排序即可保证稳定性且命中索引
    stmt = stmt.order_by(Resource.gb_id.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()
    items = [
        {
            "id": resource.id,
            "gb_id": resource.gb_id,
            "name": resource.name,
            "status": resource.status,
            "online": resource.status == 1,
            "node_type": resource.node_type or "channel",
            "civil_code": resource.civil_code,
            "parent_gb_id": resource.parent_gb_id,
            "region_parent_gb_id": getattr(resource, "region_parent_gb_id", None),
            "resource_type": getattr(resource, "type", None),
            "ptz_type": getattr(resource, "ptz_type", None),
            "asset_id": asset.id,
            "device_id": asset.gb_id,
            "device_name": asset.name,
            "device_model": getattr(asset, "model", None),
            "device_manufacturer": getattr(asset, "manufacturer", None),
            "longitude": getattr(resource, "longitude", None),
            "latitude": getattr(resource, "latitude", None),
            "has_audio": bool(getattr(resource, "has_audio", True)),
            "default_stream_type": _normalize_default_stream_type(
                (
                    (resource.capabilities or {}).get("default_stream_type")
                    if isinstance(resource.capabilities, dict)
                    else "main"
                ),
                strict=False,
            ),
        }
        for resource, asset in rows
    ]
    return {"items": items, "total": total, "online_total": online_total, "skip": skip, "limit": limit}


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    payload: ChannelUpdatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]))
):
    stmt = select(Resource).where(Resource.id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    channel = get_or_404(result, detail="Channel not found")  # FIXED: ORM查询结果空值判断
    update_data = payload.dict(exclude_unset=True) if hasattr(payload, "dict") else payload.model_dump(exclude_unset=True)

    if "name" in update_data and payload.name is not None:
        channel.name = payload.name.strip()
    if "status" in update_data and payload.status is not None:
        channel.status = 1 if int(payload.status) == 1 else 0
    if "node_type" in update_data and payload.node_type is not None:
        node_type = payload.node_type.strip().lower()
        channel.node_type = "directory" if node_type == "directory" else "channel"
    if "civil_code" in update_data:
        channel.civil_code = payload.civil_code.strip() if payload.civil_code else None

    tenant_id = current_user.tenant_id or "default"
    dir_stmt = select(Resource.gb_id).where(Resource.node_type == "directory")
    if not current_user.is_superuser:
        dir_stmt = dir_stmt.where(Resource.tenant_id == tenant_id)
    directory_ids = {str(x).strip() for x in (await db.execute(dir_stmt)).scalars().all() if str(x).strip()}

    if "parent_gb_id" in update_data:
        old_parent = (channel.parent_gb_id or "").strip() or None
        new_parent = (payload.parent_gb_id or "").strip() or None
        old_parent_valid = bool(old_parent and old_parent in directory_ids and not old_parent.startswith("region:"))
        if new_parent and old_parent_valid and new_parent != old_parent:
            raise HTTPException(status_code=400, detail="Channel already mounted to another business node, remove first")
        channel.parent_gb_id = new_parent
    if "region_parent_gb_id" in update_data:
        old_region_parent = (channel.region_parent_gb_id or "").strip() or None
        new_region_parent = (payload.region_parent_gb_id or "").strip() or None
        old_region_valid = bool(old_region_parent and old_region_parent in directory_ids and old_region_parent.startswith("region:"))
        if new_region_parent and old_region_valid and new_region_parent != old_region_parent:
            raise HTTPException(status_code=400, detail="Channel already mounted to another region node, remove first")
        channel.region_parent_gb_id = new_region_parent
    if "has_audio" in update_data and payload.has_audio is not None:
        channel.has_audio = bool(payload.has_audio)

    if "default_stream_type" in update_data and payload.default_stream_type is not None:
        v = _normalize_default_stream_type(payload.default_stream_type, strict=True)
        caps = channel.capabilities or {}
        if not isinstance(caps, dict):
            caps = {}
        caps["default_stream_type"] = v
        channel.capabilities = caps

    if "longitude" in update_data:
        channel.longitude = payload.longitude
    if "latitude" in update_data:
        channel.latitude = payload.latitude

    # GB28181 Extended
    if "address" in update_data:
        channel.address = payload.address
    if "parental" in update_data:
        channel.parental = payload.parental
    if "safety_way" in update_data:
        channel.safety_way = payload.safety_way
    if "register_way" in update_data:
        channel.register_way = payload.register_way
    if "secrecy" in update_data:
        channel.secrecy = payload.secrecy
    if "ip_address" in update_data:
        channel.ip_address = payload.ip_address
    if "port" in update_data:
        channel.port = payload.port
    if "password" in update_data:
        channel.password = payload.password
    if "ptz_type" in update_data:
        channel.ptz_type = payload.ptz_type
    if "position_type" in update_data:
        channel.position_type = payload.position_type
    if "room_type" in update_data:
        channel.room_type = payload.room_type
    if "use_type" in update_data:
        channel.use_type = payload.use_type
    if "supply_light_type" in update_data:
        channel.supply_light_type = payload.supply_light_type
    if "direction_type" in update_data:
        channel.direction_type = payload.direction_type
    if "resolution" in update_data:
        channel.resolution = payload.resolution
    if "business_group_id" in update_data:
        channel.business_group_id = payload.business_group_id

    await db.commit()
    return {"status": "ok"}


@router.post("/channels/{channel_id}/reset")
async def reset_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    stmt = select(Resource).where(Resource.id == channel_id, Resource.node_type == "channel")
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    result = await db.execute(stmt)
    channel = get_or_404(result, detail="Channel not found")  # FIXED: ORM查询结果空值判断
    if hasattr(channel, "sip_original_name") and channel.sip_original_name:
        channel.name = channel.sip_original_name
    if hasattr(channel, "sip_original_civil_code") and channel.sip_original_civil_code:
        channel.civil_code = channel.sip_original_civil_code
    if hasattr(channel, "sip_original_longitude") and channel.sip_original_longitude is not None:
        channel.longitude = channel.sip_original_longitude
    if hasattr(channel, "sip_original_latitude") and channel.sip_original_latitude is not None:
        channel.latitude = channel.sip_original_latitude
    await safe_auth_audit(
        db,
        module="devices",
        action="reset_channel",
        source="channel_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=(current_user.tenant_id or "default").strip() or "default",
        status_code=200,
        detail=f"channel_id={channel_id}",
    )
    await db.commit()
    return {"status": "ok", "reset": channel_id}


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    stmt = select(Resource).where(Resource.id == channel_id, Resource.node_type == "channel")
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    result = await db.execute(stmt)
    channel = get_or_404(result, detail="Channel not found")  # FIXED: ORM查询结果空值判断
    await db.delete(channel)
    await safe_auth_audit(
        db,
        module="devices",
        action="delete_channel",
        source="channel_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=(current_user.tenant_id or "default").strip() or "default",
        status_code=200,
        detail=f"channel_id={channel_id}",
    )
    await db.commit()
    return {"status": "ok", "deleted": channel_id}


@router.post("/channels/batch-placement")
async def batch_channel_placement(
    payload: BatchChannelPlacementPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    raw_ids = [str(x).strip() for x in (payload.resource_ids or []) if str(x).strip()]
    if not raw_ids:
        raise HTTPException(status_code=400, detail="resource_ids cannot be empty")
    placement = (payload.placement or "region").strip().lower()
    if placement not in ("region", "business"):
        raise HTTPException(status_code=400, detail="placement only supports region / business")
    tid = (payload.target_id or "").strip()
    val = tid if tid else None

    cc_update: str | None | bool = False  # False = 不修改 civil_code
    if payload.civil_code is not None:
        cc_norm = "".join(ch for ch in str(payload.civil_code) if ch.isdigit())
        cc_update = cc_norm[:16] if cc_norm else None

    tenant_id = current_user.tenant_id or "default"
    stmt = select(Resource).where(
        Resource.id.in_(raw_ids),
        Resource.node_type == "channel",
    )
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if val:
        dir_stmt = select(Resource.gb_id).where(Resource.node_type == "directory")
        if not current_user.is_superuser:
            dir_stmt = dir_stmt.where(Resource.tenant_id == tenant_id)
        directory_ids = {str(x).strip() for x in (await db.execute(dir_stmt)).scalars().all() if str(x).strip()}

        # 允许直接移动节点，不再抛出"请先移除后再添加"错误

    for ch in rows:
        if placement == "region":
            ch.region_parent_gb_id = val
            if cc_update is not False:
                ch.civil_code = cc_update
        else:
            ch.parent_gb_id = val

    await db.commit()
    return {"updated": len(rows), "requested": len(raw_ids)}


@router.post("/channels/batch-update-civil-code")
async def batch_update_civil_code(
    payload: BatchUpdateCivilCodePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]),
)):
    gb_ids = [str(x).strip() for x in (payload.gb_ids or []) if str(x).strip()]
    if not gb_ids:
        raise HTTPException(status_code=400, detail="gb_ids cannot be empty")
    civil_code = "".join(ch for ch in str(payload.civil_code) if ch.isdigit())
    if len(civil_code) != 8:
        raise HTTPException(status_code=400, detail="Administrative code must be 8 digits")
    tenant_id = current_user.tenant_id or "default"
    stmt = select(Resource).where(
        Resource.gb_id.in_(gb_ids),
        Resource.node_type == "channel",
    )
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    for ch in rows:
        ch.civil_code = civil_code
    await db.commit()
    await safe_auth_audit(
        db,
        module="devices",
        action="batch_update_civil_code",
        source="channel_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=(current_user.tenant_id or "default").strip() or "default",
        status_code=200,
        detail="ok",
        extra_summary=f"updated={len(rows)}; civil_code={civil_code}",
    )
    return {"updated": len(rows), "requested": len(gb_ids), "civil_code": civil_code}


@router.get("/directories/{parent_id}/children")
async def get_directory_children(
    parent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset).where(Asset.gb_id == parent_id)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_result = await db.execute(asset_stmt)
    device = asset_result.scalars().first()

    if device:
        # 选2：目录节点可能 asset_id 为 NULL，因此不能用 asset_id==device.id
        # 作为唯一条件，否则以设备为父节点创建的目录会被错误过滤掉。
        # 但当 parent_gb_id 为空（legacy/unmounted），仍需限定在该设备下避免跨设备混入。
        stmt = select(Resource).where(
            or_(
                Resource.parent_gb_id == parent_id,
                and_(
                    or_(Resource.parent_gb_id.is_(None), Resource.parent_gb_id == ""),
                    Resource.asset_id == device.id,
                ),
            ),
        )
        if not current_user.is_superuser:
            stmt = stmt.where(Resource.tenant_id == tenant_id)
    else:
        stmt = select(Resource).where(Resource.parent_gb_id == parent_id)
        if not current_user.is_superuser:
            # 选2：目录节点允许 asset_id 为空，因此不能通过 join Asset 限定租户
            stmt = stmt.where(Resource.tenant_id == tenant_id)

    result = await db.execute(stmt)
    resources = result.scalars().all()
    payload = []
    for item in resources:
        node = _resource_to_node(item, device.gb_id if device else "")
        node.pop("children", None)
        payload.append(node)
    return payload


@router.get("/tree")
async def get_device_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    # FIXED: /tree 端点全量查询无缓存 → 使用内存缓存，TTL 30秒
    tenant_id = current_user.tenant_id or "default"
    cache_key = f"region:{tenant_id}"
    now_ts = time.time()
    cached = _tree_cache.get(cache_key)
    if cached and (now_ts - cached[0]) < _TREE_CACHE_TTL:
        return cached[1]

    region_root = {
        "id": "region:root",
        "label": "根资源组",
        "nodeType": "root",
        "children": []
    }
    asset_stmt = select(Asset)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_result = await db.execute(asset_stmt)
    assets = asset_result.scalars().all()
    resource_stmt = select(Resource)
    if not current_user.is_superuser:
        resource_stmt = resource_stmt.where(Resource.tenant_id == tenant_id)
    resource_result = await db.execute(resource_stmt)
    resources = resource_result.scalars().all()

    # FIXED: /tree 端点结果无大小限制 → 添加最大节点数限制
    if len(resources) > _MAX_TREE_NODES:
        logger.warning(f"Tree nodes ({len(resources)}) exceed limit ({_MAX_TREE_NODES}), truncating")
        resources = resources[:_MAX_TREE_NODES]

    region_nodes: dict[str, dict[str, Any]] = {}
    region_leaf_dirs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    region_dir_nodes: dict[str, dict[str, Any]] = {}
    region_root_dir_nodes: list[dict[str, Any]] = []

    def ensure_region_chain(region_code: str) -> list[tuple[str, str]]:
        chain = _build_region_chain(region_code)
        for idx, (code, label) in enumerate(chain):
            # 只有当该行政区划在数据库中存在，或者 infer_region_placement 为 True 时才创建
            if code not in region_nodes:
                if code in region_records or infer_region_placement:
                    region_nodes[code] = {
                        "id": f"region:{code}",
                        "label": region_records.get(code, label),
                        "nodeType": "region",
                        "children": []
                    }
                else:
                    # 如果数据库没有这个行政区，且没有开启自动推断，则不创建节点
                    continue

            if idx > 0:
                parent_code = chain[idx - 1][0]
                if parent_code in region_nodes and code in region_nodes:
                    parent_node = region_nodes[parent_code]
                    if all(child["id"] != region_nodes[code]["id"] for child in parent_node["children"]):
                        parent_node["children"].append(region_nodes[code])
        return chain

    # 0) 获取所有行政区划记录，用于显示正确的名称
    from app.models.region import Region
    region_records_result = await db.execute(select(Region))
    region_records = {r.code: r.name for r in region_records_result.scalars().all()}

    # 更新已有的 region_nodes 名称
    def _update_region_names():
        for code, node in region_nodes.items():
            if code in region_records:
                node["label"] = region_records[code]
            elif code.endswith("0000"):
                node["label"] = f"省 {code}"
            elif code.endswith("00"):
                node["label"] = f"市 {code}"
            else:
                node["label"] = f"区/县 {code}"

    # 1) 先收集"行政区根/标准区划(=region:*)下"的目录节点
    for item in resources:
        if (item.node_type or "").lower() != "directory" or not item.gb_id:
            continue
        parent_gb_id = (item.parent_gb_id or "").strip()
        reg_parent_gb_id = (getattr(item, "region_parent_gb_id", None) or "").strip()
        # 不能再用 civil_code 作为判定，否则业务目录也会误进行政区树
        if reg_parent_gb_id.startswith("region:") or parent_gb_id.startswith("region:"):
            region_dir_nodes[item.gb_id] = _resource_to_node(item, "")

    # 2) 再做"闭包"：如果某目录节点的 region_parent_gb_id（或 parent_gb_id）指向一个
    #    已知行政区目录节点，那么它也应当属于行政区树，不能被过滤掉。
    #    这修复了"创建成功但树里看不到"的问题（你新增的节点常是挂在目录节点之下）。
    changed = True
    while changed:
        changed = False
        for item in resources:
            if (item.node_type or "").lower() != "directory" or not item.gb_id:
                continue
            if item.gb_id in region_dir_nodes:
                continue
            parent_gb_id = (item.parent_gb_id or "").strip()
            reg_parent_gb_id = (getattr(item, "region_parent_gb_id", None) or "").strip()
            if (reg_parent_gb_id and reg_parent_gb_id in region_dir_nodes) or (
                parent_gb_id and parent_gb_id in region_dir_nodes
            ):
                region_dir_nodes[item.gb_id] = _resource_to_node(item, "")
                changed = True

    for item in resources:
        if item.gb_id not in region_dir_nodes:
            continue
        node = region_dir_nodes[item.gb_id]
        parent_gb_id = (item.parent_gb_id or "").strip()
        reg_parent_gb_id = (getattr(item, "region_parent_gb_id", None) or "").strip()

        # 1) 优先用 region_parent_gb_id 组织 region 目录树
        if reg_parent_gb_id in region_dir_nodes and reg_parent_gb_id != item.gb_id:
            parent = region_dir_nodes[reg_parent_gb_id]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(node)
            continue

        # 2) 兼容历史：老数据使用 parent_gb_id 表示 region:* 或 region 目录父节点
        if parent_gb_id in region_dir_nodes and parent_gb_id != item.gb_id:
            parent = region_dir_nodes[parent_gb_id]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(node)
            continue

        region_code = ""
        if reg_parent_gb_id.startswith("region:"):
            tail = reg_parent_gb_id.split(":", 1)[1]
            # 修复：region:root 不是数字行政区码，不能 normalize 成 000000
            if str(tail).strip().lower() == "root":
                region_root_dir_nodes.append(node)
                continue
            region_code = _normalize_region_code(tail)
        elif parent_gb_id.startswith("region:"):
            tail = parent_gb_id.split(":", 1)[1]
            if str(tail).strip().lower() == "root":
                region_root_dir_nodes.append(node)
                continue
            region_code = _normalize_region_code(tail)
        else:
            # 不再使用 civil_code 作为归属推断，避免业务目录误入行政区树
            region_code = ""
        if region_code:
            ensure_region_chain(region_code)
            region_leaf_dirs[region_code].append(node)

    pending_region_channels: list[tuple[Resource, str]] = []
    root_region_channel_nodes: list[dict[str, Any]] = []
    infer_region_placement = False
    asset_map = {a.id: a for a in assets}
    for resource in resources:
        if (resource.node_type or "").lower() != "channel" or not resource.gb_id:
            continue
        reg_p = (getattr(resource, "region_parent_gb_id", None) or "").strip()
        if not reg_p:
            continue
        asset = asset_map.get(resource.asset_id)
        pending_region_channels.append((resource, asset.gb_id if asset else ""))

    for region_code, dir_nodes in region_leaf_dirs.items():
        leaf_node = region_nodes.get(region_code)
        if not leaf_node:
            continue
        existing_ids = {str(child.get("id")) for child in leaf_node.get("children", [])}
        for node in dir_nodes:
            if str(node.get("id")) not in existing_ids:
                leaf_node["children"].append(node)
        leaf_node["children"].sort(key=lambda x: (x.get("nodeType") != "directory", x.get("label") or ""))

    for resource, device_gb_id in pending_region_channels:
        ch_node = _resource_to_node(resource, device_gb_id)
        rp = (getattr(resource, "region_parent_gb_id", None) or "").strip()
        if not rp:
            continue
        placed = False
        if rp.startswith("region:"):
            tail = rp.split(":", 1)[1].strip() if ":" in rp else ""
            if tail.lower() == "root":
                root_region_channel_nodes.append(ch_node)
                placed = True
            else:
                rcode = _normalize_region_code(tail)
                ensure_region_chain(rcode)
                tgt = region_nodes.get(rcode)
                if tgt:
                    tgt.setdefault("children", []).append(ch_node)
                    placed = True
        elif rp in region_dir_nodes:
            pdir = region_dir_nodes[rp]
            pdir.setdefault("children", []).append(ch_node)
            placed = True
        if not placed:
            root_region_channel_nodes.append(ch_node)

    roots = [region_nodes[code] for code in region_nodes if code.endswith("0000")]
    _update_region_names()
    roots.sort(key=lambda x: x["label"])
    region_root["children"] = roots
    # region:root 下直接挂载的通道：最后补回，避免 region_root["children"] 被覆盖
    if root_region_channel_nodes:
        region_root["children"].extend(root_region_channel_nodes)
    # region:root 下直接挂载的行政区目录节点（同样最后补回）
    if region_root_dir_nodes:
        region_root["children"].extend(region_root_dir_nodes)
    _sort_tree_nodes(region_root)
    result = [region_root]
    # FIXED: /tree 端点全量查询无缓存 → 写入缓存
    _tree_cache[cache_key] = (now_ts, result)
    return result


@router.get("/tree/business")
async def get_business_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    # FIXED: /tree/business 端点全量查询无缓存 → 使用内存缓存，TTL 30秒
    tenant_id = _tenant_id_for_user(current_user)
    cache_key = f"business:{tenant_id}"
    now_ts = time.time()
    cached = _tree_cache.get(cache_key)
    if cached and (now_ts - cached[0]) < _TREE_CACHE_TTL:
        return cached[1]

    root_gb_id = _business_root_gb_id(tenant_id)
    await _ensure_business_root_resource(db, current_user)

    asset_stmt = select(Asset)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_result = await db.execute(asset_stmt)
    assets = asset_result.scalars().all()
    asset_map = {a.id: a for a in assets}
    resource_stmt = select(Resource)
    if not current_user.is_superuser:
        resource_stmt = resource_stmt.where(Resource.tenant_id == tenant_id)
    resources = (await db.execute(resource_stmt)).scalars().all()

    # FIXED: /tree/business 端点结果无大小限制 → 添加最大节点数限制
    if len(resources) > _MAX_TREE_NODES:
        logger.warning(f"Business tree nodes ({len(resources)}) exceed limit ({_MAX_TREE_NODES}), truncating")
        resources = resources[:_MAX_TREE_NODES]
    nodes: dict[str, dict[str, Any]] = {
        root_gb_id: {
            "id": root_gb_id,
            "label": "根资源组",
            "nodeType": "root",
            "children": [],
        }
    }
    resource_refs: dict[str, Resource] = {}

    # 计算"属于行政区树的目录集合"，避免行政区目录/通道被错误渲染到业务树下。
    # 思路：复用 get_device_tree 的闭包归属思想
    # - 种子：region:* 挂载，或 parent_gb_id 挂载为 region:*
    # - 闭包：只要其 parent/region_parent 指向已知行政区目录集合，也属于行政区树
    directory_nodes = [r for r in resources if (r.node_type or "").lower() == "directory" and r.gb_id]
    region_dir_set: set[str] = set()
    for r in directory_nodes:
        rp = (getattr(r, "region_parent_gb_id", None) or "").strip()
        pp = (r.parent_gb_id or "").strip()
        if rp.startswith("region:") or pp.startswith("region:"):
            region_dir_set.add(r.gb_id)
    changed = True
    while changed:
        changed = False
        for r in directory_nodes:
            if r.gb_id in region_dir_set:
                continue
            rp = (getattr(r, "region_parent_gb_id", None) or "").strip()
            pp = (r.parent_gb_id or "").strip()
            if (rp and rp in region_dir_set) or (pp and pp in region_dir_set):
                region_dir_set.add(r.gb_id)
                changed = True

    for item in resources:
        if not item.gb_id:
            continue
        # 排除行政区侧挂载（避免业务树混入 region:* 目录/通道）
        if (getattr(item, "region_parent_gb_id", None) or "").strip() or str((item.parent_gb_id or "")).startswith("region:"):
            continue
        # 进一步排除：属于行政区目录闭包的目录/通道都不要出现在业务树
        if (item.node_type or "").lower() == "directory":
            if item.gb_id in region_dir_set:
                continue
        else:
            if (item.parent_gb_id or "").strip() in region_dir_set:
                continue
            if (getattr(item, "region_parent_gb_id", None) or "").strip() in region_dir_set:
                continue
        if item.gb_id == root_gb_id:
            nodes[root_gb_id]["label"] = item.name or "根资源组"
            continue
        if (item.node_type or "").lower() == "channel":
            parent_for_channel = (item.parent_gb_id or "").strip()
            if not parent_for_channel:
                continue
        asset = asset_map.get(item.asset_id)
        device_id = asset.gb_id if asset else ""
        nodes[item.gb_id] = _resource_to_node(item, device_id)
        resource_refs[item.gb_id] = item

    for gb_id, node in list(nodes.items()):
        if gb_id == root_gb_id:
            continue
        ref = resource_refs.get(gb_id)
        parent_gb_id = (ref.parent_gb_id or "").strip() if ref else ""
        if parent_gb_id and parent_gb_id in nodes and parent_gb_id != gb_id:
            parent_node = nodes[parent_gb_id]
            if "children" not in parent_node:
                parent_node["children"] = []
            parent_node["children"].append(node)
        else:
            if (ref.node_type or "").lower() == "channel":
                continue
            nodes[root_gb_id]["children"].append(node)

    _sort_tree_nodes(nodes[root_gb_id])
    result = [nodes[root_gb_id]]
    # FIXED: /tree/business 端点全量查询无缓存 → 写入缓存
    _tree_cache[cache_key] = (now_ts, result)
    return result


@router.post("/directories")
async def create_directory(
    payload: DirectoryCreatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    gb_id = (payload.gb_id or "").strip()
    name = (payload.name or "").strip()
    if not gb_id or not name:
        raise HTTPException(status_code=400, detail="Node code and node name cannot be empty")  # FIXED: 硬编码中文→英文
    if len(gb_id) > 20:
        raise HTTPException(status_code=400, detail="Node ID length cannot exceed 20")

    tenant_id = _tenant_id_for_user(current_user)
    root_gb_id = _business_root_gb_id(tenant_id)
    await _ensure_business_root_resource(db, current_user)

    dup_stmt = select(Resource).where(Resource.gb_id == gb_id)
    if not current_user.is_superuser:
        dup_stmt = dup_stmt.where(Resource.tenant_id == tenant_id)
    duplicate = (await db.execute(dup_stmt)).scalars().first()
    if duplicate:
        raise HTTPException(status_code=400, detail="Node ID already exists")

    parent_gb_id = (payload.parent_gb_id or "").strip() or None
    # 为保证所有"业务目录节点"都在根资源组下面：当未传父节点时，强制挂到根资源组
    # （避免 parent_gb_id 为 None 导致出现"根资源组平级"的数据状态）
    if parent_gb_id is None:
        parent_gb_id = root_gb_id
    # 是否属于行政区划（region tree）：
    # - 直接以 region:xxxx 作为父节点（行政区划根/节点）=> region tree
    # - 或父节点链路中出现 region:*（兼容历史数据）
    region_parent_gb_id: str | None = None
    is_region_dir = False
    if isinstance(parent_gb_id, str) and parent_gb_id.startswith("region:"):
        is_region_dir = True
        region_parent_gb_id = parent_gb_id
    else:
        # 尝试向上追溯父目录是否属于 region tree
        cur = str(parent_gb_id or "").strip()
        for _ in range(10):
            if not cur or cur == root_gb_id:
                break
            stmt = select(Resource).where(Resource.gb_id == cur)
            if not current_user.is_superuser:
                stmt = stmt.where(Resource.tenant_id == tenant_id)
            parent = (await db.execute(stmt)).scalars().first()
            if not parent:
                break
            rp = (getattr(parent, "region_parent_gb_id", None) or "").strip()
            if rp:
                is_region_dir = True
                region_parent_gb_id = cur
                break
            pp = (getattr(parent, "parent_gb_id", None) or "").strip()
            if pp.startswith("region:"):
                is_region_dir = True
                region_parent_gb_id = cur
                break
            cur = pp
    final_civil_code = (
        _normalize_region_code(payload.civil_code) if payload.civil_code else None
    )
    if parent_gb_id and parent_gb_id.startswith("region:"):
        # 行政区划树父节点使用 region:xxxxxx 虚拟节点标识，允许直接挂载
        region_code = parent_gb_id.split(":", 1)[1] if ":" in parent_gb_id else ""
        # region:root 不是数字行政区码，不能 normalize 成 000000
        if not final_civil_code and region_code and str(region_code).strip().lower() != "root":
            final_civil_code = _normalize_region_code(region_code)
    elif parent_gb_id and parent_gb_id != root_gb_id:
        parent_stmt = select(Resource).where(Resource.gb_id == parent_gb_id)
        if not current_user.is_superuser:
            parent_stmt = parent_stmt.where(Resource.tenant_id == tenant_id)
        parent = (await db.execute(parent_stmt)).scalars().first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent node not found")
        if (parent.node_type or "").lower() != "directory":
            raise HTTPException(status_code=400, detail="Parent node must be a directory")
        if not final_civil_code and parent.civil_code:
            final_civil_code = _normalize_region_code(parent.civil_code)

    if not final_civil_code:
        # 优先从 gb_id 自身推导，避免 region:root 情况下兜底成 000000
        digits = "".join(ch for ch in str(gb_id or "") if ch.isdigit())
        if len(digits) >= 6:
            final_civil_code = _normalize_region_code(digits[:6])
        else:
            sip_id = await _get_effective_sip_id(db)
            final_civil_code = _civil_code_from_sip_id(sip_id)

    # 行政区目录创建不再做"上级前缀/同省同市"硬校验

    node = Resource(
        # 选2：目录节点不需要依赖任何设备；落库 asset_id = NULL
        asset_id=None,
        gb_id=gb_id,
        name=name,
        node_type="directory",
        status=1,
        parent_gb_id=None if is_region_dir else parent_gb_id,
        region_parent_gb_id=region_parent_gb_id if is_region_dir else None,
        civil_code=final_civil_code,
        tenant_id=tenant_id,
    )
    db.add(node)
    await db.commit()
    return {"status": "ok", "gb_id": gb_id}


@router.delete("/directories")
async def delete_directory(
    payload: DirectoryDeletePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    gb_id = (payload.gb_id or "").strip()
    if not gb_id:
        raise HTTPException(status_code=400, detail="Node ID cannot be empty")

    tenant_id = _tenant_id_for_user(current_user)
    root_gb_id = _business_root_gb_id(tenant_id)
    if gb_id == root_gb_id:
        raise HTTPException(status_code=400, detail="Root resource group cannot be deleted")

    stmt = select(Resource).where(Resource.gb_id == gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Resource.tenant_id == tenant_id)
    node = (await db.execute(stmt)).scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if (node.node_type or "").lower() != "directory":
        raise HTTPException(status_code=400, detail="Only directory nodes can be deleted")

    child_dir_stmt = select(Resource.gb_id).where(
        Resource.node_type == "directory",
        or_(Resource.parent_gb_id == gb_id, Resource.region_parent_gb_id == gb_id),
    )
    if not current_user.is_superuser:
        child_dir_stmt = child_dir_stmt.where(Resource.tenant_id == tenant_id)
    has_child_dir = (await db.execute(child_dir_stmt.limit(1))).scalars().first()
    if has_child_dir:
        raise HTTPException(status_code=400, detail="Subdirectories exist, cannot delete")

    parent_business = (node.parent_gb_id or "").strip() or None
    parent_region = (getattr(node, "region_parent_gb_id", None) or "").strip() or None

    reparent_business_stmt = (
        update(Resource)
        .where(
            Resource.node_type != "directory",
            Resource.parent_gb_id == gb_id,
        )
        .values(parent_gb_id=parent_business)
    )
    if not current_user.is_superuser:
        reparent_business_stmt = reparent_business_stmt.where(Resource.tenant_id == tenant_id)
    await db.execute(reparent_business_stmt)

    reparent_region_stmt = (
        update(Resource)
        .where(
            Resource.node_type != "directory",
            Resource.region_parent_gb_id == gb_id,
        )
        .values(region_parent_gb_id=parent_region)
    )
    if not current_user.is_superuser:
        reparent_region_stmt = reparent_region_stmt.where(Resource.tenant_id == tenant_id)
    await db.execute(reparent_region_stmt)

    await db.delete(node)
    await db.commit()
    return {"status": "ok"}


## 注：删除非根目录的一键清理接口已移除


@router.put("/directories")
async def rename_directory(
    payload: DirectoryRenamePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    gb_id = (payload.gb_id or "").strip()
    name = (payload.name or "").strip()
    if not gb_id or not name:
        raise HTTPException(status_code=400, detail="Node code and name are required")  # FIXED: hardcoded Chinese → English

    tenant_id = _tenant_id_for_user(current_user)
    stmt = select(Resource).where(Resource.gb_id == gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Resource.tenant_id == tenant_id)
    node = (await db.execute(stmt)).scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if (node.node_type or "").lower() not in {"directory", "root"}:
        raise HTTPException(status_code=400, detail="Only directory nodes can be renamed")

    node.name = name
    await db.commit()
    return {"status": "ok"}


@router.get("/directories/next-gb-id")
async def get_next_directory_gb_id(
    civil_code: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = _tenant_id_for_user(current_user)
    root_gb_id = _business_root_gb_id(tenant_id)
    await _ensure_business_root_resource(db, current_user)

    stmt = select(Resource.gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Resource.tenant_id == tenant_id)
    existing_ids = {
        str(row[0]).strip()
        for row in (await db.execute(stmt)).all()
        if row and row[0]
    }
    existing_ids.add(root_gb_id)

    # 目录节点编码规则（行政区风格）：
    # [SIP_ID前6位行政区划码] + [两位序号]，示例：13020201
    requested_code = _normalize_region_code(civil_code) if (civil_code or "").strip() else ""
    if requested_code and requested_code != "000000":
        base6 = requested_code
    else:
        sip_id = await _get_effective_sip_id(db)
        base6 = _civil_code_from_sip_id(sip_id)[:6]
    if not base6 or len(base6) != 6:
        base6 = _normalize_region_code(None)

    for seq in range(1, 100):
        gb_id = f"{base6}{seq:02d}"
        if gb_id not in existing_ids:
            return {"gb_id": gb_id}

    raise HTTPException(status_code=500, detail=f"Available sequence numbers under region code {base6} are exhausted, please fill in manually")  # FIXED: 硬编码中文→英文
