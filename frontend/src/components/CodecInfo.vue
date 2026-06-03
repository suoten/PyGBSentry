<template>
  <div class="codec-info-panel">
    <div v-if="loading" class="codec-loading">
      <el-icon class="animate-spin text-4xl text-blue-500"><Loading /></el-icon>
      <span class="text-slate-500 mt-2">正在获取编码信息...</span>
    </div>
    
    <div v-else-if="!hasInfo" class="codec-empty">
      <el-icon class="text-4xl text-slate-300"><DataLine /></el-icon>
      <span class="text-slate-400 mt-2">暂无编码信息</span>
      <el-button size="small" @click="fetchInfo" class="mt-3">
        <el-icon class="mr-1"><Refresh /></el-icon>
        刷新
      </el-button>
    </div>
    
    <div v-else class="codec-content">
      <div class="info-section">
        <div class="section-header">
          <el-icon class="text-blue-500"><VideoCamera /></el-icon>
          <span>视频信息</span>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">编码格式</span>
            <span class="info-value">{{ codecInfo.videoCodec || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">分辨率</span>
            <span class="info-value">{{ codecInfo.resolution || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">帧率</span>
            <span class="info-value">{{ codecInfo.fps ? `${codecInfo.fps} fps` : '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">码率</span>
            <span class="info-value">{{ formatBitrate(codecInfo.bitrate) }}</span>
          </div>
        </div>
      </div>

      <div class="info-section">
        <div class="section-header">
          <el-icon class="text-green-500"><Headset /></el-icon>
          <span>音频信息</span>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">编码格式</span>
            <span class="info-value">{{ codecInfo.audioCodec || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">采样率</span>
            <span class="info-value">{{ codecInfo.sampleRate ? `${codecInfo.sampleRate} Hz` : '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">声道数</span>
            <span class="info-value">{{ codecInfo.channels || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">码率</span>
            <span class="info-value">{{ formatBitrate(codecInfo.audioBitrate) }}</span>
          </div>
        </div>
      </div>

      <div class="info-section">
        <div class="section-header">
          <el-icon class="text-purple-500"><Monitor /></el-icon>
          <span>流媒体信息</span>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">应用名</span>
            <span class="info-value font-mono">{{ app || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">流ID</span>
            <span class="info-value font-mono truncate" :title="stream">{{ stream || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">媒体服务器</span>
            <span class="info-value font-mono truncate" :title="mediaServerId">{{ mediaServerId || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">在线时长</span>
            <span class="info-value">{{ formatDuration(codecInfo.duration) }}</span>
          </div>
        </div>
      </div>

      <div class="info-section">
        <div class="section-header">
          <el-icon class="text-orange-500"><TrendCharts /></el-icon>
          <span>实时统计</span>
        </div>
        <div class="stats-chart">
          <div class="stat-bar">
            <div class="stat-bar-label">
              <span>视频带宽</span>
              <span class="stat-value">{{ formatBitrate(codecInfo.videoBitrate) }}</span>
            </div>
            <div class="stat-bar-track">
              <div class="stat-bar-fill video" :style="{ width: getBarWidth(codecInfo.videoBitrate, 8000) }"></div>
            </div>
          </div>
          <div class="stat-bar">
            <div class="stat-bar-label">
              <span>音频带宽</span>
              <span class="stat-value">{{ formatBitrate(codecInfo.audioBitrate) }}</span>
            </div>
            <div class="stat-bar-track">
              <div class="stat-bar-fill audio" :style="{ width: getBarWidth(codecInfo.audioBitrate, 320) }"></div>
            </div>
          </div>
          <div class="stat-bar">
            <div class="stat-bar-label">
              <span>缓冲帧数</span>
              <span class="stat-value">{{ codecInfo.bufferFrames || 0 }}</span>
            </div>
            <div class="stat-bar-track">
              <div class="stat-bar-fill buffer" :style="{ width: getBarWidth(codecInfo.bufferFrames, 100) }"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="refresh-actions">
        <el-button size="small" @click="fetchInfo" :loading="loading">
          <el-icon class="mr-1"><Refresh /></el-icon>
          刷新信息
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  VideoCamera,
  Headset,
  Monitor,
  TrendCharts,
  DataLine,
  Loading,
  Refresh
} from '@element-plus/icons-vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { showError } from '../utils/feedback'

type CodecInfoPayload = {
  videoCodec?: string
  resolution?: string
  fps?: number
  bitrate?: number
  audioCodec?: string
  sampleRate?: number
  channels?: number | string
  audioBitrate?: number
  duration?: number
  videoBitrate?: number
  bufferFrames?: number
}

const props = defineProps<{
  app?: string
  stream?: string
  mediaServerId?: string
}>()

const loading = ref(false)
const refreshTimer = ref<number | null>(null)
const codecInfo = ref<CodecInfoPayload>({})

const hasInfo = computed(() => {
  return Object.keys(codecInfo.value).length > 0
})

const fetchInfo = async () => {
  if (!props.app || !props.stream) {
    return
  }
  
  loading.value = true
  try {
    const res = await api.get(`/api/v1/media/info`, {
      params: {
        app: props.app,
        stream: props.stream,
        media_server_id: props.mediaServerId
      }
    })
    
    if (res.data) {
      codecInfo.value = res.data as CodecInfoPayload
    }
  } catch (e) { showError('获取编码信息', e) } finally {
    loading.value = false
  }
}

const formatBitrate = (bitrate: number | undefined | null) => {
  if (!bitrate) return '-'
  if (bitrate >= 1000000) {
    return `${(bitrate / 1000000).toFixed(2)} Mbps`
  } else if (bitrate >= 1000) {
    return `${(bitrate / 1000).toFixed(2)} Kbps`
  }
  return `${bitrate} bps`
}

const formatDuration = (seconds: number | undefined | null) => {
  if (!seconds) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}h ${m}m ${s}s`
  } else if (m > 0) {
    return `${m}m ${s}s`
  }
  return `${s}s`
}

const getBarWidth = (value: number | undefined | null, max: number) => {
  if (!value) return '0%'
  const width = Math.min((value / max) * 100, 100)
  return `${width}%`
}

onMounted(() => {
  fetchInfo()
  refreshTimer.value = window.setInterval(fetchInfo, 15000)
})

onUnmounted(() => {
  if (refreshTimer.value !== null) {
    clearInterval(refreshTimer.value)
  }
})
</script>

<style scoped>
.codec-info-panel {
  padding: 8px 4px;
}

.codec-loading,
.codec-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.codec-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-section {
  padding: 16px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: white;
  border-radius: 8px;
}

.info-label {
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-value {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.stats-chart {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-bar-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.stat-bar-label span:first-child {
  color: #6b7280;
}

.stat-value {
  font-weight: 600;
  color: #374151;
}

.stat-bar-track {
  width: 100%;
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.stat-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}

.stat-bar-fill.video {
  background: linear-gradient(90deg, #3b82f6 0%, #1d4ed8 100%);
}

.stat-bar-fill.audio {
  background: linear-gradient(90deg, #10b981 0%, #059669 100%);
}

.stat-bar-fill.buffer {
  background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%);
}

.refresh-actions {
  display: flex;
  justify-content: center;
  padding-top: 8px;
}
</style>
