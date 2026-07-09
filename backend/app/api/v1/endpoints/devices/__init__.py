# FIX: [2026-07-03] devices/ 包缺少 __init__.py，导致 api.py 中 _mount(devices, ...) 找不到
#      router 属性，设备管理全部 API 返回 404。根因：包拆分时遗漏了 __init__.py。
#      修复：创建 __init__.py，合并 devices_crud 和 devices_channels 的路由。 [全栈工程师]
"""设备管理端点包 — 合并 CRUD 与通道子资源的路由。"""

# 使用 crud_router 作为主路由（包含 @router.get("") 根路由），
# 将 channels_router 的路由合并进来（channels 路由均有非空路径，可安全 include）
from .devices_crud import router as router
from .devices_channels import router as channels_router
router.include_router(channels_router)

__all__ = ["router"]
