<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('record.title')" :description="t('record.description')">
          <template #actions>
            <el-button @click="$router.push('/ops')">{{ t('record.opsCenter') }}</el-button>
            <el-button type="primary" @click="openForm()">{{ t('record.addPlan') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <QueryFormSection :title="t('record.filter')" :default-collapsed="true">
        <el-form-item :label="t('record.planType')">
          <el-select v-model="filterPlanType" :placeholder="t('record.planType')" clearable style="width: 160px" @change="fetchSchedules">
            <el-option :label="t('record.planTypeTimed')" value="timed" />
            <el-option :label="t('record.planTypeMotion')" value="motion" />
            <el-option :label="t('record.planTypeAlarm')" value="alarm" />
            <el-option :label="t('record.planTypeManual')" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="fetchSchedules" :loading="loading" type="primary">{{ t('record.apply') }}</el-button>
        </el-form-item>
      </QueryFormSection>

      <TableCard class="mt-4">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('record.list') }}</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('record.totalCount', { n: schedules.length }) }}</div>
          </div>
        </template>
      <el-table :data="paginatedItems" border v-loading="loading" :empty-text="t('record.emptyHint')">
        <el-table-column :label="t('record.channelCol')" min-width="200">
          <template #default="{ row }">
            {{ channelLabel(row.resource_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="plan_type" :label="t('record.typeCol')" width="100">
          <template #default="{ row }">
            {{ planTypeLabel(row.plan_type) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('common.enable')" width="80">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? t('common.yes') : t('common.no') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="t('record.priority')" width="90" />
        <el-table-column :label="t('record.runtimeCol')" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="space-y-1">
              <div>
                <el-tag v-if="runtime(row)?.is_recording" type="success" size="small">{{ t('record.recording') }}</el-tag>
                <el-tag v-else-if="runtime(row)?.desired_recording" type="warning" size="small">{{ t('record.desiredRecording') }}</el-tag>
                <el-tag v-else type="info" size="small">{{ t('record.notRecording') }}</el-tag>
                <el-tag v-if="runtime(row)?.forced_mode" type="primary" size="small" class="ml-2">
                  {{ t(runtime(row)?.forced_mode === 'on' ? 'record.forceOn' : 'record.forceOff') }}
                </el-tag>
              </div>
              <div class="text-xs" style="color: var(--el-text-color-secondary)">
                {{ runtime(row)?.last_action_at || runtime(row)?.last_eval_at || '—' }}
                <span v-if="runtime(row)?.last_error" style="color:#ef4444">；{{ runtime(row)?.last_error }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action')" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">{{ t('common.edit') }}</el-button>
            <el-dropdown>
              <span class="el-dropdown-link text-primary text-xs" style="cursor:pointer">{{ t('record.more') }}</span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="forceStart(row)">{{ t('record.forceStartItem', { minutes: 60 }) }}</el-dropdown-item>
                  <el-dropdown-item @click="forceStop(row)">{{ t('record.forceStopItem', { minutes: 10 }) }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button link type="danger" size="small" @click="handleDelete(row)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex justify-end mt-4 pagination-wrapper" v-if="filteredItems.length > 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="filteredItems.length"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          :prev-text="t('pagination.prev')"
          :next-text="t('pagination.next')"
          size="small"
        />
      </div>
      </TableCard>

      <div class="text-sm" style="color: var(--el-text-color-secondary)">
        {{ t('record.storageHintPrefix') }}
        <router-link to="/ops" class="text-primary hover:underline">{{ t('record.storageHintLink') }}</router-link>
        {{ t('record.storageHintSuffix') }}
      </div>

    <AppDialog v-model="dialogVisible" :title="editingId ? t('record.editTitle') : t('record.addTitle')" size="medium" @closed="resetForm">
      <el-form :model="form" label-width="100px" size="small">
        <el-form-item v-if="!editingId" :label="t('record.planTarget')" required>
          <el-radio-group v-model="form.target_scope">
            <el-radio label="channel">{{ t('record.singleChannel') }}</el-radio>
            <el-radio label="device">{{ t('record.deviceAllChannels') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="!editingId && form.target_scope === 'device'" :label="t('record.deviceLabel')" required>
          <el-select v-model="form.asset_id" :placeholder="t('record.selectDevicePlaceholder')" filterable style="width: 100%">
            <el-option v-for="d in deviceOptions" :key="d.asset_id" :label="t('record.deviceChannelCount', { name: d.device_name, count: d.channel_count })" :value="d.asset_id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!editingId && form.target_scope === 'device'">
          <el-alert type="info" :closable="false" show-icon>
            <template #title>
              {{ t('record.batchApplyHint', { count: selectedDeviceChannelCount }) }}
            </template>
          </el-alert>
        </el-form-item>
        <el-form-item v-if="editingId || form.target_scope === 'channel'" :label="t('record.channelCol')" required>
          <el-select
            v-model="form.resource_id"
            :placeholder="t('record.selectChannelPlaceholder')"
            filterable
            style="width: 100%"
            :disabled="!!editingId"
          >
            <el-option
              v-for="ch in channels"
              :key="ch.id"
              :label="t('record.channelOptionLabel', { device: ch.device_name || ch.device_id, name: ch.name || ch.gb_id })"
              :value="ch.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('record.planType')" required>
          <el-select v-model="form.plan_type" style="width: 100%">
            <el-option :label="t('record.planTypeTimed')" value="timed" />
            <el-option :label="t('record.planTypeMotion')" value="motion" />
            <el-option :label="t('record.planTypeAlarm')" value="alarm" />
            <el-option :label="t('record.planTypeManual')" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('common.enable')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item :label="t('record.priority')">
          <el-input-number v-model="form.priority" :min="0" />
        </el-form-item>
        <template v-if="form.plan_type === 'timed'">
          <el-form-item :label="t('record.quickTemplate')">
            <div class="quick-template-wrap">
              <el-button size="small" @click="applyQuickTemplate('all_day')">{{ t('record.tplAllDay') }}</el-button>
              <el-button size="small" @click="applyQuickTemplate('workday_daytime')">{{ t('record.tplWorkdayDaytime') }}</el-button>
              <el-button size="small" @click="applyQuickTemplate('workday_all')">{{ t('record.tplWorkdayAll') }}</el-button>
              <el-button size="small" @click="applyQuickTemplate('weekend_all')">{{ t('record.tplWeekendAll') }}</el-button>
            </div>
          </el-form-item>
          <el-form-item :label="t('record.scheduleMode')">
            <el-select v-model="form.schedule_mode" style="width: 100%">
              <el-option :label="t('record.modeDaily')" value="daily" />
              <el-option :label="t('record.modeWeekdays')" value="weekdays" />
              <el-option :label="t('record.modeWeekend')" value="weekend" />
              <el-option :label="t('record.modeCustom')" value="custom" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.schedule_mode === 'custom'" :label="t('record.weekday')">
            <el-checkbox-group v-model="form.custom_days">
              <el-checkbox :label="1">{{ t('record.mon') }}</el-checkbox>
              <el-checkbox :label="2">{{ t('record.tue') }}</el-checkbox>
              <el-checkbox :label="3">{{ t('record.wed') }}</el-checkbox>
              <el-checkbox :label="4">{{ t('record.thu') }}</el-checkbox>
              <el-checkbox :label="5">{{ t('record.fri') }}</el-checkbox>
              <el-checkbox :label="6">{{ t('record.sat') }}</el-checkbox>
              <el-checkbox :label="0">{{ t('record.sun') }}</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item :label="t('record.timeRange')">
            <div class="time-range-editor">
              <el-time-select
                v-model="form.start_time"
                start="00:00"
                step="00:15"
                end="23:45"
                :max-time="form.end_time || undefined"
                :placeholder="t('common.startTime')"
              />
              <span class="time-sep">{{ t('record.rangeSeparator') }}</span>
              <el-time-select
                v-model="form.end_time"
                start="00:00"
                step="00:15"
                end="23:59"
                :min-time="form.start_time || undefined"
                :placeholder="t('common.endTime')"
              />
            </div>
          </el-form-item>
          <el-form-item :label="t('record.advancedMode')">
            <el-switch v-model="form.advanced_time_ranges" />
            <span class="ml-2 text-xs" style="color: var(--el-text-color-secondary)">{{ t('record.advancedHint') }}</span>
          </el-form-item>
          <el-form-item v-if="form.advanced_time_ranges" :label="t('record.timeRangesJson')">
            <el-input v-model="form.time_ranges_str" type="textarea" :rows="3" placeholder='[{"start":"00:00","end":"23:59","days":[0,1,2,3,4,5,6]}]' />
          </el-form-item>
        </template>
        <el-form-item v-else :label="t('record.noteLabel')">
          <el-alert type="info" :closable="false" show-icon :title="t('record.eventPlanNote')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.ok') }}</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'  // FIX: [2026-07-04] 缺失 useI18n 导入导致 ReferenceError [全栈工程师]
import api from '@/utils/http'
import { logger } from '@/utils/logger'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getApiErrorMessage, getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import QueryFormSection from '../components/QueryFormSection.vue'
import AppDialog from '../components/common/AppDialog.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const { t } = useI18n()

const schedules = ref<ScheduleItem[]>([])
const channels = ref<ScheduleItem[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<string | null>(null)
const filterPlanType = ref('')
const runtimes = ref<ScheduleItem[]>([])

const form = reactive({
  target_scope: 'channel',
  asset_id: '',
  resource_id: '',
  plan_type: 'timed',
  enabled: true,
  priority: 0,
  schedule_mode: 'daily',
  custom_days: [1, 2, 3, 4, 5],
  start_time: '00:00',
  end_time: '23:59',
  advanced_time_ranges: false,
  time_ranges_str: '[]'
})

const planTypeLabel = (v: string) =>
  ({ timed: t('record.planTypeTimed'), motion: t('record.planTypeMotion'), alarm: t('record.planTypeAlarm'), manual: t('record.planTypeManual') }[v] || v)

const channelMap = computed(() => {
  const m: Record<string, string> = {}
  for (const ch of channels.value) {
    m[ch.id] = `${ch.device_name || ch.device_id} / ${ch.name || ch.gb_id}`
  }
  return m
})

const channelLabel = (resourceId: string) => channelMap.value[resourceId] || resourceId

const deviceOptions = computed(() => {
  const map: Record<string, { asset_id: string; device_name: string; channel_count: number }> = {}
  for (const ch of channels.value || []) {
    const aid = String(ch?.asset_id || '').trim()
    if (!aid) continue
    if (!map[aid]) {
      map[aid] = {
        asset_id: aid,
        device_name: String(ch?.device_name || ch?.device_id || aid),
        channel_count: 0
      }
    }
    map[aid].channel_count += 1
  }
  return Object.values(map).sort((a, b) => a.device_name.localeCompare(b.device_name))
})

const selectedDeviceChannelCount = computed(() => {
  const aid = String(form.asset_id || '').trim()
  if (!aid) return 0
  return (channels.value || []).filter((ch: Record<string, unknown>) => String(ch?.asset_id || '') === aid).length
})

type ScheduleRuntimeRow = {
  is_recording?: boolean
  desired_recording?: boolean
  forced_mode?: string
  last_action_at?: string
  last_eval_at?: string
  last_error?: string
}

const runtimeMap = computed(() => {
  const m: Record<string, ScheduleRuntimeRow> = {}
  for (const r of runtimes.value || []) {
    if (r && r.schedule_id) m[String(r.schedule_id)] = r as ScheduleRuntimeRow
  }
  return m
})

const runtime = (row: Record<string, unknown>): ScheduleRuntimeRow | undefined => runtimeMap.value[String(row?.id || '')]

const filteredItems = computed(() => {
  return schedules.value || []
})

const page = ref(1)
const pageSize = ref(10)
const paginatedItems = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredItems.value.slice(start, end)
})

const fetchChannels = async () => {
  try {
    const res = await api.get('/api/v1/devices/channels/flat', { params: { node_type: 'channel', skip: 0, limit: 5000 } })
    channels.value = Array.isArray(res.data?.items) ? res.data.items : []
  } catch (e: unknown) {
    channels.value = []
    logger.warn('加载通道列表失败', e)
  }
}

const fetchSchedules = async () => {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (filterPlanType.value) params.plan_type = filterPlanType.value
    const res = await api.get('/api/v1/record-schedule', { params })
    schedules.value = Array.isArray(res.data) ? res.data : []
    await fetchRuntimes()
  } catch (e: unknown) {
    schedules.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const openForm = (row?: Record<string, unknown>) => {
  editingId.value = row?.id || null
  if (row) {
    form.target_scope = 'channel'
    form.asset_id = ''
    form.resource_id = row.resource_id
    form.plan_type = row.plan_type || 'timed'
    form.enabled = row.enabled !== false
    form.priority = row.priority ?? 0
    const tr = Array.isArray(row.time_ranges) ? row.time_ranges : []
    form.time_ranges_str = JSON.stringify(tr, null, 2)
    form.advanced_time_ranges = false
    if (tr.length > 0) {
      const first = tr[0] || {}
      form.start_time = String(first.start || '00:00')
      form.end_time = String(first.end || '23:59')
      const days = Array.isArray(first.days) ? first.days.map((d: Record<string, unknown>) => Number(d)).filter((d: number) => !Number.isNaN(d)) : []
      if (days.length === 7) {
        form.schedule_mode = 'daily'
      } else if ([1, 2, 3, 4, 5].every((d) => days.includes(d)) && !days.includes(0) && !days.includes(6)) {
        form.schedule_mode = 'weekdays'
      } else if (days.length === 2 && days.includes(0) && days.includes(6)) {
        form.schedule_mode = 'weekend'
      } else {
        form.schedule_mode = 'custom'
      }
      form.custom_days = days.length ? days : [1, 2, 3, 4, 5]
    }
  } else {
    resetForm()
  }
  dialogVisible.value = true
}

const resetForm = () => {
  form.target_scope = 'channel'
  form.asset_id = ''
  form.resource_id = ''
  form.plan_type = 'timed'
  form.enabled = true
  form.priority = 0
  form.schedule_mode = 'daily'
  form.custom_days = [1, 2, 3, 4, 5]
  form.start_time = '00:00'
  form.end_time = '23:59'
  form.advanced_time_ranges = false
  form.time_ranges_str = '[]'
}

const buildTimeRanges = (): Record<string, unknown>[] => {
  if (form.plan_type !== 'timed') return []
  if (form.advanced_time_ranges) {
    let parsed: unknown = [] // FIXED: JSON.parse包裹try-catch
    try {
      parsed = JSON.parse(form.time_ranges_str || '[]')
    } catch {
      parsed = []
    }
    return Array.isArray(parsed) ? parsed : []
  }
  const start = String(form.start_time || '').trim()
  const end = String(form.end_time || '').trim()
  if (!start || !end) throw new Error(t('record.timeRangeRequired'))
  let days: number[] = []
  if (form.schedule_mode === 'daily') days = [0, 1, 2, 3, 4, 5, 6]
  else if (form.schedule_mode === 'weekdays') days = [1, 2, 3, 4, 5]
  else if (form.schedule_mode === 'weekend') days = [0, 6]
  else days = (form.custom_days || []).map((d: Record<string, unknown>) => Number(d)).filter((d: number) => !Number.isNaN(d))
  if (!days.length) throw new Error(t('record.weekdayRequired'))
  return [{ start, end, days }]
}

const getAllSchedulesForUpsert = async () => {
  const res = await api.get('/api/v1/record-schedule')
  return Array.isArray(res.data) ? res.data : []
}

const applyQuickTemplate = (key: 'all_day' | 'workday_daytime' | 'workday_all' | 'weekend_all') => {
  form.advanced_time_ranges = false
  if (key === 'all_day') {
    form.schedule_mode = 'daily'
    form.custom_days = [0, 1, 2, 3, 4, 5, 6]
    form.start_time = '00:00'
    form.end_time = '23:59'
    return
  }
  if (key === 'workday_daytime') {
    form.schedule_mode = 'weekdays'
    form.custom_days = [1, 2, 3, 4, 5]
    form.start_time = '09:00'
    form.end_time = '18:00'
    return
  }
  if (key === 'workday_all') {
    form.schedule_mode = 'weekdays'
    form.custom_days = [1, 2, 3, 4, 5]
    form.start_time = '00:00'
    form.end_time = '23:59'
    return
  }
  form.schedule_mode = 'weekend'
  form.custom_days = [0, 6]
  form.start_time = '00:00'
  form.end_time = '23:59'
}

const submitForm = async () => {
  let timeRanges: Record<string, unknown>[] = []
  try {
    timeRanges = buildTimeRanges()
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, t('record.configInvalid')))
    return
  }
  submitting.value = true
  try {
    const payloadBase = {
      plan_type: form.plan_type,
      enabled: form.enabled,
      priority: form.priority,
      time_ranges: timeRanges
    }
    if (editingId.value) {
      await api.put(`/api/v1/record-schedule/${editingId.value}`, {
        ...payloadBase
      })
      ElMessage.success(t('common.updated'))
    } else {
      if (form.target_scope === 'channel') {
        if (!form.resource_id) {
          ElMessage.warning(t('record.selectChannel'))
          return
        }
        await api.post('/api/v1/record-schedule', {
          resource_id: form.resource_id,
          ...payloadBase
        })
        ElMessage.success(t('common.created'))
      } else {
        if (!form.asset_id) {
          ElMessage.warning(t('record.selectDevice'))
          return
        }
        const targetIds = (channels.value || [])
          .filter((ch: Record<string, unknown>) => String(ch?.asset_id || '') === String(form.asset_id))
          .map((ch: Record<string, unknown>) => String(ch.id))
          .filter((id) => !!id)
        if (!targetIds.length) {
          ElMessage.warning(t('record.noChannels'))
          return
        }
        const allSchedules = await getAllSchedulesForUpsert()
        const existingMap: Record<string, { id?: string; resource_id?: string; plan_type?: string }> = {}
        for (const s of allSchedules) {
          existingMap[`${String(s.resource_id)}::${String(s.plan_type)}`] = s
        }
        let created = 0
        let updated = 0
        let failed = 0
        for (const rid of targetIds) {
          const key = `${rid}::${form.plan_type}`
          const existing = existingMap[key]
          try {
            if (existing?.id) {
              await api.put(`/api/v1/record-schedule/${existing.id}`, { ...payloadBase })
              updated += 1
            } else {
              await api.post('/api/v1/record-schedule', { resource_id: rid, ...payloadBase })
              created += 1
            }
          } catch {
            failed += 1
          }
        }
        if (failed > 0) {
          ElMessage.warning(t('record.batchResultWarn', { created, updated, failed }))
        } else {
          ElMessage.success(t('record.batchResultSuccess', { created, updated }))
        }
      }
    }
    dialogVisible.value = false
    await fetchSchedules()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(t('record.deleteConfirm'), t('common.tips'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/record-schedule/${row.id}`)
    ElMessage.success(t('common.deleted'))
    await fetchSchedules()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const fetchRuntimes = async () => {
  try {
    const res = await api.get('/api/v1/record-schedule/runtimes')
    runtimes.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    runtimes.value = []
    logger.warn('加载运行时状态失败', e)
  }
}

const forceStart = async (row: Record<string, unknown>) => {
  try {
    await api.post(`/api/v1/record-schedule/${row.id}/actions/force-start`, { minutes: 60 })
    ElMessage.success(t('record.forceStarted'))
    await fetchRuntimes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const forceStop = async (row: Record<string, unknown>) => {
  try {
    await api.post(`/api/v1/record-schedule/${row.id}/actions/force-stop`, { minutes: 10 })
    ElMessage.success(t('record.forceStopped'))
    await fetchRuntimes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

onMounted(async () => {
  await fetchChannels()
  await fetchSchedules()
})
</script>

<style scoped>
.time-range-editor {
  display: flex;
  align-items: center;
  gap: 10px;
}

.time-sep {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.quick-template-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
