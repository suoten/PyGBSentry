<template>
  <div 
    ref="playerContainer" 
    class="enhanced-vod-player relative w-full h-full bg-black overflow-hidden"
    :class="{ 'is-fullscreen': isFullscreen }"
  >
    <!-- 视频元素 -->
    <video
      ref="videoEl"
      class="w-full h-full"
      :class="{ 'hidden': !isDirectMp4 && !showNativeControls }"
      :poster="poster"
      :muted="config.muted || isMuted"
      :loop="config.loop"
      playsinline
      webkit-playsinline
      x5-video-player-type="h5"
      x5-video-player-fullscreen="true"
      x5-video-orientation="landscape|portrait"
    />

    <!-- Flash 播放器 (兼容性降级) -->
    <object
      v-if="useFlashPlayer && flashUrl"
      :data="flashUrl"
      type="application/x-shockwave-flash"
      class="absolute inset-0 w-full h-full"
    >
      <param name="movie" :value="flashUrl" />
      <param name="allowFullScreen" value="true" />
      <param name="allowScriptAccess" value="always" />
      <param name="flashvars" :value="flashVars" />
    </object>

    <!-- 加载状态遮罩 -->
    <div 
      v-if="state.status === 'loading' || state.status === 'buffering'" 
      class="absolute inset-0 flex flex-col items-center justify-center bg-black/70 z-10"
    >
      <div class="loading-spinner mb-4">
        <div class="spinner-ring"></div>
        <div class="spinner-ring"></div>
        <div class="spinner-ring"></div>
      </div>
      <div class="text-white text-sm font-medium">{{ loadingText }}</div>
      <div v-if="state.bufferProgress > 0" class="mt-3 w-48 h-1 bg-white/20 rounded-full overflow-hidden">
        <div 
          class="h-full bg-sky-400 transition-all duration-300"
          :style="{ width: `${state.bufferProgress}%` }"
        />
      </div>
    </div>

    <!-- 错误状态 -->
    <div 
      v-if="state.status === 'error'" 
      class="absolute inset-0 flex flex-col items-center justify-center bg-black/80 z-10"
    >
      <el-icon class="text-5xl text-red-400 mb-4"><WarningFilled /></el-icon>
      <div class="text-white text-lg font-medium mb-2">{{ t('common.error') }}</div>
      <div class="text-gray-400 text-sm text-center max-w-md mb-4">{{ state.error }}</div>
      <div class="flex gap-3">
        <el-button size="small" @click="retry">{{ t('common.retry') }}</el-button>
        <el-button 
          v-if="alternateSources.length > 0" 
          size="small" 
          type="primary"
          @click="tryNextSource"
        >
          {{ t('player.tryOtherSource') }}  <!-- FIXED: P3 i18n -->
        </el-button>
      </div>
    </div>

    <!-- 控制栏 -->
    <div 
      v-if="showControls && state.status !== 'error'"
      class="absolute bottom-0 left-0 right-0 control-bar z-20"
      :class="{ 'control-bar-visible': controlsVisible || !isPlaying }"
      @mouseenter="showControlsBar"
      @mouseleave="scheduleHideControls"
    >
      <!-- 进度条 -->
      <div 
        class="progress-container px-4 py-2 cursor-pointer"
        @click="seekTo"
        @mousedown="startSeeking"
        @mousemove="updatePreviewTime"
      >
        <div class="progress-bar">
          <div class="progress-buffered" :style="{ width: `${bufferedPercent}%` }" />
          <div class="progress-played" :style="{ width: `${playedPercent}%` }" />
          <div 
            class="progress-handle"
            :style="{ left: `${playedPercent}%` }"
          />
        </div>
        <!-- 时间预览 -->
        <div 
          v-if="previewTime !== null && showTimePreview"
          class="time-preview"
          :style="{ left: `${previewPosition}%` }"
        >
          {{ formatTime(previewTime) }}
        </div>
      </div>

      <!-- 控制按钮 -->
      <div class="control-buttons px-4 pb-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <!-- 播放/暂停 -->
          <button class="control-btn" @click="togglePlay">
            <el-icon class="text-xl"><VideoPause v-if="isPlaying" /><VideoPlay v-else /></el-icon>
          </button>
          
          <!-- 时间显示 -->
          <div class="time-display text-sm text-white/90">
            {{ formatTime(state.currentTime) }} / {{ formatTime(state.duration) }}
          </div>

          <!-- 音量控制 -->
          <div 
            class="volume-control flex items-center"
            @mouseenter="showVolumeSlider = true"
            @mouseleave="showVolumeSlider = false"
          >
            <button class="control-btn" @click="toggleMute">
              <el-icon class="text-lg">
                <Mute v-if="isMuted || state.volume === 0" />
                <Headset v-else />
              </el-icon>
            </button>
            <div v-if="showVolumeSlider" class="volume-slider ml-1">
              <el-slider
                v-model="volumeValue"
                :min="0"
                :max="1"
                :step="0.01"
                vertical
                :height="isMobile ? '60px' : '80px'"
                @input="setVolume"
              />
            </div>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <!-- 画质选择 -->
          <div 
            v-if="state.availableQualities.length > 1"
            class="quality-selector"
            @mouseenter="showQualityMenu = true"
            @mouseleave="showQualityMenu = false"
          >
            <button class="control-btn text-sm">
              {{ getQualityLabel(state.qualityLevel) }}
            </button>
            <div v-if="showQualityMenu" class="quality-menu">
              <button
                v-for="q in state.availableQualities"
                :key="q"
                class="quality-item"
                :class="{ active: q === state.qualityLevel }"
                @click="setQuality(q)"
              >
                {{ getQualityLabel(q) }}
                <el-icon v-if="q === state.qualityLevel" class="ml-1"><Check /></el-icon>
              </button>
            </div>
          </div>

          <!-- 倍速播放 -->
          <div 
            class="speed-selector"
            @mouseenter="showSpeedMenu = true"
            @mouseleave="showSpeedMenu = false"
          >
            <button class="control-btn text-sm">{{ currentSpeed }}x</button>
            <div v-if="showSpeedMenu" class="speed-menu">
              <button
                v-for="s in speedOptions"
                :key="s"
                class="speed-item"
                :class="{ active: s === currentSpeed }"
                @click="setSpeed(s)"
              >
                {{ s }}x
                <el-icon v-if="s === currentSpeed" class="ml-1"><Check /></el-icon>
              </button>
            </div>
          </div>

          <!-- 全屏 -->
          <button class="control-btn" @click="toggleFullscreen">
            <el-icon class="text-lg"><FullScreen /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <!-- 快捷操作提示 -->
    <div 
      v-if="showShortcutHint"
      class="absolute top-4 left-4 right-4 flex items-center justify-center z-30"
    >
      <div class="shortcut-toast bg-black/80 text-white px-4 py-2 rounded-lg text-sm">
        {{ shortcutHintText }}
      </div>
    </div>

    <!-- 画质/网络状态指示 -->
    <div 
      v-if="showQualityIndicator && state.status === 'playing'"
      class="absolute top-4 right-4 flex items-center gap-2 z-20"
    >
      <div 
        v-if="metrics && metrics.fps > 0" 
        class="quality-badge"
        :class="getQualityBadgeClass()"
      >
        {{ metrics.width }}x{{ metrics.height }}
      </div>
      <div 
        v-if="metrics && metrics.bitrate > 0" 
        class="quality-badge quality-badge--bitrate"
      >
        {{ Math.round(metrics.bitrate / 1000) }}kbps
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { VideoPlay, VideoPause, Mute, Headset, FullScreen, Check, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { 
  VodSource, 
  VodPlayerState, 
  VodPlayerConfig, 
  VodQualityMetrics,
  VodPlayerEvent,
  VodQualityLevel,
  VodPlayerEventPayload
} from '../types/vod'
import { useI18n } from 'vue-i18n'
import { logger } from '@/utils/logger'

const { t } = useI18n()

// Props
const props = withDefaults(defineProps<{
  sources: VodSource | string
  config?: Partial<VodPlayerConfig>
  autoplay?: boolean
  poster?: string
  startTime?: number
  showControls?: boolean
  showQualityIndicator?: boolean
  enableSeamlessPlayback?: boolean
}>(), {
  autoplay: true,
  showControls: true,
  showQualityIndicator: true,
  enableSeamlessPlayback: false
})

const emit = defineEmits<{
  (e: 'play'): void
  (e: 'pause'): void
  (e: 'ended'): void
  (e: 'timeupdate', time: number): void
  (e: 'error', error: { code: string; message: string }): void
  (e: 'ready', duration: number): void
  (e: 'qualitychange', level: VodQualityLevel): void
  (e: 'metrics', metrics: VodQualityMetrics): void
  (e: 'statechange', state: VodPlayerState): void
}>()

// 状态
const videoEl = ref<HTMLVideoElement | null>(null)
const playerContainer = ref<HTMLDivElement | null>(null)

// 播放器配置
const defaultConfig: VodPlayerConfig = {
  autoplay: true,
  muted: false,
  loop: false,
  preload: 'auto',
  quality: 'auto',
  debug: false,
  adaptiveBuffer: true,
  minBufferTime: 500,
  maxBufferTime: 5000,
  startBufferTime: 1000,
  bufferHealthThreshold: 0.3,
  enableQualityAdaptation: true,
  smoothQualityTransition: true,
  maxRetries: 3,
  retryDelay: 1000,
  requestTimeout: 30000
}

const config = computed(() => ({ ...defaultConfig, ...props.config }))

// 播放器状态
const state = ref<VodPlayerState>({
  status: 'idle',
  currentTime: 0,
  duration: 0,
  isBuffering: false,
  bufferProgress: 0,
  qualityLevel: 'auto',
  availableQualities: ['auto'],
  muted: false,
  volume: 1
})

// 质量指标
const metrics = ref<VodQualityMetrics | null>(null)

// 内部状态
const isPlaying = ref(false)
const isMuted = ref(false)
const isFullscreen = ref(false)
const controlsVisible = ref(true)
const showTimePreview = ref(false)
const previewTime = ref<number | null>(null)
const previewPosition = ref(0)
const isSeeking = ref(false)
const showVolumeSlider = ref(false)
const showQualityMenu = ref(false)
const showSpeedMenu = ref(false)
const currentSpeed = ref(1)
const speedOptions = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]
const loadingText = ref(t('player.loading'))  // FIXED: P3 i18n

// 源管理
const currentSourceIndex = ref(0)
const retryCount = ref(0)
const isDirectMp4 = ref(false)
const useFlashPlayer = ref(false)
const flashUrl = ref('')
const flashVars = ref('')

// HLS.js 实例
let hlsInstance: unknown = null

// 隐藏控制栏定时器
let hideControlsTimer: number | null = null

// 指标收集定时器
let metricsTimer: number | null = null

// 计算属性
const alternateSources = computed(() => {
  if (typeof props.sources === 'string') return []
  const sources = props.sources as VodSource
  const alternates: string[] = []
  if (sources.hls) alternates.push(sources.hls)
  if (sources.flv) alternates.push(sources.flv)
  if (sources.https_flv) alternates.push(sources.https_flv)
  if (sources.https_hls) alternates.push(sources.https_hls)
  return alternates
})

const bufferedPercent = computed(() => {
  if (!videoEl.value || state.value.duration === 0) return 0
  const buffered = videoEl.value.buffered
  if (buffered.length === 0) return 0
  return (buffered.end(buffered.length - 1) / state.value.duration) * 100
})

const playedPercent = computed(() => {
  if (state.value.duration === 0) return 0
  return (state.value.currentTime / state.value.duration) * 100
})

const shortcutHintText = computed(() => {
  if (isPlaying.value) return t('player.spaceToPause')  // FIXED: P3 i18n
  return t('player.spaceToPlay')  // FIXED: P3 i18n
})

const showShortcutHint = computed(() => {
  return state.value.status === 'playing' || state.value.status === 'paused'
})

const isMobile = computed(() => {
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
})

const volumeValue = computed({
  get: () => state.value.volume,
  set: (val) => setVolume(val)
})

// 方法

/**
 * 初始化播放器
 */
async function initPlayer() {
  if (!videoEl.value) return
  
  state.value.status = 'loading'
  loadingText.value = t('player.initializing')  // FIXED: P3 i18n
  
  try {
    // 解析源
    const sourceUrl = resolveSourceUrl()
    if (!sourceUrl) {
      throw new Error(t('player.noSource'))  // FIXED: P3 i18n
    }
    
    // 检测播放类型
    isDirectMp4.value = sourceUrl.toLowerCase().endsWith('.mp4') || 
                        sourceUrl.includes('/record/') ||
                        sourceUrl.includes('file_path=')
    
    if (isDirectMp4.value) {
      // 直接 MP4 播放
      await initDirectMp4(sourceUrl)
    } else {
      // 流式播放
      await initStreaming(sourceUrl)
    }
    
  } catch (error: unknown) {
    handleError('init_error', error.message || t('player.initFailed'))  // FIXED: P3 i18n
  }
}

/**
 * 解析源 URL
 */
function resolveSourceUrl(): string {
  if (typeof props.sources === 'string') {
    return props.sources
  }
  
  const sources = props.sources as VodSource
  
  // 优先级: mp4 > hls > flv > 其他
  if (sources.mp4) return sources.mp4
  if (sources.hls) return sources.hls
  if (sources.flv) return sources.flv
  if (sources.https_hls) return sources.https_hls
  if (sources.https_flv) return sources.https_flv
  if (sources.ws_hls) return sources.ws_hls
  if (sources.ws_flv) return sources.ws_flv
  if (sources.wss_hls) return sources.wss_hls
  if (sources.wss_flv) return sources.wss_flv
  
  return ''
}

/**
 * 初始化直接 MP4 播放
 */
async function initDirectMp4(url: string) {
  if (!videoEl.value) return
  
  loadingText.value = t('player.buffering')  // FIXED: P3 i18n
  
  // 设置源
  videoEl.value.src = url
  videoEl.value.preload = config.value.preload || 'auto'
  
  // 等待元数据加载
  await new Promise<void>((resolve, reject) => {
    const video = videoEl.value!
    
    const onLoadedMetadata = () => {
      cleanup()
      resolve()
    }
    
    const onError = () => {
      cleanup()
      reject(new Error(t('player.loadFailed')))  // FIXED: P3 i18n
    }
    
    const cleanup = () => {
      video.removeEventListener('loadedmetadata', onLoadedMetadata)
      video.removeEventListener('error', onError)
    }
    
    video.addEventListener('loadedmetadata', onLoadedMetadata)
    video.addEventListener('error', onError)
  })
  
  // 更新状态
  state.value.duration = videoEl.value.duration
  state.value.availableQualities = ['auto']
  state.value.qualityLevel = 'auto'
  
  // 跳转到指定时间
  if (props.startTime && props.startTime > 0) {
    videoEl.value.currentTime = props.startTime
  }
  
  // 自动播放
  if (props.autoplay !== false) {
    try {
      await videoEl.value.play()
    } catch (e: Event) {
      // 自动播放被阻止，监听用户交互
      setupAutoplayUnlock()
    }
  }
  
  state.value.status = 'ready'
  emit('ready', videoEl.value.duration)
  
  // 启动指标收集
  startMetricsCollection()
}

/**
 * 初始化流式播放
 */
async function initStreaming(url: string) {
  if (!videoEl.value) return
  
  loadingText.value = t('player.connecting')  // FIXED: P3 i18n
  
  // 检测 URL 类型
  const isHls = url.includes('.m3u8') || url.includes('/hls/')
  const isFlv = url.includes('.flv') || url.includes('/flv/')
  
  if (isHls) {
    await initHlsPlayer(url)
  } else if (isFlv) {
    // FLV 需要使用 flv.js
    await initFlvPlayer(url)
  } else {
    // 尝试直接播放
    await initDirectMp4(url)
  }
}

/**
 * 初始化 HLS 播放器
 */
async function initHlsPlayer(url: string) {
  // 检查 HLS.js 是否可用
  if (typeof window !== 'undefined' && (window as Record<string, unknown>).Hls) {
    const Hls = (window as Record<string, unknown>).Hls
    
    if (Hls.isSupported()) {
      hlsInstance = new Hls({
        enableWorker: true,
        lowLatencyMode: false, // 点播不使用低延迟模式
        backBufferLength: config.value.maxBufferTime ? config.value.maxBufferTime / 1000 : 30,
        maxBufferLength: config.value.maxBufferTime ? config.value.maxBufferTime / 1000 : 30,
        maxMaxBufferLength: config.value.maxBufferTime ? (config.value.maxBufferTime / 1000) * 2 : 60,
        startLevel: -1, // 自动选择
        autoStartLoad: true,
        // 稳定性优化
        fragLoadingTimeOut: 20000,
        fragLoadingMaxRetry: 3,
        levelLoadingTimeOut: 10000,
        levelLoadingMaxRetry: 3,
        manifestLoadingTimeOut: 10000,
        manifestLoadingMaxRetry: 3,
      })
      
      hlsInstance.loadSource(url)
      hlsInstance.attachMedia(videoEl.value)
      
      hlsInstance.on(Hls.Events.MANIFEST_PARSED, (_: Record<string, unknown>, data: Record<string, unknown>) => {
        const levels = data.levels || []
        if (levels.length > 0) {
          state.value.availableQualities = ['auto', ...levels.map((l: Record<string, unknown>) => `level_${l.height}p`)]
        }
        
        state.value.status = 'ready'
        
        if (props.startTime && props.startTime > 0) {
          videoEl.value!.currentTime = props.startTime
        }
        
        if (props.autoplay !== false) {
          videoEl.value!.play().catch(() => setupAutoplayUnlock())
        }
        
        emit('ready', videoEl.value!.duration)
      })
      
      hlsInstance.on(Hls.Events.LEVEL_SWITCHED, (_: Record<string, unknown>, data: Record<string, unknown>) => {
        const level = hlsInstance.levels[data.level]
        if (level) {
          const quality = `level_${level.height}p`
          if (state.value.qualityLevel !== quality) {
            const prev = state.value.qualityLevel
            state.value.qualityLevel = quality
            emit('qualitychange', quality as VodQualityLevel)
          }
        }
      })
      
      hlsInstance.on(Hls.Events.ERROR, (_: Record<string, unknown>, data: Record<string, unknown>) => {
        if (data.fatal) {
          handleError('hls_error', data.details || t('player.hlsError'))  // FIXED: P3 i18n
        }
      })
      
      startMetricsCollection()
      return
    }
  }
  
  // 降级到原生 HLS 支持
  if (videoEl.value!.canPlayType('application/vnd.apple.mpegurl')) {
    videoEl.value!.src = url
    videoEl.value!.addEventListener('loadedmetadata', () => {
      state.value.status = 'ready'
      if (props.startTime) videoEl.value!.currentTime = props.startTime
      if (props.autoplay !== false) {
        videoEl.value!.play().catch(() => setupAutoplayUnlock())
      }
    }, { once: true })
  } else {
    throw new Error(t('player.hlsNotSupported'))  // FIXED: P3 i18n
  }
}

/**
 * 初始化 FLV 播放器
 */
async function initFlvPlayer(url: string) {
  if (typeof window !== 'undefined' && (window as Record<string, unknown>).flvjs) {
    const flvjs = (window as Record<string, unknown>).flvjs
    
    if (flvjs.isSupported()) {
      const flvPlayer = flvjs.createPlayer({
        type: 'flv',
        url: url,
        hasAudio: true,
        hasVideo: true,
        cors: true,
        isLive: false, // 点播
      }, {
        enableWorker: true,
        enableStashBuffer: true,
        stashInitialSize: 128, // 增大初始缓冲区
        autoCleanupSourceBuffer: true,
        autoCleanupMinBackwardDuration: 3,
        autoCleanupMaxBackwardDuration: 8,
        // 稳定性优化
        lazyLoad: true,
        lazyLoadMaxDuration: 3 * 60,
        lazyLoadRecoverDuration: 30,
        // 缓冲控制
        bufferingTime: config.value.startBufferTime || 1000,
        maxBufferLength: 30,
        maxBufferSize: 10 * 1024 * 1024,
      })
      
      flvPlayer.attachMediaElement(videoEl.value!)
      flvPlayer.load()
      
      flvPlayer.on(flvjs.Events.METADATA_ARRIVED, (metadata: Record<string, unknown>) => {
        if (metadata) {
          state.value.duration = metadata.duration || 0
          if (props.startTime) videoEl.value!.currentTime = props.startTime
        }
      })
      
      flvPlayer.on(flvjs.Events.ERROR, (errType: Record<string, unknown>, errDetail: Record<string, unknown>, errInfo: Record<string, unknown>) => {
        handleError('flv_error', errInfo || t('player.flvError'))  // FIXED: P3 i18n
      })
      
      flvPlayer.on(flvjs.Events.STATISTICS_INFO, (info: Record<string, unknown>) => {
        updateMetrics({
          bitrate: info.speed * 8, // 转换为 bps
          fps: info.videoData?.fps || 0,
          width: info.videoData?.width || 0,
          height: info.videoData?.height || 0,
          bufferDelay: (info.speed || 0) * 1000,
          droppedFrames: info.droppedFrames || 0,
          totalFrames: info.totalFrames || 0,
          latency: 0,
          lastUpdate: Date.now()
        })
      })
      
      state.value.status = 'ready'
      
      if (props.autoplay !== false) {
        flvPlayer.play().catch(() => setupAutoplayUnlock())
      }
      
      emit('ready', state.value.duration)
      startMetricsCollection()
      return
    }
  }
  
  throw new Error(t('player.flvNotSupported'))  // FIXED: P3 i18n
}

/**
 * 设置自动播放解锁
 */
function setupAutoplayUnlock() {
  const container = playerContainer.value
  if (!container) return
  
  const unlock = () => {
    if (videoEl.value && state.value.status === 'ready') {
      videoEl.value.play().then(() => {
        isPlaying.value = true
        state.value.status = 'playing'
        emit('play')
      }).catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
    }
    container.removeEventListener('click', unlock)
    container.removeEventListener('touchstart', unlock)
  }
  
  container.addEventListener('click', unlock)
  container.addEventListener('touchstart', unlock)
}

/**
 * 播放
 */
async function play() {
  if (!videoEl.value) return
  
  try {
    await videoEl.value.play()
    isPlaying.value = true
    state.value.status = 'playing'
    emit('play')
  } catch (e: Event) {
    handleError('play_error', e.message || t('player.playFailed'))  // FIXED: P3 i18n
  }
}

/**
 * 暂停
 */
function pause() {
  if (!videoEl.value) return
  
  videoEl.value.pause()
  isPlaying.value = false
  state.value.status = 'paused'
  emit('pause')
}

/**
 * 切换播放/暂停
 */
function togglePlay() {
  if (isPlaying.value) {
    pause()
  } else {
    play()
  }
}

/**
 * 跳转
 */
async function seekTo(event: MouseEvent) {
  if (!videoEl.value || state.value.duration === 0) return
  
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const percent = (event.clientX - rect.left) / rect.width
  const targetTime = percent * state.value.duration
  
  videoEl.value.currentTime = targetTime
  state.value.currentTime = targetTime
  emit('timeupdate', targetTime)
}

/**
 * 开始拖动进度条
 */
function startSeeking(event: MouseEvent) {
  isSeeking.value = true
  seekTo(event)
  
  const onMouseMove = (e: MouseEvent) => {
    if (isSeeking.value) seekTo(e)
  }
  
  const onMouseUp = () => {
    isSeeking.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }
  
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

/**
 * 更新预览时间
 */
function updatePreviewTime(event: MouseEvent) {
  if (!videoEl.value || state.value.duration === 0) return
  
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  
  previewTime.value = percent * state.value.duration
  previewPosition.value = percent * 100
  showTimePreview.value = true
}

/**
 * 静音切换
 */
function toggleMute() {
  if (!videoEl.value) return
  
  isMuted.value = !isMuted.value
  videoEl.value.muted = isMuted.value
  state.value.muted = isMuted.value
}

/**
 * 设置音量
 */
function setVolume(value: number) {
  if (!videoEl.value) return
  
  const vol = Math.max(0, Math.min(1, value))
  videoEl.value.volume = vol
  state.value.volume = vol
  isMuted.value = vol === 0
  state.value.muted = isMuted.value
}

/**
 * 设置画质
 */
function setQuality(quality: VodQualityLevel) {
  if (!hlsInstance || quality === 'auto') {
    if (hlsInstance) {
      hlsInstance.currentLevel = -1
    }
    state.value.qualityLevel = 'auto'
    emit('qualitychange', 'auto')
    return
  }
  
  // 解析画质等级
  const height = parseInt(quality.replace('level_', '').replace('p', ''))
  const levels = hlsInstance.levels || []
  const levelIndex = levels.findIndex((l: Record<string, unknown>) => l.height === height)
  
  if (levelIndex >= 0) {
    hlsInstance.currentLevel = levelIndex
    state.value.qualityLevel = quality
    emit('qualitychange', quality)
  }
}

/**
 * 获取画质标签
 */
function getQualityLabel(quality: VodQualityLevel): string {
  if (quality === 'auto') return t('player.autoQuality')  // FIXED: P3 i18n
  if (quality.startsWith('level_')) {
    return quality.replace('level_', '').replace('p', 'P')
  }
  return quality.toUpperCase()
}

/**
 * 设置播放速度
 */
function setSpeed(speed: number) {
  if (!videoEl.value) return
  
  currentSpeed.value = speed
  videoEl.value.playbackRate = speed
}

/**
 * 全屏切换
 */
async function toggleFullscreen() {
  const container = playerContainer.value
  if (!container) return
  
  try {
    if (!document.fullscreenElement) {
      await container.requestFullscreen()
      isFullscreen.value = true
    } else {
      await document.exitFullscreen()
      isFullscreen.value = false
    }
  } catch (e: Event) {
    logger.error(t('player.fullscreenFailed'), e)  // FIXED: P3 i18n
  }
}

/**
 * 重试
 */
async function retry() {
  retryCount.value++
  
  if (retryCount.value <= (config.value.maxRetries || 3)) {
    loadingText.value = t('player.retrying', { current: retryCount.value, max: config.value.maxRetries })  // FIXED: P3 i18n
    await new Promise(resolve => setTimeout(resolve, config.value.retryDelay || 1000))
    await initPlayer()
  } else {
    // 尝试备用源
    tryNextSource()
  }
}

/**
 * 尝试下一个备用源
 */
async function tryNextSource() {
  if (alternateSources.value.length === 0) {
    handleError('no_source', t('player.allSourcesFailed'))  // FIXED: P3 i18n
    return
  }
  
  currentSourceIndex.value = (currentSourceIndex.value + 1) % (alternateSources.value.length + 1)
  retryCount.value = 0
  
  if (currentSourceIndex.value === 0) {
    // 回到主源重试
    await retry()
  } else {
    const altUrl = alternateSources.value[currentSourceIndex.value - 1]
    loadingText.value = t('player.switchingSource')  // FIXED: P3 i18n
    await initStreaming(altUrl)
  }
}

/**
 * 处理错误
 */
function handleError(code: string, message: string) {
  state.value.status = 'error'
  state.value.error = message
  
  // 释放资源
  destroyHls()
  
  emit('error', { code, message })
  
  // 自动重试
  if (retryCount.value < (config.value.maxRetries || 3)) {
    setTimeout(() => retry(), config.value.retryDelay || 1000)
  }
}

/**
 * 格式化时间
 */
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

/**
 * 显示控制栏
 */
function showControlsBar() {
  controlsVisible.value = true
  if (hideControlsTimer) {
    clearTimeout(hideControlsTimer)
    hideControlsTimer = null
  }
}

/**
 * 计划隐藏控制栏
 */
function scheduleHideControls() {
  if (isPlaying.value) {
    hideControlsTimer = window.setTimeout(() => {
      controlsVisible.value = false
    }, 3000)
  }
}

/**
 * 获取画质状态样式
 */
function getQualityBadgeClass(): string {
  if (!metrics.value) return ''
  
  // 基于帧率判断
  if (metrics.value.fps < 15) return 'quality-badge--bad'
  if (metrics.value.fps < 24) return 'quality-badge--warning'
  return 'quality-badge--good'
}

/**
 * 更新质量指标
 */
function updateMetrics(data: Partial<VodQualityMetrics>) {
  metrics.value = {
    ...(metrics.value || {
      bitrate: 0,
      fps: 0,
      width: 0,
      height: 0,
      codec: '',
      bufferDelay: 0,
      droppedFrames: 0,
      totalFrames: 0,
      latency: 0,
      lastUpdate: 0
    }),
    ...data
  }
  emit('metrics', metrics.value)
}

/**
 * 启动指标收集
 */
function startMetricsCollection() {
  if (metricsTimer) return
  
  metricsTimer = window.setInterval(() => {
    if (!videoEl.value || state.value.status !== 'playing') return
    
    // 收集视频信息
    const videoWidth = videoEl.value.videoWidth
    const videoHeight = videoEl.value.videoHeight
    
    updateMetrics({
      width: videoWidth,
      height: videoHeight,
      fps: metrics.value?.fps || 0,
      lastUpdate: Date.now()
    })
    
    emit('statechange', { ...state.value })
  }, 1000)
}

/**
 * 停止指标收集
 */
function stopMetricsCollection() {
  if (metricsTimer) {
    clearInterval(metricsTimer)
    metricsTimer = null
  }
}

/**
 * 销毁 HLS 实例
 */
function destroyHls() {
  if (hlsInstance) {
    hlsInstance.destroy()
    hlsInstance = null
  }
}

/**
 * 销毁播放器
 */
function destroy() {
  stopMetricsCollection()
  destroyHls()
  
  if (videoEl.value) {
    videoEl.value.pause()
    videoEl.value.src = ''
    videoEl.value.load()
  }
  
  state.value = {
    status: 'idle',
    currentTime: 0,
    duration: 0,
    isBuffering: false,
    bufferProgress: 0,
    qualityLevel: 'auto',
    availableQualities: ['auto'],
    muted: false,
    volume: 1
  }
  
  if (hideControlsTimer) {
    clearTimeout(hideControlsTimer)
    hideControlsTimer = null
  }
}

// 事件监听
function setupEventListeners() {
  if (!videoEl.value) return
  
  const video = videoEl.value
  
  video.addEventListener('play', () => {
    isPlaying.value = true
    state.value.status = 'playing'
    emit('play')
    scheduleHideControls()
  })
  
  video.addEventListener('pause', () => {
    isPlaying.value = false
    state.value.status = 'paused'
    emit('pause')
    showControlsBar()
  })
  
  video.addEventListener('ended', () => {
    isPlaying.value = false
    state.value.status = 'ended'
    emit('ended')
  })
  
  video.addEventListener('timeupdate', () => {
    state.value.currentTime = video.currentTime
    emit('timeupdate', video.currentTime)
  })
  
  video.addEventListener('durationchange', () => {
    state.value.duration = video.duration
  })
  
  video.addEventListener('waiting', () => {
    state.value.status = 'buffering'
    state.value.isBuffering = true
    loadingText.value = t('player.bufferingStatus')  // FIXED: P3 i18n
  })
  
  video.addEventListener('playing', () => {
    state.value.status = 'playing'
    state.value.isBuffering = false
  })
  
  video.addEventListener('canplay', () => {
    if (state.value.status === 'loading' || state.value.status === 'buffering') {
      state.value.status = 'ready'
    }
  })
  
  video.addEventListener('progress', () => {
    if (video.buffered.length > 0) {
      const bufferedEnd = video.buffered.end(video.buffered.length - 1)
      state.value.bufferProgress = (bufferedEnd / video.duration) * 100
    }
  })
  
  video.addEventListener('stalled', () => {
    state.value.status = 'buffering'
    state.value.isBuffering = true
    loadingText.value = t('player.stutteringRecovery')  // FIXED: P3 i18n
  })
  
  video.addEventListener('error', () => {
    const error = video.error
    let code = 'unknown_error'
    let message = t('player.playError')  // FIXED: P3 i18n

    if (error) {
      switch (error.code) {
        case MediaError.MEDIA_ERR_ABORTED:
          code = 'aborted'
          message = t('player.playAborted')  // FIXED: P3 i18n
          break
        case MediaError.MEDIA_ERR_NETWORK:
          code = 'network_error'
          message = t('player.networkError')  // FIXED: P3 i18n
          break
        case MediaError.MEDIA_ERR_DECODE:
          code = 'decode_error'
          message = t('player.decodeError')  // FIXED: P3 i18n
          break
        case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
          code = 'not_supported'
          message = t('player.formatNotSupported')  // FIXED: P3 i18n
          break
      }
    }
    
    handleError(code, message)
  })
  
  // 键盘快捷键
  const handleKeydown = (e: KeyboardEvent) => {
    if (state.value.status === 'error') return
    
    const target = e.target as HTMLElement
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
    
    switch (e.code) {
      case 'Space':
        e.preventDefault()
        togglePlay()
        break
      case 'ArrowLeft':
        e.preventDefault()
        if (video) video.currentTime = Math.max(0, video.currentTime - 10)
        break
      case 'ArrowRight':
        e.preventDefault()
        if (video) video.currentTime = Math.min(video.duration, video.currentTime + 10)
        break
      case 'ArrowUp':
        e.preventDefault()
        setVolume(state.value.volume + 0.1)
        break
      case 'ArrowDown':
        e.preventDefault()
        setVolume(state.value.volume - 0.1)
        break
      case 'KeyM':
        toggleMute()
        break
      case 'KeyF':
        toggleFullscreen()
        break
    }
  }
  
  document.addEventListener('keydown', handleKeydown)
  
  // 全屏变化
  const handleFullscreenChange = () => {
    isFullscreen.value = !!document.fullscreenElement
  }
  
  document.addEventListener('fullscreenchange', handleFullscreenChange)
}

// 生命周期
onMounted(() => {
  nextTick(() => {
    initPlayer()
    setupEventListeners()
  })
})

onBeforeUnmount(() => {
  destroy()
})

// 暴露方法
defineExpose({
  play,
  pause,
  togglePlay,
  seekTo: (time: number) => {
    if (videoEl.value) videoEl.value.currentTime = time
  },
  setVolume,
  setSpeed,
  setQuality,
  toggleFullscreen,
  getMetrics: () => metrics.value,
  destroy
})
</script>

<style scoped>
.enhanced-vod-player {
  user-select: none;
  -webkit-user-select: none;
}

.enhanced-vod-player video {
  object-fit: contain;
  background: #000;
}

/* 全屏样式 */
.enhanced-vod-player.is-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9999;
}

/* 加载动画 */
.loading-spinner {
  width: 48px;
  height: 48px;
  position: relative;
}

.spinner-ring {
  position: absolute;
  inset: 0;
  border: 3px solid transparent;
  border-top-color: #38bdf8;
  border-radius: 50%;
  animation: spinner-rotate 1.2s linear infinite;
}

.spinner-ring:nth-child(2) {
  inset: 6px;
  animation-delay: -0.4s;
  border-top-color: #22d3ee;
}

.spinner-ring:nth-child(3) {
  inset: 12px;
  animation-delay: -0.8s;
  border-top-color: #67e8f9;
}

@keyframes spinner-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 控制栏 */
.control-bar {
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.8));
  opacity: 0;
  transform: translateY(100%);
  transition: all 0.3s ease;
}

.control-bar-visible {
  opacity: 1;
  transform: translateY(0);
}

.enhanced-vod-player:hover .control-bar,
.control-bar:hover {
  opacity: 1;
  transform: translateY(0);
}

/* 进度条 */
.progress-container {
  position: relative;
}

.progress-bar {
  position: relative;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  cursor: pointer;
  transition: height 0.15s ease;
}

.progress-container:hover .progress-bar {
  height: 6px;
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
  width: 12px;
  height: 12px;
  background: #38bdf8;
  border-radius: 50%;
  transform: translate(-50%, -50%) scale(0);
  transition: transform 0.15s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.progress-container:hover .progress-handle {
  transform: translate(-50%, -50%) scale(1);
}

/* 时间预览 */
.time-preview {
  position: absolute;
  bottom: 20px;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

/* 控制按钮 */
.control-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
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
.volume-slider {
  background: rgba(0, 0, 0, 0.8);
  padding: 8px 4px;
  border-radius: 4px;
}

/* 画质/倍速菜单 */
.quality-selector,
.speed-selector {
  position: relative;
}

.quality-menu,
.speed-menu {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 8px;
  background: rgba(0, 0, 0, 0.9);
  border-radius: 6px;
  overflow: hidden;
  min-width: 100px;
}

.quality-item,
.speed-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 8px 16px;
  color: #fff;
  background: transparent;
  border: none;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.quality-item:hover,
.speed-item:hover {
  background: rgba(255, 255, 255, 0.1);
}

.quality-item.active,
.speed-item.active {
  color: #38bdf8;
}

/* 画质指示器 */
.quality-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
}

.quality-badge--good {
  color: #4ade80;
}

.quality-badge--warning {
  color: #fbbf24;
}

.quality-badge--bad {
  color: #f87171;
}

.quality-badge--bitrate {
  color: #a78bfa;
}

/* 快捷提示 */
.shortcut-toast {
  animation: fadeInOut 2s ease forwards;
}

@keyframes fadeInOut {
  0% { opacity: 0; transform: translateY(-10px); }
  15% { opacity: 1; transform: translateY(0); }
  85% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-10px); }
}

/* 时间显示 */
.time-display {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}
</style>
