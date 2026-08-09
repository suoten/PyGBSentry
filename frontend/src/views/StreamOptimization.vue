<template>
  <div class="space-y-4">
    <el-card class="app-surface">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-semibold">{{ t('streamOptimization.configTitle') }}</div>
        </div>
      </template>

      <el-form :model="playConfig" label-width="120px" class="max-w-2xl">
        <el-form-item :label="t('streamOptimization.protocolPreference')">
          <el-select v-model="playConfig.protocol_preference">
            <el-option :label="t('streamOptimization.autoSelect')" value="auto" />
            <el-option :label="t('streamOptimization.httpFlvRecommended')" value="flv" />
            <el-option label="HLS" value="hls" />
            <el-option label="WebRTC" value="webrtc" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('streamOptimization.qualityMode')">
          <el-select v-model="playConfig.quality_mode">
            <el-option :label="t('streamOptimization.qualityHigh')" value="high" />
            <el-option :label="t('streamOptimization.qualityBalance')" value="balance" />
            <el-option :label="t('streamOptimization.qualityStable')" value="stable" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('streamOptimization.linePreference')">
          <el-select v-model="playConfig.preferred_line">
            <el-option :label="t('streamOptimization.lineAuto')" value="auto" />
            <el-option :label="t('streamOptimization.lineMain')" value="main" />
            <el-option :label="t('streamOptimization.lineSub')" value="sub" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('streamOptimization.tcpFallback')">
          <el-switch v-model="playConfig.enable_tcp_fallback" :active-text="t('streamOptimization.enable')" :inactive-text="t('streamOptimization.disable')" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="app-surface">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-semibold">{{ t('streamOptimization.protocolInfo') }}</div>
          <el-button size="small" @click="loadProtocolInfo" :loading="protocolLoading">{{ t('streamOptimization.refresh') }}</el-button>
        </div>
      </template>
      <el-table :data="protocols" v-loading="protocolLoading" stripe size="small">
        <el-table-column prop="name" :label="t('streamOptimization.protocol')" width="120" />
        <el-table-column prop="description" :label="t('streamOptimization.description')" min-width="260" />
        <el-table-column prop="latency" :label="t('streamOptimization.latency')" width="80" />
        <el-table-column prop="compatibility" :label="t('streamOptimization.compatibility')" width="80" />
        <el-table-column prop="buffer_recommend" :label="t('streamOptimization.recommendedBuffer')" width="140" />
        <el-table-column label="HTTPS" width="80">
          <template #default="{ row }">
            <el-tag :type="row.requires_https ? 'warning' : 'success'" size="small">
              {{ row.requires_https ? t('streamOptimization.required') : t('streamOptimization.notRequired') }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="protocolRecommendation" class="mt-3 text-sm text-gray-600">
        <el-icon class="mr-1"><InfoFilled /></el-icon>
        {{ protocolRecommendation }}
      </div>
    </el-card>

    <el-card class="app-surface">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-semibold">{{ t('streamOptimization.healthMonitor') }}</div>
          <div class="flex gap-2">
            <el-input v-model="healthSessionId" :placeholder="t('streamOptimization.inputSessionId')" size="small" style="width: 240px" clearable />
            <el-button size="small" type="primary" @click="checkHealth" :loading="healthLoading" :disabled="!healthSessionId.trim()">
              {{ t('streamOptimization.queryHealthStatus') }}
            </el-button>
          </div>
        </div>
      </template>
      <div v-if="healthData" class="space-y-3">
        <div class="flex flex-wrap gap-4">
          <div class="text-center">
            <div class="text-3xl font-bold" :class="healthScoreColor">{{ healthData.health_score?.toFixed(0) }}</div>
            <div class="text-xs text-gray-500">{{ t('streamOptimization.healthScore') }}</div>
          </div>
          <div class="text-center">
            <el-tag :type="healthLevelType" size="large">{{ healthLevelLabel }}</el-tag>
            <div class="text-xs text-gray-500 mt-1">{{ t('streamOptimization.healthLevel') }}</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold">{{ healthData.fps?.toFixed(1) }}</div>
            <div class="text-xs text-gray-500">FPS</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold">{{ healthData.bitrate_kbps?.toFixed(0) }}</div>
            <div class="text-xs text-gray-500">{{ t('streamOptimization.bitrateKbps') }}</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold">{{ healthData.packet_loss_rate?.toFixed(4) }}</div>
            <div class="text-xs text-gray-500">{{ t('streamOptimization.packetLossRate') }}</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold">{{ healthData.buffer_ms?.toFixed(0) }}</div>
            <div class="text-xs text-gray-500">{{ t('streamOptimization.bufferMs') }}</div>
          </div>
          <div class="text-center">
            <div class="text-lg font-semibold">{{ healthData.resolution || '-' }}</div>
            <div class="text-xs text-gray-500">{{ t('streamOptimization.resolution') }}</div>
          </div>
        </div>
        <div v-if="healthData.recommendations?.length">
          <div class="font-medium text-sm mb-2">{{ t('streamOptimization.optimizationSuggestions') }}</div>
          <ul class="list-disc list-inside text-sm text-gray-600 space-y-1">
            <li v-for="(rec, idx) in healthData.recommendations" :key="idx">{{ rec }}</li>
          </ul>
        </div>
      </div>
      <el-empty v-else :description="t('streamOptimization.healthEmptyDesc')" :image-size="60" />
    </el-card>

    <el-card class="app-surface">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-semibold">{{ t('streamOptimization.streamStats') }}</div>
          <el-button size="small" @click="loadStats" :loading="statsLoading">{{ t('streamOptimization.refresh') }}</el-button>
        </div>
      </template>
      <div v-if="statsData" class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="text-center p-3 bg-gray-50 rounded">
          <div class="text-2xl font-bold text-blue-600">{{ statsData.active_sessions ?? 0 }}</div>
          <div class="text-xs text-gray-500">{{ t('streamOptimization.activeSessions') }}</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded">
          <div class="text-2xl font-bold text-green-600">{{ statsData.total_sessions ?? 0 }}</div>
          <div class="text-xs text-gray-500">{{ t('streamOptimization.totalSessions') }}</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded">
          <div class="text-2xl font-bold text-orange-600">{{ statsData.reconnect_count ?? 0 }}</div>
          <div class="text-xs text-gray-500">{{ t('streamOptimization.reconnectCount') }}</div>
        </div>
        <div class="text-center p-3 bg-gray-50 rounded">
          <div class="text-2xl font-bold text-purple-600">{{ statsData.avg_health_score?.toFixed(0) ?? '-' }}</div>
          <div class="text-xs text-gray-500">{{ t('streamOptimization.avgHealthScore') }}</div>
        </div>
      </div>
      <el-empty v-else :description="t('streamOptimization.statsEmptyDesc')" :image-size="60" />
    </el-card>

    <el-card class="app-surface">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-semibold">{{ t('streamOptimization.playOptimizationTips') }}</div>
          <el-button size="small" @click="loadTips" :loading="tipsLoading">{{ t('streamOptimization.refresh') }}</el-button>
        </div>
      </template>
      <el-collapse v-if="tips.length" v-model="activeTipCategories">
        <el-collapse-item v-for="category in tips" :key="category.category" :title="category.category" :name="category.category">
          <div class="space-y-3">
            <div v-for="(item, idx) in category.items" :key="idx" class="p-3 bg-gray-50 rounded">
              <div class="font-medium text-sm">{{ item.title }}</div>
              <div class="text-sm text-gray-600 mt-1">{{ item.description }}</div>
              <div class="text-xs text-gray-400 mt-1">{{ t('streamOptimization.applicable') }}{{ item.applicable }}</div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else :description="t('streamOptimization.tipsEmptyDesc')" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n' // FIXED: 国际化
import { streamOptApi } from '@/api'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { getApiErrorMessage } from '@/utils/errorMessage'

const { t } = useI18n() // FIXED: 国际化

const playConfig = ref({
  protocol_preference: 'auto',
  quality_mode: 'balance',
  preferred_line: 'auto',
  enable_tcp_fallback: true,
})

const protocolLoading = ref(false)
const protocols = ref<any[]>([])
const protocolRecommendation = ref('')

async function loadProtocolInfo() {
  protocolLoading.value = true
  try {
    const res = await streamOptApi.getProtocolInfo()
    protocols.value = res.data?.protocols || []
    protocolRecommendation.value = res.data?.recommendation || ''
  } catch {
    ElMessage.error(t('streamOptimization.loadProtocolInfoFailed'))
  } finally {
    protocolLoading.value = false
  }
}

const healthSessionId = ref('')
const healthLoading = ref(false)
const healthData = ref<any>(null)

const healthScoreColor = computed(() => {
  const s = healthData.value?.health_score ?? 0
  if (s >= 80) return 'text-green-600'
  if (s >= 60) return 'text-yellow-600'
  if (s >= 40) return 'text-orange-600'
  return 'text-red-600'
})

const healthLevelType = computed(() => {
  const l = healthData.value?.health_level || ''
  if (l === 'excellent' || l === 'healthy') return 'success'
  if (l === 'degraded') return 'warning'
  return 'danger'
})

const healthLevelLabel = computed(() => {
  const map: Record<string, string> = {
    excellent: t('streamOptimization.healthExcellent'),
    healthy: t('streamOptimization.healthHealthy'),
    degraded: t('streamOptimization.healthDegraded'),
    poor: t('streamOptimization.healthPoor'),
    critical: t('streamOptimization.healthCritical'),
  }
  return map[healthData.value?.health_level] || healthData.value?.health_level || '-'
})

async function checkHealth() {
  if (!healthSessionId.value.trim()) return
  healthLoading.value = true
  try {
    const res = await streamOptApi.getHealth(healthSessionId.value.trim())
    healthData.value = res.data
  } catch (e: any) {
    healthData.value = null
    const msg = getApiErrorMessage(e, t('streamOptimization.queryHealthFailed'))
    ElMessage.error(msg)
  } finally {
    healthLoading.value = false
  }
}

const statsLoading = ref(false)
const statsData = ref<any>(null)

async function loadStats() {
  statsLoading.value = true
  try {
    const res = await streamOptApi.getStats()
    statsData.value = res.data
  } catch {
    ElMessage.error(t('streamOptimization.loadStatsFailed'))
  } finally {
    statsLoading.value = false
  }
}

const tipsLoading = ref(false)
const tips = ref<any[]>([])
const activeTipCategories = ref<string[]>([])

async function loadTips() {
  tipsLoading.value = true
  try {
    const res = await streamOptApi.getOptimizationTips()
    tips.value = res.data?.tips || []
    activeTipCategories.value = tips.value.map((c: any) => c.category)
  } catch {
    ElMessage.error(t('streamOptimization.loadTipsFailed'))
  } finally {
    tipsLoading.value = false
  }
}

onMounted(() => {
  loadProtocolInfo()
  loadTips()
})
</script>
