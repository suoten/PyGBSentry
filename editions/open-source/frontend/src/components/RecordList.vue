<template>
  <div class="p-4 mt-4 rounded-xl record-panel" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
    <div class="record-toolbar mb-3">
      <div class="flex items-center gap-2 min-w-[220px]">
        <div class="w-2.5 h-2.5 rounded-full bg-sky-400 shadow-[0_0_0_4px_rgba(56,189,248,0.18)]"></div>
        <h3 class="text-[15px] font-semibold tracking-wide" style="color: var(--el-text-color-primary)">云端录像</h3>
        <span class="text-xs" style="color: var(--el-text-color-secondary)">按时间范围查询与回放</span>
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
        <el-button type="primary" size="small" @click="fetchRecords">查询</el-button>
        <el-button size="small" @click="resetRange">重置</el-button>
      </div>
    </div>
    
    <div class="rounded-xl" style="border: 1px solid var(--el-border-color-lighter);">
      <el-table
        :data="records"
        style="width: 100%"
        size="small"
        :row-class-name="tableRowClassName"
        class="record-table"
        empty-text="当前时间范围暂无云端录像"
        :max-height="300"
        table-layout="auto"
      >
        <el-table-column prop="start_time" label="开始时间" min-width="220">
          <template #default="scope">
            {{ (() => { const d = new Date(scope.row.start_time); return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString() })() }}
          </template>
        </el-table-column>
        <el-table-column label="时长（秒）" width="110">
          <template #default="scope">
            {{ formatDuration(scope.row.duration) }}
          </template>
        </el-table-column>
        <el-table-column prop="file_size" label="大小" width="110">
          <template #default="scope">
            {{ (scope.row.file_size / 1024 / 1024).toFixed(2) }} MB
          </template>
        </el-table-column>
        <el-table-column label="操作" width="138" align="center">
          <template #default="scope">
            <el-button type="primary" size="small" @click="play(scope.row)">回放</el-button>
            <el-button size="small" @click="download(scope.row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="flex justify-end mt-2">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="hasMore ? page * pageSize + 1 : page * pageSize"
        layout="total, sizes, prev, pager, next, jumper"
        :page-sizes="[10, 20, 50, 100]"
        prev-text="上一页"
        next-text="下一页"
        size="small"
        @current-change="fetchRecords"
        @size-change="() => { page = 1; fetchRecords() }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'

const props = defineProps<{
  deviceId: string
  channelId: string
  initialStart?: string
  initialEnd?: string
}>()

const emit = defineEmits(['play'])

type CloudRecord = {
  id: string
  start_time: string
  duration: number
  file_size: number
  file_path: string
}
type DateRange = [Date, Date]

const records = ref<CloudRecord[]>([])
const dateRange = ref<DateRange | []>([])
const page = ref(1)
const pageSize = ref(10)
const hasMore = ref(false)

const fetchRecords = async () => {
  if (!Array.isArray(dateRange.value) || dateRange.value.length < 2) return
  
  try {
    const [startDate, endDate] = dateRange.value as DateRange
    const start = startDate.toISOString()
    const end = endDate.toISOString()
    
    const res = await api.get('/api/v1/record/query', {
      params: {
        device_id: props.deviceId,
        channel_id: props.channelId,
        start_time: start,
        end_time: end,
        skip: (page.value - 1) * pageSize.value,
        limit: pageSize.value + 1
      }
    })
    const list = Array.isArray(res.data) ? (res.data as CloudRecord[]) : []
    hasMore.value = list.length > pageSize.value
    records.value = hasMore.value ? list.slice(0, pageSize.value) : list
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    records.value = []
    hasMore.value = false
  }
}

// Initial load: Last 24 hours
onMounted(() => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = new Date(props.initialEnd)
    if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) {
      dateRange.value = [s, e]
    }
  }
  if (!Array.isArray(dateRange.value) || dateRange.value.length < 2) {
    const end = new Date()
    const start = new Date()
    start.setTime(start.getTime() - 3600 * 1000 * 24)
    dateRange.value = [start, end]
  }
  
  if (props.deviceId && props.channelId) {
    fetchRecords()
  }
})

watch(() => props.channelId, () => {
  page.value = 1
  fetchRecords()
})

watch(() => [props.initialStart, props.initialEnd], () => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = new Date(props.initialEnd)
    if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) {
      page.value = 1
      dateRange.value = [s, e]
      fetchRecords()
    }
  }
})

const tableRowClassName = ({ rowIndex }: { rowIndex: number }) => {
  if (rowIndex % 2 === 0) {
    return 'warning-row'
  }
  return ''
}

const formatDuration = (v: unknown) => {
  const n = Number(v || 0)
  if (!Number.isFinite(n) || n <= 0) return '0.00'
  return n.toFixed(2)
}

const resetRange = () => {
  page.value = 1
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 3600 * 1000 * 24)
  dateRange.value = [start, end]
  fetchRecords()
}

const download = (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) {
    ElMessage.warning('缺少录像ID')
    return
  }
  window.open(`/api/v1/record/download/${id}`, '_blank')
}

const buildInlineRecordUrl = (id: string) => {
  const token = (() => { try { return localStorage.getItem('token') || '' } catch { return '' } })()
  return `/api/v1/record/download/${encodeURIComponent(id)}?inline=true&token=${encodeURIComponent(token)}`
}

const play = async (row: Record<string, unknown>) => {
  const direct = String(row?.file_path || '').trim()
  if (direct.startsWith('http://') || direct.startsWith('https://')) {
    emit('play', { urls: { raw: direct } })
    return
  }
  const id = String(row?.id || '').trim()
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
  } catch (error) {
    emit('play', { urls: { raw: buildInlineRecordUrl(id) } })
  }
}
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
:deep(.el-table__header-wrapper th.el-table__cell) {
  border-bottom: 1px solid var(--el-border-color-lighter);
}
:deep(.el-table__body-wrapper td.el-table__cell) {
  border-bottom: 1px solid var(--el-border-color-lighter);
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
