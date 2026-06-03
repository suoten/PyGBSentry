import api from '@/utils/http'

export type AuditLogItem = {
  audit_id: string
  module: string
  action: string
  operator: string
  result: string
  summary: string
  plugin_id?: string | null
  source?: string | null
  tenant_id?: string | null
  status_code?: number | null
  created_at: string
}

export type AuditLogListResponse = {
  total: number
  items: AuditLogItem[]
}

export type AuditStatsActionItem = {
  name: string
  count: number
}

export type AuditStatsCodeItem = {
  code: string
  count: number
}

export type AuditStatsResponse = {
  total: number
  failed: number
  top_actions: AuditStatsActionItem[]
  top_status_codes: AuditStatsCodeItem[]
  status_buckets: Record<string, number>
}

export type AuditQuery = {
  module?: string
  action?: string
  action_prefix?: string
  operator?: string
  result?: string
  plugin_id?: string
  source?: string
  tenant_id?: string
  status_code?: number
  status_family?: number
  start_at?: string
  end_at?: string
  page?: number
  page_size?: number
}

export const listAuditLogs = async (query: AuditQuery): Promise<AuditLogListResponse> => {
  const res = await api.get('/api/v1/audit-center/logs', { params: query })
  return res.data
}

export const getAuditStats = async (query: AuditExportQuery): Promise<AuditStatsResponse> => {
  const res = await api.get('/api/v1/audit-center/stats', { params: query })
  return res.data
}

/** 导出 CSV 的查询参数（无分页） */
export type AuditExportQuery = {
  module?: string
  action?: string
  action_prefix?: string
  operator?: string
  result?: string
  plugin_id?: string
  source?: string
  tenant_id?: string
  status_code?: number
  status_family?: number
  start_at?: string
  end_at?: string
}

/** 下载审计日志 CSV（带鉴权，使用当前筛选条件） */
export const downloadAuditCsv = async (params: AuditExportQuery): Promise<void> => {
  const res = await api.get('/api/v1/audit-center/export.csv', {
    params,
    responseType: 'blob'
  })
  const blob = res.data as Blob
  const disposition = res.headers['content-disposition']
  let filename = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`
  if (disposition) {
    const m = disposition.match(/filename=(.+)/i)
    if (m) filename = m[1].trim().replace(/^["']|["']$/g, '')
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
