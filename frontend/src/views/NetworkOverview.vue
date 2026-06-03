<template>
  <div class="app-page h-full overflow-auto thin-scrollbar space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="网络概况" description="设备在线与流量会话概览" />
      </template>

      <!-- 统计卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4" v-loading="loading">
        <div class="net-stat-card" style="--stat-accent: #6366f1">
          <div class="net-stat-icon">📹</div>
          <div class="net-stat-body">
            <div class="net-stat-value">{{ summary.device_total }}</div>
            <div class="net-stat-label">设备总数</div>
          </div>
        </div>
        <div class="net-stat-card" style="--stat-accent: #10b981">
          <div class="net-stat-icon">🟢</div>
          <div class="net-stat-body">
            <div class="net-stat-value" style="color: #10b981">{{ summary.device_online }}</div>
            <div class="net-stat-label">在线设备</div>
            <div class="net-stat-sub" v-if="summary.device_total > 0">
              在线率 {{ deviceOnlineRate }}%
            </div>
          </div>
        </div>
        <div class="net-stat-card" style="--stat-accent: #3b82f6">
          <div class="net-stat-icon">📡</div>
          <div class="net-stat-body">
            <div class="net-stat-value" style="color: #3b82f6">{{ summary.stream_count }}</div>
            <div class="net-stat-label">实时流数</div>
          </div>
        </div>
        <div class="net-stat-card" style="--stat-accent: #f59e0b">
          <div class="net-stat-icon">📊</div>
          <div class="net-stat-body">
            <div class="net-stat-value" style="color: #f59e0b">{{ summary.zlm_bandwidth_mbps }}</div>
            <div class="net-stat-label">带宽 (Mbps)</div>
          </div>
        </div>
      </div>

      <!-- 设备在线率进度条 -->
      <div v-if="summary.device_total > 0" class="mt-4 p-4 rounded-lg" style="background: var(--el-fill-color-light)">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">设备在线状态</span>
          <span class="text-xs" style="color:var(--el-text-color-secondary)">{{ summary.device_online }} / {{ summary.device_total }} 在线</span>
        </div>
        <el-progress
          :percentage="parseFloat(deviceOnlineRate)"
          :stroke-width="12"
          :color="parseFloat(deviceOnlineRate) >= 80 ? '#10b981' : parseFloat(deviceOnlineRate) >= 50 ? '#f59e0b' : '#ef4444'"
          :format="(p: number) => `${p}%`"
        />
      </div>

      <!-- 趋势图 -->
      <TableCard class="mt-4">
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-medium">流量趋势</span>
            <div class="flex items-center gap-3">
              <div class="flex items-center gap-1 text-xs" style="color:var(--el-text-color-secondary)">
                <span class="inline-block w-3 h-0.5 rounded" style="background:#38bdf8"></span> 流数
                <span class="inline-block w-3 h-0.5 rounded ml-2" style="background:#f59e0b"></span> 带宽
              </div>
              <el-radio-group v-model="range" size="small" @change="loadBandwidth">
                <el-radio-button value="1h">1 小时</el-radio-button>
                <el-radio-button value="24h">24 小时</el-radio-button>
              </el-radio-group>
            </div>
          </div>
        </template>
        <div class="h-48 mt-2 relative">
          <svg v-if="bandwidthPoints.length > 1" :width="'100%'" :height="'100%'" preserveAspectRatio="none">
            <defs>
              <linearGradient id="streamGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.3" />
                <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.02" />
              </linearGradient>
              <linearGradient id="bwGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.2" />
                <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <polygon v-if="svgAreaPoints" :points="svgAreaPoints" fill="url(#streamGrad)" />
            <polyline :points="svgPoints" fill="none" stroke="#38bdf8" stroke-width="2" />
            <polygon v-if="svgBandwidthAreaPoints" :points="svgBandwidthAreaPoints" fill="url(#bwGrad)" />
            <polyline v-if="svgBandwidthPoints" :points="svgBandwidthPoints" fill="none" stroke="#f59e0b" stroke-width="2" />
          </svg>
          <div v-else class="h-full flex flex-col items-center justify-center" style="color: var(--el-text-color-secondary)">
            <div class="text-3xl mb-2">📈</div>
            <div class="text-sm">暂无趋势数据</div>
            <div class="text-xs mt-1">数据将在设备推流后自动生成</div>
          </div>
        </div>
      </TableCard>

      <!-- 拓扑视图 -->
      <TableCard class="mt-4">
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-medium">网络拓扑</span>
            <div v-if="topology.nodes.length" class="flex items-center gap-2 text-xs" style="color:var(--el-text-color-secondary)">
              <span class="inline-block w-2 h-2 rounded-full" style="background:#22c55e"></span> 在线
              <span class="inline-block w-2 h-2 rounded-full" style="background:#9ca3af"></span> 离线
            </div>
          </div>
        </template>
        <div v-if="topology.nodes.length" class="space-y-3">
          <div class="w-full h-72 rounded-lg overflow-hidden" style="background: var(--el-fill-color-light)">
            <svg width="100%" height="100%" viewBox="0 0 1000 420" preserveAspectRatio="xMidYMid meet">
              <line
                v-for="(edge, idx) in topology.edges"
                :key="`e-${idx}`"
                :x1="findNode(edge.source)?.x || 500"
                :y1="findNode(edge.source)?.y || 210"
                :x2="findNode(edge.target)?.x || 500"
                :y2="findNode(edge.target)?.y || 210"
                :stroke="isEdgeOnline(edge) ? '#22c55e' : '#9ca3af'"
                :stroke-width="isEdgeOnline(edge) ? 2 : 1.5"
                :stroke-dasharray="isEdgeOnline(edge) ? '' : '6,4'"
              />
              <g v-for="node in topoRenderNodes" :key="node.id">
                <circle :cx="node.x" :cy="node.y" :r="node.id === 'platform' ? 20 : 14" :fill="node.status === 'offline' ? '#9ca3af' : '#22c55e'" />
                <text v-if="node.id === 'platform'" :x="node.x" :y="node.y + 5" fill="white" font-size="14" text-anchor="middle" font-weight="bold">P</text>
                <text :x="node.x" :y="node.y + (node.id === 'platform' ? 34 : 28)" fill="#64748b" font-size="12" text-anchor="middle">{{ node.label }}</text>
              </g>
            </svg>
          </div>
          <div class="flex flex-wrap gap-2">
            <div v-for="n in topology.nodes" :key="n.id" class="flex items-center gap-1.5 px-2 py-1 rounded text-xs" style="background:var(--el-fill-color-light)">
              <span class="inline-block w-2 h-2 rounded-full" :style="{ background: n.status === 'offline' ? '#9ca3af' : '#22c55e' }"></span>
              <span>{{ n.label }}</span>
              <span style="color:var(--el-text-color-secondary)">{{ n.type }}</span>
            </div>
          </div>
        </div>
        <div v-else class="flex flex-col items-center justify-center py-8" style="color: var(--el-text-color-secondary)">
          <div class="text-3xl mb-2">🌐</div>
          <div class="text-sm">暂无拓扑数据</div>
          <div class="text-xs mt-1">添加设备后将自动生成网络拓扑</div>
        </div>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'

const loading = ref(true)
const { t } = useI18n()  // FIXED: 国际化
const summary = ref({
  device_total: 0,
  device_online: 0,
  stream_count: 0,
  stream_count_zlm: 0,
  zlm_bandwidth_mbps: 0,
  description: ''
})

const range = ref<'1h' | '24h'>('1h')
const bandwidthPoints = ref<Array<{ t: string; value: number }>>([])
const bandwidthMpbsPoints = ref<Array<{ t: string; value: number }>>([])
const topology = ref<{ nodes: Array<{ id: string; type: string; label: string; status?: string }>; edges: Array<{ source: string; target: string; type: string }> }>({ nodes: [], edges: [] })

const deviceOnlineRate = computed(() => {
  if (!summary.value.device_total) return '0'
  return ((summary.value.device_online / summary.value.device_total) * 100).toFixed(1)
})

const rangeLabel = computed(() => (range.value === '1h' ? '1 小时' : '24 小时'))

const svgPoints = computed(() => {
  if (bandwidthPoints.value.length <= 1) return ''
  const values = bandwidthPoints.value.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1)
  const n = bandwidthPoints.value.length
  return bandwidthPoints.value
    .map((p, idx) => {
      const x = (idx / (n - 1)) * 100
      const y = 100 - ((p.value - min) / span) * 100
      return `${x},${y}`
    })
    .join(' ')
})

const svgAreaPoints = computed(() => {
  if (bandwidthPoints.value.length <= 1) return ''
  const values = bandwidthPoints.value.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1)
  const n = bandwidthPoints.value.length
  const linePoints = bandwidthPoints.value.map((p, idx) => {
    const x = (idx / (n - 1)) * 100
    const y = 100 - ((p.value - min) / span) * 100
    return `${x},${y}`
  })
  return [...linePoints, `100,100`, `0,100`].join(' ')
})

const svgBandwidthPoints = computed(() => {
  if (bandwidthMpbsPoints.value.length <= 1) return ''
  const values = bandwidthMpbsPoints.value.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1)
  const n = bandwidthMpbsPoints.value.length
  return bandwidthMpbsPoints.value
    .map((p, idx) => {
      const x = (idx / (n - 1)) * 100
      const y = 100 - ((p.value - min) / span) * 100
      return `${x},${y}`
    })
    .join(' ')
})

const svgBandwidthAreaPoints = computed(() => {
  if (bandwidthMpbsPoints.value.length <= 1) return ''
  const values = bandwidthMpbsPoints.value.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1)
  const n = bandwidthMpbsPoints.value.length
  const linePoints = bandwidthMpbsPoints.value.map((p, idx) => {
    const x = (idx / (n - 1)) * 100
    const y = 100 - ((p.value - min) / span) * 100
    return `${x},${y}`
  })
  return [...linePoints, `100,100`, `0,100`].join(' ')
})

const topoRenderNodes = computed(() => {
  const nodes = topology.value.nodes || []
  const centerX = 500
  const centerY = 210
  const radius = 160
  const platform = nodes.find(n => n.id === 'platform')
  const rest = nodes.filter(n => n.id !== 'platform')
  const rendered: Array<{ id: string; label: string; status?: string; x: number; y: number }> = []
  if (platform) {
    rendered.push({ ...platform, x: centerX, y: centerY })
  }
  if (!rest.length) return rendered
  rest.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / rest.length
    rendered.push({
      ...node,
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius
    })
  })
  return rendered
})

function findNode(nodeId: string) {
  return topoRenderNodes.value.find(n => n.id === nodeId)
}

function isEdgeOnline(edge: { source: string; target: string }) {
  const src = findNode(edge.source)
  const tgt = findNode(edge.target)
  return src?.status !== 'offline' && tgt?.status !== 'offline'
}

const loadSummary = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/network/summary')
    summary.value = res.data ?? {}
  } catch (e) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const loadTopology = async () => {
  try {
    const res = await api.get('/api/v1/network/topology')
    topology.value = { nodes: res.data?.nodes ?? [], edges: res.data?.edges ?? [] }
  } catch (e) {
    topology.value = { nodes: [], edges: [] }
  }
}

const loadBandwidth = async () => {
  try {
    const res = await api.get('/api/v1/network/bandwidth', { params: { range: range.value } })
    const series = Array.isArray(res.data?.series) ? res.data.series : []
    const activeSeries = series.find((s: Record<string, unknown>) => s.name === 'active_streams')
    const mbpsSeries = series.find((s: Record<string, unknown>) => s.name === 'zlm_bandwidth')
    const points = Array.isArray(activeSeries?.points) ? activeSeries.points : []
    const mbps = Array.isArray(mbpsSeries?.points) ? mbpsSeries.points : []
    bandwidthPoints.value = points.map((p: Record<string, unknown>) => ({
      t: String(p.t),
      value: Number(p.value || 0)
    }))
    bandwidthMpbsPoints.value = mbps.map((p: Record<string, unknown>) => ({
      t: String(p.t),
      value: Number(p.value || 0)
    }))
  } catch (e) {
    bandwidthPoints.value = []
    bandwidthMpbsPoints.value = []
  }
}

onMounted(async () => {
  await loadSummary()
  await loadTopology()
  await loadBandwidth()
})
</script>

<style scoped>
.net-stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 8px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  transition: box-shadow 0.2s;
}
.net-stat-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.net-stat-icon {
  font-size: 28px;
  line-height: 1;
  flex-shrink: 0;
}
.net-stat-body {
  min-width: 0;
}
.net-stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--stat-accent);
}
.net-stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.net-stat-sub {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  opacity: 0.8;
}
</style>
