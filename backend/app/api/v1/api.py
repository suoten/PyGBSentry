"""API v1 router aggregation.

Imports every endpoint module under ``app.api.v1.endpoints`` and mounts its
``router``. In the open-source edition many endpoint modules are absent (they
are enterprise-only); those are skipped gracefully so that a missing module
never blocks application startup. This mirrors the existing
``_route_stubs_oss`` philosophy where enterprise endpoints surface as 501
stubs rather than breaking the router.

Resilient import strategy:
  * Each endpoint module is imported individually inside a ``try``/``except``.
  * Missing modules resolve to ``None`` and their ``include_router`` call is
    skipped (a log line records the skip for operational visibility).
  * Modules that exist but expose no ``router`` attribute are likewise skipped.
"""
# ruff: noqa: F821  — endpoint module names are dynamically injected via globals() in the loop below
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from loguru import logger

from app.api.v1.endpoints import _route_stubs_oss
from app.core.config import settings

# Names of endpoint modules imported from ``app.api.v1.endpoints``.
# Order is preserved for deterministic router mounting.
_ENDPOINT_MODULES = [
    "hook", "devices", "control", "record", "device_record", "gb_record",
    "record_schedule", "regions", "organizations", "login", "users",
    "user_api_keys", "ops", "logs", "alarms", "talk", "map", "plugins",
    "health", "work_orders", "billing", "integrations", "push_channels",
    "trace_events", "system_config", "config_center", "release_center",
    "audit_center", "channel_import", "platforms", "asset_management",
    "network", "network_diagnostics", "reports", "setup", "demo", "metrics",
    "apps", "command", "structured", "rtp", "roles", "proxy_compat", "media",
    "blacklist", "ptz", "ai_gateway", "vod", "stream_optimization",
    "ssl_cert", "sip_trace_ws",
]


def _load(name: str):
    """Import ``app.api.v1.endpoints.<name>``; return the module or ``None``.

    FIX: [2026-07-13] Distinguish between "module doesn't exist" (expected for
    OSS edition — enterprise-only modules are absent) and "module exists but
    failed to import" (bug, missing dependency). The former is logged at DEBUG
    (expected). The latter is now logged at WARNING with full traceback so
    operators can diagnose why routes are silently missing in production.

    Previously ALL failures were logged at DEBUG, which is hidden when
    APP_ENV=prod (stderr level=WARNING). This caused modules like ``plugins``
    to silently fail import (e.g., missing ``aiohttp`` dep) with all their
    routes returning 404 and no visible error in the logs. [全栈工程师]
    """
    import importlib.util
    try:
        spec = importlib.util.find_spec(f"app.api.v1.endpoints.{name}")
    except Exception:
        spec = None
    if spec is None:
        # Module file doesn't exist — expected for OSS edition (enterprise-only)
        logger.debug(f"api router: endpoint module '{name}' not found (expected for OSS edition)")
        return None
    try:
        return importlib.import_module(f"app.api.v1.endpoints.{name}")
    except Exception as e:
        # Module EXISTS but failed to import — this is a bug, log at WARNING
        # so it's visible in production (DEBUG is hidden when APP_ENV=prod)
        logger.warning(
            f"api router: endpoint module '{name}' exists but FAILED to import: {e}",
            exc_info=True,
        )
        return None


# Import each endpoint module; missing ones become ``None``.
for _name in _ENDPOINT_MODULES:
    globals()[_name] = _load(_name)

# Sub-package routers that live in their own package (stream) or common layer.
# FIX: [2026-07-13] Log import failures at WARNING (visible in production) —
# if these modules exist but fail to import, all their routes silently 404.
try:
    from app.api.v1.endpoints.stream import router as stream_router  # type: ignore
except Exception as _e:
    logger.warning(f"api router: stream package failed to import, skipping ({_e})", exc_info=True)
    stream_router = None  # type: ignore[assignment]

try:
    from app.api.common import channel  # type: ignore
except Exception as _e:
    logger.warning(f"api router: app.api.common.channel failed to import, skipping ({_e})", exc_info=True)
    channel = None  # type: ignore[assignment]

try:
    from app.api.common import play_start  # type: ignore
except Exception as _e:
    logger.warning(f"api router: app.api.common.play_start failed to import, skipping ({_e})", exc_info=True)
    play_start = None  # type: ignore[assignment]


api_router = APIRouter()
# ARCHITECTURE: 统一使用 app.core.edition 进行版本判断，避免散落的 APP_EDITION 字符串比较
from app.core.edition import is_server_edition as _is_server_edition_fn, edition_label
is_server_edition = _is_server_edition_fn()


def _mount(mod, prefix: Optional[str] = None, tags: Optional[list] = None) -> None:
    if mod is None:
        return
    router = getattr(mod, "router", None)
    if router is None:
        return
    if prefix:
        api_router.include_router(router, prefix=prefix, tags=tags or [])
    elif tags:
        api_router.include_router(router, tags=tags)
    else:
        api_router.include_router(router)


_mount(login, tags=["login"])
_mount(users, prefix="/users", tags=["users"])
_mount(roles, prefix="/roles", tags=["roles"])
_mount(user_api_keys, prefix="/user-api-keys", tags=["user-api-keys"])
_mount(billing, prefix="/billing", tags=["billing"])
_mount(plugins, prefix="/plugins", tags=["plugins"])
if channel is not None:
    _mount(channel, prefix="/channels", tags=["channels"])

if not is_server_edition:
    _mount(setup, prefix="/setup", tags=["setup"])
    _mount(ops, prefix="/ops", tags=["ops"])
    _mount(logs, prefix="/logs", tags=["logs"])
    _mount(alarms, prefix="/alarms", tags=["alarms"])

    _mount(blacklist, prefix="/blacklist", tags=["blacklist"])
    _mount(work_orders, prefix="/work-orders", tags=["work-orders"])
    _mount(health, prefix="/health", tags=["health"])
    _mount(talk, prefix="/talk", tags=["talk"])
    _mount(map, prefix="/map", tags=["map"])
    _mount(command, prefix="/command", tags=["command"])
    _mount(structured, prefix="/structured", tags=["structured"])
    _mount(hook, prefix="/hook", tags=["hook"])
    if stream_router is not None:
        api_router.include_router(stream_router, prefix="/stream", tags=["stream"])
    _mount(stream_optimization, prefix="/stream-opt", tags=["stream-optimization"])
    _mount(media, prefix="/media", tags=["media"])
    _mount(devices, prefix="/devices", tags=["devices"])
    _mount(integrations, prefix="/integrations", tags=["integrations"])
    _mount(push_channels, prefix="/push-channels", tags=["push-channels"])
    _mount(proxy_compat, prefix="/proxy", tags=["proxy"])
    _mount(trace_events, prefix="/trace-events", tags=["trace-events"])
    # R4-03 注册SIP Trace WebSocket路由，使端点可达
    _mount(sip_trace_ws, tags=["sip-trace"])
    _mount(system_config, prefix="/system-config", tags=["system-config"])
    # DEPRECATED: /system alias — will be removed in a future version
    _mount(system_config, prefix="/system", tags=["system", "deprecated"])
    _mount(config_center, prefix="/config-center", tags=["config-center"])
    _mount(release_center, prefix="/release-center", tags=["release-center"])
    _mount(audit_center, prefix="/audit-center", tags=["audit-center"])
    _mount(control, prefix="/control", tags=["control"])
    _mount(record, prefix="/record", tags=["record"])
    _mount(vod, prefix="/vod", tags=["vod"])
    _mount(gb_record, prefix="/gb-record", tags=["gb-record"])
    _mount(record_schedule, prefix="/record-schedule", tags=["record-schedule"])
    _mount(regions, prefix="/regions", tags=["regions"])
    _mount(organizations, prefix="/organizations", tags=["organizations"])
    _mount(device_record, prefix="/device-record", tags=["device-record"])
    _mount(channel_import, prefix="/devices/channels", tags=["devices"])
    _mount(platforms, prefix="/platforms", tags=["platforms"])
    _mount(rtp, prefix="/rtp", tags=["rtp"])
    _mount(asset_management, prefix="/asset-management", tags=["asset-management"])
    _mount(network, prefix="/network", tags=["network"])
    # A-12 前缀从/network改为/network-diagnostics，避免与network路由冲突
    _mount(network_diagnostics, prefix="/network-diagnostics", tags=["network-diagnostics"])
    _mount(reports, prefix="/reports", tags=["reports"])
    _mount(ai_gateway, prefix="/ai", tags=["ai"])
    _mount(demo, prefix="/demo", tags=["demo"])
    _mount(metrics, prefix="/metrics", tags=["metrics"])
    _mount(apps, prefix="/apps", tags=["apps"])
    _mount(ptz, prefix="/ptz", tags=["ptz"])
    _mount(ssl_cert, prefix="/ssl-cert", tags=["ssl-cert"])  # 硬编码中文tag→英文

# P2-29 路由暴露验证: 以下 stub 路由有意注册到 OSS 路由表，确认无误。
# 这些端点为企业版专有功能的占位（全部返回 501 + deprecated 标记），
# 注册目的: (1) 在 OpenAPI/Swagger 文档中可见，标明企业版能力边界；
#           (2) 客户端调用时返回明确的 501 而非 404，便于区分"不存在"与"未实现"。
# 已验证: stub 路径与 OSS 真实路由无冲突（均为企业版专有路径，如
#         /plugins/license/signing-key-rotation/*、/plugins/webhooks 等）。
api_router.include_router(_route_stubs_oss.router, tags=["stubs-oss"])

@api_router.get("/ping")
def health_check():
    return {
        "status": "ok",
        "edition": edition_label(),
        "version": settings.PROJECT_VERSION,
        "project": settings.PROJECT_NAME,
    }


from fastapi.responses import RedirectResponse

@api_router.get("/push_channels")
@api_router.post("/push_channels")
async def redirect_push_channels():
    return RedirectResponse(url="/api/v1/push-channels", status_code=307)

@api_router.get("/record_schedule")
@api_router.post("/record_schedule")
async def redirect_record_schedule():
    return RedirectResponse(url="/api/v1/record-schedule", status_code=307)

@api_router.get("/device_record")
@api_router.post("/device_record")
async def redirect_device_record():
    return RedirectResponse(url="/api/v1/device-record", status_code=307)

@api_router.get("/gb_record")
@api_router.post("/gb_record")
async def redirect_gb_record():
    return RedirectResponse(url="/api/v1/gb-record", status_code=307)
# 302→307，302会导致POST请求被浏览器转为GET丢失body，307保持原始HTTP方法
