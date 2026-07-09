import api from '../utils/http'
export interface DiffItem { key?: string; old_value?: unknown; new_value?: unknown; [k: string]: unknown }
export async function getDraftDiff(scope?: string) { const res = await api.get('/api/v1/release-center/draft/diff', { params: { scope } }); return res.data ?? [] }
export async function publishDraft(scope?: string) { const res = await api.post('/api/v1/release-center/draft/publish', { scope }); return res.data ?? {} }
export async function rollbackRevision(revision: string) { const res = await api.post('/api/v1/release-center/rollback', { revision }); return res.data ?? {} }
