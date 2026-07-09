import api from '../utils/http'
export const deviceApi = {
  async list(params?: Record<string, unknown>) { const res = await api.get('/api/v1/devices', { params }); return res.data },
  async get(id: string) { const res = await api.get(`/api/v1/devices/${id}`); return res.data },
}
