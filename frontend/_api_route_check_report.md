# 前端 API 调用 vs 后端路由对照报告

- 后端注册路由数: 586
- 前端唯一 API 调用数: 358
- ✓ 完全匹配: 232
- ⚠️ 方法不匹配: 122
- ✗ 路径不存在: 4

## ⚠️ 方法不匹配

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/v1/alarms/link-rules/{id}` | 路径参数不同: ['/api/v1/alarms/link-rules/{rule_id}'] |
| DELETE | `/api/v1/asset-management/maintenances/{id}` | 路径参数不同: ['/api/v1/asset-management/maintenances/{maintenance_id}'] |
| DELETE | `/api/v1/blacklist/{id}` | 路径参数不同: ['/api/v1/blacklist/{ip}'] |
| DELETE | `/api/v1/devices/channels/{id}` | 路径参数不同: ['/api/v1/devices/channels/{channel_id}'] |
| DELETE | `/api/v1/devices/{id}` | 路径参数不同: ['/api/v1/devices/{device_id}'] |
| DELETE | `/api/v1/integrations/ffmpeg_cmd/{id}` | 路径参数不同: ['/api/v1/integrations/ffmpeg_cmd/{cmd_id}'] |
| DELETE | `/api/v1/integrations/media-nodes/{id}` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}'] |
| DELETE | `/api/v1/integrations/media-nodes/{id}/zlm-ssl` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}/zlm-ssl'] |
| DELETE | `/api/v1/integrations/sources/{id}` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}'] |
| DELETE | `/api/v1/map/providers/{id}` | 路径参数不同: ['/api/v1/map/providers/{profile_id}'] |
| DELETE | `/api/v1/organizations/{id}` | 路径参数不同: ['/api/v1/organizations/{organization_id}'] |
| DELETE | `/api/v1/platforms/{id}` | 路径参数不同: ['/api/v1/platforms/{platform_id}'] |
| DELETE | `/api/v1/plugins/{id}` | 路径参数不同: ['/api/v1/plugins/{plugin_id}'] |
| DELETE | `/api/v1/push-channels/{id}` | 路径参数不同: ['/api/v1/push-channels/{channel_id}'] |
| DELETE | `/api/v1/record-schedule/{id}` | 路径参数不同: ['/api/v1/record-schedule/{schedule_id}'] |
| DELETE | `/api/v1/record/{id}` | 路径参数不同: ['/api/v1/record/{record_id}'] |
| DELETE | `/api/v1/regions/{id}` | 路径参数不同: ['/api/v1/regions/{region_id}'] |
| DELETE | `/api/v1/roles/{id}` | 路径参数不同: ['/api/v1/roles/{role_id}'] |
| DELETE | `/api/v1/stream-opt/session/{id}` | 路径参数不同: ['/api/v1/stream-opt/session/{session_id}'] |
| DELETE | `/api/v1/users/{id}` | 路径参数不同: ['/api/v1/users/{user_id}'] |
| DELETE | `/api/v1/work-orders/{id}` | 路径参数不同: ['/api/v1/work-orders/{work_order_id}'] |
| GET | `/api/v1/command/sessions/{id}/participants` | 路径参数不同: ['/api/v1/command/sessions/{session_id}/participants'] |
| GET | `/api/v1/control/{id}/{id}/cruise/{id}/points` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/cruise/{cruise_id}/points'] |
| GET | `/api/v1/control/{id}/{id}/preset/list` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/preset/list'] |
| GET | `/api/v1/control/{id}/{id}/scan/{id}/config` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/scan/{scan_id}/config'] |
| GET | `/api/v1/control/{id}/{id}/state` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/state'] |
| GET | `/api/v1/device-record/device/queries/{id}` | 路径参数不同: ['/api/v1/device-record/device/queries/{query_id}'] |
| GET | `/api/v1/device-record/download/progress/{id}` | 路径参数不同: ['/api/v1/device-record/download/progress/{task_id}'] |
| GET | `/api/v1/devices/{id}/catalog-runtime` | 路径参数不同: ['/api/v1/devices/{device_id}/catalog-runtime'] |
| GET | `/api/v1/devices/{id}/channels` | 路径参数不同: ['/api/v1/devices/{device_id}/channels'] |
| GET | `/api/v1/gb-record/download/progress/{id}/{id}/{id}` | 路径参数不同: ['/api/v1/gb-record/download/progress/{device_id}/{channel_id}/{stream}'] |
| GET | `/api/v1/gb-record/download/start/{id}/{id}` | 路径参数不同: ['/api/v1/gb-record/download/start/{device_id}/{channel_id}'] |
| GET | `/api/v1/gb-record/download/stop/{id}/{id}/{id}` | 路径参数不同: ['/api/v1/gb-record/download/stop/{device_id}/{channel_id}/{stream}'] |
| GET | `/api/v1/gb-record/query/{id}/{id}` | 路径参数不同: ['/api/v1/gb-record/query/{device_id}/{channel_id}'] |
| GET | `/api/v1/integrations/media-nodes/{id}/zlm-config-snippet` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}/zlm-config-snippet'] |
| GET | `/api/v1/integrations/media-nodes/{id}/zlm-hook-urls` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}/zlm-hook-urls'] |
| GET | `/api/v1/integrations/sources/{id}/push-url` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}/push-url'] |
| GET | `/api/v1/platforms/{id}/catalog-resources` | 路径参数不同: ['/api/v1/platforms/{platform_id}/catalog-resources'] |
| GET | `/api/v1/platforms/{id}/diagnosis` | 路径参数不同: ['/api/v1/platforms/{platform_id}/diagnosis'] |
| GET | `/api/v1/plugins/runtime/{id}/config` | 路径参数不同: ['/api/v1/plugins/runtime/{plugin_id}/config'] |
| GET | `/api/v1/plugins/{id}/uninstall-preview` | 路径参数不同: ['/api/v1/plugins/{plugin_id}/uninstall-preview'] |
| GET | `/api/v1/record/download/sign/{id}` | 路径参数不同: ['/api/v1/record/download/sign/{record_id}'] |
| GET | `/api/v1/record/play-url/{id}` | 路径参数不同: ['/api/v1/record/play-url/{record_id}'] |
| GET | `/api/v1/release-center/drafts/{id}/diff` | 路径参数不同: ['/api/v1/release-center/drafts/{draft_id}/diff'] |
| GET | `/api/v1/stream-opt/health/{id}` | 路径参数不同: ['/api/v1/stream-opt/health/{session_id}'] |
| GET | `/api/v1/stream-opt/lines/{id}/{id}` | 路径参数不同: ['/api/v1/stream-opt/lines/{device_id}/{channel_id}'] |
| GET | `/api/v1/stream-opt/play/{id}/{id}` | 路径参数不同: ['/api/v1/stream-opt/play/{device_id}/{channel_id}'] |
| GET | `/api/v1/stream/play_status/{id}` | 路径参数不同: ['/api/v1/stream/play_status/{session_id}'] |
| GET | `/api/v1/vod/vod/optimized-url/{id}` | 路径参数不同: ['/api/v1/vod/vod/optimized-url/{record_id}'] |
| GET | `/api/v1/vod/vod/sources/{id}` | 路径参数不同: ['/api/v1/vod/vod/sources/{record_id}'] |
| POST | `/api/v1/alarms/{id}/ack` | 路径参数不同: ['/api/v1/alarms/{alarm_id}/ack'] |
| POST | `/api/v1/alarms/{id}/escalate` | 路径参数不同: ['/api/v1/alarms/{alarm_id}/escalate'] |
| POST | `/api/v1/command/sessions/{id}/close` | 路径参数不同: ['/api/v1/command/sessions/{session_id}/close'] |
| POST | `/api/v1/command/sessions/{id}/join` | 路径参数不同: ['/api/v1/command/sessions/{session_id}/join'] |
| POST | `/api/v1/config-center/drafts/{id}/validate` | 路径参数不同: ['/api/v1/config-center/drafts/{draft_id}/validate'] |
| POST | `/api/v1/control/{id}/teleboot` | 路径参数不同: ['/api/v1/control/{device_id}/teleboot'] |
| POST | `/api/v1/control/{id}/{id}/alarm-reset` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/alarm-reset'] |
| POST | `/api/v1/control/{id}/{id}/aux` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/aux'] |
| POST | `/api/v1/control/{id}/{id}/cruise` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/cruise'] |
| POST | `/api/v1/control/{id}/{id}/focus` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/focus'] |
| POST | `/api/v1/control/{id}/{id}/guard` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/guard'] |
| POST | `/api/v1/control/{id}/{id}/iframe` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/iframe'] |
| POST | `/api/v1/control/{id}/{id}/iris` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/iris'] |
| POST | `/api/v1/control/{id}/{id}/preset` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/preset'] |
| POST | `/api/v1/control/{id}/{id}/preset/delete` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/preset/delete'] |
| POST | `/api/v1/control/{id}/{id}/preset/set` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/preset/set'] |
| POST | `/api/v1/control/{id}/{id}/ptz` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/ptz'] |
| POST | `/api/v1/control/{id}/{id}/record` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/record'] |
| POST | `/api/v1/control/{id}/{id}/scan` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/scan'] |
| POST | `/api/v1/control/{id}/{id}/state` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/state'] |
| POST | `/api/v1/control/{id}/{id}/wiper` | 路径参数不同: ['/api/v1/control/{device_id}/{channel_id}/wiper'] |
| POST | `/api/v1/device-record/download/stop/{id}` | 路径参数不同: ['/api/v1/device-record/download/stop/{task_id}'] |
| POST | `/api/v1/devices/channels/{id}/reset` | 路径参数不同: ['/api/v1/devices/channels/{channel_id}/reset'] |
| POST | `/api/v1/devices/{id}/blacklist` | 路径参数不同: ['/api/v1/devices/{device_id}/blacklist'] |
| POST | `/api/v1/devices/{id}/sync` | 路径参数不同: ['/api/v1/devices/{device_id}/sync'] |
| POST | `/api/v1/integrations/media-nodes/{id}/activate` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}/activate'] |
| POST | `/api/v1/integrations/media-nodes/{id}/test` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}/test'] |
| POST | `/api/v1/integrations/sources/{id}/actions/desired-state` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}/actions/desired-state'] |
| POST | `/api/v1/integrations/sources/{id}/actions/set-enabled` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}/actions/set-enabled'] |
| POST | `/api/v1/integrations/sources/{id}/play` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}/play'] |
| POST | `/api/v1/integrations/sources/{id}/test` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}/test'] |
| POST | `/api/v1/map/providers/{id}/activate` | 路径参数不同: ['/api/v1/map/providers/{profile_id}/activate'] |
| POST | `/api/v1/platforms/{id}/actions/push-catalog` | 路径参数不同: ['/api/v1/platforms/{platform_id}/actions/push-catalog'] |
| POST | `/api/v1/platforms/{id}/actions/register` | 路径参数不同: ['/api/v1/platforms/{platform_id}/actions/register'] |
| POST | `/api/v1/push-channels/{id}/remove_from_gb` | 路径参数不同: ['/api/v1/push-channels/{channel_id}/remove_from_gb'] |
| POST | `/api/v1/push-channels/{id}/rotate-push-key` | 路径参数不同: ['/api/v1/push-channels/{channel_id}/rotate-push-key'] |
| POST | `/api/v1/push-channels/{id}/save_to_gb` | 路径参数不同: ['/api/v1/push-channels/{channel_id}/save_to_gb'] |
| POST | `/api/v1/record-schedule/{id}/actions/force-start` | 路径参数不同: ['/api/v1/record-schedule/{schedule_id}/actions/force-start'] |
| POST | `/api/v1/record-schedule/{id}/actions/force-stop` | 路径参数不同: ['/api/v1/record-schedule/{schedule_id}/actions/force-stop'] |
| POST | `/api/v1/record/repair-url/{id}` | 路径参数不同: ['/api/v1/record/repair-url/{record_id}'] |
| POST | `/api/v1/record/verify/{id}` | 路径参数不同: ['/api/v1/record/verify/{record_id}'] |
| POST | `/api/v1/rtp/receive/close/{id}` | 路径参数不同: ['/api/v1/rtp/receive/close/{task_id}'] |
| POST | `/api/v1/stream-opt/reconnect/{id}` | 路径参数不同: ['/api/v1/stream-opt/reconnect/{session_id}'] |
| POST | `/api/v1/stream/play/{id}/switch` | 路径参数不同: ['/api/v1/stream/play/{stream_id}/switch'] |
| POST | `/api/v1/stream/play/{id}/{id}` | 路径参数不同: ['/api/v1/stream/play/{device_id}/{channel_id}'] |
| POST | `/api/v1/stream/playback/{id}/{id}` | 路径参数不同: ['/api/v1/stream/playback/{device_id}/{channel_id}'] |
| POST | `/api/v1/user-api-keys/{id}/revoke` | 路径参数不同: ['/api/v1/user-api-keys/{key_id}/revoke'] |
| POST | `/api/v1/users/{id}/unlock` | 路径参数不同: ['/api/v1/users/{user_id}/unlock'] |
| PUT | `/api/v1/alarms/link-rules/{id}` | 路径参数不同: ['/api/v1/alarms/link-rules/{rule_id}'] |
| PUT | `/api/v1/asset-management/maintenances/{id}` | 路径参数不同: ['/api/v1/asset-management/maintenances/{maintenance_id}'] |
| PUT | `/api/v1/config-center/drafts/{id}/modules/{id}` | 路径参数不同: ['/api/v1/config-center/drafts/{draft_id}/modules/{module_name}'] |
| PUT | `/api/v1/devices/channels/{id}` | 路径参数不同: ['/api/v1/devices/channels/{channel_id}'] |
| PUT | `/api/v1/devices/{id}` | 路径参数不同: ['/api/v1/devices/{device_id}'] |
| PUT | `/api/v1/devices/{id}/organization` | 路径参数不同: ['/api/v1/devices/{device_id}/organization'] |
| PUT | `/api/v1/devices/{id}/stream-mode` | 路径参数不同: ['/api/v1/devices/{device_id}/stream-mode'] |
| PUT | `/api/v1/devices/{id}/subscriptions/catalog` | 路径参数不同: ['/api/v1/devices/{device_id}/subscriptions/catalog'] |
| PUT | `/api/v1/devices/{id}/subscriptions/mobile-position` | 路径参数不同: ['/api/v1/devices/{device_id}/subscriptions/mobile-position'] |
| PUT | `/api/v1/integrations/ffmpeg_cmd/{id}` | 路径参数不同: ['/api/v1/integrations/ffmpeg_cmd/{cmd_id}'] |
| PUT | `/api/v1/integrations/media-nodes/{id}` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}'] |
| PUT | `/api/v1/integrations/media-nodes/{id}/zlm-ssl` | 路径参数不同: ['/api/v1/integrations/media-nodes/{node_id}/zlm-ssl'] |
| PUT | `/api/v1/integrations/sources/{id}` | 路径参数不同: ['/api/v1/integrations/sources/{source_id}'] |
| PUT | `/api/v1/map/providers/{id}` | 路径参数不同: ['/api/v1/map/providers/{profile_id}'] |
| PUT | `/api/v1/organizations/{id}` | 路径参数不同: ['/api/v1/organizations/{organization_id}'] |
| PUT | `/api/v1/platforms/{id}` | 路径参数不同: ['/api/v1/platforms/{platform_id}'] |
| PUT | `/api/v1/platforms/{id}/catalog-resources` | 路径参数不同: ['/api/v1/platforms/{platform_id}/catalog-resources'] |
| PUT | `/api/v1/plugins/runtime/{id}/config` | 路径参数不同: ['/api/v1/plugins/runtime/{plugin_id}/config'] |
| PUT | `/api/v1/push-channels/{id}` | 路径参数不同: ['/api/v1/push-channels/{channel_id}'] |
| PUT | `/api/v1/record-schedule/{id}` | 路径参数不同: ['/api/v1/record-schedule/{schedule_id}'] |
| PUT | `/api/v1/regions/{id}` | 路径参数不同: ['/api/v1/regions/{region_id}'] |
| PUT | `/api/v1/roles/{id}` | 路径参数不同: ['/api/v1/roles/{role_id}'] |
| PUT | `/api/v1/users/{id}` | 路径参数不同: ['/api/v1/users/{user_id}'] |
| PUT | `/api/v1/work-orders/{id}` | 路径参数不同: ['/api/v1/work-orders/{work_order_id}'] |

## ✗ 路径不存在（真正的 404）

| 方法 | 路径 | 调用文件 |
|------|------|----------|
| DELETE | `/api/v1/proxy/delete?id={id}` | views\PullProxyList.vue |
| GET | `/api/v1/alarms?limit=50` | views\Dashboard.vue |
| POST | `/api/v1/plugins/marketplace/purchase` | views\PluginCenter.vue |
| POST | `/api/v1/plugins/marketplace/purchase/confirm` | views\PluginCenter.vue |

## 完全匹配的 API 列表

- ✓ DELETE `/api/v1/devices/directories`
- ✓ DELETE `/api/v1/system-config/gb28181/learning-state`
- ✓ GET `/api/common/channel/list`
- ✓ GET `/api/common/channel/stream-status`
- ✓ GET `/api/v1/alarms`
- ✓ GET `/api/v1/alarms/config`
- ✓ GET `/api/v1/alarms/link-rules`
- ✓ GET `/api/v1/alarms/notifications`
- ✓ GET `/api/v1/alarms/sla/compare`
- ✓ GET `/api/v1/alarms/sla/overview`
- ✓ GET `/api/v1/alarms/sla/presets`
- ✓ GET `/api/v1/alarms/sla/quality`
- ✓ GET `/api/v1/alarms/unread-count`
- ✓ GET `/api/v1/apps/logs`
- ✓ GET `/api/v1/apps/remote-config`
- ✓ GET `/api/v1/apps/stats`
- ✓ GET `/api/v1/asset-management/ledger`
- ✓ GET `/api/v1/asset-management/maintenances`
- ✓ GET `/api/v1/audit-center/export.csv`
- ✓ GET `/api/v1/audit-center/logs`
- ✓ GET `/api/v1/audit-center/stats`
- ✓ GET `/api/v1/billing/branding/me`
- ✓ GET `/api/v1/billing/licenses/me`
- ✓ GET `/api/v1/billing/orders/me`
- ✓ GET `/api/v1/billing/plans`
- ✓ GET `/api/v1/billing/plugins`
- ✓ GET `/api/v1/billing/subscription/me`
- ✓ GET `/api/v1/blacklist`
- ✓ GET `/api/v1/command/instructions`
- ✓ GET `/api/v1/command/sessions`
- ✓ GET `/api/v1/config-center/basic`
- ✓ GET `/api/v1/config-center/drafts/current`
- ✓ GET `/api/v1/demo/status`
- ✓ GET `/api/v1/devices`
- ✓ GET `/api/v1/devices/channels/flat`
- ✓ GET `/api/v1/devices/directories/next-gb-id`
- ✓ GET `/api/v1/devices/tree`
- ✓ GET `/api/v1/devices/tree/business`
- ✓ GET `/api/v1/health/capacity-baseline`
- ✓ GET `/api/v1/health/capacity-threshold-template`
- ✓ GET `/api/v1/health/devices`
- ✓ GET `/api/v1/health/overview`
- ✓ GET `/api/v1/health/report/daily`
- ✓ GET `/api/v1/health/tuning-recommendations`
- ✓ GET `/api/v1/integrations/ffmpeg_cmd/list`
- ✓ GET `/api/v1/integrations/media-nodes`
- ✓ GET `/api/v1/integrations/media-nodes/export/env`
- ✓ GET `/api/v1/integrations/media-nodes/export/media-nodes-json`
- ✓ GET `/api/v1/integrations/media-nodes/leases`
- ✓ GET `/api/v1/integrations/media-nodes/offline-threshold`
- ✓ GET `/api/v1/integrations/media-nodes/port-pool-status`
- ✓ GET `/api/v1/integrations/sources`
- ✓ GET `/api/v1/login/verify-token`
- ✓ GET `/api/v1/logs/files`
- ✓ GET `/api/v1/map`
- ✓ GET `/api/v1/map/command-config`
- ✓ GET `/api/v1/map/device-latest-position`
- ✓ GET `/api/v1/map/devices-latest-positions`
- ✓ GET `/api/v1/map/providers`
- ✓ GET `/api/v1/map/trajectory`
- ✓ GET `/api/v1/media/info`
- ✓ GET `/api/v1/metrics/devices-overview`
- ✓ GET `/api/v1/network/bandwidth`
- ✓ GET `/api/v1/network/summary`
- ✓ GET `/api/v1/network/topology`
- ✓ GET `/api/v1/ops/active-streams`
- ✓ GET `/api/v1/ops/backup/list`
- ✓ GET `/api/v1/ops/db-check`
- ✓ GET `/api/v1/ops/db-compat-report`
- ✓ GET `/api/v1/ops/diagnose-report`
- ✓ GET `/api/v1/ops/diagnostics/export`
- ✓ GET `/api/v1/ops/help-docs`
- ✓ GET `/api/v1/ops/status`
- ✓ GET `/api/v1/ops/stream-diagnose`
- ✓ GET `/api/v1/organizations`
- ✓ GET `/api/v1/platforms`
- ✓ GET `/api/v1/platforms/channels/flat`
- ✓ GET `/api/v1/platforms/inbound/diagnosis`
- ✓ GET `/api/v1/plugins/app-version-check`
- ✓ GET `/api/v1/plugins/installed`
- ✓ GET `/api/v1/plugins/marketplace`
- ✓ GET `/api/v1/plugins/marketplace-shop-url`
- ✓ GET `/api/v1/plugins/menus`
- ✓ GET `/api/v1/plugins/mobile-entries`
- ✓ GET `/api/v1/plugins/purchased`
- ✓ GET `/api/v1/plugins/runtime/auto_record/events`
- ✓ GET `/api/v1/plugins/runtime/feishu_alert/events`
- ✓ GET `/api/v1/plugins/runtime/health-status`
- ✓ GET `/api/v1/plugins/runtime/mqtt_bridge/events`
- ✓ GET `/api/v1/plugins/runtime/network_watchdog/events`
- ✓ GET `/api/v1/plugins/runtime/ptz_tour/events`
- ✓ GET `/api/v1/plugins/runtime/pull_proxy_monitor/events`
- ✓ GET `/api/v1/plugins/runtime/record_index_verifier/events`
- ✓ GET `/api/v1/plugins/runtime/record_schedule_executor/events`
- ✓ GET `/api/v1/plugins/runtime/rtmp_push_channel_monitor/events`
- ✓ GET `/api/v1/plugins/runtime/s3_sync/events`
- ✓ GET `/api/v1/plugins/runtime/security-report`
- ✓ GET `/api/v1/plugins/runtime/sip_logger/logs`
- ✓ GET `/api/v1/plugins/runtime/sms_alert/events`
- ✓ GET `/api/v1/plugins/runtime/snapshot_refresh/events`
- ✓ GET `/api/v1/plugins/runtime/stream_health/health`
- ✓ GET `/api/v1/plugins/runtime/stream_idle/events`
- ✓ GET `/api/v1/plugins/runtime/timelapse/events`
- ✓ GET `/api/v1/plugins/runtime/webhook_pusher/events`
- ✓ GET `/api/v1/plugins/runtime/wecom_alert/events`
- ✓ GET `/api/v1/push-channels`
- ✓ GET `/api/v1/record-schedule`
- ✓ GET `/api/v1/record-schedule/runtimes`
- ✓ GET `/api/v1/record-schedule/storage-config`
- ✓ GET `/api/v1/record-schedule/storage-nodes`
- ✓ GET `/api/v1/record/query`
- ✓ GET `/api/v1/record/search`
- ✓ GET `/api/v1/regions/tree`
- ✓ GET `/api/v1/reports/data/alarms`
- ✓ GET `/api/v1/reports/data/stream-quality`
- ✓ GET `/api/v1/reports/data/traffic`
- ✓ GET `/api/v1/reports/export`
- ✓ GET `/api/v1/reports/export.pdf`
- ✓ GET `/api/v1/reports/list`
- ✓ GET `/api/v1/reports/mobile-regression/closeout-governance-dashboard/drilldown`
- ✓ GET `/api/v1/reports/mobile-regression/closeout-governance-dashboard/summary`
- ✓ GET `/api/v1/reports/report-suite/config`
- ✓ GET `/api/v1/reports/summary`
- ✓ GET `/api/v1/roles`
- ✓ GET `/api/v1/setup/status`
- ✓ GET `/api/v1/ssl-cert/status`
- ✓ GET `/api/v1/stream-opt/optimization-tips`
- ✓ GET `/api/v1/stream-opt/protocol-info`
- ✓ GET `/api/v1/stream-opt/stats`
- ✓ GET `/api/v1/stream/list`
- ✓ GET `/api/v1/structured/search`
- ✓ GET `/api/v1/system-config/database`
- ✓ GET `/api/v1/system-config/gb28181/learning-state`
- ✓ GET `/api/v1/system-config/gb28181/play-config`
- ✓ GET `/api/v1/system-config/info`
- ✓ GET `/api/v1/system-config/system-info`
- ✓ GET `/api/v1/trace-events`
- ✓ GET `/api/v1/user-api-keys/me`
- ✓ GET `/api/v1/users`
- ✓ GET `/api/v1/users/me`
- ✓ GET `/api/v1/work-orders`
- ✓ POST `/api/common/channel/add`
- ✓ POST `/api/common/channel/civilCode/unusual/clear`
- ✓ POST `/api/common/channel/group/add`
- ✓ POST `/api/common/channel/group/delete`
- ✓ POST `/api/common/channel/group/device/add`
- ✓ POST `/api/common/channel/group/device/delete`
- ✓ POST `/api/common/channel/parent/unusual/clear`
- ✓ POST `/api/common/channel/play/stop`
- ✓ POST `/api/common/channel/region/add`
- ✓ POST `/api/common/channel/region/delete`
- ✓ POST `/api/common/channel/region/device/add`
- ✓ POST `/api/common/channel/region/device/delete`
- ✓ POST `/api/common/channel/reset`
- ✓ POST `/api/v1/alarms/link-rules`
- ✓ POST `/api/v1/asset-management/maintenances`
- ✓ POST `/api/v1/auth/ws-ticket`
- ✓ POST `/api/v1/billing/orders`
- ✓ POST `/api/v1/billing/payment/callback`
- ✓ POST `/api/v1/command/instructions`
- ✓ POST `/api/v1/command/sessions`
- ✓ POST `/api/v1/device-record/device/queries`
- ✓ POST `/api/v1/device-record/download/start`
- ✓ POST `/api/v1/devices`
- ✓ POST `/api/v1/devices/batch-delete`
- ✓ POST `/api/v1/devices/channels/batch-placement`
- ✓ POST `/api/v1/devices/channels/batch-update-civil-code`
- ✓ POST `/api/v1/devices/channels/snap-batch`
- ✓ POST `/api/v1/devices/directories`
- ✓ POST `/api/v1/devices/export`
- ✓ POST `/api/v1/health/apply-recommendations`
- ✓ POST `/api/v1/integrations/ffmpeg_cmd`
- ✓ POST `/api/v1/integrations/media-nodes`
- ✓ POST `/api/v1/integrations/media-nodes/leases/cleanup`
- ✓ POST `/api/v1/integrations/media-nodes/test-all`
- ✓ POST `/api/v1/integrations/sources`
- ✓ POST `/api/v1/login/access-token`
- ✓ POST `/api/v1/login/logout`
- ✓ POST `/api/v1/map`
- ✓ POST `/api/v1/map/mobile-position/subscribe`
- ✓ POST `/api/v1/map/providers`
- ✓ POST `/api/v1/map/trajectory`
- ✓ POST `/api/v1/ops/backup`
- ✓ POST `/api/v1/ops/restore`
- ✓ POST `/api/v1/ops/shutdown`
- ✓ POST `/api/v1/organizations`
- ✓ POST `/api/v1/platforms`
- ✓ POST `/api/v1/plugins/alert-test`
- ✓ POST `/api/v1/plugins/marketplace/install`
- ✓ POST `/api/v1/plugins/upload`
- ✓ POST `/api/v1/proxy/save`
- ✓ POST `/api/v1/proxy/start`
- ✓ POST `/api/v1/proxy/stop`
- ✓ POST `/api/v1/push-channels`
- ✓ POST `/api/v1/push-channels/batch`
- ✓ POST `/api/v1/push-channels/import`
- ✓ POST `/api/v1/record-schedule`
- ✓ POST `/api/v1/record/delete-batch`
- ✓ POST `/api/v1/record/repair-url-batch`
- ✓ POST `/api/v1/record/verify-batch`
- ✓ POST `/api/v1/regions`
- ✓ POST `/api/v1/register`
- ✓ POST `/api/v1/release-center/publish`
- ✓ POST `/api/v1/release-center/rollback`
- ✓ POST `/api/v1/reports/report-suite/connector-test`
- ✓ POST `/api/v1/roles`
- ✓ POST `/api/v1/rtp/receive/open`
- ✓ POST `/api/v1/setup/complete`
- ✓ POST `/api/v1/ssl-cert/renew`
- ✓ POST `/api/v1/stream-opt/quality-report`
- ✓ POST `/api/v1/stream/play_status`
- ✓ POST `/api/v1/stream/stop`
- ✓ POST `/api/v1/system-config/database/test`
- ✓ POST `/api/v1/user-api-keys`
- ✓ POST `/api/v1/users`
- ✓ POST `/api/v1/users/me/2fa/disable`
- ✓ POST `/api/v1/users/me/2fa/enable`
- ✓ POST `/api/v1/users/me/2fa/setup`
- ✓ POST `/api/v1/users/me/change-password`
- ✓ POST `/api/v1/work-orders`
- ✓ PUT `/api/v1/alarms/config`
- ✓ PUT `/api/v1/alarms/sla/presets`
- ✓ PUT `/api/v1/billing/branding/me`
- ✓ PUT `/api/v1/config-center/basic`
- ✓ PUT `/api/v1/devices/directories`
- ✓ PUT `/api/v1/integrations/media-nodes/offline-threshold`
- ✓ PUT `/api/v1/record-schedule/storage-config`
- ✓ PUT `/api/v1/record-schedule/storage-nodes`
- ✓ PUT `/api/v1/reports/report-suite/config`
- ✓ PUT `/api/v1/system-config/database`
- ✓ PUT `/api/v1/system-config/gb28181/play-config`
- ✓ PUT `/api/v1/users/me`
