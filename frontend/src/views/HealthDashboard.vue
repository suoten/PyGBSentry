<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('health.title')" :description="t('health.description')">
          <template #actions>
            <el-button size="small" @click="refreshAll" :loading="loading">
              <el-icon class="mr-1"><Refresh /></el-icon>
              {{ t('common.refresh') }}
            </el-button>
          </template>
        </PageHeader>
      </template>

      <!-- System Health Gauges -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <el-card shadow="hover" class="health-gauge-card">
          <div class="health-gauge-title">{{ t('ops.cpuUsage') }}</div>
          <VChart class="health-gauge" :option="cpuGaugeOption" autoresize style="height: 160px" />
        </el-card>
        <el-card shadow="hover" class="health-gauge-card">
          <div class="health-gauge-title">{{ t('ops.memoryUsage') }}</div>
          <VChart class="health-gauge" :option="memoryGaugeOption" autoresize style="height: 160px" />
        </el-card>
        <el-card shadow="hover" class="health-gauge-card">
          <div class="health-gauge-title">Disk</div>
          <VChart class="health-gauge" :option="diskGaugeOption" autoresize style="height: 160px" />
        </el-card>
        <el-card shadow="hover" class="health-gauge-card">
          <div class="health-gauge-title">{{ t('health.onlineRate') }}</div>
          <VChart class="health-gauge" :option="onlineGaugeOption" autoresize style="height: 160px" />
        </el-card>
      </div>

      <!-- Service Status & Device Overview -->
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
        <!-- Service Status -->
        <el-card shadow="never">
          <template #header>
            <span class="font-semibold">{{ t('health.serviceStatus') }}</span>
          </template>
          <div class="space-y-3" v-loading="loading">
            <div class="health-row">
              <span class="health-row-label">ZLM</span>
              <el-tag :type="ops.zlm_status === 'Online' ? 'success' : 'danger'" effect="dark">
                {{ ops.zlm_status === 'Online' ? t('network.online') : t('network.offline') }}
              </el-tag>
              <span class="health-row-detail" v-if="ops.zlm_target">{{ ops.zlm_target }}</span>
              <span class="health-row-error" v-if="ops.zlm_error">{{ ops.zlm_error }}</span>
            </div>
            <div class="health-row">
              <span class="health-row-label">{{ t('health.uptime') }}</span>
              <span class="health-row-value">{{ formatUptime(ops.uptime_seconds) }}</span>
            </div>
            <div class="health-row">
              <span class="health-row-label">{{ t('health.processMemory') }}</span>
              <span class="health-row-value">{{ ops.process_memory_mb }} MB</span>
            </div>
            <div class="health-row">
              <span class="health-row-label">{{ t('health.processThreads') }}</span>
              <span class="health-row-value">{{ ops.process_threads }}</span>
            </div>
            <div class="health-row">
              <span class="health-row-label">{{ t('health.pythonVersion') }}</span>
              <span class="health-row-value">{{ ops.python_version }}</span>
            </div>
            <div class="health-row">
              <span class="health-row-label">{{ t('health.platform') }}</span>
              <span class="health-row-value text-sm">{{ ops.platform }}</span>
            </div>
          </div>
        </el-card>

        <!-- Device Overview -->
        <el-card shadow="never">
          <template #header>
            <span class="font-semibold">{{ t('health.deviceOverview') }}</span>
          </template>
          <div class="grid grid-cols-2 gap-4" v-loading="loading">
            <div class="health-stat-box">
              <div class="health-stat-label">{{ t('network.deviceTotal') }}</div>
              <div class="health-stat-value">{{ overview.device_total }}</div>
            </div>
            <div class="health-stat-box">
              <div class="health-stat-label">{{ t('network.online') }}</div>
              <div class="health-stat-value" style="color: var(--el-color-success)">{{ overview.device_online }}</div>
            </div>
            <div class="health-stat-box">
              <div class="health-stat-label">{{ t('network.channelTotal') }}</div>
              <div class="health-stat-value">{{ overview.channel_total }}</div>
            </div>
            <div class="health-stat-box">
              <div class="health-stat-label">{{ t('network.online') }} ({{ t('network.channelTotal') }})</div>
              <div class="health-stat-value" style="color: var(--el-color-success)">{{ overview.channel_online }}</div>
            </div>
          </div>
          <el-divider />
          <div class="grid grid-cols-2 gap-4">
            <div class="health-stat-box">
              <div class="health-stat-label">{{ t('health.onlineRate') }}</div>
              <div class="health-stat-value">
                {{ overview.device_online_rate_pct?.toFixed(1) || '0.0' }}%
              </div>
            </div>
            <div class="health-stat-box">
              <div class="health-stat-label">{{ t('health.channelOnlineRate') }}</div>
              <div class="health-stat-value">
                {{ overview.channel_total ? ((overview.channel_online / overview.channel_total) * 100).toFixed(1) : '0.0' }}%
              </div>
            </div>
          </div>
        </el-card>
      </div>

      <!-- Overall Health Summary -->
      <el-card shadow="never">
        <template #header>
          <span class="font-semibold">{{ t('health.systemHealth') }}</span>
        </template>
        <div class="flex items-center gap-4">
          <el-tag :type="overallHealthTag" effect="dark" size="large">
            {{ overallHealthLabel }}
          </el-tag>
          <el-progress
            :percentage="overallScore"
            :color="overallHealthColor"
            :stroke-width="20"
            :text-inside="true"
            style="flex: 1"
          />
        </div>
        <div class="mt-3 text-sm text-gray-500">
          {{ t('health.systemHealth') }}: CPU {{ ops.cpu }}% | {{ t('ops.memoryUsage') }} {{ ops.memory_percent }}% | Disk {{ ops.disk_percent }}% | ZLM {{ ops.zlm_status }}
        </div>
      </el-card>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import api from '@/utils/http'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GaugeChart } from 'echarts/charts'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import { getFriendlyError } from '../utils/errorMessage'

use([CanvasRenderer, GaugeChart])

const { t } = useI18n()

const loading = ref(false)

interface OpsStatus {
  cpu: number
  memory_percent: number
  disk_percent: number
  zlm_status: string
  zlm_streams: number
  zlm_target: string
  zlm_error: string
  uptime_seconds: number
  process_memory_mb: number
  process_threads: number
  platform: string
  python_version: string
}

interface DeviceOverview {
  device_total: number
  device_online: number
  channel_total: number
  channel_online: number
  device_online_rate_pct: number
}

const ops = ref<OpsStatus>({
  cpu: 0, memory_percent: 0, disk_percent: 0,
  zlm_status: 'Offline', zlm_streams: 0, zlm_target: '', zlm_error: '',
  uptime_seconds: 0, process_memory_mb: 0, process_threads: 0,
  platform: '', python_version: ''
})

const overview = ref<DeviceOverview>({
  device_total: 0, device_online: 0, channel_total: 0,
  channel_online: 0, device_online_rate_pct: 0
})

const fetchOps = async () => {
  try {
    const res = await api.get('/api/v1/ops/status')
    ops.value = { ...ops.value, ...res.data }
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const fetchOverview = async () => {
  try {
    const res = await api.get('/api/v1/metrics/devices-overview')
    overview.value = { ...overview.value, ...res.data }
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const refreshAll = async () => {
  loading.value = true
  await Promise.allSettled([fetchOps(), fetchOverview()])
  loading.value = false
}

// --- Gauge Options ---
const makeGauge = (value: number, name: string, thresholds: [number, number]) => {
  const [warn, crit] = thresholds
  return {
    series: [{
      type: 'gauge',
      startAngle: 200,
      endAngle: -20,
      min: 0, max: 100,
      progress: { show: true, width: 14 },
      axisLine: { lineStyle: { width: 14, color: [[warn / 100, '#67c23a'], [crit / 100, '#e6a23c'], [1, '#f56c6c']] } },
      axisTick: { show: false },
      splitLine: { length: 8, lineStyle: { width: 1, color: '#999' } },
      axisLabel: { show: false },
      pointer: { width: 4 },
      detail: { valueAnimation: true, formatter: '{value}%', fontSize: 18, offsetCenter: [0, '60%'] },
      data: [{ value: Math.round(value), name }]
    }]
  }
}

const cpuGaugeOption = computed(() => makeGauge(ops.value.cpu, 'CPU', [60, 80]))
const memoryGaugeOption = computed(() => makeGauge(ops.value.memory_percent, 'MEM', [70, 85]))
const diskGaugeOption = computed(() => makeGauge(ops.value.disk_percent, 'DISK', [70, 90]))
const onlineGaugeOption = computed(() => makeGauge(overview.value.device_online_rate_pct || 0, 'ONLINE', [50, 80]))

// --- Overall Health ---
const overallScore = computed(() => {
  const cpuOk = ops.value.cpu < 80 ? 100 - ops.value.cpu : 0
  const memOk = ops.value.memory_percent < 85 ? 100 - ops.value.memory_percent : 0
  const diskOk = ops.value.disk_percent < 90 ? 100 - ops.value.disk_percent : 0
  const zlmOk = ops.value.zlm_status === 'Online' ? 100 : 0
  const devOk = overview.value.device_total > 0 ? overview.value.device_online_rate_pct : 100
  return Math.round(cpuOk * 0.25 + memOk * 0.2 + diskOk * 0.15 + zlmOk * 0.25 + devOk * 0.15)
})

const overallHealthTag = computed(() => {
  const s = overallScore.value
  if (s >= 80) return 'success'
  if (s >= 50) return 'warning'
  return 'danger'
})

const overallHealthLabel = computed(() => {
  const s = overallScore.value
  if (s >= 80) return t('health.healthy')
  if (s >= 50) return t('health.warning')
  return t('health.critical')
})

const overallHealthColor = computed(() => {
  const s = overallScore.value
  if (s >= 80) return '#67c23a'
  if (s >= 50) return '#e6a23c'
  return '#f56c6c'
})

// --- Helpers ---
const formatUptime = (seconds: number) => {
  if (!seconds) return '-'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

// --- Lifecycle ---
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refreshAll()
  pollTimer = setInterval(refreshAll, 15000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.health-gauge-card {
  text-align: center;
}
.health-gauge-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.health-gauge {
  width: 100%;
}
.health-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.health-row-label {
  font-weight: 500;
  min-width: 100px;
  color: var(--el-text-color-secondary);
}
.health-row-value {
  color: var(--el-text-color-primary);
}
.health-row-detail {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.health-row-error {
  font-size: 12px;
  color: var(--el-color-danger);
}
.health-stat-box {
  text-align: center;
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}
.health-stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.health-stat-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}
</style>
