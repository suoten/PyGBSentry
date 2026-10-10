"""
plugins — 插件管理 API 子模块聚合。

将 5+1 个子模块的 router 统一挂载到同一个 prefix 下，
对外导出单一 `router`，与原 plugins.py 行为完全一致。

plugins_market（插件市场）子模块在 PLUGIN_MARKETPLACE_ENABLED=False 时不注册，
以避免开源版启动时连接外部 API。但仍提供前端常用接口的空响应 stub，
避免前端请求时收到 404/405。
"""
from fastapi import APIRouter, HTTPException

from app.core.config import settings # __import__ 反模式改为标准 import

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

_is_marketplace_enabled = settings.PLUGIN_MARKETPLACE_ENABLED # __import__ 反模式改为标准 import

# 官网账户代理端点（双版账户打通）；市场禁用时由下方 503 stub 兜底
if _is_marketplace_enabled:
    from .plugins_official_account import router as official_account_router
    router.include_router(official_account_router)
else:
    @router.get("/official-account/status")
    async def official_account_status_stub():
        return {"marketplace_configured": False, "marketplace_enabled": False, "marketplace_host": ""}

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
        # FIXED: [2026-10-10] 与启用时的裸数组形状保持一致（前端按数组渲染）
        return []

    @router.get("/marketplace")
    async def marketplace_list_stub():
        return {"items": [], "total": 0}

    # 修复：购买相关端点在 marketplace 禁用时返回 503，避免前端调用收到 404
    @router.post("/marketplace/purchase")
    async def marketplace_purchase_stub():
        raise HTTPException(
            status_code=503,
            detail="Plugin marketplace not configured. Set PLUGIN_MARKETPLACE_ENABLED=true to enable purchases.",
        )

    @router.post("/marketplace/purchase/confirm")
    async def marketplace_purchase_confirm_stub():
        raise HTTPException(
            status_code=503,
            detail="Plugin marketplace not configured. Set PLUGIN_MARKETPLACE_ENABLED=true to enable purchases.",
        )

# AI 插件运行时数据端点（face/plate/behavior 三个付费 AI 插件的 iframe 管理页依赖），
# AI 插件是付费的，随插件市场一起启用；加载失败仅告警，不阻断启动。
if _is_marketplace_enabled:
    try:
        from .plugins_ai_runtime import router as ai_runtime_router

        router.include_router(ai_runtime_router)
    except Exception as exc:  # noqa: BLE001
        from loguru import logger

        logger.warning(f"plugins_ai_runtime 注册失败，AI 插件运行时数据端点不可用: {exc}")
