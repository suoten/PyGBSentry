"""devices 子模块聚合：将 CRUD / 通道 / 控制三个子 router 合并为一个统一 router。"""

from fastapi import APIRouter

from .devices_crud import router as crud_router
from .devices_channels import router as channels_router
from .devices_control import router as control_router
from .devices_control import get_channel_snapshot

router = APIRouter()

for r in crud_router.routes:
    router.routes.append(r)
router.include_router(channels_router)
router.include_router(control_router)
