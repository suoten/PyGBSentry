# FIX: [2026-07-03] devices/ 包缺少 __init__.py，导致 api.py 中 _mount(devices, ...) 找不到
#      router 属性，设备管理全部 API 返回 404。根因：包拆分时遗漏了 __init__.py。
#      修复：创建 __init__.py，合并 devices_crud 和 devices_channels 的路由。 [全栈工程师]
"""设备管理端点包 — 合并 CRUD、通道子资源与控制端点的路由。"""

# 使用 crud_router 作为主路由（包含 @router.get("") 根路由），
# 将 channels_router 的路由合并进来（channels 路由均有非空路径，可安全 include）
from .devices_crud import router as router
from .devices_channels import router as channels_router
router.include_router(channels_router)

# FIX: [2026-07-13] 从 2ad636a 恢复 devices_control 路由 — 包含快照、同步、
# 目录查询等设备控制端点。ConvergeLoop Round 0 删除了 devices_control.py，
# 导致 /api/v1/devices/channels/{id}/snap 等端点全部 404。 [全栈工程师]
try:
    from .devices_control import router as control_router
    router.include_router(control_router)
except Exception as _e:
    import loguru
    loguru.logger.warning(f"devices_control router import failed, skipping: {_e}")

__all__ = ["router"]
