<template>
  <TableCard class="devices-card">
    <template #header>
      <TableToolbar :title="t('device.table.title')" :subtitle="deviceTableSubtitle">
        <template #actions>
          <div class="device-toolbar-actions">
            <el-button v-if="selectedDevices.length > 0" type="danger" plain size="small" @click="handleBatchDelete">
              <el-icon class="mr-1"><Delete /></el-icon>{{ t('device.table.batchDelete', { n: selectedDevices.length }) }}
            </el-button>
            <span class="toolbar-pill"><el-icon><Document /></el-icon><span>{{ t('device.table.total', { n: totalDisplay }) }}</span></span>
            <span v-if="currentDevice?.gb_id" class="toolbar-pill toolbar-pill--active"><el-icon><Monitor /></el-icon><span>{{ t('device.table.currentDevice', { name: currentDevice?.name || currentDevice?.gb_id }) }}</span></span>
            <el-popover placement="bottom-end" :width="250" trigger="click">
              <template #reference><el-button size="small" plain><el-icon class="mr-1"><Setting /></el-icon>{{ t('device.table.fieldDisplay') }}</el-button></template>
              <div class="text-xs mb-2" style="color: var(--el-text-color-secondary)">{{ t('device.table.fieldDisplayHint') }}</div>
              <el-checkbox-group v-model="visibleColumns" class="grid grid-cols-2 gap-y-2 gap-x-3">
                <el-checkbox v-for="col in columnOptions" :key="col.key" :label="col.key">{{ col.label }}</el-checkbox>
              </el-checkbox-group>
              <div class="mt-3 flex justify-end"><el-button size="small" text @click="resetColumns">{{ t('device.table.resetDefault') }}</el-button></div>
            </el-popover>
          </div>
        </template>
      </TableToolbar>
    </template>
    <TableSkeleton v-if="loading && devices.length === 0" :rows="6" />
    <el-table v-else :data="devices" style="width: 100%" v-loading="loading" :empty-text="devicesEmptyText" class="devices-table" row-key="gb_id" size="small" header-row-class-name="devices-table-header-row" :row-class-name="getRowClassName" fit @row-dblclick="(row: Record<string, unknown>) => emit('viewDevice', row)" @selection-change="(val: Record<string, unknown>[]) => emit('selectionChange', val)">
      <template #empty>
        <EmptyStateWithAction :description="t('device.table.emptyDesc')">
          <template #action>
            <el-button type="primary" @click="emit('openAddDialog')" class="empty-action-btn"><el-icon class="mr-1"><Plus /></el-icon>{{ t('device.table.addDevice') }}</el-button>
            <el-button @click="emit('openAccessInfoDialog')" class="empty-action-btn-secondary"><el-icon class="mr-1"><InfoFilled /></el-icon>{{ t('device.table.accessInfo') }}</el-button>
          </template>
        </EmptyStateWithAction>
      </template>
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column v-if="isColVisible('gb_id')" prop="gb_id" width="180">
        <template #header><div class="flex items-center gap-1"><span>{{ t('device.table.colGbId') }}</span><el-tooltip :content="t('device.table.colGbIdTip')" placement="top"><el-icon class="cursor-help text-slate-400 hover:text-slate-600 transition-colors"><InfoFilled /></el-icon></el-tooltip></div></template>
        <template #default="scope"><span class="font-mono text-xs text-slate-500">{{ scope.row.gb_id }}</span></template>
      </el-table-column>
      <el-table-column v-if="isColVisible('name')" prop="name" :label="t('device.table.colName')" min-width="140" show-overflow-tooltip>
        <template #default="scope">
          <div class="device-name-block">
            <div class="device-name-cell truncate"><el-icon class="text-slate-400"><Monitor /></el-icon><span>{{ scope.row.name }}</span></div>
            <div class="device-name-meta">
              <span class="device-meta-chip">{{ scope.row.manufacturer || t('device.table.unknownManufacturer') }}</span>
              <span class="device-meta-chip">{{ t('device.table.channelCountUnit', { n: scope.row.channel_count ?? 0 }) }}</span>
              <span v-if="currentDevice?.gb_id === scope.row.gb_id && dialogVisible" class="device-meta-chip device-meta-chip--active">{{ t('device.table.workspaceOpened') }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('organization')" :label="t('device.table.colOrg')" width="160">
        <template #default="scope">
          <div class="org-field"><span class="field-label">{{ t('device.table.orgBelong') }}</span>
            <el-select v-model="scope.row.organization_id" :placeholder="t('device.table.orgUnassigned')" clearable size="small" class="org-select-cell" :loading="savingOrg[scope.row.gb_id]" @change="() => emit('saveOrganization', scope.row)">
              <el-option :label="t('device.table.orgUnassigned')" value="" /><el-option v-for="opt in organizationOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('ip_addr')" prop="ip_addr" :label="t('device.table.colIp')" width="130">
        <template #default="scope"><div class="ip-cell"><el-tag size="small" type="info" effect="plain" v-if="scope.row.ip_addr" class="font-mono text-[10px]">{{ scope.row.ip_addr }}</el-tag><span v-else class="text-slate-400 text-xs">—</span></div></template>
      </el-table-column>
      <el-table-column v-if="isColVisible('channel_count')" :label="t('device.table.colChannelCount')" width="100" align="center">
        <template #default="scope"><span class="text-xs font-medium text-slate-600">{{ scope.row.channel_count ?? 0 }}</span></template>
      </el-table-column>
      <el-table-column v-if="isColVisible('manufacturer')" prop="manufacturer" :label="t('device.table.colManufacturer')" width="100" show-overflow-tooltip />
      <el-table-column v-if="isColVisible('last_active')" :label="t('device.table.colLastActive')" width="140">
        <template #default="scope">
          <div class="text-[10px] flex flex-col gap-0.5 leading-tight">
            <div class="flex items-center gap-1 text-slate-500"><span class="text-slate-400 scale-90">{{ t('device.table.heartbeatLabel') }}</span><span>{{ fmtDateTime(scope.row.last_keepalive) }}</span></div>
            <div class="flex items-center gap-1 text-slate-400"><span class="text-slate-400 scale-90">{{ t('device.table.registerLabel') }}</span><span>{{ fmtDateTime(scope.row.register_time) }}</span></div>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('stream_mode')" :label="t('device.table.colStreamMode')" width="130">
        <template #default="scope">
          <el-tooltip :content="savingMode[scope.row.gb_id] ? t('device.table.streamModeSaving') : t('device.table.streamModeTip')" placement="top">
            <span><div class="mode-field"><span class="field-label">{{ t('device.table.modeLabel') }}</span>
              <el-select v-model="scope.row.stream_mode" size="small" class="mode-select" :loading="savingMode[scope.row.gb_id]" @change="() => emit('saveStreamMode', scope.row)">
                <el-option v-for="item in streamModeOpts" :key="item.value" :label="item.label" :value="item.value" />
              </el-select></div></span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('status')" :label="t('device.table.colStatus')" width="100" align="center">
        <template #default="scope">
          <div class="status-cell">
            <el-tooltip :content="isOnline(scope.row.status) ? t('device.table.statusOnline') : t('device.table.statusOffline')" placement="top">
              <span class="status-pill" :class="isOnline(scope.row.status) ? 'online' : 'offline'">
                <span class="status-dot" :class="isOnline(scope.row.status) ? 'online' : 'offline'"></span>
                <span class="status-text">{{ isOnline(scope.row.status) ? t('device.table.statusOnline') : t('device.table.statusOffline') }}</span>
              </span>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('subscription')" :label="t('device.table.colSubscription')" width="180" align="center">
        <template #default="scope">
          <div class="subscription-card">
            <div class="subscription-row">
              <div class="subscription-meta"><span class="subscription-label">{{ t('device.table.catalogSubscribe') }}</span><span class="subscription-value">{{ fmtCycle(scope.row.catalog_subscribe_cycle_seconds, t('device.table.noCycleSet')) }}</span></div>
              <div class="subscription-actions">
                <el-tooltip :content="savingCatalogSub[scope.row.gb_id] ? t('device.table.streamModeSaving') : t('device.table.catalogSubSwitch')" placement="top"><span>
                  <el-switch v-model="scope.row.catalog_subscribe_enabled" size="small" inline-prompt :active-text="t('channel.edit.switchOn')" :inactive-text="t('channel.edit.switchOff')" class="pretty-switch pretty-switch--success" :loading="savingCatalogSub[scope.row.gb_id]" @change="(val: boolean) => emit('toggleCatalogSubscribe', scope.row, val)" />
                </span></el-tooltip>
                <el-tooltip :content="scope.row.catalog_subscribe_cycle_seconds ? t('device.table.catalogSubCycleTip') : t('device.table.catalogSubCycleSetTip')" placement="top">
                  <button class="subscription-link" @click="emit('setCatalogSubscribeCycle', scope.row)">{{ t('device.table.setCycle') }}</button>
                </el-tooltip>
              </div>
            </div>
            <div class="subscription-row">
              <div class="subscription-meta"><span class="subscription-label">{{ t('device.table.locationSubscribe') }}</span><span class="subscription-value">{{ fmtCycle(scope.row.mobile_position_interval_seconds, t('device.table.noIntervalSet')) }}</span></div>
              <div class="subscription-actions">
                <el-tooltip :content="savingMobileSub[scope.row.gb_id] ? t('device.table.streamModeSaving') : t('device.table.locationSubSwitch')" placement="top"><span>
                  <el-switch v-model="scope.row.mobile_position_subscribe_enabled" size="small" inline-prompt :active-text="t('channel.edit.switchOn')" :inactive-text="t('channel.edit.switchOff')" class="pretty-switch" :loading="savingMobileSub[scope.row.gb_id]" @change="(val: boolean) => emit('toggleMobileSubscribe', scope.row, val)" />
                </span></el-tooltip>
                <el-tooltip :content="scope.row.mobile_position_interval_seconds ? t('device.table.locationSubIntervalTip') : t('device.table.locationSubIntervalSetTip')" placement="top">
                  <button class="subscription-link" @click="emit('setMobileSubscribeInterval', scope.row)">{{ t('device.table.setInterval') }}</button>
                </el-tooltip>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="t('device.table.colAction')" align="center" width="340" fixed="right">
        <template #default="scope">
          <div class="device-actions table-action-inline">
            <el-tooltip :content="Number(scope.row.status) !== 1 ? t('device.table.refreshOfflineTip') : t('device.table.refreshTip')" placement="top"><span>
              <el-button size="small" plain @click="emit('syncDeviceChannels', scope.row)" :loading="catalogSyncPolling[String(scope.row.gb_id || '')]" :disabled="Number(scope.row.status) !== 1 || catalogSyncPolling[String(scope.row.gb_id || '')]" class="device-action-btn device-action-btn--refresh"><el-icon class="mr-1"><Refresh /></el-icon>{{ t('device.table.refresh') }}</el-button>
            </span></el-tooltip>
            <el-divider direction="vertical" />
            <el-tooltip :content="t('device.table.viewChannelsTip')" placement="top"><span>
              <el-button size="small" plain @click="emit('viewDevice', scope.row)" class="device-action-btn device-action-btn--view"><el-icon class="mr-1"><View /></el-icon>{{ t('device.table.channels') }}</el-button>
            </span></el-tooltip>
            <el-dropdown trigger="click" @command="(cmd: string) => handleDropdownCommand(scope.row, cmd)">
              <el-button size="small" plain class="device-action-btn device-action-btn--more table-action-more">{{ t('device.table.more') }}<el-icon class="ml-1"><MoreFilled /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit"><el-icon><Edit /></el-icon>{{ t('device.table.actionEdit') }}</el-dropdown-item>
                  <el-dropdown-item command="on"><el-icon class="text-emerald-500"><Bell /></el-icon>{{ t('device.table.actionDefend') }}</el-dropdown-item>
                  <el-dropdown-item command="off"><el-icon class="text-amber-500"><MuteNotification /></el-icon>{{ t('device.table.actionWithdraw') }}</el-dropdown-item>
                  <el-dropdown-item command="map" divided><el-icon><Location /></el-icon>{{ t('device.table.actionLocate') }}</el-dropdown-item>
                  <el-dropdown-item command="syncBasic"><el-icon><Tools /></el-icon>{{ t('device.table.actionSyncBasic') }}</el-dropdown-item>
                  <el-dropdown-item command="teleboot" divided><el-icon><SwitchButton /></el-icon>{{ t('device.table.actionTeleboot') }}</el-dropdown-item>
                  <el-dropdown-item command="recordStart"><el-icon><VideoCamera /></el-icon>{{ t('device.table.actionRecordStart') }}</el-dropdown-item>
                  <el-dropdown-item command="recordStop"><el-icon><VideoPause /></el-icon>{{ t('device.table.actionRecordStop') }}</el-dropdown-item>
                  <el-dropdown-item command="alarmReset"><el-icon><BellFilled /></el-icon>{{ t('device.table.actionAlarmReset') }}</el-dropdown-item>
                  <el-dropdown-item command="iframe"><el-icon><Film /></el-icon>{{ t('device.table.actionIframe') }}</el-dropdown-item>
                  <el-dropdown-item command="blacklist" divided class="text-warning"><el-icon><Warning /></el-icon>{{ t('device.table.actionBlacklist') }}</el-dropdown-item>
                  <el-dropdown-item command="delete" divided class="text-danger"><el-icon><Delete /></el-icon>{{ t('device.table.actionDelete') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <div class="flex justify-end mt-4 pagination-wrapper">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="totalDisplay" layout="total, sizes, prev, pager, next, jumper" :page-sizes="[10, 20, 50, 100]" :prev-text="t('device.table.prevPage')" :next-text="t('device.table.nextPage')" size="small" @current-change="emit('fetchDevices')" @size-change="emit('pageSizeChange')" />
    </div>
  </TableCard>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Setting, Document, Monitor, View, Refresh, Edit, Delete, Warning, Bell, Plus, MoreFilled, MuteNotification, InfoFilled, Location, Tools, SwitchButton, VideoCamera, VideoPause, BellFilled, Film } from '@element-plus/icons-vue'
import EmptyStateWithAction from '../../components/EmptyStateWithAction.vue'
import TableSkeleton from '../../components/TableSkeleton.vue'
import TableCard from '../../components/TableCard.vue'
import TableToolbar from '../../components/TableToolbar.vue'
import type { Device } from '@/types/models'
import { confirmDangerous } from '../../utils/feedback'
import { useI18n } from 'vue-i18n'  // FIXED: [2026-07-13] P1 i18n — 添加国际化支持

const { t } = useI18n()

const props = defineProps<{
  devices: Device[]; loading: boolean; devicesEmptyText: string; totalDisplay: number
  page: number; pageSize: number; currentDevice: Device | null; dialogVisible: boolean
  selectedDevices: Device[]; savingMode: Record<string, boolean>; savingOrg: Record<string, boolean>
  savingCatalogSub: Record<string, boolean>; savingMobileSub: Record<string, boolean>
  catalogSyncPolling: Record<string, boolean>; organizationOptions: { id: string; label: string }[]
}>()

const emit = defineEmits<{
  (e: 'update:page', v: number): void; (e: 'update:pageSize', v: number): void
  (e: 'fetchDevices'): void; (e: 'pageSizeChange'): void; (e: 'viewDevice', row: Record<string, unknown>): void
  (e: 'selectionChange', val: Record<string, unknown>[]): void; (e: 'batchDelete'): void; (e: 'openAddDialog'): void
  (e: 'openAccessInfoDialog'): void; (e: 'saveOrganization', row: Record<string, unknown>): void
  (e: 'saveStreamMode', row: Record<string, unknown>): void; (e: 'toggleCatalogSubscribe', row: Record<string, unknown>, enabled: boolean): void
  (e: 'setCatalogSubscribeCycle', row: Record<string, unknown>): void; (e: 'toggleMobileSubscribe', row: Record<string, unknown>, enabled: boolean): void
  (e: 'setMobileSubscribeInterval', row: Record<string, unknown>): void; (e: 'syncDeviceChannels', row: Record<string, unknown>): void
  (e: 'alarmDropdownCommand', row: Record<string, unknown>, cmd: string): void
}>()

const page = computed({ get: () => props.page, set: (v) => emit('update:page', v) })
const pageSize = computed({ get: () => props.pageSize, set: (v) => emit('update:pageSize', v) })

// Column visibility (self-managed)
const COL_KEY = 'device_list_visible_columns_v2'
const columnOptions = computed(() => [
  { key: 'gb_id', label: t('device.table.colGbId') }, { key: 'name', label: t('device.table.colName') }, { key: 'status', label: t('device.table.colStatus') },
  { key: 'channel_count', label: t('device.table.colChannelCount') }, { key: 'last_active', label: t('device.table.colLastActive') },
  { key: 'organization', label: t('device.table.colOrg') }, { key: 'ip_addr', label: t('device.table.colIp') },
  { key: 'manufacturer', label: t('device.table.colManufacturer') }, { key: 'stream_mode', label: t('device.table.colStreamMode') }, { key: 'subscription', label: t('device.table.colSubscription') }
])
const defaultCols = ['gb_id', 'name', 'status', 'channel_count', 'last_active'] as const
const visibleColumns = ref<string[]>([])
const isColVisible = (key: string) => visibleColumns.value.includes(key)
const initColumns = () => {
  try {
    const raw = localStorage.getItem(COL_KEY)
    if (!raw) { visibleColumns.value = [...defaultCols]; return }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) { visibleColumns.value = [...defaultCols]; return }
    const allowed = new Set<string>(columnOptions.value.map(i => String(i.key)))
    const next = parsed.map((i: number) => String(i || '').trim()).filter((i: string) => allowed.has(i))
    visibleColumns.value = next.length ? next : [...defaultCols]
  } catch { visibleColumns.value = [...defaultCols] }
}
const resetColumns = () => { visibleColumns.value = [...defaultCols] }
onMounted(initColumns)
watch(visibleColumns, (v) => { if (!v.length) { visibleColumns.value = [...defaultCols]; return } localStorage.setItem(COL_KEY, JSON.stringify(v)) }, { deep: true })

const streamModeOpts = computed(() => [
  { label: t('device.table.streamModeGlobal'), value: 'GLOBAL' },
  { label: t('device.table.streamModeAuto'), value: 'AUTO' },
  { label: 'UDP', value: 'UDP' },
  { label: t('device.table.streamModeTcpPassive'), value: 'TCP_PASSIVE' },
  { label: t('device.table.streamModeTcpActive'), value: 'TCP_ACTIVE' }
])
const deviceTableSubtitle = computed(() => t('device.table.total', { n: props.totalDisplay }))
const isOnline = (s: Record<string, unknown>) => Number(s) === 1 || String(s) === 'Online'
const getRowClassName = ({ row }: { row: Record<string, unknown> }) => isOnline(row?.status) ? 'device-row--online' : 'device-row--offline'
const fmtDateTime = (input: string | Date | null | undefined, empty = '-') => { if (!input) return empty; const d = input instanceof Date ? input : new Date(input); if (Number.isNaN(d.getTime())) return String(input); return d.toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) }
const fmtCycle = (s: Record<string, unknown>, empty = t('device.table.statusOffline')) => { const n = Number(s || 0); if (!Number.isFinite(n) || n <= 0) return empty; if (n < 60) return `${Math.round(n)}s`; const m = n / 60; if (m < 60) return `${Math.round(m)}m`; return `${Math.round(m / 60)}h` }

async function handleBatchDelete() {
  try {
    await confirmDangerous(t('device.table.actionDelete'), `${props.selectedDevices.length}`)
  } catch { return }
  emit('batchDelete')
}

async function handleDropdownCommand(row: Record<string, unknown>, cmd: string) {
  if (cmd === 'delete') {
    try {
      await confirmDangerous(t('device.table.actionDelete'), String(row.name || row.gb_id || ''))
    } catch { return }
  }
  emit('alarmDropdownCommand', row, cmd)
}
</script>

<style scoped>
.devices-card { border-radius: 8px; overflow: hidden; }
.device-toolbar-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; }
.toolbar-pill { display: inline-flex; align-items: center; gap: 6px; min-height: 26px; padding: 0 10px; border: 1px solid var(--el-border-color); border-radius: 3px; background: var(--el-bg-color); color: var(--el-text-color-secondary); font-size: 12px; }
.toolbar-pill strong { color: var(--el-text-color-primary); }
.toolbar-pill--active { border-color: var(--el-color-success-light-7); background: var(--el-color-success-light-9); color: var(--el-color-success); }
.devices-table { border-radius: 4px; overflow: hidden; }
.devices-table :deep(.el-table__body tr) { transition: all var(--transition-time-02); }
.devices-table :deep(.el-table__body tr.is-current-device > td.el-table__cell) { background: var(--el-color-primary-light-9); }
.devices-table :deep(.el-table__body tr:hover) { background: var(--el-fill-color-extra-light); transform: none; }
.devices-table :deep(.el-table__fixed-right), .devices-table :deep(.el-table__fixed) { height: 100% !important; bottom: 0 !important; background-color: var(--el-bg-color) !important; box-shadow: none; }
.devices-table :deep(.el-table__fixed-right .el-table__fixed-body-wrapper), .devices-table :deep(.el-table__fixed .el-table__fixed-body-wrapper) { background-color: var(--el-bg-color); }
.devices-table :deep(.el-table__fixed-right .el-table__cell), .devices-table :deep(.el-table__fixed .el-table__cell) { background-color: var(--el-bg-color) !important; }
.devices-table :deep(.el-table__body tr:hover > td.el-table__cell) { background-color: var(--el-fill-color-extra-light) !important; }
.devices-table :deep(.el-table__body tr:focus-within > td.el-table__cell) { background-color: var(--el-color-primary-light-9) !important; }
.devices-table :deep(.el-table__cell) { vertical-align: middle; padding: 8px 0; color: var(--el-text-color-regular); }
.devices-table-header-row :deep(.el-table__cell) { background-color: var(--el-fill-color-light) !important; color: var(--el-text-color-primary) !important; font-weight: 600; letter-spacing: 0.01em; }
.device-name-block { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.device-name-cell { display: flex; align-items: center; gap: 8px; font-weight: 500; height: 32px; color: var(--el-text-color-primary); }
.device-name-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.device-meta-chip { display: inline-flex; align-items: center; min-height: 20px; padding: 0 7px; border-radius: 2px; background: var(--el-fill-color-light); color: var(--el-text-color-secondary); font-size: 11px; }
.device-meta-chip--active { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.status-cell { display: flex; align-items: center; justify-content: center; gap: 6px; height: 32px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.status-dot.online { background: var(--el-color-success); box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2); }
.status-dot.offline { background: var(--el-border-color); }
.status-pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 12px; border: 1px solid; font-size: 12px; font-weight: 500; white-space: nowrap; line-height: 1.4; }
.status-pill .status-text { color: inherit; }
.status-pill.online { border-color: var(--el-color-success-light-5); background: var(--el-color-success-light-9); color: var(--el-color-success-dark-2); }
.status-pill.offline { border-color: var(--el-border-color); background: var(--el-fill-color-light); color: var(--el-text-color-secondary); }
.subscription-card { display: flex; flex-direction: column; gap: 8px; padding: 8px; border: 1px solid var(--el-border-color); border-radius: 4px; background: var(--el-bg-color); }
.subscription-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.subscription-meta { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.subscription-label { font-size: 12px; font-weight: 700; color: var(--el-text-color-primary); }
.subscription-value { font-size: 11px; color: var(--el-text-color-secondary); }
.subscription-actions { display: flex; align-items: center; gap: 8px; }
.subscription-link { border: none; padding: 0; background: transparent; color: var(--el-color-primary); font-size: 11px; font-weight: 600; cursor: pointer; }
.subscription-link:hover { color: var(--el-color-primary); }
.device-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 6px; }
.device-action-btn { min-width: 72px; height: 26px; margin-left: 0; padding: 0 10px; border-radius: 4px; border-color: var(--el-border-color); background: var(--el-bg-color); color: var(--el-text-color-primary); font-weight: 600; transition: all 0.18s ease; }
.device-action-btn:hover { transform: none; box-shadow: none; }
.device-action-btn--refresh { border-color: var(--el-border-color); background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
.device-action-btn--view { border-color: var(--el-color-primary-light-7); background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.device-action-btn--more { border-color: var(--el-color-primary-light-7); background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.text-danger { color: var(--el-color-danger); }
.pagination-wrapper { padding: 10px 14px; background: var(--el-bg-color); border-radius: 0 0 4px 4px; border-top: 1px solid var(--el-border-color-lighter); }
.pretty-switch { --el-switch-on-color: var(--el-color-primary); --el-switch-off-color: var(--el-border-color); }
.pretty-switch--success { --el-switch-on-color: var(--el-color-success); }
.pretty-switch :deep(.el-switch__core) { min-width: 52px !important; height: 26px; border: none; box-shadow: none; border-radius: 13px; }
.pretty-switch :deep(.el-switch__core::before), .pretty-switch :deep(.el-switch__core::after) { display: none; }
.pretty-switch :deep(.el-switch__action), .pretty-switch :deep(.el-switch__button) { width: 20px; height: 20px; top: 3px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15); border-radius: 50%; transition: transform 0.2s ease; }
.pretty-switch :deep(.el-switch__inner) { display: flex; align-items: center; justify-content: center; height: 100%; padding: 0 4px; }
.pretty-switch :deep(.el-switch__inner .is-text) { font-size: 10px; font-weight: 700; color: #ffffff; text-shadow: 0 1px 1px rgba(0,0,0,0.1); }
.pretty-switch :deep(.is-checked .el-switch__inner .is-text) { color: #ffffff; }
@media (max-width: 960px) { .org-select-cell, .mode-select { width: 100%; } .device-toolbar-actions { justify-content: flex-start; } }
</style>
