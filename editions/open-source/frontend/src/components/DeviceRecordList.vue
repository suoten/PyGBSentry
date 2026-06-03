<template>
  <div class="p-4 mt-4 rounded-xl" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
    <div class="record-toolbar mb-2">
      <div class="flex items-center gap-2">
        <div class="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,0.16)]"></div>
        <h3 class="text-[15px] font-semibold tracking-wide" style="color: var(--el-text-color-primary)">设备录像</h3>
        <span class="text-xs" style="color: var(--el-text-color-secondary)">设备录像查询/回放/下载</span>
      </div>
      <div class="record-toolbar-actions">
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          size="small"
        />
        <el-button type="primary" size="small" :loading="loading" @click="fetchRecords">查询</el-button>
        <el-button size="small" @click="resetRange">重置</el-button>
      </div>
    </div>

    <div v-if="records.length" class="mb-3 rounded border p-2" style="border-color: var(--el-border-color-lighter)">
      <div class="text-xs mb-2 flex items-center justify-between gap-2" style="color: var(--el-text-color-secondary)">
        <span>时间轴分段（点击可回放）</span>
        <span>{{ currentRecordIndex >= 0 ? `已选：${currentRecordLabel}` : '未选择录像' }}</span>
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
      <div>下载任务：{{ downloadStateText }}</div>
      <div class="flex items-center gap-2">
        <el-button size="small" @click="pollDownloadProgress">刷新</el-button>
        <el-button v-if="downloadState.status === 'pending' || downloadState.status === 'running'" size="small" type="danger" @click="stopDownload">停止</el-button>
      </div>
    </div>

    <div v-if="downloadState.records.length" class="mb-3 flex flex-wrap gap-2">
      <el-button v-for="item in downloadState.records" :key="item.record_id" size="small" type="success" plain @click="downloadByUrl(item.download_url)">下载文件</el-button>
    </div>

    <div class="h-64 overflow-y-auto" v-loading="loading">
      <el-table :data="paginatedRecords" style="width: 100%" size="small" class="record-table" empty-text="当前时间范围暂无设备录像">
        <el-table-column prop="startTime" label="开始时间" width="180">
          <template #default="scope">{{ formatTime(scope.row.startTime) }}</template>
        </el-table-column>
        <el-table-column prop="endTime" label="结束时间" width="180">
          <template #default="scope">{{ formatTime(scope.row.endTime) }}</template>
        </el-table-column>
        <el-table-column label="时长" width="110">
          <template #default="scope">{{ calcDuration(scope.row) }}</template>
        </el-table-column>
        <el-table-column label="操作">
          <template #default="scope">
            <div class="flex items-center gap-2">
              <el-button type="primary" size="small" @click="playRecordAt(findRecordIndex(scope.row))">回放</el-button>
              <el-button type="success" plain size="small" @click="openDownloadDialog(scope.row)">下载</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="mt-4 flex justify-end" v-if="records.length > 0">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper" :total="records.length" />
      </div>
    </div>

    <el-dialog v-model="playbackVisible" title="录像回放" width="74%" :destroy-on-close="false" @close="closePlayback">
      <div v-if="playbackUrl">
        <div class="flex items-center justify-between gap-2 mb-2 flex-wrap">
          <div class="text-xs" style="color: var(--el-text-color-secondary)">
            {{ currentRecordLabel }}
          </div>
          <div class="flex items-center gap-2">
            <el-button size="small" :disabled="playbackCtlBusy || currentRecordIndex <= 0" @click="playPrev">上一条</el-button>
            <el-button size="small" :disabled="playbackCtlBusy || currentRecordIndex >= records.length - 1" @click="playNext">下一条</el-button>
            <el-button size="small" :loading="playbackCtlBusy" @click="togglePause">{{ paused ? '继续' : '暂停' }}</el-button>
            <el-select v-model="playSpeed" size="small" style="width: 90px" :disabled="playbackCtlBusy" @change="changeSpeed">
              <el-option v-for="sp in speedOptions" :key="sp" :label="`${sp}x`" :value="sp" />
            </el-select>
            <el-button size="small" :disabled="playbackCtlBusy" @click="seekBy(-10)">快退10s</el-button>
            <el-button size="small" :disabled="playbackCtlBusy" @click="seekBy(10)">快进10s</el-button>
          </div>
        </div>
        <div class="text-xs mb-2" style="color: var(--el-text-color-secondary)">
          快捷键：`←/→` 切换上一条/下一条，`Space` 暂停或继续
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
      <div v-else class="text-sm" style="color: var(--el-text-color-secondary)">暂无可用回放地址</div>
    </el-dialog>

    <el-dialog v-model="downloadDialogVisible" title="下载录像" width="560px">
      <div class="text-sm mb-3" style="color: var(--el-text-color-secondary)">
        {{ downloadTargetLabel }}
      </div>
      <el-form label-width="120px" size="small">
        <el-form-item label="下载倍速">
          <el-select v-model="downloadSpeed" style="width: 140px">
            <el-option v-for="sp in [1,2,4,8]" :key="sp" :label="`${sp}x`" :value="sp" />
          </el-select>
        </el-form-item>
      </el-form>
      <div v-if="downloadState.stream" class="rounded border p-3 mt-2" style="border-color: var(--el-border-color-lighter)">
        <div class="text-xs mb-2" style="color: var(--el-text-color-secondary)">
          任务状态：{{ downloadStateText }}
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
          失败原因：{{ downloadState.lastError }}
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <el-button size="small" @click="pollDownloadProgress">刷新进度</el-button>
          <el-button
            v-if="downloadState.status === 'pending' || downloadState.status === 'running'"
            size="small"
            type="danger"
            @click="stopDownload"
          >
            停止任务
          </el-button>
          <el-button
            v-if="downloadState.status === 'failed' && !isDownloadTaskActive"
            size="small"
            type="warning"
            @click="retryDownload"
          >
            重试下载
          </el-button>
          <el-button
            v-if="!isDownloadTaskActive"
            size="small"
            @click="clearDownloadState"
          >
            清空任务
          </el-button>
        </div>
        <div v-if="downloadRetryTip" class="text-xs mt-2" style="color: var(--el-text-color-secondary)">
          {{ downloadRetryTip }}
        </div>
      </div>
      <div v-if="downloadState.records.length > 1" class="mt-3">
        <el-button size="small" type="primary" @click="downloadAllReadyFiles">
          一键下载全部（{{ downloadState.records.length }}）
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
          下载文件
        </el-button>
      </div>
      <template #footer>
        <el-button @click="downloadDialogVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="isDownloadTaskActive" :loading="downloadRowKey !== ''" @click="confirmStartDownload">开始下载</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError, getApiErrorMessage } from '../utils/errorMessage'
import { showSuccess } from '@/utils/feedback'
import EnhancedStreamPlayer from './EnhancedStreamPlayer.vue'

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
  if (status === 'done') return '完成'
  if (status === 'running') return `进行中（${progress}%）`
  if (status === 'pending') return '等待设备响应'
  if (status === 'cancelled') return '已停止'
  if (status === 'failed') return '失败'
  return status
})

const currentRecordLabel = computed(() => {
  const row = records.value[currentRecordIndex.value]
  if (!row) return '未选择录像'
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

const downloadTargetLabel = computed(() => {
  if (!downloadTarget.value) return '未选择录像'
  return `${formatTime(downloadTarget.value.startTime)} - ${formatTime(downloadTarget.value.endTime)}`
})

const isDownloadTaskActive = computed(() => {
  const s = String(downloadState.value.status || '')
  return !!downloadState.value.stream && (s === 'pending' || s === 'running')
})

const downloadProgressText = computed(() => {
  const rec = Math.max(0, Number(downloadState.value.recordedSeconds || 0))
  const total = Math.max(0, Number(downloadState.value.totalSeconds || 0))
  if (total <= 0) return '设备录像正在生成下载片段...'
  return `已录制 ${rec}s / 目标 ${total}s`
})

const downloadRetryTip = computed(() => {
  if (!isDownloadTaskActive.value || downloadRetryCount.value <= 0) return ''
  return `网络波动，正在自动重试进度查询（第 ${downloadRetryCount.value} 次）`
})

const fetchRecords = async () => {
  if (!Array.isArray(dateRange.value) || dateRange.value.length < 2) return
  loading.value = true
  queryStatusText.value = '正在查询设备录像...'
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
    queryStatusText.value = `查询完成，共 ${records.value.length} 条录像`
  } catch (error) {
    const friendly = getFriendlyError(error)
    queryStatusText.value = `查询失败：${friendly.message}`
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
    showSuccess('录像回放已开始')
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
    showSuccess('操作成功')
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '录像播放/暂停/快进控制失败，请检查设备在线状态与回放协议'))
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
    ElMessage.warning('下载进度查询失败，请稍后手动点击“刷新进度”')
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
