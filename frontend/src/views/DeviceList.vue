<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('device.title')" :description="t('device.listDescription')">
          <template #actions>
            <el-button type="primary" @click="onOpenAddDialog" class="action-btn"><el-icon class="mr-1"><Plus /></el-icon>{{ t('device.addDevice') }}</el-button>
            <el-button type="warning" plain @click="onOpenIpBlacklistDialog" class="action-btn"><el-icon class="mr-1"><Warning /></el-icon>{{ t('device.ipBlacklist') }}</el-button>
            <el-button @click="onOpenAccessInfoDialog" class="action-btn"><el-icon class="mr-1"><InfoFilled /></el-icon>{{ t('device.accessInfo.title') }}</el-button>
            <el-tooltip :content="t('device.refreshList')" placement="top"><el-button @click="refreshDevices" circle class="action-btn refresh-btn"><el-icon><Refresh /></el-icon></el-button></el-tooltip>
            <el-tooltip :content="autoRefresh ? t('device.stopAutoRefresh') : t('device.startAutoRefresh')" placement="top"><el-button @click="toggleAutoRefresh" :type="autoRefresh ? 'success' : 'default'" plain circle class="action-btn"><el-icon><Timer /></el-icon></el-button></el-tooltip>
            <el-button type="success" plain @click="onExportCsv" class="action-btn"><el-icon class="mr-1"><Download /></el-icon>{{ t('device.exportLedger') }}</el-button>
            <el-dropdown class="ml-2" @command="onExportCommand">
              <el-button type="success" plain class="action-btn"><el-icon class="mr-1"><Download /></el-icon>{{ t('device.serverExport') }}<el-icon class="ml-1"><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="csv">{{ t('device.csvWithChannels') }}</el-dropdown-item>
                  <el-dropdown-item command="json">{{ t('device.jsonWithChannels') }}</el-dropdown-item>
                  <el-dropdown-item command="csv-no-channels">{{ t('device.csvDeviceOnly') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button type="primary" plain @click="onBatchSnapshot" :loading="batchSnapping" class="action-btn ml-2"><el-icon class="mr-1"><Camera /></el-icon>{{ t('device.batchSnapshot') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <DeviceFilterBar ref="filterBar" :organization-options="organizationOptions" :total-display="totalDisplay" :device-stats-total="deviceStatsTotal" :device-stats-online="deviceStatsOnline" :device-stats-offline="deviceStatsOffline" :page-size="pageSize" @search="handleSearch" />

      <DeviceTable :devices="devices" :loading="loading" :devices-empty-text="devicesEmptyText" :total-display="totalDisplay" :page="page" :page-size="pageSize" :current-device="currentDevice" :dialog-visible="dialogVisible" :selected-devices="selectedDevices" :saving-mode="savingMode" :saving-org="savingOrg" :saving-catalog-sub="savingCatalogSub" :saving-mobile-sub="savingMobileSub" :catalog-sync-polling="catalogSyncPolling" :organization-options="organizationOptions" @update:page="(v: number) => page = v" @update:page-size="(v: number) => pageSize = v" @fetch-devices="fetchDevices" @page-size-change="handlePageSizeChange" @view-device="handleView" @selection-change="(v: unknown) => selectedDevices = v as Device[]" @batch-delete="onBatchDelete" @open-add-dialog="onOpenAddDialog" @open-access-info-dialog="onOpenAccessInfoDialog" @save-organization="onSaveOrganization" @save-stream-mode="onSaveStreamMode" @toggle-catalog-subscribe="onToggleCatalogSubscribe" @set-catalog-subscribe-cycle="onSetCatalogSubscribeCycle" @toggle-mobile-subscribe="onToggleMobileSubscribe" @set-mobile-subscribe-interval="onSetMobileSubscribeInterval" @sync-device-channels="onSyncDeviceChannels" @alarm-dropdown-command="onAlarmDropdownCommand" />
    </PageContainer>

    <DeviceDetailDrawer ref="detailDrawer" :current-device="currentDevice" :current-channel="currentChannel" :dialog-visible="dialogVisible" :player-visible="playerVisible" :channel-stream-reset="channelStreamReset" :channel-page="channelPage" :channel-page-size="channelPageSize" :devices="devices" @update:dialog-visible="(v: boolean) => dialogVisible = v" @update:player-visible="(v: boolean) => playerVisible = v" @update:current-channel="(v: unknown) => currentChannel = v as Device | null" @update:channel-stream-reset="(v: string) => channelStreamReset = v" @update:channel-page="(v: number) => channelPage = v" @update:channel-page-size="(v: number) => channelPageSize = v" @fetch-devices="fetchDevices" />

    <DeviceBatchOps ref="batchOpsRef" :devices="devices" :selected-devices="selectedDevices" @fetch-devices="fetchDevices" @add-success="fetchDevices" @edit-success="fetchDevices" @blacklist-success="fetchDevices" @update:selected-devices="(v: unknown) => selectedDevices = v as Device[]" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { deviceApi } from '@/api/index'
import { ElMessage } from 'element-plus'
import { Plus, Warning, InfoFilled, Refresh, Timer, Download, ArrowDown, Camera } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import { getOrganizationTree, flattenOrgTree } from '../api/organizations'
import { useRoute } from 'vue-router'
import { getFriendlyError } from '../utils/errorMessage'
import { logger } from '@/utils/logger'
import type { Device } from '@/types/models'
import DeviceFilterBar from './device-list/DeviceFilterBar.vue'
import DeviceTable from './device-list/DeviceTable.vue'
import DeviceDetailDrawer from './device-list/DeviceDetailDrawer.vue'
import DeviceBatchOps from './device-list/DeviceBatchOps.vue'

interface FilterBarInstance {
  deviceKeyword: string
  deviceStatus: string
  filterOrganizationId: string
  focusKeywordInput: () => void
  restoredPageSize?: number
}

interface BatchOpsInstance {
  openAddDialog: () => void
  openIpBlacklistDialog: () => void
  openAccessInfoDialog: () => void
  handleBatchDelete: () => void
  exportToCsv: (opts: { id: string; label: string }[]) => void
  exportDevicesFromServer: (format: string, withChannels: boolean) => void
  batchSnapshot: () => void
  saveOrganization: (row: Record<string, unknown>) => void
  saveStreamMode: (row: Record<string, unknown>) => void
  toggleCatalogSubscribe: (row: Record<string, unknown>, enabled: boolean) => void
  setCatalogSubscribeCycle: (row: Record<string, unknown>) => void
  toggleMobileSubscribe: (row: Record<string, unknown>, enabled: boolean) => void
  setMobileSubscribeInterval: (row: Record<string, unknown>) => void
  syncDeviceChannels: (row: Record<string, unknown>) => void
  handleAlarmDropdownCommand: (row: Record<string, unknown>, cmd: string) => void
  savingMode: Record<string, boolean>
  savingOrg: Record<string, boolean>
  savingCatalogSub: Record<string, boolean>
  savingMobileSub: Record<string, boolean>
  catalogSyncPolling: Record<string, boolean>
  batchSnapping: boolean
  clearCatalogSyncDialogCloseTimer: () => void
  catalogSyncPollingTimers: Record<string, number | null>
}

const { t } = useI18n()  // FIXED: 国际化
const filterBar = ref<FilterBarInstance>()
const detailDrawer = ref<InstanceType<typeof DeviceDetailDrawer>>()
const batchOpsRef = ref<BatchOpsInstance>()

const devices = ref<Device[]>([])
const loading = ref(false)
const devicesEmptyText = ref(t('device.emptyNoDevice'))
const dialogVisible = ref(false)
const playerVisible = ref(false)
const currentDevice = ref<Device | null>(null)
const currentChannel = ref<Device | null>(null)
const selectedDevices = ref<Device[]>([])
const autoRefresh = ref(false)
let autoRefreshTimer: number | null = null
const organizationOptions = ref<{ id: string; label: string }[]>([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalDisplay = ref(0)
const deviceStatsTotal = ref(0)
const deviceStatsOnline = ref(0)
const deviceStatsOffline = ref(0)
const channelPage = ref(1)
const channelPageSize = ref(10)
const channelStreamReset = ref<string>('')
// Reactive refs synced from batchOps for table binding
const savingMode = ref<Record<string, boolean>>({})
const savingOrg = ref<Record<string, boolean>>({})
const savingCatalogSub = ref<Record<string, boolean>>({})
const savingMobileSub = ref<Record<string, boolean>>({})
const catalogSyncPolling = ref<Record<string, boolean>>({})
const batchSnapping = ref(false)

const loadOrganizations = async () => { try { organizationOptions.value = flattenOrgTree(await getOrganizationTree()).map(o => ({ id: o.id, label: o.name })) } catch { organizationOptions.value = []; logger.warn('加载组织树失败') } }

const fetchDevices = async (silentArg?: boolean | number) => {
  const silent = typeof silentArg === 'boolean' ? silentArg : false
  if (!silent) loading.value = true
  const fb = filterBar.value
  try {
    const keyword = String(fb?.deviceKeyword || '').trim()
    // FIX: [2026-07-13] 当 deviceStatus 为 undefined/null 时 Number() 产生 NaN，
    // 导致 /api/v1/devices?status=NaN 422 错误。使用显式空值检查避免 NaN。
    // [全栈工程师]
    const rawStatus = fb?.deviceStatus
    const status = (rawStatus && rawStatus !== '') ? Number(rawStatus) : undefined
    const res = await deviceApi.list({ skip: (page.value - 1) * pageSize.value, limit: pageSize.value, organization_id: fb?.filterOrganizationId || undefined, keyword: keyword || undefined, status })
    const payload = res.data || {}; const items = Array.isArray(payload?.items) ? payload.items : []; const stats = payload?.stats || {}
    devices.value = items; total.value = Number(payload?.total || 0); totalDisplay.value = total.value
    deviceStatsTotal.value = Number(stats?.total ?? total.value ?? 0)
    deviceStatsOnline.value = Number(stats?.online ?? items.filter((d: Record<string, unknown>) => Number(d?.status) === 1 || String(d?.status) === 'Online').length)
    deviceStatsOffline.value = Number(stats?.offline ?? Math.max(0, deviceStatsTotal.value - deviceStatsOnline.value))
    if (!items.length) devicesEmptyText.value = keyword || fb?.filterOrganizationId || fb?.deviceStatus !== '' ? t('device.noMatchDevice') : t('device.emptyNoDevice')
    return true
  } catch (e: unknown) {
    devices.value = []; total.value = 0; totalDisplay.value = 0; deviceStatsTotal.value = 0; deviceStatsOnline.value = 0; deviceStatsOffline.value = 0; devicesEmptyText.value = t('device.loadDeviceFailed')
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message); return false
  } finally { if (!silent) loading.value = false }
}

const handlePageSizeChange = () => { page.value = 1; fetchDevices() }
const handleSearch = () => { page.value = 1; fetchDevices() }
const handleView = async (row: Record<string, unknown>) => { if (!row?.gb_id) return; currentDevice.value = row; currentChannel.value = null; channelPage.value = 1; dialogVisible.value = true; await detailDrawer.value?.loadChannelsDialog() }
const refreshDevices = async () => { page.value = 1; const ok = await fetchDevices(); if (ok) ElMessage.success(t('device.refreshedDeviceList')) }
const toggleAutoRefresh = () => {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) { ElMessage.success(t('device.autoRefreshStarted')); autoRefreshTimer = window.setInterval(() => fetchDevices(true), 15000) }
  else { ElMessage.info(t('device.autoRefreshStopped2')); if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null } }
}

// Delegate actions to batchOps
const bo = () => batchOpsRef.value!
const onOpenAddDialog = () => bo().openAddDialog()
const onOpenIpBlacklistDialog = () => bo().openIpBlacklistDialog()
const onOpenAccessInfoDialog = () => bo().openAccessInfoDialog()
const onBatchDelete = () => bo().handleBatchDelete()
const onExportCsv = () => bo().exportToCsv(organizationOptions.value)
const onExportCommand = (cmd: string) => {
  if (cmd === 'csv') bo().exportDevicesFromServer('csv', true)
  else if (cmd === 'json') bo().exportDevicesFromServer('json', true)
  else if (cmd === 'csv-no-channels') bo().exportDevicesFromServer('csv', false)
}
const onBatchSnapshot = () => bo().batchSnapshot()
const onSaveOrganization = (row: Record<string, unknown>) => bo().saveOrganization(row)
const onSaveStreamMode = (row: Record<string, unknown>) => bo().saveStreamMode(row)
const onToggleCatalogSubscribe = (row: Record<string, unknown>, enabled: boolean) => bo().toggleCatalogSubscribe(row, enabled)
const onSetCatalogSubscribeCycle = (row: Record<string, unknown>) => bo().setCatalogSubscribeCycle(row)
const onToggleMobileSubscribe = (row: Record<string, unknown>, enabled: boolean) => bo().toggleMobileSubscribe(row, enabled)
const onSetMobileSubscribeInterval = (row: Record<string, unknown>) => bo().setMobileSubscribeInterval(row)
const onSyncDeviceChannels = (row: Record<string, unknown>) => bo().syncDeviceChannels(row)
const onAlarmDropdownCommand = (row: Record<string, unknown>, cmd: string) => bo().handleAlarmDropdownCommand(row, cmd)

// Sync reactive state from batchOps
const syncBatchOpsState = () => {
  const b = batchOpsRef.value; if (!b) return
  savingMode.value = b.savingMode; savingOrg.value = b.savingOrg
  savingCatalogSub.value = b.savingCatalogSub; savingMobileSub.value = b.savingMobileSub
  catalogSyncPolling.value = b.catalogSyncPolling
  batchSnapping.value = b.batchSnapping
}

const handleGlobalKeydown = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && String(event.key || '').toLowerCase() === 'f') { event.preventDefault(); filterBar.value?.focusKeywordInput() } }

const route = useRoute()
const tryOpenPlaybackFromQuery = async () => {
  const q = route.query || {}; const deviceId = String(q.deviceId || q.device_id || '').trim(); if (!deviceId) return
  if (!devices.value.length) await fetchDevices(true)
  const target = devices.value.find((i: Device) => String(i?.gb_id || '') === deviceId); if (!target) return
  currentDevice.value = target; dialogVisible.value = true
  const tabRaw = String(q.tab || '').trim().toLowerCase(); const tab = tabRaw === 'cloud' || tabRaw === 'device' || tabRaw === 'timeline' ? tabRaw : 'channels'
  await detailDrawer.value?.loadChannelsDialog()
  const channelId = String(q.channelId || q.channel_id || '').trim()
  if (channelId) {
    const chs = detailDrawer.value?.channels || []; const ch = chs.find((i: Device) => String(i?.gb_id || '') === channelId)
    if (ch && tab !== 'channels' && detailDrawer.value) {
      const mins = Math.max(1, Number(String(q.window_minutes || 30).trim() || 30))
      const center = (() => { const r = String(q.time || '').trim(); if (!r) return new Date(); const d = new Date(r); return Number.isNaN(d.getTime()) ? new Date() : d })()
      detailDrawer.value.recordWindowMinutesRef = mins; detailDrawer.value.recordAnchorAtRef = detailDrawer.value.toRecordAnchorValue(center)
      await detailDrawer.value.openRecordTab(ch, tab as 'cloud' | 'device' | 'timeline')
    }
  }
}

onMounted(async () => { loadOrganizations(); if (filterBar.value?.restoredPageSize) pageSize.value = filterBar.value.restoredPageSize; await fetchDevices(); await tryOpenPlaybackFromQuery(); window.addEventListener('keydown', handleGlobalKeydown) })
watch(() => route.query, async () => { await tryOpenPlaybackFromQuery() })
watch(() => batchOpsRef.value, () => syncBatchOpsState(), { immediate: true })
watch([() => batchOpsRef.value?.savingMode, () => batchOpsRef.value?.savingOrg, () => batchOpsRef.value?.savingCatalogSub, () => batchOpsRef.value?.savingMobileSub, () => batchOpsRef.value?.catalogSyncPolling], () => syncBatchOpsState(), { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  try { if (playerVisible.value) void detailDrawer.value?.closePlayer() } catch { /* cleanup: ignore */ }
  try { if (batchOpsRef.value) { batchOpsRef.value.clearCatalogSyncDialogCloseTimer(); for (const k of Object.keys(batchOpsRef.value.catalogSyncPollingTimers)) { const t = batchOpsRef.value.catalogSyncPollingTimers[k]; if (t != null) window.clearInterval(t) } } } catch { /* ignore */ }
  if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null }
})
</script>

<style scoped>
.action-btn { transition: all var(--transition-time-02); border-radius: 3px; }
.action-btn:hover { transform: none; box-shadow: none; }
</style>
