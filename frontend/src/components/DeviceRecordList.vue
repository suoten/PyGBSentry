<template>
  <div class="p-4 mt-4 rounded-xl" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
    <div class="record-toolbar mb-2">
      <div class="flex items-center gap-2">
        <div class="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,0.16)]"></div>
        <h3 class="text-[15px] font-semibold tracking-wide" style="color: var(--el-text-color-primary)">{{ t('deviceRecordList.title') }}</h3>
        <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('deviceRecordList.subtitle') }}</span>
      </div>
      <div class="record-toolbar-actions">
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          :range-separator="t('deviceRecordList.rangeSeparator')"
          :start-placeholder="t('deviceRecordList.startPlaceholder')"
          :end-placeholder="t('deviceRecordList.endPlaceholder')"
          size="small"
        />
        <el-button type="primary" size="small" :loading="loading" @click="fetchRecords">{{ t('common.query') }}</el-button>
        <el-button size="small" @click="resetRange">{{ t('common.reset') }}</el-button>
      </div>
    </div>

    <div v-if="records.length" class="mb-3 rounded border p-2" style="border-color: var(--el-border-color-lighter)">
      <div class="text-xs mb-2 flex items-center justify-between gap-2" style="color: var(--el-text-color-secondary)">
        <span>{{ t('deviceRecordList.timelineSegmentHint') }}</span>
        <span>{{ currentRecordIndex >= 0 ? t('deviceRecordList.selected', { label: currentRecordLabel }) : t('deviceRecordList.noRecordSelected') }}</span>
      </div>
      <div class="timeline-wrap">
        <div
          v-for="(row, idx) in records"
          :key="recordKey(row)"
          class="timeline-seg"
          :class="{ active: idx === currentRecordIndex }"
          :style="timelineStyle(row)"
          :title="`${formatTime(row.startTime)} - ${formatTime(row.endTime)}`"
          @click="playRecordAt(idx)"
        />
      </div>
      <div class="timeline-axis">
        <span>{{ timelineAxisStart }}</span>
        <span>{{ timelineAxisEnd }}</span>
      </div>
    </div>

    <div v-if="queryStatusText" class="mb-2 text-xs" style="color: var(--el-text-color-secondary)">
      {{ queryStatusText }}
    </div>

    <div v-if="downloadState.stream" class="mb-2 text-xs flex items-center justify-between" style="color: var(--el-text-color-secondary)">
      <div>{{ t('deviceRecordList.downloadTask') }}：{{ downloadStateText }}</div>
      <div class="flex items-center gap-2">
        <el-button size="small" @click="pollDownloadProgress">{{ t('common.refresh') }}</el-button>
        <el-button v-if="downloadState.status === 'pending' || downloadState.status === 'running'" size="small" type="danger" @click="stopDownload">{{ t('deviceRecordList.stop') }}</el-button>
      </div>
    </div>

    <div v-if="downloadState.records.length" class="mb-3 flex flex-wrap gap-2">
      <el-button v-for="item in downloadState.records" :key="item.record_id" size="small" type="success" plain @click="downloadByUrl(item.download_url)">{{ t('deviceRecordList.downloadFile') }}</el-button>
    </div>

    <div class="h-64 overflow-y-auto" v-loading="loading">
      <el-table :data="paginatedRecords" style="width: 100%" size="small" class="record-table" :empty-text="t('deviceRecordList.emptyRecords')">
        <el-table-column prop="startTime" :label="t('deviceRecordList.colStartTime')" width="180">
          <template #default="scope">{{ formatTime(scope.row.startTime) }}</template>
        </el-table-column>
        <el-table-column prop="endTime" :label="t('deviceRecordList.colEndTime')" width="180">
          <template #default="scope">{{ formatTime(scope.row.endTime) }}</template>
        </el-table-column>
        <el-table-column :label="t('deviceRecordList.colDuration')" width="110">
          <template #default="scope">{{ calcDuration(scope.row) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.action')">
          <template #default="scope">
            <div class="flex items-center gap-2">
              <el-button type="primary" size="small" @click="playRecordAt(findRecordIndex(scope.row))">{{ t('deviceRecordList.playback') }}</el-button>
              <el-button type="success" plain size="small" @click="openDownloadDialog(scope.row)">{{ t('common.download') }}</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="mt-4 flex justify-end" v-if="records.length > 0">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper" :total="records.length" />
      </div>
    </div>

    <el-dialog v-model="playbackVisible" :title="t('deviceRecordList.playbackTitle')" width="74%" :destroy-on-close="false" @close="closePlayback">
      <div v-if="playbackUrl">
        <div class="flex items-center justify-between gap-2 mb-2 flex-wrap">
          <div class="text-xs" style="color: var(--el-text-color-secondary)">
            {{ currentRecordLabel }}
          </div>
          <div class="flex items-center gap-2">
            <el-button size="small" :disabled="playbackCtlBusy || currentRecordIndex <= 0" @click="playPrev">{{ t('deviceRecordList.prevRecord') }}</el-button>
            <el-button size="small" :disabled="playbackCtlBusy || currentRecordIndex >= records.length - 1" @click="playNext">{{ t('deviceRecordList.nextRecord') }}</el-button>
            <el-button size="small" :loading="playbackCtlBusy" @click="togglePause">{{ paused ? t('deviceRecordList.resume') : t('deviceRecordList.pause') }}</el-button>
            <el-select v-model="playSpeed" size="small" style="width: 90px" :disabled="playbackCtlBusy" @change="changeSpeed">
              <el-option v-for="sp in speedOptions" :key="sp" :label="`${sp}x`" :value="sp" />
            </el-select>
            <el-button size="small" :disabled="playbackCtlBusy" @click="seekBy(-10)">{{ t('deviceRecordList.rewind10s') }}</el-button>
            <el-button size="small" :disabled="playbackCtlBusy" @click="seekBy(10)">{{ t('deviceRecordList.forward10s') }}</el-button>
          </div>
        </div>
        <div class="text-xs mb-2" style="color: var(--el-text-color-secondary)">
          {{ t('deviceRecordList.shortcutHint') }}
        </div>
        <div class="playback-progress-wrap">
          <el-slider
            :model-value="playSeekCursor"
            :min="playbackRange.min"
            :max="playbackRange.max"
            :step="1"
            :disabled="playbackCtlBusy || !playbackRange.valid"
            @change="onSeekSliderChange"
          />
          <div class="playback-progress-meta">
            <span>{{ playbackCursorLabel }}</span>
            <span>{{ playbackDurationLabel }}</span>
          </div>
        </div>
        <div style="height: 420px; background: #000;">
          <EnhancedStreamPlayer
            :video-url="playbackUrl"
            :hls-url="playbackHlsUrl"
            :candidates="playbackUrl ? [playbackUrl] : []"
            :codec="playbackCodec"
            :show-controls="true"
            :is-playback="true"
            :start-time="playbackStartTime"
            :duration="playbackDuration"
          />
        </div>
      </div>
      <div v-else class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('deviceRecordList.noPlaybackUrl') }}</div>
    </el-dialog>

    <el-dialog v-model="downloadDialogVisible" :title="t('deviceRecordList.downloadTitle')" width="560px">
      <div class="text-sm mb-3" style="color: var(--el-text-color-secondary)">
        {{ downloadTargetLabel }}
      </div>
      <el-form label-width="120px" size="small">
        <el-form-item :label="t('deviceRecordList.downloadSpeed')">
          <el-select v-model="downloadSpeed" style="width: 140px">
            <el-option v-for="sp in [1,2,4,8]" :key="sp" :label="`${sp}x`" :value="sp" />
          </el-select>
        </el-form-item>
      </el-form>
      <div v-if="downloadState.stream" class="rounded border p-3 mt-2" style="border-color: var(--el-border-color-lighter)">
        <div class="text-xs mb-2" style="color: var(--el-text-color-secondary)">
          {{ t('deviceRecordList.taskStatus') }}：{{ downloadStateText }}
        </div>
        <el-progress
          :percentage="Number(downloadState.progress || 0)"
          :status="downloadState.status === 'failed' ? 'exception' : (downloadState.status === 'done' ? 'success' : undefined)"
          :stroke-width="10"
        />
        <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">
          {{ downloadProgressText }}
        </div>
        <div v-if="downloadState.lastError" class="text-xs mt-1" style="color: var(--el-color-danger)">
          {{ t('deviceRecordList.failureReason') }}：{{ downloadState.lastError }}
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <el-button size="small" @click="pollDownloadProgress">{{ t('deviceRecordList.refreshProgress') }}</el-button>
          <el-button
            v-if="downloadState.status === 'pending' || downloadState.status === 'running'"
            size="small"
            type="danger"
            @click="stopDownload"
          >
            {{ t('deviceRecordList.stopTask') }}
          </el-button>
          <el-button
            v-if="downloadState.status === 'failed' && !isDownloadTaskActive"
            size="small"
            type="warning"
            @click="retryDownload"
          >
            {{ t('deviceRecordList.retryDownload') }}
          </el-button>
          <el-button
            v-if="!isDownloadTaskActive"
            size="small"
            @click="clearDownloadState"
          >
            {{ t('deviceRecordList.clearTask') }}
          </el-button>
        </div>
        <div v-if="downloadRetryTip" class="text-xs mt-2" style="color: var(--el-text-color-secondary)">
          {{ downloadRetryTip }}
        </div>
      </div>
      <div v-if="downloadState.records.length > 1" class="mt-3">
        <el-button size="small" type="primary" @click="downloadAllReadyFiles">
          {{ t('deviceRecordList.downloadAll', { count: downloadState.records.length }) }}
        </el-button>
      </div>
      <div v-if="downloadState.records.length" class="mt-3 flex flex-wrap gap-2">
        <el-button
          v-for="item in downloadState.records"
          :key="item.record_id"
          size="small"
          type="success"
          plain
          @click="downloadByUrl(item.download_url)"
        >
          {{ t('deviceRecordList.downloadFile') }}
        </el-button>
      </div>
      <template #footer>
        <el-button @click="downloadDialogVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="primary" :disabled="isDownloadTaskActive" :loading="downloadRowKey !== ''" @click="confirmStartDownload">{{ t('deviceRecordList.startDownload') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError, getApiErrorMessage } from '../utils/errorMessage'
import { showSuccess } from '@/utils/feedback'
import EnhancedStreamPlayer from './EnhancedStreamPlayer.vue'

const { t } = useI18n()

const props = defineProps<{
  deviceId: string
  channelId: string
  initialStart?: string
  initialEnd?: string
}>()

const emit = defineEmits(['play-record'])
type DateRange = [Date, Date]
type RecordItem = { startTime: string; endTime: string; type?: string; name?: string }

const records = ref<RecordItem[]>([])
const dateRange = ref<DateRange | []>([])
const loading = ref(false)
const queryStatusText = ref('')
const page = ref(1)
const pageSize = ref(10)

const playbackVisible = ref(false)
const playbackApp = ref('playback')
const playbackStream = ref('')
const playbackUrl = ref('')
const playbackHlsUrl = ref('')
const playbackCodec = ref('')
const paused = ref(false)
const playSpeed = ref(1)
const playSeekCursor = ref(0)
const playbackCtlBusy = ref(false)
const playbackTickTimer = ref<number | null>(null)
const playbackLastTickAt = ref(0)
const currentRecordIndex = ref(-1)
const speedOptions = [0.25, 0.5, 1, 2, 4, 8]

const downloadDialogVisible = ref(false)
const downloadSpeed = ref(4)
const downloadTarget = ref<RecordItem | null>(null)
const downloadTimer = ref<number | null>(null)
const downloadRetryTimer = ref<number | null>(null)
const downloadRetryCount = ref(0)
const downloadRowKey = ref('')
const downloadState = ref<{ app: string; stream: string; status: string; progress: number; records: Array<{ record_id: string; download_url: string }>; recordedSeconds: number; totalSeconds: number; lastError: string }>({
  app: '',
  stream: '',
  status: '',
  progress: 0,
  records: [],
  recordedSeconds: 0,
  totalSeconds: 0,
  lastError: ''
})

const paginatedRecords = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return records.value.slice(start, start + pageSize.value)
})

const timelineRange = computed(() => {
  if (!records.value.length) return { start: 0, end: 0, span: 1 }
  const starts = records.value.map(r => new Date(normalizeDateTime(r.startTime)).getTime()).filter(Number.isFinite)
  const ends = records.value.map(r => new Date(normalizeDateTime(r.endTime)).getTime()).filter(Number.isFinite)
  const start = Math.min(...starts)
  const end = Math.max(...ends)
  return { start, end, span: Math.max(1, end - start) }
})

const downloadStateText = computed(() => {
  const status = String(downloadState.value.status || '')
  const progress = Number(downloadState.value.progress || 0)
  if (!status) return '-'
  if (status === 'done') return t('deviceRecordList.stateDone')
  if (status === 'running') return t('deviceRecordList.stateRunning', { progress })
  if (status === 'pending') return t('deviceRecordList.statePending')
  if (status === 'cancelled') return t('deviceRecordList.stateCancelled')
  if (status === 'failed') return t('deviceRecordList.stateFailed')
  return status
})

const currentRecordLabel = computed(() => {
  const row = records.value[currentRecordIndex.value]
  if (!row) return t('deviceRecordList.noRecordSelected')
  return `${formatTime(row.startTime)} - ${formatTime(row.endTime)}`
})

const timelineAxisStart = computed(() => {
  if (!records.value.length) return '-'
  return formatTime(new Date(timelineRange.value.start).toISOString())
})

const timelineAxisEnd = computed(() => {
  if (!records.value.length) return '-'
  return formatTime(new Date(timelineRange.value.end).toISOString())
})

const playbackRange = computed(() => {
  const row = records.value[currentRecordIndex.value]
  if (!row) return { valid: false, min: 0, max: 1 }
  const min = Math.floor(new Date(normalizeDateTime(row.startTime)).getTime() / 1000)
  const max = Math.floor(new Date(normalizeDateTime(row.endTime)).getTime() / 1000)
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return { valid: false, min: 0, max: 1 }
  return { valid: true, min, max }
})

const playbackCursorLabel = computed(() => {
  if (!playbackRange.value.valid) return '-'
  return formatTime(new Date(Math.floor(playSeekCursor.value) * 1000).toISOString())
})

const playbackDurationLabel = computed(() => {
  if (!playbackRange.value.valid) return '-'
  const total = Math.max(0, playbackRange.value.max - playbackRange.value.min)
  const current = Math.max(0, Math.min(total, Math.floor(playSeekCursor.value) - playbackRange.value.min))
  return `${current}s / ${total}s`
})

// 回放进度/跳转由服务端 API 控制（seek/pause/speed），本地播放器不做初始 seek；
// 这里仅为模板引用补齐定义，取值保持与组件默认值一致（0），维持既有运行时行为
const playbackStartTime = computed(() => 0)
const playbackDuration = computed(() => 0)

const downloadTargetLabel = computed(() => {
  if (!downloadTarget.value) return t('deviceRecordList.noRecordSelected')
  return `${formatTime(downloadTarget.value.startTime)} - ${formatTime(downloadTarget.value.endTime)}`
})

const isDownloadTaskActive = computed(() => {
  const s = String(downloadState.value.status || '')
  return !!downloadState.value.stream && (s === 'pending' || s === 'running')
})

const downloadProgressText = computed(() => {
  const rec = Math.max(0, Number(downloadState.value.recordedSeconds || 0))
  const total = Math.max(0, Number(downloadState.value.totalSeconds || 0))
  if (total <= 0) return t('deviceRecordList.progressGenerating')
  return t('deviceRecordList.progressRecorded', { rec, total })
})

const downloadRetryTip = computed(() => {
  if (!isDownloadTaskActive.value || downloadRetryCount.value <= 0) return ''
  return t('deviceRecordList.retryTip', { count: downloadRetryCount.value })
})

const fetchRecords = async () => {
  if (!Array.isArray(dateRange.value) || dateRange.value.length < 2) return
  loading.value = true
  queryStatusText.value = t('deviceRecordList.queryingRecords')
  try {
    const [startDate, endDate] = dateRange.value as DateRange
    const res = await api.get(`/api/v1/gb-record/query/${encodeURIComponent(props.deviceId)}/${encodeURIComponent(props.channelId)}`, {
      params: { startTime: toRecordDateTime(startDate), endTime: toRecordDateTime(endDate) }
    })
    const recordList = res.data?.data?.recordList
    const list = Array.isArray(recordList) ? recordList : []
    records.value = list.map((item: Record<string, unknown>) => ({
      startTime: String(item?.startTime || ''),
      endTime: String(item?.endTime || ''),
      type: String(item?.type || ''),
      name: String(item?.name || '')
    }))
    queryStatusText.value = t('deviceRecordList.queryCompleted', { count: records.value.length })
  } catch (error) {
    const friendly = getFriendlyError(error)
    queryStatusText.value = t('deviceRecordList.queryFailed', { message: friendly.message })
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    records.value = []
  } finally {
    loading.value = false
  }
}

const findRecordIndex = (row: RecordItem) => records.value.findIndex(i => recordKey(i) === recordKey(row))

const playRecordAt = async (idx: number) => {
  if (idx < 0 || idx >= records.value.length) return
  const row = records.value[idx]
  try {
    const start = Math.floor(new Date(normalizeDateTime(row.startTime)).getTime() / 1000)
    const end = Math.floor(new Date(normalizeDateTime(row.endTime)).getTime() / 1000)
    const res = await api.post(`/api/v1/stream/playback/${props.deviceId}/${props.channelId}`, null, {
      params: { start_time: start, end_time: end }
    })
    currentRecordIndex.value = idx
    playbackApp.value = String(res.data?.app || 'playback')
    playbackStream.value = String(res.data?.stream || '')
    playbackUrl.value = String(res.data?.webrtc || res.data?.flv || res.data?.hls || '')
    playbackHlsUrl.value = String(res.data?.hls || '')
    playbackCodec.value = String(res.data?.codec || '')
    paused.value = false
    playSpeed.value = 1
    playSeekCursor.value = start
    playbackVisible.value = true
    showSuccess(t('deviceRecordList.playbackStarted'))
    emit('play-record', { index: idx, app: playbackApp.value, stream: playbackStream.value })
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const playPrev = async () => {
  if (currentRecordIndex.value <= 0) return
  await playRecordAt(currentRecordIndex.value - 1)
}

const playNext = async () => {
  if (currentRecordIndex.value >= records.value.length - 1) return
  await playRecordAt(currentRecordIndex.value + 1)
}

const controlPlayback = async (path: string, payload: Record<string, unknown>) => {
  if (!playbackApp.value || !playbackStream.value) return
  try {
    await api.post(path, payload)
    showSuccess(t('deviceRecordList.operationSuccess'))
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, t('deviceRecordList.playbackControlFailed')))
  }
}

const withPlaybackControl = async (handler: () => Promise<void>) => {
  if (playbackCtlBusy.value) return
  playbackCtlBusy.value = true
  try {
    await handler()
  } finally {
    playbackCtlBusy.value = false
  }
}

const touchPlaybackTicker = () => {
  playbackLastTickAt.value = Date.now()
}

const stopPlaybackTicker = () => {
  if (playbackTickTimer.value != null) {
    window.clearInterval(playbackTickTimer.value)
    playbackTickTimer.value = null
  }
}

const startPlaybackTicker = () => {
  stopPlaybackTicker()
  touchPlaybackTicker()
  playbackTickTimer.value = window.setInterval(() => {
    if (!playbackVisible.value || paused.value || !playbackRange.value.valid) {
      touchPlaybackTicker()
      return
    }
    const now = Date.now()
    const delta = Math.max(0, (now - playbackLastTickAt.value) / 1000)
    playbackLastTickAt.value = now
    const next = playSeekCursor.value + delta * Number(playSpeed.value || 1)
    playSeekCursor.value = Math.max(playbackRange.value.min, Math.min(playbackRange.value.max, next))
  }, 300)
}

const togglePause = async () => {
  if (!playbackApp.value || !playbackStream.value) return
  try {
    await withPlaybackControl(async () => {
      if (paused.value) {
        await controlPlayback('/api/v1/stream/playback/resume', { app: playbackApp.value, stream: playbackStream.value })
        paused.value = false
        touchPlaybackTicker()
      } else {
        await controlPlayback('/api/v1/stream/playback/pause', { app: playbackApp.value, stream: playbackStream.value })
        paused.value = true
      }
    })
  } catch (error) {
    ElMessage.warning(getFriendlyError(error).message)
  }
}

const changeSpeed = async () => {
  try {
    await withPlaybackControl(async () => {
      await controlPlayback('/api/v1/stream/playback/speed', { app: playbackApp.value, stream: playbackStream.value, speed: Number(playSpeed.value) })
      touchPlaybackTicker()
    })
  } catch (error) {
    ElMessage.warning(getFriendlyError(error).message)
  }
}

const seekTo = async (targetSec: number) => {
  if (!playbackRange.value.valid) return
  const clamped = Math.max(playbackRange.value.min, Math.min(playbackRange.value.max, Math.floor(targetSec)))
  playSeekCursor.value = clamped
  await withPlaybackControl(async () => {
    await controlPlayback('/api/v1/stream/playback/seek', { app: playbackApp.value, stream: playbackStream.value, seek_time: clamped })
    touchPlaybackTicker()
  })
}

const onSeekSliderChange = async (value: number | number[]) => {
  if (Array.isArray(value)) return
  try {
    await seekTo(Number(value || 0))
  } catch (error) {
    ElMessage.warning(getFriendlyError(error).message)
  }
}

const seekBy = async (deltaSec: number) => {
  if (!playbackRange.value.valid) return
  const next = playSeekCursor.value + deltaSec
  try {
    await seekTo(next)
  } catch (error) {
    ElMessage.warning(getFriendlyError(error).message)
  }
}

const closePlayback = async () => {
  if (playbackApp.value && playbackStream.value) {
    try {
      await api.post('/api/v1/stream/stop', { app: playbackApp.value, stream: playbackStream.value })
    } catch { /* cleanup: ignore */ }
  }
  playbackStream.value = ''
  playbackUrl.value = ''
  playbackHlsUrl.value = ''
  playbackCodec.value = ''
  paused.value = false
  playbackCtlBusy.value = false
  stopPlaybackTicker()
}

const openDownloadDialog = (row: RecordItem) => {
  downloadTarget.value = row
  downloadSpeed.value = 4
  downloadDialogVisible.value = true
  if (downloadState.value.stream) void pollDownloadProgress()
}

const confirmStartDownload = async () => {
  if (!downloadTarget.value) return
  const row = downloadTarget.value
  downloadRowKey.value = recordKey(row)
  try {
    const res = await api.get(`/api/v1/gb-record/download/start/${encodeURIComponent(props.deviceId)}/${encodeURIComponent(props.channelId)}`, {
      params: {
        startTime: String(row.startTime || ''),
        endTime: String(row.endTime || ''),
        downloadSpeed: Number(downloadSpeed.value || 4)
      }
    })
    downloadState.value = {
      app: String(res.data?.data?.app || 'playback'),
      stream: String(res.data?.data?.stream || ''),
      status: String(res.data?.data?.status || 'pending'),
      progress: 0,
      records: [],
      recordedSeconds: 0,
      totalSeconds: 0,
      lastError: ''
    }
    downloadRetryCount.value = 0
    await pollDownloadProgress()
    startDownloadPolling()
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    downloadRowKey.value = ''
  }
}

const pollDownloadProgress = async () => {
  if (!downloadState.value.stream) return
  try {
    const res = await api.get(`/api/v1/gb-record/download/progress/${encodeURIComponent(props.deviceId)}/${encodeURIComponent(props.channelId)}/${encodeURIComponent(downloadState.value.stream)}`)
    const data = res.data?.data || {}
    downloadState.value = {
      app: String(data.app || downloadState.value.app || 'playback'),
      stream: String(data.stream || downloadState.value.stream || ''),
      status: String(data.status || ''),
      progress: Number(data.progress || 0),
      records: Array.isArray(data.records) ? data.records : [],
      recordedSeconds: Number(data.recordedSeconds || 0),
      totalSeconds: Number(data.totalSeconds || 0),
      lastError: String(data.lastError || '')
    }
    downloadRetryCount.value = 0
    clearDownloadRetry()
    if (['done', 'cancelled', 'failed'].includes(downloadState.value.status)) stopDownloadPolling()
  } catch (error) {
    stopDownloadPolling()
    scheduleDownloadPollRetry()
  }
}

const retryDownload = async () => {
  if (!downloadTarget.value) return
  await confirmStartDownload()
}

const clearDownloadState = () => {
  stopDownloadPolling()
  clearDownloadRetry()
  downloadRetryCount.value = 0
  downloadState.value = {
    app: '',
    stream: '',
    status: '',
    progress: 0,
    records: [],
    recordedSeconds: 0,
    totalSeconds: 0,
    lastError: ''
  }
}

const stopDownload = async () => {
  if (!downloadState.value.stream) return
  try {
    await api.get(`/api/v1/gb-record/download/stop/${encodeURIComponent(props.deviceId)}/${encodeURIComponent(props.channelId)}/${encodeURIComponent(downloadState.value.stream)}`)
    await pollDownloadProgress()
  } finally {
    stopDownloadPolling()
    clearDownloadRetry()
    downloadRetryCount.value = 0
  }
}

const downloadByUrl = (url: string) => {
  const u = String(url || '').trim()
  if (!u) return
  window.open(u, '_blank', 'noopener,noreferrer')
}

const startDownloadPolling = () => {
  stopDownloadPolling()
  clearDownloadRetry()
  downloadTimer.value = window.setInterval(() => void pollDownloadProgress(), 1500)
}

const stopDownloadPolling = () => {
  if (downloadTimer.value != null) {
    window.clearInterval(downloadTimer.value)
    downloadTimer.value = null
  }
}

const clearDownloadRetry = () => {
  if (downloadRetryTimer.value != null) {
    window.clearTimeout(downloadRetryTimer.value)
    downloadRetryTimer.value = null
  }
}

const scheduleDownloadPollRetry = () => {
  if (!isDownloadTaskActive.value) return
  const maxRetries = 5
  if (downloadRetryCount.value >= maxRetries) {
    ElMessage.warning(t('deviceRecordList.pollRetryFailedHint'))
    return
  }
  downloadRetryCount.value += 1
  const delayMs = Math.min(8000, 1000 * (2 ** (downloadRetryCount.value - 1)))
  clearDownloadRetry()
  downloadRetryTimer.value = window.setTimeout(() => {
    downloadRetryTimer.value = null
    void pollDownloadProgress()
  }, delayMs)
}

const downloadAllReadyFiles = () => {
  const items = Array.isArray(downloadState.value.records) ? downloadState.value.records : []
  if (!items.length) return
  items.forEach((item, idx) => {
    window.setTimeout(() => downloadByUrl(String(item.download_url || '')), idx * 180)
  })
}

const timelineStyle = (row: RecordItem) => {
  const st = new Date(normalizeDateTime(row.startTime)).getTime()
  const et = new Date(normalizeDateTime(row.endTime)).getTime()
  const left = ((st - timelineRange.value.start) / timelineRange.value.span) * 100
  const width = Math.max(0.8, ((et - st) / timelineRange.value.span) * 100)
  return { left: `${Math.max(0, left)}%`, width: `${Math.min(100, width)}%` }
}

const recordKey = (row: RecordItem) => `${String(row?.startTime || '')}_${String(row?.endTime || '')}`
const normalizeDateTime = (value: string) => String(value || '').replace(' ', 'T')
const pad2 = (n: number) => String(n).padStart(2, '0')
const toRecordDateTime = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
const formatTime = (isoString: string) => new Date(normalizeDateTime(isoString)).toLocaleString()

const calcDuration = (row: RecordItem) => {
  const st = new Date(normalizeDateTime(String(row?.startTime || ''))).getTime()
  const et = new Date(normalizeDateTime(String(row?.endTime || ''))).getTime()
  if (!Number.isFinite(st) || !Number.isFinite(et) || et <= st) return '-'
  const sec = Math.floor((et - st) / 1000)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

const resetRange = () => {
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 24 * 3600 * 1000)
  dateRange.value = [start, end]
  void fetchRecords()
}

watch(() => records.value, () => { page.value = 1 })

onMounted(() => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = new Date(props.initialEnd)
    if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) dateRange.value = [s, e]
  }
  if (!dateRange.value || dateRange.value.length < 2) {
    const end = new Date()
    const start = new Date()
    start.setTime(start.getTime() - 24 * 3600 * 1000)
    dateRange.value = [start, end]
  }
  if (props.deviceId && props.channelId) void fetchRecords()
})

watch(() => [props.initialStart, props.initialEnd], () => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = new Date(props.initialEnd)
    if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) dateRange.value = [s, e]
  }
})

const onPlaybackKeydown = (event: KeyboardEvent) => {
  if (!playbackVisible.value) return
  const target = event.target as HTMLElement | null
  const tag = String(target?.tagName || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea') return
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    void playPrev()
    return
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    void playNext()
    return
  }
  if (event.code === 'Space') {
    event.preventDefault()
    void togglePause()
  }
}

watch(() => props.channelId, () => {
  clearDownloadState()
  stopDownloadPolling()
  currentRecordIndex.value = -1
  playbackVisible.value = false
  void fetchRecords()
})

watch(() => playbackVisible.value, (visible) => {
  if (visible) {
    window.addEventListener('keydown', onPlaybackKeydown)
    startPlaybackTicker()
  } else {
    window.removeEventListener('keydown', onPlaybackKeydown)
    stopPlaybackTicker()
  }
})

onBeforeUnmount(() => {
  stopDownloadPolling()
  clearDownloadRetry()
  stopPlaybackTicker()
  window.removeEventListener('keydown', onPlaybackKeydown)
  void closePlayback()
})
</script>

<style scoped>
:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}
:deep(.el-table__row:hover) {
  background-color: var(--el-fill-color-light) !important;
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
.timeline-wrap {
  position: relative;
  height: 24px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  overflow: hidden;
}
.timeline-seg {
  position: absolute;
  top: 3px;
  height: 18px;
  border-radius: 4px;
  background: rgba(56, 189, 248, 0.55);
  cursor: pointer;
  transition: all .15s ease;
}
.timeline-seg:hover {
  background: rgba(56, 189, 248, 0.85);
}
.timeline-seg.active {
  background: rgba(59, 130, 246, 0.95);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.65);
}
.timeline-axis {
  margin-top: 6px;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.playback-progress-wrap {
  margin-bottom: 8px;
  padding: 8px 10px 4px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
}
.playback-progress-meta {
  margin-top: -2px;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
