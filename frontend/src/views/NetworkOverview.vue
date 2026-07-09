<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('network.title')" :description="t('network.description')">
          <template #actions>
            <el-button size="small" @click="refreshAll" :loading="loading">
              <el-icon class="mr-1"><Refresh /></el-icon>
              {{ t('common.refresh') }}
            </el-button>
            <el-radio-group v-model="bandwidthRange" size="small" @change="fetchBandwidth">
              <el-radio-button value="1h">1h</el-radio-button>
              <el-radio-button value="6h">6h</el-radio-button>
              <el-radio-button value="24h">24h</el-radio-button>
            </el-radio-group>
          </template>
        </PageHeader>
      </template>

      <!-- KPI Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <el-card shadow="hover" class="net-kpi-card">
          <div class="net-kpi-label">{{ t('network.deviceTotal') }}</div>
          <div class="net-kpi-value">{{ summary.device_total }}</div>
          <div class="net-kpi-sub">
            <el-tag size="small" type="success">{{ t('network.online') }}: {{ summary.device_online }}</el-tag>
            <el-tag size="small" type="danger" class="ml-1">{{ t('network.offline') }}: {{ summary.device_offline }}</el-tag>
          </div>
        </el-card>
        <el-card shadow="hover" class="net-kpi-card">
          <div class="net-kpi-label">{{ t('network.channelTotal') }}</div>
          <div class="net-kpi-value">{{ summary.channel_total }}</div>
          <div class="net-kpi-sub">
            <el-tag size="small" type="success">{{ t('network.online') }}: {{ summary.channel_online }}</el-tag>
          </div>
        </el-card>
        <el-card shadow="hover" class="net-kpi-card">
          <div class="net-kpi-label">{{ t('network.activeStreams') }}</div>
          <div class="net-kpi-value" style="color: var(--el-color-warning)">{{ summary.stream_count }}</div>
          <div class="net-kpi-sub">{{ t('network.realtimeStreams') }}</div>
        </el-card>
        <el-card shadow="hover" class="net-kpi-card">
          <div class="net-kpi-label">{{ t('network.currentBandwidth') }}</div>
          <div class="net-kpi-value">{{ bandwidth.current_bandwidth_mbps?.toFixed(2) || '0.00' }} Mbps</div>
          <div class="net-kpi-sub">
            <span>{{ t('network.peak') }}: {{ bandwidth.peak_bandwidth_mbps?.toFixed(2) || '0.00' }} Mbps</span>
            <span class="ml-2">{{ t('network.avg') }}: {{ bandwidth.avg_bandwidth_mbps?.toFixed(2) || '0.00' }} Mbps</span>
          </div>
        </el-card>
      </div>

      <!-- Bandwidth Chart -->
      <el-card shadow="never" class="mb-4">
        <template #header>
          <span class="font-semibold">{{ t('network.bandwidthTrend') }}</span>
        </template>
        <VChart class="net-chart" :option="bandwidthChartOption" autoresize style="height: 300px" />
      </el-card>

      <!-- Device Online Rate & Topology -->
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <!-- Device Online Rate Gauge -->
        <el-card shadow="never">
          <template #header>
            <span class="font-semibold">{{ t('network.deviceOnlineRate') }}</span>
          </template>
          <VChart class="net-chart" :option="onlineRateOption" autoresize style="height: 280px" />
        </el-card>

        <!-- Topology Table -->
        <el-card shadow="never">
          <template #header>
            <span class="font-semibold">{{ t('network.topology') }}</span>
          </template>
          <el-table :data="topologyNodes" v-loading="loading" stripe size="small" style="max-height: 280px; overflow-y: auto">
            <el-table-column prop="label" :label="t('network.nodeLabel')" min-width="180" />
            <el-table-column prop="type" :label="t('network.nodeType')" width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="topologyTagType(row.type)">{{ topologyTypeLabel(row.type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" :label="t('network.nodeStatus')" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'online' ? 'success' : 'danger'">
                  {{ row.status === 'online' ? t('network.online') : t('network.offline') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="topologyNodes.some(n => n.ip_addr)" prop="ip_addr" :label="t('network.ipAddress')" width="140" />
          </el-table>
        </el-card>
      </div>

      <!-- Topology Graph (visual) -->
      <el-card shadow="never" class="mt-4">
        <template #header>
          <span class="font-semibold">{{ t('network.topologyGraph') }}</span>
        </template>
        <div class="topology-graph-container" v-loading="loading">
          <div v-if="topologyNodes.length === 0" class="text-center text-gray-400 py-8">
            {{ t('network.noData') }}
          </div>
          <div v-else class="topology-graph">
            <!-- Platform center node -->
            <div v-for="node in topologyNodes.slice(0, 50)" :key="node.id"
                 class="topology-node"
                 :class="`topo-${node.type}`">
              <el-icon v-if="node.type === 'platform'" class="topo-icon"><Platform /></el-icon>
              <el-icon v-else-if="node.type === 'device'" class="topo-icon"><VideoCamera /></el-icon>
              <el-icon v-else-if="node.type === 'media_server'" class="topo-icon"><Monitor /></el-icon>
              <el-icon v-else class="topo-icon"><Connection /></el-icon>
              <span class="topo-label">{{ node.label }}</span>
              <el-tag size="small" :type="node.status === 'online' ? 'success' : 'danger'" class="topo-status">
                {{ node.status === 'online' ? '●' : '○' }}
              </el-tag>
            </div>
          </div>
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
import { Refresh, Platform, VideoCamera, Monitor, Connection } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, GaugeChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import { getFriendlyError } from '../utils/errorMessage'

use([CanvasRenderer, LineChart, GaugeChart, GridComponent, TooltipComponent, LegendComponent])

const { t } = useI18n()

// --- State ---
const loading = ref(false)
const bandwidthRange = ref('1h')

interface SummaryData {
  device_total: number
  device_online: number
  device_offline: number
  channel_total: number
  channel_online: number
  stream_count: number
  timestamp: string
}

interface BandwidthData {
  range: string
  active_streams: number
  current_bandwidth_mbps: number
  peak_bandwidth_mbps: number
  avg_bandwidth_mbps: number
  series: Array<{ timestamp: number; value: number }>
}

interface TopologyNode {
  id: string
  label: string
  type: string
  status: string
  ip_addr?: string
}

const summary = ref<SummaryData>({
  device_total: 0, device_online: 0, device_offline: 0,
  channel_total: 0, channel_online: 0, stream_count: 0, timestamp: ''
})
const bandwidth = ref<BandwidthData>({
  range: '1h', active_streams: 0, current_bandwidth_mbps: 0,
  peak_bandwidth_mbps: 0, avg_bandwidth_mbps: 0, series: []
})
const topologyNodes = ref<TopologyNode[]>([])

// --- Fetch ---
const fetchSummary = async () => {
  try {
    const res = await api.get('/api/v1/network/summary')
    summary.value = res.data || summary.value
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const fetchBandwidth = async () => {
  try {
    const res = await api.get('/api/v1/network/bandwidth', { params: { range: bandwidthRange.value } })
    bandwidth.value = res.data || bandwidth.value
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const fetchTopology = async () => {
  try {
    const res = await api.get('/api/v1/network/topology')
    topologyNodes.value = (res.data?.nodes || []) as TopologyNode[]
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const refreshAll = async () => {
  loading.value = true
  await Promise.allSettled([fetchSummary(), fetchBandwidth(), fetchTopology()])
  loading.value = false
}

// --- Charts ---
const bandwidthChartOption = computed(() => {
  const series = bandwidth.value.series || []
  const xData = series.map(p => {
    const d = new Date(p.timestamp * 1000)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  })
  const yData = series.map(p => p.value)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: [t('network.bandwidthMbps')] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: xData, boundaryGap: false },
    yAxis: { type: 'value', name: 'Mbps' },
    series: [{
      name: t('network.bandwidthMbps'),
      type: 'line',
      data: yData,
      smooth: true,
      areaStyle: { opacity: 0.3 },
      lineStyle: { width: 2 },
      itemStyle: { color: '#409eff' }
    }]
  }
})

const onlineRateOption = computed(() => {
  const total = summary.value.device_total || 0
  const online = summary.value.device_online || 0
  const rate = total > 0 ? Math.round((online / total) * 100) : 0
  return {
    series: [{
      type: 'gauge',
      startAngle: 200,
      endAngle: -20,
      min: 0, max: 100,
      progress: { show: true, width: 18 },
      axisLine: { lineStyle: { width: 18 } },
      axisTick: { show: false },
      splitLine: { length: 10, lineStyle: { width: 2, color: '#999' } },
      axisLabel: { distance: 25, color: '#999', fontSize: 10 },
      pointer: { width: 5 },
      detail: {
        valueAnimation: true,
        formatter: `{value}%\n(${online}/${total})`,
        color: 'auto',
        fontSize: 20,
        offsetCenter: [0, '70%']
      },
      data: [{ value: rate, name: t('network.onlineRate') }]
    }]
  }
})

// --- Helpers ---
const topologyTagType = (type: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  if (type === 'platform') return 'primary'
  if (type === 'media_server') return 'warning'
  if (type === 'tenant') return 'info'
  return 'success'
}

const topologyTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    platform: t('network.platform'),
    device: t('network.device'),
    media_server: t('network.mediaServer'),
    tenant: t('network.tenant')
  }
  return map[type] || type
}

// --- Lifecycle ---
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refreshAll()
  pollTimer = setInterval(refreshAll, 30000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.net-kpi-card {
  text-align: center;
  padding: 8px 0;
}
.net-kpi-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.net-kpi-value {
  font-size: 28px;
  font-weight: bold;
  color: var(--el-text-color-primary);
  line-height: 1.4;
}
.net-kpi-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
.net-chart {
  width: 100%;
}
.topology-graph-container {
  min-height: 200px;
}
.topology-graph {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.topology-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  min-width: 100px;
  position: relative;
  transition: box-shadow 0.2s;
}
.topology-node:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
.topo-platform {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.topo-media_server {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.topo-icon {
  font-size: 24px;
  margin-bottom: 4px;
  color: var(--el-color-primary);
}
.topo-media_server .topo-icon {
  color: var(--el-color-warning);
}
.topo-label {
  font-size: 12px;
  text-align: center;
  word-break: break-all;
  max-width: 120px;
}
.topo-status {
  position: absolute;
  top: 4px;
  right: 4px;
}
</style>
