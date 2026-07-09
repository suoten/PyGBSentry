import type { FieldSchema } from '../types/center-fields'

export type ConfigCenterFieldKey =
  | 'streamPullTimeout'
  | 'alarmDefaultLevel'
  | 'deviceHeartbeatInterval'
  | 'recordAutoCleanDays'
  | 'logRetentionDays'

export type ReleasePublishFieldKey = 'draftId' | 'publishNote'
export type ReleaseRollbackFieldKey = 'targetRevision' | 'reason'
export type AuditFilterFieldKey = 'module' | 'operator' | 'result' | 'plugin_id' | 'source' | 'date_range'

export const configCenterFields: FieldSchema<ConfigCenterFieldKey>[] = [
  { key: 'streamPullTimeout', label: 'configCenter.fields.streamPullTimeout', component: 'number', min: 1, max: 120, required: true, hint: 'configCenter.fields.streamPullTimeoutHint' },
  {
    key: 'alarmDefaultLevel',
    label: 'configCenter.fields.alarmDefaultLevel',
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
    label: 'configCenter.fields.deviceHeartbeatInterval',
    component: 'number',
    min: 10,
    max: 300,
    hint: 'configCenter.fields.deviceHeartbeatHint'
  },
  {
    key: 'recordAutoCleanDays',
    label: 'configCenter.fields.recordAutoCleanDays',
    component: 'number',
    min: 0,
    max: 365,
    hint: 'configCenter.fields.recordAutoCleanHint'
  },
  {
    key: 'logRetentionDays',
    label: 'configCenter.fields.logRetentionDays',
    component: 'number',
    min: 1,
    max: 90,
    hint: 'configCenter.fields.logRetentionHint'
  }
]

export const releasePublishFields: FieldSchema<ReleasePublishFieldKey>[] = [
  {
    key: 'draftId',
    label: 'releaseCenter.draftIdLabel',
    component: 'input',
    placeholder: 'dr_xxx',
    required: true,
    pattern: '^dr_[a-zA-Z0-9]+$',
    patternMessage: 'releaseCenter.draftIdPatternMessage'
  },
  { key: 'publishNote', label: 'releaseCenter.publishNoteLabel', component: 'input', placeholder: 'releaseCenter.optionalPlaceholder' }
]

export const releaseRollbackFields: FieldSchema<ReleaseRollbackFieldKey>[] = [
  { key: 'targetRevision', label: 'releaseCenter.targetRevisionLabel', component: 'number', required: true, min: 1 },
  { key: 'reason', label: 'releaseCenter.rollbackReasonLabel', component: 'input', placeholder: 'releaseCenter.optionalPlaceholder' }
]

export const auditFilterFields: FieldSchema<AuditFilterFieldKey>[] = [
  { key: 'module', label: 'audit.module', component: 'input', placeholder: 'audit.modulePlaceholder', maxLength: 64 },
  { key: 'operator', label: 'audit.operator', component: 'input', placeholder: 'audit.operatorPlaceholder', maxLength: 64 },
  {
    key: 'result',
    label: 'audit.resultLabel',
    component: 'select',
    options: [
      { label: 'success', value: 'success' },
      { label: 'failed', value: 'failed' },
      { label: 'rollback', value: 'rollback' }
    ]
  },
  { key: 'plugin_id', label: 'audit.pluginId', component: 'input', placeholder: 'audit.pluginIdPlaceholder', maxLength: 64 },
  { key: 'source', label: 'audit.source', component: 'input', placeholder: 'audit.sourcePlaceholder', maxLength: 64 },
  // FIX H-8: 移除 tenant_id 过滤字段，防止非超管用户跨租户查询审计日志
  { key: 'date_range', label: 'audit.dateRangeLabel', component: 'daterange' }
]
