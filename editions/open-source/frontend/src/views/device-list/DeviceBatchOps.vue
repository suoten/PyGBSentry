<template>
  <DeviceEditDialog v-model="editDialogVisible" :device-data="editDialogDeviceData" @success="emit('editSuccess')" />
  <DeviceAddDialog v-model="addDialogVisible" @success="emit('addSuccess')" />
  <DeviceAccessInfoDialog v-model="accessInfoDialogVisible" />
  <DeviceBlacklistDialog v-model="blacklistDialogVisible" :device-data="blacklistDialogDeviceData" @success="emit('blacklistSuccess')" />
  <DeviceIpBlacklistDialog v-model="ipBlacklistDialogVisible" />
  <CatalogSyncProgressDialog v-model="catalogSyncDialogVisible" :gb-id="catalogSyncDialogGbId" :device-name="catalogSyncDialogName" :runtime="catalogSyncDialogRuntime" :progress-status="catalogSyncProgressStatus" @closed="onCatalogSyncDialogClosed" />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import DeviceEditDialog from '../../components/device/DeviceEditDialog.vue'
import DeviceAddDialog from '../../components/device/DeviceAddDialog.vue'
import DeviceAccessInfoDialog from '../../components/device/DeviceAccessInfoDialog.vue'
import DeviceBlacklistDialog from '../../components/device/DeviceBlacklistDialog.vue'
import DeviceIpBlacklistDialog from '../../components/device/DeviceIpBlacklistDialog.vue'
import CatalogSyncProgressDialog from '../../components/device/CatalogSyncProgressDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'
import { parseDeviceChannelsResponse } from '../../utils/deviceApi'
import { useRouter } from 'vue-router'
import type { Device } from '@/types/models'

const props = defineProps<{ devices: Device[]; selectedDevices: Device[] }>()
const { t } = useI18n()  // FIXED: 国际化
const emit = defineEmits<{
  (e: 'fetchDevices'): void; (e: 'addSuccess'): void; (e: 'editSuccess'): void
  (e: 'blacklistSuccess'): void; (e: 'update:selectedDevices', v: Device[]): void
}>()

const router = useRouter()

// Dialog visibility
const addDialogVisible = ref(false)
const editDialogVisible = ref(false)
const editDialogDeviceData = ref<Device>(null)
const accessInfoDialogVisible = ref(false)
const blacklistDialogVisible = ref(false)
const blacklistDialogDeviceData = ref<Device>(null)
const ipBlacklistDialogVisible = ref(false)

// Inline saving state
const savingMode = ref<Record<string, boolean>>({})
const savingOrg = ref<Record<string, boolean>>({})
const savingCatalogSub = ref<Record<string, boolean>>({})
const savingMobileSub = ref<Record<string, boolean>>({})

// Catalog sync
const catalogSyncPolling = ref<Record<string, boolean>>({})
const catalogSyncPollingTimers: Record<string, number> = {}
let catalogSyncDialogCloseTimer: number | null = null
const catalogSyncDialogVisible = ref(false)
const catalogSyncDialogGbId = ref('')
const catalogSyncDialogName = ref('')
const catalogSyncDialogRuntime = ref<Device>({})

const scheduleCatalogSyncDialogClose = (delayMs = 1600) => {
  clearCatalogSyncDialogCloseTimer()
  catalogSyncDialogCloseTimer = window.setTimeout(() => { catalogSyncDialogVisible.value = false }, Math.max(0, Number(delayMs) || 0))
}
const getCatalogSyncSubText = (runtime: Record<string, unknown>) => {
  const state = String(runtime?.['catalog.sync_state'] || '').trim()
  const errorText = String(runtime?.['catalog.last_error'] || '').trim()
  const total = Number(runtime?.['catalog.last_sum_num'] || 0)
  const received = Number(runtime?.['catalog.last_received_total'] || 0)
  if (state === 'synced') return total > 0 ? `目录同步完成（${Math.max(0, received)}/${total}）` : '目录同步完成'
  if (state === 'partial') return total > 0 ? `已接收目录（${Math.max(0, received)}/${total}）` : '已收到部分目录，正在继续处理'
  if (state === 'query_failed') return errorText ? `目录查询失败：${errorText}` : '目录查询失败'
  if (state === 'query_timeout') return '目录查询超时，请稍后重试'
  if (state === 'query_sent') { const r = Number(runtime?.['catalog.retry_attempts'] || 1); return r > 1 ? `已发起目录请求（第 ${r} 次）` : '已发起目录请求，等待设备响应' }
  if (state === 'response_received') return '已收到设备响应，正在处理目录数据'
  return errorText || ''
}
const clearCatalogSyncDialogCloseTimer = () => { if (catalogSyncDialogCloseTimer != null) { window.clearTimeout(catalogSyncDialogCloseTimer); catalogSyncDialogCloseTimer = null } }
const catalogSyncProgressStatus = computed((): 'success' | 'exception' | undefined => {
  const state = String((catalogSyncDialogRuntime.value || {})?.['catalog.sync_state'] || '').trim()
  if (state === 'synced') return 'success'
  if (state === 'query_failed' || state === 'query_timeout') return 'exception'
  return undefined
})
const onCatalogSyncDialogClosed = () => {
  clearCatalogSyncDialogCloseTimer()
  const key = String(catalogSyncDialogGbId.value || '').trim()
  if (key && catalogSyncPollingTimers[key]) { window.clearInterval(catalogSyncPollingTimers[key]); delete catalogSyncPollingTimers[key] }
  if (key) catalogSyncPolling.value = { ...catalogSyncPolling.value, [key]: false }
  catalogSyncDialogGbId.value = ''; catalogSyncDialogName.value = ''; catalogSyncDialogRuntime.value = {}
}
const finishCatalogSyncPollingKey = (key: string) => {
  if (catalogSyncPollingTimers[key]) { window.clearInterval(catalogSyncPollingTimers[key]); delete catalogSyncPollingTimers[key] }
  catalogSyncPolling.value = { ...catalogSyncPolling.value, [key]: false }
}
const startCatalogSyncPolling = (gbId: string) => {
  const key = String(gbId || '').trim()
  if (!key) return
  if (catalogSyncPollingTimers[key]) { window.clearInterval(catalogSyncPollingTimers[key]); delete catalogSyncPollingTimers[key] }
  let round = 0; const maxRounds = 15; const intervalMs = 2000
  catalogSyncPolling.value = { ...catalogSyncPolling.value, [key]: true }
  catalogSyncPollingTimers[key] = window.setInterval(async () => {
    round += 1
    try {
      const res = await api.get(`/api/v1/devices/${key}/catalog-runtime`)
      const runtime = res.data?.catalog_sync_runtime || {}
      const idx = props.devices.findIndex((d: Record<string, unknown>) => String(d?.gb_id || '') === key)
      if (idx >= 0) props.devices[idx] = { ...props.devices[idx], catalog_sync_runtime: runtime }
      if (catalogSyncDialogVisible.value && catalogSyncDialogGbId.value === key) catalogSyncDialogRuntime.value = runtime
      const state = String(runtime?.['catalog.sync_state'] || '').trim()
      if (state === 'synced' || state === 'query_failed' || state === 'query_timeout') {
        finishCatalogSyncPollingKey(key)
        if (catalogSyncDialogVisible.value && catalogSyncDialogGbId.value === key) {
          if (state === 'synced') ElMessage.success('目录同步完成')
          else ElMessage.error(getCatalogSyncSubText(runtime) || (state === 'query_failed' ? '目录查询失败' : '目录同步超时'))
          scheduleCatalogSyncDialogClose()
        }
        return
      }
    } catch { /* ignore */ }
    if (round >= maxRounds) {
      finishCatalogSyncPollingKey(key)
      if (catalogSyncDialogVisible.value && catalogSyncDialogGbId.value === key) { ElMessage.warning('未在预定时间内收到目录同步结束状态，请稍后刷新列表查看'); scheduleCatalogSyncDialogClose() }
    }
  }, intervalMs)
}

// Public actions
const openAddDialog = () => { addDialogVisible.value = true }
const openAccessInfoDialog = () => { accessInfoDialogVisible.value = true }
const openIpBlacklistDialog = () => { ipBlacklistDialogVisible.value = true }
const handleEdit = (row: Record<string, unknown>) => { editDialogDeviceData.value = row; editDialogVisible.value = true }
const handleDelete = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(`确定要删除设备 "${row.name || row.gb_id}" 吗？此操作不可恢复！`, '确认删除', { confirmButtonText: t('common.ok'), cancelButtonText: t('common.cancel'), type: 'warning' })
    await api.delete(`/api/v1/devices/${row.gb_id}`); ElMessage.success('设备删除成功'); emit('fetchDevices')
  } catch (e: unknown) { if (e !== 'cancel') { const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message) } }
}
const handleBatchDelete = () => {
  if (props.selectedDevices.length === 0) return
  ElMessageBox.confirm(`确定要删除选中的 ${props.selectedDevices.length} 个设备吗？删除后无法恢复！`, '确认批量删除', { confirmButtonText: '确定删除', cancelButtonText: t('common.cancel'), type: 'error' }).then(async () => {
    try { const gb_ids = props.selectedDevices.map(d => d.gb_id); const res = await api.post('/api/v1/devices/batch-delete', { gb_ids }); ElMessage.success(`已删除 ${res.data?.deleted_count ?? gb_ids.length} 台设备`); emit('update:selectedDevices', [] as Device[]); emit('fetchDevices') } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) }
  }).catch(() => {})
}
const handleBlacklist = (row: Record<string, unknown>) => { blacklistDialogDeviceData.value = row; blacklistDialogVisible.value = true }
const handleAlarm = async (row: Record<string, unknown>, isOn: boolean) => {
  try {
    const action = isOn ? '布防' : '撤防'; const guardCmd = isOn ? 'SetGuard' : 'ResetGuard'
    const channelsRes = await api.get(`/api/v1/devices/${row.gb_id}/channels`); const channels = parseDeviceChannelsResponse(channelsRes.data)
    if (channels.length === 0) { ElMessage.warning('该设备没有可用通道，无法执行操作'); return }
    await api.post(`/api/v1/control/${row.gb_id}/${channels[0].gb_id}/guard`, { guard_cmd: guardCmd }); ElMessage.success(`${action}命令已发送`)
  } catch (e: unknown) { const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message) }
}
const showDevicePosition = (row: Record<string, unknown>) => { const id = String(row?.gb_id || '').trim(); if (id) router.push(`/map?deviceId=${encodeURIComponent(id)}`) }
const syncBasicParam = async (row: Record<string, unknown>) => {
  try { await api.post(`/api/v1/devices/${row.gb_id}/sync`); ElMessage.success('已发送设备配置同步请求，请稍后刷新查看设备参数') } catch (e: unknown) { const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message) }
}
const syncDeviceChannels = async (row: Record<string, unknown>) => {
  if (!row?.gb_id) return; const gbId = String(row.gb_id || '').trim()
  try {
    clearCatalogSyncDialogCloseTimer(); catalogSyncDialogGbId.value = gbId; catalogSyncDialogName.value = String(row.name || '').trim(); catalogSyncDialogRuntime.value = {}; catalogSyncDialogVisible.value = true
    await api.post(`/api/v1/devices/${gbId}/sync`); emit('fetchDevices')
    const idx = props.devices.findIndex((d: Record<string, unknown>) => String(d?.gb_id || '') === gbId)
    if (idx >= 0 && props.devices[idx]?.catalog_sync_runtime) catalogSyncDialogRuntime.value = { ...props.devices[idx].catalog_sync_runtime }
    startCatalogSyncPolling(gbId)
  } catch (e: unknown) { catalogSyncDialogVisible.value = false; clearCatalogSyncDialogCloseTimer(); catalogSyncDialogGbId.value = ''; catalogSyncDialogName.value = ''; catalogSyncDialogRuntime.value = {}; const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message) }
}
const handleAlarmDropdownCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'edit') { handleEdit(row); return } if (cmd === 'on') { await handleAlarm(row, true); return } if (cmd === 'off') { await handleAlarm(row, false); return }
  if (cmd === 'map') { showDevicePosition(row); return } if (cmd === 'syncBasic') { await syncBasicParam(row); return } if (cmd === 'blacklist') { handleBlacklist(row); return }
  if (cmd === 'teleboot') { await handleTeleboot(row); return }
  if (cmd === 'recordStart') { await handleRecordControl(row, 'VideoRecord'); return }
  if (cmd === 'recordStop') { await handleRecordControl(row, 'StopRecord'); return }
  if (cmd === 'alarmReset') { await handleAlarmReset(row); return }
  if (cmd === 'iframe') { await handleIFrame(row); return }
  if (cmd === 'delete') await handleDelete(row)
}

const getFirstChannelId = async (deviceId: string): Promise<string | null> => {
  try {
    const res = await api.get(`/api/v1/devices/${deviceId}/channels`)
    const channels = parseDeviceChannelsResponse(res.data)
    return channels.length > 0 ? channels[0].gb_id : null
  } catch { return null }
}

const handleTeleboot = async (row: Record<string, unknown>) => {
  const gbId = String(row?.gb_id || '').trim()
  if (!gbId) return
  try {
    await ElMessageBox.confirm(`确定远程重启设备「${row.name || gbId}」？设备将重新启动。`, '远程重启', { type: 'warning' })
  } catch { return }
  try {
    await api.post(`/api/v1/control/${gbId}/teleboot`)
    ElMessage.success('远程重启命令已发送')
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  }
}

const handleRecordControl = async (row: Record<string, unknown>, recordCmd: string) => {
  const gbId = String(row?.gb_id || '').trim()
  if (!gbId) return
  const channelId = await getFirstChannelId(gbId)
  if (!channelId) { ElMessage.warning('该设备没有可用通道，无法执行录像控制'); return }
  const action = recordCmd === 'VideoRecord' ? '开始录像' : '停止录像'
  try {
    await ElMessageBox.confirm(`确定对设备「${row.name || gbId}」执行${action}？`, action, { type: 'info' })
  } catch { return }
  try {
    await api.post(`/api/v1/control/${gbId}/${channelId}/record`, { record_cmd: recordCmd })
    ElMessage.success(`${action}命令已发送`)
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  }
}

const handleAlarmReset = async (row: Record<string, unknown>) => {
  const gbId = String(row?.gb_id || '').trim()
  if (!gbId) return
  const channelId = await getFirstChannelId(gbId)
  if (!channelId) { ElMessage.warning('该设备没有可用通道，无法执行告警复位'); return }
  try {
    await ElMessageBox.confirm(`确定对设备「${row.name || gbId}」执行告警复位？`, '告警复位', { type: 'warning' })
  } catch { return }
  try {
    await api.post(`/api/v1/control/${gbId}/${channelId}/alarm-reset`, { alarm_method: 'All', alarm_type: 'All' })
    ElMessage.success('告警复位命令已发送')
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  }
}

const handleIFrame = async (row: Record<string, unknown>) => {
  const gbId = String(row?.gb_id || '').trim()
  if (!gbId) return
  const channelId = await getFirstChannelId(gbId)
  if (!channelId) { ElMessage.warning('该设备没有可用通道，无法请求关键帧'); return }
  try {
    await api.post(`/api/v1/control/${gbId}/${channelId}/iframe`)
    ElMessage.success('强制关键帧命令已发送')
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  }
}

// Inline save with loading state
const saveOrganization = async (row: Record<string, unknown>) => {
  const gbId = String(row?.gb_id || '').trim(); if (!gbId) return
  savingOrg.value = { ...savingOrg.value, [gbId]: true }
  try { await api.put(`/api/v1/devices/${gbId}/organization`, { organization_id: row?.organization_id || null }); ElMessage.success('组织已更新') } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) } finally { savingOrg.value = { ...savingOrg.value, [gbId]: false } }
}
const saveStreamMode = async (row: Record<string, unknown>) => {
  const gbId = String(row?.gb_id || '').trim(); if (!gbId) return
  savingMode.value = { ...savingMode.value, [gbId]: true }
  try { await api.put(`/api/v1/devices/${gbId}/stream-mode`, { stream_mode: String(row?.stream_mode || 'GLOBAL') }); ElMessage.success('流模式已更新') } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) } finally { savingMode.value = { ...savingMode.value, [gbId]: false } }
}
const toggleCatalogSubscribe = async (row: Record<string, unknown>, enabled?: boolean) => {
  const gbId = String(row?.gb_id || '').trim(); if (!gbId) return; const next = enabled == null ? !!row?.catalog_subscribe_enabled : !!enabled
  savingCatalogSub.value = { ...savingCatalogSub.value, [gbId]: true }
  try { await api.put(`/api/v1/devices/${gbId}/subscriptions/catalog`, { enabled: next, cycle_seconds: Number(row?.catalog_subscribe_cycle_seconds || 300) }); row.catalog_subscribe_enabled = next; ElMessage.success(next ? '目录订阅已开启' : '目录订阅已关闭') } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) } finally { savingCatalogSub.value = { ...savingCatalogSub.value, [gbId]: false } }
}
const setCatalogSubscribeCycle = async (row: Record<string, unknown>) => {
  try {
    const res = await ElMessageBox.prompt('请输入目录订阅周期（秒）', '设置周期', { confirmButtonText: t('common.ok'), cancelButtonText: t('common.cancel'), inputValue: String(Number(row?.catalog_subscribe_cycle_seconds || 300)), inputPattern: /^\d+$/, inputErrorMessage: t('common.enterPositiveInteger') })
    const cycle = Math.max(1, Number(String(res.value || '').trim() || 300)); row.catalog_subscribe_cycle_seconds = cycle
    await api.put(`/api/v1/devices/${String(row?.gb_id || '').trim()}/subscriptions/catalog`, { enabled: !!row?.catalog_subscribe_enabled, cycle_seconds: cycle }); ElMessage.success('目录订阅周期已更新')
  } catch (e: unknown) { if (e === 'cancel') return; ElMessage.error(getFriendlyError(e).message) }
}
const toggleMobileSubscribe = async (row: Record<string, unknown>, enabled?: boolean) => {
  const gbId = String(row?.gb_id || '').trim(); if (!gbId) return; const next = enabled == null ? !!row?.mobile_position_subscribe_enabled : !!enabled
  savingMobileSub.value = { ...savingMobileSub.value, [gbId]: true }
  try { await api.put(`/api/v1/devices/${gbId}/subscriptions/mobile-position`, { enabled: next, interval_seconds: Number(row?.mobile_position_interval_seconds || 60) }); row.mobile_position_subscribe_enabled = next; ElMessage.success(next ? '位置订阅已开启' : '位置订阅已关闭') } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) } finally { savingMobileSub.value = { ...savingMobileSub.value, [gbId]: false } }
}
const setMobileSubscribeInterval = async (row: Record<string, unknown>) => {
  try {
    const res = await ElMessageBox.prompt('请输入位置上报间隔（秒）', '设置间隔', { confirmButtonText: t('common.ok'), cancelButtonText: t('common.cancel'), inputValue: String(Number(row?.mobile_position_interval_seconds || 60)), inputPattern: /^\d+$/, inputErrorMessage: t('common.enterPositiveInteger') })
    const interval = Math.max(1, Number(String(res.value || '').trim() || 60)); row.mobile_position_interval_seconds = interval
    await api.put(`/api/v1/devices/${String(row?.gb_id || '').trim()}/subscriptions/mobile-position`, { enabled: !!row?.mobile_position_subscribe_enabled, interval_seconds: interval }); ElMessage.success('位置上报间隔已更新')
  } catch (e: unknown) { if (e === 'cancel') return; ElMessage.error(getFriendlyError(e).message) }
}
const exportToCsv = (organizationOptions: { id: string; label: string }[]) => {
  if (!props.devices || props.devices.length === 0) { ElMessage.warning('当前列表没有数据可以导出'); return }
  const headers = ['国标ID', '设备名称', '状态', 'IP地址', '所属组织', '厂家', '通道数', '最近活跃时间', '流模式']
  const rows = props.devices.map(d => { const org = organizationOptions.find(o => o.id === d.organization_id)?.label || '未分配'; const status = (Number(d.status) === 1 || d.status === 'Online') ? '在线' : '离线'; return [`\t${d.gb_id}`, d.name || '', status, d.ip_addr || '', org, d.manufacturer || '', d.channel_count || 0, d.last_keepalive ? new Date(d.last_keepalive).toLocaleString() : '', d.stream_mode || 'GLOBAL'] })
  let csv = '\uFEFF'; csv += headers.join(',') + '\n'; rows.forEach(r => { csv += r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',') + '\n' })
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.setAttribute('download', `设备台账_${new Date().toISOString().slice(0,10)}.csv`); document.body.appendChild(link); link.click(); document.body.removeChild(link)
}

const exportingDevices = ref(false)
const exportDevicesFromServer = async (format: 'csv' | 'json' = 'csv', includeChannels = false) => {
  exportingDevices.value = true
  try {
    const gbIds = props.selectedDevices.length > 0 ? props.selectedDevices.map(d => d.gb_id) : undefined
    const res = await api.post('/api/v1/devices/export', {
      format,
      include_channels: includeChannels,
      gb_ids: gbIds
    }, { responseType: format === 'json' ? 'json' : 'blob' })
    if (format === 'json') {
      const content = JSON.stringify(res.data, null, 2)
      const blob = new Blob([content], { type: 'application/json;charset=utf-8;' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.setAttribute('download', `devices_export_${new Date().toISOString().slice(0, 19).replace(/:/g, '')}.json`)
      document.body.appendChild(link); link.click(); document.body.removeChild(link)
    } else {
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      const contentDisposition = res.headers?.['content-disposition']
      let filename = `devices_export_${new Date().toISOString().slice(0, 19).replace(/:/g, '')}.csv`
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/)
        if (match?.[1]) filename = match[1].replace(/["']/g, '')
      }
      link.setAttribute('download', filename)
      document.body.appendChild(link); link.click(); document.body.removeChild(link)
    }
    ElMessage.success('设备导出成功')
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  } finally {
    exportingDevices.value = false
  }
}

const batchSnapping = ref(false)
const batchSnapshot = async () => {
  if (props.selectedDevices.length === 0) { ElMessage.warning('请先选择设备'); return }
  batchSnapping.value = true
  try {
    const channelIds: string[] = []
    for (const d of props.selectedDevices) {
      const gbId = String(d?.gb_id || '').trim()
      if (!gbId) continue
      try {
        const res = await api.get(`/api/v1/devices/${gbId}/channels`)
        const channels = parseDeviceChannelsResponse(res.data)
        for (const ch of channels) {
          if (ch.gb_id) channelIds.push(ch.gb_id)
        }
      } catch { continue }
    }
    if (channelIds.length === 0) { ElMessage.warning('所选设备没有可用通道'); return }
    await ElMessageBox.confirm(`将为 ${props.selectedDevices.length} 台设备的 ${channelIds.length} 个通道刷新截图，可能需要较长时间。是否继续？`, '批量截图', { type: 'info' })
    const res = await api.post('/api/v1/devices/channels/snap-batch', { channel_ids: channelIds })
    const ok = Number(res.data?.ok || 0)
    const failed = Number(res.data?.failed || 0)
    ElMessage.success(`批量截图完成：成功 ${ok}，失败 ${failed}`)
  } catch (e: unknown) {
    if (e === 'cancel') return
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  } finally {
    batchSnapping.value = false
  }
}

defineExpose({
  openAddDialog, openAccessInfoDialog, openIpBlacklistDialog, handleEdit, handleDelete, handleBatchDelete,
  handleBlacklist, handleAlarm, showDevicePosition, syncBasicParam, syncDeviceChannels, handleAlarmDropdownCommand,
  saveOrganization, saveStreamMode, toggleCatalogSubscribe, setCatalogSubscribeCycle, toggleMobileSubscribe,
  setMobileSubscribeInterval, exportToCsv, exportDevicesFromServer, batchSnapshot, catalogSyncPolling, savingMode, savingOrg, savingCatalogSub, savingMobileSub,
  clearCatalogSyncDialogCloseTimer, catalogSyncPollingTimers, exportingDevices, batchSnapping,
})
</script>
