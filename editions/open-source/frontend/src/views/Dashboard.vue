<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="工作台" description="关键指标概览与实时告警">
          <template #actions>
            <el-button @click="openSystemInfoDialog" class="action-btn system-info-btn">
              <el-icon class="mr-1"><InfoFilled /></el-icon>
              平台信息
            </el-button>
            <el-button type="primary" @click="$router.push('/monitor')" class="action-btn monitor-btn">
              <el-icon class="mr-1"><Monitor /></el-icon>
              监控中心
            </el-button>
            <el-button @click="$router.push('/devices')" class="action-btn devices-btn">
              <el-icon class="mr-1"><Box /></el-icon>
              设备列表
            </el-button>
          </template>
        </PageHeader>
      </template>

    <el-alert
      v-if="demoEnabled"
      title="演示模式已开启"
      type="info"
      show-icon
      :closable="false"
      class="mb-6 demo-alert"
      description="当前系统开启了演示模式，将在设备列表展示内置示例设备（仅用于体验，不含真实视频流）。如需关闭，请在后端环境变量中将演示模式设为 false 并重启。"
    />

    <el-tabs v-model="activeTab" class="dashboard-tabs">
      <el-tab-pane label="工作台概览" name="overview">
    <!-- 统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <el-card class="stat-card stat-card--primary" v-loading="statsLoading" shadow="never">
        <div class="stat-icon">
          <el-icon><Monitor /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">设备总数</div>
          <div class="stat-value">{{ stats.device_total }}</div>
          <div class="stat-desc">国标设备数量</div>
        </div>
      </el-card>
      <el-card class="stat-card stat-card--success" v-loading="statsLoading" shadow="never">
        <div class="stat-icon">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">在线设备</div>
          <div class="stat-value">{{ stats.device_online }}</div>
          <div class="stat-desc">当前在线</div>
        </div>
      </el-card>
      <el-card class="stat-card stat-card--warning" v-loading="statsLoading" shadow="never">
        <div class="stat-icon">
          <el-icon><TrendCharts /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">设备在线率</div>
          <div class="stat-value" :class="onlineRateClass">{{ stats.online_rate_pct }}%</div>
          <div class="stat-desc">
            通道 {{ stats.channel_online }}/{{ stats.channel_total }} · 录像完整率 {{ stats.record_completeness_pct }}%
          </div>
        </div>
      </el-card>
      <el-card class="stat-card stat-card--danger" v-loading="statsLoading" shadow="never">
        <div class="stat-icon">
          <el-icon><Bell /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">未处理告警</div>
          <div class="stat-value">{{ alarms.length }}</div>
          <div class="stat-desc">
            <router-link v-if="alarms.length > 0" to="/alarms" class="text-link hover:underline font-medium">查看告警中心 →</router-link>
            <span v-else>暂无新告警</span>
          </div>
        </div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      <TableCard class="chart-card">
        <template #header>
          <div class="chart-title">设备在线占比</div>
        </template>
        <div class="donut-wrap">
          <div class="donut" :style="onlineDonutStyle">
            <div class="donut-center">
              <div class="donut-rate">{{ stats.online_rate_pct }}%</div>
              <div class="donut-sub">在线率</div>
            </div>
          </div>
          <div class="donut-legend">
            <div class="legend-item">
              <span class="legend-dot online"></span>
              在线 {{ stats.device_online }}
            </div>
            <div class="legend-item">
              <span class="legend-dot offline"></span>
              离线 {{ Math.max(0, stats.device_total - stats.device_online) }}
            </div>
            <div class="legend-item total">总计 {{ stats.device_total }}</div>
          </div>
        </div>
      </TableCard>

      <TableCard class="chart-card">
        <template #header>
          <div class="chart-title">告警级别分布</div>
        </template>
        <div class="bar-list">
          <div v-for="item in alarmPriorityStats" :key="item.key" class="bar-item">
            <div class="bar-meta">
              <span>{{ item.label }}</span>
              <span>{{ item.value }}</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill" :class="item.key" :style="{ width: `${item.rate}%` }"></div>
            </div>
          </div>
        </div>
      </TableCard>

      <TableCard class="chart-card">
        <template #header>
          <div class="chart-title">24小时告警趋势</div>
        </template>
        <div class="line-chart-wrap">
          <svg class="line-chart" viewBox="0 0 360 160" preserveAspectRatio="none">
            <polyline :points="alarmTrendPolyline" fill="none" stroke="var(--el-color-primary)" stroke-width="2.5" />
            <polyline :points="alarmTrendFillPolyline" fill="rgba(var(--el-color-primary-rgb),0.15)" stroke="none" />
          </svg>
          <div class="line-axis">
            <span>{{ trendStartLabel }}</span>
            <span>现在</span>
          </div>
        </div>
      </TableCard>
    </div>

    <!-- 快捷入口 -->
    <TableCard class="mb-6 quick-access-card">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-semibold quick-access-title">
            快捷入口
          </div>
          <div class="text-xs quick-access-subtitle">常用功能快速跳转</div>
        </div>
      </template>
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <router-link to="/devices" class="quick-link quick-link--devices">
          <div class="quick-link-icon">
            <el-icon><Box /></el-icon>
          </div>
          <span class="quick-link-text">设备列表</span>
          <span class="quick-link-sub">台账与状态</span>
        </router-link>
        <router-link to="/monitor" class="quick-link quick-link--monitor">
          <div class="quick-link-icon">
            <el-icon><Monitor /></el-icon>
          </div>
          <span class="quick-link-text">监控中心</span>
          <span class="quick-link-sub">实时预览</span>
        </router-link>
        <router-link to="/alarms" class="quick-link quick-link--alarms">
          <div class="quick-link-icon">
            <el-icon><Bell /></el-icon>
          </div>
          <span class="quick-link-text">告警中心</span>
          <span class="quick-link-sub">处理告警</span>
        </router-link>
        <router-link to="/platforms" class="quick-link quick-link--platforms">
          <div class="quick-link-icon">
            <el-icon><Connection /></el-icon>
          </div>
          <span class="quick-link-text">国标级联</span>
          <span class="quick-link-sub">平台接入</span>
        </router-link>
        <router-link to="/record-schedule" class="quick-link quick-link--record">
          <div class="quick-link-icon">
            <el-icon><VideoPlay /></el-icon>
          </div>
          <span class="quick-link-text">录像计划</span>
          <span class="quick-link-sub">策略编排</span>
        </router-link>
        <router-link to="/ops" class="quick-link quick-link--ops">
          <div class="quick-link-icon">
            <el-icon><Setting /></el-icon>
          </div>
          <span class="quick-link-text">运维中心</span>
          <span class="quick-link-sub">系统运维</span>
        </router-link>
        <router-link to="/health" class="quick-link quick-link--health">
          <div class="quick-link-icon">
            <el-icon><DataAnalysis /></el-icon>
          </div>
          <span class="quick-link-text">健康大屏</span>
          <span class="quick-link-sub">运行态势</span>
        </router-link>
      </div>
    </TableCard>

    <!-- 实时告警列表 -->
    <TableCard class="alarms-card">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="font-bold text-slate-700 flex items-center gap-2">
              <el-icon class="text-rose-500"><BellFilled /></el-icon>
              实时告警
            </div>
            <el-tag v-if="alarms.length > 0" type="danger" effect="dark" class="alarm-tag">
              <el-icon class="mr-1"><Warning /></el-icon>
              有新告警
            </el-tag>
          </div>
          <router-link to="/alarms">
            <el-button type="primary" size="small" class="view-alarms-btn">
              <el-icon class="mr-1"><Right /></el-icon>
              前往告警中心
            </el-button>
          </router-link>
        </div>
      </template>
      <el-table
        :data="paginatedAlarms"
        max-height="420"
        v-loading="alarmsLoading"
        :empty-text="alarmsEmptyText"
        class="alarms-table"
        :row-class-name="getAlarmRowClass"
      >
        <el-table-column prop="time" label="时间" width="180">
          <template #default="scope">
            <div class="time-cell">
              <el-icon class="text-slate-400"><Clock /></el-icon>
              {{ formatTime(scope.row.time) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="device_id" label="设备ID" width="200">
          <template #default="scope">
            <div class="device-cell">
              <el-tag size="small" type="info" effect="plain">{{ scope.row.device_id }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述">
          <template #default="scope">
            <div class="desc-cell">{{ scope.row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="级别" width="100" align="center">
          <template #default="scope">
            <el-tag :type="getPriorityType(scope.row.priority)" size="small" effect="dark" class="priority-tag">
              {{ scope.row.priority === '1' ? '紧急' : scope.row.priority === '2' ? '重要' : '一般' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="mt-4 flex justify-end">
        <el-pagination
          v-model:current-page="alarmsPage"
          v-model:page-size="alarmsPageSize"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="alarms.length"
        />
      </div>
    </TableCard>
      </el-tab-pane>

      <el-tab-pane label="资源统计" name="metrics">
        <TableCard class="mb-4">
          <template #header>
            <div class="flex items-center justify-between">
              <div class="font-semibold metrics-title">系统资源实时统计</div>
              <div class="flex items-center gap-2">
                <el-select v-model="wvpAutoRefresh" class="metrics-refresh-select" @change="onWvpAutoRefreshChange">
                  <el-option label="手动刷新" value="0" />
                  <el-option label="15秒" value="15" />
                  <el-option label="30秒" value="30" />
                  <el-option label="60秒" value="60" />
                </el-select>
                <el-button type="primary" :loading="wvpLoading" @click="fetchWvpMetrics">刷新统计</el-button>
              </div>
            </div>
          </template>

          <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <el-card shadow="never" class="wvp-kpi-card">
              <div class="wvp-kpi-label">CPU</div>
              <div class="wvp-kpi-value">{{ wvpKpi.cpu.toFixed(1) }}%</div>
            </el-card>
            <el-card shadow="never" class="wvp-kpi-card">
              <div class="wvp-kpi-label">内存</div>
              <div class="wvp-kpi-value">{{ wvpKpi.memory.toFixed(1) }}%</div>
            </el-card>
            <el-card shadow="never" class="wvp-kpi-card">
              <div class="wvp-kpi-label">磁盘</div>
              <div class="wvp-kpi-value">{{ wvpKpi.disk.toFixed(1) }}%</div>
            </el-card>
            <el-card shadow="never" class="wvp-kpi-card">
              <div class="wvp-kpi-label">网络带宽</div>
              <div class="wvp-kpi-value">{{ wvpKpi.networkMbps.toFixed(2) }} Mbps</div>
            </el-card>
            <el-card shadow="never" class="wvp-kpi-card">
              <div class="wvp-kpi-label">节点负载</div>
              <div class="wvp-kpi-value">{{ wvpKpi.nodeLoad.toFixed(1) }}%</div>
            </el-card>
          </div>

          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div class="wvp-chart-box">
              <div class="wvp-chart-title">CPU / 内存 / 磁盘 趋势</div>
              <VChart class="wvp-chart" :option="resourceTrendOption" autoresize />
            </div>
            <div class="wvp-chart-box">
              <div class="wvp-chart-title">网络吞吐与流数量（1小时）</div>
              <VChart class="wvp-chart" :option="networkTrendOption" autoresize />
            </div>
            <div class="wvp-chart-box">
              <div class="wvp-chart-title">节点负载（租户在线率 Top）</div>
              <VChart class="wvp-chart" :option="tenantLoadOption" autoresize />
            </div>
            <div class="wvp-chart-box">
              <div class="wvp-chart-title">资源负载仪表盘</div>
              <VChart class="wvp-chart" :option="gaugeOption" autoresize />
            </div>
          </div>
        </TableCard>
      </el-tab-pane>
    </el-tabs>

    <AppDialog v-model="systemInfoVisible" title="平台信息" size="medium" class="system-info-dialog">
      <div class="dialog-content">
        <div class="info-section">
          <div class="info-item">
            <div class="info-label">编号</div>
            <div class="info-value-wrapper">
              <span class="info-value">{{ systemInfo.sip_id || '-' }}</span>
              <el-button 
                v-if="systemInfo.sip_id" 
                size="small" 
                type="primary" 
                link 
                @click="copyToClipboard(systemInfo.sip_id)"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="info-item">
            <div class="info-label">域</div>
            <div class="info-value-wrapper">
              <span class="info-value">{{ systemInfo.sip_domain || '-' }}</span>
              <el-button 
                v-if="systemInfo.sip_domain" 
                size="small" 
                type="primary" 
                link 
                @click="copyToClipboard(systemInfo.sip_domain)"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="info-item">
            <div class="info-label">IP</div>
            <div class="info-value-wrapper">
              <span class="info-value">{{ systemInfo.sip_ip || '-' }}</span>
              <el-button 
                v-if="systemInfo.sip_ip" 
                size="small" 
                type="primary" 
                link 
                @click="copyToClipboard(systemInfo.sip_ip)"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="info-item">
            <div class="info-label">端口</div>
            <div class="info-value-wrapper">
              <span class="info-value">{{ systemInfo.sip_port || '-' }}</span>
              <el-button 
                v-if="systemInfo.sip_port" 
                size="small" 
                type="primary" 
                link 
                @click="copyToClipboard(String(systemInfo.sip_port))"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="info-item">
            <div class="info-label">密码</div>
            <div class="info-value-wrapper">
              <el-input 
                v-if="systemInfo.sip_password" 
                :model-value="systemInfo.sip_password" 
                type="password" 
                show-password 
                size="small" 
                readonly 
                class="info-password-input"
              />
              <span v-else class="info-value-empty">未设置</span>
              <el-button 
                v-if="systemInfo.sip_password" 
                size="small" 
                type="primary" 
                link 
                @click="copyToClipboard(systemInfo.sip_password)"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="systemInfoVisible = false">关闭</el-button>
          <el-button 
            type="primary" 
            @click="copyAllSystemInfo"
            class="copy-all-btn"
          >
            <el-icon class="mr-1"><DocumentCopy /></el-icon>
            一键复制全部
          </el-button>
        </div>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onDeactivated, onActivated, watch } from 'vue'
import api from '@/utils/http'
import { ElNotification, ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, GaugeChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { 
  Monitor, Box, CircleCheck, TrendCharts, Bell, Grid, 
  Connection, VideoPlay, Setting, DataAnalysis, BellFilled, 
  Warning, Right, Clock, InfoFilled, DocumentCopy 
} from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

use([CanvasRenderer, LineChart, BarChart, GaugeChart, GridComponent, TooltipComponent, LegendComponent])

const demoEnabled = ref(false)

const stats = ref({
  device_total: 0,
  device_online: 0,
  channel_total: 0,
  channel_online: 0,
  online_rate_pct: 0,
  record_count: 0,
  channels_with_record: 0,
  record_completeness_pct: 0
})
const statsLoading = ref(true)
const alarms = ref<Alarm[]>([])
const alarmsLoading = ref(true)
const alarmsEmptyText = ref('暂无告警记录，有告警时会在此显示')
const alarmsPage = ref(1)
const alarmsPageSize = ref(10)
const activeTab = ref<'overview' | 'metrics'>('overview')
const wvpLoading = ref(false)
const wvpAutoRefresh = ref('30')
const wvpRefreshTimer = ref<number | null>(null)
const wvpKpi = ref({
  cpu: 0,
  memory: 0,
  disk: 0,
  networkMbps: 0,
  nodeLoad: 0
})
const resourceTrend = ref<Array<{ time: string; cpu: number; memory: number; disk: number; nodeLoad: number }>>([])
const networkTrend = ref<Array<{ time: string; estimated: number; zlm: number; streams: number }>>([])
const tenantLoads = ref<Array<{ name: string; ratio: number }>>([])

const onlineDonutStyle = computed(() => {
  const pct = Number(stats.value.online_rate_pct || 0)
  const fixed = Math.max(0, Math.min(100, pct))
  return {
    background: `conic-gradient(#22c55e ${fixed}%, #e5e7eb ${fixed}% 100%)`
  }
})

const alarmPriorityStats = computed(() => {
  const levels = [
    { key: 'p1', label: '紧急', matcher: (p: string) => p === '1' },
    { key: 'p2', label: '重要', matcher: (p: string) => p === '2' },
    { key: 'p3', label: '一般', matcher: (p: string) => p !== '1' && p !== '2' }
  ]
  const total = alarms.value.length || 1
  return levels.map((item) => {
    const value = alarms.value.filter((x) => item.matcher(String(x?.priority || ''))).length
    return {
      key: item.key,
      label: item.label,
      value,
      rate: Math.round((value / total) * 100)
    }
  })
})

const alarmTrendSeries = computed(() => {
  const bucketCount = 12
  const now = Date.now()
  const start = now - 24 * 60 * 60 * 1000
  const step = (24 * 60 * 60 * 1000) / bucketCount
  const buckets = new Array(bucketCount).fill(0)
  for (const item of alarms.value) {
    const ts = Number(new Date(item?.time || '').getTime())
    if (!Number.isFinite(ts) || ts < start || ts > now) continue
    const idx = Math.min(bucketCount - 1, Math.max(0, Math.floor((ts - start) / step)))
    buckets[idx] += 1
  }
  return buckets
})

const alarmTrendPolyline = computed(() => {
  const w = 360
  const h = 160
  const top = 12
  const bottom = 24
  const max = Math.max(...alarmTrendSeries.value, 1)
  const stepX = w / (alarmTrendSeries.value.length - 1 || 1)
  return alarmTrendSeries.value
    .map((v, i) => {
      const x = i * stepX
      const y = top + (1 - v / max) * (h - top - bottom)
      return `${x},${y}`
    })
    .join(' ')
})

const alarmTrendFillPolyline = computed(() => {
  const w = 360
  const h = 160
  const baseY = h - 24
  const line = alarmTrendPolyline.value
  if (!line) return `0,${baseY} ${w},${baseY}`
  return `0,${baseY} ${line} ${w},${baseY}`
})

const trendStartLabel = computed(() => {
  const d = new Date(Date.now() - 24 * 60 * 60 * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
})

const resourceTrendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { top: 4, textStyle: { color: '#64748b', fontSize: 12 } },
  grid: { left: 36, right: 20, top: 36, bottom: 24 },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: resourceTrend.value.map((x) => x.time),
    axisLabel: { color: '#94a3b8', fontSize: 11 }
  },
  yAxis: {
    type: 'value',
    min: 0,
    max: 100,
    axisLabel: { formatter: '{value}%', color: '#94a3b8', fontSize: 11 },
    splitLine: { lineStyle: { color: '#f1f5f9' } }
  },
  series: [
    { name: 'CPU', type: 'line', smooth: true, data: resourceTrend.value.map((x) => x.cpu), lineStyle: { width: 2, color: '#3b82f6' }, areaStyle: { color: 'rgba(59,130,246,0.10)' } },
    { name: '内存', type: 'line', smooth: true, data: resourceTrend.value.map((x) => x.memory), lineStyle: { width: 2, color: '#22c55e' }, areaStyle: { color: 'rgba(34,197,94,0.08)' } },
    { name: '磁盘', type: 'line', smooth: true, data: resourceTrend.value.map((x) => x.disk), lineStyle: { width: 2, color: '#f59e0b' } },
    { name: '节点负载', type: 'line', smooth: true, data: resourceTrend.value.map((x) => x.nodeLoad), lineStyle: { width: 2, color: '#ef4444' } }
  ]
}))

const networkTrendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { top: 4, textStyle: { color: '#64748b', fontSize: 12 } },
  grid: { left: 42, right: 46, top: 36, bottom: 24 },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: networkTrend.value.map((x) => x.time),
    axisLabel: { color: '#94a3b8', fontSize: 11 }
  },
  yAxis: [
    {
      type: 'value',
      name: 'Mbps',
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    {
      type: 'value',
      name: '流数量',
      axisLabel: { color: '#94a3b8', fontSize: 11 }
    }
  ],
  series: [
    { name: '估算带宽', type: 'line', smooth: true, data: networkTrend.value.map((x) => x.estimated), lineStyle: { width: 2, color: '#22c55e' } },
    { name: '节点带宽', type: 'line', smooth: true, data: networkTrend.value.map((x) => x.zlm), lineStyle: { width: 2, color: '#3b82f6' }, areaStyle: { color: 'rgba(59,130,246,0.08)' } },
    { name: '流数量', type: 'line', smooth: true, yAxisIndex: 1, data: networkTrend.value.map((x) => x.streams), lineStyle: { width: 2, color: '#f59e0b' } }
  ]
}))

const tenantLoadOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 42, right: 20, top: 20, bottom: 24 },
  xAxis: {
    type: 'value',
    min: 0,
    max: 100,
    axisLabel: { formatter: '{value}%', color: '#94a3b8', fontSize: 11 },
    splitLine: { lineStyle: { color: '#f1f5f9' } }
  },
  yAxis: {
    type: 'category',
    data: tenantLoads.value.map((x) => x.name),
    axisLabel: { color: '#64748b', fontSize: 12 }
  },
  series: [
    {
      type: 'bar',
      data: tenantLoads.value.map((x) => x.ratio),
      barWidth: 14,
      itemStyle: { color: 'var(--el-color-primary)', borderRadius: [0, 8, 8, 0] },
      label: { show: true, position: 'right', formatter: '{c}%' }
    }
  ]
}))

const gaugeOption = computed(() => ({
  tooltip: { formatter: '{a}<br/>{b}: {c}%' },
  series: [
    {
      name: '节点负载',
      type: 'gauge',
      center: ['50%', '58%'],
      min: 0,
      max: 100,
      splitNumber: 5,
      progress: { show: true, width: 10 },
      axisLine: { lineStyle: { width: 10 } },
      pointer: { width: 3 },
      detail: { valueAnimation: true, formatter: '{value}%' },
      data: [{ value: Number(wvpKpi.value.nodeLoad.toFixed(1)), name: '负载指数' }]
    }
  ]
}))

const normalizeToPercent = (value: number) => Math.max(0, Math.min(100, Number(value || 0)))

const clearWvpRefreshTimer = () => {
  if (wvpRefreshTimer.value !== null) {
    window.clearInterval(wvpRefreshTimer.value)
    wvpRefreshTimer.value = null
  }
}

const onWvpAutoRefreshChange = () => {
  clearWvpRefreshTimer()
  const interval = Number(wvpAutoRefresh.value)
  if (interval > 0 && activeTab.value === 'metrics') {
    wvpRefreshTimer.value = window.setInterval(() => {
      fetchWvpMetrics()
    }, interval * 1000)
  }
}

const extractDiskPercent = (diagnoseData: Record<string, unknown>) => {
  const items = Array.isArray(diagnoseData?.items) ? diagnoseData.items : []
  const systemItem = items.find((x: Record<string, unknown>) => x?.section === 'system')
  const text = String(systemItem?.text || '')
  const match = text.match(/磁盘已用\s*([0-9.]+)%/)
  return match ? Number(match[1]) : 0
}

const fetchWvpMetrics = async () => {
  wvpLoading.value = true
  try {
    const [opsRes, summaryRes, bandwidthRes, topologyRes, diagnoseRes] = await Promise.all([
      api.get('/api/v1/ops/status'),
      api.get('/api/v1/network/summary'),
      api.get('/api/v1/network/bandwidth', { params: { range: '1h' } }),
      api.get('/api/v1/network/topology'),
      api.get('/api/v1/ops/diagnose-report')
    ])
    const ops = opsRes.data || {}
    const summary = summaryRes.data || {}
    const disk = normalizeToPercent(extractDiskPercent(diagnoseRes.data))
    const cpu = normalizeToPercent(Number(ops.cpu || 0))
    const memory = normalizeToPercent(Number(ops.memory_percent || 0))
    const networkMbps = Number(summary.zlm_bandwidth_mbps ?? 0)
    const streams = Number(summary.stream_count_zlm ?? summary.stream_count ?? 0)

    const tenantNodes = (Array.isArray(topologyRes.data?.nodes) ? topologyRes.data.nodes : [])
      .filter((x: Record<string, unknown>) => x?.type === 'tenant')
      .map((x: Record<string, unknown>) => {
        const online = Number(x?.metrics?.device_online || 0)
        const total = Number(x?.metrics?.device_total || 0)
        const ratio = total > 0 ? normalizeToPercent((online / total) * 100) : 0
        return { name: String(x?.label || x?.id || '未知租户'), ratio }
      })
      .sort((a: Record<string, unknown>, b: Record<string, unknown>) => b.ratio - a.ratio)
      .slice(0, 8)
    tenantLoads.value = tenantNodes

    const nodeLoad = normalizeToPercent(cpu * 0.45 + memory * 0.35 + Math.min(20, networkMbps) * 1.0)
    wvpKpi.value = {
      cpu,
      memory,
      disk,
      networkMbps,
      nodeLoad
    }

    const nowLabel = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    resourceTrend.value = [...resourceTrend.value, { time: nowLabel, cpu, memory, disk, nodeLoad }].slice(-40)

    const series = Array.isArray(bandwidthRes.data?.series) ? bandwidthRes.data.series : []
    const streamSeries = series.find((x: Record<string, unknown>) => x?.name === 'active_streams')
    const estSeries = series.find((x: Record<string, unknown>) => x?.name === 'estimated_bandwidth')
    const zlmSeries = series.find((x: Record<string, unknown>) => x?.name === 'zlm_bandwidth')
    const points = new Map<string, { estimated: number; zlm: number; streams: number }>()
    for (const p of streamSeries?.points || []) {
      const key = String(p?.t || '')
      points.set(key, { estimated: 0, zlm: 0, streams: Number(p?.value || 0) })
    }
    for (const p of estSeries?.points || []) {
      const key = String(p?.t || '')
      const base = points.get(key) || { estimated: 0, zlm: 0, streams: 0 }
      base.estimated = Number(p?.value || 0)
      points.set(key, base)
    }
    for (const p of zlmSeries?.points || []) {
      const key = String(p?.t || '')
      const base = points.get(key) || { estimated: 0, zlm: 0, streams: 0 }
      base.zlm = Number(p?.value || 0)
      points.set(key, base)
    }
    networkTrend.value = Array.from(points.entries())
      .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
      .map(([k, v]) => {
        const d = new Date(k)
        const hh = String(d.getHours()).padStart(2, '0')
        const mm = String(d.getMinutes()).padStart(2, '0')
        return { time: `${hh}:${mm}`, estimated: v.estimated, zlm: v.zlm, streams: v.streams }
      })
      .slice(-60)
    if (!networkTrend.value.length && streams > 0) {
      networkTrend.value = [{ time: nowLabel, estimated: networkMbps, zlm: networkMbps, streams }]
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    wvpLoading.value = false
  }
}

const paginatedAlarms = computed(() => {
  const start = (alarmsPage.value - 1) * alarmsPageSize.value
  const end = start + alarmsPageSize.value
  return alarms.value.slice(start, end)
})

watch(() => alarms.value.length, () => {
  const maxPage = Math.ceil(alarms.value.length / alarmsPageSize.value) || 1
  if (alarmsPage.value > maxPage) {
    alarmsPage.value = maxPage
  }
})
let ws: WebSocket | null = null
let closedByUser = false
let reconnectTimer: number | null = null
let reconnectAttempts = 0

let notifyTimer: number | null = null
let notifyWindowStartedAt = 0
let pendingNotifyCount = 0
let lastPendingAlarm: Record<string, unknown> = null
const NOTIFY_WINDOW_MS = 2000

const systemInfoVisible = ref(false)
const systemInfo = ref({
  sip_id: '',
  sip_domain: '',
  sip_ip: '',
  sip_port: 0,
  sip_password: '',
  version: '',
  project_name: ''
})

const onlineRateClass = computed(() => {
  const pct = stats.value.online_rate_pct
  if (pct >= 90) return 'text-emerald-400'
  if (pct >= 60) return 'text-amber-300'
  return 'text-rose-400'
})

const fetchStats = async () => {
  statsLoading.value = true
  try {
    const res = await api.get('/api/v1/metrics/devices-overview')
    const d = res.data || {}
    stats.value = {
      device_total: d.device_total ?? 0,
      device_online: d.device_online ?? 0,
      channel_total: d.channel_total ?? 0,
      channel_online: d.channel_online ?? 0,
      online_rate_pct: d.device_online_rate_pct ?? d.online_rate_pct ?? 0,
      record_count: stats.value.record_count,
      channels_with_record: stats.value.channels_with_record,
      record_completeness_pct: stats.value.record_completeness_pct
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    statsLoading.value = false
  }
}

const formatTime = (t: string | number) => {
  if (!t) return '—'
  try {
    return new Date(t).toLocaleString('zh-CN')
  } catch {
    return String(t)
  }
}

const fetchAlarms = async () => {
  alarmsLoading.value = true
  try {
    const res = await api.get('/api/v1/alarms?limit=50')
    alarms.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    alarms.value = []
    alarmsEmptyText.value = '加载告警列表失败，请稍后重试'
  } finally {
    alarmsLoading.value = false
  }
}

const getPriorityType = (p: string) => {
  if (p === '1') return 'danger'
  if (p === '2') return 'warning'
  return 'info'
}

const getAlarmRowClass = ({ row }: { row: Record<string, unknown> }) => {
  if (row.priority === '1') return 'alarm-row-danger'
  if (row.priority === '2') return 'alarm-row-warning'
  return ''
}

const initWebSocket = () => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.host
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  ws = new WebSocket(`${protocol}://${host}/api/v1/alarms/ws`)
  
  ws.onmessage = (event) => {
    try {
      const alarm = JSON.parse(event.data)
      alarms.value.unshift(alarm)
      if (alarms.value.length > 50) alarms.value.pop()

      const now = Date.now()
      if (!notifyWindowStartedAt || now - notifyWindowStartedAt >= NOTIFY_WINDOW_MS) {
        notifyWindowStartedAt = now
        pendingNotifyCount = 0
        lastPendingAlarm = null
      }
      pendingNotifyCount += 1
      lastPendingAlarm = alarm

      if (notifyTimer == null) {
        const delay = Math.max(0, NOTIFY_WINDOW_MS - (now - notifyWindowStartedAt))
        notifyTimer = window.setTimeout(() => {
          const count = pendingNotifyCount
          const last = lastPendingAlarm
          notifyTimer = null
          notifyWindowStartedAt = 0
          pendingNotifyCount = 0
          lastPendingAlarm = null

          const message = last ? `${last.device_id}: ${last.description || '告警'}` : '收到新告警'
          ElNotification({
            title: count > 1 ? `新告警（${count} 条）` : '新告警',
            message,
            type: 'error',
            duration: 5000
          })
        }, delay)
      }
    } catch { /* cleanup: ignore */ }
  }

  ws.onopen = () => {
    reconnectAttempts = 0
  }

  ws.onclose = () => {
    if (closedByUser) return
    if (reconnectTimer != null) return
    reconnectAttempts += 1
    if (reconnectAttempts > 10) {
      return
    }
    const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(reconnectAttempts, 5)))
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      initWebSocket()
    }, delay)
  }
}

onMounted(() => {
  api.get('/api/v1/demo/status').then((r) => {
    demoEnabled.value = r.data?.enabled === true
  }).catch(() => {
    demoEnabled.value = false
  })
  fetchStats()
  fetchAlarms()
  initWebSocket()
  if (activeTab.value === 'metrics') {
    fetchWvpMetrics()
    onWvpAutoRefreshChange()
  }
})

watch(activeTab, (tab) => {
  if (tab === 'metrics') {
    if (resourceTrend.value.length === 0) {
      fetchWvpMetrics()
    }
    onWvpAutoRefreshChange()
  } else {
    clearWvpRefreshTimer()
  }
})

onBeforeUnmount(() => {
  closedByUser = true
  if (ws) ws.close()
  if (notifyTimer != null) {
    clearTimeout(notifyTimer)
    notifyTimer = null
  }
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  clearWvpRefreshTimer()
})

onDeactivated(() => {
  closedByUser = true
  if (ws) ws.close()
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  clearWvpRefreshTimer()
})

onActivated(() => {
  closedByUser = false
  reconnectAttempts = 0
  initWebSocket()
  fetchStats()
})

const openSystemInfoDialog = async () => {
  systemInfoVisible.value = true
  await fetchSystemInfo()
}

const fetchSystemInfo = async () => {
  try {
    const res = await api.get('/api/v1/system-config/system-info')
    const data = res.data
    systemInfo.value = data && typeof data === 'object'
      ? { sip_id: '', sip_domain: '', sip_ip: '', sip_port: 0, sip_password: '', version: '', project_name: '', ...data }
      : { sip_id: '', sip_domain: '', sip_ip: '', sip_port: 0, sip_password: '', version: '', project_name: '' }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const copyToClipboard = async (text: string) => {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success('已复制到剪贴板')
      return
    } catch {
      // fallback
    }
  }
  
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    const successful = document.execCommand('copy')
    textArea.remove()
    if (successful) {
      ElMessage.success('已复制到剪贴板')
    } else {
      ElMessage.warning('复制失败，请手动复制')
    }
  } catch (err) {
    ElMessage.warning('复制失败，请手动复制')
  }
}

const copyAllSystemInfo = () => {
  const info = systemInfo.value
  const text = `编号: ${info.sip_id}
域: ${info.sip_domain}
IP: ${info.sip_ip}
端口: ${info.sip_port}
密码: ${info.sip_password || '未设置'}`
  copyToClipboard(text)
}
</script>

<style scoped>
/* Demo Alert */
.demo-alert {
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: none;
}

/* Action Buttons */
.action-btn {
  transition: all var(--transition-time-02);
  border-radius: 6px;
}
.dashboard-tabs {
  margin-top: 10px;
}
.wvp-kpi-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #ffffff;
}
.wvp-kpi-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.wvp-kpi-value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.1;
}
.wvp-chart-box {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-bg-color);
  box-shadow: none;
}
.wvp-chart-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}
.wvp-chart {
  width: 100%;
  height: 230px;
}

/* Stat Cards */
.stat-card {
  --accent: var(--el-color-primary);
  border-radius: 8px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: #ffffff;
  box-shadow: none;
  transition: transform var(--transition-time-02), box-shadow var(--transition-time-02), border-color var(--transition-time-02);
}
.stat-card--primary { --accent: var(--el-color-primary); }
.stat-card--success { --accent: var(--el-color-success); }
.stat-card--warning { --accent: var(--el-color-warning); }
.stat-card--danger { --accent: var(--el-color-danger); }
.stat-card :deep(.el-card__body) {
  padding: 0;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
}
.stat-card:hover {
  border-color: var(--el-color-primary-light-7);
  transform: none;
  box-shadow: none;
}
.stat-icon {
  width: 34px;
  height: 34px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, white);
  box-shadow: none;
}
.stat-content {
  flex: 1;
  min-width: 0;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 600;
  margin-bottom: 6px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
}
.stat-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Quick Access */
.quick-access-card {
  border-radius: 8px;
}
.chart-card {
  border-radius: 8px;
}
.chart-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.donut-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 180px;
}
.donut {
  width: 132px;
  height: 132px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 8px rgba(255, 255, 255, 0.45);
}
.donut-center {
  width: 94px;
  height: 94px;
  border-radius: 50%;
  background: var(--el-bg-color);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.donut-rate {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}
.donut-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.donut-legend {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.legend-item.total {
  margin-top: 4px;
  font-weight: 600;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}
.legend-dot.online {
  background: var(--el-color-success);
}
.legend-dot.offline {
  background: var(--el-border-color);
}
.bar-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 160px;
  justify-content: center;
}
.bar-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bar-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.bar-track {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}
.bar-fill.p1 {
  background: var(--el-color-danger);
}
.bar-fill.p2 {
  background: var(--el-color-warning);
}
.bar-fill.p3 {
  background: var(--el-color-primary);
}
.line-chart-wrap {
  min-height: 160px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.line-chart {
  width: 100%;
  height: 136px;
}
.line-axis {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.quick-link {
  --quick-accent: var(--el-color-primary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  border-radius: 8px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  text-decoration: none;
  box-shadow: none;
  transition: transform var(--transition-time-02), box-shadow var(--transition-time-02), border-color var(--transition-time-02), background-color var(--transition-time-02);
}
.quick-link:hover {
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
  transform: none;
  box-shadow: none;
}
.quick-link-icon {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--quick-accent);
  background: color-mix(in srgb, var(--quick-accent) 14%, white);
}
.quick-link-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.quick-link-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1;
}
.quick-link--devices { --quick-accent: var(--el-color-primary); }
.quick-link--monitor { --quick-accent: var(--el-color-primary); }
.quick-link--alarms { --quick-accent: var(--el-color-primary); }
.quick-link--platforms { --quick-accent: var(--el-color-primary); }
.quick-link--record { --quick-accent: var(--el-color-primary); }
.quick-link--ops { --quick-accent: var(--el-color-primary); }
.quick-link--health { --quick-accent: var(--el-color-primary); }

.quick-access-title {
  color: var(--el-text-color-primary);
}

.quick-access-subtitle {
  color: var(--el-text-color-secondary);
}

@media (max-width: 768px) {
  .stat-card {
    padding: 16px;
  }
  .stat-value {
    font-size: 28px;
  }
  .quick-link {
    padding: 14px 10px;
  }
}

/* Alarms Card */
.alarms-card {
  border-radius: 8px;
}
.alarm-tag {
  animation: none;
}
.view-alarms-btn {
  transition: all var(--transition-time-02);
  border-radius: 6px;
}
.view-alarms-btn:hover {
  transform: none;
}

/* Alarms Table */
.alarms-table :deep(.el-table__row) {
  transition: all var(--transition-time-02);
}
.alarms-table :deep(.el-table__row:hover) {
  background: var(--el-fill-color-extra-light);
}
.alarm-row-danger {
  background: var(--el-color-danger-light-9);
}
.alarm-row-warning {
  background: var(--el-color-warning-light-9);
}
.text-link {
  color: var(--el-color-primary);
}
.time-cell, .device-cell, .desc-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.priority-tag {
  font-weight: 600;
  border-radius: 999px;
}

.system-info-btn {
  border-color: var(--el-border-color);
}
.system-info-btn:hover {
  box-shadow: none;
  transform: none;
}

.gb-info-section h3,
.version-info-section h3 {
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding-bottom: 10px;
}

.info-item,
.version-item {
  padding: 12px 14px;
  background: var(--el-bg-color);
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);
}

.copy-all-btn {
  border-color: var(--el-border-color);
}
.copy-all-btn:hover {
  box-shadow: none;
}

.system-info-dialog :deep(.el-dialog__header) {
  padding: 18px 22px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.system-info-dialog :deep(.el-dialog__body) {
  padding: 18px 22px;
}

.system-info-dialog :deep(.el-dialog__footer) {
  padding: 12px 22px 18px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.dialog-content {
  width: 100%;
}

.info-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--el-bg-color);
  border-radius: 14px;
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.info-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  min-width: 70px;
}

.info-value-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  justify-content: flex-end;
}

.info-value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.info-value-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

.dialog-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.metrics-title {
  color: var(--el-text-color-primary);
}

.metrics-refresh-select {
  width: 130px;
}

.info-password-input {
  width: 180px;
}
</style>
