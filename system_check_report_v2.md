# PyGBSentry 系统全面检查报告

| 属性 | 值 |
|------|----|
| 生成时间 | 2026-07-02T15:54:14.076236 |
| 项目根目录 | E:\硕腾网络\PyGBSentry\PyGBSentry |
| 检查版本 | open-source |
| 工具版本 | 1.0.0 |
| 总耗时 | 9.4秒 |


## 总体统计

| 领域 | 开源版问题数 | 服务器版问题数 |
|------|------------|-------------|
| API一致性 | 0 | 0 |
| 占位功能 | 65 | 0 |
| 健壮性 | 93 | 0 |
| 可用性 | 12 | 0 |
| 好用性 | 9 | 0 |
| 可扩展性 | 257 | 0 |

## API一致性检查


### open-source

- 前端API调用数: 214
- 后端路由数: 0
- 匹配数: 0
- 正向不匹配(前端→后端): 214
- 反向不匹配(后端→前端): 0


#### 正向覆盖问题 (前端调用但后端缺失)

| # | 方法 | 路径 | 状态 | 严重度 | 详情 |
|---|------|------|------|--------|------|
| 1 | GET | `/audit/logs` | missing_backend | high | 前端调用 GET /audit/logs 在后端无对应路由 |
| 2 | GET | `/audit/stats` | missing_backend | high | 前端调用 GET /audit/stats 在后端无对应路由 |
| 3 | GET | `/audit/logs/export` | missing_backend | high | 前端调用 GET /audit/logs/export 在后端无对应路由 |
| 4 | GET | `/config-center/draft` | missing_backend | high | 前端调用 GET /config-center/draft 在后端无对应路由 |
| 5 | GET | `/devices` | missing_backend | high | 前端调用 GET /devices 在后端无对应路由 |
| 6 | GET | `/devices/{id}` | missing_backend | high | 前端调用 GET /devices/{id} 在后端无对应路由 |
| 7 | GET | `/organizations/tree` | missing_backend | high | 前端调用 GET /organizations/tree 在后端无对应路由 |
| 8 | GET | `/release-center/draft/diff` | missing_backend | high | 前端调用 GET /release-center/draft/diff 在后端无对应路由 |
| 9 | POST | `/release-center/draft/publish` | missing_backend | high | 前端调用 POST /release-center/draft/publish 在后端无对应路由 |
| 10 | POST | `/release-center/rollback` | missing_backend | high | 前端调用 POST /release-center/rollback 在后端无对应路由 |
| 11 | GET | `/alarms/unread-count` | missing_backend | high | 前端调用 GET /alarms/unread-count 在后端无对应路由 |
| 12 | GET | `/alarms/sla/overview` | missing_backend | high | 前端调用 GET /alarms/sla/overview 在后端无对应路由 |
| 13 | GET | `/alarms` | missing_backend | high | 前端调用 GET /alarms 在后端无对应路由 |
| 14 | POST | `/alarms/${row.id}/ack` | missing_backend | high | 前端调用 POST /alarms/${row.id}/ack 在后端无对应路由 |
| 15 | POST | `/alarms/${row.id}/escalate` | missing_backend | high | 前端调用 POST /alarms/${row.id}/escalate 在后端无对应路由 |
| 16 | GET | `/alarms/config` | missing_backend | high | 前端调用 GET /alarms/config 在后端无对应路由 |
| 17 | PUT | `/alarms/config` | missing_backend | high | 前端调用 PUT /alarms/config 在后端无对应路由 |
| 18 | GET | `/user-api-keys/me` | missing_backend | high | 前端调用 GET /user-api-keys/me 在后端无对应路由 |
| 19 | POST | `/user-api-keys` | missing_backend | high | 前端调用 POST /user-api-keys 在后端无对应路由 |
| 20 | POST | `/user-api-keys/{id}/revoke` | missing_backend | high | 前端调用 POST /user-api-keys/{id}/revoke 在后端无对应路由 |
| 21 | GET | `/apps/logs` | missing_backend | high | 前端调用 GET /apps/logs 在后端无对应路由 |
| 22 | GET | `/platforms` | missing_backend | high | 前端调用 GET /platforms 在后端无对应路由 |
| 23 | POST | `/platforms/{id}/actions/register` | missing_backend | high | 前端调用 POST /platforms/{id}/actions/register 在后端无对应路 |
| 24 | POST | `/platforms/{id}/actions/push-catalog` | missing_backend | high | 前端调用 POST /platforms/{id}/actions/push-catalog 在后端 |
| 25 | PUT | `/platforms/${editingId.value}` | missing_backend | high | 前端调用 PUT /platforms/${editingId.value} 在后端无对应路由 |
| 26 | GET | `/platforms/exist/${encodeURIComponent(String(form.server_gb_id || '').trim())}` | missing_backend | high | 前端调用 GET /platforms/exist/${encodeURIComponent(Str |
| 27 | POST | `/platforms` | missing_backend | high | 前端调用 POST /platforms 在后端无对应路由 |
| 28 | DELETE | `/platforms/${row.id}` | missing_backend | high | 前端调用 DELETE /platforms/${row.id} 在后端无对应路由 |
| 29 | GET | `/platforms/channels/flat` | missing_backend | high | 前端调用 GET /platforms/channels/flat 在后端无对应路由 |
| 30 | GET | `/platforms/${catalogPlatformId.value}/catalog-resources` | missing_backend | high | 前端调用 GET /platforms/${catalogPlatformId.value}/cat |
| 31 | PUT | `/platforms/${catalogPlatformId.value}/catalog-resources` | missing_backend | high | 前端调用 PUT /platforms/${catalogPlatformId.value}/cat |
| 32 | GET | `/platforms/{id}/diagnosis` | missing_backend | high | 前端调用 GET /platforms/{id}/diagnosis 在后端无对应路由 |
| 33 | GET | `/api/common/channel/list` | missing_backend | high | 前端调用 GET /api/common/channel/list 在后端无对应路由 |
| 34 | POST | `/api/common/channel/region/add` | missing_backend | high | 前端调用 POST /api/common/channel/region/add 在后端无对应路由 |
| 35 | POST | `/api/common/channel/group/add` | missing_backend | high | 前端调用 POST /api/common/channel/group/add 在后端无对应路由 |
| 36 | POST | `/stream/stop` | missing_backend | high | 前端调用 POST /stream/stop 在后端无对应路由 |
| 37 | GET | `/devices/channels/flat` | missing_backend | high | 前端调用 GET /devices/channels/flat 在后端无对应路由 |
| 38 | POST | `/api/common/channel/reset` | missing_backend | high | 前端调用 POST /api/common/channel/reset 在后端无对应路由 |
| 39 | POST | `/devices/channels/batch-placement` | missing_backend | high | 前端调用 POST /devices/channels/batch-placement 在后端无对应 |
| 40 | GET | `/devices/channels/flat` | missing_backend | high | 前端调用 GET /devices/channels/flat 在后端无对应路由 |
| 41 | PUT | `/devices/channels/{id}` | missing_backend | high | 前端调用 PUT /devices/channels/{id} 在后端无对应路由 |
| 42 | PUT | `/devices/channels/${String(ch.id)}` | missing_backend | high | 前端调用 PUT /devices/channels/${String(ch.id)} 在后端无对应 |
| 43 | POST | `/stream/play_status` | missing_backend | high | 前端调用 POST /stream/play_status 在后端无对应路由 |
| 44 | POST | `/stream/stop` | missing_backend | high | 前端调用 POST /stream/stop 在后端无对应路由 |
| 45 | POST | `/devices/channels/${row.id}/reset` | missing_backend | high | 前端调用 POST /devices/channels/${row.id}/reset 在后端无对应 |
| 46 | DELETE | `/devices/channels/${row.id}` | missing_backend | high | 前端调用 DELETE /devices/channels/${row.id} 在后端无对应路由 |
| 47 | POST | `/devices/{gb_id}/sync` | missing_backend | high | 前端调用 POST /devices/{gb_id}/sync 在后端无对应路由 |
| 48 | GET | `/devices/tree/business` | missing_backend | high | 前端调用 GET /devices/tree/business 在后端无对应路由 |
| 49 | GET | `/regions/tree` | missing_backend | high | 前端调用 GET /regions/tree 在后端无对应路由 |
| 50 | GET | `/system-config/system-info` | missing_backend | high | 前端调用 GET /system-config/system-info 在后端无对应路由 |
| 51 | DELETE | `/devices/directories` | missing_backend | high | 前端调用 DELETE /devices/directories 在后端无对应路由 |
| 52 | PUT | `/devices/directories` | missing_backend | high | 前端调用 PUT /devices/directories 在后端无对应路由 |
| 53 | PUT | `/devices/channels/${channel.id}` | missing_backend | high | 前端调用 PUT /devices/channels/${channel.id} 在后端无对应路由 |
| 54 | GET | `/system-config/gb28181/play-config` | missing_backend | high | 前端调用 GET /system-config/gb28181/play-config 在后端无对应 |
| 55 | GET | `/system-config/gb28181/learning-state` | missing_backend | high | 前端调用 GET /system-config/gb28181/learning-state 在后端 |
| 56 | PUT | `/system-config/gb28181/play-config` | missing_backend | high | 前端调用 PUT /system-config/gb28181/play-config 在后端无对应 |
| 57 | DELETE | `/system-config/gb28181/learning-state` | missing_backend | high | 前端调用 DELETE /system-config/gb28181/learning-state  |
| 58 | GET | `/config-center/basic` | missing_backend | high | 前端调用 GET /config-center/basic 在后端无对应路由 |
| 59 | PUT | `/config-center/basic` | missing_backend | high | 前端调用 PUT /config-center/basic 在后端无对应路由 |
| 60 | GET | `/system-config/database` | missing_backend | high | 前端调用 GET /system-config/database 在后端无对应路由 |
| 61 | POST | `/system-config/database/test` | missing_backend | high | 前端调用 POST /system-config/database/test 在后端无对应路由 |
| 62 | PUT | `/system-config/database` | missing_backend | high | 前端调用 PUT /system-config/database 在后端无对应路由 |
| 63 | GET | `/ops/db-compat-report` | missing_backend | high | 前端调用 GET /ops/db-compat-report 在后端无对应路由 |
| 64 | GET | `/integrations/sources` | missing_backend | high | 前端调用 GET /integrations/sources 在后端无对应路由 |
| 65 | POST | `/integrations/sources/{id}/test` | missing_backend | high | 前端调用 POST /integrations/sources/{id}/test 在后端无对应路由 |
| 66 | DELETE | `/integrations/sources/{id}` | missing_backend | high | 前端调用 DELETE /integrations/sources/{id} 在后端无对应路由 |
| 67 | POST | `/integrations/sources/{id}/play` | missing_backend | high | 前端调用 POST /integrations/sources/{id}/play 在后端无对应路由 |
| 68 | POST | `/stream/stop` | missing_backend | high | 前端调用 POST /stream/stop 在后端无对应路由 |
| 69 | GET | `/record-schedule/storage-config` | missing_backend | high | 前端调用 GET /record-schedule/storage-config 在后端无对应路由 |
| 70 | GET | `/record-schedule/storage-nodes` | missing_backend | high | 前端调用 GET /record-schedule/storage-nodes 在后端无对应路由 |
| 71 | PUT | `/record-schedule/storage-config` | missing_backend | high | 前端调用 PUT /record-schedule/storage-config 在后端无对应路由 |
| 72 | PUT | `/record-schedule/storage-nodes` | missing_backend | high | 前端调用 PUT /record-schedule/storage-nodes 在后端无对应路由 |
| 73 | GET | `/audit-center/logs` | missing_backend | high | 前端调用 GET /audit-center/logs 在后端无对应路由 |
| 74 | GET | `/ops/status` | missing_backend | high | 前端调用 GET /ops/status 在后端无对应路由 |
| 75 | GET | `/network/summary` | missing_backend | high | 前端调用 GET /network/summary 在后端无对应路由 |
| 76 | GET | `/network/bandwidth` | missing_backend | high | 前端调用 GET /network/bandwidth 在后端无对应路由 |
| 77 | GET | `/network/topology` | missing_backend | high | 前端调用 GET /network/topology 在后端无对应路由 |
| 78 | GET | `/ops/diagnose-report` | missing_backend | high | 前端调用 GET /ops/diagnose-report 在后端无对应路由 |
| 79 | GET | `/metrics/devices-overview` | missing_backend | high | 前端调用 GET /metrics/devices-overview 在后端无对应路由 |
| 80 | GET | `/alarms?limit=50` | missing_backend | high | 前端调用 GET /alarms?limit=50 在后端无对应路由 |
| 81 | GET | `/demo/status` | missing_backend | high | 前端调用 GET /demo/status 在后端无对应路由 |
| 82 | GET | `/system-config/system-info` | missing_backend | high | 前端调用 GET /system-config/system-info 在后端无对应路由 |
| 83 | GET | `/devices/${device.gb_id}/channels` | missing_backend | high | 前端调用 GET /devices/${device.gb_id}/channels 在后端无对应路 |
| 84 | GET | `/map/trajectory` | missing_backend | high | 前端调用 GET /map/trajectory 在后端无对应路由 |
| 85 | GET | `/map/device-latest-position` | missing_backend | high | 前端调用 GET /map/device-latest-position 在后端无对应路由 |
| 86 | POST | `/map/mobile-position/subscribe` | missing_backend | high | 前端调用 POST /map/mobile-position/subscribe 在后端无对应路由 |
| 87 | GET | `/map/devices-latest-positions` | missing_backend | high | 前端调用 GET /map/devices-latest-positions 在后端无对应路由 |
| 88 | GET | `/map/providers` | missing_backend | high | 前端调用 GET /map/providers 在后端无对应路由 |
| 89 | POST | `/map` | missing_backend | high | 前端调用 POST /map 在后端无对应路由 |
| 90 | POST | `/login/access-token` | missing_backend | high | 前端调用 POST /login/access-token 在后端无对应路由 |
| 91 | GET | `/integrations/sources` | missing_backend | high | 前端调用 GET /integrations/sources 在后端无对应路由 |
| 92 | POST | `/stream/stop` | missing_backend | high | 前端调用 POST /stream/stop 在后端无对应路由 |
| 93 | POST | `/integrations/sources/${channel.sourceId}/play` | missing_backend | high | 前端调用 POST /integrations/sources/${channel.sourceId |
| 94 | GET | `/stream/play_status/{session_id}` | missing_backend | high | 前端调用 GET /stream/play_status/{session_id} 在后端无对应路由 |
| 95 | GET | `/logs/files` | missing_backend | high | 前端调用 GET /logs/files 在后端无对应路由 |
| 96 | GET | `/logs/files/${encodeURIComponent(currentLogFile.value).replace(/%2F/g, '/')}/lines` | missing_backend | high | 前端调用 GET /logs/files/${encodeURIComponent(currentL |
| 97 | GET | `/logs/files/${encodeURIComponent(row.name).replace(/%2F/g, '/')}/download` | missing_backend | high | 前端调用 GET /logs/files/${encodeURIComponent(row.name |
| 98 | GET | `/trace-events` | missing_backend | high | 前端调用 GET /trace-events 在后端无对应路由 |
| 99 | GET | `/ops/status` | missing_backend | high | 前端调用 GET /ops/status 在后端无对应路由 |
| 100 | GET | `/integrations/media-nodes` | missing_backend | high | 前端调用 GET /integrations/media-nodes 在后端无对应路由 |
| 101 | GET | `/integrations/media-nodes/offline-threshold` | missing_backend | high | 前端调用 GET /integrations/media-nodes/offline-thresho |
| 102 | PUT | `/integrations/media-nodes/offline-threshold` | missing_backend | high | 前端调用 PUT /integrations/media-nodes/offline-thresho |
| 103 | PUT | `/integrations/media-nodes/${editingMediaId.value}/zlm-ssl` | missing_backend | high | 前端调用 PUT /integrations/media-nodes/${editingMediaI |
| 104 | DELETE | `/integrations/media-nodes/${editingMediaId.value}/zlm-ssl` | missing_backend | high | 前端调用 DELETE /integrations/media-nodes/${editingMed |
| 105 | PUT | `/integrations/media-nodes/${editingMediaId.value}` | missing_backend | high | 前端调用 PUT /integrations/media-nodes/${editingMediaI |
| 106 | POST | `/integrations/media-nodes` | missing_backend | high | 前端调用 POST /integrations/media-nodes 在后端无对应路由 |
| 107 | GET | `/integrations/media-nodes/{id}/zlm-hook-urls` | missing_backend | high | 前端调用 GET /integrations/media-nodes/{id}/zlm-hook-u |
| 108 | GET | `/integrations/media-nodes/{id}/zlm-config-snippet` | missing_backend | high | 前端调用 GET /integrations/media-nodes/{id}/zlm-config |
| 109 | GET | `/integrations/media-nodes/export/media-nodes-json` | missing_backend | high | 前端调用 GET /integrations/media-nodes/export/media-no |
| 110 | GET | `/integrations/media-nodes/export/env` | missing_backend | high | 前端调用 GET /integrations/media-nodes/export/env 在后端无 |
| 111 | GET | `/integrations/media-nodes/leases` | missing_backend | high | 前端调用 GET /integrations/media-nodes/leases 在后端无对应路由 |
| 112 | POST | `/integrations/media-nodes/leases/cleanup` | missing_backend | high | 前端调用 POST /integrations/media-nodes/leases/cleanup |
| 113 | POST | `/integrations/media-nodes/test-all` | missing_backend | high | 前端调用 POST /integrations/media-nodes/test-all 在后端无对 |
| 114 | POST | `/integrations/media-nodes/{id}/test` | missing_backend | high | 前端调用 POST /integrations/media-nodes/{id}/test 在后端无 |
| 115 | POST | `/integrations/media-nodes/{id}/activate` | missing_backend | high | 前端调用 POST /integrations/media-nodes/{id}/activate  |
| 116 | DELETE | `/integrations/media-nodes/{id}` | missing_backend | high | 前端调用 DELETE /integrations/media-nodes/{id} 在后端无对应路 |
| 117 | POST | `/ops/shutdown` | missing_backend | high | 前端调用 POST /ops/shutdown 在后端无对应路由 |
| 118 | GET | `/ops/diagnostics/export` | missing_backend | high | 前端调用 GET /ops/diagnostics/export 在后端无对应路由 |
| 119 | GET | `/ops/diagnose-report` | missing_backend | high | 前端调用 GET /ops/diagnose-report 在后端无对应路由 |
| 120 | GET | `/ops/db-check` | missing_backend | high | 前端调用 GET /ops/db-check 在后端无对应路由 |
| 121 | GET | `/network/summary` | missing_backend | high | 前端调用 GET /network/summary 在后端无对应路由 |
| 122 | GET | `/ops/backup/list` | missing_backend | high | 前端调用 GET /ops/backup/list 在后端无对应路由 |
| 123 | POST | `/ops/backup` | missing_backend | high | 前端调用 POST /ops/backup 在后端无对应路由 |
| 124 | POST | `/ops/restore` | missing_backend | high | 前端调用 POST /ops/restore 在后端无对应路由 |
| 125 | GET | `/ops/active-streams` | missing_backend | high | 前端调用 GET /ops/active-streams 在后端无对应路由 |
| 126 | POST | `/rtp/receive/open` | missing_backend | high | 前端调用 POST /rtp/receive/open 在后端无对应路由 |
| 127 | POST | `/rtp/receive/close/{task_id}` | missing_backend | high | 前端调用 POST /rtp/receive/close/{task_id} 在后端无对应路由 |
| 128 | GET | `/ssl-cert/status` | missing_backend | high | 前端调用 GET /ssl-cert/status 在后端无对应路由 |
| 129 | POST | `/ssl-cert/renew` | missing_backend | high | 前端调用 POST /ssl-cert/renew 在后端无对应路由 |
| 130 | GET | `/integrations/media-nodes/port-pool-status` | missing_backend | high | 前端调用 GET /integrations/media-nodes/port-pool-statu |
| 131 | GET | `/integrations/ffmpeg_cmd/list` | missing_backend | high | 前端调用 GET /integrations/ffmpeg_cmd/list 在后端无对应路由 |
| 132 | PUT | `/integrations/ffmpeg_cmd/${editingFfmpegCmdId.value}` | missing_backend | high | 前端调用 PUT /integrations/ffmpeg_cmd/${editingFfmpegC |
| 133 | POST | `/integrations/ffmpeg_cmd` | missing_backend | high | 前端调用 POST /integrations/ffmpeg_cmd 在后端无对应路由 |
| 134 | DELETE | `/integrations/ffmpeg_cmd/{id}` | missing_backend | high | 前端调用 DELETE /integrations/ffmpeg_cmd/{id} 在后端无对应路由 |
| 135 | GET | `/platforms/inbound/diagnosis` | missing_backend | high | 前端调用 GET /platforms/inbound/diagnosis 在后端无对应路由 |
| 136 | GET | `/ops/stream-diagnose` | missing_backend | high | 前端调用 GET /ops/stream-diagnose 在后端无对应路由 |
| 137 | GET | `/plugins/runtime/health-status` | missing_backend | high | 前端调用 GET /plugins/runtime/health-status 在后端无对应路由 |
| 138 | GET | `/plugins/runtime/security-report` | missing_backend | high | 前端调用 GET /plugins/runtime/security-report 在后端无对应路由 |
| 139 | POST | `/plugins/marketplace/purchase` | missing_backend | high | 前端调用 POST /plugins/marketplace/purchase 在后端无对应路由 |
| 140 | POST | `/plugins/marketplace/purchase/confirm` | missing_backend | high | 前端调用 POST /plugins/marketplace/purchase/confirm 在后 |
| 141 | POST | `/plugins/upload` | missing_backend | high | 前端调用 POST /plugins/upload 在后端无对应路由 |
| 142 | GET | `/plugins/marketplace` | missing_backend | high | 前端调用 GET /plugins/marketplace 在后端无对应路由 |
| 143 | GET | `/plugins/installed` | missing_backend | high | 前端调用 GET /plugins/installed 在后端无对应路由 |
| 144 | GET | `/plugins/marketplace-shop-url` | missing_backend | high | 前端调用 GET /plugins/marketplace-shop-url 在后端无对应路由 |
| 145 | GET | `/plugins/purchased` | missing_backend | high | 前端调用 GET /plugins/purchased 在后端无对应路由 |
| 146 | GET | `/plugins/{plugin_id}/uninstall-preview` | missing_backend | high | 前端调用 GET /plugins/{plugin_id}/uninstall-preview 在后 |
| 147 | DELETE | `/plugins/{plugin_id}` | missing_backend | high | 前端调用 DELETE /plugins/{plugin_id} 在后端无对应路由 |
| 148 | GET | `/plugins/runtime/health-status` | missing_backend | high | 前端调用 GET /plugins/runtime/health-status 在后端无对应路由 |
| 149 | GET | `/plugins/runtime/security-report` | missing_backend | high | 前端调用 GET /plugins/runtime/security-report 在后端无对应路由 |
| 150 | POST | `/plugins/upload` | missing_backend | high | 前端调用 POST /plugins/upload 在后端无对应路由 |
| 151 | GET | `/plugins/marketplace` | missing_backend | high | 前端调用 GET /plugins/marketplace 在后端无对应路由 |
| 152 | GET | `/plugins/installed` | missing_backend | high | 前端调用 GET /plugins/installed 在后端无对应路由 |
| 153 | GET | `/plugins/marketplace-shop-url` | missing_backend | high | 前端调用 GET /plugins/marketplace-shop-url 在后端无对应路由 |
| 154 | GET | `/plugins/purchased` | missing_backend | high | 前端调用 GET /plugins/purchased 在后端无对应路由 |
| 155 | DELETE | `/plugins/{id}` | missing_backend | high | 前端调用 DELETE /plugins/{id} 在后端无对应路由 |
| 156 | GET | `/plugins/runtime/stream_health/health` | missing_backend | high | 前端调用 GET /plugins/runtime/stream_health/health 在后端 |
| 157 | GET | `/plugins/runtime/sip_logger/logs` | missing_backend | high | 前端调用 GET /plugins/runtime/sip_logger/logs 在后端无对应路由 |
| 158 | GET | `/plugins/runtime/network_watchdog/events` | missing_backend | high | 前端调用 GET /plugins/runtime/network_watchdog/events  |
| 159 | GET | `/plugins/runtime/stream_idle/events` | missing_backend | high | 前端调用 GET /plugins/runtime/stream_idle/events 在后端无对 |
| 160 | GET | `/plugins/runtime/timelapse/events` | missing_backend | high | 前端调用 GET /plugins/runtime/timelapse/events 在后端无对应路 |
| 161 | GET | `/plugins/runtime/webhook_pusher/events` | missing_backend | high | 前端调用 GET /plugins/runtime/webhook_pusher/events 在后 |
| 162 | GET | `/plugins/runtime/s3_sync/events` | missing_backend | high | 前端调用 GET /plugins/runtime/s3_sync/events 在后端无对应路由 |
| 163 | GET | `/plugins/runtime/ptz_tour/events` | missing_backend | high | 前端调用 GET /plugins/runtime/ptz_tour/events 在后端无对应路由 |
| 164 | GET | `/plugins/runtime/auto_record/events` | missing_backend | high | 前端调用 GET /plugins/runtime/auto_record/events 在后端无对 |
| 165 | GET | `/plugins/runtime/record_schedule_executor/events` | missing_backend | high | 前端调用 GET /plugins/runtime/record_schedule_executor |
| 166 | GET | `/plugins/runtime/record_index_verifier/events` | missing_backend | high | 前端调用 GET /plugins/runtime/record_index_verifier/ev |
| 167 | GET | `/plugins/runtime/snapshot_refresh/events` | missing_backend | high | 前端调用 GET /plugins/runtime/snapshot_refresh/events  |
| 168 | GET | `/plugins/runtime/rtmp_push_channel_monitor/events` | missing_backend | high | 前端调用 GET /plugins/runtime/rtmp_push_channel_monito |
| 169 | GET | `/plugins/runtime/pull_proxy_monitor/events` | missing_backend | high | 前端调用 GET /plugins/runtime/pull_proxy_monitor/event |
| 170 | GET | `/plugins/runtime/mqtt_bridge/events` | missing_backend | high | 前端调用 GET /plugins/runtime/mqtt_bridge/events 在后端无对 |
| 171 | GET | `/plugins/runtime/feishu_alert/events` | missing_backend | high | 前端调用 GET /plugins/runtime/feishu_alert/events 在后端无 |
| 172 | GET | `/plugins/runtime/wecom_alert/events` | missing_backend | high | 前端调用 GET /plugins/runtime/wecom_alert/events 在后端无对 |
| 173 | GET | `/plugins/runtime/sms_alert/events` | missing_backend | high | 前端调用 GET /plugins/runtime/sms_alert/events 在后端无对应路 |
| 174 | POST | `/plugins/alert-test` | missing_backend | high | 前端调用 POST /plugins/alert-test 在后端无对应路由 |
| 175 | GET | `/plugins/runtime/${encodeURIComponent(targetPid)}/config` | missing_backend | high | 前端调用 GET /plugins/runtime/${encodeURIComponent(tar |
| 176 | PUT | `/plugins/runtime/${encodeURIComponent(pid)}/config` | missing_backend | high | 前端调用 PUT /plugins/runtime/${encodeURIComponent(pid |
| 177 | GET | `/plugins/marketplace-shop-url` | missing_backend | high | 前端调用 GET /plugins/marketplace-shop-url 在后端无对应路由 |
| 178 | GET | `/plugins/purchased` | missing_backend | high | 前端调用 GET /plugins/purchased 在后端无对应路由 |
| 179 | GET | `/plugins/installed` | missing_backend | high | 前端调用 GET /plugins/installed 在后端无对应路由 |
| 180 | GET | `/plugins/menus` | missing_backend | high | 前端调用 GET /plugins/menus 在后端无对应路由 |
| 181 | GET | `/devices/channels/flat` | missing_backend | high | 前端调用 GET /devices/channels/flat 在后端无对应路由 |
| 182 | GET | `/record-schedule` | missing_backend | high | 前端调用 GET /record-schedule 在后端无对应路由 |
| 183 | PUT | `/record-schedule/${editingId.value}` | missing_backend | high | 前端调用 PUT /record-schedule/${editingId.value} 在后端无对 |
| 184 | POST | `/record-schedule` | missing_backend | high | 前端调用 POST /record-schedule 在后端无对应路由 |
| 185 | PUT | `/record-schedule/${existing.id}` | missing_backend | high | 前端调用 PUT /record-schedule/${existing.id} 在后端无对应路由 |
| 186 | DELETE | `/record-schedule/${row.id}` | missing_backend | high | 前端调用 DELETE /record-schedule/${row.id} 在后端无对应路由 |
| 187 | GET | `/record-schedule/runtimes` | missing_backend | high | 前端调用 GET /record-schedule/runtimes 在后端无对应路由 |
| 188 | POST | `/record-schedule/${row.id}/actions/force-start` | missing_backend | high | 前端调用 POST /record-schedule/${row.id}/actions/force |
| 189 | POST | `/record-schedule/${row.id}/actions/force-stop` | missing_backend | high | 前端调用 POST /record-schedule/${row.id}/actions/force |
| 190 | GET | `/roles` | missing_backend | high | 前端调用 GET /roles 在后端无对应路由 |
| 191 | GET | `/plugins/menus` | missing_backend | high | 前端调用 GET /plugins/menus 在后端无对应路由 |
| 192 | PUT | `/roles/${roleEditingId.value}` | missing_backend | high | 前端调用 PUT /roles/${roleEditingId.value} 在后端无对应路由 |
| 193 | POST | `/roles` | missing_backend | high | 前端调用 POST /roles 在后端无对应路由 |
| 194 | DELETE | `/roles/${row.id}` | missing_backend | high | 前端调用 DELETE /roles/${row.id} 在后端无对应路由 |
| 195 | GET | `/integrations/sources` | missing_backend | high | 前端调用 GET /integrations/sources 在后端无对应路由 |
| 196 | POST | `/stream/stop` | missing_backend | high | 前端调用 POST /stream/stop 在后端无对应路由 |
| 197 | POST | `/integrations/sources/${channel.sourceId}/play` | missing_backend | high | 前端调用 POST /integrations/sources/${channel.sourceId |
| 198 | POST | `/stream/play_status` | missing_backend | high | 前端调用 POST /stream/play_status 在后端无对应路由 |
| 199 | GET | `/users` | missing_backend | high | 前端调用 GET /users 在后端无对应路由 |
| 200 | GET | `/users/me` | missing_backend | high | 前端调用 GET /users/me 在后端无对应路由 |
| 201 | GET | `/roles` | missing_backend | high | 前端调用 GET /roles 在后端无对应路由 |
| 202 | PUT | `/users/${editingId.value}` | missing_backend | high | 前端调用 PUT /users/${editingId.value} 在后端无对应路由 |
| 203 | POST | `/users` | missing_backend | high | 前端调用 POST /users 在后端无对应路由 |
| 204 | DELETE | `/users/{id}` | missing_backend | high | 前端调用 DELETE /users/{id} 在后端无对应路由 |
| 205 | POST | `/users/{id}/unlock` | missing_backend | high | 前端调用 POST /users/{id}/unlock 在后端无对应路由 |
| 206 | GET | `/map/trajectory` | missing_backend | high | 前端调用 GET /map/trajectory 在后端无对应路由 |
| 207 | POST | `/map/trajectory` | missing_backend | high | 前端调用 POST /map/trajectory 在后端无对应路由 |
| 208 | GET | `/map` | missing_backend | high | 前端调用 GET /map 在后端无对应路由 |
| 209 | GET | `/map/command-config` | missing_backend | high | 前端调用 GET /map/command-config 在后端无对应路由 |
| 210 | GET | `/devices/channels/flat` | missing_backend | high | 前端调用 GET /devices/channels/flat 在后端无对应路由 |
| 211 | GET | `/api/common/channel/stream-status` | missing_backend | high | 前端调用 GET /api/common/channel/stream-status 在后端无对应路 |
| 212 | GET | `/devices/{gb_id}/channels` | missing_backend | high | 前端调用 GET /devices/{gb_id}/channels 在后端无对应路由 |
| 213 | POST | `/stream/stop` | missing_backend | high | 前端调用 POST /stream/stop 在后端无对应路由 |
| 214 | PUT | `/devices/channels/${encodeURIComponent(channelId)}` | missing_backend | high | 前端调用 PUT /devices/channels/${encodeURIComponent(ch |

## 占位功能扫描


### open-source

- 总计: 65

**按类型:**

  - todo_comment: 5
  - exception_swallow: 60

**按优先级:**

  - P0: 32
  - P2: 5
  - P3: 28

| # | 优先级 | 类型 | 位置 | 行号 | 描述 |
|---|--------|------|------|------|------|
| 1 | P3 | todo_comment | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\initial_data.py` | 39 | TODO/FIXME注释: # 回退到 os.environ（支持命令行 ADM |
| 2 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 51 | 异常被静默吞没 (except ...: pass) |
| 3 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1030 | 异常被静默吞没 (except ...: pass) |
| 4 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 200 | 异常被静默吞没 (except ...: pass) |
| 5 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1018 | 异常被静默吞没 (except ...: pass) |
| 6 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1024 | 异常被静默吞没 (except ...: pass) |
| 7 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1006 | 异常被静默吞没 (except ...: pass) |
| 8 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1141 | 异常被静默吞没 (except ...: pass) |
| 9 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 184 | 异常被静默吞没 (except ...: pass) |
| 10 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\async_utils.py` | 40 | 异常被静默吞没 (except ...: pass) |
| 11 | P2 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\config.py` | 843 | 异常被静默吞没 (except ...: pass) |
| 12 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\delay_queue.py` | 30 | 异常被静默吞没 (except ...: pass) |
| 13 | P2 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\log_masker.py` | 40 | 异常被静默吞没 (except ...: pass) |
| 14 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1562 | 异常被静默吞没 (except ...: pass) |
| 15 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 116 | 异常被静默吞没 (except ...: pass) |
| 16 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 592 | 异常被静默吞没 (except ...: pass) |
| 17 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1222 | 异常被静默吞没 (except ...: pass) |
| 18 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\ratelimit.py` | 62 | 异常被静默吞没 (except ...: pass) |
| 19 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 237 | 异常被静默吞没 (except ...: pass) |
| 20 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 244 | 异常被静默吞没 (except ...: pass) |
| 21 | P2 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\auth_audit.py` | 67 | 异常被静默吞没 (except ...: pass) |
| 22 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\channel_placement_migration.py` | 71 | 异常被静默吞没 (except ...: pass) |
| 23 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\device_subscription_service.py` | 73 | 异常被静默吞没 (except ...: pass) |
| 24 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\device_subscription_service.py` | 166 | 异常被静默吞没 (except ...: pass) |
| 25 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 928 | 异常被静默吞没 (except ...: pass) |
| 26 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\media_manager.py` | 106 | 异常被静默吞没 (except ...: pass) |
| 27 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\platform_subscription_service.py` | 86 | 异常被静默吞没 (except ...: pass) |
| 28 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\region_directory_split_migration.py` | 69 | 异常被静默吞没 (except ...: pass) |
| 29 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\region_import_service.py` | 190 | 异常被静默吞没 (except ...: pass) |
| 30 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\catalog_runtime.py` | 60 | 异常被静默吞没 (except ...: pass) |
| 31 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\dialog_manager.py` | 76 | 异常被静默吞没 (except ...: pass) |
| 32 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\dialog_manager.py` | 130 | 异常被静默吞没 (except ...: pass) |
| 33 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\handlers.py` | 3313 | 异常被静默吞没 (except ...: pass) |
| 34 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\handlers.py` | 3146 | 异常被静默吞没 (except ...: pass) |
| 35 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\invite.py` | 2429 | 异常被静默吞没 (except ...: pass) |
| 36 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\message.py` | 438 | 异常被静默吞没 (except ...: pass) |
| 37 | P0 | todo_comment | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\message.py` | 160 | TODO/FIXME注释: # From/To 头中的 ;tag=xxx |
| 38 | P0 | todo_comment | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\message.py` | 162 | TODO/FIXME注释: # Via 头中的 ;branch=xxx |
| 39 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 360 | 异常被静默吞没 (except ...: pass) |
| 40 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 294 | 异常被静默吞没 (except ...: pass) |
| 41 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 815 | 异常被静默吞没 (except ...: pass) |
| 42 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 402 | 异常被静默吞没 (except ...: pass) |
| 43 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 139 | 异常被静默吞没 (except ...: pass) |
| 44 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 184 | 异常被静默吞没 (except ...: pass) |
| 45 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\server.py` | 489 | 异常被静默吞没 (except ...: pass) |
| 46 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\ssrc_manager.py` | 281 | 异常被静默吞没 (except ...: pass) |
| 47 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\subscribe_manager.py` | 279 | 异常被静默吞没 (except ...: pass) |
| 48 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 225 | 异常被静默吞没 (except ...: pass) |
| 49 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 131 | 异常被静默吞没 (except ...: pass) |
| 50 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 622 | 异常被静默吞没 (except ...: pass) |
| 51 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\watchdog.py` | 202 | 异常被静默吞没 (except ...: pass) |
| 52 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\watchdog.py` | 207 | 异常被静默吞没 (except ...: pass) |
| 53 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\utils\firewall.py` | 74 | 异常被静默吞没 (except ...: pass) |
| 54 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\device_record.py` | 719 | 异常被静默吞没 (except ...: pass) |
| 55 | P2 | todo_comment | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\login.py` | 121 | TODO/FIXME注释: 再用 `ws?ticket=xxx` 建立 WebS |
| 56 | P2 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\logs.py` | 98 | 异常被静默吞没 (except ...: pass) |
| 57 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\record.py` | 109 | 异常被静默吞没 (except ...: pass) |
| 58 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\sip_trace_ws.py` | 72 | 异常被静默吞没 (except ...: pass) |
| 59 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\talk.py` | 291 | 异常被静默吞没 (except ...: pass) |
| 60 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\ssl_certbot\certbot_manager.py` | 75 | 异常被静默吞没 (except ...: pass) |
| 61 | P0 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\device_watchdog.py` | 99 | 异常被静默吞没 (except ...: pass) |
| 62 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 100 | 异常被静默吞没 (except ...: pass) |
| 63 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 102 | 异常被静默吞没 (except ...: pass) |
| 64 | P3 | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 86 | 异常被静默吞没 (except ...: pass) |
| 65 | P3 | todo_comment | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\utils\wsTicket.ts` | 14 | TODO/FIXME注释: * @returns A ws:// or wss: |

## 健壮性检查


### open-source

- 问题数: 93

**按类别:**

  - exception_swallow: 93

| # | 严重度 | 类别 | 位置 | 行号 | 描述 |
|---|--------|------|------|------|------|
| 1 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 184 | 异常被静默吞没: except Exception:
              |
| 2 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1006 | 异常被静默吞没: except asyncio.CancelledError:
 |
| 3 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1018 | 异常被静默吞没: except asyncio.CancelledError:
 |
| 4 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1141 | 异常被静默吞没: except Exception:
              |
| 5 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\async_utils.py` | 40 | 异常被静默吞没: except Exception:
            p |
| 6 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\config.py` | 843 | 异常被静默吞没: except (ValueError, TypeError): |
| 7 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 116 | 异常被静默吞没: except Exception:
              |
| 8 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1222 | 异常被静默吞没: except Exception:
              |
| 9 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\ratelimit.py` | 62 | 异常被静默吞没: except Exception:
        pass |
| 10 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 237 | 异常被静默吞没: except ImportError:
            |
| 11 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 244 | 异常被静默吞没: except Exception:
              |
| 12 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\device_subscription_service.py` | 166 | 异常被静默吞没: except Exception:
              |
| 13 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\dialog_manager.py` | 76 | 异常被静默吞没: except Exception:
            p |
| 14 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\handlers.py` | 3313 | 异常被静默吞没: except Exception:
            p |
| 15 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\invite.py` | 2429 | 异常被静默吞没: except Exception:
              |
| 16 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\message.py` | 438 | 异常被静默吞没: except ValueError:
             |
| 17 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 294 | 异常被静默吞没: except (ValueError, TypeError,  |
| 18 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 360 | 异常被静默吞没: except (IndexError, ValueError) |
| 19 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 815 | 异常被静默吞没: except Exception:
              |
| 20 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 139 | 异常被静默吞没: except ValueError:
             |
| 21 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 184 | 异常被静默吞没: except ValueError:
             |
| 22 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 402 | 异常被静默吞没: except (ValueError, TypeError): |
| 23 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\server.py` | 489 | 异常被静默吞没: except Exception:
            p |
| 24 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\ssrc_manager.py` | 281 | 异常被静默吞没: except ValueError:
             |
| 25 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 131 | 异常被静默吞没: except Exception:
              |
| 26 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 622 | 异常被静默吞没: except Exception:
              |
| 27 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\watchdog.py` | 202 | 异常被静默吞没: except Exception:
            p |
| 28 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\watchdog.py` | 207 | 异常被静默吞没: except Exception:
            p |
| 29 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\logs.py` | 98 | 异常被静默吞没: except Exception:
              |
| 30 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\record.py` | 109 | 异常被静默吞没: except Exception:
            p |
| 31 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\sip_trace_ws.py` | 72 | 异常被静默吞没: except WebSocketDisconnect:
    |
| 32 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\device_watchdog.py` | 99 | 异常被静默吞没: except (asyncio.CancelledError, |
| 33 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 100 | 异常被静默吞没: except (asyncio.CancelledError, |
| 34 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 51 | except:pass 且无raise/return，异常完全吞没 |
| 35 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1030 | except:pass 且无raise/return，异常完全吞没 |
| 36 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 200 | except:pass 且无raise/return，异常完全吞没 |
| 37 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1018 | except:pass 且无raise/return，异常完全吞没 |
| 38 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1024 | except:pass 且无raise/return，异常完全吞没 |
| 39 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1006 | except:pass 且无raise/return，异常完全吞没 |
| 40 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1141 | except:pass 且无raise/return，异常完全吞没 |
| 41 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 184 | except:pass 且无raise/return，异常完全吞没 |
| 42 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\async_utils.py` | 40 | except:pass 且无raise/return，异常完全吞没 |
| 43 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\config.py` | 843 | except:pass 且无raise/return，异常完全吞没 |
| 44 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\delay_queue.py` | 30 | except:pass 且无raise/return，异常完全吞没 |
| 45 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\log_masker.py` | 40 | except:pass 且无raise/return，异常完全吞没 |
| 46 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1562 | except:pass 且无raise/return，异常完全吞没 |
| 47 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 116 | except:pass 且无raise/return，异常完全吞没 |
| 48 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 592 | except:pass 且无raise/return，异常完全吞没 |
| 49 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1222 | except:pass 且无raise/return，异常完全吞没 |
| 50 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\ratelimit.py` | 62 | except:pass 且无raise/return，异常完全吞没 |
| 51 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 237 | except:pass 且无raise/return，异常完全吞没 |
| 52 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 244 | except:pass 且无raise/return，异常完全吞没 |
| 53 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\auth_audit.py` | 67 | except:pass 且无raise/return，异常完全吞没 |
| 54 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\channel_placement_migration.py` | 71 | except:pass 且无raise/return，异常完全吞没 |
| 55 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\device_subscription_service.py` | 73 | except:pass 且无raise/return，异常完全吞没 |
| 56 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\device_subscription_service.py` | 166 | except:pass 且无raise/return，异常完全吞没 |
| 57 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 928 | except:pass 且无raise/return，异常完全吞没 |
| 58 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\media_manager.py` | 106 | except:pass 且无raise/return，异常完全吞没 |
| 59 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\platform_subscription_service.py` | 86 | except:pass 且无raise/return，异常完全吞没 |
| 60 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\region_directory_split_migration.py` | 69 | except:pass 且无raise/return，异常完全吞没 |
| 61 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\region_import_service.py` | 190 | except:pass 且无raise/return，异常完全吞没 |
| 62 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\catalog_runtime.py` | 60 | except:pass 且无raise/return，异常完全吞没 |
| 63 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\dialog_manager.py` | 76 | except:pass 且无raise/return，异常完全吞没 |
| 64 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\dialog_manager.py` | 130 | except:pass 且无raise/return，异常完全吞没 |
| 65 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\handlers.py` | 3313 | except:pass 且无raise/return，异常完全吞没 |
| 66 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\handlers.py` | 3146 | except:pass 且无raise/return，异常完全吞没 |
| 67 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\invite.py` | 2429 | except:pass 且无raise/return，异常完全吞没 |
| 68 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\message.py` | 438 | except:pass 且无raise/return，异常完全吞没 |
| 69 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 360 | except:pass 且无raise/return，异常完全吞没 |
| 70 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 294 | except:pass 且无raise/return，异常完全吞没 |
| 71 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\response_handler.py` | 815 | except:pass 且无raise/return，异常完全吞没 |
| 72 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 402 | except:pass 且无raise/return，异常完全吞没 |
| 73 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 139 | except:pass 且无raise/return，异常完全吞没 |
| 74 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\sdp.py` | 184 | except:pass 且无raise/return，异常完全吞没 |
| 75 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\server.py` | 489 | except:pass 且无raise/return，异常完全吞没 |
| 76 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\ssrc_manager.py` | 281 | except:pass 且无raise/return，异常完全吞没 |
| 77 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\subscribe_manager.py` | 279 | except:pass 且无raise/return，异常完全吞没 |
| 78 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 225 | except:pass 且无raise/return，异常完全吞没 |
| 79 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 131 | except:pass 且无raise/return，异常完全吞没 |
| 80 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\talk.py` | 622 | except:pass 且无raise/return，异常完全吞没 |
| 81 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\watchdog.py` | 202 | except:pass 且无raise/return，异常完全吞没 |
| 82 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\sip\watchdog.py` | 207 | except:pass 且无raise/return，异常完全吞没 |
| 83 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\utils\firewall.py` | 74 | except:pass 且无raise/return，异常完全吞没 |
| 84 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\device_record.py` | 719 | except:pass 且无raise/return，异常完全吞没 |
| 85 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\logs.py` | 98 | except:pass 且无raise/return，异常完全吞没 |
| 86 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\record.py` | 109 | except:pass 且无raise/return，异常完全吞没 |
| 87 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\sip_trace_ws.py` | 72 | except:pass 且无raise/return，异常完全吞没 |
| 88 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\endpoints\talk.py` | 291 | except:pass 且无raise/return，异常完全吞没 |
| 89 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\ssl_certbot\certbot_manager.py` | 75 | except:pass 且无raise/return，异常完全吞没 |
| 90 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\device_watchdog.py` | 99 | except:pass 且无raise/return，异常完全吞没 |
| 91 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 100 | except:pass 且无raise/return，异常完全吞没 |
| 92 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 102 | except:pass 且无raise/return，异常完全吞没 |
| 93 | high | exception_swallow | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\tasks\task_manager.py` | 86 | except:pass 且无raise/return，异常完全吞没 |

## 可用性检查


### open-source

- 问题数: 12

**按类别:**

  - no_failure_feedback: 3
  - no_loading: 5
  - no_success_feedback: 3
  - batch_no_progress: 1

| # | 严重度 | 类别 | 位置 | 行号 | 描述 |
|---|--------|------|------|------|------|
| 1 | medium | no_failure_feedback | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\App.vue` | 1 | API调用有catch但无错误提示 |
| 2 | low | no_loading | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\App.vue` | 1 | API调用无loading状态指示 |
| 3 | low | no_loading | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\RecordList.vue` | 1 | API调用无loading状态指示 |
| 4 | medium | no_success_feedback | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\RecordTimeline.vue` | 1 | 写操作后无成功反馈提示 |
| 5 | medium | no_success_feedback | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\TopBar.vue` | 1 | 写操作后无成功反馈提示 |
| 6 | medium | no_failure_feedback | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\TopBar.vue` | 1 | API调用有catch但无错误提示 |
| 7 | low | no_loading | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\TopBar.vue` | 1 | API调用无loading状态指示 |
| 8 | low | no_loading | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\Dashboard.vue` | 1 | API调用无loading状态指示 |
| 9 | medium | batch_no_progress | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\DeviceList.vue` | 1 | 批量操作无进度反馈 |
| 10 | medium | no_success_feedback | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\VisualCommand.vue` | 1 | 写操作后无成功反馈提示 |
| 11 | medium | no_failure_feedback | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\components\device\DeviceAccessInfoDialog.vue` | 1 | API调用有catch但无错误提示 |
| 12 | low | no_loading | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\device-list\DeviceDetailDrawer.vue` | 1 | API调用无loading状态指示 |

## 好用性检查


### open-source

- 问题数: 9

**按类别:**

  - tech_jargon: 4
  - vague_error: 1
  - legacy_naming: 4

| # | 严重度 | 类别 | 位置 | 行号 | 描述 |
|---|--------|------|------|------|------|
| 1 | high | tech_jargon | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\GisMap.vue` | 595 | 错误提示暴露技术细节: "errNo" |
| 2 | high | tech_jargon | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\GisMap.vue` | 595 | 错误提示暴露技术细节: "errNo" |
| 3 | high | tech_jargon | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\GisMap.vue` | 596 | 错误提示暴露技术细节: "errNo" |
| 4 | high | tech_jargon | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\GisMap.vue` | 596 | 错误提示暴露技术细节: "errNo" |
| 5 | medium | vague_error | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\src\views\VisualCommand.vue` | 546 | 模糊错误提示: "处理失败" |
| 6 | low | legacy_naming | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\api.py` | 1 | 历史遗留命名: gb_record |
| 7 | low | legacy_naming | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\api.py` | 1 | 历史遗留命名: record_schedule |
| 8 | low | legacy_naming | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\api.py` | 1 | 历史遗留命名: push_channels |
| 9 | low | legacy_naming | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\api\v1\api.py` | 1 | 历史遗留命名: device_record |

## 可扩展性检查


### open-source

- 问题数: 257

**按类别:**

  - hardcode: 156
  - missing_config: 2
  - direct_dependency: 99

| # | 严重度 | 类别 | 位置 | 行号 | 描述 |
|---|--------|------|------|------|------|
| 1 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\initial_data.py` | 127 | 内联timeout配置: timeout=5 |
| 2 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\initial_data.py` | 159 | 固定URL: "http://{settings.BACKEND_PUBLIC_ |
| 3 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 387 | 内联timeout配置: timeout=30 |
| 4 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 404 | 内联timeout配置: timeout=120 |
| 5 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 420 | 内联timeout配置: timeout=30 |
| 6 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 455 | 内联timeout配置: timeout=30 |
| 7 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 466 | 内联timeout配置: timeout=30 |
| 8 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 479 | 内联timeout配置: timeout=30 |
| 9 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 501 | 内联timeout配置: timeout=20 |
| 10 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 556 | 内联timeout配置: timeout=25 |
| 11 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 588 | 内联timeout配置: timeout=60 |
| 12 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 595 | 内联timeout配置: timeout=60 |
| 13 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 632 | 内联timeout配置: timeout=30 |
| 14 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 662 | 内联timeout配置: timeout=10 |
| 15 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 704 | 内联timeout配置: timeout=10 |
| 16 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 759 | 内联timeout配置: timeout=20 |
| 17 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 779 | 内联timeout配置: timeout=20 |
| 18 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 795 | 内联timeout配置: timeout=10 |
| 19 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 805 | 内联timeout配置: timeout=10 |
| 20 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 829 | 内联timeout配置: timeout=20 |
| 21 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 855 | 内联timeout配置: timeout=20 |
| 22 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 880 | 内联timeout配置: timeout=130 |
| 23 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 893 | 内联timeout配置: timeout=5 |
| 24 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1038 | 内联timeout配置: timeout=10 |
| 25 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\main.py` | 1046 | 内联timeout配置: timeout=10 |
| 26 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes.py` | 101 | 固定URL: "http://{node[' |
| 27 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes.py` | 104 | 内联timeout配置: timeout=2 |
| 28 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes.py` | 130 | 固定URL: "http://{node[' |
| 29 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes.py` | 133 | 内联timeout配置: timeout=2 |
| 30 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes.py` | 173 | 内联timeout配置: timeout=10 |
| 31 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 235 | 固定URL: "http://{hook_host}:{backend_publ |
| 32 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 264 | 固定URL: "http://{media_host}:{backend_pub |
| 33 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 308 | 固定URL: "http://{node.host}:{node.http_po |
| 34 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 311 | 内联timeout配置: timeout=2 |
| 35 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 385 | 固定URL: "http://{node.host}:{node.http_po |
| 36 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 386 | 固定URL: "http://{node.host}:{node.http_po |
| 37 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 396 | 内联timeout配置: timeout=2 |
| 38 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\media_nodes_db.py` | 406 | 内联timeout配置: timeout=2 |
| 39 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1099 | 内联timeout配置: timeout=0 |
| 40 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\plugin_manager.py` | 1546 | 内联timeout配置: timeout=30 |
| 41 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 47 | 内联timeout配置: timeout=5 |
| 42 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 54 | 内联timeout配置: timeout=5 |
| 43 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 55 | 内联timeout配置: timeout=5 |
| 44 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 70 | 内联timeout配置: timeout=5 |
| 45 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 71 | 内联timeout配置: timeout=5 |
| 46 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 309 | 内联timeout配置: timeout=1 |
| 47 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\redis.py` | 309 | 内联timeout配置: timeout=2 |
| 48 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 95 | 内联timeout配置: timeout=30 |
| 49 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 109 | 内联timeout配置: timeout=120 |
| 50 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 124 | 内联timeout配置: timeout=30 |
| 51 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 164 | 内联timeout配置: timeout=30 |
| 52 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 188 | 内联timeout配置: timeout=20 |
| 53 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 251 | 内联timeout配置: timeout=25 |
| 54 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 272 | 内联timeout配置: timeout=60 |
| 55 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 277 | 内联timeout配置: timeout=60 |
| 56 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 315 | 内联timeout配置: timeout=30 |
| 57 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 349 | 内联timeout配置: timeout=10 |
| 58 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 390 | 内联timeout配置: timeout=10 |
| 59 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 433 | 内联timeout配置: timeout=20 |
| 60 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 458 | 内联timeout配置: timeout=20 |
| 61 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 475 | 内联timeout配置: timeout=10 |
| 62 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 486 | 内联timeout配置: timeout=10 |
| 63 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 508 | 内联timeout配置: timeout=20 |
| 64 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 536 | 内联timeout配置: timeout=20 |
| 65 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 548 | 内联timeout配置: timeout=130 |
| 66 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\core\startup.py` | 647 | 内联timeout配置: timeout=5 |
| 67 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\db\session.py` | 59 | 内联timeout配置: timeout=5 |
| 68 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\db\session.py` | 80 | 内联timeout配置: timeout=5 |
| 69 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 259 | 固定URL: "http://{host}:{port}/index/api/g |
| 70 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 262 | 内联timeout配置: timeout=2 |
| 71 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 573 | 内联timeout配置: timeout=3 |
| 72 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 643 | 内联timeout配置: timeout=5 |
| 73 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 664 | 内联timeout配置: timeout=8 |
| 74 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\health_service.py` | 670 | 内联timeout配置: timeout=8 |
| 75 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\license_service.py` | 224 | 内联timeout配置: timeout=10 |
| 76 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\license_service.py` | 240 | 内联timeout配置: timeout=10 |
| 77 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\media_manager.py` | 187 | 固定URL: "http://{host}:{http_port}/index/ |
| 78 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\media_manager.py` | 190 | 内联timeout配置: timeout=3 |
| 79 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\media_manager.py` | 202 | 固定URL: "http://{host}:{http_port}/index/ |
| 80 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\media_manager.py` | 203 | 内联timeout配置: timeout=2 |
| 81 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\stream_session_service.py` | 52 | 固定URL: "http://{node_host}:{node_http_po |
| 82 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\stream_session_service.py` | 61 | 内联timeout配置: timeout=3 |
| 83 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\stream_session_service.py` | 122 | 固定URL: "http://{node_host}:{node_http_po |
| 84 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\stream_session_service.py` | 131 | 内联timeout配置: timeout=3 |
| 85 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\vision_hub.py` | 109 | 固定URL: "http://{settings.MEDIA_SERVER_HO |
| 86 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_rtp_server_service.py` | 123 | 固定URL: "http://{host}:{http_port}{path}" |
| 87 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 20 | 固定URL: "http://{host}:{http_port}/index/ |
| 88 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 21 | 固定URL: "http://{host}:{http_port}/index/ |
| 89 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 26 | 内联timeout配置: timeout=2 |
| 90 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 27 | 内联timeout配置: timeout=2 |
| 91 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 53 | 固定URL: "http://{host}:{http_port}/index/ |
| 92 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 55 | 内联timeout配置: timeout=2 |
| 93 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 138 | 固定URL: "http://{host}:{http_port}/index/ |
| 94 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 151 | 内联timeout配置: timeout=3 |
| 95 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 166 | 固定URL: "http://{host}:{http_port}/index/ |
| 96 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 175 | 内联timeout配置: timeout=2 |
| 97 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 192 | 固定URL: "http://{host}:{http_port}/index/ |
| 98 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 203 | 内联timeout配置: timeout=5 |
| 99 | medium | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 214 | 固定URL: "http://{host}:{http_port}/index/ |
| 100 | low | hardcode | `E:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend\app\services\zlm_stream_control.py` | 221 | 内联timeout配置: timeout=3 |