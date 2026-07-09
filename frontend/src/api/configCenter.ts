import api from '../utils/http'
export async function getCurrentDraft(scope?: string) { const res = await api.get('/api/v1/config-center/draft', { params: { scope } }); return res.data ?? {} }
