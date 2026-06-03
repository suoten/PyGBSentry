"""
plugins — 插件管理 API 子模块聚合。

将 5+1 个子模块的 router 统一挂载到同一个 prefix 下，
对外导出单一 `router`，与原 plugins.py 行为完全一致。

plugins_market（插件市场）子模块在 PLUGIN_MARKETPLACE_ENABLED=False 时不注册，
以避免开源版启动时连接外部 API。但仍提供前端常用接口的空响应 stub，
避免前端请求时收到 405。
"""
from fastapi import APIRouter

from app.core.config import settings # FIXED: __import__ 反模式改为标准 import

from .plugins_install import router as install_router
from .plugins_runtime import router as runtime_router
from .plugins_license import router as license_router
from .plugins_events import router as events_router
from .plugins_events2 import router as events2_router

router = APIRouter()

router.include_router(install_router)
router.include_router(runtime_router)
router.include_router(license_router)
router.include_router(events_router)
router.include_router(events2_router)

_is_marketplace_enabled = bool(getattr(settings, "PLUGIN_MARKETPLACE_ENABLED", False)) # FIXED: __import__ 反模式改为标准 import

if _is_marketplace_enabled:
    from .plugins_market import router as market_router
    router.include_router(market_router)
else:
    @router.get("/purchased")
    async def purchased_stub():
        return {"plugin_ids": [], "plugins": [], "plugin_id_to_name": {}}

    @router.get("/marketplace-shop-url")
    async def marketplace_shop_url_stub():
        return {"url": ""}

    @router.get("/marketplace")
    async def marketplace_list_stub():
        return {"items": [], "total": 0}
