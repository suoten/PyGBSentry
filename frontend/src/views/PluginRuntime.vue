<template>
  <div class="plugin-runtime h-full flex flex-col">
    <div v-if="loading" class="flex-1 flex items-center justify-center" style="color: var(--el-text-color-secondary)">
      加载中...
    </div>
    <template v-else>
      <div v-show="iframeUrl" class="flex-1 min-h-0 flex flex-col overflow-hidden">
        <iframe
          :src="iframeUrl"
          :class="
            isEmbedOpsSplitIframe
              ? 'w-full flex-1 min-h-[38vh] border-0 rounded-lg'
              : 'w-full h-full border-0 rounded-lg'
          "
          title="插件运行页"
        />
        <TableCard
          v-if="isEmbedOpsSplitIframe"
          class="flex-shrink-0 !rounded-none border-t border-[var(--el-border-color)] max-h-[52vh] flex flex-col overflow-hidden"
        >
          <template #header>
            <span class="text-sm font-medium" style="color: var(--el-text-color-primary)">运维数据</span>
          </template>
          <div id="plugin-runtime-embed-anchor" class="min-h-0 max-h-[calc(52vh-3.5rem)] overflow-auto"></div>
        </TableCard>
        <div
          v-else-if="iframeUrl"
          id="plugin-runtime-embed-anchor"
          class="sr-only"
          aria-hidden="true"
        ></div>
      </div>
      <div v-show="!iframeUrl" class="min-h-screen">
        <PageContainer>
          <template #header>
            <PageHeader
              :title="pluginTitle"
              :description="showConfigForm ? '插件配置（运行时）' : '插件已安装（后端能力为主）'"
            />
          </template>
          <TableCard>
            <template v-if="!showConfigForm">
              <div style="color: var(--el-text-color-regular)">{{ runtimeMessage }}</div>
              <div class="mt-4">
                <el-button type="primary" @click="router.push('/plugins')">{{ pluginCenterActionLabel }}</el-button>
              </div>
            </template>
            <template v-else>
              <el-alert v-if="configError" :title="configError" type="error" show-icon />
              <el-alert
                v-if="!configError && runtimeSaveSuccessMessage"
                :title="runtimeSaveSuccessMessage"
                type="success"
                show-icon
                :closable="true"
                class="mb-4"
                @close="clearRuntimeSaveSuccess()"
              >
                <template #default>
                  <div class="mt-2 flex flex-wrap gap-3">
                    <el-button size="small" type="primary" @click="router.push('/plugins')">返回插件中心</el-button>
                    <el-button
                      v-if="runtimeSaveQuickActionLabel"
                      size="small"
                      :loading="runtimeSaveQuickActionLoading"
                      @click="performRuntimeSaveQuickAction"
                    >
                      {{ runtimeSaveQuickActionLabel }}
                    </el-button>
                    <el-button
                      v-if="runtimeSaveFollowupRoute"
                      size="small"
                      @click="router.push(runtimeSaveFollowupRoute)"
                    >
                      {{ runtimeSaveFollowupLabel }}
                    </el-button>
                  </div>
                </template>
              </el-alert>

              <el-form
                ref="runtimeFormRef"
                v-if="!configError"
                :model="runtimeConfig"
                label-width="160px"
                size="small"
                :disabled="loadingConfig || savingConfig"
              >
              <el-form-item v-if="runtimeFields.length === 0" :label="t('common.status')">
                <span style="color: var(--el-text-color-secondary)">{{ runtimeMessage }}</span>
              </el-form-item>

              <template v-for="f in runtimeFields" :key="String(f.key)">
                <el-form-item
                  :label="f.label || f.key"
                  :data-runtime-field-key="String(f.key)"
                  :class="{ 'runtime-field--focus': focusedRuntimeFieldKey === String(f.key) }"
                >
                  <el-switch
                    v-if="String(f.type || '').toLowerCase() === 'bool'"
                    v-model="runtimeConfig[f.key]"
                  />

                  <el-input-number
                    v-else-if="['number','int','float'].includes(String(f.type || '').toLowerCase())"
                    v-model="runtimeConfig[f.key]"
                    :min="typeof f.min === 'number' ? f.min : undefined"
                    :max="typeof f.max === 'number' ? f.max : undefined"
                  />

                  <el-input
                    v-else-if="['password','secret'].includes(String(f.type || '').toLowerCase())"
                    v-model="runtimeConfig[f.key]"
                    type="password"
                    show-password
                    clearable
                  />

                  <el-input
                    v-else-if="String(f.type || '').toLowerCase() === 'json'"
                    v-model="jsonText[String(f.key)]"
                    type="textarea"
                    :rows="6"
                    clearable
                  />

                  <el-input v-else v-model="runtimeConfig[f.key]" clearable />
                </el-form-item>
              </template>

              <div class="flex gap-3 mt-3">
                <el-button
                  ref="saveConfigButtonRef"
                  type="primary"
                  :loading="savingConfig"
                  :class="{ 'runtime-save-button--highlight': highlightSaveConfigButton }"
                  @click="saveRuntimeConfig"
                >
                  保存配置
                </el-button>
              </div>
              </el-form>
            </template>

            <div id="plugin-runtime-page-anchor"></div>
            <Teleport :to="teleportTarget">
              <PluginPanels
                :plugin-id="pluginId"
                @focus-config-field="focusRuntimeFieldByKey"
                @retry-alert-test="triggerAlertChannelTest"
              />
            </Teleport>
          </TableCard>
        </PageContainer>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onActivated, reactive, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRoute, useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage, ElForm, ElButton } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import PluginPanels from '../components/plugin/PluginPanels.vue'
import { getFriendlyError, getApiErrorMessage } from '../utils/errorMessage'
// 无需商城跳转
import { useActivatedRefreshOnce } from '../composables/useActivatedRefreshOnce'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const route = useRoute()
const { t } = useI18n()  // FIXED: 国际化
const router = useRouter()
const pluginId = computed(() => String(route.params.pluginId || ''))
const pluginDisplayName = ref<string>('')
const pluginTitle = computed(() => `插件运行页 - ${pluginDisplayName.value || pluginId.value}`)

const loading = ref(true)
const iframeUrl = ref('')
const runtimeMessage = ref('')
const shopUrl = ref('')
const showConfigForm = ref(false)
const purchasedPluginIds = ref<string[]>([])
const installedPluginIds = ref<string[]>([])
const isS3SyncPlugin = computed(() => pluginId.value === 's3_sync')
type RuntimeGuidanceState = 'default' | 'buy' | 'renew' | 'install' | 'upgrade' | 'reinstall' | 'configure'
const runtimeGuidanceState = ref<RuntimeGuidanceState>('default')

/** 带「运维表格」的插件：与 Teleport 包裹范围一致 */
const RUNTIME_EMBED_OPS_PLUGIN_IDS: readonly string[] = [
  'feishu_alert',
  'wecom_alert',
  'sms_alert',
  'network_watchdog',
  'stream_health',
  'sip_logger',
  'stream_idle',
  'timelapse',
  'webhook_pusher',
  's3_sync',
  'ptz_tour',
  'auto_record',
  'record_schedule_executor',
  'record_index_verifier',
  'snapshot_refresh',
  'rtmp_push_channel_monitor',
  'pull_proxy_monitor',
  'mqtt_bridge',
]

const teleportTarget = computed(() =>
  iframeUrl.value ? '#plugin-runtime-embed-anchor' : '#plugin-runtime-page-anchor',
)
const isPluginPurchased = computed(() => purchasedPluginIds.value.includes(pluginId.value))
const isPluginInstalled = computed(() => installedPluginIds.value.includes(pluginId.value))
const pluginCenterActionLabel = computed(() => {
  switch (runtimeGuidanceState.value) {
    case 'install':
      return '返回插件中心安装'
    case 'upgrade':
      return '返回插件中心查看升级'
    case 'reinstall':
      return '返回插件中心重新安装'
    case 'configure':
      return '返回插件中心查看说明'
    default:
      return '返回插件中心'
  }
})

/** 有 iframe 且当前插件有运维表时，缩短上方 iframe 高度 */
const isEmbedOpsSplitIframe = computed(
  () => Boolean(iframeUrl.value) && RUNTIME_EMBED_OPS_PLUGIN_IDS.includes(pluginId.value),
)

type RuntimeField = {
  key: string
  label?: string
  type?: string
  min?: number
  max?: number
}

const runtimeSchema = ref<{ fields?: RuntimeField[] } | null>(null)
const runtimeConfig = reactive<Record<string, unknown>>({})
const jsonText = reactive<Record<string, string>>({})
const loadingConfig = ref(false)
const savingConfig = ref(false)
const configError = ref('')
const runtimeFormRef = ref<InstanceType<typeof ElForm> | null>(null)
const saveConfigButtonRef = ref<InstanceType<typeof ElButton> | null>(null)
const highlightSaveConfigButton = ref(false)
const focusedRuntimeFieldKey = ref('')
let saveConfigHighlightTimer: ReturnType<typeof setTimeout> | null = null
let runtimeFieldHighlightTimer: ReturnType<typeof setTimeout> | null = null
const runtimeSaveSuccessMessage = ref('')
const runtimeSaveFollowupRoute = ref('')
const runtimeSaveFollowupLabel = ref('')
const runtimeSaveQuickActionType = ref<'none' | 'alert_test' | 'refresh_runtime_data'>('none')
const runtimeSaveQuickActionLabel = ref('')
const runtimeSaveQuickActionLoading = ref(false)

const runtimeFields = computed<RuntimeField[]>(() => {
  const fields = runtimeSchema.value?.fields
  return Array.isArray(fields) ? (fields as RuntimeField[]) : []
})

// stream_health runtime special UI
const streamHealthLoading = ref(false)
const streamHealthError = ref('')
const streamHealthRows = ref<PluginRuntimeRow[]>([])
const streamHealthPage = ref(1)
const streamHealthPageSize = ref(10)
const streamHealthAppFilter = ref('')
const streamHealthStreamFilter = ref('')
const streamHealthOnlyLowBitrate = ref(true)
let streamHealthAutoTimer: ReturnType<typeof setInterval> | null = null

function clearStreamHealthAutoRefresh() {
  if (streamHealthAutoTimer) {
    clearInterval(streamHealthAutoTimer)
    streamHealthAutoTimer = null
  }
}


const paginatedStreamHealthRows = computed(() => {
  const start = (streamHealthPage.value - 1) * streamHealthPageSize.value
  const end = start + streamHealthPageSize.value
  return streamHealthRows.value.slice(start, end)
})

watch(() => streamHealthRows.value, () => {
  streamHealthPage.value = 1
})

/** 路由快速切换时丢弃慢请求，避免把上一插件的面板数据写回当前页 */
const isCurrentRuntimePlugin = (id: string) => pluginId.value === id

const fetchStreamHealth = async () => {
  streamHealthLoading.value = true
  streamHealthError.value = ''
  try {
    const params: Record<string, unknown> = {}
    if (streamHealthAppFilter.value) params.app = streamHealthAppFilter.value
    if (streamHealthStreamFilter.value) params.stream = streamHealthStreamFilter.value
    params.only_low_bitrate = !!streamHealthOnlyLowBitrate.value

    const resp = await api.get('/api/v1/plugins/runtime/stream_health/health', { params })
    if (!isCurrentRuntimePlugin('stream_health')) return
    const data = resp?.data || {}
    streamHealthRows.value = Array.isArray(data.rows) ? data.rows : []
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('stream_health')) return
    streamHealthError.value = getApiErrorMessage(e, '拉取健康快照失败')
    streamHealthRows.value = []
  } finally {
    streamHealthLoading.value = false
  }
}

// sip_logger runtime special UI
const sipLogLoading = ref(false)
const sipLogError = ref('')
const sipLogRows = ref<PluginRuntimeRow[]>([])
const sipLogKeyword = ref('')
const sipLogDirection = ref('')
const sipLogProto = ref('')
const sipLogPage = ref(1)
const sipLogPageSize = ref(50)
const sipLogHasMore = ref(false)
const sipTimeRange = ref<[string, string] | null>(null)

const pad2 = (n: number) => String(n).padStart(2, '0')
const formatDateTimeLocal = (d: Date) => {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

const fetchSipLoggerLogs = async () => {
  sipLogLoading.value = true
  sipLogError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: sipLogPage.value,
      page_size: sipLogPageSize.value,
    }
    if (sipTimeRange.value?.[0]) params.start_at = sipTimeRange.value[0]
    if (sipTimeRange.value?.[1]) params.end_at = sipTimeRange.value[1]
    if (sipLogKeyword.value) params.keyword = sipLogKeyword.value
    if (sipLogDirection.value) params.direction = sipLogDirection.value
    if (sipLogProto.value) params.proto = sipLogProto.value

    const resp = await api.get('/api/v1/plugins/runtime/sip_logger/logs', { params })
    if (!isCurrentRuntimePlugin('sip_logger')) return
    const data = resp?.data || {}
    sipLogRows.value = Array.isArray(data.rows) ? data.rows : []
    sipLogHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('sip_logger')) return
    sipLogError.value = getApiErrorMessage(e, '拉取 SIP 日志失败')
    sipLogRows.value = []
    sipLogHasMore.value = false
  } finally {
    sipLogLoading.value = false
  }
}

// network_watchdog runtime special UI
const nwLoading = ref(false)
const nwError = ref('')
const nwRows = ref<PluginRuntimeRow[]>([])
const nwKeyword = ref('')
const nwDevice = ref('')
const nwIp = ref('')
const nwPage = ref(1)
const nwPageSize = ref(50)
const nwHasMore = ref(false)
const nwTimeRange = ref<[string, string] | null>(null)

const fetchNetworkWatchdogEvents = async () => {
  nwLoading.value = true
  nwError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: nwPage.value,
      page_size: nwPageSize.value,
    }
    if (nwTimeRange.value?.[0]) params.start_at = nwTimeRange.value[0]
    if (nwTimeRange.value?.[1]) params.end_at = nwTimeRange.value[1]
    if (nwKeyword.value) params.keyword = nwKeyword.value
    if (nwDevice.value) params.device = nwDevice.value
    if (nwIp.value) params.ip = nwIp.value

    const resp = await api.get('/api/v1/plugins/runtime/network_watchdog/events', { params })
    if (!isCurrentRuntimePlugin('network_watchdog')) return
    const data = resp?.data || {}
    nwRows.value = Array.isArray(data.rows) ? data.rows : []
    nwHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('network_watchdog')) return
    nwError.value = getApiErrorMessage(e, '拉取网络告警失败')
    nwRows.value = []
    nwHasMore.value = false
  } finally {
    nwLoading.value = false
  }
}

// stream_idle：断流事件查询
const siLoading = ref(false)
const siError = ref('')
const siRows = ref<PluginRuntimeRow[]>([])
const siKeyword = ref('')
const siApp = ref('')
const siStream = ref('')
const siNode = ref('')
const siPage = ref(1)
const siPageSize = ref(50)
const siHasMore = ref(false)
const siTimeRange = ref<[string, string] | null>(null)

const fetchStreamIdleEvents = async () => {
  siLoading.value = true
  siError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: siPage.value,
      page_size: siPageSize.value,
    }
    if (siTimeRange.value?.[0]) params.start_at = siTimeRange.value[0]
    if (siTimeRange.value?.[1]) params.end_at = siTimeRange.value[1]
    if (siKeyword.value) params.keyword = siKeyword.value
    if (siApp.value) params.app = siApp.value
    if (siStream.value) params.stream = siStream.value
    if (siNode.value) params.node = siNode.value

    const resp = await api.get('/api/v1/plugins/runtime/stream_idle/events', { params })
    if (!isCurrentRuntimePlugin('stream_idle')) return
    const data = resp?.data || {}
    siRows.value = Array.isArray(data.rows) ? data.rows : []
    siHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('stream_idle')) return
    siError.value = getApiErrorMessage(e, '拉取断流事件失败')
    siRows.value = []
    siHasMore.value = false
  } finally {
    siLoading.value = false
  }
}

// timelapse：截图事件查询
const tlLoading = ref(false)
const tlError = ref('')
const tlRows = ref<PluginRuntimeRow[]>([])
const tlKeyword = ref('')
const tlApp = ref('')
const tlStream = ref('')
const tlPage = ref(1)
const tlPageSize = ref(50)
const tlHasMore = ref(false)
const tlTimeRange = ref<[string, string] | null>(null)

const fetchTimelapseEvents = async () => {
  tlLoading.value = true
  tlError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: tlPage.value,
      page_size: tlPageSize.value,
    }
    if (tlTimeRange.value?.[0]) params.start_at = tlTimeRange.value[0]
    if (tlTimeRange.value?.[1]) params.end_at = tlTimeRange.value[1]
    if (tlKeyword.value) params.keyword = tlKeyword.value
    if (tlApp.value) params.app = tlApp.value
    if (tlStream.value) params.stream = tlStream.value

    const resp = await api.get('/api/v1/plugins/runtime/timelapse/events', { params })
    if (!isCurrentRuntimePlugin('timelapse')) return
    const data = resp?.data || {}
    tlRows.value = Array.isArray(data.rows) ? data.rows : []
    tlHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('timelapse')) return
    tlError.value = getApiErrorMessage(e, '拉取截图事件失败')
    tlRows.value = []
    tlHasMore.value = false
  } finally {
    tlLoading.value = false
  }
}

// webhook_pusher：推送事件查询
const wpLoading = ref(false)
const wpError = ref('')
const wpRows = ref<PluginRuntimeRow[]>([])
const wpKeyword = ref('')
const wpDevice = ref('')
const wpStatus = ref<string | null>(null)
const wpOkMode = ref<'all' | 'true' | 'false'>('all')
const wpPage = ref(1)
const wpPageSize = ref(50)
const wpHasMore = ref(false)
const wpTimeRange = ref<[string, string] | null>(null)

const fetchWebhookPusherEvents = async () => {
  wpLoading.value = true
  wpError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: wpPage.value,
      page_size: wpPageSize.value,
    }
    if (wpTimeRange.value?.[0]) params.start_at = wpTimeRange.value[0]
    if (wpTimeRange.value?.[1]) params.end_at = wpTimeRange.value[1]
    if (wpKeyword.value) params.keyword = wpKeyword.value
    if (wpDevice.value) params.device = wpDevice.value
    if (wpStatus.value) params.status = wpStatus.value
    if (wpOkMode.value === 'true') params.ok = true
    if (wpOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/webhook_pusher/events', { params })
    if (!isCurrentRuntimePlugin('webhook_pusher')) return
    const data = resp?.data || {}
    wpRows.value = Array.isArray(data.rows) ? data.rows : []
    wpHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('webhook_pusher')) return
    wpError.value = getApiErrorMessage(e, '拉取 Webhook 事件失败')
    wpRows.value = []
    wpHasMore.value = false
  } finally {
    wpLoading.value = false
  }
}

// s3_sync：上传事件查询
const s3Loading = ref(false)
const s3Error = ref('')
const s3Rows = ref<PluginRuntimeRow[]>([])
const s3Keyword = ref('')
const s3Bucket = ref('')
const s3OkMode = ref<'all' | 'true' | 'false'>('all')
const s3Page = ref(1)
const s3PageSize = ref(50)
const s3HasMore = ref(false)
const s3TimeRange = ref<[string, string] | null>(null)

const fetchS3SyncEvents = async () => {
  s3Loading.value = true
  s3Error.value = ''
  try {
    const params: Record<string, unknown> = {
      page: s3Page.value,
      page_size: s3PageSize.value,
    }
    if (s3TimeRange.value?.[0]) params.start_at = s3TimeRange.value[0]
    if (s3TimeRange.value?.[1]) params.end_at = s3TimeRange.value[1]
    if (s3Keyword.value) params.keyword = s3Keyword.value
    if (s3Bucket.value) params.bucket = s3Bucket.value
    if (s3OkMode.value === 'true') params.ok = true
    if (s3OkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/s3_sync/events', { params })
    if (!isCurrentRuntimePlugin('s3_sync')) return
    const data = resp?.data || {}
    s3Rows.value = Array.isArray(data.rows) ? data.rows : []
    s3HasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('s3_sync')) return
    s3Error.value = getApiErrorMessage(e, '拉取 S3 同步事件失败')
    s3Rows.value = []
    s3HasMore.value = false
  } finally {
    s3Loading.value = false
  }
}

// ptz_tour：预置位下发事件
const ptzLoading = ref(false)
const ptzError = ref('')
const ptzRows = ref<PluginRuntimeRow[]>([])
const ptzKeyword = ref('')
const ptzDevice = ref('')
const ptzChannel = ref('')
const ptzOkMode = ref<'all' | 'true' | 'false'>('all')
const ptzPage = ref(1)
const ptzPageSize = ref(50)
const ptzHasMore = ref(false)
const ptzTimeRange = ref<[string, string] | null>(null)

const fetchPtzTourEvents = async () => {
  ptzLoading.value = true
  ptzError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: ptzPage.value,
      page_size: ptzPageSize.value,
    }
    if (ptzTimeRange.value?.[0]) params.start_at = ptzTimeRange.value[0]
    if (ptzTimeRange.value?.[1]) params.end_at = ptzTimeRange.value[1]
    if (ptzKeyword.value) params.keyword = ptzKeyword.value
    if (ptzDevice.value) params.device = ptzDevice.value
    if (ptzChannel.value) params.channel = ptzChannel.value
    if (ptzOkMode.value === 'true') params.ok = true
    if (ptzOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/ptz_tour/events', { params })
    if (!isCurrentRuntimePlugin('ptz_tour')) return
    const data = resp?.data || {}
    ptzRows.value = Array.isArray(data.rows) ? data.rows : []
    ptzHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('ptz_tour')) return
    ptzError.value = getApiErrorMessage(e, '拉取 PTZ 轮巡事件失败')
    ptzRows.value = []
    ptzHasMore.value = false
  } finally {
    ptzLoading.value = false
  }
}

// auto_record：录像启停事件
const arLoading = ref(false)
const arError = ref('')
const arRows = ref<PluginRuntimeRow[]>([])
const arKeyword = ref('')
const arStream = ref('')
const arOp = ref<string | null>(null)
const arOkMode = ref<'all' | 'true' | 'false'>('all')
const arPage = ref(1)
const arPageSize = ref(50)
const arHasMore = ref(false)
const arTimeRange = ref<[string, string] | null>(null)

const fetchAutoRecordEvents = async () => {
  arLoading.value = true
  arError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: arPage.value,
      page_size: arPageSize.value,
    }
    if (arTimeRange.value?.[0]) params.start_at = arTimeRange.value[0]
    if (arTimeRange.value?.[1]) params.end_at = arTimeRange.value[1]
    if (arKeyword.value) params.keyword = arKeyword.value
    if (arStream.value) params.stream = arStream.value
    if (arOp.value) params.op = arOp.value
    if (arOkMode.value === 'true') params.ok = true
    if (arOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/auto_record/events', { params })
    if (!isCurrentRuntimePlugin('auto_record')) return
    const data = resp?.data || {}
    arRows.value = Array.isArray(data.rows) ? data.rows : []
    arHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('auto_record')) return
    arError.value = getApiErrorMessage(e, '拉取自动录像事件失败')
    arRows.value = []
    arHasMore.value = false
  } finally {
    arLoading.value = false
  }
}

const rseLoading = ref(false)
const rseError = ref('')
const rseRows = ref<PluginRuntimeRow[]>([])
const rseKeyword = ref('')
const rseSchedule = ref('')
const rseStream = ref('')
const rseEvt = ref<string | null>(null)
const rsePage = ref(1)
const rsePageSize = ref(50)
const rseHasMore = ref(false)
const rseTimeRange = ref<[string, string] | null>(null)

const fetchRecordScheduleExecutorEvents = async () => {
  rseLoading.value = true
  rseError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: rsePage.value,
      page_size: rsePageSize.value,
    }
    if (rseTimeRange.value?.[0]) params.start_at = rseTimeRange.value[0]
    if (rseTimeRange.value?.[1]) params.end_at = rseTimeRange.value[1]
    if (rseKeyword.value) params.keyword = rseKeyword.value
    if (rseSchedule.value) params.schedule = rseSchedule.value
    if (rseStream.value) params.stream = rseStream.value
    if (rseEvt.value) params.evt = rseEvt.value

    const resp = await api.get('/api/v1/plugins/runtime/record_schedule_executor/events', { params })
    if (!isCurrentRuntimePlugin('record_schedule_executor')) return
    const data = resp?.data || {}
    rseRows.value = Array.isArray(data.rows) ? data.rows : []
    rseHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('record_schedule_executor')) return
    rseError.value = getApiErrorMessage(e, '拉取录像计划执行事件失败')
    rseRows.value = []
    rseHasMore.value = false
  } finally {
    rseLoading.value = false
  }
}

const rivLoading = ref(false)
const rivError = ref('')
const rivRows = ref<PluginRuntimeRow[]>([])
const rivKeyword = ref('')
const rivRecordId = ref('')
const rivOkMode = ref<'all' | 'true' | 'false'>('all')
const rivNote = ref<string | null>(null)
const rivPage = ref(1)
const rivPageSize = ref(50)
const rivHasMore = ref(false)
const rivTimeRange = ref<[string, string] | null>(null)

const fetchRecordIndexVerifierEvents = async () => {
  rivLoading.value = true
  rivError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: rivPage.value,
      page_size: rivPageSize.value,
    }
    if (rivTimeRange.value?.[0]) params.start_at = rivTimeRange.value[0]
    if (rivTimeRange.value?.[1]) params.end_at = rivTimeRange.value[1]
    if (rivKeyword.value) params.keyword = rivKeyword.value
    if (rivRecordId.value) params.record_id = rivRecordId.value
    if (rivOkMode.value === 'true') params.ok = true
    if (rivOkMode.value === 'false') params.ok = false
    if (rivNote.value) params.note = rivNote.value

    const resp = await api.get('/api/v1/plugins/runtime/record_index_verifier/events', { params })
    if (!isCurrentRuntimePlugin('record_index_verifier')) return
    const data = resp?.data || {}
    rivRows.value = Array.isArray(data.rows) ? data.rows : []
    rivHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('record_index_verifier')) return
    rivError.value = getApiErrorMessage(e, '拉取录像索引校验事件失败')
    rivRows.value = []
    rivHasMore.value = false
  } finally {
    rivLoading.value = false
  }
}

const snapLoading = ref(false)
const snapError = ref('')
const snapRows = ref<PluginRuntimeRow[]>([])
const snapKeyword = ref('')
const snapAsset = ref('')
const snapChannel = ref('')
const snapOkMode = ref<'all' | 'true' | 'false'>('all')
const snapPage = ref(1)
const snapPageSize = ref(50)
const snapHasMore = ref(false)
const snapTimeRange = ref<[string, string] | null>(null)

const fetchSnapshotRefreshEvents = async () => {
  snapLoading.value = true
  snapError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: snapPage.value,
      page_size: snapPageSize.value,
    }
    if (snapTimeRange.value?.[0]) params.start_at = snapTimeRange.value[0]
    if (snapTimeRange.value?.[1]) params.end_at = snapTimeRange.value[1]
    if (snapKeyword.value) params.keyword = snapKeyword.value
    if (snapAsset.value) params.asset = snapAsset.value
    if (snapChannel.value) params.channel = snapChannel.value
    if (snapOkMode.value === 'true') params.ok = true
    if (snapOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/snapshot_refresh/events', { params })
    if (!isCurrentRuntimePlugin('snapshot_refresh')) return
    const data = resp?.data || {}
    snapRows.value = Array.isArray(data.rows) ? data.rows : []
    snapHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('snapshot_refresh')) return
    snapError.value = getApiErrorMessage(e, '拉取快照刷新事件失败')
    snapRows.value = []
    snapHasMore.value = false
  } finally {
    snapLoading.value = false
  }
}

const rtmpLoading = ref(false)
const rtmpError = ref('')
const rtmpRows = ref<PluginRuntimeRow[]>([])
const rtmpKeyword = ref('')
const rtmpStream = ref('')
const rtmpSourceId = ref('')
const rtmpEvt = ref<string | null>(null)
const rtmpPage = ref(1)
const rtmpPageSize = ref(50)
const rtmpHasMore = ref(false)
const rtmpTimeRange = ref<[string, string] | null>(null)

const fetchRtmpPushMonitorEvents = async () => {
  rtmpLoading.value = true
  rtmpError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: rtmpPage.value,
      page_size: rtmpPageSize.value,
    }
    if (rtmpTimeRange.value?.[0]) params.start_at = rtmpTimeRange.value[0]
    if (rtmpTimeRange.value?.[1]) params.end_at = rtmpTimeRange.value[1]
    if (rtmpKeyword.value) params.keyword = rtmpKeyword.value
    if (rtmpStream.value) params.stream = rtmpStream.value
    if (rtmpSourceId.value) params.source_id = rtmpSourceId.value
    if (rtmpEvt.value) params.evt = rtmpEvt.value

    const resp = await api.get('/api/v1/plugins/runtime/rtmp_push_channel_monitor/events', { params })
    if (!isCurrentRuntimePlugin('rtmp_push_channel_monitor')) return
    const data = resp?.data || {}
    rtmpRows.value = Array.isArray(data.rows) ? data.rows : []
    rtmpHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('rtmp_push_channel_monitor')) return
    rtmpError.value = getApiErrorMessage(e, '拉取 RTMP 推流监控事件失败')
    rtmpRows.value = []
    rtmpHasMore.value = false
  } finally {
    rtmpLoading.value = false
  }
}

const ppmLoading = ref(false)
const ppmError = ref('')
const ppmRows = ref<PluginRuntimeRow[]>([])
const ppmKeyword = ref('')
const ppmStream = ref('')
const ppmEvt = ref<string | null>(null)
const ppmOkMode = ref<'all' | 'true' | 'false'>('all')
const ppmPage = ref(1)
const ppmPageSize = ref(50)
const ppmHasMore = ref(false)
const ppmTimeRange = ref<[string, string] | null>(null)

const fetchPullProxyMonitorEvents = async () => {
  ppmLoading.value = true
  ppmError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: ppmPage.value,
      page_size: ppmPageSize.value,
    }
    if (ppmTimeRange.value?.[0]) params.start_at = ppmTimeRange.value[0]
    if (ppmTimeRange.value?.[1]) params.end_at = ppmTimeRange.value[1]
    if (ppmKeyword.value) params.keyword = ppmKeyword.value
    if (ppmStream.value) params.stream = ppmStream.value
    if (ppmEvt.value) params.evt = ppmEvt.value
    if (ppmOkMode.value === 'true') params.ok = true
    if (ppmOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/pull_proxy_monitor/events', { params })
    if (!isCurrentRuntimePlugin('pull_proxy_monitor')) return
    const data = resp?.data || {}
    ppmRows.value = Array.isArray(data.rows) ? data.rows : []
    ppmHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('pull_proxy_monitor')) return
    ppmError.value = getApiErrorMessage(e, '拉取拉流代理监控事件失败')
    ppmRows.value = []
    ppmHasMore.value = false
  } finally {
    ppmLoading.value = false
  }
}

const mqttLoading = ref(false)
const mqttError = ref('')
const mqttRows = ref<PluginRuntimeRow[]>([])
const mqttKeyword = ref('')
const mqttDevice = ref('')
const mqttKind = ref<string | null>(null)
const mqttAlarmType = ref('')
const mqttOkMode = ref<'all' | 'true' | 'false'>('all')
const mqttPage = ref(1)
const mqttPageSize = ref(50)
const mqttHasMore = ref(false)
const mqttTimeRange = ref<[string, string] | null>(null)

const fetchMqttBridgeEvents = async () => {
  mqttLoading.value = true
  mqttError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: mqttPage.value,
      page_size: mqttPageSize.value,
    }
    if (mqttTimeRange.value?.[0]) params.start_at = mqttTimeRange.value[0]
    if (mqttTimeRange.value?.[1]) params.end_at = mqttTimeRange.value[1]
    if (mqttKeyword.value) params.keyword = mqttKeyword.value
    if (mqttDevice.value) params.device = mqttDevice.value
    if (mqttKind.value) params.kind = mqttKind.value
    if (mqttAlarmType.value) params.alarm_type = mqttAlarmType.value
    if (mqttOkMode.value === 'true') params.ok = true
    if (mqttOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/mqtt_bridge/events', { params })
    if (!isCurrentRuntimePlugin('mqtt_bridge')) return
    const data = resp?.data || {}
    mqttRows.value = Array.isArray(data.rows) ? data.rows : []
    mqttHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('mqtt_bridge')) return
    mqttError.value = getApiErrorMessage(e, '拉取 MQTT 桥接事件失败')
    mqttRows.value = []
    mqttHasMore.value = false
  } finally {
    mqttLoading.value = false
  }
}

const feishuLoading = ref(false)
const feishuError = ref('')
const feishuRows = ref<PluginRuntimeRow[]>([])
const feishuKeyword = ref('')
const feishuDevice = ref('')
const feishuAlarmType = ref('')
const feishuOkMode = ref<'all' | 'true' | 'false'>('all')
const feishuPage = ref(1)
const feishuPageSize = ref(50)
const feishuHasMore = ref(false)
const feishuTimeRange = ref<[string, string] | null>(null)

const fetchFeishuAlertEvents = async () => {
  feishuLoading.value = true
  feishuError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: feishuPage.value,
      page_size: feishuPageSize.value,
    }
    if (feishuTimeRange.value?.[0]) params.start_at = feishuTimeRange.value[0]
    if (feishuTimeRange.value?.[1]) params.end_at = feishuTimeRange.value[1]
    if (feishuKeyword.value) params.keyword = feishuKeyword.value
    if (feishuDevice.value) params.device = feishuDevice.value
    if (feishuAlarmType.value) params.alarm_type = feishuAlarmType.value
    if (feishuOkMode.value === 'true') params.ok = true
    if (feishuOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/feishu_alert/events', { params })
    if (!isCurrentRuntimePlugin('feishu_alert')) return
    const data = resp?.data || {}
    feishuRows.value = Array.isArray(data.rows) ? data.rows : []
    feishuHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('feishu_alert')) return
    feishuError.value = getApiErrorMessage(e, '拉取飞书告警事件失败')
    feishuRows.value = []
    feishuHasMore.value = false
  } finally {
    feishuLoading.value = false
  }
}

const wecomLoading = ref(false)
const wecomError = ref('')
const wecomRows = ref<PluginRuntimeRow[]>([])
const wecomKeyword = ref('')
const wecomDevice = ref('')
const wecomAlarmType = ref('')
const wecomOkMode = ref<'all' | 'true' | 'false'>('all')
const wecomPage = ref(1)
const wecomPageSize = ref(50)
const wecomHasMore = ref(false)
const wecomTimeRange = ref<[string, string] | null>(null)

const fetchWecomAlertEvents = async () => {
  wecomLoading.value = true
  wecomError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: wecomPage.value,
      page_size: wecomPageSize.value,
    }
    if (wecomTimeRange.value?.[0]) params.start_at = wecomTimeRange.value[0]
    if (wecomTimeRange.value?.[1]) params.end_at = wecomTimeRange.value[1]
    if (wecomKeyword.value) params.keyword = wecomKeyword.value
    if (wecomDevice.value) params.device = wecomDevice.value
    if (wecomAlarmType.value) params.alarm_type = wecomAlarmType.value
    if (wecomOkMode.value === 'true') params.ok = true
    if (wecomOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/wecom_alert/events', { params })
    if (!isCurrentRuntimePlugin('wecom_alert')) return
    const data = resp?.data || {}
    wecomRows.value = Array.isArray(data.rows) ? data.rows : []
    wecomHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('wecom_alert')) return
    wecomError.value = getApiErrorMessage(e, '拉取企业微信告警事件失败')
    wecomRows.value = []
    wecomHasMore.value = false
  } finally {
    wecomLoading.value = false
  }
}

const smsLoading = ref(false)
const smsError = ref('')
const smsRows = ref<PluginRuntimeRow[]>([])
const smsKeyword = ref('')
const smsDevice = ref('')
const smsAlarmType = ref('')
const smsOkMode = ref<'all' | 'true' | 'false'>('all')
const smsPage = ref(1)
const smsPageSize = ref(50)
const smsHasMore = ref(false)
const smsTimeRange = ref<[string, string] | null>(null)

const fetchSmsAlertEvents = async () => {
  smsLoading.value = true
  smsError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: smsPage.value,
      page_size: smsPageSize.value,
    }
    if (smsTimeRange.value?.[0]) params.start_at = smsTimeRange.value[0]
    if (smsTimeRange.value?.[1]) params.end_at = smsTimeRange.value[1]
    if (smsKeyword.value) params.keyword = smsKeyword.value
    if (smsDevice.value) params.device = smsDevice.value
    if (smsAlarmType.value) params.alarm_type = smsAlarmType.value
    if (smsOkMode.value === 'true') params.ok = true
    if (smsOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/sms_alert/events', { params })
    if (!isCurrentRuntimePlugin('sms_alert')) return
    const data = resp?.data || {}
    smsRows.value = Array.isArray(data.rows) ? data.rows : []
    smsHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    if (!isCurrentRuntimePlugin('sms_alert')) return
    smsError.value = getApiErrorMessage(e, '拉取短信告警事件失败')
    smsRows.value = []
    smsHasMore.value = false
  } finally {
    smsLoading.value = false
  }
}

const clearRuntimeConfig = () => {
  for (const k of Object.keys(runtimeConfig)) delete runtimeConfig[k]
}

const clearSaveConfigHighlight = () => {
  if (saveConfigHighlightTimer) {
    clearTimeout(saveConfigHighlightTimer)
    saveConfigHighlightTimer = null
  }
  highlightSaveConfigButton.value = false
}

const clearRuntimeFieldHighlight = () => {
  if (runtimeFieldHighlightTimer) {
    clearTimeout(runtimeFieldHighlightTimer)
    runtimeFieldHighlightTimer = null
  }
  focusedRuntimeFieldKey.value = ''
}

const clearRuntimeSaveSuccess = () => {
  runtimeSaveSuccessMessage.value = ''
  runtimeSaveFollowupRoute.value = ''
  runtimeSaveFollowupLabel.value = ''
  runtimeSaveQuickActionType.value = 'none'
  runtimeSaveQuickActionLabel.value = ''
  runtimeSaveQuickActionLoading.value = false
}

const normalizeFocusFieldKey = (value?: unknown) => String(value || '').trim()

const getAlertChannelFromPluginId = () => {
  if (pluginId.value === 'sms_alert') return 'sms'
  if (pluginId.value === 'wecom_alert') return 'wecom'
  if (pluginId.value === 'feishu_alert') return 'feishu'
  return ''
}

const getAlertChannelFromPluginTarget = (targetPluginId?: string) => {
  const normalized = String(targetPluginId || '').trim()
  if (normalized === 'sms_alert') return 'sms'
  if (normalized === 'wecom_alert') return 'wecom'
  if (normalized === 'feishu_alert') return 'feishu'
  return ''
}

const buildAlarmNotificationFollowupRoute = (focusLatest = false) => {
  const channelValue = getAlertChannelFromPluginId()
  const params = new URLSearchParams()
  if (channelValue) params.set('channel', channelValue)
  if (focusLatest) params.set('focus_latest', '1')
  return params.toString() ? `/alarm-notifications?${params.toString()}` : '/alarm-notifications'
}

const resolveRuntimeSaveFollowup = () => {
  if (['feishu_alert', 'wecom_alert', 'sms_alert'].includes(pluginId.value)) {
    return {
      message: '配置已保存，可前往告警通知记录验证消息是否正常发送。',
      quickActionType: 'alert_test' as const,
      quickActionLabel:
        pluginId.value === 'sms_alert'
          ? '发送测试短信'
          : pluginId.value === 'wecom_alert'
            ? '发送测试企微'
            : '发送测试飞书',
      route: buildAlarmNotificationFollowupRoute(false),
      label: '查看告警通知记录'
    }
  }
  if (
    [
      'stream_health',
      'network_watchdog',
      'stream_idle',
      'timelapse',
      'webhook_pusher',
      's3_sync',
      'mqtt_bridge',
      'auto_record',
      'record_schedule_executor',
      'record_index_verifier',
      'snapshot_refresh',
      'rtmp_push_channel_monitor',
      'pull_proxy_monitor',
      'sip_logger',
      'ptz_tour'
    ].includes(pluginId.value)
  ) {
    return {
      message: '配置已保存，可继续查看当前页下方运维数据，或前往运维中心验证该插件是否开始生效。',
      quickActionType: 'refresh_runtime_data' as const,
      quickActionLabel: '刷新当前数据',
      route: '/ops',
      label: '前往运维中心'
    }
  }
  return {
    message: '配置已保存。若该插件主要提供后端能力，可返回插件中心或相关业务页继续验证效果。',
    quickActionType: 'none' as const,
    quickActionLabel: '',
    route: '',
    label: ''
  }
}

const getRuntimeDataCount = () => {
  const countByPluginId: Record<string, number> = {
    stream_health: streamHealthRows.value.length,
    sip_logger: sipLogRows.value.length,
    network_watchdog: nwRows.value.length,
    stream_idle: siRows.value.length,
    timelapse: tlRows.value.length,
    webhook_pusher: wpRows.value.length,
    s3_sync: s3Rows.value.length,
    ptz_tour: ptzRows.value.length,
    auto_record: arRows.value.length,
    record_schedule_executor: rseRows.value.length,
    record_index_verifier: rivRows.value.length,
    snapshot_refresh: snapRows.value.length,
    rtmp_push_channel_monitor: rtmpRows.value.length,
    pull_proxy_monitor: ppmRows.value.length,
    mqtt_bridge: mqttRows.value.length,
    feishu_alert: feishuRows.value.length,
    wecom_alert: wecomRows.value.length,
    sms_alert: smsRows.value.length,
  }
  return countByPluginId[pluginId.value] ?? 0
}

const triggerAlertChannelTest = async (channelOverride?: string) => {
  const pid = pluginId.value
  const channel = ['sms_alert', 'wecom_alert', 'feishu_alert'].includes(String(channelOverride || '').trim())
    ? String(channelOverride || '').trim()
    : ['sms_alert', 'wecom_alert', 'feishu_alert'].includes(pluginId.value)
      ? pluginId.value
      : 'all'
  const alertChannel = getAlertChannelFromPluginTarget(channel)
  const expectedAfter = Date.now()
  const res = await api.post('/api/v1/plugins/alert-test', { channel })
  if (pluginId.value !== pid) return
  runtimeSaveSuccessMessage.value = res.data?.message || '测试告警已触发，可前往告警通知记录确认消息是否已送达。'
  if (!alertChannel) {
    runtimeSaveFollowupRoute.value = '/alarm-notifications'
  } else {
    const params = new URLSearchParams()
    params.set('channel', alertChannel)
    params.set('focus_latest', '1')
    params.set('expected_after', String(expectedAfter))
    runtimeSaveFollowupRoute.value = `/alarm-notifications?${params.toString()}`
  }
  runtimeSaveFollowupLabel.value = '查看告警通知记录'
  ElMessage.success(runtimeSaveSuccessMessage.value)
}

const performRuntimeSaveQuickAction = async () => {
  if (runtimeSaveQuickActionType.value === 'none') return
  const actionPid = pluginId.value
  runtimeSaveQuickActionLoading.value = true
  try {
    if (runtimeSaveQuickActionType.value === 'alert_test') {
      await triggerAlertChannelTest(pluginId.value)
      return
    }

    if (runtimeSaveQuickActionType.value === 'refresh_runtime_data') {
      const refreshByPluginId: Record<string, () => Promise<void>> = {
        stream_health: fetchStreamHealth,
        sip_logger: fetchSipLoggerLogs,
        network_watchdog: fetchNetworkWatchdogEvents,
        stream_idle: fetchStreamIdleEvents,
        timelapse: fetchTimelapseEvents,
        webhook_pusher: fetchWebhookPusherEvents,
        s3_sync: fetchS3SyncEvents,
        ptz_tour: fetchPtzTourEvents,
        auto_record: fetchAutoRecordEvents,
        record_schedule_executor: fetchRecordScheduleExecutorEvents,
        record_index_verifier: fetchRecordIndexVerifierEvents,
        snapshot_refresh: fetchSnapshotRefreshEvents,
        rtmp_push_channel_monitor: fetchRtmpPushMonitorEvents,
        pull_proxy_monitor: fetchPullProxyMonitorEvents,
        mqtt_bridge: fetchMqttBridgeEvents,
        feishu_alert: fetchFeishuAlertEvents,
        wecom_alert: fetchWecomAlertEvents,
        sms_alert: fetchSmsAlertEvents,
      }
      const refreshAction = refreshByPluginId[actionPid]
      if (!refreshAction) {
        ElMessage.warning('当前插件暂无可直接刷新的运行数据，请前往相关业务页验证效果。')
        return
      }
      await refreshAction()
      if (pluginId.value !== actionPid) return
      const rowCount = getRuntimeDataCount()
      if (rowCount > 0) {
        runtimeSaveSuccessMessage.value = `已刷新当前插件运行数据，当前可见 ${rowCount} 条记录，可继续在本页验证插件是否生效。`
        ElMessage.success('已刷新当前插件运行数据')
      } else {
        runtimeSaveSuccessMessage.value = '已刷新当前插件运行数据，但暂未看到新的结果。若业务事件尚未触发，这是正常现象，可稍后重试或前往相关业务页继续验证。'
        ElMessage.info('已刷新数据，当前暂无新记录')
      }
    }
  } catch (error: unknown) {
    if (pluginId.value !== actionPid) return
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    runtimeSaveQuickActionLoading.value = false
  }
}

const focusRuntimeConfigEntry = async () => {
  if (!showConfigForm.value || iframeUrl.value) return
  await nextTick()

  const formRoot = runtimeFormRef.value?.$el ?? runtimeFormRef.value
  if (formRoot instanceof HTMLElement) {
    const firstEditable = formRoot.querySelector(
      [
        'textarea:not([disabled])',
        'input:not([type="hidden"]):not([disabled])',
        'button.el-switch__button:not([disabled])',
        'button:not([disabled])'
      ].join(', ')
    ) as HTMLElement | null
    if (firstEditable) {
      firstEditable.scrollIntoView({ behavior: 'smooth', block: 'center' })
      firstEditable.focus()
      return
    }
  }

  const rawSaveButton = saveConfigButtonRef.value?.$el ?? saveConfigButtonRef.value
  const saveButton = rawSaveButton instanceof HTMLElement
    ? (rawSaveButton.tagName === 'BUTTON' ? rawSaveButton : rawSaveButton.querySelector('button'))
    : null
  if (!(saveButton instanceof HTMLElement)) return
  highlightSaveConfigButton.value = true
  saveButton.scrollIntoView({ behavior: 'smooth', block: 'center' })
  saveButton.focus()
  if (saveConfigHighlightTimer) clearTimeout(saveConfigHighlightTimer)
  saveConfigHighlightTimer = setTimeout(() => {
    highlightSaveConfigButton.value = false
    saveConfigHighlightTimer = null
  }, 4200)
}

const focusRuntimeFieldByKey = async (fieldKey?: string) => {
  const targetKey = normalizeFocusFieldKey(fieldKey)
  if (!targetKey || !showConfigForm.value || iframeUrl.value) return
  await nextTick()

  const fieldRoot = document.querySelector(`[data-runtime-field-key="${targetKey}"]`) as HTMLElement | null
  if (!fieldRoot) {
    ElMessage.warning(`当前插件未找到配置项 ${targetKey}`)
    return
  }

  clearRuntimeFieldHighlight()
  focusedRuntimeFieldKey.value = targetKey
  fieldRoot.scrollIntoView({ behavior: 'smooth', block: 'center' })

  const focusable = fieldRoot.querySelector(
    [
      'textarea:not([disabled])',
      'input:not([type="hidden"]):not([disabled])',
      'button.el-switch__button:not([disabled])',
      'button:not([disabled])'
    ].join(', ')
  ) as HTMLElement | null
  focusable?.focus()

  runtimeFieldHighlightTimer = setTimeout(() => {
    focusedRuntimeFieldKey.value = ''
    runtimeFieldHighlightTimer = null
  }, 4200)
}

const focusRuntimeFieldFromRoute = async () => {
  const queryValue = Array.isArray(route.query.focus_field)
    ? route.query.focus_field[0]
    : route.query.focus_field
  const targetKey = normalizeFocusFieldKey(queryValue)
  if (!targetKey) return
  await focusRuntimeFieldByKey(targetKey)
}

const loadRuntimeConfig = async (lockPluginId?: string) => {
  const targetPid = lockPluginId ?? pluginId.value
  loadingConfig.value = true
  configError.value = ''
  try {
    const resp = await api.get(`/api/v1/plugins/runtime/${encodeURIComponent(targetPid)}/config`)
    if (lockPluginId != null && pluginId.value !== lockPluginId) return
    const data = resp?.data || {}
    runtimeSchema.value = data.schema || {}
    clearRuntimeConfig()

    const cfg = data.config && typeof data.config === 'object' ? data.config : {}
    for (const [k, v] of Object.entries(cfg)) {
      runtimeConfig[k] = v
    }

    // json 字段单独用文本编辑，保存时再 parse
    for (const f of runtimeFields.value) {
      const t = String(f.type || '').toLowerCase()
      const key = String(f.key)
      if (t === 'json') {
        const v = runtimeConfig[key]
        if (typeof v === 'string') jsonText[key] = v
        else jsonText[key] = JSON.stringify(v ?? {}, null, 2)
      }
      if (t === 'bool' && typeof runtimeConfig[key] !== 'boolean') {
        runtimeConfig[key] = Boolean(runtimeConfig[key])
      }
    }

    // 是否展示配置表单：只要 schema.fields 存在即可
    showConfigForm.value = runtimeFields.value.length > 0
    runtimeGuidanceState.value = 'default'
    clearRuntimeSaveSuccess()
    runtimeMessage.value = showConfigForm.value
      ? `插件 ${pluginDisplayName.value || targetPid} 可配置`
      : `插件 ${pluginDisplayName.value || targetPid} 未提供 config_schema`
    if (showConfigForm.value) {
      await focusRuntimeConfigEntry()
      await focusRuntimeFieldFromRoute()
    }
  } catch (e: unknown) {
    if (lockPluginId != null && pluginId.value !== lockPluginId) return
    const friendly = getFriendlyError(e)
    const failure = buildRuntimeLoadFailureState(friendly.message, friendly.suggestion)
    runtimeGuidanceState.value = failure.state
    runtimeMessage.value = failure.message
    configError.value = failure.message
    showConfigForm.value = false
  } finally {
    if (lockPluginId == null || pluginId.value === lockPluginId) loadingConfig.value = false
  }
}

const saveRuntimeConfig = async () => {
  if (!runtimeFields.value.length) return
  const pid = pluginId.value
  savingConfig.value = true
  configError.value = ''
  clearRuntimeSaveSuccess()
  try {
    const configToSend: Record<string, unknown> = {}
    for (const f of runtimeFields.value) {
      const key = String(f.key)
      const t = String(f.type || '').toLowerCase()
      if (t === 'json') {
        const txt = String(jsonText[key] ?? '').trim()
        if (!txt) {
          configToSend[key] = {}
          continue
        }
        try {
          configToSend[key] = JSON.parse(txt)
        } catch {
          throw new Error(`字段 ${key} 的 JSON 解析失败，请检查格式`)
        }
      } else {
        configToSend[key] = runtimeConfig[key]
      }
    }
    await api.put(`/api/v1/plugins/runtime/${encodeURIComponent(pid)}/config`, { config: configToSend })
    if (pluginId.value !== pid) return
    const followup = resolveRuntimeSaveFollowup()
    runtimeSaveSuccessMessage.value = followup.message
    runtimeSaveQuickActionType.value = followup.quickActionType
    runtimeSaveQuickActionLabel.value = followup.quickActionLabel
    runtimeSaveFollowupRoute.value = followup.route
    runtimeSaveFollowupLabel.value = followup.label
    ElMessage.success(followup.message)
  } catch (e: unknown) {
    if (pluginId.value !== pid) return
    configError.value = e instanceof Error ? e.message : '保存失败'
    ElMessage.error(configError.value)
  } finally {
    savingConfig.value = false
  }
}

/** iframe 无法带 Bearer，plugin-assets 依赖 deps 的 query token，与 axios 使用同一 localStorage token。 */
const withPluginAssetsAuthToken = (url: unknown) => {
  const u = String(url || '').trim()
  if (!u || !u.includes('plugin-assets')) return u
  const token = localStorage.getItem('token')
  if (!token) return u
  const sep = u.includes('?') ? '&' : '?'
  return `${u}${sep}token=${encodeURIComponent(token)}`
}

const withRuntimeSuggestion = (message: string, suggestion?: string) => {
  const base = String(message || '').trim()
  const extra = String(suggestion || '').trim()
  if (!extra) return base
  if (base.includes(extra)) return base
  return `${base} ${extra}`
}

const buildRuntimeLoadFailureState = (detail?: unknown, suggestion?: string) => {
  const text = typeof detail === 'string' ? detail.trim() : ''
  const includesAny = (...needles: string[]) => needles.some((needle) => text.includes(needle))

  if (includesAny('未购买', '无授权')) {
    if (isPluginPurchased.value && !isPluginInstalled.value) {
      return {
        state: 'install' as const,
        message: '已同步到该插件的购买状态，但当前实例尚未完成安装。请返回插件中心安装后再进入运行页。'
      }
    }
    return {
      state: 'buy' as const,
      message: '未检测到该付费插件授权，请先前往服务器版完成购买或续费，再回到开源端安装。'
    }
  }

  if (includesAny('缺少 license')) {
    if (isPluginPurchased.value) {
      return {
        state: 'reinstall' as const,
        message: '已检测到购买记录，但当前实例缺少授权文件。请返回插件中心重新安装或同步授权后，再进入运行页。'
      }
    }
    return {
      state: 'buy' as const,
      message: '当前实例尚未同步到该插件授权，请先到服务器版完成购买后再返回安装。'
    }
  }

  if (includesAny('授权无效', 'license 无效', 'license invalid')) {
    return {
      state: 'renew' as const,
      message: '当前插件授权无效、已过期或与当前实例不匹配。请到服务器版续费或重新发放授权后，再回到插件中心重新安装。'
    }
  }

  if (includesAny('开源版') && includesAny('版本', '兼容')) {
    return {
      state: 'upgrade' as const,
      message: '当前开源版版本与该插件不兼容，请先升级开源版到要求版本后，再继续安装或运行。'
    }
  }

  if (includesAny('废弃')) {
    return {
      state: 'configure' as const,
      message: '该插件已进入废弃态，当前实例不再建议继续运行。请返回插件中心查看替代插件或迁移说明。'
    }
  }

  if (includesAny('灰度', '白名单')) {
    return {
      state: 'configure' as const,
      message: '当前租户暂未开通该插件运行权限，请联系管理员确认灰度范围、购买状态或授权开通情况。'
    }
  }

  if (includesAny('plugin-assets', 'index.html', 'frontend_url', '资源不存在', '404')) {
    return {
      state: isPluginInstalled.value ? 'reinstall' as const : 'install' as const,
      message: isPluginInstalled.value
        ? '该插件已安装，但运行入口资源缺失或不可达。请返回插件中心重新安装或升级插件后再试。'
        : '当前实例尚未准备好该插件运行入口，请先返回插件中心完成安装。'
    }
  }

  if (includesAny('config_schema', 'schema')) {
    return {
      state: 'configure' as const,
      message: '该插件未提供可视化运行配置，请返回插件中心查看文档说明，或仅使用其后端能力。'
    }
  }

  if (isPluginPurchased.value && !isPluginInstalled.value) {
    return {
      state: 'install' as const,
      message: '已检测到该插件已购买，但当前开源端实例尚未安装。请返回插件中心完成安装后再进入运行页。'
    }
  }

  if (!isPluginPurchased.value && !isPluginInstalled.value) {
    return {
      state: 'buy' as const,
      message: '当前实例尚未安装该插件；若为付费插件，请先到服务器版完成购买，再回到插件中心安装。'
    }
  }

  if (isPluginInstalled.value) {
    return {
      state: 'configure' as const,
      message: withRuntimeSuggestion(
        '该插件已安装，但当前版本未提供独立运行入口。请返回插件中心查看说明，或前往配置页继续配置。',
        suggestion
      )
    }
  }

  return {
    state: 'default' as const,
    message: withRuntimeSuggestion(
      '加载插件运行入口失败，请返回插件中心检查该插件是否已购买、已安装并满足版本要求。',
      suggestion
    )
  }
}

const loadPluginAccessState = async () => {
  const [shopRes, purchasedRes, installedRes] = await Promise.all([
    api.get('/api/v1/plugins/marketplace-shop-url').catch(() => ({ data: { url: '' } })),
    api.get('/api/v1/plugins/purchased').catch(() => ({ data: { plugin_ids: [] } })),
    api.get('/api/v1/plugins/installed').catch(() => ({ data: [] }))
  ])
  shopUrl.value = String(shopRes?.data?.url || '').trim()
  purchasedPluginIds.value = Array.isArray(purchasedRes?.data?.plugin_ids)
    ? purchasedRes.data.plugin_ids.map((item: unknown) => String(item))
    : []
  installedPluginIds.value = Array.isArray(installedRes?.data)
    ? installedRes.data
      .map((item: unknown) => (item && typeof item === 'object' && 'id' in item ? String((item as { id?: unknown }).id || '') : ''))
      .filter(Boolean)
    : []
}

const buildRuntimeLoadFailureMessage = (detail?: unknown) => {
  const failure = buildRuntimeLoadFailureState(detail)
  runtimeGuidanceState.value = failure.state
  return failure.message
}

const onPurchaseSync = async () => {
  const previousPurchased = isPluginPurchased.value
  await loadPluginAccessState()
  if (!previousPurchased && isPluginPurchased.value && !isPluginInstalled.value && !iframeUrl.value) {
    runtimeGuidanceState.value = 'install'
    runtimeMessage.value = '已同步到服务器版购买结果，当前实例仍未安装该插件，请返回插件中心安装后再进入运行页。'
    ElMessage.success('购买状态已同步，请先返回插件中心安装插件')
  }
}

const handlePurchaseSyncEvent = () => {
  void onPurchaseSync()
}

async function bootstrapPluginRuntime() {
  clearStreamHealthAutoRefresh()
  const bootstrapId = pluginId.value
  if (!bootstrapId) {
    runtimeMessage.value = '缺少 pluginId，无法加载插件运行入口'
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [res] = await Promise.all([
      api.get('/api/v1/plugins/menus'),
      loadPluginAccessState()
    ])
    if (pluginId.value !== bootstrapId) return
    const menus = Array.isArray(res.data) ? res.data : []
    const entry = menus.find(
      (m: Record<string, unknown>) =>
        m.plugin_id === bootstrapId ||
        m.path === `/plugins/runtime/${bootstrapId}` ||
        (typeof m.path === 'string' && m.path.endsWith(`/plugins/runtime/${bootstrapId}`))
    )
    if (entry?.frontend_url) {
      iframeUrl.value = withPluginAssetsAuthToken(entry.frontend_url)
      pluginDisplayName.value = String(entry.title || bootstrapId)
      runtimeGuidanceState.value = 'default'
      runtimeMessage.value = `插件 ${pluginDisplayName.value} 已安装，可在其运行页中继续配置业务功能。`
    } else {
      // 无 frontend_url 代表该插件未提供 oss 运行入口（后端能力为主时常见）。
      iframeUrl.value = ''
      pluginDisplayName.value = String(entry?.title || bootstrapId)
      // 尝试拉取 config_schema 并展示“通用配置页”
      await loadRuntimeConfig(bootstrapId)
      if (pluginId.value !== bootstrapId) return
    }

    // stream_health：即使也有通用配置表单，也附加健康快照列表
    if (bootstrapId === 'stream_health') {
      await fetchStreamHealth()
      // 低频刷新：避免频繁打 ZLM
      streamHealthAutoTimer = setInterval(() => {
        fetchStreamHealth()
      }, 30000)
    }

    // sip_logger：专用日志查询页（不做轮询，手动刷新/翻页）
    if (bootstrapId === 'sip_logger') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      sipTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      sipLogPage.value = 1
      await fetchSipLoggerLogs()
    }

    // network_watchdog：不可达事件查询页（含 iframe 嵌入页下方运维表）
    if (bootstrapId === 'network_watchdog') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      nwTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      nwPage.value = 1
      await fetchNetworkWatchdogEvents()
    }

    // stream_idle：断流事件查询页
    if (bootstrapId === 'stream_idle') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      siTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      siPage.value = 1
      await fetchStreamIdleEvents()
    }

    // timelapse：截图事件查询页
    if (bootstrapId === 'timelapse') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      tlTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      tlPage.value = 1
      await fetchTimelapseEvents()
    }

    // webhook_pusher：推送事件查询
    if (bootstrapId === 'webhook_pusher') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      wpTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      wpPage.value = 1
      await fetchWebhookPusherEvents()
    }

    // s3_sync：上传事件查询
    if (bootstrapId === 's3_sync') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      s3TimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      s3Page.value = 1
      await fetchS3SyncEvents()
    }

    if (bootstrapId === 'ptz_tour') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      ptzTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      ptzPage.value = 1
      await fetchPtzTourEvents()
    }

    if (bootstrapId === 'auto_record') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      arTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      arPage.value = 1
      await fetchAutoRecordEvents()
    }

    if (bootstrapId === 'record_schedule_executor') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      rseTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      rsePage.value = 1
      await fetchRecordScheduleExecutorEvents()
    }

    if (bootstrapId === 'record_index_verifier') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      rivTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      rivPage.value = 1
      await fetchRecordIndexVerifierEvents()
    }

    if (bootstrapId === 'snapshot_refresh') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      snapTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      snapPage.value = 1
      await fetchSnapshotRefreshEvents()
    }

    if (bootstrapId === 'rtmp_push_channel_monitor') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      rtmpTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      rtmpPage.value = 1
      await fetchRtmpPushMonitorEvents()
    }

    if (bootstrapId === 'pull_proxy_monitor') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      ppmTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      ppmPage.value = 1
      await fetchPullProxyMonitorEvents()
    }

    if (bootstrapId === 'mqtt_bridge') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      mqttTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      mqttPage.value = 1
      await fetchMqttBridgeEvents()
    }

    if (bootstrapId === 'feishu_alert') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      feishuTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      feishuPage.value = 1
      await fetchFeishuAlertEvents()
    }

    if (bootstrapId === 'wecom_alert') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      wecomTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      wecomPage.value = 1
      await fetchWecomAlertEvents()
    }

    if (bootstrapId === 'sms_alert') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      smsTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      smsPage.value = 1
      await fetchSmsAlertEvents()
    }
  } catch (error: unknown) {
    if (pluginId.value !== bootstrapId) return
    iframeUrl.value = ''
    pluginDisplayName.value = bootstrapId
    const friendly = getFriendlyError(error)
    runtimeMessage.value = buildRuntimeLoadFailureMessage(friendly.message)
  } finally {
    if (pluginId.value === bootstrapId) loading.value = false
  }
}

onMounted(() => {
  void bootstrapPluginRuntime()
  window.addEventListener('plugin-purchases-updated', handlePurchaseSyncEvent)
})

watch(pluginId, (id, prev) => {
  if (!id || prev === undefined || prev === id) return
  void bootstrapPluginRuntime()
})

useActivatedRefreshOnce(() => bootstrapPluginRuntime())

onBeforeUnmount(() => {
  clearStreamHealthAutoRefresh()
  clearSaveConfigHighlight()
  clearRuntimeFieldHighlight()
  window.removeEventListener('plugin-purchases-updated', handlePurchaseSyncEvent)
})

watch(
  () => route.query.focus_field,
  () => {
    if (showConfigForm.value && !iframeUrl.value) {
      void focusRuntimeFieldFromRoute()
    }
  }
)
</script>

<style scoped>
.plugin-runtime {
  height: 100%;
}

:deep(.runtime-save-button--highlight) {
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.18);
  transition: box-shadow 0.25s ease;
}

:deep(.runtime-field--focus .el-form-item__label),
:deep(.runtime-field--focus .el-input__wrapper),
:deep(.runtime-field--focus .el-textarea__inner),
:deep(.runtime-field--focus .el-input-number),
:deep(.runtime-field--focus .el-switch) {
  transition: box-shadow 0.25s ease, border-color 0.25s ease;
}

:deep(.runtime-field--focus .el-input__wrapper),
:deep(.runtime-field--focus .el-textarea__inner),
:deep(.runtime-field--focus .el-input-number),
:deep(.runtime-field--focus .el-switch) {
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.18);
}

:deep(.runtime-field--focus .el-form-item__label) {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>

