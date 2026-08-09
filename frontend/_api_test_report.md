# 前端 API 端点验证报告

- 总测试数: 318
- ✓ 通过: 226
- ✗ 失败: 78
- ⊙ 跳过: 14

## 失败的端点

| 方法 | 路径 | 状态码 | 结论 | 文件 |
|------|------|--------|------|------|
| POST | `/api/v1/alarms/1` | 404 | FAIL: 端点不存在 | views\AlarmCenter.vue, views\SlaDashboard.vue |
| DELETE | `/api/v1/alarms/link-rules/1` | 404 | FAIL: 端点不存在 | views\AlarmLinkRules.vue |
| DELETE | `/api/v1/asset-management/maintenances/1` | 404 | FAIL: 端点不存在 | views\AssetManagement.vue |
| PUT | `/api/v1/asset-management/maintenances/1` | 404 | FAIL: 端点不存在 | views\AssetManagement.vue |
| GET | `/api/v1/command/sessions/1` | 404 | FAIL: 端点不存在 | views\MobileCommand.vue |
| POST | `/api/v1/command/sessions/1` | 404 | FAIL: 端点不存在 | views\MobileCommand.vue |
| POST | `/api/v1/config-center/drafts/1` | 404 | FAIL: 端点不存在 | api\configCenter.ts |
| PUT | `/api/v1/config-center/drafts/1` | 404 | FAIL: 端点不存在 | api\configCenter.ts |
| GET | `/api/v1/config-center/drafts/current` | 500 | FAIL: 服务器错误 | api\configCenter.ts |
| GET | `/api/v1/control/1` | 404 | FAIL: 端点不存在 | components\AdvancedPtzControl.vue, components\PtzPanel.vue |
| POST | `/api/v1/control/1` | 404 | FAIL: 端点不存在 | components\AdvancedPtzControl.vue, components\PtzPanel.vue |
| GET | `/api/v1/device-record/device/queries/1` | 404 | FAIL: 端点不存在 | components\RecordTimeline.vue |
| GET | `/api/v1/device-record/download/progress/1` | 404 | FAIL: 端点不存在 | components\RecordTimeline.vue |
| POST | `/api/v1/device-record/download/stop/1` | 404 | FAIL: 端点不存在 | components\RecordTimeline.vue |
| DELETE | `/api/v1/devices/1` | 404 | FAIL: 端点不存在 | api\index.ts, components\device\DeviceBlacklistDialog.vue |
| PUT | `/api/v1/devices/1` | 404 | FAIL: 端点不存在 | api\index.ts, components\device\DeviceBlacklistDialog.vue |
| DELETE | `/api/v1/devices/channels/1` | 404 | FAIL: 端点不存在 | api\index.ts, components\channel\ChannelEditDialog.vue |
| PUT | `/api/v1/devices/channels/1` | 404 | FAIL: 端点不存在 | api\index.ts, components\channel\ChannelEditDialog.vue |
| DELETE | `/api/v1/devices/directories` | 404 | FAIL: 端点不存在 | components\channel\CreateDirectoryDialog.vue, components\channel\RenameDirectoryDialog.vue |
| PUT | `/api/v1/devices/directories` | 404 | FAIL: 端点不存在 | components\channel\CreateDirectoryDialog.vue, components\channel\RenameDirectoryDialog.vue |
| POST | `/api/v1/devices/export` | 404 | FAIL: 端点不存在 | views\device-list\DeviceBatchOps.vue |
| GET | `/api/v1/gb-record/download/progress/1` | 404 | FAIL: 端点不存在 | components\DeviceRecordList.vue |
| GET | `/api/v1/gb-record/download/start/1` | 404 | FAIL: 端点不存在 | components\DeviceRecordList.vue |
| GET | `/api/v1/gb-record/download/stop/1` | 404 | FAIL: 端点不存在 | components\DeviceRecordList.vue |
| GET | `/api/v1/gb-record/query/1` | 404 | FAIL: 端点不存在 | components\DeviceRecordList.vue |
| DELETE | `/api/v1/integrations/ffmpeg_cmd/1` | 404 | FAIL: 端点不存在 | views\Operations.vue |
| DELETE | `/api/v1/integrations/media-nodes/1` | 404 | FAIL: 端点不存在 | views\Operations.vue |
| GET | `/api/v1/integrations/media-nodes/leases` | 500 | FAIL: 服务器错误 | views\Operations.vue |
| DELETE | `/api/v1/integrations/sources/1` | 404 | FAIL: 端点不存在 | views\ConfigCenter.vue, views\MonitorCenter.vue |
| DELETE | `/api/v1/map/providers/1` | 404 | FAIL: 端点不存在 | views\MapProviders.vue |
| PUT | `/api/v1/map/providers/1` | 404 | FAIL: 端点不存在 | views\MapProviders.vue |
| GET | `/api/v1/ops/active-streams` | 502 | FAIL: 服务器错误 | views\Operations.vue |
| POST | `/api/v1/ops/backup` | 500 | FAIL: 服务器错误 | views\Operations.vue |
| DELETE | `/api/v1/organizations/1` | 404 | FAIL: 端点不存在 | api\organizations.ts |
| PUT | `/api/v1/organizations/1` | 404 | FAIL: 端点不存在 | api\organizations.ts |
| DELETE | `/api/v1/platforms/1` | 404 | FAIL: 端点不存在 | views\CascadePlatforms.vue |
| PUT | `/api/v1/platforms/1` | 404 | FAIL: 端点不存在 | views\CascadePlatforms.vue |
| POST | `/api/v1/plugins/marketplace/purchase` | 404 | FAIL: 端点不存在 | views\PluginCenter.vue |
| POST | `/api/v1/plugins/marketplace/purchase/confirm` | 404 | FAIL: 端点不存在 | views\PluginCenter.vue |
| GET | `/api/v1/plugins/runtime/1` | 404 | FAIL: 端点不存在 | components\plugin\PluginPanels.vue, views\BehaviorRecognitionMobile.vue |
| PUT | `/api/v1/plugins/runtime/1` | 404 | FAIL: 端点不存在 | components\plugin\PluginPanels.vue, views\BehaviorRecognitionMobile.vue |
| GET | `/api/v1/plugins/runtime/stream_health/health` | 500 | FAIL: 服务器错误 | components\plugin\PluginPanels.vue, views\PluginRuntime.vue |
| DELETE | `/api/v1/proxy/delete?id=/1` | 404 | FAIL: 端点不存在 | views\PullProxyList.vue |
| DELETE | `/api/v1/push-channels/1` | 404 | FAIL: 端点不存在 | views\PushStreamList.vue |
| PUT | `/api/v1/push-channels/1` | 404 | FAIL: 端点不存在 | views\PushStreamList.vue |
| DELETE | `/api/v1/record-schedule/1` | 404 | FAIL: 端点不存在 | views\RecordSchedule.vue |
| PUT | `/api/v1/record-schedule/1` | 404 | FAIL: 端点不存在 | views\RecordSchedule.vue |
| PUT | `/api/v1/record-schedule/storage-config` | 404 | FAIL: 端点不存在 | views\ConfigCenter.vue |
| PUT | `/api/v1/record-schedule/storage-nodes` | 404 | FAIL: 端点不存在 | views\ConfigCenter.vue |
| DELETE | `/api/v1/record/1` | 404 | FAIL: 端点不存在 | views\CloudRecords.vue |
| GET | `/api/v1/record/download/sign/1` | 404 | FAIL: 端点不存在 | components\EnhancedCloudRecordList.vue, views\CloudRecords.vue |
| GET | `/api/v1/record/play-url/1` | 404 | FAIL: 端点不存在 | components\EnhancedCloudRecordList.vue, components\RecordList.vue |
| POST | `/api/v1/record/repair-url/1` | 404 | FAIL: 端点不存在 | views\CloudRecords.vue |
| POST | `/api/v1/record/verify/1` | 404 | FAIL: 端点不存在 | components\EnhancedCloudRecordList.vue, views\CloudRecords.vue |
| DELETE | `/api/v1/regions/1` | 404 | FAIL: 端点不存在 | views\ChannelRegion.vue |
| PUT | `/api/v1/regions/1` | 404 | FAIL: 端点不存在 | views\ChannelRegion.vue |
| GET | `/api/v1/release-center/drafts/1` | 404 | FAIL: 端点不存在 | api\releaseCenter.ts |
| GET | `/api/v1/reports/list` | 500 | FAIL: 服务器错误 | views\ReportCenter.vue |
| GET | `/api/v1/reports/report-suite/config` | 500 | FAIL: 服务器错误 | views\ReportCenter.vue |
| PUT | `/api/v1/reports/report-suite/config` | 500 | FAIL: 服务器错误 | views\ReportCenter.vue |
| POST | `/api/v1/reports/report-suite/connector-test` | 500 | FAIL: 服务器错误 | views\ReportCenter.vue |
| DELETE | `/api/v1/roles/1` | 404 | FAIL: 端点不存在 | views\RoleManager.vue |
| POST | `/api/v1/rtp/receive/close/1` | 404 | FAIL: 端点不存在 | views\Operations.vue |
| GET | `/api/v1/stream-opt/health/1` | 404 | FAIL: 端点不存在 | api\index.ts |
| GET | `/api/v1/stream-opt/lines/1` | 404 | FAIL: 端点不存在 | api\index.ts |
| GET | `/api/v1/stream-opt/play/1` | 404 | FAIL: 端点不存在 | api\index.ts |
| POST | `/api/v1/stream/play/1` | 404 | FAIL: 端点不存在 | views\ChannelManager.vue, views\GisMap.vue |
| GET | `/api/v1/stream/play_status/1` | 503 | FAIL: 服务器错误 | views\MonitorCenter.vue, views\channel-manager\usePlayer.ts |
| POST | `/api/v1/stream/playback/1` | 404 | FAIL: 端点不存在 | components\DeviceRecordList.vue, components\RecordTimeline.vue |
| POST | `/api/v1/user-api-keys/1` | 404 | FAIL: 端点不存在 | views\ApiKeyManager.vue |
| DELETE | `/api/v1/users/1` | 404 | FAIL: 端点不存在 | views\UserManager.vue |
| PUT | `/api/v1/users/1` | 404 | FAIL: 端点不存在 | views\UserManager.vue |
| PUT | `/api/v1/users/me` | 404 | FAIL: 端点不存在 | views\AccountSecurity.vue, views\ProfileCenter.vue |
| POST | `/api/v1/users/me/2fa/setup` | 500 | FAIL: 服务器错误 | views\AccountSecurity.vue |
| GET | `/api/v1/vod/vod/optimized-url/1` | 404 | FAIL: 端点不存在 | views\CloudRecords.vue |
| GET | `/api/v1/vod/vod/sources/1` | 404 | FAIL: 端点不存在 | views\CloudRecords.vue |
| DELETE | `/api/v1/work-orders/1` | 404 | FAIL: 端点不存在 | views\WorkOrders.vue |
| PUT | `/api/v1/work-orders/1` | 404 | FAIL: 端点不存在 | views\WorkOrders.vue |

## 全部测试结果

| 方法 | 路径 | 状态码 | 结论 |
|------|------|--------|------|
| POST | `/api/common/channel/add` | 422 | PASS (参数校验) |
| POST | `/api/common/channel/civilCode/unusual/clear` | 200 | PASS |
| POST | `/api/common/channel/group/add` | 422 | PASS (参数校验) |
| POST | `/api/common/channel/group/delete` | 400 | PASS (参数校验) |
| POST | `/api/common/channel/group/device/add` | 422 | PASS (参数校验) |
| POST | `/api/common/channel/group/device/delete` | 400 | PASS (参数校验) |
| GET | `/api/common/channel/list` | 200 | PASS |
| POST | `/api/common/channel/parent/unusual/clear` | 200 | PASS |
| POST | `/api/common/channel/play/stop` | 400 | PASS (参数校验) |
| POST | `/api/common/channel/region/add` | 422 | PASS (参数校验) |
| POST | `/api/common/channel/region/delete` | 400 | PASS (参数校验) |
| POST | `/api/common/channel/region/device/add` | 422 | PASS (参数校验) |
| POST | `/api/common/channel/region/device/delete` | 400 | PASS (参数校验) |
| POST | `/api/common/channel/reset` | 422 | PASS (参数校验) |
| GET | `/api/common/channel/stream-status` | 422 | PASS (参数校验) |
| GET | `/api/v1/alarms` | 200 | PASS |
| POST | `/api/v1/alarms/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/alarms/config` | 200 | PASS |
| PUT | `/api/v1/alarms/config` | 200 | PASS |
| GET | `/api/v1/alarms/link-rules` | 200 | PASS |
| POST | `/api/v1/alarms/link-rules` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/alarms/link-rules/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/alarms/link-rules/1` | 422 | PASS (参数校验) |
| GET | `/api/v1/alarms/notifications` | 200 | PASS |
| GET | `/api/v1/alarms/sla/compare` | 200 | PASS |
| GET | `/api/v1/alarms/sla/overview` | 200 | PASS |
| GET | `/api/v1/alarms/sla/presets` | 200 | PASS |
| PUT | `/api/v1/alarms/sla/presets` | 422 | PASS (参数校验) |
| GET | `/api/v1/alarms/sla/quality` | 200 | PASS |
| GET | `/api/v1/alarms/unread-count` | 200 | PASS |
| GET | `/api/v1/alarms?limit=50` | 200 | PASS |
| GET | `/api/v1/apps/logs` | 200 | PASS |
| GET | `/api/v1/apps/remote-config` | 422 | PASS (参数校验) |
| GET | `/api/v1/apps/stats` | 200 | PASS |
| GET | `/api/v1/asset-management/ledger` | 200 | PASS |
| GET | `/api/v1/asset-management/maintenances` | 200 | PASS |
| POST | `/api/v1/asset-management/maintenances` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/asset-management/maintenances/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/asset-management/maintenances/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/audit-center/export.csv` | 200 | PASS |
| GET | `/api/v1/audit-center/logs` | 200 | PASS |
| GET | `/api/v1/audit-center/stats` | 200 | PASS |
| POST | `/api/v1/auth/ws-ticket` | 200 | PASS |
| GET | `/api/v1/billing/branding/me` | 200 | PASS |
| PUT | `/api/v1/billing/branding/me` | 200 | PASS |
| GET | `/api/v1/billing/licenses/me` | 200 | PASS |
| POST | `/api/v1/billing/orders` | 403 | PASS (需要权限) |
| GET | `/api/v1/billing/orders/me` | 403 | PASS (需要权限) |
| POST | `/api/v1/billing/payment/callback` | 403 | PASS (需要权限) |
| GET | `/api/v1/billing/plans` | 200 | PASS |
| GET | `/api/v1/billing/plugins` | 403 | PASS (需要权限) |
| GET | `/api/v1/billing/subscription/me` | 200 | PASS |
| GET | `/api/v1/blacklist` | 200 | PASS |
| DELETE | `/api/v1/blacklist/1` | 200 | PASS |
| GET | `/api/v1/command/instructions` | 422 | PASS (参数校验) |
| POST | `/api/v1/command/instructions` | 422 | PASS (参数校验) |
| GET | `/api/v1/command/sessions` | 200 | PASS |
| POST | `/api/v1/command/sessions` | 200 | PASS |
| GET | `/api/v1/command/sessions/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/command/sessions/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/config-center/basic` | 200 | PASS |
| PUT | `/api/v1/config-center/basic` | 200 | PASS |
| POST | `/api/v1/config-center/drafts/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/config-center/drafts/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/config-center/drafts/current` | 500 | FAIL: 服务器错误 |
| GET | `/api/v1/control/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/control/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/demo/status` | 200 | PASS |
| POST | `/api/v1/device-record/device/queries` | 422 | PASS (参数校验) |
| GET | `/api/v1/device-record/device/queries/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/device-record/download/progress/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/device-record/download/start` | 422 | PASS (参数校验) |
| POST | `/api/v1/device-record/download/stop/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/devices` | 200 | PASS |
| POST | `/api/v1/devices` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/devices/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/devices/1` | 405 | SKIP (状态码 405) |
| POST | `/api/v1/devices/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/devices/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/devices/batch-delete` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/devices/channels/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/devices/channels/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/devices/channels/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/devices/channels/batch-placement` | 422 | PASS (参数校验) |
| POST | `/api/v1/devices/channels/batch-update-civil-code` | 422 | PASS (参数校验) |
| GET | `/api/v1/devices/channels/flat` | 200 | PASS |
| POST | `/api/v1/devices/channels/snap-batch` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/devices/directories` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/devices/directories` | 400 | PASS (参数校验) |
| PUT | `/api/v1/devices/directories` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/devices/directories/next-gb-id` | 200 | PASS |
| POST | `/api/v1/devices/export` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/devices/tree` | 200 | PASS |
| GET | `/api/v1/devices/tree/business` | 200 | PASS |
| GET | `/api/v1/gb-record/download/progress/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/gb-record/download/start/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/gb-record/download/stop/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/gb-record/query/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/health/apply-recommendations` | 200 | PASS |
| GET | `/api/v1/health/capacity-baseline` | 200 | PASS |
| GET | `/api/v1/health/capacity-threshold-template` | 200 | PASS |
| GET | `/api/v1/health/devices` | 200 | PASS |
| GET | `/api/v1/health/overview` | 200 | PASS |
| GET | `/api/v1/health/report/daily` | 200 | PASS |
| GET | `/api/v1/health/tuning-recommendations` | 200 | PASS |
| POST | `/api/v1/integrations/ffmpeg_cmd` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/integrations/ffmpeg_cmd/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/integrations/ffmpeg_cmd/1` | 422 | PASS (参数校验) |
| GET | `/api/v1/integrations/ffmpeg_cmd/list` | 200 | PASS |
| GET | `/api/v1/integrations/media-nodes` | 200 | PASS |
| POST | `/api/v1/integrations/media-nodes` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/integrations/media-nodes/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/integrations/media-nodes/1` | 405 | SKIP (状态码 405) |
| POST | `/api/v1/integrations/media-nodes/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/integrations/media-nodes/1` | 422 | PASS (参数校验) |
| GET | `/api/v1/integrations/media-nodes/export/env` | 200 | PASS |
| GET | `/api/v1/integrations/media-nodes/export/media-nodes-json` | 200 | PASS |
| GET | `/api/v1/integrations/media-nodes/leases` | 500 | FAIL: 服务器错误 |
| POST | `/api/v1/integrations/media-nodes/leases/cleanup` | 200 | PASS |
| GET | `/api/v1/integrations/media-nodes/offline-threshold` | 200 | PASS |
| PUT | `/api/v1/integrations/media-nodes/offline-threshold` | 422 | PASS (参数校验) |
| GET | `/api/v1/integrations/media-nodes/port-pool-status` | 200 | PASS |
| POST | `/api/v1/integrations/media-nodes/test-all` | 200 | PASS |
| GET | `/api/v1/integrations/sources` | 200 | PASS |
| POST | `/api/v1/integrations/sources` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/integrations/sources/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/integrations/sources/1` | 405 | SKIP (状态码 405) |
| POST | `/api/v1/integrations/sources/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/integrations/sources/1` | 422 | PASS (参数校验) |
| POST | `/api/v1/login/access-token` | 422 | PASS (参数校验) |
| POST | `/api/v1/login/logout` | 200 | PASS |
| GET | `/api/v1/login/verify-token` | 200 | PASS |
| GET | `/api/v1/logs/files` | 200 | PASS |
| GET | `/api/v1/map` | 200 | PASS |
| POST | `/api/v1/map` | 422 | PASS (参数校验) |
| GET | `/api/v1/map/command-config` | 200 | PASS |
| GET | `/api/v1/map/device-latest-position` | 422 | PASS (参数校验) |
| GET | `/api/v1/map/devices-latest-positions` | 200 | PASS |
| POST | `/api/v1/map/mobile-position/subscribe` | 422 | PASS (参数校验) |
| GET | `/api/v1/map/providers` | 200 | PASS |
| POST | `/api/v1/map/providers` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/map/providers/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/map/providers/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/map/providers/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/map/trajectory` | 422 | PASS (参数校验) |
| POST | `/api/v1/map/trajectory` | 422 | PASS (参数校验) |
| GET | `/api/v1/media/info` | 422 | PASS (参数校验) |
| GET | `/api/v1/metrics/devices-overview` | 200 | PASS |
| GET | `/api/v1/network/bandwidth` | 200 | PASS |
| GET | `/api/v1/network/summary` | 200 | PASS |
| GET | `/api/v1/network/topology` | 200 | PASS |
| GET | `/api/v1/ops/active-streams` | 502 | FAIL: 服务器错误 |
| POST | `/api/v1/ops/backup` | 500 | FAIL: 服务器错误 |
| GET | `/api/v1/ops/backup/list` | 200 | PASS |
| GET | `/api/v1/ops/db-check` | 200 | PASS |
| GET | `/api/v1/ops/db-compat-report` | 200 | PASS |
| GET | `/api/v1/ops/diagnose-report` | 200 | PASS |
| GET | `/api/v1/ops/diagnostics/export` | 200 | PASS |
| GET | `/api/v1/ops/help-docs` | 200 | PASS |
| POST | `/api/v1/ops/restore` | 422 | PASS (参数校验) |
| POST | `/api/v1/ops/shutdown` | 403 | PASS (需要权限) |
| GET | `/api/v1/ops/status` | 200 | PASS |
| GET | `/api/v1/ops/stream-diagnose` | 200 | PASS |
| GET | `/api/v1/organizations` | 200 | PASS |
| POST | `/api/v1/organizations` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/organizations/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/organizations/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/platforms` | 200 | PASS |
| POST | `/api/v1/platforms` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/platforms/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/platforms/1` | 405 | SKIP (状态码 405) |
| POST | `/api/v1/platforms/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/platforms/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/platforms/channels/flat` | 200 | PASS |
| GET | `/api/v1/platforms/inbound/diagnosis` | 200 | PASS |
| DELETE | `/api/v1/plugins/1` | 400 | PASS (参数校验) |
| GET | `/api/v1/plugins/1` | 405 | SKIP (状态码 405) |
| POST | `/api/v1/plugins/alert-test` | 200 | PASS |
| GET | `/api/v1/plugins/app-version-check` | 422 | PASS (参数校验) |
| GET | `/api/v1/plugins/installed` | 200 | PASS |
| GET | `/api/v1/plugins/marketplace` | 200 | PASS |
| GET | `/api/v1/plugins/marketplace-shop-url` | 200 | PASS |
| POST | `/api/v1/plugins/marketplace/install` | 422 | PASS (参数校验) |
| POST | `/api/v1/plugins/marketplace/purchase` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/plugins/marketplace/purchase/confirm` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/plugins/menus` | 200 | PASS |
| GET | `/api/v1/plugins/mobile-entries` | 200 | PASS |
| GET | `/api/v1/plugins/purchased` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/plugins/runtime/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/plugins/runtime/auto_record/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/feishu_alert/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/health-status` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/mqtt_bridge/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/network_watchdog/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/ptz_tour/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/pull_proxy_monitor/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/record_index_verifier/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/record_schedule_executor/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/rtmp_push_channel_monitor/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/s3_sync/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/security-report` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/sip_logger/logs` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/sms_alert/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/snapshot_refresh/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/stream_health/health` | 500 | FAIL: 服务器错误 |
| GET | `/api/v1/plugins/runtime/stream_idle/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/timelapse/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/webhook_pusher/events` | 200 | PASS |
| GET | `/api/v1/plugins/runtime/wecom_alert/events` | 200 | PASS |
| POST | `/api/v1/plugins/upload` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/proxy/delete?id=/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/proxy/save` | 200 | PASS |
| POST | `/api/v1/proxy/start` | 422 | PASS (参数校验) |
| POST | `/api/v1/proxy/stop` | 422 | PASS (参数校验) |
| GET | `/api/v1/push-channels` | 200 | PASS |
| POST | `/api/v1/push-channels` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/push-channels/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/push-channels/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/push-channels/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/push-channels/batch` | 422 | PASS (参数校验) |
| POST | `/api/v1/push-channels/import` | 422 | PASS (参数校验) |
| GET | `/api/v1/record-schedule` | 200 | PASS |
| POST | `/api/v1/record-schedule` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/record-schedule/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/record-schedule/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/record-schedule/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/record-schedule/runtimes` | 200 | PASS |
| GET | `/api/v1/record-schedule/storage-config` | 200 | PASS |
| PUT | `/api/v1/record-schedule/storage-config` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/record-schedule/storage-nodes` | 200 | PASS |
| PUT | `/api/v1/record-schedule/storage-nodes` | 404 | FAIL: 端点不存在 |
| DELETE | `/api/v1/record/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/record/delete-batch` | 422 | PASS (参数校验) |
| GET | `/api/v1/record/download/sign/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/record/play-url/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/record/query` | 422 | PASS (参数校验) |
| POST | `/api/v1/record/repair-url-batch` | 422 | PASS (参数校验) |
| POST | `/api/v1/record/repair-url/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/record/search` | 200 | PASS |
| POST | `/api/v1/record/verify-batch` | 422 | PASS (参数校验) |
| POST | `/api/v1/record/verify/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/regions` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/regions/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/regions/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/regions/tree` | 200 | PASS |
| POST | `/api/v1/register` | 422 | PASS (参数校验) |
| GET | `/api/v1/release-center/drafts/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/release-center/publish` | 422 | PASS (参数校验) |
| POST | `/api/v1/release-center/rollback` | 422 | PASS (参数校验) |
| GET | `/api/v1/reports/data/alarms` | 200 | PASS |
| GET | `/api/v1/reports/data/stream-quality` | 200 | PASS |
| GET | `/api/v1/reports/data/traffic` | 200 | PASS |
| GET | `/api/v1/reports/export` | 200 | PASS |
| GET | `/api/v1/reports/export.pdf` | 200 | PASS |
| GET | `/api/v1/reports/list` | 500 | FAIL: 服务器错误 |
| GET | `/api/v1/reports/mobile-regression/closeout-governance-dashboard/drilldown` | 200 | PASS |
| GET | `/api/v1/reports/mobile-regression/closeout-governance-dashboard/summary` | 200 | PASS |
| GET | `/api/v1/reports/report-suite/config` | 500 | FAIL: 服务器错误 |
| PUT | `/api/v1/reports/report-suite/config` | 500 | FAIL: 服务器错误 |
| POST | `/api/v1/reports/report-suite/connector-test` | 500 | FAIL: 服务器错误 |
| GET | `/api/v1/reports/summary` | 200 | PASS |
| GET | `/api/v1/roles` | 200 | PASS |
| POST | `/api/v1/roles` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/roles/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/roles/1` | 422 | PASS (参数校验) |
| POST | `/api/v1/rtp/receive/close/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/rtp/receive/open` | 422 | PASS (参数校验) |
| POST | `/api/v1/setup/complete` | 200 | PASS |
| GET | `/api/v1/setup/status` | 200 | PASS |
| POST | `/api/v1/ssl-cert/renew` | 200 | PASS |
| GET | `/api/v1/ssl-cert/status` | 200 | PASS |
| GET | `/api/v1/stream-opt/health/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/stream-opt/lines/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/stream-opt/optimization-tips` | 200 | PASS |
| GET | `/api/v1/stream-opt/play/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/stream-opt/protocol-info` | 200 | PASS |
| POST | `/api/v1/stream-opt/quality-report` | 422 | PASS (参数校验) |
| POST | `/api/v1/stream-opt/reconnect/1` | 200 | PASS |
| DELETE | `/api/v1/stream-opt/session/1` | 200 | PASS |
| GET | `/api/v1/stream-opt/stats` | 200 | PASS |
| GET | `/api/v1/stream/list` | 200 | PASS |
| POST | `/api/v1/stream/play/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/stream/play_status` | 422 | PASS (参数校验) |
| GET | `/api/v1/stream/play_status/1` | 503 | FAIL: 服务器错误 |
| POST | `/api/v1/stream/playback/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/stream/stop` | 400 | PASS (参数校验) |
| GET | `/api/v1/structured/search` | 200 | PASS |
| GET | `/api/v1/system-config/database` | 200 | PASS |
| PUT | `/api/v1/system-config/database` | 422 | PASS (参数校验) |
| POST | `/api/v1/system-config/database/test` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/system-config/gb28181/learning-state` | 200 | PASS |
| GET | `/api/v1/system-config/gb28181/learning-state` | 200 | PASS |
| GET | `/api/v1/system-config/gb28181/play-config` | 200 | PASS |
| PUT | `/api/v1/system-config/gb28181/play-config` | 200 | PASS |
| GET | `/api/v1/system-config/info` | 200 | PASS |
| GET | `/api/v1/system-config/system-info` | 200 | PASS |
| GET | `/api/v1/trace-events` | 200 | PASS |
| POST | `/api/v1/user-api-keys` | 422 | PASS (参数校验) |
| POST | `/api/v1/user-api-keys/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/user-api-keys/me` | 200 | PASS |
| GET | `/api/v1/users` | 200 | PASS |
| POST | `/api/v1/users` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/users/1` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/users/1` | 405 | SKIP (状态码 405) |
| PUT | `/api/v1/users/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/users/me` | 200 | PASS |
| PUT | `/api/v1/users/me` | 404 | FAIL: 端点不存在 |
| POST | `/api/v1/users/me/2fa/disable` | 422 | PASS (参数校验) |
| POST | `/api/v1/users/me/2fa/enable` | 422 | PASS (参数校验) |
| POST | `/api/v1/users/me/2fa/setup` | 500 | FAIL: 服务器错误 |
| POST | `/api/v1/users/me/change-password` | 422 | PASS (参数校验) |
| GET | `/api/v1/vod/vod/optimized-url/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/vod/vod/sources/1` | 404 | FAIL: 端点不存在 |
| GET | `/api/v1/work-orders` | 200 | PASS |
| POST | `/api/v1/work-orders` | 422 | PASS (参数校验) |
| DELETE | `/api/v1/work-orders/1` | 404 | FAIL: 端点不存在 |
| PUT | `/api/v1/work-orders/1` | 404 | FAIL: 端点不存在 |
