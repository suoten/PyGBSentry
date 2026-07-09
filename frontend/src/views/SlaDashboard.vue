<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('sla.title')" :description="t('sla.description')">
          <template #actions>
            <el-button size="small" @click="refreshAll" :loading="loading">
              <el-icon class="mr-1"><Refresh /></el-icon>
              {{ t('common.refresh') }}
            </el-button>
          </template>
        </PageHeader>
      </template>

      <!-- SLA KPI Cards -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
        <el-card shadow="hover" class="sla-kpi-card">
          <div class="sla-kpi-label">{{ t('sla.totalOpen') }}</div>
          <div class="sla-kpi-value" :style="{ color: sla.total_open > 0 ? 'var(--el-color-warning)' : 'var(--el-color-success)' }">
            {{ sla.total_open }}
          </div>
        </el-card>
        <el-card shadow="hover" class="sla-kpi-card">
          <div class="sla-kpi-label">{{ t('sla.escalatedOpen') }}</div>
          <div class="sla-kpi-value" :style="{ color: sla.escalated_open > 0 ? 'var(--el-color-danger)' : 'var(--el-color-success)' }">
            {{ sla.escalated_open }}
          </div>
        </el-card>
        <el-card shadow="hover" class="sla-kpi-card">
          <div class="sla-kpi-label">{{ t('sla.overdueOpen') }}</div>
          <div class="sla-kpi-value" :style="{ color: sla.overdue_open > 0 ? 'var(--el-color-danger)' : 'var(--el-color-success)' }">
            {{ sla.overdue_open }}
          </div>
        </el-card>
        <el-card shadow="hover" class="sla-kpi-card">
          <div class="sla-kpi-label">{{ t('sla.acknowledgedToday') }}</div>
          <div class="sla-kpi-value" style="color: var(--el-color-success)">{{ sla.acknowledged_today }}</div>
        </el-card>
        <el-card shadow="hover" class="sla-kpi-card">
          <div class="sla-kpi-label">{{ t('sla.avgAckTime') }}</div>
          <div class="sla-kpi-value">{{ sla.avg_ack_minutes_today?.toFixed(1) || '0.0' }} {{ t('sla.minutes') }}</div>
        </el-card>
      </div>

      <!-- Alert Trend Comparison -->
      <el-card shadow="never" class="mb-4">
        <template #header>
          <span class="font-semibold">{{ t('sla.compareTitle') }}</span>
          <el-radio-group v-model="compareDays" size="small" class="ml-4" @change="fetchCompare">
            <el-radio-button :value="7">7d</el-radio-button>
            <el-radio-button :value="14">14d</el-radio-button>
            <el-radio-button :value="30">30d</el-radio-button>
          </el-radio-group>
        </template>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="sla-compare-box">
            <div class="sla-compare-label">{{ t('sla.currentPeriod') }} ({{ compare.days }}d)</div>
            <div class="sla-compare-value">{{ compare.period_current }}</div>
            <div class="sla-compare-sub">vs {{ t('sla.previousPeriod') }}: {{ compare.period_previous }}</div>
          </div>
          <div class="sla-compare-box">
            <div class="sla-compare-label">{{ t('sla.currentPeriod') }} (1d)</div>
            <div class="sla-compare-value">{{ compare.day_current }}</div>
            <div class="sla-compare-sub">vs {{ t('sla.previousPeriod') }}: {{ compare.day_previous }}</div>
          </div>
          <div class="sla-compare-box">
            <div class="sla-compare-label">{{ t('sla.changeRate') }}</div>
            <div class="sla-compare-value" :style="{ color: compare.period_change_pct > 0 ? 'var(--el-color-danger)' : 'var(--el-color-success)' }">
              {{ compare.period_change_pct > 0 ? '+' : '' }}{{ compare.period_change_pct?.toFixed(1) || '0.0' }}%
            </div>
            <div class="sla-compare-sub">{{ compare.days }}d {{ t('sla.changeRate') }}</div>
          </div>
        </div>
      </el-card>

      <!-- Quality Analysis -->
      <el-card shadow="never">
        <template #header>
          <span class="font-semibold">{{ t('sla.qualityTitle') }}</span>
        </template>
        <div v-loading="loading">
          <el-table :data="qualityRows" stripe size="small">
            <el-table-column prop="level" :label="t('sla.qualityDistribution')" min-width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="qualityTagType(row.level)">{{ row.level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="Count" width="100" />
            <el-table-column prop="pct" label="%" width="100">
              <template #default="{ row }">
                <el-progress :percentage="row.pct" :color="qualityColor(row.level)" :stroke-width="12" :text-inside="true" />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/utils/http'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import { getFriendlyError } from '../utils/errorMessage'

const { t } = useI18n()

const loading = ref(false)
const compareDays = ref(7)

interface SlaData {
  total_open: number
  escalated_open: number
  overdue_open: number
  acknowledged_today: number
  avg_ack_minutes_today: number
}

interface CompareData {
  days: number
  period_current: number
  period_previous: number
  period_change_pct: number
  day_current: number
  day_previous: number
}

interface QualityRow {
  level: string
  count: number
  pct: number
}

const sla = ref<SlaData>({
  total_open: 0, escalated_open: 0, overdue_open: 0,
  acknowledged_today: 0, avg_ack_minutes_today: 0
})

const compare = ref<CompareData>({
  days: 7, period_current: 0, period_previous: 0,
  period_change_pct: 0, day_current: 0, day_previous: 0
})

const qualityRows = ref<QualityRow[]>([])

const fetchSla = async () => {
  try {
    const res = await api.get('/api/v1/alarms/sla/overview')
    sla.value = { ...sla.value, ...res.data }
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const fetchCompare = async () => {
  try {
    const res = await api.get('/api/v1/alarms/sla/compare', { params: { days: compareDays.value } })
    compare.value = { ...compare.value, ...res.data }
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const fetchQuality = async () => {
  try {
    const res = await api.get('/api/v1/alarms/sla/quality')
    const d = res.data || {}
    const levels = ['critical', 'major', 'minor', 'info']
    const raw = levels.map(l => ({ level: l, count: Number(d[`${l}_count`] || d[l] || 0) }))
    const total = raw.reduce((s, r) => s + r.count, 0)
    qualityRows.value = raw.map(r => ({ ...r, pct: total > 0 ? Math.round((r.count / total) * 100) : 0 }))
  } catch (e: unknown) {
    const f = getFriendlyError(e)
    ElMessage.error(f.message)
  }
}

const refreshAll = async () => {
  loading.value = true
  await Promise.allSettled([fetchSla(), fetchCompare(), fetchQuality()])
  loading.value = false
}

const qualityTagType = (level: string) => {
  if (level === 'critical') return 'danger'
  if (level === 'major') return 'warning'
  if (level === 'minor') return 'info'
  return 'success'
}

const qualityColor = (level: string) => {
  if (level === 'critical') return '#f56c6c'
  if (level === 'major') return '#e6a23c'
  if (level === 'minor') return '#909399'
  return '#67c23a'
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.sla-kpi-card {
  text-align: center;
  padding: 8px 0;
}
.sla-kpi-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.sla-kpi-value {
  font-size: 28px;
  font-weight: bold;
}
.sla-compare-box {
  text-align: center;
  padding: 16px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}
.sla-compare-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.sla-compare-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}
.sla-compare-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
