<template>
  <!-- FIX: [2026-07-04] EnhancedVodPlayer 原为 stub 空壳，导致录像回放完全不能用。
       根因：开源版发布时组件未实现，仅保留 9 行 stub。
       修复：实现录像点播播放器，MP4 用原生 video，FLV 用 flv.js（package.json 已声明依赖） [全栈工程师] -->
  <div class="vod-player-wrap">
    <video
      ref="videoRef"
      class="vod-video"
      playsinline
      :muted="config.muted"
      @play="onPlay"
      @pause="onPause"
      @ended="onEnded"
      @error="onVideoError"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
    />
    <div v-if="errorMsg" class="vod-error-overlay">{{ errorMsg }}</div>
    <div v-if="showQualityIndicator && currentQuality" class="vod-quality-badge">{{ currentQuality }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import flvjs from 'flv.js'
import { logger } from '@/utils/logger'
import type { VodSource } from '../types/vod'

// FIX: [2026-07-04] VOD 播放器配置类型 [全栈工程师]
interface VodPlayerConfig {
  autoplay?: boolean
  muted?: boolean
  adaptiveBuffer?: boolean
  minBufferTime?: number
  maxBufferTime?: number
  startBufferTime?: number
}

const props = withDefaults(defineProps<{
  sources?: VodSource
  config?: VodPlayerConfig
  startTime?: number
  showQualityIndicator?: boolean
}>(), {
  sources: () => ({}),
  config: () => ({}),
  startTime: 0,
  showQualityIndicator: false,
})

const emit = defineEmits<{
  (e: 'play'): void
  (e: 'pause'): void
  (e: 'ended'): void
  (e: 'error'): void
  (e: 'timeupdate', currentTime: number): void
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const errorMsg = ref('')
const currentQuality = ref('')
let flvPlayer: flvjs.Player | null = null
let errored = false
let destroyed = false
let pendingSeek: number | null = null

// FIX: [2026-07-04] 从 VodSource 提取播放地址与格式。
// sources 可能结构：{mp4: url}、{flv: url}、{hls: url}、{url, type} [全栈工程师]
function extractSource(sources: VodSource): { url: string; format: string } {
  if (!sources || typeof sources !== 'object') return { url: '', format: '' }
  const mp4 = String(sources.mp4 || '').trim()
  if (mp4) return { url: mp4, format: 'mp4' }
  const flv = String(sources.flv || '').trim()
  if (flv) return { url: flv, format: 'flv' }
  const hls = String(sources.hls || sources.m3u8 || '').trim()
  if (hls) return { url: hls, format: 'hls' }
  const rawUrl = String(sources.url || '').trim()
  if (rawUrl) {
    const type = String(sources.type || '').toLowerCase()
    if (type) return { url: rawUrl, format: type }
    // FIX: [2026-07-04] 根据 URL 后缀推断格式 [全栈工程师]
    const lower = rawUrl.toLowerCase()
    if (lower.includes('.flv')) return { url: rawUrl, format: 'flv' }
    if (lower.includes('.m3u8')) return { url: rawUrl, format: 'hls' }
    return { url: rawUrl, format: 'mp4' }
  }
  return { url: '', format: '' }
}

function applyConfig() {
  const v = videoRef.value
  if (!v) return
  v.autoplay = props.config.autoplay !== false
  v.muted = Boolean(props.config.muted)
}

// FIX: [2026-07-04] 使用 flv.js 播放 FLV 点播流。
// flv.js API：createPlayer(mediaDataSource, config) — 第一参为 MediaDataSource（type/url/isLive），
// 第二参为 Config（缓冲/worker 等）。autoplay/muted 由 video 元素属性控制（见 applyConfig） [全栈工程师]
function startFlvPlayback(url: string) {
  if (!videoRef.value) return
  if (!flvjs.isSupported()) {
    logger.warn('EnhancedVodPlayer: flv.js not supported in this browser')
    emitError('FLV playback not supported')
    return
  }
  const mediaDataSource: flvjs.MediaDataSource = {
    type: 'flv',
    url,
    isLive: false,
  }
  const flvConfig: Partial<flvjs.Config> = {}
  // FIX: [2026-07-04] 应用缓冲配置 [全栈工程师]
  if (props.config.adaptiveBuffer) {
    flvConfig.stashInitialSize = Math.max(1, Math.floor((props.config.minBufferTime || 500) / 100))
  }
  flvPlayer = flvjs.createPlayer(mediaDataSource, flvConfig)
  flvPlayer.attachMediaElement(videoRef.value)
  flvPlayer.on(flvjs.Events.ERROR, (errorType: unknown, errorDetail: unknown, errorInfo: unknown) => {
    logger.error('EnhancedVodPlayer flv.js error:', errorType, errorDetail, errorInfo)
    emitError('FLV playback error')
  })
  flvPlayer.load()
  if (props.config.autoplay !== false) {
    const ret = flvPlayer.play()
    if (ret && typeof (ret as Promise<void>).catch === 'function') {
      ;(ret as Promise<void>).catch((e) => {
        logger.warn('EnhancedVodPlayer flv autoplay blocked:', e)
      })
    }
  }
  currentQuality.value = 'FLV'
}

// FIX: [2026-07-04] 使用原生 video 播放 MP4/HLS 点播流 [全栈工程师]
function startNativePlayback(url: string, format: string) {
  if (!videoRef.value) return
  videoRef.value.src = url
  videoRef.value.load()
  if (props.config.autoplay !== false) {
    videoRef.value.play().catch((e) => {
      logger.warn('EnhancedVodPlayer native autoplay blocked:', e)
    })
  }
  currentQuality.value = format.toUpperCase()
}

function startPlayback() {
  const { url, format } = extractSource(props.sources)
  if (!url) {
    logger.warn('EnhancedVodPlayer: no playable URL in sources')
    emitError('No playable source')
    return
  }
  errorMsg.value = ''
  applyConfig()
  if (props.startTime && props.startTime > 0) {
    pendingSeek = props.startTime
  }
  if (format === 'flv') {
    startFlvPlayback(url)
  } else {
    startNativePlayback(url, format)
  }
}

function onLoadedMetadata() {
  // FIX: [2026-07-04] 元数据加载后执行待处理的 seek 操作 [全栈工程师]
  if (pendingSeek !== null && videoRef.value) {
    try {
      videoRef.value.currentTime = pendingSeek
    } catch (e) {
      logger.warn('EnhancedVodPlayer seek failed:', e)
    }
    pendingSeek = null
  }
}

function onPlay() {
  emit('play')
}
function onPause() {
  emit('pause')
}
function onEnded() {
  emit('ended')
}
function onTimeUpdate() {
  if (videoRef.value) {
    emit('timeupdate', videoRef.value.currentTime)
  }
}
function onVideoError() {
  if (errored || destroyed) return
  const code = videoRef.value?.error?.code
  logger.warn('EnhancedVodPlayer video error, code:', code)
  emitError('Video playback error')
}

function emitError(msg: string) {
  if (errored || destroyed) return
  errored = true
  errorMsg.value = msg
  emit('error')
}

function cleanup() {
  if (flvPlayer) {
    try {
      flvPlayer.pause()
      flvPlayer.unload()
      flvPlayer.detachMediaElement()
      flvPlayer.destroy()
    } catch (e) {
      logger.warn('EnhancedVodPlayer flv.js cleanup error:', e)
    }
    flvPlayer = null
  }
  if (videoRef.value) {
    videoRef.value.pause()
    videoRef.value.removeAttribute('src')
    videoRef.value.load()
  }
}

// FIX: [2026-07-04] 暴露 seekTo 方法供剪辑功能调用 [全栈工程师]
const seekTo = (timestamp: number) => {
  if (!videoRef.value) {
    pendingSeek = timestamp
    return
  }
  try {
    videoRef.value.currentTime = timestamp
  } catch (e) {
    logger.warn('EnhancedVodPlayer seekTo failed:', e)
  }
}

defineExpose({ seekTo })

onMounted(() => {
  startPlayback()
})

onBeforeUnmount(() => {
  destroyed = true
  cleanup()
})

watch(
  () => props.sources,
  () => {
    errored = false
    errorMsg.value = ''
    cleanup()
    startPlayback()
  },
  { deep: true }
)

watch(
  () => props.config,
  () => {
    applyConfig()
  },
  { deep: true }
)
</script>

<style scoped>
.vod-player-wrap {
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: #000;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.vod-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.vod-error-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #fff;
  font-size: 14px;
  background: rgba(0, 0, 0, 0.6);
  padding: 8px 16px;
  border-radius: 4px;
}
.vod-quality-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  color: #fff;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 8px;
  border-radius: 3px;
}
</style>
