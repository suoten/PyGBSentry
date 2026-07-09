import api from '../utils/http'
export interface AuditLogItem { id?: string; [k: string]: unknown }
export interface AuditStatsResponse { total?: number; [k: string]: unknown }
export async function listAuditLogs(params?: Record<string, unknown>) { const res = await api.get('/api/v1/audit/logs', { params }); return res.data ?? { items: [], total: 0 } }
export async function getAuditStats(params?: Record<string, unknown>) { const res = await api.get('/api/v1/audit/stats', { params }); return res.data ?? {} }
export async function downloadAuditCsv(params?: Record<string, unknown>) { const res = await api.get('/api/v1/audit/logs/export', { params, responseType: 'blob' }); return res.data }
