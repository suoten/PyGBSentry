<template>
  <el-dialog
    v-model="visibleState"
    :width="width"
    :fullscreen="isFullscreen"
    :destroy-on-close="destroyOnClose"
    :append-to-body="true"
    :close-on-click-modal="false"
    :show-close="false"
    :draggable="true"
    top="6vh"
    class="stream-player-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="stream-player-dialog__header">
        <div class="flex items-center gap-2 min-w-0">
          <el-icon class="text-emerald-500"><VideoPlay /></el-icon>
          <div class="min-w-0">
            <div class="font-semibold text-slate-900 truncate">{{ title }}</div>
            <div v-if="subtitle" class="text-xs text-slate-500 truncate">{{ subtitle }}</div>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <button class="stream-player-dialog__icon-btn" @click="toggleFullscreen">
            <el-icon><component :is="isFullscreen ? CopyDocument : FullScreen" /></el-icon>
          </button>
          <button class="stream-player-dialog__icon-btn stream-player-dialog__close-btn" @click="handleClose">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </div>
    </template>

    <div class="stream-player-dialog__content">
      <div class="stream-player-dialog__top">
        <div class="stream-player-dialog__main">
          <div class="stream-player-dialog__toolbar">
            <el-radio-group v-model="modeState" size="small">
              <el-radio-button v-if="urls.webrtc" value="webrtc">WebRTC</el-radio-button>
              <el-radio-button v-if="urls.flv" value="flv">FLV</el-radio-button>
              <el-radio-button v-if="urls.hls" value="hls">HLS</el-radio-button>
              <el-radio-button v-if="urls.raw" value="raw">原始</el-radio-button>
            </el-radio-group>
            <div class="flex items-center gap-2">
              <el-dropdown v-if="switchStreamType" trigger="click" @command="switchStreamType">
                <el-button size="small" :loading="switchingStream" :disabled="!playUrl">切换码流</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="main">主码流</el-dropdown-item>
                    <el-dropdown-item command="sub">子码流</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" type="danger" plain @click="handleStop" :disabled="!playUrl">停止</el-button>
              <el-button size="small" @click="copyPlayUrl" :disabled="!playUrl">复制地址</el-button>
              <el-button size="small" @click="openPlayUrl" :disabled="!playUrl">新标签打开</el-button>
            </div>
          </div>

          <slot name="toolbar"></slot>

          <div class="stream-player-dialog__stage">
            <!-- 优化版播放器：支持多协议、自适应缓冲、自动重连 -->
            <EnhancedStreamPlayer
              ref="playerRef"
              :video-url="playUrl"
              :hls-url="urls.hls"
              :flv-url="urls.flv"
              :webrtc-url="urls.webrtc"
              :candidates="playUrl ? [playUrl] : []"
              :codec="codec"
              :show-controls="true"
              :show-stats="showStreamStats"
              :enable-auto-reconnect="true"
              :max-reconnect-attempts="5"
              @play="onPlayerPlay"
              @error="onPlayerError"
              @stats="onPlayerStats"
            />
            <!-- 质量统计浮层 -->
            <div v-if="showStreamStats && streamMetrics" class="stream-stats-overlay">
              <div class="stats-grid">
                <span class="stats-label">FPS:</span>
                <span class="stats-value" :class="fpsClass">{{ streamMetrics.fps.toFixed(1) }}</span>
                <span class="stats-label">码率:</span>
                <span class="stats-value">{{ formatBitrate(streamMetrics.bitrate) }}</span>
                <span class="stats-label">缓冲:</span>
                <span class="stats-value" :class="bufferClass">{{ streamMetrics.buffer }}%</span>
                <span class="stats-label">健康:</span>
                <span class="stats-value" :class="healthClass">{{ streamMetrics.healthScore }}%</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="$slots.side" class="stream-player-dialog__side">
          <slot name="side"></slot>
        </div>
      </div>

      <div v-if="$slots.default" class="stream-player-dialog__bottom">
        <slot></slot>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Close, FullScreen, CopyDocument, VideoPlay } from '@element-plus/icons-vue'
import EnhancedStreamPlayer from './EnhancedStreamPlayer.vue'
import { getApiErrorMessage } from '../utils/errorMessage'
import api from '@/utils/http'
import { logger } from '@/utils/logger'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title?: string
    subtitle?: string
    width?: string | number
    destroyOnClose?: boolean
    mode?: 'webrtc' | 'flv' | 'hls' | 'raw'
    urls: { webrtc?: string; flv?: string; hls?: string; raw?: string }
    playUrl: string
    codec?: string
    switchStreamType?: (target: string) => void
    switchingStream?: boolean
  }>(),
  {
    title: '实时预览',
    subtitle: '',
    width: '80vw',
    destroyOnClose: true,
    mode: 'webrtc',
    codec: '',
    switchingStream: false
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:mode', v: 'webrtc' | 'flv' | 'hls' | 'raw'): void
  (e: 'close'): void
  (e: 'stop'): void
}>()

const playerRef = ref<InstanceType<typeof EnhancedStreamPlayer> | null>(null)

// ========== 流媒体质量监控 ==========
const showStreamStats = ref(false)  // 是否显示质量统计
const streamMetrics = ref<{
  fps: number
  bitrate: number
  buffer: number
  healthScore: number
} | null>(null)

const visibleState = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const modeState = computed({
  get: () => props.mode,
  set: (v) => emit('update:mode', v)
})

const isFullscreen = ref(false)

watch(
  () => props.modelValue,
  (v) => {
    if (v) isFullscreen.value = false
  }
)

// 格式化码率
const formatBitrate = (bps: number): string => {
  if (bps > 1000000) return `${(bps / 1000000).toFixed(1)} Mbps`
  if (bps > 1000) return `${(bps / 1000).toFixed(0)} kbps`
  return `${bps} bps`
}

// 播放器事件处理
const onPlayerPlay = () => {
  showStreamStats.value = true
  // 上报到后端
  reportQualityMetrics()
}

const onPlayerError = (error: { code: string; message: string }) => {
  logger.error('Player error:', error)
  ElMessage.warning(`播放异常: ${getApiErrorMessage(error, '播放异常')}`)
}

const onPlayerStats = (stats: Record<string, unknown>) => {
  streamMetrics.value = {
    fps: stats.fps || 0,
    bitrate: stats.bitrate || 0,
    buffer: stats.buffer || 0,
    healthScore: stats.healthScore || 100
  }
}

// 上报质量数据到后端
const reportQualityMetrics = async () => {
  if (!streamMetrics.value) return
  try {
    await api.post('/api/v1/stream-opt/quality-report', {
      session_id: playStreamId || 'unknown',
      ...streamMetrics.value
    })
  } catch {
    // 静默失败
  }
}

// 质量状态样式
const fpsClass = computed(() => {
  const fps = streamMetrics.value?.fps || 0
  if (fps >= 25) return 'text-green-500'
  if (fps >= 20) return 'text-yellow-500'
  return 'text-red-500'
})

const bufferClass = computed(() => {
  const buffer = streamMetrics.value?.buffer || 0
  if (buffer > 50) return 'text-green-500'
  if (buffer > 20) return 'text-yellow-500'
  return 'text-red-500'
})

const healthClass = computed(() => {
  const score = streamMetrics.value?.healthScore || 0
  if (score >= 80) return 'text-green-500'
  if (score >= 60) return 'text-yellow-500'
  return 'text-red-500'
})

// 外部传入的播放ID
const playStreamId = ref('')

watch(
  () => props.urls,
  (urls) => {
    // 当 URLs 变化时，记录播放ID
    if (urls && Object.keys(urls).length > 0) {
      playStreamId.value = `stream_${Date.now()}`
    }
  }
)

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value
}

const handleClose = () => {
  isFullscreen.value = false
  emit('close')
  emit('update:modelValue', false)
}

const handleStop = () => {
  try {
    playerRef.value?.stop?.()
  } catch { /* ignore */ }
  emit('stop')
  // 关闭时停止质量上报
  showStreamStats.value = false
  streamMetrics.value = null
}

const copyPlayUrl = async () => {
  if (!props.playUrl) return
  try {
    await navigator.clipboard.writeText(props.playUrl)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

const openPlayUrl = () => {
  if (!props.playUrl) return
  window.open(props.playUrl, '_blank')
}
</script>

<style scoped>
.stream-player-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 16px;
  height: 54px;
}

.stream-player-dialog__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--el-text-color-regular);
  cursor: pointer;
}

.stream-player-dialog__icon-btn:hover {
  background: rgba(15, 23, 42, 0.06);
  color: var(--el-text-color-primary);
}

.stream-player-dialog__close-btn:hover {
  background: rgba(239, 68, 68, 0.12);
  color: rgb(239, 68, 68);
}

.stream-player-dialog__content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stream-player-dialog__top {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.stream-player-dialog__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stream-player-dialog__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.stream-player-dialog__stage {
  position: relative;
  width: 100%;
  height: min(62vh, 560px);
  border-radius: 12px;
  overflow: hidden;
  background: #000;
}

/* 质量统计浮层 */
.stream-stats-overlay {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.75);
  border-radius: 6px;
  padding: 8px 12px;
  z-index: 100;
  pointer-events: none;
}

.stats-grid {
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 10px;
  font-size: 11px;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.stats-label {
  color: rgba(255, 255, 255, 0.6);
}

.stats-value {
  color: #fff;
  font-weight: 500;
  text-align: right;
}

.stream-player-dialog__side {
  width: 280px;
  flex: 0 0 auto;
}
</style>
