<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('slaPage.title')" :description="t('slaPage.description')">
          <template #actions>
            <div class="flex items-center gap-2">
              <el-select v-model="stateFilter" style="width: 160px">
                <el-option :label="t('slaPage.allStates')" value="" />
                <el-option :label="t('slaPage.stateOpen')" value="open" />
                <el-option :label="t('slaPage.stateAcknowledged')" value="acknowledged" />
              </el-select>
              <el-input-number v-model="minEscalationLevel" :min="0" :max="10" :placeholder="t('slaPage.minLevel')" />
              <el-button type="primary" @click="refreshAll" :loading="loading">{{ t('slaPage.refresh') }}</el-button>
            </div>
          </template>
        </PageHeader>
      </template>

    <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
      <el-card class="app-surface">
        <div class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.unacknowledgedAlarms') }}</div>
        <div class="text-2xl font-bold text-rose-400">{{ overview.total_open }}</div>
      </el-card>
      <el-card class="app-surface">
        <div class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.escalatedUnack') }}</div>
        <div class="text-2xl font-bold text-amber-300">{{ overview.escalated_open }}</div>
      </el-card>
      <el-card class="app-surface">
        <div class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.overdueUnack') }}</div>
        <div class="text-2xl font-bold text-yellow-300">{{ overview.overdue_open }}</div>
      </el-card>
      <el-card class="app-surface">
        <div class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.acknowledgedToday') }}</div>
        <div class="text-2xl font-bold text-emerald-400">{{ overview.acknowledged_today }}</div>
      </el-card>
      <el-card class="app-surface">
        <div class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.avgAckMinutesToday') }}</div>
        <div class="text-2xl font-bold text-sky-400">{{ overview.avg_ack_minutes_today }}</div>
      </el-card>
    </div>

    <TableCard>
      <el-table :data="paginatedAlarms" v-loading="loading" stripe border style="width: 100%" :empty-text="t('slaPage.noAlarms')">
        <el-table-column prop="time" :label="t('slaPage.timeCol')" width="170">
          <template #default="scope">
            {{ formatDate(scope.row.time) }}
          </template>
        </el-table-column>
        <el-table-column prop="device_id" :label="t('slaPage.deviceCol')" width="170" />
        <el-table-column prop="description" :label="t('slaPage.descriptionCol')" min-width="220" show-overflow-tooltip />
        <el-table-column prop="priority" :label="t('slaPage.priorityCol')" width="90">
          <template #default="scope">
            <el-tag :type="getPriorityType(scope.row.priority)" size="small">{{ scope.row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="escalation_level" :label="t('slaPage.escalationLevelCol')" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.escalation_level > 1 ? 'danger' : scope.row.escalation_level > 0 ? 'warning' : 'info'" size="small">
              {{ scope.row.escalation_level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="escalation_state" :label="t('slaPage.stateCol')" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.escalation_state === 'acknowledged' ? 'success' : 'danger'" effect="plain" size="small">
              {{ scope.row.escalation_state === 'acknowledged' ? t('slaPage.stateAcknowledged') : t('slaPage.stateOpen') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="escalation_note" :label="t('slaPage.noteCol')" min-width="180" show-overflow-tooltip />
        <el-table-column :label="t('slaPage.actionCol')" width="230" fixed="right">
          <template #default="scope">
            <div class="table-action-inline">
              <el-dropdown trigger="click">
                <el-button size="small">
                  {{ t('slaPage.playback') }} <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="goPlayback(scope.row, 1)">{{ t('slaPage.playback1Min') }}</el-dropdown-item>
                    <el-dropdown-item @click="goPlayback(scope.row, 5)">{{ t('slaPage.playback5Min') }}</el-dropdown-item>
                    <el-dropdown-item @click="goPlayback(scope.row, 15)">{{ t('slaPage.playback15Min') }}</el-dropdown-item>
                    <el-dropdown-item @click="goPlayback(scope.row, 30)">{{ t('slaPage.playback30Min') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" @click="goTvWall(scope.row)">{{ t('slaPage.toTvWall') }}</el-button>
              <el-dropdown trigger="click" @command="(cmd: string) => handleAlarmMoreCommand(scope.row, cmd)">
                <el-button size="small" plain class="table-action-more">{{ t('slaPage.more') }}</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="command">{{ t('slaPage.command') }}</el-dropdown-item>
                    <el-dropdown-item command="workorder">{{ t('slaPage.createWorkOrder') }}</el-dropdown-item>
                    <el-dropdown-item command="escalate" :disabled="scope.row.escalation_state === 'acknowledged'">{{ t('slaPage.escalate') }}</el-dropdown-item>
                    <el-dropdown-item command="ack" :disabled="scope.row.escalation_state === 'acknowledged'">{{ t('slaPage.acknowledge') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="mt-4 flex justify-end">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="alarms.length"
        />
      </div>
    </TableCard>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
      <el-card>
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-semibold">{{ t('slaPage.alarmCompareTitle') }}</span>
            <el-input-number v-model="compareDays" :min="3" :max="30" size="small" style="width: 120px" @change="fetchCompare" />
          </div>
        </template>
        <div v-loading="compareLoading" class="space-y-3">
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.currentPeriod') }}</span>
            <span class="text-lg font-bold">{{ compare.period_current }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.previousPeriod') }}</span>
            <span class="text-lg font-bold">{{ compare.period_previous }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.periodChangeRate') }}</span>
            <span class="text-lg font-bold" :style="{ color: compare.period_change_pct > 0 ? 'var(--el-color-danger)' : compare.period_change_pct < 0 ? 'var(--el-color-success)' : '' }">
              {{ compare.period_change_pct > 0 ? '+' : '' }}{{ compare.period_change_pct.toFixed(1) }}%
            </span>
          </div>
          <el-divider class="!my-2" />
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.today') }}</span>
            <span class="text-lg font-bold">{{ compare.day_current }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.yesterday') }}</span>
            <span class="text-lg font-bold">{{ compare.day_previous }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.dayChangeRate') }}</span>
            <span class="text-lg font-bold" :style="{ color: compare.day_change_pct > 0 ? 'var(--el-color-danger)' : compare.day_change_pct < 0 ? 'var(--el-color-success)' : '' }">
              {{ compare.day_change_pct > 0 ? '+' : '' }}{{ compare.day_change_pct.toFixed(1) }}%
            </span>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-semibold">{{ t('slaPage.ackQualityTitle') }}</span>
            <el-input-number v-model="qualityDays" :min="3" :max="30" size="small" style="width: 120px" @change="fetchQuality" />
          </div>
        </template>
        <div v-loading="qualityLoading" class="space-y-3">
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.p50AckMinutes') }}</span>
            <span class="text-lg font-bold">{{ quality.p50_ack_minutes?.toFixed(1) ?? '-' }} {{ t('slaPage.minutes') }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.p90AckMinutes') }}</span>
            <span class="text-lg font-bold" :style="{ color: (quality.p90_ack_minutes ?? 0) > 30 ? 'var(--el-color-danger)' : '' }">{{ quality.p90_ack_minutes?.toFixed(1) ?? '-' }} {{ t('slaPage.minutes') }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('slaPage.ackSamples') }}</span>
            <span class="text-lg font-bold">{{ quality.samples ?? 0 }}</span>
          </div>
          <el-divider class="!my-2" />
          <div class="text-sm font-semibold mb-1" style="color: var(--el-text-color-secondary)">{{ t('slaPage.levelDistribution') }}</div>
          <div class="flex gap-2 flex-wrap">
            <el-tag v-for="(count, level) in quality.level_distribution" :key="String(level)" size="small">{{ level }}: {{ count }}</el-tag>
          </div>
          <div v-if="quality.slow_samples?.length" class="mt-2">
            <div class="text-sm font-semibold mb-1" style="color: var(--el-text-color-secondary)">{{ t('slaPage.slowestTop', { count: quality.slow_samples!.length }) }}</div>
            <div v-for="s in quality.slow_samples" :key="s.alarm_id" class="text-xs flex justify-between py-1 border-b" style="border-color: var(--el-border-color-extra-light)">
              <span>{{ s.device_id?.slice(0, 12) || '-' }}</span>
              <span :style="{ color: s.ack_minutes! > 60 ? 'var(--el-color-danger)' : '' }">{{ s.ack_minutes?.toFixed(1) }} {{ t('slaPage.minutes') }}</span>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <el-card class="mt-4">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-semibold">{{ t('slaPage.dashboardPresets') }}</span>
          <div class="flex gap-2">
            <el-button size="small" @click="loadPresets" :loading="presetsLoading">{{ t('slaPage.refresh') }}</el-button>
            <el-button size="small" type="primary" :disabled="!presetsWritable" @click="savePresets" :loading="presetsSaving">{{ t('slaPage.savePreset') }}</el-button>
          </div>
        </div>
      </template>
      <div v-if="!presetsWritable" class="text-xs mb-2" style="color: var(--el-text-color-secondary)">{{ t('slaPage.adminOnlyEdit') }}</div>
      <el-table :data="presetItems" stripe :empty-text="t('slaPage.noPresets')">
        <el-table-column prop="name" :label="t('slaPage.presetNameCol')" min-width="200">
          <template #default="{ row }">
            <el-input v-if="presetsWritable" v-model="row.name" size="small" :placeholder="t('slaPage.presetNameCol')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('slaPage.configCol')" min-width="300">
          <template #default="{ row }">
            <el-input v-if="presetsWritable" v-model="row.configJson" type="textarea" :rows="2" size="small" :placeholder="t('slaPage.jsonConfigPlaceholder')" />
            <pre v-else class="text-xs whitespace-pre-wrap">{{ typeof row.config === 'string' ? row.config : JSON.stringify(row.config, null, 2) }}</pre>
          </template>
        </el-table-column>
        <el-table-column :label="t('slaPage.actionCol')" width="80" v-if="presetsWritable">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="presetItems.splice($index, 1)">{{ t('slaPage.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button v-if="presetsWritable" size="small" class="mt-2" @click="presetItems.push({ name: '', config: {}, configJson: '{}' })">{{ t('slaPage.addPreset') }}</el-button>
    </el-card>

    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'

interface AlarmItem {
  id: string
  time: string
  device_id: string
  channel_id?: string
  description: string
  priority: string
  escalation_level: number
  escalation_state: string
  escalation_note: string | null
}

interface SlaOverview {
  total_open: number
  escalated_open: number
  overdue_open: number
  acknowledged_today: number
  avg_ack_minutes_today: number
}

interface SlaSlowSample {
  alarm_id: string
  device_id?: string
  ack_minutes?: number
}

interface SlaQuality {
  p50_ack_minutes?: number
  p90_ack_minutes?: number
  samples?: number
  level_distribution?: Record<string, number>
  slow_samples?: SlaSlowSample[]
}

const { t } = useI18n()
const loading = ref(false)
const alarms = ref<AlarmItem[]>([])
const page = ref(1)
const pageSize = ref(10)

const paginatedAlarms = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return alarms.value.slice(start, start + pageSize.value)
})

watch(() => alarms.value, () => {
  page.value = 1
})
const router = useRouter()
const stateFilter = ref('')
const minEscalationLevel = ref(0)
const overview = ref<SlaOverview>({
  total_open: 0,
  escalated_open: 0,
  overdue_open: 0,
  acknowledged_today: 0,
  avg_ack_minutes_today: 0
})

const fetchOverview = async () => {
  try {
    const res = await api.get('/api/v1/alarms/sla/overview')
    overview.value = res.data ?? { total_open: 0, escalated_open: 0, overdue_open: 0, acknowledged_today: 0, avg_ack_minutes_today: 0 }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const fetchAlarms = async () => {
  try {
    const params: Record<string, string | number> = {
      limit: 100,
      min_escalation_level: minEscalationLevel.value
    }
    if (stateFilter.value) params.escalation_state = stateFilter.value
    const res = await api.get('/api/v1/alarms', { params })
    alarms.value = Array.isArray(res.data?.items) ? res.data.items : (Array.isArray(res.data) ? res.data : [])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const refreshAll = async () => {
  loading.value = true
  try {
    await Promise.all([fetchOverview(), fetchAlarms()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const handleEscalate = async (row: AlarmItem) => {
  try {
    const { value } = await ElMessageBox.prompt(t('slaPage.escalatePrompt'), t('slaPage.escalateTitle', { id: row.id }), {
      confirmButtonText: t('slaPage.confirmEscalate'),
      cancelButtonText: t('slaPage.cancel')
    })
    await api.post(`/api/v1/alarms/${row.id}/escalate`, { note: value || null })
    ElMessage.success(t('slaPage.alarmEscalated'))
    await refreshAll()
  } catch (e: unknown) {
    if (e === 'cancel' || e === 'close') return
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const handleAcknowledge = async (row: AlarmItem) => {
  try {
    const { value } = await ElMessageBox.prompt(t('slaPage.ackPrompt'), t('slaPage.ackTitle', { id: row.id }), {
      confirmButtonText: t('slaPage.confirmAck'),
      cancelButtonText: t('slaPage.cancel')
    })
    await api.post(`/api/v1/alarms/${row.id}/ack`, { note: value || null })
    ElMessage.success(t('slaPage.alarmAcknowledged'))
    await refreshAll()
  } catch (e: unknown) {
    if (e === 'cancel' || e === 'close') return
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const createWorkOrder = async (row: AlarmItem) => {
  try {
    await api.post('/api/v1/work-orders', {
      alarm_id: row.id,
      title: t('slaPage.workOrderTitle', { deviceId: row.device_id, id: row.id.slice(0, 6) }),
      description: row.description,
      priority: row.escalation_level > 1 ? 'high' : row.escalation_level > 0 ? 'medium' : 'low'
    })
    ElMessage.success(t('slaPage.workOrderCreated'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const goPlayback = (row: AlarmItem, windowMinutes: number = 30) => {
  const deviceId = String(row.device_id || '').trim()
  const channelId = String(row.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('slaPage.missingDeviceChannelPlayback'))
    return
  }
  const time = row.time || ''
  router.push({ path: '/devices', query: { device_id: deviceId, channel_id: channelId, time, tab: 'timeline', window_minutes: String(windowMinutes) } })
}

const goTvWall = (row: AlarmItem) => {
  const deviceId = String(row.device_id || '').trim()
  const channelId = String(row.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('slaPage.missingDeviceChannelTvWall'))
    return
  }
  if (!router.hasRoute('TvWall')) {
    ElMessage.warning(t('slaPage.tvWallPluginRequired'))
    router.push('/plugins')
    return
  }
  router.push({ path: '/tv-wall', query: { device_id: deviceId, channel_id: channelId } })
}

const goVisualCommand = (row: AlarmItem) => {
  const deviceId = String(row.device_id || '').trim()
  const channelId = String(row.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('slaPage.missingDeviceChannelCommand'))
    return
  }
  if (!router.hasRoute('VisualCommand')) {
    ElMessage.warning(t('slaPage.visualCommandPluginRequired'))
    router.push('/plugins')
    return
  }
  router.push({ path: '/visual-command', query: { device_id: deviceId, channel_id: channelId } })
}

const handleAlarmMoreCommand = async (row: AlarmItem, cmd: string) => {
  try {
    if (cmd === 'command') {
      goVisualCommand(row)
      return
    }
    if (cmd === 'workorder') {
      await createWorkOrder(row)
      return
    }
    if (cmd === 'escalate') {
      await handleEscalate(row)
      return
    }
    if (cmd === 'ack') {
      await handleAcknowledge(row)
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const getPriorityType = (priority: string) => {
  if (priority === '1') return 'danger'
  if (priority === '2') return 'warning'
  return 'info'
}

const formatDate = (value: string) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

watch([stateFilter, minEscalationLevel], () => {
  refreshAll()
})

const compareDays = ref(7)
const compareLoading = ref(false)
const compare = ref<{ period_current: number; period_previous: number; period_change_pct: number; day_current: number; day_previous: number; day_change_pct: number }>({ period_current: 0, period_previous: 0, period_change_pct: 0, day_current: 0, day_previous: 0, day_change_pct: 0 })

const fetchCompare = async () => {
  compareLoading.value = true
  try {
    const res = await api.get('/api/v1/alarms/sla/compare', { params: { days: compareDays.value } })
    const d = res.data ?? {}
    compare.value = {
      period_current: Number(d.period_current ?? 0),
      period_previous: Number(d.period_previous ?? 0),
      period_change_pct: Number(d.period_change_pct ?? 0),
      day_current: Number(d.day_current ?? 0),
      day_previous: Number(d.day_previous ?? 0),
      day_change_pct: Number(d.day_change_pct ?? 0)
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    compareLoading.value = false
  }
}

const qualityDays = ref(7)
const qualityLoading = ref(false)
const quality = ref<SlaQuality>({})

const fetchQuality = async () => {
  qualityLoading.value = true
  try {
    const res = await api.get('/api/v1/alarms/sla/quality', { params: { days: qualityDays.value } })
    quality.value = res.data || {}
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    qualityLoading.value = false
  }
}

const presetItems = ref<{ name: string; config: Record<string, unknown>; configJson: string }[]>([])
const presetsWritable = ref(false)
const presetsLoading = ref(false)
const presetsSaving = ref(false)

const loadPresets = async () => {
  presetsLoading.value = true
  try {
    const res = await api.get('/api/v1/alarms/sla/presets')
    presetsWritable.value = Boolean(res.data?.writable)
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    presetItems.value = items.map((it: Record<string, unknown>) => ({ ...it, configJson: typeof it.config === 'string' ? it.config : JSON.stringify(it.config || {}, null, 2) }))
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    presetsLoading.value = false
  }
}

const savePresets = async () => {
  presetsSaving.value = true
  try {
    const items = presetItems.value.filter(it => it.name.trim()).map(it => {
      let parsed = it.config
      try { parsed = JSON.parse(it.configJson) } catch { /* invalid JSON: skip */ }
      return { name: it.name, config: parsed }
    })
    await api.put('/api/v1/alarms/sla/presets', { items })
    ElMessage.success(t('slaPage.presetsSaved'))
    await loadPresets()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    presetsSaving.value = false
  }
}

onMounted(() => {
  refreshAll()
  fetchCompare()
  fetchQuality()
  loadPresets()
})
</script>
