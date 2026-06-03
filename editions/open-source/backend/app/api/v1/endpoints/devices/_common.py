"""devices 子模块共享的工具函数、常量和 Pydantic 模型。"""

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.core.config import settings
from typing import Any
import hashlib

# ---------- 常量 ----------

_DEFAULT_STREAM_TYPE_ALIAS = {
    "main": "main",
    "sub": "sub",
    "0": "main",
    "1": "sub",
    "stream:0": "stream:0",
    "stream:1": "stream:1",
    "streamnumber:0": "streamnumber:0",
    "streamnumber:1": "streamnumber:1",
    "streamprofile:0": "streamprofile:0",
    "streamprofile:1": "streamprofile:1",
    "streammode:main": "streamMode:MAIN",
    "streammode:sub": "streamMode:SUB",
}

# ---------- 工具函数 ----------


def _normalize_default_stream_type(value: Any, *, strict: bool = False) -> str:
    key = str(value or "").strip().lower()
    normalized = _DEFAULT_STREAM_TYPE_ALIAS.get(key)
    if normalized:
        return normalized
    if strict:
        raise HTTPException(status_code=400, detail="Invalid default_stream_type")
    return "main"


def _normalize_region_code(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return "000000"
    value = "".join(ch for ch in value if ch.isdigit())
    if not value:
        return "000000"
    if len(value) >= 6:
        return value[:6]
    return value.ljust(6, "0")


def _build_region_chain(region_code: str) -> list[tuple[str, str]]:
    # region_code 可能已经是省/市级（例如 110000/110100 这种），
    # 如果直接拼接会出现重复 code，进一步在 build tree 时可能形成自引用导致递归爆栈。
    province = region_code[:2] + "0000"
    city = region_code[:4] + "00"

    codes: list[str] = []
    for code in (province, city, region_code):
        if code and code not in codes:
            codes.append(code)

    return [(code, f"行政区 {code}") for code in codes]


def _resource_to_node(resource: Resource, device_id: str) -> dict[str, Any]:
    node_type = (resource.node_type or "channel").lower()
    if node_type not in {"directory", "channel"}:
        node_type = "channel"
    node = {
        "id": resource.gb_id,
        "label": resource.name or resource.gb_id,
        "nodeType": node_type,
        "deviceId": device_id,
        "channelId": resource.gb_id if node_type == "channel" else None,
        "status": resource.status,
        "hasChildren": node_type == "directory"
    }
    if node_type == "directory":
        node["children"] = []
    return node


async def _get_effective_sip_id(db: AsyncSession) -> str:
    result = await db.execute(
        select(SystemSetting.setting_value).where(SystemSetting.setting_key == "sip.sip_id")
    )
    value = result.scalar()
    return str(value or settings.SIP_ID or "").strip()


def _civil_code_from_sip_id(sip_id: str) -> str:
    digits = "".join(ch for ch in str(sip_id or "") if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    return _normalize_region_code(digits)


def _tenant_id_for_user(user: User) -> str:
    return user.tenant_id or "default"


def _business_root_gb_id(tenant_id: str) -> str:
    # GBID 最多 20 位，使用稳定 hash 生成租户唯一根节点编码
    digest = hashlib.md5(tenant_id.encode("utf-8")).hexdigest()[:19]
    return f"R{digest}"


async def _pick_tenant_anchor_asset(
    db: AsyncSession,
    current_user: User,
    device_id: str | None = None,
) -> Asset | None:
    tenant_id = _tenant_id_for_user(current_user)
    stmt = select(Asset)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    if device_id:
        stmt = stmt.where(Asset.gb_id == device_id)
    stmt = stmt.order_by(desc(Asset.updated_at), desc(Asset.created_at))
    result = await db.execute(stmt.limit(1))
    return result.scalars().first()


def _sort_tree_nodes(node: dict[str, Any]) -> None:
    children = node.get("children")
    if not isinstance(children, list):
        return
    def _is_playable_channel(ch: dict[str, Any]) -> bool:
        if str(ch.get("nodeType") or "").lower() != "channel":
            return False
        if int(ch.get("status") or 0) != 1:
            return False
        gb_id = str(ch.get("id") or "")
        type_code = gb_id[10:13] if len(gb_id) >= 13 else ""
        return type_code in {"131", "132", "111", "112", "118"}

    def _node_sort_key(item: dict[str, Any]):
        node_type = str(item.get("nodeType") or "").lower()
        if node_type in {"root", "region", "directory"}:
            rank = 0
        elif node_type == "channel":
            if _is_playable_channel(item):
                rank = 1
            elif int(item.get("status") or 0) == 1:
                rank = 2
            else:
                rank = 3
        else:
            rank = 4
        return (rank, str(item.get("label") or ""))

    children.sort(key=_node_sort_key)
    for child in children:
        _sort_tree_nodes(child)


async def _ensure_business_root_resource(
    db: AsyncSession,
    current_user: User,
) -> Resource | None:
    tenant_id = _tenant_id_for_user(current_user)
    root_gb_id = _business_root_gb_id(tenant_id)
    stmt = select(Resource).where(Resource.gb_id == root_gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Resource.tenant_id == tenant_id)
    root = (await db.execute(stmt)).scalars().first()
    if root:
        if (root.node_type or "").lower() != "directory":
            root.node_type = "directory"
            root.name = root.name or "根资源组"
            await db.commit()
        return root
    root = Resource(
        # 选2：不依赖设备；根目录节点允许不落到任何 Asset 上。
        asset_id=None,
        gb_id=root_gb_id,
        name="根资源组",
        node_type="directory",
        status=1,
        parent_gb_id=None,
        civil_code=None,
        tenant_id=tenant_id,
    )
    db.add(root)
    await db.commit()
    await db.refresh(root)
    return root


def _safe_val(v):
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


# ---------- Pydantic 模型 ----------

class StreamModeUpdate(BaseModel):
    stream_mode: str


class DeviceOrganizationUpdate(BaseModel):
    organization_id: str | None = None


class CatalogSubscriptionUpdate(BaseModel):
    cycle_seconds: int = 60


class MobilePositionSubscriptionUpdate(BaseModel):
    enabled: bool = True
    interval_seconds: int = 60
    renew_seconds: int = 300


class BatchChannelPlacementPayload(BaseModel):
    """批量修改通道在行政区树或业务树下的挂载（支持批量设置区划/分组）。"""
    resource_ids: list[str]
    placement: str = "region"  # region | business
    # 目标父节点国标/region: 前缀；空字符串表示从当前维度卸下挂载
    target_id: str | None = None
    # 仅 placement=region 时可选：同步写入 Resource.civil_code（6 位区划码）；不传则不修改 civil_code
    civil_code: str | None = None


class BatchChannelSnapPayload(BaseModel):
    channel_ids: list[str]


class ChannelUpdatePayload(BaseModel):
    name: str | None = None
    status: int | None = None
    node_type: str | None = None
    civil_code: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    parent_gb_id: str | None = None
    region_parent_gb_id: str | None = None
    has_audio: bool | None = None
    # 码流偏好：main=主码流, sub=子码流
    default_stream_type: str | None = None

    # GB28181 Extended
    address: str | None = None
    parental: int | None = None
    safety_way: int | None = None
    register_way: int | None = None
    secrecy: int | None = None
    ip_address: str | None = None
    port: int | None = None
    password: str | None = None
    ptz_type: int | None = None
    position_type: int | None = None
    room_type: int | None = None
    use_type: int | None = None
    supply_light_type: int | None = None
    direction_type: int | None = None
    resolution: str | None = None
    business_group_id: str | None = None


class DirectoryCreatePayload(BaseModel):
    gb_id: str
    name: str
    parent_gb_id: str | None = None
    device_id: str | None = None
    civil_code: str | None = None


class DirectoryDeletePayload(BaseModel):
    gb_id: str


class DirectoryRenamePayload(BaseModel):
    gb_id: str
    name: str


class DeviceCreatePayload(BaseModel):
    gb_id: str
    name: str
    password: str | None = None
    ip_addr: str | None = None
    port: int | None = None
    transport: str = "UDP"
    manufacturer: str | None = None
    model: str | None = None
    firmware: str | None = None
    domain: str | None = None
    charset: str | None = "UTF-8"
    ssrc_check: bool | None = False
    geo_coord_sys: str | None = "WGS84"
    as_message_channel: bool | None = False
    heartbeat_interval: int | None = 60
    heartbeat_count: int | None = 3


class DeviceUpdatePayload(BaseModel):
    name: str | None = None
    password: str | None = None
    ip_addr: str | None = None
    port: int | None = None
    transport: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware: str | None = None
    domain: str | None = None
    charset: str | None = None
    ssrc_check: bool | None = None
    geo_coord_sys: str | None = None
    as_message_channel: bool | None = None
    heartbeat_interval: int | None = None
    heartbeat_count: int | None = None


class BatchDeletePayload(BaseModel):
    gb_ids: list[str]


class DeviceBlacklistRequest(BaseModel):
    ip: str
    delete_current: bool = True
    delete_all_from_ip: bool = False
    blacklist_ip: bool = True


class DeviceExportPayload(BaseModel):
    gb_ids: list[str] | None = None
    format: str = "csv"  # csv | json
    include_channels: bool = False


class BatchUpdateCivilCodePayload(BaseModel):
    gb_ids: list[str] = []
    civil_code: str = ""
