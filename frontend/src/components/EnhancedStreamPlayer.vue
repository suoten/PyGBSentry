<template>
  <div class="enhanced-stream-player relative w-full h-full bg-black overflow-hidden">
    <!-- 视频容器 -->
    <div 
      ref="containerRef" 
      class="video-container w-full h-full"
      :class="{ 'cursor-pointer': showControls }"
    >
      <!-- 加载状态 -->
      <div v-if="playerState === 'loading'" class="loading-overlay absolute inset-0 flex flex-col items-center justify-center bg-black/80 z-20">
        <div class="loading-animation mb-4">
          <div class="loading-ring"></div>
          <div class="loading-ring loading-ring--delay"></div>
        </div>
        <div class="text-white text-sm font-medium">{{ loadingText }}</div>
        <div class="text-gray-400 text-xs mt-2">{{ loadingStage }}</div>
      </div>

      <!-- 错误状态 -->
      <div v-if="playerState === 'error'" class="error-overlay absolute inset-0 flex flex-col items-center justify-center bg-black/90 z-20">
        <el-icon class="text-5xl text-red-400 mb-4"><WarningFilled /></el-icon>
        <div class="text-white text-lg font-medium mb-2">{{ errorTitle }}</div>
        <div class="text-gray-400 text-sm text-center max-w-md mb-4">{{ errorMessage }}</div>
        <div class="flex gap-3">
          <el-button size="small" @click="retry">{{ t('enhancedPlayer.retry') }}</el-button>
          <el-button
            v-if="alternateUrls.length > 0"
            size="small"
            type="primary"
            @click="switchToAlternate"
          >
            {{ t('enhancedPlayer.tryOtherLines') }}
          </el-button>
        </div>
      </div>

      <!-- 断流提示 -->
      <div v-if="showReconnecting" class="reconnect-overlay absolute inset-0 flex flex-col items-center justify-center bg-black/70 z-15">
        <el-icon class="is-loading text-4xl text-yellow-400 mb-3"><RefreshRight /></el-icon>
        <div class="text-white text-sm font-medium">{{ t('enhancedPlayer.reconnecting') }}</div>
        <div class="text-gray-400 text-xs mt-1">{{ reconnectCount }} / {{ maxReconnectAttempts }}</div>
      </div>

      <!-- 统计信息浮层 -->
      <div 
        v-if="showStats && playerState === 'playing'" 
        class="stats-overlay absolute top-2 left-2 bg-black/70 rounded px-3 py-2 z-15"
      >
        <div class="text-xs text-white/90 space-y-1">
          <div v-if="metrics.fps > 0">FPS: <span class="text-green-400">{{ metrics.fps }}</span></div>
          <div v-if="metrics.bitrate > 0">{{ t('enhancedPlayer.bitrate') }}: <span class="text-blue-400">{{ formatBitrate(metrics.bitrate) }}</span></div>
          <div v-if="metrics.resolution">{{ t('enhancedPlayer.resolution') }}: <span class="text-yellow-400">{{ metrics.resolution }}</span></div>
          <div>{{ t('enhancedPlayer.droppedFrames') }}: <span :class="metrics.droppedFrames > 10 ? 'text-red-400' : 'text-gray-400'">{{ metrics.droppedFrames }}</span></div>
          <div>{{ t('enhancedPlayer.buffer') }}: <span :class="bufferStatusClass">{{ bufferStatus }}</span></div>
        </div>
      </div>

      <!-- 控制栏 -->
      <div 
        v-if="showControls && playerState === 'playing'"
        class="control-bar absolute bottom-0 left-0 right-0 z-20"
        @mouseenter="showControlsBar"
        @mouseleave="scheduleHideControls"
      >
        <!-- 进度条（仅录像模式） -->
        <div v-if="isPlaybackMode" class="progress-container px-4 py-2 cursor-pointer" @click="seekTo">
          <div class="progress-bar">
            <div class="progress-buffered" :style="{ width: `${bufferedPercent}%` }"></div>
            <div class="progress-played" :style="{ width: `${playedPercent}%` }"></div>
            <div class="progress-handle" :style="{ left: `${playedPercent}%` }"></div>
          </div>
        </div>

        <!-- 按钮组 -->
        <div class="control-buttons px-4 pb-3 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <!-- 播放/暂停 -->
            <button class="control-btn" @click="togglePlay" :title="isPlaying ? t('enhancedPlayer.pause') : t('enhancedPlayer.play')">
              <el-icon class="text-lg"><VideoPause v-if="isPlaying" /><VideoPlay v-else /></el-icon>
            </button>

            <!-- 静音 -->
            <button class="control-btn" @click="toggleMute" :title="isMuted ? t('enhancedPlayer.unmute') : t('enhancedPlayer.mute')">
              <el-icon class="text-lg">
                <Mute v-if="isMuted || volumeValue === 0" />
                <Headset v-else />
              </el-icon>
            </button>

            <!-- 音量滑块 -->
            <div class="volume-control" @mouseenter="showVolumeSlider = true" @mouseleave="showVolumeSlider = false">
              <el-slider
                v-if="showVolumeSlider"
                v-model="volumeValue"
                :min="0"
                :max="1"
                :step="0.01"
                :show-tooltip="false"
                @input="setVolume"
              />
            </div>

            <!-- 时间显示（录像模式） -->
            <div v-if="isPlaybackMode" class="time-display text-xs text-white/80">
              {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
            </div>
          </div>

          <div class="flex items-center gap-2">
            <!-- 截图 -->
            <button class="control-btn" @click="screenshot" :title="t('enhancedPlayer.screenshot')">
              <el-icon class="text-lg"><Camera /></el-icon>
            </button>

            <!-- 线路切换 -->
            <div v-if="alternateUrls.length > 1" class="quality-selector relative">
              <button class="control-btn text-xs" @click="showLineMenu = !showLineMenu">
                {{ currentLineLabel }}
              </button>
              <div v-if="showLineMenu" class="line-menu absolute bottom-full right-0 mb-2 bg-black/90 rounded overflow-hidden">
                <button
                  v-for="(url, idx) in alternateUrls"
                  :key="idx"
                  class="block w-full px-4 py-2 text-xs text-white hover:bg-white/10 text-left"
                  :class="{ 'text-green-400': idx === currentLineIndex }"
                  @click="switchLine(idx)"
                >
                  {{ t('enhancedPlayer.lineLabel') }} {{ idx + 1 }} {{ idx === currentLineIndex ? '✓' : '' }}
                </button>
              </div>
            </div>

            <!-- 全屏 -->
            <button class="control-btn" @click="toggleFullscreen" :title="t('enhancedPlayer.fullscreen')">
              <el-icon class="text-lg"><FullScreen /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 隐藏的 canvas 用于截图 -->
    <canvas ref="canvasRef" class="hidden"></canvas>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { VideoPlay, VideoPause, Mute, Headset, FullScreen, Camera, WarningFilled, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { logger } from '@/utils/logger'
import { useI18n } from 'vue-i18n' // FIXED: 国际化

const { t } = useI18n() // FIXED: 国际化

// Props
interface StreamMetrics {
  fps: number
  bitrate: number
  resolution: string
  droppedFrames: number
  totalFrames: number
  latency: number
}

// window 上挂载的第三方播放器库的最小类型声明（按本组件实际用到的 API）
type JessibucaPlayerInstance = {
  on<T>(event: string, handler: (data: T) => void): void
  destroy(): void
  muted?: boolean
  volume?: number
}
type HlsPlayerInstance = {
  loadSource(url: string): void
  attachMedia(media: HTMLVideoElement): void
  on<E, D>(event: string, handler: (event: E, data: D) => void): void
  recoverMediaError(): void
  destroy(): void
}
type HlsStatic = {
  isSupported(): boolean
  new (config: Record<string, unknown>): HlsPlayerInstance
  Events: Record<string, string>
  ErrorTypes: Record<string, string>
}

const props = withDefaults(defineProps<{
  // 流地址
  videoUrl?: string
  hlsUrl?: string
  flvUrl?: string
  webrtcUrl?: string
  candidates?: string[]
  preferredUrl?: string
  urls?: Record<string, unknown>

  // 配置
  autoplay?: boolean
  muted?: boolean
  showControls?: boolean
  showStats?: boolean
  enableAutoReconnect?: boolean
  maxReconnectAttempts?: number
  reconnectInterval?: number

  // 录像模式
  isPlayback?: boolean
  startTime?: number
  duration?: number

  // 编码信息
  codec?: string
}>(), {
  autoplay: true,
  muted: false,
  showControls: true,
  showStats: false,
  enableAutoReconnect: true,
  maxReconnectAttempts: 5,
  reconnectInterval: 3000,
  isPlayback: false,
  startTime: 0,
  duration: 0,
  codec: ''
})

const emit = defineEmits<{
  (e: 'play'): void
  (e: 'pause'): void
  (e: 'stop'): void
  (e: 'error', error: { code: string; message: string }): void
  (e: 'stats', metrics: StreamMetrics): void
  (e: 'reconnect', count: number): void
  (e: 'lineChange', lineIndex: number): void
}>()

// Refs
const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)

// Player state
type PlayerState = 'idle' | 'loading' | 'playing' | 'paused' | 'error' | 'reconnecting'
const playerState = ref<PlayerState>('idle')
const isPlaying = ref(false)
const isMuted = ref(false)
const isFullscreen = ref(false)
const showVolumeSlider = ref(false)
const showLineMenu = ref(false)

// Volume
const volumeValue = ref(1)

// Time (playback mode)
const currentTime = ref(0)
const bufferedPercent = ref(0)
const playedPercent = ref(0)

// Reconnect
const reconnectCount = ref(0)
const showReconnecting = ref(false)

// Lines
const currentLineIndex = ref(0)
const alternateUrls = ref<string[]>([])

// Metrics
const metrics = ref<StreamMetrics>({
  fps: 0,
  bitrate: 0,
  resolution: '',
  droppedFrames: 0,
  totalFrames: 0,
  latency: 0
})

// Loading
const loadingText = ref(t('player.connectingStream')) // FIXED: 国际化
const loadingStage = ref('')

// Error
const errorTitle = ref(t('player.playFailed')) // FIXED: 国际化
const errorMessage = ref('')

// Timers
let reconnectTimer: number | null = null
let statsTimer: number | null = null
let hideControlsTimer: number | null = null

// Current player instance (jessibuca, hls, or native)
let currentPlayer: Record<string, unknown> | null = null
let jessibucaInstance: JessibucaPlayerInstance | null = null
// FIX: [2026-07-17 P1] 使用 AbortController 统一管理 video 元素事件监听器，
// destroyCurrentPlayer 时 abort 即可移除所有监听器，防止内存泄漏
let _nativePlayerAbort: AbortController | null = null

// Computed
const isPlaybackMode = computed(() => props.isPlayback)
const currentLineLabel = computed(() => `${t('player.lineLabel')} ${currentLineIndex.value + 1}`) // FIXED: 国际化

const bufferStatus = computed(() => {
  const percent = bufferedPercent.value
  if (percent > 80) return t('player.bufferSufficient') // FIXED: 国际化
  if (percent > 50) return t('player.bufferGood')
  if (percent > 20) return t('player.bufferFair')
  return t('player.bufferInsufficient')
})

const bufferStatusClass = computed(() => {
  const percent = bufferedPercent.value
  if (percent > 50) return 'text-green-400'
  if (percent > 20) return 'text-yellow-400'
  return 'text-red-400'
})

// Methods

/**
 * 初始化播放器
 */
async function initPlayer() {
  if (!props.videoUrl && (!props.candidates || props.candidates.length === 0)) {
    handleError('no_url', t('player.noPlayAddress')) // FIXED: 国际化
    return
  }

  playerState.value = 'loading'
  loadingText.value = t('player.initializing') // FIXED: 国际化
  
  // 收集可用地址
  const urls: string[] = []
  if (props.candidates) urls.push(...props.candidates.filter(Boolean))
  if (props.videoUrl && !urls.includes(props.videoUrl)) urls.push(props.videoUrl)
  if (props.flvUrl && !urls.includes(props.flvUrl)) urls.push(props.flvUrl)
  if (props.hlsUrl && !urls.includes(props.hlsUrl)) urls.push(props.hlsUrl)
  
  alternateUrls.value = urls
  currentLineIndex.value = 0

  // 选择最优地址
  const selectedUrl = selectBestUrl(urls)
  await startPlaying(selectedUrl)
}

/**
 * 选择最优播放地址
 */
function selectBestUrl(urls: string[]): string {
  // 如果有 preferredUrl（由后端根据流类型选择的最优协议），优先使用
  const preferred = props.preferredUrl || (props.urls as { preferredUrl?: string } | undefined)?.preferredUrl
  if (preferred && urls.includes(preferred)) {
    return preferred
  }
  if (preferred && urls.some(u => u.startsWith(preferred.split('?')[0].split('/').slice(-1)[0] ? preferred.split('?')[0] : ''))) {
    return preferred
  }
  
  // 优先 HLS，其次 WS/WSS，再次 FLV
  const hlsUrls = urls.filter(u => u.toLowerCase().includes('.m3u8') || u.toLowerCase().includes('/hls/'))
  if (hlsUrls.length > 0) return hlsUrls[0]
  
  const wsUrls = urls.filter(u => u.toLowerCase().includes('ws://') || u.toLowerCase().includes('wss://'))
  if (wsUrls.length > 0) return wsUrls[0]
  
  const flvUrls = urls.filter(u => u.toLowerCase().includes('.flv') || u.toLowerCase().includes('/live/'))
  if (flvUrls.length > 0) return flvUrls[0]
  
  return urls[0] || ''
}

/**
 * 开始播放
 */
async function startPlaying(url: string) {
  if (!url) {
    handleError('invalid_url', t('player.invalidAddress')) // FIXED: 国际化
    return
  }

  playerState.value = 'loading'
  loadingText.value = t('player.establishingConnection') // FIXED: 国际化
  
  // 清理之前的播放器
  destroyCurrentPlayer()
  
  try {
    // 检测 URL 类型
    const urlLower = url.toLowerCase()
    
    if (urlLower.includes('.flv') || urlLower.includes('/live/') || urlLower.includes('ws://') || urlLower.includes('wss://')) {
      // FLV 流
      await initFlvPlayer(url)
    } else if (urlLower.includes('.m3u8') || urlLower.includes('/hls/')) {
      // HLS 流
      await initHlsPlayer(url)
    } else if (urlLower.includes('webrtc') || urlLower.includes('/rtc/')) {
      // WebRTC
      await initWebRTCPlayer(url)
    } else {
      // 降级到原生 video
      await initNativePlayer(url)
    }
    
    // 开始收集统计
    startStatsCollection()
    
    // 自动播放
    if (props.autoplay) {
      await play()
    }
    
  } catch (error: unknown) {
    handleError('init_error', (error as { message?: string }).message || t('player.initFailed')) // FIXED: 国际化
  }
}

/**
 * 初始化 FLV 播放器 (使用 jessibuca)
 */
async function initFlvPlayer(url: string) {
  // 检查 jessibuca 是否已加载
  const JessibucaCtor = typeof window !== 'undefined'
    ? (window as unknown as { jessibuca?: new (options: Record<string, unknown>) => JessibucaPlayerInstance }).jessibuca
    : undefined
  if (JessibucaCtor) {
    loadingText.value = t('player.loadingDecoder') // FIXED: 国际化

    const container = containerRef.value
    if (!container) return

    jessibucaInstance = new JessibucaCtor({
      url: url,
      container: container,
      // 稳定性优化配置
      bufferTime: 1000,          // 缓冲时间 1秒（防抖动的关键！）
      isResize: true,
      autoFit: true,
      keepScreenOn: true,
      showBandwidth: false,
      // 解码器配置
      useWCS: false,            // 使用 MSE 解码（更稳定）
      // 错误处理
      hasAudio: true,
      timeout: 15000,
      // 性能优化
      workloadLevel: 1,         // 低负载模式，更稳定
      decoder: 'gm',            // 使用 GPU 解码（如果可用）
    })
    
    // 事件处理
    jessibucaInstance.on('load', () => {
      loadingText.value = t('player.decodingVideo') // FIXED: 国际化
    })
    
    jessibucaInstance.on('mediaInfo', (info: Record<string, unknown>) => {
      metrics.value.resolution = `${info.width}x${info.height}`
      loadingStage.value = t('player.resolutionInfo', { w: info.width, h: info.height }) // FIXED: 国际化
    })
    
    jessibucaInstance.on('videoInfo', (info: Record<string, unknown>) => {
      metrics.value.bitrate = (info.bitrate as number) || 0
    })
    
    jessibucaInstance.on('fps', (fps: number) => {
      metrics.value.fps = fps
    })
    
    jessibucaInstance.on('kbps', (kbps: number) => {
      metrics.value.bitrate = kbps * 1000
    })
    
    jessibucaInstance.on('start', () => {
      onPlayerReady()
    })
    
    jessibucaInstance.on('error', (error: unknown) => {
      logger.error('Jessibuca error:', error)
      onPlayerError(error)
    })
    
    jessibucaInstance.on('close', () => {
      onPlayerClose()
    })
    
    currentPlayer = jessibucaInstance
  } else {
    // 降级到原生 video
    await initNativePlayer(url)
  }
}

/**
 * 初始化 HLS 播放器
 */
async function initHlsPlayer(url: string) {
  const video = createVideoElement()
  if (!video) return

  const Hls = typeof window !== 'undefined' ? (window as unknown as { Hls?: HlsStatic }).Hls : undefined
  if (Hls && Hls.isSupported()) {
    const hls = new Hls({
      // 稳定性优化
      enableWorker: true,
      lowLatencyMode: false,          // 关闭低延迟模式，更稳定
      backBufferLength: 30,             // 30秒回退缓冲
      maxBufferLength: 30,              // 最大缓冲30秒
      maxMaxBufferLength: 60,          // 最大60秒
      // 时序控制
      startLevel: -1,                   // 自动选择
      capLevelToPlayerSize: true,       // 限制画质
      // 加载控制
      fragLoadingTimeOut: 20000,
      fragLoadingMaxRetry: 3,
      levelLoadingTimeOut: 10000,
      // 错误恢复
      autoStartLoad: true,
      autoRecover: true,
    })
    
    hls.loadSource(url)
    hls.attachMedia(video)
    
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      loadingText.value = t('player.bufferingStatus') // FIXED: 国际化
    })
    
    hls.on(Hls.Events.ERROR, (_: Record<string, unknown>, data: Record<string, unknown>) => {
      if (data.fatal) {
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            handleNetworkError(data)
            break
          case Hls.ErrorTypes.MEDIA_ERROR:
            hls.recoverMediaError()
            break
          default:
            handleError('hls_error', t('player.hlsError')) // FIXED: 国际化
            break
        }
      }
    })
    
    hls.on(Hls.Events.FRAG_LOADED, () => {
      updateBufferProgress(video)
    })
    
    currentPlayer = hls
    video.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
    
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // Safari 原生 HLS
    video.src = url
    video.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
  } else {
    handleError('not_supported', t('player.hlsNotSupported')) // FIXED: 国际化
  }
}

/**
 * 初始化 WebRTC 播放器
 */
async function initWebRTCPlayer(url: string) {
  // WebRTC 播放需要特殊的处理
  // 这里使用原生 video 元素尝试播放
  const video = createVideoElement()
  if (!video) return
  
  try {
    video.src = url
    await video.play()
  } catch {
    handleError('webrtc_error', t('player.webrtcFailed')) // FIXED: 国际化
  }
}

/**
 * 初始化原生 video 元素
 */
async function initNativePlayer(url: string) {
  const video = createVideoElement()
  if (!video) return

  video.src = url
  video.preload = 'auto'

  // FIX: [2026-07-17 P1] 使用 AbortController 统一管理监听器，destroy 时一次 abort 全部移除
  _nativePlayerAbort = new AbortController()
  const _ac = _nativePlayerAbort.signal

  video.addEventListener('loadedmetadata', () => {
    onPlayerReady()
    if (props.autoplay) {
      video.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
    }
  }, { signal: _ac })

  video.addEventListener('error', () => {
    const error = video.error
    let message = t('player.playError') // FIXED: 国际化
    if (error) {
      switch (error.code) {
        case MediaError.MEDIA_ERR_NETWORK:
          message = t('player.networkError') // FIXED: 国际化
          break
        case MediaError.MEDIA_ERR_DECODE:
          message = t('player.decodeErrorShort') // FIXED: 国际化
          break
        case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
          message = t('player.formatNotSupported') // FIXED: 国际化
          break
      }
    }
    handleError('video_error', message)
  }, { signal: _ac })

  video.addEventListener('waiting', () => {
    loadingText.value = t('player.bufferingStatus') // FIXED: 国际化 - waiting state
  }, { signal: _ac })

  video.addEventListener('canplay', () => {
    if (playerState.value === 'loading') {
      onPlayerReady()
    }
  }, { signal: _ac })

  currentPlayer = { type: 'native', element: video }
}

/**
 * 创建 video 元素
 */
function createVideoElement(): HTMLVideoElement | null {
  const container = containerRef.value
  if (!container) return null
  
  // 移除旧的 video
  const old = container.querySelector('video')
  if (old) old.remove()
  
  const video = document.createElement('video')
  video.className = 'w-full h-full'
  video.style.objectFit = 'contain'
  video.style.background = '#000'
  video.setAttribute('playsinline', '')
  video.setAttribute('webkit-playsinline', '')
  
  container.appendChild(video)
  
  return video
}

/**
 * 播放器就绪
 */
function onPlayerReady() {
  playerState.value = 'playing'
  isPlaying.value = true
  emit('play')
  
  // 重置重连计数
  reconnectCount.value = 0
  showReconnecting.value = false
  
  // 初始化进度（录像模式）
  if (props.isPlayback && props.startTime > 0) {
    const video = getVideoElement()
    if (video) {
      video.currentTime = props.startTime
    }
  }
}

/**
 * 播放器错误
 */
function onPlayerError(error: unknown) {
  const err = error as { message?: string; info?: string } | null | undefined
  const message = err?.message || err?.info || t('player.playAbnormal') // FIXED: 国际化
  
  // 检查是否有备用线路
  if (currentLineIndex.value < alternateUrls.value.length - 1) {
    switchToAlternate()
  } else {
    handleError('play_error', message)
  }
}

/**
 * 播放器关闭
 */
function onPlayerClose() {
  if (!props.enableAutoReconnect) {
    emit('stop')
    return
  }

  if (reconnectCount.value < (props.maxReconnectAttempts || 5)) {
    showReconnecting.value = true
    reconnectCount.value++
    emit('reconnect', reconnectCount.value)

    // FIX [2026-07-17 P1-E8]: 引入指数退避 + 随机抖动，避免重连风暴打垮恢复中的服务器。
    // delay = baseInterval * 2^(attempt-1) + jitter，上限 30 秒。
    const _baseInterval = props.reconnectInterval || 3000
    const _maxBackoff = 30000
    const _exponentialDelay = Math.min(_baseInterval * Math.pow(2, reconnectCount.value - 1), _maxBackoff)
    const _jitter = Math.random() * 500 // 0-500ms 随机抖动，防止多客户端同步重连
    const _actualDelay = Math.round(_exponentialDelay + _jitter)

    reconnectTimer = window.setTimeout(() => {
      const url = alternateUrls.value[currentLineIndex.value]
      if (url) {
        startPlaying(url)
      }
    }, _actualDelay)
  } else {
    handleError('reconnect_failed', t('player.reconnectLimit')) // FIXED: 国际化
  }
}

/**
 * 网络错误处理
 */
function handleNetworkError(data: Record<string, unknown>) {
  if (currentLineIndex.value < alternateUrls.value.length - 1) {
    switchToAlternate()
  } else {
    handleError('network_error', t('player.networkConnectFailed')) // FIXED: 国际化
  }
}

/**
 * 处理错误
 */
function handleError(code: string, message: string) {
  playerState.value = 'error'
  isPlaying.value = false
  errorTitle.value = t('player.playFailed') // FIXED: 国际化
  errorMessage.value = message
  emit('error', { code, message })
  
  // 停止统计
  stopStatsCollection()
}

/**
 * 重试
 */
async function retry() {
  reconnectCount.value = 0
  showReconnecting.value = false
  await initPlayer()
}

/**
 * 切换到备用线路
 */
async function switchToAlternate() {
  if (currentLineIndex.value < alternateUrls.value.length - 1) {
    currentLineIndex.value++
    emit('lineChange', currentLineIndex.value)
    await startPlaying(alternateUrls.value[currentLineIndex.value])
  }
}

/**
 * 切换到指定线路
 */
async function switchLine(index: number) {
  if (index !== currentLineIndex.value && index < alternateUrls.value.length) {
    currentLineIndex.value = index
    emit('lineChange', index)
    showLineMenu.value = false
    await startPlaying(alternateUrls.value[index])
  }
}

/**
 * 播放
 */
async function play() {
  if (playerState.value === 'error') return

  isPlaying.value = true
  playerState.value = 'playing'

  if (currentPlayer?.type === 'native') {
    ;(currentPlayer.element as HTMLVideoElement | undefined)?.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
  }
}

/**
 * 暂停
 */
function pause() {
  isPlaying.value = false
  playerState.value = 'paused'
  
  if (currentPlayer?.type === 'native') {
    ;(currentPlayer.element as HTMLVideoElement | undefined)?.pause()
  } else if (jessibucaInstance) {
    // Jessibuca 不支持暂停
  }
}

/**
 * 切换播放/暂停
 */
function togglePlay() {
  if (isPlaying.value) {
    pause()
    emit('pause')
  } else {
    play()
  }
}

/**
 * 静音切换
 */
function toggleMute() {
  isMuted.value = !isMuted.value

  if (currentPlayer?.type === 'native') {
    ;(currentPlayer.element as HTMLVideoElement).muted = isMuted.value
  } else if (jessibucaInstance) {
    jessibucaInstance.muted = isMuted.value
  }
}

/**
 * 设置音量
 */
function setVolume(value: number | number[]) {
  const val = Array.isArray(value) ? value[0] : value
  volumeValue.value = val
  isMuted.value = val === 0

  if (currentPlayer?.type === 'native') {
    ;(currentPlayer.element as HTMLVideoElement).volume = val
  } else if (jessibucaInstance) {
    jessibucaInstance.volume = val
  }
}

/**
 * 跳转（录像模式）
 */
function seekTo(event: MouseEvent) {
  if (!props.isPlayback) return
  
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const percent = (event.clientX - rect.left) / rect.width
  const video = getVideoElement()
  
  if (video && props.duration > 0) {
    video.currentTime = percent * props.duration
  }
}

/**
 * 截图
 */
function screenshot() {
  const video = getVideoElement()
  if (!video) return
  
  const canvas = canvasRef.value
  if (!canvas) return
  
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  ctx.drawImage(video, 0, 0)
  
  const url = canvas.toDataURL('image/png')
  const a = document.createElement('a')
  a.href = url
  a.download = `screenshot_${Date.now()}.png`
  a.click()
  
  ElMessage.success(t('player.screenshotSaved')) // FIXED: 国际化
}

/**
 * 全屏切换
 */
async function toggleFullscreen() {
  const container = containerRef.value
  if (!container) return
  
  try {
    if (!document.fullscreenElement) {
      await container.requestFullscreen()
      isFullscreen.value = true
    } else {
      await document.exitFullscreen()
      isFullscreen.value = false
    }
  } catch {
    logger.error('Fullscreen error')
  }
}

/**
 * 获取 video 元素
 */
function getVideoElement(): HTMLVideoElement | null {
  if (currentPlayer?.type === 'native') {
    return currentPlayer.element as HTMLVideoElement
  }
  return containerRef.value?.querySelector('video') ?? null
}

/**
 * 获取时间
 */
function getCurrentTime(): number {
  return currentTime.value
}

/**
 * 获取缓冲状态
 */
function getBufferPercent(): number {
  return bufferedPercent.value
}

// 统计收集
function startStatsCollection() {
  if (statsTimer) return
  
  statsTimer = window.setInterval(() => {
    const video = getVideoElement()
    if (!video) return
    
    currentTime.value = video.currentTime
    updateBufferProgress(video)
    
    // 计算播放进度
    if (video.duration > 0) {
      playedPercent.value = (video.currentTime / video.duration) * 100
    }
    
    emit('stats', { ...metrics.value })
  }, 1000)
}

function stopStatsCollection() {
  if (statsTimer) {
    clearInterval(statsTimer)
    statsTimer = null
  }
}

function updateBufferProgress(video: HTMLVideoElement) {
  if (video.buffered.length > 0 && video.duration > 0) {
    const buffered = video.buffered.end(video.buffered.length - 1)
    bufferedPercent.value = (buffered / video.duration) * 100
  }
}

// 控制栏显示
function showControlsBar() {
  if (hideControlsTimer) {
    clearTimeout(hideControlsTimer)
    hideControlsTimer = null
  }
}

function scheduleHideControls() {
  if (isPlaying.value && !isFullscreen.value) {
    hideControlsTimer = window.setTimeout(() => {
      showVolumeSlider.value = false
      showLineMenu.value = false
    }, 3000)
  }
}

// 格式化
function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00'
  
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  
  if (h > 0) {
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function formatBitrate(bps: number): string {
  if (bps > 1000000) return `${(bps / 1000000).toFixed(1)} Mbps`
  if (bps > 1000) return `${(bps / 1000).toFixed(0)} kbps`
  return `${bps} bps`
}

// 销毁播放器
function destroyCurrentPlayer() {
  // FIX: [2026-07-17 P1] abort 所有 video 元素事件监听器，防止内存泄漏
  if (_nativePlayerAbort) {
    _nativePlayerAbort.abort()
    _nativePlayerAbort = null
  }

  if (jessibucaInstance) {
    try {
      jessibucaInstance.destroy()
    } catch { /* ignore */ }
    jessibucaInstance = null
  }
  
  if (currentPlayer?.type === 'native' && currentPlayer.element) {
    ;(currentPlayer.element as HTMLVideoElement).pause()
    ;(currentPlayer.element as HTMLVideoElement).src = ''
  }

  if (currentPlayer?.destroy) {
    try {
      ;(currentPlayer.destroy as () => void)()
    } catch { /* cleanup: ignore */ }
  }

  currentPlayer = null
}

// 停止
function stop() {
  destroyCurrentPlayer()
  playerState.value = 'idle'
  isPlaying.value = false
  reconnectCount.value = 0
  showReconnecting.value = false
  stopStatsCollection()
  emit('stop')
}

// Watch video URL changes
watch(() => props.videoUrl, (newUrl) => {
  if (newUrl) {
    retry()
  }
})

// Lifecycle
onMounted(() => {
  nextTick(() => {
    initPlayer()
  })
})

onBeforeUnmount(() => {
  stop()
  destroyCurrentPlayer()
  
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (hideControlsTimer) clearTimeout(hideControlsTimer)
})

// Expose
defineExpose({
  play,
  pause,
  stop,
  retry,
  togglePlay,
  toggleMute,
  setVolume,
  screenshot,
  toggleFullscreen,
  getCurrentTime,
  getBufferPercent,
  switchLine,
  getMetrics: () => ({ ...metrics.value }),
  destroy: () => {
    destroyCurrentPlayer()
    stopStatsCollection()
  }
})
</script>

<style scoped>
.enhanced-stream-player {
  position: relative;
  background: #000;
}

.video-container {
  position: relative;
  overflow: hidden;
}

.video-container video {
  object-fit: contain;
  background: #000;
}

/* 全屏样式 */
:fullscreen .enhanced-stream-player {
  width: 100vw;
  height: 100vh;
}

/* 加载动画 */
.loading-animation {
  width: 48px;
  height: 48px;
  position: relative;
}

.loading-ring {
  position: absolute;
  inset: 0;
  border: 3px solid transparent;
  border-top-color: #38bdf8;
  border-radius: 50%;
  animation: spin 1.2s linear infinite;
}

.loading-ring--delay {
  inset: 8px;
  animation-delay: -0.4s;
  border-top-color: #22d3ee;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 控制栏 */
.control-bar {
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.8));
  opacity: 0;
  transition: opacity 0.3s ease;
}

.control-bar:hover,
.video-container:hover .control-bar {
  opacity: 1;
}

/* 进度条 */
.progress-container {
  cursor: pointer;
}

.progress-bar {
  position: relative;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.progress-buffered {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}

.progress-played {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: #38bdf8;
  border-radius: 2px;
}

.progress-handle {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  background: #38bdf8;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.progress-container:hover .progress-handle {
  opacity: 1;
}

/* 控制按钮 */
.control-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: #fff;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.control-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

/* 音量滑块 */
.volume-control {
  width: 60px;
}

.volume-control :deep(.el-slider__runway) {
  background: rgba(255, 255, 255, 0.3);
}

.volume-control :deep(.el-slider__bar) {
  background: #38bdf8;
}

/* 时间显示 */
.time-display {
  font-variant-numeric: tabular-nums;
}

/* 菜单 */
.line-menu {
  min-width: 100px;
}

/* 统计信息 */
.stats-overlay {
  pointer-events: none;
}

/* 重连提示 */
.reconnect-overlay {
  pointer-events: none;
}
</style>
