"""Demo mode: returns demo device/channel data for new user onboarding.

Requires DEMO_MODE=true to enable. When enabled, a startup warning is emitted
and all demo data is clearly marked with is_demo=true.

Demo data is loaded from an external JSON file (data/demo_data.json) if available,
otherwise falls back to built-in defaults.
"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends
from loguru import logger
from app.core.config import settings
from app.api import deps
from app.models.user import User

router = APIRouter()

# Built-in fallback demo data (used when external file is not available)
_FALLBACK_DEVICES = [
    {
        "id": "demo-device-1",
        "device_id": "34020000001320000001",
        "name": "Demo - Gate",
        "manufacturer": "Demo",
        "model": "Demo",
        "status": "Online",
        "is_demo": True,
    },
    {
        "id": "demo-device-2",
        "device_id": "34020000001320000002",
        "name": "Demo - Workshop A",
        "manufacturer": "Demo",
        "model": "Demo",
        "status": "Online",
        "is_demo": True,
    },
    {
        "id": "demo-device-3",
        "device_id": "34020000001320000003",
        "name": "Demo - Warehouse",
        "manufacturer": "Demo",
        "model": "Demo",
        "status": "Online",
        "is_demo": True,
    },
]

_FALLBACK_CHANNELS = [
    {"id": "demo-ch-1", "device_id": "demo-device-1", "channel_id": "34020000001320000001", "name": "Gate-1", "status": "Online", "is_demo": True},
    {"id": "demo-ch-2", "device_id": "demo-device-2", "channel_id": "34020000001320000002", "name": "Workshop A-1", "status": "Online", "is_demo": True},
    {"id": "demo-ch-3", "device_id": "demo-device-3", "channel_id": "34020000001320000003", "name": "Warehouse-1", "status": "Online", "is_demo": True},
]


def _load_demo_data() -> tuple[list, list]:
    """Load demo data from external JSON file, falling back to built-in defaults."""
    demo_file = Path(__file__).resolve().parent.parent.parent.parent / "data" / "demo_data.json"
    if demo_file.is_file():
        try:
            with open(demo_file, encoding="utf-8") as f:
                data = json.load(f)
            devices = data.get("devices", _FALLBACK_DEVICES)
            channels = data.get("channels", _FALLBACK_CHANNELS)
            # Ensure all items are marked as demo
            for d in devices:
                d["is_demo"] = True
            for c in channels:
                c["is_demo"] = True
            return devices, channels
        except Exception as e:
            logger.warning(f"Failed to load demo data from {demo_file}: {e}, using defaults")
    return _FALLBACK_DEVICES, _FALLBACK_CHANNELS


DEMO_DEVICES, DEMO_CHANNELS = _load_demo_data()


def _demo_enabled() -> bool:
    enabled = settings.DEMO_MODE is True
    if enabled:
        logger.warning(
            "DEMO_MODE is enabled. Demo device data is being served. "
            "Disable DEMO_MODE in production by setting DEMO_MODE=false in .env."
        )
    return enabled


@router.get("/status")
def demo_status(current_user: User = Depends(deps.get_current_active_user)):
    """Check if demo mode is enabled."""
    return {"enabled": _demo_enabled()}


@router.get("/devices")
def demo_devices(current_user: User = Depends(deps.get_current_active_user)):
    """Return demo device list when demo mode is enabled; empty array otherwise."""
    if not _demo_enabled():
        return []
    return DEMO_DEVICES


@router.get("/channels")
def demo_channels(current_user: User = Depends(deps.get_current_active_user)):
    """Return demo channel list when demo mode is enabled; empty array otherwise."""
    if not _demo_enabled():
        return []
    return DEMO_CHANNELS
