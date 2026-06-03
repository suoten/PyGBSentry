from fastapi import APIRouter
from app.api.v1.endpoints import hook, devices, control, record, device_record, gb_record, record_schedule, regions, organizations, login, users, user_api_keys, ops, logs, alarms, talk, map, plugins, health, work_orders, billing, integrations, push_channels, trace_events, system_config, config_center, release_center, audit_center, channel_import, platforms, asset_management, network, network_diagnostics, reports, setup, demo, metrics, apps, command, structured, rtp, roles, proxy_compat, media, blacklist, ptz, ai_gateway, vod, stream_optimization, ssl_cert
from app.api.v1.endpoints import _route_stubs_oss
from app.api.v1.endpoints.stream import router as stream_router
from app.api.common import channel
from app.core.config import settings

api_router = APIRouter()
is_server_edition = (settings.APP_EDITION or "oss").lower() == "server"

api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(user_api_keys.router, prefix="/user-api-keys", tags=["user-api-keys"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(plugins.router, prefix="/plugins", tags=["plugins"])
api_router.include_router(channel.router, prefix="/channels", tags=["channels"])

if not is_server_edition:
    api_router.include_router(setup.router, prefix="/setup", tags=["setup"])
    api_router.include_router(ops.router, prefix="/ops", tags=["ops"])
    api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
    api_router.include_router(alarms.router, prefix="/alarms", tags=["alarms"])

    api_router.include_router(blacklist.router, prefix="/blacklist", tags=["blacklist"])
    api_router.include_router(work_orders.router, prefix="/work-orders", tags=["work-orders"])
    api_router.include_router(health.router, prefix="/health", tags=["health"])
    api_router.include_router(talk.router, prefix="/talk", tags=["talk"])
    api_router.include_router(map.router, prefix="/map", tags=["map"])
    api_router.include_router(command.router, prefix="/command", tags=["command"])
    api_router.include_router(structured.router, prefix="/structured", tags=["structured"])
    api_router.include_router(hook.router, prefix="/hook", tags=["hook"])
    api_router.include_router(stream_router, prefix="/stream", tags=["stream"])
    api_router.include_router(stream_optimization.router, prefix="/stream-opt", tags=["stream-optimization"])
    api_router.include_router(media.router, prefix="/media", tags=["media"])
    api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
    api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
    api_router.include_router(push_channels.router, prefix="/push-channels", tags=["push-channels"])
    api_router.include_router(proxy_compat.router, prefix="/proxy", tags=["proxy"])
    api_router.include_router(trace_events.router, prefix="/trace-events", tags=["trace-events"])
    api_router.include_router(system_config.router, prefix="/system-config", tags=["system-config"])
    # DEPRECATED: /system alias — will be removed in a future version
    api_router.include_router(system_config.router, prefix="/system", tags=["system", "deprecated"])
    api_router.include_router(config_center.router, prefix="/config-center", tags=["config-center"])
    api_router.include_router(release_center.router, prefix="/release-center", tags=["release-center"])
    api_router.include_router(audit_center.router, prefix="/audit-center", tags=["audit-center"])
    api_router.include_router(control.router, prefix="/control", tags=["control"])
    api_router.include_router(record.router, prefix="/record", tags=["record"])
    api_router.include_router(vod.router, prefix="/vod", tags=["vod"])
    api_router.include_router(gb_record.router, prefix="/gb-record", tags=["gb-record"])
    api_router.include_router(record_schedule.router, prefix="/record-schedule", tags=["record-schedule"])
    api_router.include_router(regions.router, prefix="/regions", tags=["regions"])
    api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
    api_router.include_router(device_record.router, prefix="/device-record", tags=["device-record"])
    api_router.include_router(channel_import.router, prefix="/devices/channels", tags=["devices"])
    api_router.include_router(platforms.router, prefix="/platforms", tags=["platforms"])
    api_router.include_router(rtp.router, prefix="/rtp", tags=["rtp"])
    api_router.include_router(asset_management.router, prefix="/asset-management", tags=["asset-management"])
    api_router.include_router(network.router, prefix="/network", tags=["network"])
    api_router.include_router(network_diagnostics.router, prefix="/network-diagnostics", tags=["network-diagnostics"])  # FIXED: A-12 前缀从/network改为/network-diagnostics，避免与network路由冲突
    api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
    api_router.include_router(ai_gateway.router, prefix="/ai", tags=["ai"])
    api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
    api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
    api_router.include_router(apps.router, prefix="/apps", tags=["apps"])
    api_router.include_router(ptz.router, prefix="/ptz", tags=["ptz"])
    api_router.include_router(ssl_cert.router, prefix="/ssl-cert", tags=["ssl-cert"])  # FIXED: 硬编码中文tag→英文

api_router.include_router(_route_stubs_oss.router, tags=["stubs-oss"])

@api_router.get("/ping")
def health_check():
    return {
        "status": "ok",
        "edition": (settings.APP_EDITION or "oss"),
        "version": getattr(settings, "PROJECT_VERSION", "1.0.0"),
        "project": getattr(settings, "PROJECT_NAME", "PyGBSentry"),
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
# FIXED: 302→307，302会导致POST请求被浏览器转为GET丢失body，307保持原始HTTP方法
