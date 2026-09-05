# FIX: [2026-07-03] devices/ 包缺少 __init__.py，导致 api.py 中 _mount(devices, ...) 找不到
#      router 属性，设备管理全部 API 返回 404。根因：包拆分时遗漏了 __init__.py。
#      修复：创建 __init__.py，合并 devices_crud 和 devices_channels 的路由。 [全栈工程师]
"""设备管理端点包 — 合并 CRUD、通道子资源与控制端点的路由。

FIX: [2026-08-22 P1] 路由遮蔽修复：crud 的 PUT/DELETE /{device_id} 通配路由先注册，
channels 后注册的单段静态路径 PUT/DELETE /directories 被通配路由抢先匹配
（device_id="directories"），目录改名/删除端点永远不可达（实测 422/404）。
修复：全部路由挂载完成后，把"单段通配路由"（形如 /{device_id}）稳定地移到
路由表末尾 —— FastAPI 按注册顺序匹配，静态路径先于通配路径即可消除遮蔽。
（不能新建独立 router 重挂 crud：其 GET "" 空路径路由在无前缀 include 时
会触发 FastAPI "Prefix and path cannot be both empty" 导入失败。）
"""
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


def _is_single_segment_wildcard(route) -> bool:
    """判断路由是否为单段通配路径（形如 ``/{device_id}``）。

    多段路径（如 ``/{device_id}/sync``）不参与单段遮蔽竞争，无需移动。
    """
    path = getattr(route, "path", "") or ""
    return (
        path.startswith("/{")
        and path.endswith("}")
        and "/" not in path[2:-1]
    )


# 单段通配路由（PUT/DELETE /{device_id}）移到路由表末尾，
# 确保同形状的静态路径（/directories 等）先被匹配。
_static_routes = [r for r in router.routes if not _is_single_segment_wildcard(r)]
_wildcard_routes = [r for r in router.routes if _is_single_segment_wildcard(r)]
router.routes[:] = _static_routes + _wildcard_routes

__all__ = ["router"]
