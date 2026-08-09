# FIX: [2026-07-03] devices_crud.py 和 devices_channels.py 从 ._common 导入大量符号，
#      但 _common.py 文件在包拆分时遗漏创建，导致两个子模块均无法导入、设备管理 API 全部 404。
#      根因：refactoring 时遗漏了共享模块的创建。修复：按使用方式重建 _common.py。 [全栈工程师]
"""设备端点共享工具函数与 Pydantic 模型。

由 devices_crud.py 和 devices_channels.py 共同使用。
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.resource import Resource
from app.models.user import User
from loguru import logger


# ─── 工具函数 ──────────────────────────────────────────────────────────────────

def _tenant_id_for_user(user: User) -> str:
    """返回用户的 tenant_id，空值回退为 'default'。"""
    return (user.tenant_id or "default").strip() or "default"


def _safe_val(val: Any) -> str:
    """安全地将任意值转为字符串，None 返回空串。"""
    if val is None:
        return ""
    return str(val)


def _normalize_default_stream_type(val: Any, strict: bool = False) -> str:
    """规范化码流类型：main / sub。strict=True 时非法值抛 ValueError。"""
    v = str(val or "").strip().lower()
    if v in ("main", "sub"):
        return v
    if v in ("0", "primary"):
        return "main"
    if v in ("1", "secondary"):
        return "sub"
    if strict:
        raise ValueError(f"Invalid stream type: {val}")
    return "main"


def _normalize_region_code(val: Any) -> str:
    """将行政区码规范化为 6 位数字字符串。空值返回 '000000'。"""
    if not val:
        return "000000"
    digits = "".join(ch for ch in str(val) if ch.isdigit())
    if not digits:
        return "000000"
    # 取前 6 位
    return digits[:6].ljust(6, "0")


def _civil_code_from_sip_id(sip_id: str) -> str:
    """从 SIP ID（20 位国标编码）提取前 6 位行政区划码。"""
    if not sip_id:
        return "000000"
    digits = "".join(ch for ch in str(sip_id) if ch.isdigit())
    return digits[:6].ljust(6, "0") if digits else "000000"


def _business_root_gb_id(tenant_id: str) -> str:
    """业务根资源组的 GB ID（基于 SIP_ID 生成）。"""
    sip_id = settings.SIP_ID or "34020000002000000001"
    # 根资源组 ID = SIP_ID 前 10 位 + "0000000000"（共 20 位）
    base = sip_id[:10] if len(sip_id) >= 10 else sip_id.ljust(10, "0")
    return f"{base}0000000000"[:20]


async def _get_effective_sip_id(db: AsyncSession) -> str:
    """从数据库或配置获取有效的 SIP ID。"""
    # 优先从 SystemSetting 读取，回退到配置
    try:
        from app.models.system_setting import SystemSetting
        result = await db.execute(
            select(SystemSetting.setting_value).where(SystemSetting.setting_key == "sip_id")
        )
        val = result.scalar()
        if val:
            return str(val).strip()
    except Exception as e:
        logger.debug(f"_common: failed to load sip_id from DB: {e}")
    return settings.SIP_ID or "34020000002000000001"


async def _ensure_business_root_resource(db: AsyncSession, current_user: User) -> None:
    """确保业务根资源组存在，不存在则创建。"""
    tenant_id = _tenant_id_for_user(current_user)
    root_gb_id = _business_root_gb_id(tenant_id)
    stmt = select(Resource).where(Resource.gb_id == root_gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Resource.tenant_id == tenant_id)
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing:
        return
    root = Resource(
        asset_id=None,
        gb_id=root_gb_id,
        name="根资源组",
        node_type="directory",
        status=1,
        parental=1,
        tenant_id=tenant_id,
    )
    db.add(root)
    await db.commit()


def _resource_to_node(r: Resource, device_id: str = "") -> dict[str, Any]:
    """将 Resource ORM 对象转为前端树节点 dict。

    FIX: [2026-07-13] 添加可选 ``device_id`` 参数 — 5 处调用点均传入 device_id
    但函数签名只接受 1 个参数，导致 ``TypeError: _resource_to_node() takes 1
    positional argument but 2 were given``，``/api/v1/devices/tree/business``
    等端点返回 500。 [全栈工程师]
    """
    return {
        "id": r.gb_id,
        "label": r.name or r.gb_id,
        "nodeType": r.node_type or "channel",
        "gb_id": r.gb_id,
        "name": r.name,
        "status": r.status,
        "online": r.status == 1,
        "civil_code": r.civil_code,
        "parent_gb_id": r.parent_gb_id,
        "region_parent_gb_id": getattr(r, "region_parent_gb_id", None),
        "has_audio": bool(r.has_audio),
        "has_ptz": bool(getattr(r, "has_ptz", False)),
        "longitude": r.longitude,
        "latitude": r.latitude,
        "address": r.address,
        # FIX: [2026-07-13] Resource 模型本身没有 manufacturer/model 字段（这些在 Asset 父设备上），
        # 直接访问会触发 AttributeError: 'Resource' object has no attribute 'manufacturer'，
        # 导致 /api/v1/devices/tree/business 等端点 500。使用 getattr 安全访问，未关联设备时返回 None。
        # 服务器日志确认：app/api/v1/endpoints/devices/_common.py:140 AttributeError。
        "manufacturer": getattr(r, "manufacturer", None),
        "model": getattr(r, "model", None),
        "device_id": device_id,
    }


def _build_region_chain(code: str, nodes: dict[str, dict]) -> None:
    """根据行政区码构建层级目录链，填充 nodes 字典。"""
    if not code or code == "000000":
        return
    chain = []
    for length in (2, 4, 6):
        c = code[:length].ljust(length, "0")
        if c == "000000" and length == 6:
            continue
        chain.append(c)
    for c in chain:
        gb_id = f"region:{c}"
        if gb_id not in nodes:
            nodes[gb_id] = {
                "id": gb_id,
                "label": f"行政区 {c}",
                "nodeType": "directory",
                "children": [],
            }


def _sort_tree_nodes(node: dict[str, Any]) -> None:
    """递归排序树节点：目录在前，通道在后，各自按 label 排序。"""
    children = node.get("children")
    if not children:
        return
    directories = [c for c in children if (c.get("nodeType") or "") == "directory"]
    channels = [c for c in children if (c.get("nodeType") or "") != "directory"]
    directories.sort(key=lambda x: (x.get("label") or ""))
    channels.sort(key=lambda x: (x.get("label") or ""))
    node["children"] = directories + channels
    for child in node["children"]:
        _sort_tree_nodes(child)


# ─── Pydantic 模型 ─────────────────────────────────────────────────────────────

class StreamModeUpdate(BaseModel):
    """设备码流传输模式更新。"""
    model_config = ConfigDict(extra="forbid")
    stream_mode: str


class DeviceOrganizationUpdate(BaseModel):
    """设备组织归属更新。"""
    model_config = ConfigDict(extra="forbid")
    organization_id: str | None = None


class CatalogSubscriptionUpdate(BaseModel):
    """目录订阅更新。"""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    expiry: int = 3600


class MobilePositionSubscriptionUpdate(BaseModel):
    """移动位置订阅更新。"""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    interval: int = 60


class DeviceCreatePayload(BaseModel):
    """手动添加设备请求体。"""
    model_config = ConfigDict(extra="forbid")
    gb_id: str
    name: str
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


class DeviceUpdatePayload(BaseModel):
    """编辑设备信息请求体。"""
    model_config = ConfigDict(extra="forbid")
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
    """批量删除设备请求体。"""
    model_config = ConfigDict(extra="forbid")
    gb_ids: list[str]


class DeviceBlacklistRequest(BaseModel):
    """设备拉黑请求体。"""
    model_config = ConfigDict(extra="forbid")
    ip: str
    blacklist_ip: bool = True
    delete_all_from_ip: bool = False
    delete_current: bool = False


class DeviceExportPayload(BaseModel):
    """设备导出请求体。"""
    model_config = ConfigDict(extra="forbid")
    format: str = "csv"
    include_channels: bool = False
    gb_ids: list[str] | None = None


class BatchChannelSnapPayload(BaseModel):
    """批量通道截图请求体。

    FIX: [2026-07-13] 从 2ad636a 恢复 — devices_control.py 的 /channels/snap-batch
    端点需要此模型，ConvergeLoop Round 0 删除了它。[全栈工程师]
    """
    model_config = ConfigDict(extra="forbid")
    channel_ids: list[str]


class ChannelUpdatePayload(BaseModel):
    """通道更新请求体。"""
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    status: int | None = None
    node_type: str | None = None
    civil_code: str | None = None
    parent_gb_id: str | None = None
    region_parent_gb_id: str | None = None
    has_audio: bool | None = None
    default_stream_type: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    address: str | None = None
    parental: int | None = None
    safety_way: int | None = None
    register_way: int | None = None
    secrecy: int | None = None
    ptz_type: str | None = None
    position_type: str | None = None
    room_type: str | None = None
    use_type: str | None = None
    supply_light_type: str | None = None
    direction_type: str | None = None
    resolution: str | None = None
    business_group_id: str | None = None


class BatchChannelPlacementPayload(BaseModel):
    """批量通道归属设置请求体。"""
    model_config = ConfigDict(extra="forbid")
    resource_ids: list[str]
    placement: str = "region"
    target_id: str | None = None
    civil_code: str | None = None


class DirectoryCreatePayload(BaseModel):
    """目录创建请求体。"""
    model_config = ConfigDict(extra="forbid")
    gb_id: str | None = None
    name: str | None = None
    parent_gb_id: str | None = None
    civil_code: str | None = None


class DirectoryDeletePayload(BaseModel):
    """目录删除请求体。"""
    model_config = ConfigDict(extra="forbid")
    gb_id: str | None = None


class DirectoryRenamePayload(BaseModel):
    """目录重命名请求体。"""
    model_config = ConfigDict(extra="forbid")
    gb_id: str | None = None
    name: str | None = None


class BatchUpdateCivilCodePayload(BaseModel):
    """批量更新行政区码请求体。"""
    model_config = ConfigDict(extra="forbid")
    gb_ids: list[str]
    civil_code: str
