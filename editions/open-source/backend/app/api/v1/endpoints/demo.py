"""演示模式：内置演示设备与状态，供新用户体验。需配置 DEMO_MODE=true 启用。"""
from fastapi import APIRouter, Depends
from app.core.config import settings
from app.api import deps
from app.models.user import User

router = APIRouter()

DEMO_DEVICES = [
    {
        "id": "demo-device-1",
        "device_id": "34020000001320000001",
        "name": "演示-大门",
        "manufacturer": "演示",
        "model": "Demo",
        "status": "Online",
        "is_demo": True,
    },
    {
        "id": "demo-device-2",
        "device_id": "34020000001320000002",
        "name": "演示-车间A",
        "manufacturer": "演示",
        "model": "Demo",
        "status": "Online",
        "is_demo": True,
    },
    {
        "id": "demo-device-3",
        "device_id": "34020000001320000003",
        "name": "演示-仓库",
        "manufacturer": "演示",
        "model": "Demo",
        "status": "Online",
        "is_demo": True,
    },
]

DEMO_CHANNELS = [
    {"id": "demo-ch-1", "device_id": "demo-device-1", "channel_id": "34020000001320000001", "name": "大门-1", "status": "Online", "is_demo": True},
    {"id": "demo-ch-2", "device_id": "demo-device-2", "channel_id": "34020000001320000002", "name": "车间A-1", "status": "Online", "is_demo": True},
    {"id": "demo-ch-3", "device_id": "demo-device-3", "channel_id": "34020000001320000003", "name": "仓库-1", "status": "Online", "is_demo": True},
]


def _demo_enabled() -> bool:
    return getattr(settings, "DEMO_MODE", False) is True


@router.get("/status")
def demo_status(current_user: User = Depends(deps.get_current_active_user)):
    """是否开启演示模式。"""
    return {"enabled": _demo_enabled()}


@router.get("/devices")
def demo_devices(current_user: User = Depends(deps.get_current_active_user)):
    """演示模式开启时返回内置演示设备列表；未开启返回空数组。"""
    if not _demo_enabled():
        return []
    return DEMO_DEVICES


@router.get("/channels")
def demo_channels(current_user: User = Depends(deps.get_current_active_user)):
    """演示模式开启时返回内置演示通道列表；未开启返回空数组。"""
    if not _demo_enabled():
        return []
    return DEMO_CHANNELS
