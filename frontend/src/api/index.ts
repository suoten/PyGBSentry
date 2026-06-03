import api from '@/utils/http'

export const deviceApi = {
  list: (params?: Record<string, unknown>) =>
    api.get('/api/v1/devices', { params }),
  batchDelete: (gbIds: string[]) =>
    api.post('/api/v1/devices/batch-delete', { gb_ids: gbIds }),
  getChannels: (gbId: string, params?: Record<string, unknown>) =>
    api.get(`/api/v1/devices/${gbId}/channels`, { params }),
  updateOrganization: (gbId: string, organizationId: string | null) =>
    api.put(`/api/v1/devices/${gbId}/organization`, { organization_id: organizationId }),
  updateStreamMode: (gbId: string, streamMode: string) =>
    api.put(`/api/v1/devices/${gbId}/stream-mode`, { stream_mode: streamMode }),
  updateCatalogSubscription: (gbId: string, enabled: boolean, cycleSeconds?: number) =>
    api.put(`/api/v1/devices/${gbId}/subscriptions/catalog`, { enabled, cycle_seconds: cycleSeconds }),
  updateMobilePositionSubscription: (gbId: string, enabled: boolean, intervalSeconds?: number) =>
    api.put(`/api/v1/devices/${gbId}/subscriptions/mobile-position`, { enabled, interval_seconds: intervalSeconds }),
}

export const channelApi = {
  list: (params?: Record<string, unknown>) =>
    api.get('/api/common/channel/list', { params }),
  flatList: (deviceId: string, keyword?: string, limit?: number) =>
    api.get('/api/v1/devices/channels/flat', { params: { device_id: deviceId, keyword, limit } }),
  update: (channelId: string, data: Record<string, unknown>) =>
    api.put(`/api/v1/devices/channels/${encodeURIComponent(channelId)}`, data),
  addToRegion: (civilCode: string, channelIds: string[]) =>
    api.post('/api/common/channel/region/add', { civilCode, channelIds: channelIds.map(Number) }),  // FIXED: 后端期望list[int]
  addToGroup: (groupId: string, channelIds: string[], groupName?: string) =>
    api.post('/api/common/channel/group/add', { parentId: groupId, channelIds, businessGroup: groupName || '' }),  // FIXED: 参数名与后端模型对齐
  reset: (channelId: string, channelFields: string[] = []) =>
    api.post('/api/common/channel/reset', { id: Number(channelId), channelFields }),  // FIXED: 参数名/类型与后端模型对齐
  stopPlay: (streamId: string) =>
    api.post('/api/common/channel/play/stop', { app: 'live', stream: streamId }),  // FIXED: I9 play/stop从GET改为POST
  streamStatus: (params?: Record<string, unknown>) =>
    api.get('/api/common/channel/stream-status', { params }),
}

export const streamApi = {
  stop: (app: string, stream: string) =>
    api.post('/api/v1/stream/stop', { app, stream }),
}

export const alarmApi = {
  listNotifications: (params?: Record<string, unknown>) =>
    api.get('/api/v1/alarms/notifications', { params }),
  testAlert: (channel: string) =>
    api.post('/api/v1/plugins/alert-test', { channel }),
}

export const streamOptApi = {
  optimizedPlay: (deviceId: string, channelId: string, params?: Record<string, unknown>) =>
    api.get(`/api/v1/stream-opt/play/${deviceId}/${channelId}`, { params }),
  reportQuality: (data: Record<string, unknown>) =>
    api.post('/api/v1/stream-opt/quality-report', data),
  getHealth: (sessionId: string) =>
    api.get(`/api/v1/stream-opt/health/${sessionId}`),
  getLines: (deviceId: string, channelId: string) =>
    api.get(`/api/v1/stream-opt/lines/${deviceId}/${channelId}`),
  reconnect: (sessionId: string) =>
    api.post(`/api/v1/stream-opt/reconnect/${sessionId}`),
  closeSession: (sessionId: string) =>
    api.delete(`/api/v1/stream-opt/session/${sessionId}`),
  getStats: () =>
    api.get('/api/v1/stream-opt/stats'),
  getProtocolInfo: () =>
    api.get('/api/v1/stream-opt/protocol-info'),
  getOptimizationTips: () =>
    api.get('/api/v1/stream-opt/optimization-tips'),
}

export const appApi = {
  logs: (params?: Record<string, unknown>) =>
    api.get('/api/v1/apps/logs', { params }),
  stats: (params?: Record<string, unknown>) =>
    api.get('/api/v1/apps/stats', { params }),
  versionCheck: (params?: Record<string, unknown>) =>
    api.get('/api/v1/plugins/app-version-check', { params }),
  remoteConfig: (params?: Record<string, unknown>) =>
    api.get('/api/v1/apps/remote-config', { params }),
}
