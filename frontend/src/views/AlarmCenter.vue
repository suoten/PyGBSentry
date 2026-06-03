<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('alarm.title')" :description="t('alarm.description')">
          <template #actions>
              <el-button @click="$router.push('/monitor')" class="action-btn">
              <el-icon class="mr-1"><VideoCamera /></el-icon>
              {{ t('route.monitor') }}
            </el-button>
            <el-button type="primary" @click="fetchAlarms" :loading="loading" class="refresh-btn">
              <el-icon class="mr-1"><Refresh /></el-icon>
              {{ t('common.refresh') }}
            </el-button>
          </template>
        </PageHeader>
      </template>

      <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <el-card class="stat-card stat-card--open">
          <div class="stat-icon-wrapper">
            <el-icon class="stat-icon"><Bell /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('alarm.unreadAlarm') }}</div>
            <div class="stat-value">{{ unreadCount }}</div>
          </div>
        </el-card>
        <el-card class="stat-card stat-card--open">
          <div class="stat-icon-wrapper">
            <el-icon class="stat-icon"><Bell /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('alarm.unconfirmed') }}</div>
            <div class="stat-value">{{ overview.total_open }}</div>
          </div>
        </el-card>
        <el-card class="stat-card stat-card--escalated">
          <div class="stat-icon-wrapper">
            <el-icon class="stat-icon"><TrendCharts /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('alarm.escalated') }}</div>
            <div class="stat-value">{{ overview.escalated_open }}</div>
          </div>
        </el-card>
        <el-card class="stat-card stat-card--overdue">
          <div class="stat-icon-wrapper">
            <el-icon class="stat-icon"><Warning /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('alarm.overdue') }}</div>
            <div class="stat-value">{{ overview.overdue_open }}</div>
          </div>
        </el-card>
        <el-card class="stat-card stat-card--ack">
          <div class="stat-icon-wrapper">
            <el-icon class="stat-icon"><CircleCheck /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('alarm.acknowledgedToday') }}</div>
            <div class="stat-value">{{ overview.acknowledged_today }}</div>
          </div>
        </el-card>
        <el-card class="stat-card stat-card--avg">
          <div class="stat-icon-wrapper">
            <el-icon class="stat-icon"><Timer /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('alarm.avgAckMinutes') }}</div>
            <div class="stat-value">{{ overview.avg_ack_minutes_today }}</div>
          </div>
        </el-card>
      </div>

      <QueryFormSection :title="t('alarm.filterTitle')" :default-collapsed="true">
        <el-form-item :label="t('alarm.statusLabel')">
          <el-select v-model="filters.escalation_state" :placeholder="t('alarm.allStatus')" clearable class="filter-select">
            <el-option :label="t('alarm.unconfirmed')" value="open" />
            <el-option :label="t('alarm.confirmed')" value="acknowledged" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('alarm.minLevel')">
          <el-input-number v-model="filters.min_escalation_level" :min="0" :max="10" class="filter-number" />
        </el-form-item>
        <el-form-item>
          <el-button @click="fetchAlarms" :loading="loading" type="primary">
            <el-icon class="mr-1"><Search /></el-icon>
            {{ t('alarm.applyFilter') }}
          </el-button>
        </el-form-item>
        <el-form-item>
          <div class="text-xs text-slate-500 flex items-center gap-1">
            <el-icon><InfoFilled /></el-icon>
            {{ t('alarm.operationTip') }}
          </div>
        </el-form-item>
      </QueryFormSection>

      <TableCard class="alarms-card">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-bold text-slate-700 flex items-center gap-2">
              <el-icon class="text-slate-500"><AlarmClock /></el-icon>
              {{ t('alarm.alarmList') }}
            </div>
            <div class="text-xs text-slate-500 flex items-center gap-2">
              <el-icon><Document /></el-icon>
              {{ t('alarm.totalRecords', { total: total }) }}
            </div>
          </div>
        </template>
        <TableSkeleton v-if="loading && alarms.length === 0" :rows="6" />
        <el-table v-else :data="alarms" v-loading="loading" :empty-text="t('alarm.noAlarms')" class="alarms-table" :row-class-name="getAlarmRowClass" fit>
          <template #empty>
            <EmptyStateWithAction :description="t('alarm.noAlarmHint')">
              <template #action>
                <el-button type="primary" @click="$router.push('/monitor')" class="empty-action-btn">
                  <el-icon class="mr-1"><VideoCamera /></el-icon>
                  {{ t('route.monitor') }}
                </el-button>
              </template>
            </EmptyStateWithAction>
          </template>
          <el-table-column :label="t('alarm.timeLabel')" width="190">
            <template #header>
              <div class="flex items-center gap-1">
                <el-icon class="text-slate-400"><Clock /></el-icon>
                <span>{{ t('alarm.time') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="time-cell">
                <el-icon class="text-sky-400"><Clock /></el-icon>
                <span>{{ formatTime(row.time) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="device_id" :label="t('alarm.deviceId')" width="170">
            <template #header>
              <div class="flex items-center gap-1">
                <el-icon class="text-slate-400"><Monitor /></el-icon>
                <span>{{ t('alarm.deviceId') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="id-cell">
                <el-tag size="small" type="info" effect="plain">{{ row.device_id }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="channel_id" :label="t('alarm.channelId')" width="170">
            <template #header>
              <div class="flex items-center gap-1">
                <el-icon class="text-slate-400"><Connection /></el-icon>
                <span>{{ t('alarm.channelId') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="id-cell">
                <el-tag size="small" type="info" effect="plain">{{ row.channel_id }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="alarm_type" :label="t('alarm.typeLabel')" width="130">
            <template #header>
              <div class="flex items-center gap-1">
                <el-icon class="text-slate-400"><WarningFilled /></el-icon>
                <span>{{ t('alarm.type') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <el-tag :type="getAlarmTypeColor(row.alarm_type)" size="small" effect="dark" class="type-tag">
                {{ row.alarm_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" :label="t('alarm.description')" min-width="240" show-overflow-tooltip>
            <template #header>
              <div class="flex items-center gap-1">
                <el-icon class="text-slate-400"><ChatDotRound /></el-icon>
                <span>{{ t('alarm.description') }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="priority" :label="t('alarm.levelLabel')" width="100" align="center">
            <template #header>
              <div class="flex items-center justify-center gap-1">
                <el-icon class="text-slate-400"><Odometer /></el-icon>
                <span>{{ t('alarm.level') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="priority-cell">
                <span class="priority-badge" :class="'priority-' + row.priority">
                  L{{ row.priority }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('alarm.statusLabel')" width="110" align="center">
            <template #header>
              <div class="flex items-center justify-center gap-1">
                <el-icon class="text-slate-400"><CircleCheck /></el-icon>
                <span>{{ t('alarm.statusCol') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="status-cell">
                <span class="status-dot" :class="row.escalation_state === 'acknowledged' ? 'acknowledged' : 'open'"></span>
                <el-tag :type="row.escalation_state === 'acknowledged' ? 'success' : 'warning'" size="small" effect="dark">
                  {{ row.escalation_state === 'acknowledged' ? t('alarm.confirmedSuccess') : t('alarm.unconfirmed') }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('alarm.upgrade')" width="110" align="center">
            <template #header>
              <div class="flex items-center justify-center gap-1">
                <el-icon class="text-slate-400"><TrendCharts /></el-icon>
                <span>{{ t('alarm.upgrade') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="escalation-cell">
                <el-tag type="danger" size="small" effect="plain">L{{ row.escalation_level }}</el-tag>
                <span class="text-slate-500 text-sm">/ {{ row.escalation_count }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('alarm.action')" width="260" align="center">
            <template #header>
              <div class="flex items-center justify-center gap-1">
                <el-icon class="text-slate-400"><Tools /></el-icon>
                <span>{{ t('alarm.action') }}</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="action-buttons table-action-inline">
                <el-dropdown trigger="click">
                  <el-button size="small" class="playback-btn">
                    <el-icon class="mr-1"><VideoPlay /></el-icon>
                    {{ t('alarm.jumpToPlayback') }}
                    <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu class="playback-dropdown">
                      <el-dropdown-item @click="goPlayback(row, 1)">
                        <el-icon class="mr-1"><Clock /></el-icon>
                        {{ t('alarm.jumpTimeout', { minutes: 1 }) }}
                      </el-dropdown-item>
                      <el-dropdown-item @click="goPlayback(row, 5)">
                        <el-icon class="mr-1"><Clock /></el-icon>
                        {{ t('alarm.jumpTimeout', { minutes: 5 }) }}
                      </el-dropdown-item>
                      <el-dropdown-item @click="goPlayback(row, 15)">
                        <el-icon class="mr-1"><Clock /></el-icon>
                        {{ t('alarm.jumpTimeout', { minutes: 15 }) }}
                      </el-dropdown-item>
                      <el-dropdown-item @click="goPlayback(row, 30)">
                        <el-icon class="mr-1"><VideoPlay /></el-icon>
                        {{ t('alarm.jumpTimeout', { minutes: 30 }) }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>

                <el-button size="small" @click="goTvWall(row)" class="tv-wall-btn" plain>
                  <el-icon class="mr-1"><Monitor /></el-icon>
                  {{ t('alarm.tvWall') }}
                </el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => handleAlarmMoreCommand(row, cmd)">
                  <el-button size="small" plain class="table-action-more">{{ t('common.more') }}</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="command">{{ t('alarm.command') }}</el-dropdown-item>
                      <el-dropdown-item command="ack" :disabled="row.escalation_state === 'acknowledged'">{{ t('alarm.confirmAlarm') }}</el-dropdown-item>
                      <el-dropdown-item command="escalate" :disabled="row.escalation_state === 'acknowledged'">{{ t('alarm.upgradeAlarm') }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div class="flex justify-end mt-4 pagination-wrapper">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            prev-text="t('pagination.prev')"
            next-text="t('pagination.next')"
            size="small"
            @current-change="fetchAlarms"
            @size-change="() => { page = 1; fetchAlarms() }"
          />
        </div>
      </TableCard>

      <el-card class="mt-4">
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-semibold">{{ t('alarm.alarmRecordLinkConfig') }}</span>
          </div>
        </template>
        <div class="flex items-center gap-4">
          <span class="text-sm">{{ t('alarm.alarmRecordLinkage') }}</span>
          <el-switch v-model="alarmRecordLinkEnabled" :loading="alarmConfigLoading" @change="saveAlarmConfig" />
          <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('alarm.alarmRecordLinkageEnabled') }}</span>
        </div>
      </el-card>

    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown, VideoCamera, Refresh, Bell, TrendCharts, Warning, CircleCheck, Timer, Search, InfoFilled,
  AlarmClock, Document, Clock, Monitor, Connection, WarningFilled, ChatDotRound, Odometer, Tools, VideoPlay
} from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import QueryFormSection from '../components/QueryFormSection.vue'

const router = useRouter()
const { t } = useI18n()  // FIXED: 国际化
type AlarmRow = {
  id?: string | number
  device_id?: string
  channel_id?: string
  time?: string
  escalation_state?: string
  escalation_level?: number
}

const alarms = ref<AlarmRow[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const filters = ref({
  escalation_state: '',
  min_escalation_level: 0
})
const overview = ref({
  total_open: 0,
  escalated_open: 0,
  overdue_open: 0,
  acknowledged_today: 0,
  avg_ack_minutes_today: 0
})

const unreadCount = ref(0)

const fetchUnreadCount = async () => {
  try {
    const res = await api.get('/api/v1/alarms/unread-count')
    unreadCount.value = res.data?.unread_count ?? 0
  } catch {
    console.warn(t('alarm.loadUnreadFailed'))
    unreadCount.value = 0
  }
}

const getAlarmRowClass = (row: AlarmRow) => {
  if (row.escalation_state === 'acknowledged') return 'acknowledged-row'
  if (Number(row.escalation_level || 0) >= 5) return 'high-priority-row'
  return ''
}

const getAlarmTypeColor = (type: string) => {
  const typeMap: Record<string, unknown> = {
    'motion': 'danger',
    'intrusion': 'danger',
    'face': 'warning',
    'vehicle': 'info',
    'fire': 'danger',
    'smoke': 'warning'
  }
  return typeMap[type] || 'info'
}

const fetchOverview = async () => {
  try {
    const res = await api.get('/api/v1/alarms/sla/overview')
    const data = res.data
    overview.value = data && typeof data === 'object'
      ? { total_open: 0, escalated_open: 0, overdue_open: 0, acknowledged_today: 0, avg_ack_minutes_today: 0, ...data }
      : { total_open: 0, escalated_open: 0, overdue_open: 0, acknowledged_today: 0, avg_ack_minutes_today: 0 }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const fetchAlarms = async () => {
  loading.value = true
  try {
    const params: Record<string, string | number> = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (filters.value.escalation_state) {
      params.escalation_state = filters.value.escalation_state
    }
    if (filters.value.min_escalation_level > 0) {
      params.min_escalation_level = filters.value.min_escalation_level
    }
    const res = await api.get('/api/v1/alarms', { params })
    alarms.value = Array.isArray(res.data?.items) ? res.data.items : []
    total.value = Number(res.data?.total || 0)
  } catch (e: unknown) {
    alarms.value = []
    total.value = 0
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const goPlayback = (row: AlarmRow, windowMinutes: number = 30) => {
  const deviceId = String(row.device_id || '').trim()
  const channelId = String(row.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('alarm.missingDeviceChannel'))
    return
  }
  const time = row.time || ''
  router.push({ path: '/devices', query: { device_id: deviceId, channel_id: channelId, time, tab: 'timeline', window_minutes: String(windowMinutes) } })
}

const goTvWall = (row: AlarmRow) => {
  const deviceId = String(row.device_id || '').trim()
  const channelId = String(row.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('alarm.missingDeviceChannelTvWall'))
    return
  }
  if (!router.hasRoute('TvWall')) {
    ElMessage.warning(t('alarm.tvWallPluginRequired'))
    router.push('/plugins')
    return
  }
  router.push({ path: '/tv-wall', query: { device_id: deviceId, channel_id: channelId } })
}

const goVisualCommand = (row: AlarmRow) => {
  const deviceId = String(row.device_id || '').trim()
  const channelId = String(row.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('alarm.missingDeviceChannelCommand'))
    return
  }
  if (!router.hasRoute('VisualCommand')) {
    ElMessage.warning(t('alarm.commandPluginRequired'))
    router.push('/plugins')
    return
  }
  router.push({ path: '/visual-command', query: { device_id: deviceId, channel_id: channelId } })
}

const ack = async (row: AlarmRow) => {
  let note = ''
  try {
    const { value } = await ElMessageBox.prompt(t('alarm.confirmRemark'), t('alarm.confirmAlarm'), {
      confirmButtonText: 'Confirm',
      cancelButtonText: 'Cancel',
      inputPlaceholder: 'Remark' // FIXED: 硬编码中文→英文
    })
    note = value ?? ''
  } catch {
    return
  }
  if ((row as Record<string, unknown>)._acking) return
  ;(row as Record<string, unknown>)._acking = true
  try {
    await api.post(`/api/v1/alarms/${row.id}/ack`, { note })
    ElMessage.success(t('alarm.confirmedSuccess'))
    await Promise.all([fetchAlarms(), fetchOverview(), fetchUnreadCount()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    ;(row as Record<string, unknown>)._acking = false
  }
}

const escalate = async (row: AlarmRow) => {
  let note = ''
  try {
    const { value } = await ElMessageBox.prompt(t('alarm.upgradeRemark'), t('alarm.upgradeAlarm'), {
      confirmButtonText: 'Escalate',
      cancelButtonText: 'Cancel',
      inputPlaceholder: 'Remark' // FIXED: 硬编码中文→英文
    })
    note = value ?? ''
  } catch {
    return
  }
  if ((row as Record<string, unknown>)._escalating) return
  ;(row as Record<string, unknown>)._escalating = true
  try {
    await api.post(`/api/v1/alarms/${row.id}/escalate`, { note })
    ElMessage.success(t('alarm.upgradedSuccess'))
    await Promise.all([fetchAlarms(), fetchOverview(), fetchUnreadCount()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    ;(row as Record<string, unknown>)._escalating = false
  }
}

const handleAlarmMoreCommand = async (row: AlarmRow, cmd: string) => {
  try {
    if (cmd === 'command') {
      goVisualCommand(row)
      return
    }
    if (cmd === 'ack') {
      await ack(row)
      return
    }
    if (cmd === 'escalate') {
      await escalate(row)
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const formatTime = (iso: string | null) => {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })  // FIXED-P3: 移除硬编码zh-CN，使用浏览器默认语言
  } catch {
    return '—'
  }
}

const alarmRecordLinkEnabled = ref(false)
const alarmConfigLoading = ref(false)

const loadAlarmConfig = async () => {
  try {
    const res = await api.get('/api/v1/alarms/config')
    alarmRecordLinkEnabled.value = Boolean(res.data?.alarm_record_link_enabled)
  } catch { console.warn(t('alarm.loadConfigFailed')) }
}

const saveAlarmConfig = async () => {
  alarmConfigLoading.value = true
  try {
    await api.put('/api/v1/alarms/config', { alarm_record_link_enabled: alarmRecordLinkEnabled.value })
    ElMessage.success(alarmRecordLinkEnabled.value ? t('alarm.recordLinkageOn') : t('alarm.recordLinkageOff'))
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
    await loadAlarmConfig()
  } finally {
    alarmConfigLoading.value = false
  }
}

onMounted(async () => {
  try {
    await Promise.all([fetchOverview(), fetchAlarms(), loadAlarmConfig(), fetchUnreadCount()])
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
})
</script>

<style scoped>
.action-btn {
  transition: all var(--transition-time-02);
  border-radius: 3px;
}
.action-btn:hover {
  background: var(--el-fill-color-extra-light);
  color: var(--el-text-color-primary);
  border-color: var(--el-border-color);
}

.refresh-btn {
  transition: all var(--transition-time-02);
}
.refresh-btn:hover {
  transform: none;
  box-shadow: none;
}

.stat-card {
  --accent: var(--el-color-primary);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  box-shadow: none;
  transition: all var(--transition-time-02);
}
.stat-card:hover {
  border-color: var(--el-color-primary-light-7);
  box-shadow: var(--el-box-shadow-lighter);
}

.stat-card--open { --accent: var(--el-color-warning); }
.stat-card--escalated { --accent: var(--el-color-danger); }
.stat-card--overdue { --accent: var(--el-color-danger); }
.stat-card--ack { --accent: var(--el-color-success); }
.stat-card--avg { --accent: var(--el-color-primary); }

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
}

.stat-icon-wrapper {
  width: 34px;
  height: 34px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--accent) 10%, white);
}

.stat-icon {
  font-size: 15px;
  color: var(--accent);
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 2px;
  font-weight: 500;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}

.filter-select {
  width: 150px;
}

.filter-number {
  width: 130px;
}

.alarms-card {
  border-radius: 4px;
  box-shadow: none;
}

.alarms-table {
  border-radius: 4px;
  overflow: hidden;
}
.alarms-table :deep(.el-table__body tr) {
  transition: all var(--transition-time-02);
}
.alarms-table :deep(.el-table__body tr:hover) {
  background: var(--el-fill-color-extra-light);
  transform: none;
}
.alarms-table :deep(.el-table__row.high-priority-row) {
  background: var(--el-color-danger-light-9);
}
.alarms-table :deep(.el-table__row.acknowledged-row) {
  opacity: 0.7;
}

.time-cell,
.id-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.type-tag {
  font-weight: 500;
}

.priority-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}
.priority-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 24px;
  padding: 0 6px;
  border-radius: 3px;
  font-weight: 700;
  font-size: 12px;
}
.priority-0, .priority-1, .priority-2 {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.priority-3, .priority-4 {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.priority-5, .priority-6, .priority-7 {
  background: var(--el-color-warning-light-8);
  color: var(--el-color-warning-dark-2);
}
.priority-8, .priority-9, .priority-10 {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.status-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  animation: none;
}
.status-dot.open {
  background: var(--el-color-warning);
}
.status-dot.acknowledged {
  background: var(--el-color-success);
}

.escalation-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.action-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
}

.playback-btn {
  border-color: var(--el-border-color);
}
.playback-btn:hover {
  box-shadow: none;
}

.tv-wall-btn {
  border-color: var(--el-color-primary-light-6);
  color: var(--el-color-primary);
}
.tv-wall-btn:hover {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-6);
  color: var(--el-color-primary);
}

.empty-action-btn {
  border-color: var(--el-border-color);
}
.empty-action-btn:hover {
  box-shadow: none;
}

.pagination-wrapper {
  padding: 10px 14px;
  background: var(--el-bg-color);
  border-radius: 3px;
  margin-top: 12px;
}
</style>
