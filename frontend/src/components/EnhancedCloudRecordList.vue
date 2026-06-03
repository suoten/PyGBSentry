<template>
  <div class="enhanced-cloud-record-list">
    <!-- 工具栏 -->
    <div class="toolbar mb-4">
      <div class="toolbar-left">
        <div class="flex items-center gap-2">
          <div class="status-dot status-dot--cloud"></div>
          <h3 class="text-base font-semibold">云端录像</h3>
          <span class="text-xs text-gray-500">快速点播与无缝回放</span>
        </div>
      </div>
      <div class="toolbar-right flex items-center gap-3">
        <!-- 日期范围选择 -->
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          size="small"
          :shortcuts="dateShortcuts"
          @change="handleDateChange"
        />
        
        <!-- 查询按钮 -->
        <el-button 
          type="primary" 
          size="small" 
          :loading="loading"
          @click="fetchRecords"
        >
          <el-icon v-if="!loading" class="mr-1"><Search /></el-icon>
          查询
        </el-button>
        
        <!-- 重置按钮 -->
        <el-button size="small" @click="resetRange">
          <el-icon class="mr-1"><Refresh /></el-icon>
          重置
        </el-button>
        
        <!-- 批量操作 -->
        <el-dropdown v-if="selectedRecords.length > 0" @command="handleBatchCommand">
          <el-button size="small" type="success">
            批量操作 ({{ selectedRecords.length }})
            <el-icon class="ml-1"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="download">批量下载</el-dropdown-item>
              <el-dropdown-item command="play">连续播放</el-dropdown-item>
              <el-dropdown-item command="export">导出列表</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 质量信息提示 -->
    <div v-if="recordStats" class="stats-bar mb-3">
      <div class="stats-item">
        <span class="stats-label">录像数量</span>
        <span class="stats-value">{{ recordStats.totalCount }}</span>
      </div>
      <div class="stats-item">
        <span class="stats-label">总时长</span>
        <span class="stats-value">{{ formatDuration(recordStats.totalDuration) }}</span>
      </div>
      <div class="stats-item">
        <span class="stats-label">总大小</span>
        <span class="stats-value">{{ formatFileSize(recordStats.totalSize) }}</span>
      </div>
      <div class="stats-item">
        <span class="stats-label">平均码率</span>
        <span class="stats-value">{{ recordStats.avgBitrate }} kbps</span>
      </div>
    </div>

    <!-- 时间轴视图 -->
    <div v-if="records.length > 0" class="timeline-section mb-4">
      <div class="timeline-header flex justify-between items-center mb-2">
        <span class="text-sm font-medium">录像时间轴</span>
        <span class="text-xs text-gray-500">
          {{ timelineAxisStart }} - {{ timelineAxisEnd }}
        </span>
      </div>
      <div class="timeline-container">
        <div class="timeline-track">
          <div 
            v-for="(record, idx) in timelineRecords" 
            :key="record.id"
            class="timeline-block"
            :class="{ 
              'is-active': idx === activeTimelineIndex,
              'is-playing': idx === playingIndex
            }"
            :style="getTimelineStyle(record)"
            @click="handleTimelineClick(record, idx)"
            @mouseenter="hoverTimelineIndex = idx"
            @mouseleave="hoverTimelineIndex = -1"
          >
            <div class="timeline-block-inner"></div>
            <div v-if="hoverTimelineIndex === idx" class="timeline-tooltip">
              <div class="tooltip-time">{{ formatTime(record.startTime) }}</div>
              <div class="tooltip-duration">{{ formatDuration(record.duration) }}</div>
            </div>
          </div>
        </div>
        <div class="timeline-axis">
          <span>{{ timelineAxisStart }}</span>
          <span>{{ timelineAxisEnd }}</span>
        </div>
      </div>
    </div>

    <!-- 录像表格 -->
    <div class="record-table-wrapper rounded-lg border border-gray-200">
      <el-table
        ref="tableRef"
        :data="paginatedRecords"
        style="width: 100%"
        size="small"
        :row-class-name="tableRowClassName"
        @selection-change="handleSelectionChange"
        empty-text="当前时间范围暂无云端录像"
        :max-height="400"
        table-layout="auto"
        @row-click="handleRowClick"
        @row-dblclick="handleRowDblClick"
      >
        <el-table-column type="selection" width="40" />
        
        <el-table-column prop="start_time" label="开始时间" min-width="180" sortable>
          <template #default="scope">
            <div class="flex items-center gap-2">
              <div 
                class="record-status-dot"
                :class="getRecordStatusClass(scope.row)"
              ></div>
              <span>{{ formatTime(scope.row.start_time) }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="end_time" label="结束时间" min-width="180">
          <template #default="scope">
            {{ formatTime(scope.row.end_time) }}
          </template>
        </el-table-column>
        
        <el-table-column label="时长" width="100" sortable>
          <template #default="scope">
            <span class="font-mono">{{ formatDuration(scope.row.duration) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column label="大小" width="110">
          <template #default="scope">
            <span>{{ formatFileSize(scope.row.file_size) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column label="质量" width="80">
          <template #default="scope">
            <el-tag 
              :type="getQualityType(scope.row)" 
              size="small"
            >
              {{ getQualityLabel(scope.row) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="状态" width="80">
          <template #default="scope">
            <el-tag 
              v-if="scope.row.url_ok === false" 
              type="danger" 
              size="small"
            >
              异常
            </el-tag>
            <el-tag 
              v-else-if="scope.row.url_status_code === 200" 
              type="success" 
              size="small"
            >
              正常
            </el-tag>
            <el-tag v-else size="small">
              未知
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <div class="flex items-center gap-2">
              <el-button 
                type="primary" 
                size="small"
                :type="scope.$index === playingIndex ? 'warning' : 'primary'"
                @click.stop="playRecord(scope.row, scope.$index)"
              >
                {{ scope.$index === playingIndex ? '停止' : '播放' }}
              </el-button>
              <el-button 
                size="small"
                @click.stop="previewRecord(scope.row)"
              >
                预览
              </el-button>
              <el-dropdown size="small" @command="(cmd: string) => handleCommand(cmd, scope.row)">
                <el-button size="small">
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="download">下载</el-dropdown-item>
                    <el-dropdown-item command="share">分享</el-dropdown-item>
                    <el-dropdown-item command="clip">剪辑</el-dropdown-item>
                    <el-dropdown-item command="verify">校验</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrapper mt-4 flex justify-end">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="records.length"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        prev-text="上一页"
        next-text="下一页"
        size="small"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>

    <!-- 播放器对话框 -->
    <el-dialog
      v-model="playerDialogVisible"
      :title="playerDialogTitle"
      width="85%"
      top="3vh"
      :close-on-click-modal="false"
      :destroy-on-close="true"
      class="vod-player-dialog"
    >
      <EnhancedVodPlayer
        v-if="playerDialogVisible && currentPlayUrl"
        :sources="currentPlaySources"
        :config="playerConfig"
        :start-time="playbackStartTime"
        show-quality-indicator
        @play="handlePlayerPlay"
        @pause="handlePlayerPause"
        @ended="handlePlayerEnded"
        @error="handlePlayerError"
        @timeupdate="handleTimeUpdate"
      />
      <div v-else class="flex items-center justify-center h-96">
        <el-icon class="is-loading text-4xl text-gray-400"><Loading /></el-icon>
      </div>
      
      <template #footer>
        <div class="flex justify-between items-center">
          <div class="text-sm text-gray-500">
            {{ currentRecordInfo }}
          </div>
          <div class="flex gap-2">
            <el-button @click="playerDialogVisible = false">关闭</el-button>
            <el-button 
              v-if="!isSeamlessMode" 
              type="primary" 
              @click="switchToSeamlessMode"
            >
              开启无缝回放
            </el-button>
            <el-button 
              v-else 
              type="warning"
              @click="isSeamlessMode = false"
            >
              退出无缝模式
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 预览对话框 -->
    <el-dialog
      v-model="previewDialogVisible"
      title="录像预览"
      width="60%"
      top="15vh"
      :destroy-on-close="true"
    >
      <div class="preview-container">
        <EnhancedVodPlayer
          v-if="previewDialogVisible && previewUrl"
          :sources="previewSources"
          :config="{ autoplay: true, muted: true }"
          show-quality-indicator
        />
      </div>
    </el-dialog>

    <!-- 分享对话框 -->
    <el-dialog
      v-model="shareDialogVisible"
      title="分享录像"
      width="500px"
    >
      <el-form label-width="80px">
        <el-form-item label="分享类型">
          <el-radio-group v-model="shareType">
            <el-radio label="link">链接分享</el-radio>
            <el-radio label="embed">嵌入代码</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="有效期">
          <el-select v-model="shareExpireHours" style="width: 100%">
            <el-option label="1小时" :value="1" />
            <el-option label="6小时" :value="6" />
            <el-option label="24小时" :value="24" />
            <el-option label="7天" :value="168" />
            <el-option label="30天" :value="720" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="shareType === 'link'" label="分享链接">
          <el-input v-model="shareLink" readonly>
            <template #append>
              <el-button @click="copyShareLink">复制</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item v-else label="嵌入代码">
          <el-input v-model="embedCode" type="textarea" :rows="4" readonly />
        </el-form-item>
      </el-form>
    </el-dialog>

    <!-- 剪辑对话框 -->
    <el-dialog
      v-model="clipDialogVisible"
      title="录像剪辑"
      width="70%"
      top="5vh"
      :destroy-on-close="true"
    >
      <div class="clip-container">
        <div class="clip-form mb-4">
          <el-form inline>
            <el-form-item label="开始时间">
              <el-date-picker
                v-model="clipStartTime"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="选择开始时间"
              />
            </el-form-item>
            <el-form-item label="结束时间">
              <el-date-picker
                v-model="clipEndTime"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="选择结束时间"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="applyClip">应用</el-button>
            </el-form-item>
          </el-form>
        </div>
        <EnhancedVodPlayer
          v-if="clipDialogVisible && clipUrl"
          ref="clipPlayerRef"
          :sources="clipSources"
          :config="{ autoplay: false }"
          :start-time="clipStartTimestamp"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { Search, Refresh, ArrowDown, MoreFilled, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/http'
import type { VodSource } from '../types/vod'
import { getApiErrorMessage } from '../utils/errorMessage'
import EnhancedVodPlayer from './EnhancedVodPlayer.vue'

interface CloudRecord {
  id: string
  start_time: string
  end_time: string
  duration: number
  file_size: number
  file_path: string
  url_ok?: boolean
  url_status_code?: number
  url_error?: string
  record_app?: string
  media_node_id?: string
}

interface RecordStats {
  totalCount: number
  totalDuration: number
  totalSize: number
  avgBitrate: number
}

const props = defineProps<{
  deviceId: string
  channelId: string
  initialStart?: string
  initialEnd?: string
}>()

const emit = defineEmits<{
  (e: 'play', record: CloudRecord, sources: VodSource): void
  (e: 'batch-play', records: CloudRecord[]): void
  (e: 'download', record: CloudRecord): void
}>()

// 状态
const records = ref<CloudRecord[]>([])
const selectedRecords = ref<CloudRecord[]>([])
const loading = ref(false)
const dateRange = ref<[Date, Date] | null>(null)
const page = ref(1)
const pageSize = ref(20)
const playingIndex = ref(-1)
const activeTimelineIndex = ref(-1)
const hoverTimelineIndex = ref(-1)

// 播放器相关
const playerDialogVisible = ref(false)
const playerDialogTitle = ref('录像播放')
const currentPlayUrl = ref('')
const currentPlaySources = ref<VodSource>({})
const currentPlayingRecord = ref<CloudRecord | null>(null)
const playbackStartTime = ref(0)
const playerConfig = ref({
  autoplay: true,
  muted: false,
  adaptiveBuffer: true,
  minBufferTime: 500,
  maxBufferTime: 5000,
  startBufferTime: 1000
})
const isSeamlessMode = ref(false)

// 预览相关
const previewDialogVisible = ref(false)
const previewUrl = ref('')
const previewSources = ref<VodSource>({})

// 分享相关
const shareDialogVisible = ref(false)
const shareType = ref<'link' | 'embed'>('link')
const shareExpireHours = ref(24)
const shareLink = ref('')
const embedCode = ref('')
const sharingRecord = ref<CloudRecord | null>(null)

// 剪辑相关
const clipDialogVisible = ref(false)
const clipUrl = ref('')
const clipSources = ref<VodSource>({})
const clipStartTime = ref('')
const clipEndTime = ref('')
const clipStartTimestamp = ref(0)
const clipPlayerRef = ref<InstanceType<typeof EnhancedVodPlayer> | null>(null)

// 日期快捷选项
const dateShortcuts = [
  {
    text: '最近1小时',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000)
      return [start, end]
    }
  },
  {
    text: '最近6小时',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 6 * 3600 * 1000)
      return [start, end]
    }
  },
  {
    text: '最近24小时',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 24 * 3600 * 1000)
      return [start, end]
    }
  },
  {
    text: '最近7天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 7 * 24 * 3600 * 1000)
      return [start, end]
    }
  }
]

// 计算属性
const paginatedRecords = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return records.value.slice(start, end)
})

const timelineRecords = computed(() => records.value)

const recordStats = computed((): RecordStats | null => {
  if (records.value.length === 0) return null
  
  const totalDuration = records.value.reduce((sum, r) => sum + (r.duration || 0), 0)
  const totalSize = records.value.reduce((sum, r) => sum + (r.file_size || 0), 0)
  const avgBitrate = totalDuration > 0 ? Math.round((totalSize * 8) / totalDuration / 1000) : 0
  
  return {
    totalCount: records.value.length,
    totalDuration,
    totalSize,
    avgBitrate
  }
})

const timelineRange = computed(() => {
  if (records.value.length === 0) return { start: 0, end: 1 }
  
  const starts = records.value.map(r => new Date(r.start_time).getTime()).filter(Number.isFinite)
  const ends = records.value.map(r => new Date(r.end_time).getTime()).filter(Number.isFinite)
  
  return {
    start: Math.min(...starts),
    end: Math.max(...ends)
  }
})

const timelineAxisStart = computed(() => formatTime(new Date(timelineRange.value.start).toISOString()))
const timelineAxisEnd = computed(() => formatTime(new Date(timelineRange.value.end).toISOString()))

const currentRecordInfo = computed(() => {
  if (!currentPlayingRecord.value) return ''
  const record = currentPlayingRecord.value
  return `${formatTime(record.start_time)} - ${formatTime(record.end_time)} | 时长: ${formatDuration(record.duration)}`
})

// 方法

/**
 * 获取播放 URL
 */
async function getPlayUrl(recordId: string): Promise<VodSource> {
  try {
    const res = await api.get(`/api/v1/record/play-url/${recordId}`)
    const data = res.data || {}
    return {
      mp4: data.url,
      flv: data.flv || data.wss_flv || data.ws_flv || data.https_flv,
      hls: data.hls || data.wss_hls || data.ws_hls || data.https_hls,
      webrtc: data.webrtc || data.rtcs || data.rtc,
      hint: data.hint || data.webrtc_hint
    }
  } catch (error) {
    // 降级到直接下载 URL
    return {
      mp4: `/api/v1/record/download/${recordId}`
    }
  }
}

/**
 * 获取备用下载 URL
 */
function getDownloadUrl(recordId: string, inline = false): string {
  const token = localStorage.getItem('token') || ''
  return `/api/v1/record/download/${recordId}?inline=${inline}&token=${encodeURIComponent(token)}`
}

/**
 * 播放录像
 */
async function playRecord(record: CloudRecord, index: number) {
  if (playingIndex.value === index) {
    // 停止播放
    playingIndex.value = -1
    playerDialogVisible.value = false
    return
  }
  
  loading.value = true
  try {
    const sources = await getPlayUrl(record.id)
    currentPlaySources.value = sources
    currentPlayingRecord.value = record
    playbackStartTime.value = 0
    playerDialogTitle.value = `云端录像 - ${formatTime(record.start_time)}`
    playingIndex.value = index
    playerDialogVisible.value = true
    
    emit('play', record, sources)
  } catch (error: unknown) {
    ElMessage.error(`获取播放地址失败: ${getApiErrorMessage(error, '获取播放地址失败')}`)
  } finally {
    loading.value = false
  }
}

/**
 * 预览录像
 */
async function previewRecord(record: CloudRecord) {
  previewUrl.value = getDownloadUrl(record.id, true)
  previewSources.value = {
    mp4: previewUrl.value
  }
  previewDialogVisible.value = true
}

/**
 * 处理表格行点击
 */
function handleRowClick(row: CloudRecord) {
  activeTimelineIndex.value = records.value.findIndex(r => r.id === row.id)
}

/**
 * 处理表格行双击
 */
async function handleRowDblClick(row: CloudRecord) {
  const index = records.value.findIndex(r => r.id === row.id)
  await playRecord(row, index)
}

/**
 * 处理时间轴点击
 */
function handleTimelineClick(record: CloudRecord, index: number) {
  activeTimelineIndex.value = index
  playRecord(record, index)
}

/**
 * 获取时间轴样式
 */
function getTimelineStyle(record: CloudRecord) {
  const range = timelineRange.value
  const span = range.end - range.start
  if (span <= 0) return { width: '0%', left: '0%' }
  
  const start = new Date(record.start_time).getTime()
  const end = new Date(record.end_time).getTime()
  
  const left = ((start - range.start) / span) * 100
  const width = Math.max(0.5, ((end - start) / span) * 100)
  
  return {
    left: `${Math.max(0, left)}%`,
    width: `${Math.min(100 - left, width)}%`
  }
}

/**
 * 获取录像状态样式
 */
function getRecordStatusClass(record: CloudRecord): string {
  if (record.url_ok === false) return 'record-status-dot--error'
  if (record.url_status_code === 200) return 'record-status-dot--success'
  return 'record-status-dot--warning'
}

/**
 * 获取质量标签
 */
function getQualityLabel(record: CloudRecord): string {
  const size = record.file_size || 0
  const duration = record.duration || 1
  const bitrate = (size * 8) / duration / 1000
  
  if (bitrate > 4000) return '超清'
  if (bitrate > 2000) return '高清'
  if (bitrate > 1000) return '标清'
  return '流畅'
}

/**
 * 获取质量类型
 */
function getQualityType(record: CloudRecord): string {
  const label = getQualityLabel(record)
  switch (label) {
    case '超清': return 'success'
    case '高清': return 'primary'
    case '标清': return 'warning'
    default: return 'info'
  }
}

/**
 * 格式化时间
 */
function formatTime(isoString: string): string {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

/**
 * 格式化时长
 */
function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0:00'
  
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }
  return `${m}:${s.toString().padStart(2, '0')}`
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B'
  
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let unitIndex = 0
  
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }
  
  return `${size.toFixed(2)} ${units[unitIndex]}`
}

/**
 * 查询录像
 */
async function fetchRecords() {
  if (!dateRange.value || dateRange.value.length < 2) {
    ElMessage.warning('请选择时间范围')
    return
  }
  
  loading.value = true
  try {
    const [startDate, endDate] = dateRange.value
    const res = await api.get('/api/v1/record/query', {
      params: {
        device_id: props.deviceId,
        channel_id: props.channelId,
        start_time: startDate.toISOString(),
        end_time: endDate.toISOString(),
        skip: 0,
        limit: 5000
      }
    })
    
    records.value = Array.isArray(res.data) ? res.data : []
    page.value = 1
    
    ElMessage.success(`查询完成，共 ${records.value.length} 条录像`)
  } catch (error: unknown) {
    ElMessage.error(`查询失败: ${getApiErrorMessage(error, '查询失败')}`)
    records.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 重置范围
 */
function resetRange() {
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 24 * 3600 * 1000)
  dateRange.value = [start, end]
  page.value = 1
  fetchRecords()
}

/**
 * 日期变化处理
 */
function handleDateChange() {
  // 可选：自动查询
}

/**
 * 表格行样式
 */
function tableRowClassName({ rowIndex }: { rowIndex: number }): string {
  if (rowIndex === activeTimelineIndex.value) return 'active-row'
  if (rowIndex % 2 === 0) return 'even-row'
  return ''
}

/**
 * 选择变化
 */
function handleSelectionChange(selection: CloudRecord[]) {
  selectedRecords.value = selection
}

/**
 * 批量操作
 */
async function handleBatchCommand(command: string) {
  switch (command) {
    case 'download':
      for (const record of selectedRecords.value) {
        window.open(getDownloadUrl(record.id), '_blank')
      }
      ElMessage.success(`已打开 ${selectedRecords.value.length} 个下载链接`)
      break
    case 'play':
      emit('batch-play', selectedRecords.value)
      break
    case 'export':
      exportRecordList()
      break
  }
}

/**
 * 导出录像列表
 */
function exportRecordList() {
  const data = records.value.map(r => ({
    start_time: r.start_time,
    end_time: r.end_time,
    duration: r.duration,
    file_size: r.file_size,
    quality: getQualityLabel(r)
  }))
  
  const csv = [
    ['开始时间', '结束时间', '时长(秒)', '大小(字节)', '质量'].join(','),
    ...data.map(row => Object.values(row).join(','))
  ].join('\n')
  
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cloud_records_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success('录像列表已导出')
}

/**
 * 处理命令
 */
async function handleCommand(command: string, record: CloudRecord) {
  switch (command) {
    case 'download':
      window.open(getDownloadUrl(record.id), '_blank')
      break
    case 'share':
      openShareDialog(record)
      break
    case 'clip':
      openClipDialog(record)
      break
    case 'verify':
      await verifyRecord(record)
      break
  }
}

/**
 * 打开分享对话框
 */
async function openShareDialog(record: CloudRecord) {
  sharingRecord.value = record
  
  try {
    const res = await api.get(`/api/v1/record/download/sign/${record.id}`, {
      params: { ttl_seconds: shareExpireHours.value * 3600 }
    })
    
    shareLink.value = res.data?.url || ''
    
    const baseUrl = window.location.origin
    embedCode.value = `<iframe src="${baseUrl}/#/play/${encodeURIComponent(shareLink.value)}" width="960" height="540" frameborder="0"></iframe>`
    
    shareDialogVisible.value = true
  } catch (error: unknown) {
    ElMessage.error(`生成分享链接失败: ${getApiErrorMessage(error, '生成分享链接失败')}`)
  }
}

/**
 * 复制分享链接
 */
async function copyShareLink() {
  try {
    await navigator.clipboard.writeText(shareLink.value)
    ElMessage.success('分享链接已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

/**
 * 打开剪辑对话框
 */
function openClipDialog(record: CloudRecord) {
  clipUrl.value = getDownloadUrl(record.id, true)
  clipSources.value = { mp4: clipUrl.value }
  clipStartTime.value = record.start_time
  clipEndTime.value = record.end_time
  clipStartTimestamp.value = 0
  clipDialogVisible.value = true
}

/**
 * 应用剪辑
 */
function applyClip() {
  if (clipPlayerRef.value && clipStartTime.value) {
    const startDate = new Date(clipStartTime.value)
    clipStartTimestamp.value = startDate.getTime() / 1000
    ;(clipPlayerRef.value as Record<string, unknown>).seekTo(clipStartTimestamp.value)
  }
}

/**
 * 校验录像
 */
async function verifyRecord(record: CloudRecord) {
  try {
    const res = await api.post(`/api/v1/record/verify/${record.id}`)
    const data = res.data || {}
    
    if (data.ok) {
      ElMessage.success('录像可用')
    } else {
      ElMessage.warning(`录像异常: ${data.error || '链接不可达'}`)
    }
  } catch (error: unknown) {
    ElMessage.error(`校验失败: ${getApiErrorMessage(error, '校验失败')}`)
  }
}

/**
 * 切换到无缝模式
 */
function switchToSeamlessMode() {
  if (selectedRecords.value.length === 0 && currentPlayingRecord.value) {
    selectedRecords.value = [currentPlayingRecord.value]
  }
  
  if (selectedRecords.value.length < 2) {
    ElMessage.warning('无缝回放需要选择多条录像')
    return
  }
  
  isSeamlessMode.value = true
  ElMessage.info('已开启无缝回放模式，录像将连续播放')
}

/**
 * 播放器事件处理
 */
function handlePlayerPlay() {
  if (playingIndex.value >= 0) {
    const rec = records.value[playingIndex.value]
    if (rec) currentPlayingRecord.value = rec
  }
}

function handlePlayerPause() {
}

function handlePlayerEnded() {
  if (isSeamlessMode.value && playingIndex.value < records.value.length - 1) {
    // 自动播放下一条
    const nextIndex = playingIndex.value + 1
    playRecord(records.value[nextIndex], nextIndex)
  }
}

function handlePlayerError(error: { code: string; message: string }) {
  ElMessage.error(`播放错误: ${getApiErrorMessage(error, '播放失败')}`)
}

function handleTimeUpdate(time: number) {
  // 可以用于更新播放进度
}

function handlePageChange() {
  // 页码变化
}

function handleSizeChange() {
  page.value = 1
}

// 初始化
onMounted(() => {
  if (props.initialStart && props.initialEnd) {
    const s = new Date(props.initialStart)
    const e = props.initialEnd ? new Date(props.initialEnd) : new Date()
    dateRange.value = [s, e]
    nextTick(() => fetchRecords())
  } else {
    resetRange()
  }
})

// 监听设备/通道变化
watch(() => [props.deviceId, props.channelId], () => {
  records.value = []
  selectedRecords.value = []
  playingIndex.value = -1
  activeTimelineIndex.value = -1
  page.value = 1
})
</script>

<style scoped>
.enhanced-cloud-record-list {
  padding: 16px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 状态指示器 */
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot--cloud {
  background: #38bdf8;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.2);
}

.status-dot--device {
  background: #34d399;
  box-shadow: 0 0 0 4px rgba(52, 211, 153, 0.2);
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.stats-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stats-label {
  font-size: 12px;
  color: #64748b;
}

.stats-value {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

/* 时间轴 */
.timeline-section {
  padding: 16px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.timeline-header {
  margin-bottom: 12px;
}

.timeline-container {
  position: relative;
}

.timeline-track {
  position: relative;
  height: 28px;
  background: #f1f5f9;
  border-radius: 6px;
  overflow: hidden;
}

.timeline-block {
  position: absolute;
  top: 3px;
  height: 22px;
  background: rgba(56, 189, 248, 0.6);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  overflow: visible;
}

.timeline-block:hover,
.timeline-block.is-active {
  background: rgba(56, 189, 248, 0.9);
}

.timeline-block.is-playing {
  background: rgba(59, 130, 246, 0.9);
}

.timeline-block-inner {
  width: 100%;
  height: 100%;
}

.timeline-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 8px;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.9);
  border-radius: 6px;
  white-space: nowrap;
  z-index: 100;
}

.tooltip-time {
  font-size: 12px;
  color: #fff;
  margin-bottom: 2px;
}

.tooltip-duration {
  font-size: 11px;
  color: #94a3b8;
}

.timeline-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 11px;
  color: #64748b;
}

/* 表格 */
.record-table-wrapper {
  background: #fff;
}

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #f8fafc;
}

:deep(.el-table__row) {
  cursor: pointer;
  transition: background 0.15s ease;
}

:deep(.el-table__row:hover) {
  background-color: #f1f5f9 !important;
}

:deep(.el-table__row.active-row) {
  background-color: #eff6ff !important;
}

:deep(.el-table__row.even-row) {
  background-color: #fafafa;
}

.record-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.record-status-dot--success {
  background: #22c55e;
}

.record-status-dot--warning {
  background: #f59e0b;
}

.record-status-dot--error {
  background: #ef4444;
}

/* 播放器对话框 */
.vod-player-dialog :deep(.el-dialog) {
  border-radius: 12px;
  overflow: hidden;
}

.preview-container {
  height: 400px;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.clip-container {
  height: 500px;
}
</style>
