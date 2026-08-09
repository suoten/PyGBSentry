<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader :title="t('record.deviceTitle')" :description="t('record.deviceDesc')" />
      </template>

      <div class="mt-3 rounded-xl border border-slate-200 bg-white p-4 flex flex-wrap items-end gap-3">
        <div class="w-[520px] max-w-full">
          <div class="text-xs text-slate-500 mb-1">{{ t('record.deviceLabel') }}</div>
          <el-popover
            v-model:visible="devicePickerVisible"
            trigger="click"
            placement="bottom-start"
            :width="560"
            popper-class="device-records-tree-popper"
            @show="onDevicePopoverShow"
          >
            <template #reference>
              <el-input
                :model-value="selectedDeviceLabel"
                readonly
                clearable
                :placeholder="t('record.selectDeviceByOrg')"
                class="w-full device-picker"
                @clear="clearSelectedDevice"
              />
            </template>
            <div class="device-picker-panel">
              <el-input
                v-model="deviceKeyword"
                size="small"
                clearable
                :placeholder="t('record.searchDevice')"
                class="device-picker-search"
              />
              <el-tree
                ref="deviceTreeRef"
                :data="deviceTreeData"
                :props="treeProps"
                node-key="value"
                highlight-current
                default-expand-all
                :expand-on-click-node="false"
                :filter-node-method="filterDeviceNode"
                class="device-picker-tree"
                @node-click="handleDeviceNodeClick"
              >
                <template #default="{ data }">
                  <div class="device-tree-node">
                    <div class="device-tree-node__name">{{ data.deviceName || data.label }}</div>
                    <div v-if="data.deviceId" class="device-tree-node__id">{{ data.deviceId }}</div>
                  </div>
                </template>
              </el-tree>
            </div>
          </el-popover>
        </div>
        <div class="w-80 max-w-full">
          <div class="text-xs text-slate-500 mb-1">{{ t('record.channelLabel') }}</div>
          <el-select
            v-model="selectedChannelId"
            filterable
            clearable
            :placeholder="t('record.selectChannelPlaceholder')"
            class="w-full"
            :disabled="!selectedDeviceId"
            popper-class="device-records-select-popper"
          >
            <OptionWithTitle
              v-for="item in channelOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </div>
        <el-button @click="reloadDevices" :loading="loadingDevices">{{ t('record.refreshDevices') }}</el-button>
      </div>

      <div class="mt-3">
        <el-empty v-if="!selectedDeviceId || !selectedChannelId" :description="t('record.selectDeviceChannelHint')" />
        <DeviceRecordList
          v-else
          :device-id="selectedDeviceId"
          :channel-id="selectedChannelId"
          @play-record="forwardPlayRecord"
        />
      </div>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRoute, useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import DeviceRecordList from '../components/DeviceRecordList.vue'
import OptionWithTitle from '../components/OptionWithTitle.vue'
import { parseDeviceChannelsResponse } from '../utils/deviceApi'
import { getApiErrorMessage } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const route = useRoute()
const { t } = useI18n()  // FIXED: 国际化
const router = useRouter()

const loadingDevices = ref(false)
const selectedDeviceId = ref('')
const selectedChannelId = ref('')
const deviceOptions = ref<Array<{ value: string; label: string }>>([])
const channelOptions = ref<Array<{ value: string; label: string }>>([])
const treeProps = { label: 'label', children: 'children', disabled: 'disabled' }
const devicePickerVisible = ref(false)
const deviceKeyword = ref('')
type DeviceTreeRef = {
  setCurrentKey?: (key: string | null) => void
  filter?: (keyword: string) => void
}

const deviceTreeRef = ref<DeviceTreeRef | null>(null)

const deviceTreeData = ref<TreeNode[]>([])
const selectedDeviceLabel = computed(() => {
  const id = String(selectedDeviceId.value || '').trim()
  if (!id) return ''
  return deviceOptions.value.find((item) => item.value === id)?.label || id
})

const normalizeDeviceRows = (data: Record<string, unknown>): Record<string, unknown>[] => {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    if (Array.isArray(data.items)) return data.items
    if (Array.isArray(data.devices)) return data.devices
  }
  return []
}

const normalizeOrgRows = (data: Record<string, unknown>): Record<string, unknown>[] => {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    if (Array.isArray(data.items)) return data.items
    if (Array.isArray(data.organizations)) return data.organizations
  }
  return []
}

const buildDeviceTree = (devices: Array<{ value: string; label: string; name: string; deviceId: string; organizationId: string }>, orgs: Record<string, unknown>[]) => {
  const tree: Record<string, unknown>[] = []
  const byParent = new Map<string, any[]>()
  const orgMap = new Map<string, any>()
  for (const item of orgs) {
    const id = String(item?.id || '').trim()
    if (!id) continue
    orgMap.set(id, item)
    const pid = String(item?.parent_id || '').trim() || '__root__'
    if (!byParent.has(pid)) byParent.set(pid, [])
    byParent.get(pid)!.push(item)
  }

  const createOrgNode = (org: Record<string, unknown>): Record<string, unknown> => {
    const id = String(org?.id || '').trim()
    const label = String(org?.name || id || t('record.unnamedOrg')).trim()
    const childrenOrgs = (byParent.get(id) || []).map(createOrgNode)
    const childrenDevices = devices
      .filter((d) => d.organizationId === id)
      .map((d) => ({
        value: d.value,
        label: d.label,
        deviceName: d.name,
        deviceId: d.deviceId,
        children: [],
      }))
    return { value: `org:${id}`, label, disabled: true, children: [...childrenOrgs, ...childrenDevices] }
  }

  const rootOrgs = byParent.get('__root__') || []
  tree.push(...rootOrgs.map(createOrgNode))

  const usedOrgIds = new Set<string>()
  rootOrgs.forEach((o) => usedOrgIds.add(String(o?.id || '').trim()))
  const danglingOrgs = orgs.filter((o) => {
    const id = String(o?.id || '').trim()
    if (!id) return false
    if (usedOrgIds.has(id)) return false
    const pid = String(o?.parent_id || '').trim()
    return pid && !orgMap.has(pid)
  })
  if (danglingOrgs.length) {
    tree.push({
      value: 'org:__dangling__',
      label: t('record.unlinkedOrg'),
      disabled: true,
      children: danglingOrgs.map(createOrgNode),
    })
  }

  const noOrgDevices = devices
    .filter((d) => !d.organizationId)
    .map((d) => ({
      value: d.value,
      label: d.label,
      deviceName: d.name,
      deviceId: d.deviceId,
      children: [],
    }))
  if (noOrgDevices.length) {
    tree.push({
      value: 'org:__none__',
      label: t('record.unassignedOrg'),
      disabled: true,
      children: noOrgDevices,
    })
  }
  return tree
}

const reloadDevices = async () => {
  loadingDevices.value = true
  try {
    const [deviceRes, orgRes] = await Promise.all([
      api.get('/api/v1/devices'),
      api.get('/api/v1/organizations').catch(() => ({ data: [] as Record<string, unknown>[] })),
    ])
    const rows = normalizeDeviceRows(deviceRes.data)
    const orgRows = normalizeOrgRows(orgRes.data)
    const normalizedDevices = rows
      .map((item: Record<string, unknown>) => {
        const gbId = String(item?.gb_id || '').trim()
        if (!gbId) return null
        const name = String(item?.name || item?.device_name || gbId).trim()
        return {
          value: gbId,
          label: `${name} (${gbId})`,
          name,
          deviceId: gbId,
          organizationId: String(item?.organization_id || '').trim(),
        }
      })
      .filter(Boolean) as Array<{ value: string; label: string; name: string; deviceId: string; organizationId: string }>
    deviceOptions.value = normalizedDevices.map((d) => ({ value: d.value, label: d.label }))
    deviceTreeData.value = buildDeviceTree(normalizedDevices, orgRows)
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('record.deviceLoadFailed')))
    deviceOptions.value = []
    deviceTreeData.value = []
  } finally {
    loadingDevices.value = false
  }
}

const loadChannels = async (deviceId: string) => {
  const d = String(deviceId || '').trim()
  if (!d) {
    channelOptions.value = []
    selectedChannelId.value = ''
    return
  }
  try {
    const res = await api.get(`/api/v1/devices/${encodeURIComponent(d)}/channels`)
    const rows = parseDeviceChannelsResponse(res.data)
    channelOptions.value = rows
      .map((item: Record<string, unknown>) => {
        const id = String(item?.gb_id || '').trim()
        if (!id) return null
        const name = String(item?.name || item?.channel_name || id).trim()
        return { value: id, label: `${name} (${id})` }
      })
      .filter(Boolean) as Array<{ value: string; label: string }>
    if (!channelOptions.value.some(i => i.value === selectedChannelId.value)) {
      selectedChannelId.value = channelOptions.value[0]?.value || ''
    }
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('record.channelLoadFailed')))
    channelOptions.value = []
    selectedChannelId.value = ''
  }
}

const handleDeviceChange = async () => {
  await loadChannels(selectedDeviceId.value)
}

const clearSelectedDevice = () => {
  selectedDeviceId.value = ''
  selectedChannelId.value = ''
  channelOptions.value = []
}

const filterDeviceNode = (keyword: string, data: Record<string, unknown>) => {
  const q = String(keyword || '').trim().toLowerCase()
  if (!q) return true
  const fullText = [
    String(data?.label || ''),
    String(data?.deviceName || ''),
    String(data?.deviceId || ''),
  ].join(' ').toLowerCase()
  return fullText.includes(q)
}

const onDevicePopoverShow = () => {
  nextTick(() => {
    deviceTreeRef.value?.setCurrentKey?.(selectedDeviceId.value || null)
    deviceTreeRef.value?.filter?.(deviceKeyword.value)
  })
}

const handleDeviceNodeClick = async (data: Record<string, unknown>) => {
  if (!data || data.disabled || String(data.value || '').startsWith('org:')) return
  const nextId = String(data.value || '').trim()
  if (!nextId) return
  selectedDeviceId.value = nextId
  devicePickerVisible.value = false
  await handleDeviceChange()
}

const syncQuery = () => {
  const query: Record<string, string> = {}
  if (selectedDeviceId.value) query.device_id = selectedDeviceId.value
  if (selectedChannelId.value) query.channel_id = selectedChannelId.value
  router.replace({ path: '/device-records', query }).catch(() => {})
}

const initByQuery = async () => {
  const q = route.query || {}
  selectedDeviceId.value = String(q.device_id || q.deviceId || '').trim()
  selectedChannelId.value = String(q.channel_id || q.channelId || '').trim()
  if (!deviceOptions.value.length) {
    await reloadDevices()
  }
  if (selectedDeviceId.value) {
    await loadChannels(selectedDeviceId.value)
  }
}

const forwardPlayRecord = (payload: Record<string, unknown>) => {
  if (!payload) return
  const deviceId = String(payload.device_id || payload.deviceId || selectedDeviceId.value || '')
  const channelId = String(payload.channel_id || payload.channelId || selectedChannelId.value || '')
  const startTime = String(payload.start_time || payload.startTime || '')
  const endTime = String(payload.end_time || payload.endTime || '')
  if (!deviceId) {
    ElMessage.warning(t('record.missingDeviceForPlayback'))
    return
  }
  const query: Record<string, string> = { device_id: deviceId }
  if (channelId) query.channel_id = channelId
  if (startTime) query.start_time = startTime
  if (endTime) query.end_time = endTime
  router.push({ path: '/device-records', query })
}

watch([selectedDeviceId, selectedChannelId], syncQuery)
watch(deviceKeyword, (keyword) => {
  deviceTreeRef.value?.filter?.(keyword)
})

onMounted(async () => {
  await reloadDevices()
  await initByQuery()
})
</script>

<style>
.device-records-tree-popper,
.device-records-select-popper {
  max-width: 92vw !important;
}

.device-records-tree-popper {
  min-width: 560px !important;
}

.device-records-select-popper .el-select-dropdown__item {
  max-width: 100%;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow: hidden;
}

.device-records-select-popper .el-select-dropdown__item {
  height: 32px;
  line-height: 32px;
  display: flex;
  align-items: center;
}

.device-records-tree-popper .el-tree-node__content {
  height: auto !important;
  min-height: 32px;
  width: 100%;
  padding: 0 12px !important;
  display: flex;
  align-items: flex-start !important;
  padding-top: 6px !important;
  padding-bottom: 6px !important;
  box-sizing: border-box;
  overflow: hidden;
}

.device-records-tree-popper .el-tree-node__label {
  display: block !important;
  height: auto !important;
  width: 100% !important;
  max-width: 100% !important;
  white-space: normal !important;
  overflow: hidden !important;
  text-overflow: initial !important;
  line-height: 1.4 !important;
  word-break: break-all !important;
}

.device-picker-panel {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}

.device-picker-search {
  margin-bottom: 8px;
  width: 100%;
}

.device-picker-search .el-input__wrapper {
  width: 100%;
  box-sizing: border-box;
}

.device-picker-tree {
  width: 100%;
  max-height: 56vh;
  overflow: auto;
  overflow-x: hidden;
}

.device-tree-node {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  min-width: 0;
  max-width: 100%;
}

.device-tree-node__name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  width: 100%;
  min-width: 0;
  white-space: nowrap;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
}

.device-tree-node__id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  width: 100%;
  min-width: 0;
  white-space: nowrap;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
