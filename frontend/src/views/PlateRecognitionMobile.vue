<template>
  <div class="min-h-screen p-3 space-y-3">
    <div v-if="loadingConfig" class="flex justify-center py-12">
      <el-icon class="is-loading text-2xl" style="color: var(--el-text-color-secondary)"><Loading /></el-icon>
    </div>
    <template v-else>
    <el-card shadow="never">
      <div class="flex justify-between items-center gap-2">
        <div>
          <div class="font-semibold" style="color: var(--el-text-color-primary)">{{ t('plateMobile.title') }}</div>
          <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
            {{ t('plateMobile.currentStatus') }}
            <span :class="statusColorClass">{{ statusText }}</span>
          </div>
        </div>
        <el-switch v-model="enabled" :active-text="t('common.enable')" :inactive-text="t('common.disable')" @change="onToggleEnabled" />
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="flex justify-between items-center mb-2">
        <div class="font-semibold text-sm" style="color: var(--el-text-color-primary)">{{ t('plateMobile.callbackConfig') }}</div>
        <el-button size="small" @click="openConfigDialog">{{ t('common.edit') }}</el-button>
      </div>
      <div class="text-xs space-y-1" style="color: var(--el-text-color-secondary)">
        <div>{{ t('plateMobile.callbackUrl') }}：{{ config.ai_callback_url || t('plateMobile.notConfigured') }}</div>
        <div>{{ t('plateMobile.pushSnapshotUrl') }}：{{ config.send_snapshot_url ? t('common.yes') : t('common.no') }}</div>
        <div>{{ t('plateMobile.syncNotifyUrl') }}：{{ formatSyncUrls(config.sync_urls) || t('plateMobile.notConfigured') }}</div>
        <div>{{ t('plateMobile.requestTimeout') }}：{{ config.timeout_seconds || 10 }} {{ t('plateMobile.secondsUnit') }}</div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="flex justify-between items-center mb-2">
        <div class="font-semibold text-sm" style="color: var(--el-text-color-primary)">{{ t('plateMobile.recentPushRecords') }}</div>
        <el-button size="small" text @click="loadEvents">{{ t('common.refresh') }}</el-button>
      </div>
      <div v-if="loadingEvents" class="text-xs py-4 text-center" style="color: var(--el-text-color-secondary)">{{ t('common.loading') }}</div>
      <div v-else-if="events.length === 0" class="text-xs py-4 text-center" style="color: var(--el-text-color-secondary)">{{ t('plateMobile.noRecords') }}</div>
      <el-timeline v-else class="max-h-[60vh] overflow-auto pr-1">
        <el-timeline-item
          v-for="item in events"
          :key="item.id"
          :timestamp="item.time"
          :type="item.ok ? 'success' : 'danger'"
        >
          <div class="text-xs truncate" style="color: var(--el-text-color-regular)" :title="item.summary">{{ item.summary }}</div>
          <div class="text-[11px] mt-1" style="color: var(--el-text-color-secondary)">
            {{ item.detail }}
          </div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <AppDialog v-model="configDialogVisible" :title="t('plateMobile.configTitle')" size="medium">
      <el-form :model="configForm" label-width="90px">
        <el-form-item :label="t('plateMobile.callbackUrl')">
          <el-input v-model="configForm.ai_callback_url" :placeholder="t('plateMobile.callbackUrlPlaceholder')" clearable />
          <div class="text-[11px] mt-1" style="color: var(--el-text-color-secondary)">{{ t('plateMobile.callbackUrlTip') }}</div>
        </el-form-item>
        <el-form-item :label="t('plateMobile.syncNotify')">
          <el-input
            v-model="configForm.sync_urls"
            type="textarea"
            :rows="2"
            :placeholder="t('plateMobile.syncNotifyPlaceholder')"
          />
          <div class="text-[11px] mt-1" style="color: var(--el-text-color-secondary)">{{ t('plateMobile.syncNotifyTip') }}</div>
        </el-form-item>
        <el-form-item :label="t('plateMobile.pushSnapshot')">
          <el-switch v-model="configForm.send_snapshot_url" />
        </el-form-item>
        <el-form-item :label="t('plateMobile.requestTimeout')">
          <el-input-number v-model="configForm.timeout_seconds" :min="1" :max="60" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">{{ t('common.save') }}</el-button>
      </template>
    </AppDialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loading } from '@element-plus/icons-vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import AppDialog from '../components/common/AppDialog.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, MaintenanceRecord, StructuredEvent, PluginConfig } from '@/types/models'
import { logger } from '@/utils/logger'

interface MobilePluginConfig {
  ai_callback_url?: string
  sync_urls?: string
  send_snapshot_url?: boolean
  timeout_seconds?: number
  enabled?: boolean
}

interface PluginPushEvent {
  id: string
  time?: string
  ok?: boolean
  summary?: string
  detail?: string
}

const { t } = useI18n()

const pluginId = 'plate_recognition_suite'

const loadingConfig = ref(true)
const enabled = ref(false)
const config = ref<MobilePluginConfig>({})

const statusText = computed(() => (enabled.value ? t('plateMobile.enabled') : t('plateMobile.notEnabled')))
const statusColorClass = computed(() =>
  enabled.value ? 'text-emerald-400 font-medium' : 'text-gray-500'
)

function formatSyncUrls(v: unknown): string {
  if (v == null || v === '') return ''
  if (Array.isArray(v)) return v.filter(Boolean).join(', ')
  return String(v)
}

const configDialogVisible = ref(false)
const configForm = ref<MobilePluginConfig>({})
const saving = ref(false)

const events = ref<PluginPushEvent[]>([])
const loadingEvents = ref(false)

async function loadConfig() {
  loadingConfig.value = true
  try {
    const res = await api.get(`/api/v1/plugins/runtime/${pluginId}/config`)
    const cfg = (res.data?.config && typeof res.data.config === 'object') ? res.data.config : {}
    enabled.value = !!cfg.enabled
    config.value = cfg
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || t('plateMobile.loadConfigFailed'))
  } finally {
    loadingConfig.value = false
  }
}

function openConfigDialog() {
  const c = config.value || {}
  configForm.value = {
    ai_callback_url: c.ai_callback_url || '',
    sync_urls: c.sync_urls || '',
    send_snapshot_url: !!c.send_snapshot_url,
    timeout_seconds: c.timeout_seconds || 10
  }
  configDialogVisible.value = true
}

async function saveConfig() {
  if (enabled.value && !(configForm.value.ai_callback_url || '').trim()) {
    ElMessage.warning(t('plateMobile.callbackUrlRequired'))
    return
  }
  saving.value = true
  try {
    const payload = { ...configForm.value, enabled: enabled.value }
    await api.put(`/api/v1/plugins/runtime/${pluginId}/config`, { config: payload })
    await loadConfig()
    configDialogVisible.value = false
    ElMessage.success(t('common.saveSuccess'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || t('plateMobile.saveFailedRetry'))
  } finally {
    saving.value = false
  }
}

async function onToggleEnabled() {
  try {
    await api.put(`/api/v1/plugins/runtime/${pluginId}/config`, {
      config: { enabled: enabled.value }
    })
    ElMessage.success(enabled.value ? t('plateMobile.enabled') : t('plateMobile.disabled'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || t('plateMobile.toggleFailed'))
    enabled.value = !enabled.value
  }
}

async function loadEvents() {
  loadingEvents.value = true
  try {
    const res = await api.get('/api/v1/structured/search', { params: { event_type: 'plate', limit: 50 } })
    events.value = res.data?.items ?? res.data ?? []
  } catch (e) {
    logger.error('加载车牌识别事件失败', e)
    events.value = []
  } finally {
    loadingEvents.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  await loadEvents()
})
</script>

