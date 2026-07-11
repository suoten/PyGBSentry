<template>
  <div class="p-4 mt-4 rounded-xl" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
    <div class="record-toolbar mb-3">
      <div class="flex items-center gap-2">
        <div class="w-2.5 h-2.5 rounded-full bg-sky-400 shadow-[0_0_0_4px_rgba(56,189,248,0.16)]"></div>
        <h3 class="text-[15px] font-semibold tracking-wide" style="color: var(--el-text-color-primary)">{{ t('record.timelineTitle') }}</h3>
        <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('record.timelineSubtitle') }}</span>
      </div>
      <div class="record-toolbar-actions">
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          :range-separator="t('record.rangeSeparator')"
          :start-placeholder="t('common.startTime')"
          :end-placeholder="t('common.endTime')"
          size="small"
        />
        <el-button type="primary" size="small" @click="fetchAll" :loading="loading">{{ t('common.query') }}</el-button>
        <el-button size="small" @click="resetRange">{{ t('common.reset') }}</el-button>
        <el-button size="small" type="success" @click="startDeviceDownload" :loading="downloadLoading" :disabled="!windowStart || !windowEnd">
          {{ t('record.downloadDeviceRecord') }}
        </el-button>
      </div>
    </div>
    <div v-if="deviceQueryStatus && !loading" class="mb-3 text-xs flex items-center justify-between">
      <div style="color: var(--el-text-color-secondary)">
        {{ t('record.deviceRecordLabel') }}{{ deviceQueryStatusText }}
      </div>
      <el-button v-if="deviceQueryStatus.status === 'running' || deviceQueryStatus.status === 'pending'" size="small" @click="cancelDeviceQuery">
        {{ t('record.cancelQuery') }}
      </el-button>
    </div>

    <div v-if="downloadStatus && !loading" class="mb-3 text-xs" style="color: var(--el-text-color-secondary)">
      <div class="flex items-center justify-between">
        <div>
          {{ t('record.downloadTaskLabel') }}{{ downloadStatusText }}
        </div>
        <div class="flex gap-2">
          <el-button v-if="downloadStatus.status === 'pending' || downloadStatus.status === 'running'" size="small" @click="refreshDownloadStatus">
            {{ t('common.refresh') }}
          </el-button>
          <el-button v-if="downloadStatus.status === 'pending' || downloadStatus.status === 'running'" size="small" type="danger" @click="stopDeviceDownload">
            {{ t('record.stop') }}
          </el-button>
        </div>
      </div>
      <div v-if="Array.isArray(downloadStatus.records) && downloadStatus.records.length" class="mt-2 flex flex-wrap gap-2">
        <el-button
          v-for="r in downloadStatus.records"
          :key="r.record_id"
          size="small"
          @click="openDownload(r.download_url)"
        >
          {{ t('record.downloadFile') }}
        </el-button>
      </div>
    </div>

    <div v-if="!loading" class="space-y-3">
      <div>
        <div class="text-xs mb-1" style="color: var(--el-text-color-secondary)">{{ t('record.cloudTitle') }}</div>
        <div class="timeline-row">
          <div
            v-for="item in cloudSegments"
            :key="String(item.id ?? '')"
            class="segment cloud"
            :style="segmentStyle(item)"
            @click="playCloud(item)"
          />
        </div>
      </div>
      <div>
        <div class="text-xs mb-1" style="color: var(--el-text-color-secondary)">{{ t('common.deviceRecord') }}</div>
        <div class="timeline-row">
          <div
            v-for="item in deviceSegments"
            :key="String(item.id ?? '')"
            class="segment device"
            :style="segmentStyle(item)"
            @click="playDevice(item)"
          />
        </div>
      </div>
      <div class="flex justify-between text-xs mt-1" style="color: var(--el-text-color-secondary)">
        <span>{{ formatTime(windowStart) }}</span>
        <span>{{ formatTime(windowEnd) }}</span>
      </div>
    </div>

    <div v-else class="h-24 flex items-center justify-center" style="color: var(--el-text-color-secondary)">
      {{ t('common.loading') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import { showSuccess, showError } from '@/utils/feedback'

const { t } = useI18n()

const props = defineProps<{
  deviceId: string
  channelId: string
  initialStart?: string
  initialEnd?: string
}>()

type PlayPayload =
  | string
  | {
      app?: string
      stream?: string
      codec?: string
      start_time?: number
      end_time?: number
      urls: { webrtc?: string; flv?: string; hls?: string; raw?: string }
    }

const emit = defineEmits<{
  (e: 'play', payload: PlayPayload): void
}>()

type DateRange = [Date, Date]
const dateRange = ref<DateRange | []>([])
const loading = ref(false)
const cloudSegments = ref<Record<string, unknown>[]>([])
const deviceSegments = ref<Record<string, unknown>[]>([])
const deviceQueryStatus = ref<Record<string, unknown> | null>(null)
const cancelToken = ref(0)
const downloadTaskId = ref<string>('')
const downloadStatus = ref<Record<string, unknown> | null>(null)
const downloadLoading = ref(false)

const windowStart = computed(() => (dateRange.value?.[0] as Date | null) || null)
const windowEnd = computed(() => (dateRange.value?.[1] as Date | null) || null)

const fetchCloud = async () => {
  if (!windowStart.value || !windowEnd.value) return []
  try {
    const res = await api.get('/api/v1/record/query', {
      params: {
        device_id: props.deviceId,
        channel_id: props.channelId,
        start_time: windowStart.value.toISOString(),
        end_time: windowEnd.value.toISOString()
      }
    })
    return res.data || []
  } catch (e) {
    showError(t('record.fetchCloudRecord'), e)
    return []
  }
}

const fetchDevice = async () => {
  if (!windowStart.value || !windowEnd.value) return []
  try {
    const myToken = Date.now()
    cancelToken.value = myToken
    deviceQueryStatus.value = { status: 'pending', received: 0, sum_num: 0 }
    const startRes = await api.post('/api/v1/device-record/device/queries', {
      device_id: props.deviceId,
      channel_id: props.channelId,
      start_time: windowStart.value.toISOString(),
      end_time: windowEnd.value.toISOString(),
      timeout_seconds: 20
    })
    const queryId = String(startRes.data?.query_id || '')
    if (!queryId) return []

    const startedAt = Date.now()
    const deadline = startedAt + 22000
    let lastItems: Record<string, unknown>[] = []
    while (Date.now() < deadline) {
      if (cancelToken.value !== myToken) {
        deviceQueryStatus.value = { status: 'cancelled', received: 0, sum_num: 0 }
        return lastItems
      }
      const statusRes = await api.get(`/api/v1/device-record/device/queries/${queryId}`, {
        params: { offset: 0, limit: 5000 }
      })
      const st = statusRes.data || {}
      deviceQueryStatus.value = st
      const items = Array.isArray(st.items) ? st.items : []
      if (items.length) lastItems = items
      const status = String(st.status || '')
      if (status === 'done' || status === 'partial' || status === 'timeout') {
        return lastItems
      }
      await new Promise((r) => setTimeout(r, 500))
    }
    deviceQueryStatus.value = { status: 'timeout', received: lastItems.length, sum_num: 0 }
    return lastItems
  } catch (e) {
    showError(t('record.fetchDeviceRecord'), e)
    deviceQueryStatus.value = { status: 'error', received: 0, sum_num: 0 }
    return []
  }
}

const fetchAll = async () => {
  if (!windowStart.value || !windowEnd.value) return
  loading.value = true
  deviceQueryStatus.value = null
  try {
    const [cloud, device] = await Promise.all([fetchCloud(), fetchDevice()])
    cloudSegments.value = (cloud || []).map((item: Record<string, unknown>) => ({
      ...item,
      start: (() => { const t = new Date(item.start_time as string | number | Date).getTime(); return Number.isFinite(t) ? t : Date.now() })(),
      end: (() => { const t = new Date(item.end_time as string | number | Date).getTime(); return Number.isFinite(t) ? t : Date.now() })()
    }))
    deviceSegments.value = (device || []).map((item: Record<string, unknown>) => ({
      ...item,
      start: (() => { const t = new Date(item.start_time as string | number | Date).getTime(); return Number.isFinite(t) ? t : Date.now() })(),
      end: (() => { const t = new Date(item.end_time as string | number | Date).getTime(); return Number.isFinite(t) ? t : Date.now() })()
    }))
  } catch (e) {
    const friendly = getFriendlyError(e)
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const deviceQueryStatusText = computed(() => {
  const st = deviceQueryStatus.value
  if (!st) return ''
  const status = String(st.status || '')
  const received = Number(st.received || 0)
  const sum = Number(st.sum_num || 0)
  const progress = sum > 0 ? `${received}/${sum}` : `${received}`
  if (status === 'done') return t('record.queryDone', { progress })
  if (status === 'running') return t('record.queryRunning', { progress })
  if (status === 'pending') return t('record.queryPending', { progress })
  if (status === 'partial') return t('record.queryPartial', { progress })
  if (status === 'timeout') return t('record.queryTimeout', { progress })
  if (status === 'cancelled') return t('record.queryCancelled')
  return status
})

const cancelDeviceQuery = () => {
  cancelToken.value = Date.now()
}

const openDownload = (url: string) => {
  const u = String(url || '').trim()
  if (!u) return
  window.open(u, '_blank')
}

const refreshDownloadStatus = async () => {
  if (!downloadTaskId.value) return
  try {
    const res = await api.get(`/api/v1/device-record/download/progress/${downloadTaskId.value}`, {
      params: { auto_stop: true }
    })
    downloadStatus.value = res.data || null
  } catch (e) {
    showError(t('record.refreshDownloadStatus'), e)
    downloadStatus.value = null
  }
}

const stopDeviceDownload = async () => {
  if (!downloadTaskId.value) return
  try {
    await api.post(`/api/v1/device-record/download/stop/${downloadTaskId.value}`)
    showSuccess(t('record.downloadStopped'))
    await refreshDownloadStatus()
  } catch (e) {
    showError(t('record.stopDownload'), e)
  }
}

const startDeviceDownload = async () => {
  if (!windowStart.value || !windowEnd.value) return
  downloadLoading.value = true
  try {
    const startRes = await api.post('/api/v1/device-record/download/start', {
      device_id: props.deviceId,
      channel_id: props.channelId,
      start_time: windowStart.value.toISOString(),
      end_time: windowEnd.value.toISOString()
    })
    downloadTaskId.value = String(startRes.data?.task_id || '')
    showSuccess(t('record.downloadTaskStarted'))
    await refreshDownloadStatus()
  } catch (e) {
    const friendly = getFriendlyError(e)
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    downloadLoading.value = false
  }
}

const downloadStatusText = computed(() => {
  const st = downloadStatus.value
  if (!st) return ''
  const status = String(st.status || '')
  const percent = Number(st.percent || 0)
  if (status === 'done') return t('record.downloadDone')
  if (status === 'running') return t('record.downloadRecording', { percent })
  if (status === 'pending') return t('record.downloadPending')
  if (status === 'cancelled') return t('record.downloadStoppedStatus')
  if (status === 'failed') return t('record.downloadFailed')
  return status
})

const segmentStyle = (item: Record<string, unknown>) => {
  if (!windowStart.value || !windowEnd.value) return {}
  const total = windowEnd.value.getTime() - windowStart.value.getTime()
  if (total <= 0) return {}
  const startOffset = Math.max((item.start as number) - windowStart.value.getTime(), 0)
  const endOffset = Math.min(item.end as number, windowEnd.value.getTime()) - windowStart.value.getTime()
  const left = (startOffset / total) * 100
  const width = Math.max(((endOffset - startOffset) / total) * 100, 0.5)
  return {
    left: `${left}%`,
    width: `${width}%`
  }
}

const buildInlineRecordUrl = (id: string) => {
  // P0-6: 移除 URL 中的 token，改由 HttpOnly cookie 认证（硬约束 #1）
  return `/api/v1/record/download/${encodeURIComponent(id)}?inline=true`
}

const playCloud = async (item: Record<string, unknown>) => {
  const direct = String(item?.file_path || '').trim()
  if (direct.startsWith('http://') || direct.startsWith('https://')) {
    emit('play', { urls: { raw: direct } })
    return
  }
  const id = String(item?.id || '').trim()
  if (!id) {
    emit('play', { urls: { raw: direct } })
    return
  }
  try {
    const res = await api.get(`/api/v1/record/play-url/${id}`)
    const data = res.data || {}
    const urls = {
      webrtc: String(data.rtcs || data.webrtc || data.rtc || '').trim(),
      flv: String(data.wss_flv || data.ws_flv || data.https_flv || data.flv || '').trim(),
      hls: String(data.wss_hls || data.ws_hls || data.https_hls || data.hls || '').trim(),
      raw: String(data.url || direct || '').trim()
    }
    if (!urls.webrtc && !urls.flv && !urls.hls && !urls.raw) {
      urls.raw = buildInlineRecordUrl(id)
    }
    emit('play', { urls })
  } catch {
    emit('play', { urls: { raw: buildInlineRecordUrl(id) } })
  }
}

const playDevice = async (item: Record<string, unknown>) => {
  try {
    const rawStart = new Date(item.start_time as string | number | Date).getTime()
    const rawEnd = new Date(item.end_time as string | number | Date).getTime()
    if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd)) {
      ElMessage.warning(t('record.invalidTimeNoPlayback'))
      return
    }
    const start = rawStart / 1000
    const end = rawEnd / 1000
    const res = await api.post(`/api/v1/stream/playback/${props.deviceId}/${props.channelId}`, null, {
      params: {
        start_time: Math.floor(start),
        end_time: Math.floor(end)
      }
    })
    emit('play', {
      app: res.data?.app,
      stream: res.data?.stream,
      codec: res.data?.codec,
      start_time: Math.floor(start),
      end_time: Math.floor(end),
      urls: { webrtc: res.data?.webrtc, flv: res.data?.flv, hls: res.data?.hls }
    })
  } catch (e) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const formatTime = (d: Date | null) => {
  if (!d) return '-'
  return d.toLocaleString()
}

const resetRange = () => {
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 3600 * 1000 * 24)
  dateRange.value = [start, end]
  fetchAll()
}

onMounted(() => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = new Date(props.initialEnd)
    if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) {
      dateRange.value = [s, e]
      return
    }
  }
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 3600 * 1000 * 24)
  dateRange.value = [start, end]
})

watch(() => [props.initialStart, props.initialEnd], () => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = new Date(props.initialEnd)
    if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) {
      dateRange.value = [s, e]
      fetchAll()
    }
  }
})
</script>

<style scoped>
.timeline-row {
  position: relative;
  height: 18px;
  background-color: var(--el-fill-color-light);
  border-radius: 10px;
  overflow: hidden;
}
.segment {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 3px;
  cursor: pointer;
}
.segment.cloud {
  background-color: rgba(59, 130, 246, 0.8);
}
.segment.device {
  background-color: rgba(16, 185, 129, 0.8);
}
.segment:hover {
  opacity: 0.9;
}
.record-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.record-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
</style>
