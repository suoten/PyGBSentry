<template>
  <div class="min-h-screen p-3 space-y-3">
    <div v-if="loadingConfig" class="flex justify-center py-12">
      <el-icon class="is-loading text-2xl" style="color: var(--el-text-color-secondary)"><Loading /></el-icon>
    </div>
    <template v-else>
    <el-card shadow="never">
      <div class="flex justify-between items-center gap-2">
        <div>
          <div class="font-semibold" style="color: var(--el-text-color-primary)">行为识别</div>
          <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
            当前状态：
            <span :class="statusColorClass">{{ statusText }}</span>
          </div>
        </div>
        <el-switch v-model="enabled" active-text="启用" inactive-text="停用" @change="onToggleEnabled" />
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="flex justify-between items-center mb-2">
        <div class="font-semibold text-sm" style="color: var(--el-text-color-primary)">回调配置</div>
        <el-button size="small" @click="openConfigDialog">编辑</el-button>
      </div>
      <div class="text-xs space-y-1" style="color: var(--el-text-color-secondary)">
        <div>回调地址：{{ config.ai_callback_url || '未配置' }}</div>
        <div>是否推送截图 URL：{{ config.send_snapshot_url ? '是' : '否' }}</div>
        <div>同步通知地址：{{ formatSyncUrls(config.sync_urls) || '未配置' }}</div>
        <div>请求超时：{{ config.timeout_seconds || 10 }} 秒</div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="flex justify-between items-center mb-2">
        <div class="font-semibold text-sm" style="color: var(--el-text-color-primary)">最近推送记录</div>
        <el-button size="small" text @click="loadEvents">刷新</el-button>
      </div>
      <div v-if="loadingEvents" class="text-xs py-4 text-center" style="color: var(--el-text-color-secondary)">加载中...</div>
      <div v-else-if="events.length === 0" class="text-xs py-4 text-center" style="color: var(--el-text-color-secondary)">暂无记录</div>
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

    <AppDialog v-model="configDialogVisible" title="行为识别配置" size="medium">
      <el-form :model="configForm" label-width="90px">
        <el-form-item label="回调地址">
          <el-input v-model="configForm.ai_callback_url" placeholder="http(s)://行为识别分析服务API地址" clearable />
          <div class="text-[11px] mt-1" style="color: var(--el-text-color-secondary)">报警时 POST 到此地址，供外部分析服务接收</div>
        </el-form-item>
        <el-form-item label="同步通知">
          <el-input
            v-model="configForm.sync_urls"
            type="textarea"
            :rows="2"
            placeholder="可选，多地址用逗号分隔"
          />
          <div class="text-[11px] mt-1" style="color: var(--el-text-color-secondary)">同步到上级平台或大数据平台</div>
        </el-form-item>
        <el-form-item label="推送截图">
          <el-switch v-model="configForm.send_snapshot_url" />
        </el-form-item>
        <el-form-item label="请求超时">
          <el-input-number v-model="configForm.timeout_seconds" :min="1" :max="60" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
      </template>
    </AppDialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import AppDialog from '../components/common/AppDialog.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'
import { logger } from '@/utils/logger'

const pluginId = 'behavior_recognition_suite'

const loadingConfig = ref(true)
const enabled = ref(false)
const config = ref<StructuredEvent>({})

const statusText = computed(() => (enabled.value ? '已启用' : '未启用'))
const statusColorClass = computed(() =>
  enabled.value ? 'text-emerald-400 font-medium' : 'text-gray-500'
)

function formatSyncUrls(v: unknown): string {
  if (v == null || v === '') return ''
  if (Array.isArray(v)) return v.filter(Boolean).join(', ')
  return String(v)
}

const configDialogVisible = ref(false)
const configForm = ref<StructuredEvent>({})
const saving = ref(false)

const events = ref<StructuredEvent[]>([])
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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '加载配置失败')
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
    ElMessage.warning('启用时请填写回调地址')
    return
  }
  saving.value = true
  try {
    const payload = { ...configForm.value, enabled: enabled.value }
    await api.put(`/api/v1/plugins/runtime/${pluginId}/config`, { config: payload })
    await loadConfig()
    configDialogVisible.value = false
    ElMessage.success('保存成功')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

async function onToggleEnabled() {
  try {
    await api.put(`/api/v1/plugins/runtime/${pluginId}/config`, {
      config: { enabled: enabled.value }
    })
    ElMessage.success(enabled.value ? '已启用' : '已停用')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '行为识别插件启用/停用配置失败，请检查插件服务连接')
    enabled.value = !enabled.value
  }
}

async function loadEvents() {
  loadingEvents.value = true
  try {
    const res = await api.get('/api/v1/structured/search', { params: { event_type: 'behavior', limit: 50 } })
    events.value = res.data?.items ?? res.data ?? []
  } catch (e) {
    logger.error('加载行为识别事件失败', e)
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

