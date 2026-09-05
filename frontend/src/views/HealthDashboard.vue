<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('healthPage.title')" :description="t('healthPage.description')">
          <template #actions>
            <div class="flex items-center gap-2 flex-wrap">
              <el-select v-model="autoRefresh" style="width: 140px" @change="onAutoRefreshChange">
                <el-option :label="t('healthPage.manualRefresh')" value="0" />
                <el-option :label="t('healthPage.every15s')" value="15" />
                <el-option :label="t('healthPage.every30s')" value="30" />
                <el-option :label="t('healthPage.every60s')" value="60" />
              </el-select>
              <el-button @click="resetFilters">{{ t('healthPage.resetFilters') }}</el-button>
              <el-button @click="previewRecommendations" :loading="applying">{{ t('healthPage.smartPreview') }}</el-button>
              <el-button @click="previewP5Template" :loading="loading">{{ t('healthPage.p5Template') }}</el-button>
              <el-button @click="previewDailyReport" :loading="loading">{{ t('healthPage.dailyReport') }}</el-button>
              <el-button @click="downloadDailyReportCsv">{{ t('healthPage.downloadDailyCsv') }}</el-button>
              <el-button @click="exportCurrentCsv">{{ t('healthPage.exportCsv') }}</el-button>
              <el-button type="primary" @click="fetchData" :loading="loading">
                <el-icon class="mr-1"><Refresh /></el-icon> {{ t('healthPage.refresh') }}
              </el-button>
            </div>
          </template>
        </PageHeader>
      </template>

    <TableCard class="mb-4">
      <div class="grid grid-cols-1 md:grid-cols-8 gap-3">
        <el-select v-model="filters.risk_level" :placeholder="t('healthPage.riskLevel')" clearable>
          <el-option :label="t('healthPage.riskLow')" value="low" />
          <el-option :label="t('healthPage.riskMedium')" value="medium" />
          <el-option :label="t('healthPage.riskHigh')" value="high" />
        </el-select>
        <el-select v-model="filters.current_policy_mode" :placeholder="t('healthPage.currentPolicy')" clearable>
          <el-option label="GLOBAL" value="GLOBAL" />
          <el-option label="AUTO" value="AUTO" />
          <el-option label="UDP" value="UDP" />
          <el-option :label="t('healthPage.tcpPassive')" value="TCP_PASSIVE" />
          <el-option :label="t('healthPage.tcpActive')" value="TCP_ACTIVE" />
        </el-select>
        <el-input-number v-model="filters.min_failure_rate" :min="0" :max="100" :step="5" class="w-full" :placeholder="t('healthPage.minFailureRate')" />
        <el-switch v-model="filters.only_diff" inline-prompt :active-text="t('healthPage.diffOnly')" :inactive-text="t('healthPage.all')" />
        <el-switch v-model="alertConfig.enabled" inline-prompt :active-text="t('healthPage.riskAlert')" :inactive-text="t('healthPage.silent')" />
        <el-input-number v-model="alertConfig.highRiskThreshold" :min="1" :max="50" :step="1" class="w-full" />
        <el-input-number v-model="alertConfig.holdMinutes" :min="1" :max="120" :step="1" class="w-full" />
        <div class="flex items-center gap-2">
          <el-button type="warning" @click="applyHighRiskRecommendations" :loading="applying">{{ t('healthPage.applyHighRisk') }}</el-button>
          <el-button type="success" @click="applySelectedRecommendations" :disabled="selectedRows.length === 0" :loading="applying">{{ t('healthPage.applySelected') }}</el-button>
        </div>
      </div>
    </TableCard>

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.onlineRate') }}</div>
        <div class="text-2xl font-bold" :style="{ color: healthOverview.online_rate_pct >= 90 ? 'var(--el-color-success)' : healthOverview.online_rate_pct >= 70 ? 'var(--el-color-warning)' : 'var(--el-color-danger)' }">{{ healthOverview.online_rate_pct?.toFixed(1) ?? '-' }}%</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.deviceOnline') }}</div>
        <div class="text-2xl font-bold text-emerald-400">{{ healthOverview.device_online ?? '-' }} / {{ healthOverview.device_total ?? '-' }}</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.channelOnline') }}</div>
        <div class="text-2xl font-bold text-sky-400">{{ healthOverview.channel_online ?? '-' }} / {{ healthOverview.channel_total ?? '-' }}</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.recordCount') }}</div>
        <div class="text-2xl font-bold text-blue-400">{{ healthOverview.record_count ?? '-' }}</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.recordCompleteness') }}</div>
        <div class="text-2xl font-bold" :style="{ color: healthOverview.record_completeness_pct >= 90 ? 'var(--el-color-success)' : 'var(--el-color-warning)' }">{{ healthOverview.record_completeness_pct?.toFixed(1) ?? '-' }}%</div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
      <el-card class="app-surface text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.totalDevices') }}</div>
        <div class="text-2xl font-bold text-sky-400">{{ stats.total }}</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.highFailureRate') }}</div>
        <div class="text-2xl font-bold text-rose-400">{{ stats.highFailure }}</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.autoSwitched') }}</div>
        <div class="text-2xl font-bold text-amber-300">{{ stats.autoSwitched }}</div>
      </el-card>
      <el-card shadow="hover" class="text-center">
        <div class="mb-1" style="color: var(--el-text-color-secondary)">{{ t('healthPage.unstable') }}</div>
        <div class="text-2xl font-bold text-yellow-300">{{ stats.unstable }}</div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
      <el-card shadow="hover">
        <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">{{ t('healthPage.capacityBaselineLevel') }}</div>
        <el-tag :type="capacityBaseline.health_level === 'red' ? 'danger' : capacityBaseline.health_level === 'yellow' ? 'warning' : 'success'">
          {{ capacityBaseline.health_level || 'green' }}
        </el-tag>
        <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">
          {{ t('healthPage.highRiskRatio') }} {{ (capacityBaseline.high_risk_ratio * 100).toFixed(1) }}%，{{ t('healthPage.unstableRatio') }} {{ (capacityBaseline.unstable_ratio * 100).toFixed(1) }}%
        </div>
      </el-card>
      <el-card shadow="hover">
        <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">{{ t('healthPage.sipRateLimitHit') }}</div>
        <div class="text-xs">
          {{ t('healthPage.deviceRateLimit') }}: {{ sipRateStats.blocked_device }} {{ t('healthPage.times') }} · {{ t('healthPage.tenantRateLimit') }}: {{ sipRateStats.blocked_tenant }} {{ t('healthPage.times') }}
        </div>
        <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">
          backend(redis/local/fallback): {{ sipRateStats.backend_redis }}/{{ sipRateStats.backend_local }}/{{ sipRateStats.backend_fallback }}
        </div>
      </el-card>
      <el-card shadow="hover">
        <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">{{ t('healthPage.p4TuningAdvice') }}</div>
        <div class="text-xs">{{ t('healthPage.policy') }}: {{ tuningRecommendations.profile }} · {{ t('healthPage.changedCount') }}: {{ tuningRecommendations.changed_count }}</div>
        <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">{{ tuningRecommendations.reason || '—' }}</div>
      </el-card>
    </div>

    <TableCard>
      <el-table :data="paginatedHealthData" style="width: 100%" v-loading="loading" stripe border row-key="device_id" @selection-change="onSelectionChange" :empty-text="t('healthPage.noHealthData')">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="device_id" :label="t('healthPage.deviceIdCol')" width="180" sortable />
        <el-table-column prop="device_name" :label="t('common.name')" min-width="140" />

        <el-table-column prop="last_mode" :label="t('healthPage.lastModeCol')" width="120">
          <template #default="scope">
            <el-tag :type="getModeTagType(scope.row.last_mode) as 'success' | 'warning' | 'info'" size="small">
              {{ scope.row.last_mode || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="current_policy_mode" :label="t('healthPage.policyCol')" width="110">
          <template #default="scope">
            <el-tag effect="plain">{{ scope.row.current_policy_mode }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="t('healthPage.successRateCol')" width="180" sortable :sort-method="sortBySuccessRate">
          <template #default="scope">
            <div class="flex items-center">
              <el-progress
                :percentage="calculateSuccessRate(scope.row)"
                :status="getProgressStatus(scope.row)"
                :stroke-width="15"
                text-inside
                class="w-full"
              />
            </div>
            <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
              {{ scope.row.success_total }} {{ t('healthPage.success') }} / {{ scope.row.fail_total }} {{ t('healthPage.fail') }}
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="failure_rate" :label="t('healthPage.failureRateCol')" width="130" sortable>
          <template #default="scope">
            <el-tag :type="scope.row.failure_rate > 50 ? 'danger' : scope.row.failure_rate > 20 ? 'warning' : 'success'" effect="plain">
              {{ scope.row.failure_rate }}%
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="recommended_mode" :label="t('healthPage.recommendCol')" width="120">
          <template #default="scope">
            <el-tag :type="getModeTagType(scope.row.recommended_mode) as 'success' | 'warning' | 'info'" size="small">
              {{ scope.row.recommended_mode }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="risk_level" :label="t('healthPage.riskCol')" width="90">
          <template #default="scope">
            <el-tag :type="scope.row.risk_level === 'high' ? 'danger' : scope.row.risk_level === 'medium' ? 'warning' : 'success'" effect="plain" size="small">
              {{ scope.row.risk_level === 'high' ? t('healthPage.riskHigh') : scope.row.risk_level === 'medium' ? t('healthPage.riskMedium') : t('healthPage.riskLow') }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="recommend_reason" :label="t('healthPage.recommendReasonCol')" min-width="220" show-overflow-tooltip />

        <el-table-column prop="consecutive_failures" :label="t('healthPage.consecutiveFailuresCol')" width="110" sortable>
          <template #default="scope">
            <el-badge :value="scope.row.consecutive_failures" :type="scope.row.consecutive_failures > 0 ? 'danger' : 'info'" v-if="scope.row.consecutive_failures > 0" />
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">0</span>
          </template>
        </el-table-column>

        <el-table-column prop="auto_switch_count" :label="t('healthPage.autoSwitchCountCol')" width="120" sortable>
           <template #default="scope">
            <span :class="{'text-amber-300 font-semibold': scope.row.auto_switch_count > 0}">
              {{ scope.row.auto_switch_count }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="last_status_code" :label="t('healthPage.lastStatusCodeCol')" width="110">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.last_status_code)" effect="plain" size="small">
              {{ scope.row.last_status_code ?? '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="updated_at" :label="t('common.updateTime')" min-width="180">
          <template #default="scope">
            {{ formatDate(scope.row.updated_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="mt-4 flex justify-end">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="healthData.length"
        />
      </div>
    </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'

interface DeviceHealth {
  device_id: string
  device_name: string
  last_mode: string | null
  last_status_code: number | null
  success_total: number
  fail_total: number
  consecutive_failures: number
  auto_switch_count: number
  failure_rate: number
  current_policy_mode: string
  recommended_mode: string
  recommend_reason: string
  risk_level: string
  updated_at: string | null
}

interface HealthFilters {
  risk_level: string | null
  min_failure_rate: number
  current_policy_mode: string | null
  only_diff: boolean
}

interface ApplyResult {
  device_id: string
  previous_mode: string
  recommended_mode: string
  would_apply: boolean
  applied: boolean
  reason: string
}

interface SipRateStats {
  allowed: number
  blocked_device: number
  blocked_tenant: number
  backend_redis: number
  backend_local: number
  backend_fallback: number
}

interface CapacityBaseline {
  high_risk_ratio: number
  unstable_ratio: number
  health_level: string
  sip_rate_limit?: {
    stats?: SipRateStats
  }
}

interface TuningRecommendations {
  profile: string
  reason: string
  changed_count: number
}

interface P5Template {
  profile: string
  fleet_size: number
  recommended_concurrency: number
  performance_target?: {
    snapshot_p95_ms?: number
    play_first_frame_p95_ms?: number
  }
}

const healthData = ref<DeviceHealth[]>([])
const { t } = useI18n()  // FIXED: 国际化
const loading = ref(false)
const applying = ref(false)
const selectedRows = ref<DeviceHealth[]>([])
const autoRefresh = ref('0')
const refreshTimer = ref<number | null>(null)
const highRiskFirstSeenAt = ref<number | null>(null)
const alertCooldownUntil = ref(0)
const capacityBaseline = ref<CapacityBaseline>({
  high_risk_ratio: 0,
  unstable_ratio: 0,
  health_level: 'green'
})
const tuningRecommendations = ref<TuningRecommendations>({
  profile: 'balanced',
  reason: '',
  changed_count: 0
})
const p5Template = ref<P5Template>({
  profile: 'balanced',
  fleet_size: 0,
  recommended_concurrency: 5
})
const filters = ref<HealthFilters>({
  risk_level: null,
  min_failure_rate: 0,
  current_policy_mode: null,
  only_diff: false
})
const alertConfig = ref({
  enabled: true,
  highRiskThreshold: 3,
  holdMinutes: 5
})

const page = ref(1)
const pageSize = ref(20)

const paginatedHealthData = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return healthData.value.slice(start, end)
})

watch(() => healthData.value, () => {
  page.value = 1
})

const stats = computed(() => {
  const total = healthData.value.length
  const highFailure = healthData.value.filter(d => {
    return d.failure_rate > 50
  }).length
  const autoSwitched = healthData.value.filter(d => d.auto_switch_count > 0).length
  const unstable = healthData.value.filter(d => d.consecutive_failures > 0).length
  
  return { total, highFailure, autoSwitched, unstable }
})

const sipRateStats = computed<SipRateStats>(() => {
  const s = capacityBaseline.value?.sip_rate_limit?.stats
  return {
    allowed: Number(s?.allowed || 0),
    blocked_device: Number(s?.blocked_device || 0),
    blocked_tenant: Number(s?.blocked_tenant || 0),
    backend_redis: Number(s?.backend_redis || 0),
    backend_local: Number(s?.backend_local || 0),
    backend_fallback: Number(s?.backend_fallback || 0)
  }
})

const healthOverview = ref<{ device_total: number; device_online: number; channel_total: number; channel_online: number; online_rate_pct: number; record_count: number; channels_with_record: number; record_completeness_pct: number }>({ device_total: 0, device_online: 0, channel_total: 0, channel_online: 0, online_rate_pct: 0, record_count: 0, channels_with_record: 0, record_completeness_pct: 0 })

const fetchData = async () => {
  loading.value = true
  try {
    const params: Record<string, string | number | boolean> = {}
    if (filters.value.risk_level) params.risk_level = filters.value.risk_level
    if (filters.value.current_policy_mode) params.current_policy_mode = filters.value.current_policy_mode
    if (filters.value.min_failure_rate > 0) params.min_failure_rate = filters.value.min_failure_rate
    if (filters.value.only_diff) params.only_diff = true
    const [devicesRes, baselineRes, tuningRes, p5Res, overviewRes] = await Promise.all([
      api.get('/api/v1/health/devices', { params }),
      api.get('/api/v1/health/capacity-baseline'),
      api.get('/api/v1/health/tuning-recommendations'),
      api.get('/api/v1/health/capacity-threshold-template'),
      api.get('/api/v1/health/overview').catch(() => ({ data: null }))
    ])
    healthData.value = devicesRes.data
    capacityBaseline.value = baselineRes.data || capacityBaseline.value
    tuningRecommendations.value = tuningRes.data || tuningRecommendations.value
    p5Template.value = p5Res.data || p5Template.value
    if (overviewRes.data) healthOverview.value = overviewRes.data
    evaluateRiskAlert()
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const onSelectionChange = (rows: DeviceHealth[]) => {
  selectedRows.value = rows
}

const applyRecommendations = async (payload: Record<string, unknown>, tip: string) => {
  applying.value = true
  try {
    const res = await api.post('/api/v1/health/apply-recommendations', payload)
    const data = res.data as { matched: number; would_apply: number; applied: number; results: ApplyResult[] }
    ElMessage.success(t('healthPage.applyExecuted', { tip, matched: data.matched, wouldApply: data.would_apply, applied: data.applied }))
    await fetchData()
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    applying.value = false
  }
}

const applySelectedRecommendations = async () => {
  const deviceIds = selectedRows.value.map(item => item.device_id)
  if (deviceIds.length === 0) {
    ElMessage.warning(t('healthPage.pleaseSelectDevice'))
    return
  }
  try {
    await ElMessageBox.confirm(t('healthPage.confirmApplySelected', { count: deviceIds.length }), t('healthPage.confirmAction'), {
      confirmButtonText: t('common.ok'),
      cancelButtonText: t('healthPage.cancel'),
      type: 'warning'
    })
    await applyRecommendations({ device_ids: deviceIds, only_diff: true }, t('healthPage.applyBySelected'))
  } catch { /* cleanup: ignore */ }
}

const applyHighRiskRecommendations = async () => {
  try {
    await ElMessageBox.confirm(t('healthPage.confirmApplyHighRisk'), t('healthPage.confirmAction'), {
      confirmButtonText: t('common.ok'),
      cancelButtonText: t('healthPage.cancel'),
      type: 'warning'
    })
    await applyRecommendations({ risk_level: 'high', only_diff: true }, t('healthPage.applyByHighRisk'))
  } catch { /* cleanup: ignore */ }
}

const previewRecommendations = async () => {
  applying.value = true
  try {
    const payload: Record<string, unknown> = {
      dry_run: true,
      only_diff: filters.value.only_diff
    }
    if (filters.value.risk_level) payload.risk_level = filters.value.risk_level
    if (filters.value.min_failure_rate > 0) payload.min_failure_rate = filters.value.min_failure_rate
    const res = await api.post('/api/v1/health/apply-recommendations', payload)
    const data = res.data as { matched: number; would_apply: number; results: ApplyResult[] }
    const previewIds = data.results.filter(item => item.would_apply).slice(0, 5).map(item => item.device_id).join(', ')
    ElNotification({
      title: t('healthPage.previewResultTitle'),
      type: data.would_apply > 0 ? 'warning' : 'success',
      message: data.would_apply > 0
        ? t('healthPage.previewMatchedWithChange', { matched: data.matched, wouldApply: data.would_apply, sample: previewIds || t('healthPage.none') })
        : t('healthPage.previewMatchedNoChange', { matched: data.matched })
    })
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    applying.value = false
  }
}

const previewDailyReport = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/health/report/daily', { params: { top_limit: 5 } })
    const data = res.data as {
      total_devices: number
      high_risk: number
      medium_risk: number
      low_risk: number
      would_apply: number
      top_risky: Array<{ device_id: string }>
    }
    const topIds = data.top_risky.map(item => item.device_id).join(', ')
    ElNotification({
      title: t('healthPage.dailyReportTitle'),
      type: data.high_risk > 0 ? 'warning' : 'success',
      message: t('healthPage.dailyReportMessage', { total: data.total_devices, high: data.high_risk, medium: data.medium_risk, low: data.low_risk, wouldApply: data.would_apply, top: topIds || t('healthPage.none') })
    })
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const previewP5Template = async () => {
  loading.value = true
  try {
    const data = p5Template.value
    const target = data.performance_target || {}
    ElNotification({
      title: t('healthPage.p5TemplateTitle'),
      type: 'info',
      message: t('healthPage.p5TemplateMessage', { fleetSize: data.fleet_size, profile: data.profile, concurrency: data.recommended_concurrency, snapshotP95: target.snapshot_p95_ms || '-', firstFrameP95: target.play_first_frame_p95_ms || '-' })
    })
  } finally {
    loading.value = false
  }
}

const downloadDailyReportCsv = () => {
  const url = '/api/v1/health/report/daily.csv'
  const link = document.createElement('a')
  link.href = url
  link.target = '_blank'
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const exportCurrentCsv = () => {
  const columns = [
    ['Device ID', 'device_id'],
    ['Name', 'device_name'],
    ['Risk', 'risk_level'],
    ['Current Policy', 'current_policy_mode'],
    ['Recommended', 'recommended_mode'],
    ['Failure Rate', 'failure_rate'],
    ['Consecutive Failures', 'consecutive_failures'],
    ['Auto Switches', 'auto_switch_count'],
    ['Reason', 'recommend_reason'],
    ['Updated At', 'updated_at']
  ] as Array<[string, keyof DeviceHealth]>
  const header = columns.map(item => item[0]).join(',')
  const body = healthData.value.map(row => {
    return columns.map(([, key]) => {
      const value = row[key]
      const text = value === null || value === undefined ? '' : String(value)
      return `"${text.replace(/"/g, '""')}"`
    }).join(',')
  }).join('\n')
  const csv = `${header}\n${body}`
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `health-dashboard-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  ElMessage.success(t('healthPage.exportedRecords', { count: healthData.value.length }))
}

const clearRefreshTimer = () => {
  if (refreshTimer.value !== null) {
    window.clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

const onAutoRefreshChange = () => {
  clearRefreshTimer()
  const interval = Number(autoRefresh.value)
  if (interval > 0) {
    refreshTimer.value = window.setInterval(() => {
      fetchData()
    }, interval * 1000)
  }
}

const resetFilters = async () => {
  filters.value = {
    risk_level: null,
    min_failure_rate: 0,
    current_policy_mode: null,
    only_diff: false
  }
}

const evaluateRiskAlert = () => {
  if (!alertConfig.value.enabled) {
    highRiskFirstSeenAt.value = null
    return
  }
  const highRiskCount = healthData.value.filter(item => item.risk_level === 'high').length
  if (highRiskCount < alertConfig.value.highRiskThreshold) {
    highRiskFirstSeenAt.value = null
    return
  }
  const now = Date.now()
  if (highRiskFirstSeenAt.value === null) {
    highRiskFirstSeenAt.value = now
    return
  }
  const holdMs = alertConfig.value.holdMinutes * 60 * 1000
  if (now - highRiskFirstSeenAt.value < holdMs) {
    return
  }
  if (now < alertCooldownUntil.value) {
    return
  }
  alertCooldownUntil.value = now + 10 * 60 * 1000
  ElNotification({
    title: t('healthPage.highRiskAlertTitle'),
    type: 'error',
    duration: 0,
    message: t('healthPage.highRiskAlertMessage', { count: highRiskCount })
  })
}

const calculateSuccessRate = (row: DeviceHealth) => {
  const total = row.success_total + row.fail_total
  if (total === 0) return 0
  return Math.round((row.success_total / total) * 100)
}

const sortBySuccessRate = (a: DeviceHealth, b: DeviceHealth) => {
  return calculateSuccessRate(a) - calculateSuccessRate(b)
}

const getProgressStatus = (row: DeviceHealth) => {
  const rate = calculateSuccessRate(row)
  if (rate >= 90) return 'success'
  if (rate >= 70) return 'warning'
  return 'exception'
}

const getModeTagType = (mode: string | null) => {
  if (!mode) return 'info'
  if (mode === 'UDP') return 'success'
  if (mode.includes('TCP')) return 'warning'
  return ''
}

const getStatusTagType = (code: number | null) => {
  if (!code) return 'info'
  if (code >= 200 && code < 300) return 'success'
  if (code >= 400) return 'danger'
  return 'warning'
}

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-'
  const value = new Date(dateStr)
  if (Number.isNaN(value.getTime())) return '-'
  return value.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  const saved = localStorage.getItem('health_alert_config')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (parsed && typeof parsed === 'object') {
        alertConfig.value = {
          ...alertConfig.value,
          ...(parsed as Record<string, unknown>)
        }
      }
    } catch {
      // ignore
    }
  }
  fetchData()
})

watch(filters, () => {
  fetchData()
}, { deep: true })

watch(alertConfig, (value) => {
  localStorage.setItem('health_alert_config', JSON.stringify(value))
  evaluateRiskAlert()
}, { deep: true })

onBeforeUnmount(() => {
  clearRefreshTimer()
})
</script>

<style scoped></style>
