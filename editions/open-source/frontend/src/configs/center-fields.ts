import type { FieldSchema } from '../types/center-fields'

export type ConfigCenterFieldKey =
  | 'streamPullTimeout'
  | 'alarmDefaultLevel'
  | 'deviceHeartbeatInterval'
  | 'recordAutoCleanDays'
  | 'logRetentionDays'

export type ReleasePublishFieldKey = 'draftId' | 'publishNote'
export type ReleaseRollbackFieldKey = 'targetRevision' | 'reason'
export type AuditFilterFieldKey = 'module' | 'operator' | 'result' | 'plugin_id' | 'source' | 'tenant_id' | 'date_range'

export const configCenterFields: FieldSchema<ConfigCenterFieldKey>[] = [
  { key: 'streamPullTimeout', label: '拉流超时（秒）', component: 'number', min: 1, max: 120, required: true, hint: '拉流建立连接的最长等待时间，超时则提示拉流失败' },
  {
    key: 'alarmDefaultLevel',
    label: '默认告警等级',
    component: 'select',
    required: true,
    options: [
      { label: 'low', value: 'low' },
      { label: 'medium', value: 'medium' },
      { label: 'high', value: 'high' }
    ]
  },
  {
    key: 'deviceHeartbeatInterval',
    label: '设备心跳间隔（秒）',
    component: 'number',
    min: 10,
    max: 300,
    hint: '设备心跳检测间隔，建议 30-60 秒'
  },
  {
    key: 'recordAutoCleanDays',
    label: '录像自动清理（天）',
    component: 'number',
    min: 0,
    max: 365,
    hint: '0 表示不自动清理，否则按天数自动删除旧录像'
  },
  {
    key: 'logRetentionDays',
    label: '日志保留天数',
    component: 'number',
    min: 1,
    max: 90,
    hint: '系统日志保留天数，超期日志自动清理'
  }
]

export const releasePublishFields: FieldSchema<ReleasePublishFieldKey>[] = [
  {
    key: 'draftId',
    label: '当前草稿 ID',
    component: 'input',
    placeholder: 'dr_xxx',
    required: true,
    pattern: '^dr_[a-zA-Z0-9]+$',
    patternMessage: '草稿 ID 格式应为 dr_xxx'
  },
  { key: 'publishNote', label: '发布备注', component: 'input', placeholder: '可选' }
]

export const releaseRollbackFields: FieldSchema<ReleaseRollbackFieldKey>[] = [
  { key: 'targetRevision', label: '目标 Revision', component: 'number', required: true, min: 1 },
  { key: 'reason', label: '回滚原因', component: 'input', placeholder: '可选' }
]

export const auditFilterFields: FieldSchema<AuditFilterFieldKey>[] = [
  { key: 'module', label: '模块', component: 'input', placeholder: 'auth / users / roles / regions / platforms / push-channels / record-schedule / asset-management / alarms / work-orders / map / channel-import / rtp / blacklist / devices / organizations / system-config / ops / setup / config-center / release-center / billing / command / plugins / integrations / control / stream / device-record / record / hook / reports', maxLength: 64 },
  { key: 'operator', label: '操作人', component: 'input', placeholder: '用户名', maxLength: 64 },
  {
    key: 'result',
    label: '结果',
    component: 'select',
    options: [
      { label: 'success', value: 'success' },
      { label: 'failed', value: 'failed' },
      { label: 'rollback', value: 'rollback' }
    ]
  },
  { key: 'plugin_id', label: '插件ID', component: 'input', placeholder: '如 mobile_app_suite', maxLength: 64 },
  { key: 'source', label: '来源', component: 'input', placeholder: '如 login/register/2fa/bearer/api_key/rbac/setup_wizard/ops_api/role_admin/region_admin/platform_admin/push_channel_admin/record_schedule_admin/asset_admin/alarm_admin/work_order_admin/map_admin/map_config/channel_import/rtp_admin/ip_blacklist/device_admin/org_admin/system_settings/app_logs/user_admin/payment_callback/command_console/release_center/plugin_runtime/plugin_license/plugin_alert_test/integrations/device_control/stream_console/device-record_query/record_query/zlm_hook/config_center/report_suite_config', maxLength: 64 },
  { key: 'tenant_id', label: '租户', component: 'input', placeholder: '如 default', maxLength: 64 },
  { key: 'date_range', label: '时间范围', component: 'daterange' }
]
