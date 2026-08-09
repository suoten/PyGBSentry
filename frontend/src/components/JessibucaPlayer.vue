<template>
  <div ref="playerRoot" class="player-with-zoom relative w-full h-full">
    <div 
      ref="container" 
      class="jessibuca-container"
      @mousedown="handleMouseDown"
      @mousemove="handleMouseMove"
      @mouseup="handleMouseUp"
      @mouseleave="handleMouseLeave"
    ></div>
    
    <!-- DragZoom Box Overlay -->
    <div 
      v-if="isDragging && dragBoxStyle" 
      class="absolute border-2 border-green-500 bg-green-500/20 pointer-events-none z-10"
      :style="dragBoxStyle"
    ></div>

    <div v-if="overlayVisible" class="absolute inset-0 flex items-center justify-center z-20 bg-black/50 backdrop-blur-sm">
      <div class="flex flex-col items-center justify-center text-white p-4 text-center">
        <el-icon v-if="overlayKind === 'loading'" class="is-loading text-3xl mb-2 text-sky-400"><Loading /></el-icon>
        <el-icon v-else class="text-3xl mb-2 text-red-500"><Warning /></el-icon>
        <div class="text-sm font-medium">{{ overlayTitle }}</div>
        <div class="text-xs mt-1 text-white/70 max-w-[200px] truncate" :title="overlayMessage">{{ overlayMessage }}</div>
        
        <div class="mt-3 flex gap-2" v-if="overlayKind === 'error'">
          <button
            v-if="showRefreshButton"
            class="px-3 py-1 rounded bg-sky-500 hover:bg-sky-600 text-xs text-white transition-colors"
            @click="emit('refreshRequest')"
          >
            {{ t('player.jessibuca.reinvite') }}
          </button>
          <button
            v-else-if="showLocalRetryButton"
            class="px-3 py-1 rounded bg-sky-500 hover:bg-sky-600 text-xs text-white transition-colors"
            @click="retry"
          >
            {{ t('player.jessibuca.retryPlay') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n' // FIXED: 国际化
import { Loading, Warning } from '@element-plus/icons-vue'

type PlayRequestUi = {
  status: 'idle' | 'requesting' | 'waiting' | 'ready' | 'error'
  stage?: string
  progress?: number
  message?: string
  suggestion?: string
  retryable?: boolean
  diagnostics?: Record<string, unknown>
}

const { t } = useI18n() // FIXED: 国际化

const props = withDefaults(defineProps<{
  videoUrl: string
  hlsUrl?: string
  codec?: string
  candidates?: string[]
  request?: PlayRequestUi | null
  suggestedPlayer?: 'h265' | 'webrtc' | ''
  hasAudio?: boolean
}>(), {
  hasAudio: true
})

const emit = defineEmits<{
  (e: 'status', v: { status: 'loading' | 'ready' | 'error'; hint?: string }): void
  (e: 'error', v: { hint: string }): void
  (e: 'refreshRequest'): void
  (e: 'suggestSwitch', v: 'h265' | 'webrtc'): void
  (e: 'dragZoom', v: { 
    length: number, 
    width: number, 
    mid_point_x: number, 
    mid_point_y: number, 
    length_x: number, 
    length_y: number 
  }): void
}>()

const uiStatus = ref<'loading' | 'ready' | 'error'>('loading')
const errorHint = ref('')
const candidateIndex = ref(0)
const initSeq = ref(0)
const decoderMode = ref<'performance' | 'compatibility'>('performance')
const showStatusDetails = ref(false)
const jessibucaKbps = ref(0)
const lastPositiveKbpsAt = ref(0)
const slowFrameGraceUsed = ref(false)
const lastVideoInfoAt = ref(0)
const lastRenderSignalAt = ref(0)

// DragZoom state
const isDragging = ref(false)
const startPos = ref({ x: 0, y: 0 })
const currentPos = ref({ x: 0, y: 0 })

const dragBoxStyle = computed(() => {
  if (!isDragging.value) return null
  const left = Math.min(startPos.value.x, currentPos.value.x)
  const top = Math.min(startPos.value.y, currentPos.value.y)
  const width = Math.abs(currentPos.value.x - startPos.value.x)
  const height = Math.abs(currentPos.value.y - startPos.value.y)
  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`
  }
})

const handleMouseDown = (e: MouseEvent) => {
  // Only handle left click and if we have a valid container
  if (e.button !== 0 || !container.value) return
  
  // Optional: check if a specific "DragZoom Mode" is active via props or inject
  // For now, we enable it unconditionally or you can wrap this in a prop check
  
  const rect = container.value.getBoundingClientRect()
  startPos.value = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
  currentPos.value = { ...startPos.value }
  isDragging.value = true
}

const handleMouseMove = (e: MouseEvent) => {
  if (!isDragging.value || !container.value) return
  const rect = container.value.getBoundingClientRect()
  currentPos.value = {
    x: Math.max(0, Math.min(e.clientX - rect.left, rect.width)),
    y: Math.max(0, Math.min(e.clientY - rect.top, rect.height))
  }
}

const handleMouseUp = (e: MouseEvent) => {
  if (!isDragging.value || !container.value) return
  isDragging.value = false
  
  const rect = container.value.getBoundingClientRect()
  const width = rect.width
  const height = rect.height
  
  const left = Math.min(startPos.value.x, currentPos.value.x)
  const top = Math.min(startPos.value.y, currentPos.value.y)
  const boxWidth = Math.abs(currentPos.value.x - startPos.value.x)
  const boxHeight = Math.abs(currentPos.value.y - startPos.value.y)
  
  // Ignore tiny clicks (not a real drag)
  if (boxWidth < 20 || boxHeight < 20) return
  
  const midPointX = left + (boxWidth / 2)
  const midPointY = top + (boxHeight / 2)
  
  emit('dragZoom', {
    length: Math.round(height), // Total container height (GB28181 uses length for height)
    width: Math.round(width),   // Total container width
    mid_point_x: Math.round(midPointX),
    mid_point_y: Math.round(midPointY),
    length_x: Math.round(boxWidth),
    length_y: Math.round(boxHeight)
  })
}

const handleMouseLeave = (e: MouseEvent) => {
  if (isDragging.value) {
    handleMouseUp(e)
  }
}

const candidates = computed(() => {
  const list: string[] = []
  const push = (v: unknown) => {
    const value = String(v || '').trim()
    if (!value) return
    if (!list.includes(value)) list.push(value)
  }
  for (const item of props.candidates || []) push(item)
  push(props.videoUrl)
  if (props.hlsUrl) push(props.hlsUrl)
  return list
})

const currentUrl = computed(() => candidates.value[candidateIndex.value] || '')
const isFlvLikeUrl = computed(() => {
  const url = String(currentUrl.value || '').toLowerCase()
  return url.includes('.flv') || url.includes('/live/') || url.includes('type=flv')
})
const isHlsLikeUrl = computed(() => {
  const url = String(currentUrl.value || '').toLowerCase()
  return url.includes('.m3u8') || url.includes('/hls/')
})

// Jessibuca 不支持 HLS，当 URL 是 HLS 时应该使用原生 video 标签
// 这里提前检测并准备切换到 H265 播放器（使用 HLS URL）
const requestStatus = computed(() => props.request?.status || 'idle')
const requestRetryable = computed(() => Boolean(props.request?.retryable ?? true))
const requestProgress = computed(() => {
  const value = props.request?.progress
  if (typeof value === 'number' && Number.isFinite(value)) return Math.max(-1, Math.min(100, Math.round(value)))
  return requestStatus.value === 'error' ? -1 : 0
})
const requestMessage = computed(() => String(props.request?.message || '').trim())
const requestSuggestion = computed(() => String(props.request?.suggestion || '').trim())
const requestStage = computed(() => String(props.request?.stage || '').trim())
const requestDiagnosticsText = computed(() => {
  const d = props.request?.diagnostics
  if (!d || typeof d !== 'object') return ''
  try {
    const payload = JSON.stringify(d, null, 2)
    return payload.length > 0 ? payload : ''
  } catch {
    return ''
  }
})
const requestProbe = computed<Record<string, unknown> | null>(() => {
  const probe = props.request?.diagnostics?.probe
  return probe && typeof probe === 'object' ? (probe as Record<string, unknown>) : null
})
const overlayVisible = computed(() => uiStatus.value !== 'ready')
const overlayKind = computed<'loading' | 'error'>(() => {
  if (requestStatus.value === 'error' || uiStatus.value === 'error') return 'error'
  return 'loading'
})
const overlayTitle = computed(() => {
  if (requestStatus.value === 'requesting') return t('player.jessibuca.opening') // FIXED: 国际化
  if (requestStatus.value === 'waiting') return t('player.jessibuca.establishing') // FIXED: 国际化
  if (requestStatus.value === 'error') return t('player.jessibuca.cannotPlayNow') // FIXED: 国际化
  if (uiStatus.value === 'error') return t('player.jessibuca.cannotPlayNow') // FIXED: 国际化
  return t('player.jessibuca.connectingVideo') // FIXED: 国际化
})
const overlayMessage = computed(() => {
  if (requestStatus.value === 'requesting') return t('player.jessibuca.requestingStream') // FIXED: 国际化
  if (requestStatus.value === 'waiting') {
    if (decoderMode.value === 'compatibility') return t('player.jessibuca.switchedStableMode') // FIXED: 国际化
    return t('player.jessibuca.streamInitiated') // FIXED: 国际化
  }
  if (requestStatus.value === 'error') return requestMessage.value || t('player.jessibuca.playNotEstablished') // FIXED: 国际化
  if (uiStatus.value === 'error') return errorHint.value || t('player.jessibuca.playerNoFrame') // FIXED: 国际化
  return decoderMode.value === 'compatibility' ? t('player.jessibuca.switchedStableReconnecting') : t('player.jessibuca.connectingStreamWait') // FIXED: 国际化
})
const overlaySubMessage = computed(() => {
  if (requestStatus.value === 'requesting') return t('player.jessibuca.windowOpened') // FIXED: 国际化
  if (requestStatus.value === 'waiting') return t('player.jessibuca.waitLongerTip') // FIXED: 国际化
  if (requestStatus.value === 'error') return requestSuggestion.value || t('player.jessibuca.canRetryOrSwitch') // FIXED: 国际化
  if (uiStatus.value === 'error') return decoderMode.value === 'compatibility' ? t('player.jessibuca.compatModeFailed') : t('player.jessibuca.willTryStableMode') // FIXED: 国际化
  return ''
})
const overlayProgress = computed(() => {
  if (requestStatus.value !== 'idle') return requestProgress.value
  return overlayKind.value === 'error' ? -1 : 8
})
const statusItems = computed(() => {
  const probe = requestProbe.value
  const zlmProbeOk = Boolean(props.request?.diagnostics?.zlm_probe_ok)
  const streamFound = Boolean(probe?.stream_found)
  const playable = Boolean(probe?.playable)
  const requestDone = requestStatus.value === 'waiting' || requestStatus.value === 'ready' || requestStatus.value === 'error'
  return [
    {
      label: t('player.jessibuca.deviceStatus'), // FIXED: 国际化
      text: requestDone ? t('player.jessibuca.responded') : t('player.jessibuca.processing'), // FIXED: 国际化
      state: requestDone ? 'done' : 'loading'
    },
    {
      label: t('player.jessibuca.playLink'), // FIXED: 国际化
      text: zlmProbeOk ? t('player.jessibuca.normal') : requestStatus.value === 'error' ? t('player.jessibuca.abnormal') : t('player.jessibuca.checking'), // FIXED: 国际化
      state: zlmProbeOk ? 'done' : requestStatus.value === 'error' && requestProbe.value ? 'error' : 'loading'
    },
    {
      label: t('player.jessibuca.frameEstablish'), // FIXED: 国际化
      text: playable || uiStatus.value === 'ready' ? t('player.jessibuca.completed') : streamFound ? t('player.jessibuca.inProgress') : overlayKind.value === 'error' ? t('player.jessibuca.failed') : t('player.jessibuca.preparing'), // FIXED: 国际化
      state: playable || uiStatus.value === 'ready' ? 'done' : overlayKind.value === 'error' ? 'error' : 'loading'
    }
  ]
})
const showRefreshButton = computed(() => requestStatus.value === 'error' && requestRetryable.value)
const showLocalRetryButton = computed(() => requestStatus.value !== 'error' && uiStatus.value === 'error')
const showDetailsButton = computed(() => overlayKind.value === 'error' && !!requestDiagnosticsText.value)

const suggestAlternativePlayer = (hint: string) => {
  const nextPlayer = props.suggestedPlayer
  if (!nextPlayer) return false
  uiStatus.value = 'error'
  errorHint.value = hint
  emit('status', { status: 'error', hint })
  emit('error', { hint })
  emit('suggestSwitch', nextPlayer)
  return true
}

const scheduleWatchdog = (delay = 12000) => {
  if (watchdogTimer) {
    clearTimeout(watchdogTimer)
    watchdogTimer = null
  }
  watchdogTimer = setTimeout(() => {
    if (uiStatus.value === 'ready') return
    let isPlaying = false
    try {
      if (jessibuca && typeof jessibuca.isPlaying === 'function') {
        isPlaying = !!jessibuca.isPlaying()
      }
    } catch { /* ignore */ }
    if (isPlaying) {
      uiStatus.value = 'ready'
      errorHint.value = ''
      emit('status', { status: 'ready' })
      return
    }
    const hasRecentData = jessibucaKbps.value > 0 && Date.now() - lastPositiveKbpsAt.value < 8000
    const hasRecentVideoInfo = lastVideoInfoAt.value > 0 && Date.now() - lastVideoInfoAt.value < 12000
    const hasRecentRenderSignal = lastRenderSignalAt.value > 0 && Date.now() - lastRenderSignalAt.value < 12000
    if (hasRecentData && !slowFrameGraceUsed.value) {
      slowFrameGraceUsed.value = true
      uiStatus.value = 'loading'
      errorHint.value = hasRecentVideoInfo ? t('player.jessibuca.parsedVideoFrame') : t('player.jessibuca.receivedStream') // FIXED: 国际化
      emit('status', { status: 'loading', hint: errorHint.value })
      scheduleWatchdog(decoderMode.value === 'compatibility' ? 12000 : 10000)
      return
    }
    if (hasRecentData && decoderMode.value === 'compatibility') {
      const suggested = suggestAlternativePlayer(
        hasRecentVideoInfo || hasRecentRenderSignal
          ? t('player.jessibuca.noFrameSuggestSwitch') // FIXED: 国际化
          : t('player.jessibuca.noStreamFrameSuggestSwitch') // FIXED: 国际化
      )
      if (suggested) return
    }
    const switchedCompat = switchToCompatibilityMode(t('player.jessibuca.streamConnectedNoFrame')) // FIXED: 国际化
    if (switchedCompat) return
    const switched = switchToNextCandidate(hasRecentData ? t('player.jessibuca.hasSpeedNoFrame') : t('player.jessibuca.timeoutSwitching')) // FIXED: 国际化
    if (!switched) {
      uiStatus.value = 'error'
      errorHint.value = hasRecentData ? t('player.jessibuca.speedNoFrameSwitch') : t('player.jessibuca.timeoutCheck') // FIXED: 国际化
      emit('status', { status: 'error', hint: errorHint.value })
      emit('error', { hint: errorHint.value })
    }
  }, delay)
}

const switchToNextCandidate = (hint: string) => {
  const list = candidates.value
  if (candidateIndex.value + 1 >= list.length) return false
  candidateIndex.value += 1
  decoderMode.value = 'performance'
  errorHint.value = hint
  Promise.resolve().then(() => initByCodec())
  return true
}

const switchToCompatibilityMode = (hint: string) => {
  if (decoderMode.value === 'compatibility' || !isFlvLikeUrl.value) return false
  decoderMode.value = 'compatibility'
  errorHint.value = hint
  Promise.resolve().then(() => initByCodec())
  return true
}

const playerRoot = ref<HTMLElement | null>(null)
const container = ref<HTMLElement | null>(null)
let jessibuca: Record<string, unknown> = null
let h265Player: Record<string, unknown> = null
let h265VideoEl: HTMLVideoElement | null = null
let watchdogTimer: Record<string, unknown> = null
let resizeObserver: ResizeObserver | null = null
let teardownTask: Promise<void> = Promise.resolve()
let fallbackTimer: Record<string, unknown> = null
const h265webInitSeq = ref(0)

const markJessibucaDestroying = (instance: Record<string, unknown>) => {
  if (!instance) return
  try {
    ;(instance as Record<string, unknown>).__pygbsentryDestroying = true
  } catch { /* cleanup: ignore */ }
}

const patchJessibucaInternalReset = (instance: Record<string, unknown>) => {
  if (!instance || typeof instance._resetPlayer !== 'function') return
  if ((instance as Record<string, unknown>).__pygbsentryResetPatched) return
  const rawResetPlayer = instance._resetPlayer.bind(instance)
  ;(instance as Record<string, unknown>).__pygbsentryResetPatched = true
  instance._resetPlayer = async (...args: unknown[]) => {
    if ((instance as Record<string, unknown>).__pygbsentryDestroying) return
    try {
      return await rawResetPlayer(...args)
    } catch (err: unknown) {
      const message = err instanceof Error ? String(err.message || err) : String(err || '')
      if (message.includes("reading 'destroy'") || message.includes('removeChild')) return
      throw err
    }
  }
}

const H265WEB_PUBLIC_TOKEN = (import.meta as Record<string, unknown>)?.env?.VITE_H265WEB_TOKEN || ''

const loadScript = (src: string) =>
  new Promise<void>((resolve, reject) => {
    const existed = document.querySelector(`script[src="${src}"]`) as HTMLScriptElement | null
    if (existed) {
      if ((existed as Record<string, unknown>).dataset.loaded === '1') {
        resolve()
        return
      }
      existed.addEventListener('load', () => resolve(), { once: true })
      existed.addEventListener('error', () => reject(new Error(`load script failed: ${src}`)), { once: true })
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => {
      ;(script as Record<string, unknown>).dataset.loaded = '1'
      resolve()
    }
    script.onerror = () => reject(new Error(`load script failed: ${src}`))
    document.head.appendChild(script)
  })

const loadFirstOk = async (srcList: string[]) => {
  let lastErr: unknown = null
  for (const src of srcList) {
    try {
      await loadScript(src)
      return src
    } catch (e) {
      lastErr = e
    }
  }
  throw lastErr || new Error('load script failed')
}

const resolveJessibucaCtor = async () => {
  const win = window as Record<string, unknown>
  if (typeof win.Jessibuca === 'function') return win.Jessibuca
  try {
    await loadFirstOk([
      '/static/jessibuca/jessibuca.js',
      '/static/js/jessibuca/jessibuca.js',
      '/node_modules/jessibuca/dist/jessibuca.js',
      '/node_modules/jessibuca/jessibuca.js'
    ])
  } catch {
    return null
  }
  return typeof win.Jessibuca === 'function' ? win.Jessibuca : null
}

const destroyPlayers = async () => {
  const run = async () => {
    jessibucaKbps.value = 0
    lastPositiveKbpsAt.value = 0
    slowFrameGraceUsed.value = false
    lastVideoInfoAt.value = 0
    lastRenderSignalAt.value = 0
    if (watchdogTimer) {
      clearTimeout(watchdogTimer)
      watchdogTimer = null
    }
    if (fallbackTimer) {
      clearTimeout(fallbackTimer)
      fallbackTimer = null
    }
    if (resizeObserver) {
      try {
        resizeObserver.disconnect()
      } catch { /* ignore */ }
      resizeObserver = null
    }
    const instance = jessibuca
    jessibuca = null
    if (instance) {
      markJessibucaDestroying(instance)
      try {
        const ret = instance.destroy()
        if (ret && typeof ret.then === 'function') {
          await ret.catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
        }
      } catch { /* cleanup: ignore */ }
    }
    const localH265Player = h265Player
    h265Player = null
    if (localH265Player && typeof localH265Player.destroy === 'function') {
      try {
        const ret = localH265Player.destroy()
        if (ret && typeof ret.then === 'function') {
          await ret.catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
        }
      } catch { /* cleanup: ignore */ }
    } else if (localH265Player && typeof localH265Player.release === 'function') {
      try {
        const ret = localH265Player.release()
        if (ret && typeof ret.then === 'function') {
          await ret.catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
        }
      } catch { /* cleanup: ignore */ }
    }
    const localVideoEl = h265VideoEl
    h265VideoEl = null
    if (localVideoEl) {
      try {
        localVideoEl.pause()
      } catch { /* cleanup: ignore */ }
      try {
        if (localVideoEl.parentNode) localVideoEl.parentNode.removeChild(localVideoEl)
      } catch { /* cleanup: ignore */ }
    }
    if (container.value) {
      try {
        container.value.replaceChildren()
      } catch {
        try {
          container.value.innerHTML = ''
        } catch { /* cleanup: ignore */ }
      }
      try {
        container.value.removeAttribute('data-jessibuca')
      } catch { /* cleanup: ignore */ }
      try {
        ;(container.value as Record<string, unknown>).dataset.jessibuca = ''
      } catch { /* cleanup: ignore */ }
    }
  }
  teardownTask = teardownTask.then(run, run)
  await teardownTask
}

const initPlayer = (JessibucaCtor: Record<string, unknown>) => {
  if (!container.value || typeof JessibucaCtor !== 'function') return

  // Jessibuca 不支持 HLS，如果当前 URL 是 HLS，提前提示并切换到备选方案
  if (isHlsLikeUrl.value) {
    uiStatus.value = 'error'
    errorHint.value = t('player.jessibuca.hlsNotForJessibuca') // FIXED: 国际化
    emit('status', { status: 'error', hint: errorHint.value })
    emit('error', { hint: errorHint.value })
    emit('suggestSwitch', 'h265')  // 建议切换到 H265 播放器
    return
  }

  uiStatus.value = 'loading'
  const list = candidates.value
  const idx = Math.max(0, Math.min(candidateIndex.value, Math.max(0, list.length - 1)))
  const suffix = list.length > 1 ? `（${idx + 1}/${list.length}）` : ''
  errorHint.value = t('player.jessibuca.connectingStreamSuffix', { suffix }) // FIXED: 国际化
  slowFrameGraceUsed.value = false
  emit('status', { status: 'loading' })

  try {
    container.value.innerHTML = ''
  } catch { /* cleanup: ignore */ }
  try {
    container.value.removeAttribute('data-jessibuca')
  } catch { /* cleanup: ignore */ }
  try {
    ;(container.value as Record<string, unknown>).dataset.jessibuca = ''
  } catch { /* ignore */ }

  const playUrl = String(currentUrl.value || '').trim()
  const lowerPlayUrl = playUrl.toLowerCase()
  const isFlvLike = lowerPlayUrl.includes('.flv') || lowerPlayUrl.includes('/live/')
  const options: Record<string, unknown> = {
    container: container.value,
    videoBuffer: 0.2,
    isResize: true,
    isFullResize: false,
    isFlv: isFlvLike,
    text: '',
    controlAutoHide: true,
    decoder: '/static/jessibuca/decoder.js',
    hotKey: false,
    wasmDecodeErrorReplay: false,
    wcsUseVideoRender: true,
    autoWasm: true,
    forceNoOffscreen: false,
    useMSE: true,
    useWCS: false,
    hiddenAutoPause: false,
    keepScreenOn: false,
    loadingText: t('player.jessibuca.pleaseWaitLoading'), // FIXED: 国际化
    debug: false,
    // ========== 实时预览优化配置 ==========
    // 缓冲时间（防抖动关键！）：建议 500-1000ms
    bufferTime: 1000,
    // 性能优化
    workloadLevel: 1,            // 低负载模式，更稳定
    showBandwidth: false,        // 关闭性能面板，减少干扰
    // 超时配置
    timeout: 15,                 // 15秒超时
    loadingTimeout: 15,
    heartTimeout: 8,             // 增加心跳超时
    heartTimeoutReplay: true,
    loadingTimeoutReplay: true,
    heartTimeoutReplayTimes: 5,  // 增加重试次数
    loadingTimeoutReplayTimes: 5,
    supportDblclickFullscreen: true,
    openWebglAlignment: false,
    hasAudio: props.hasAudio !== false,
    useWebFullScreen: true,
    operateBtns: {
      fullscreen: true,
      screenshot: true,
      play: true,
      audio: props.hasAudio !== false,
    }
  }

  if (decoderMode.value === 'compatibility') {
    options.useWCS = false
    options.useMSE = false
    options.forceNoOffscreen = true
  }
  jessibuca = new JessibucaCtor(options)
  patchJessibucaInternalReset(jessibuca)

  if (playUrl && window.location.protocol === 'https:' && (playUrl.startsWith('http://') || playUrl.startsWith('ws://'))) {
    const switched = switchToNextCandidate(t('player.jessibuca.httpsMixedContent')) // FIXED: 国际化
    if (!switched) {
      uiStatus.value = 'error'
      errorHint.value = t('player.jessibuca.httpsCannotLoad') // FIXED: 国际化
      emit('status', { status: 'error', hint: errorHint.value })
      emit('error', { hint: errorHint.value })
    }
    return
  }
  if (playUrl) jessibuca.play(playUrl)

  if (!resizeObserver && typeof ResizeObserver !== 'undefined') {
      const host = playerRoot.value || container.value
      if (host) {
        resizeObserver = new ResizeObserver(() => {
          try {
            if (jessibuca && typeof jessibuca.resize === 'function') {
              requestAnimationFrame(() => jessibuca.resize())
            }
            if (h265Player && typeof h265Player.resize === 'function') {
              requestAnimationFrame(() => h265Player.resize())
            }
          } catch { /* cleanup: ignore */ }
        })
        try {
          resizeObserver.observe(host)
        } catch { /* cleanup: ignore */ }
      }
    }

  try {
    if (typeof jessibuca.on === 'function') {
      jessibuca.on('error', (e: unknown) => {
        const hint = (() => {
          if (e == null) return t('player.playFailed') // FIXED: 国际化
          if (e instanceof Error) return String(e.message || e)
          if (typeof e === 'object') {
            const o = e as Record<string, unknown>
            const fromKeys = o.message ?? o.msg
            if (fromKeys != null && String(fromKeys) !== '') return String(fromKeys)
            return String(e)
          }
          return String(e || t('player.playFailed')) // FIXED: 国际化
        })()
        const switchedCompat = switchToCompatibilityMode(t('player.jessibuca.streamDataDecodeFailed')) // FIXED: 国际化
        if (switchedCompat) return
        const switched = switchToNextCandidate(t('player.jessibuca.addressUnavailable', { hint })) // FIXED: 国际化
        if (!switched) {
          uiStatus.value = 'error'
          errorHint.value = hint
          emit('status', { status: 'error', hint })
          emit('error', { hint })
        }
      })
      jessibuca.on('play', () => {
        if (fallbackTimer) {
          clearTimeout(fallbackTimer)
          fallbackTimer = null
        }
        jessibucaKbps.value = 0
        lastPositiveKbpsAt.value = 0
        slowFrameGraceUsed.value = false
        lastVideoInfoAt.value = Date.now()
        lastRenderSignalAt.value = Date.now()
        uiStatus.value = 'ready'
        errorHint.value = ''
        emit('status', { status: 'ready' })
      })
      jessibuca.on('loading', () => {
        uiStatus.value = 'loading'
        emit('status', { status: 'loading' })
      })
      jessibuca.on('kBps', (value: unknown) => {
        const num = Number(value)
        if (Number.isFinite(num)) {
          jessibucaKbps.value = num
          if (num > 0) {
            lastPositiveKbpsAt.value = Date.now()
          }
        }
      })
      jessibuca.on('videoInfo', () => {
        lastVideoInfoAt.value = Date.now()
      })
      jessibuca.on('playToRenderTimes', () => {
        lastRenderSignalAt.value = Date.now()
      })
      jessibuca.on('timeout', () => {
        if (fallbackTimer) clearTimeout(fallbackTimer)
        fallbackTimer = setTimeout(() => {
          fallbackTimer = null
          if (uiStatus.value === 'ready') return
          if (jessibucaKbps.value > 0) {
            errorHint.value = lastVideoInfoAt.value > 0 ? t('player.jessibuca.parsedVideoFrame') : t('player.jessibuca.receivedStream') // FIXED: 国际化
            emit('status', { status: 'loading', hint: errorHint.value })
            return
          }
          
          // Check for "Fake Stream" where connection is made but no data arrives
          const isFakeStream = jessibucaKbps.value === 0 && Date.now() - lastPositiveKbpsAt.value > 5000;
          
          if (decoderMode.value === 'compatibility' && jessibucaKbps.value > 0) {
            const suggested = suggestAlternativePlayer(t('player.jessibuca.compatInsufficient')) // FIXED: 国际化
            if (suggested) return
          }
          const switchedCompat = switchToCompatibilityMode(t('player.jessibuca.slowSwitchStable')) // FIXED: 国际化
          if (switchedCompat) return
          const switched = switchToNextCandidate(t('player.jessibuca.addressTimeoutSwitch')) // FIXED: 国际化
          if (!switched) {
            uiStatus.value = 'error'
            errorHint.value = isFakeStream 
              ? t('player.jessibuca.noVideoData')  // FIXED: 国际化
              : t('player.jessibuca.playConnectTimeout') // FIXED: 国际化
            emit('status', { status: 'error', hint: errorHint.value })
            emit('error', { hint: errorHint.value })
          }
        }, 0)
      })
      jessibuca.on('loadingTimeout', () => {
        if (fallbackTimer) clearTimeout(fallbackTimer)
        fallbackTimer = setTimeout(() => {
          fallbackTimer = null
          if (uiStatus.value === 'ready') return
          if (jessibucaKbps.value > 0) {
            errorHint.value = lastVideoInfoAt.value > 0 ? t('player.jessibuca.parsedVideoFrame') : t('player.jessibuca.receivedStream') // FIXED: 国际化
            emit('status', { status: 'loading', hint: errorHint.value })
            return
          }
          if (decoderMode.value === 'compatibility' && jessibucaKbps.value > 0) {
            const suggested = suggestAlternativePlayer(t('player.jessibuca.speedNoFrameCompat')) // FIXED: 国际化
            if (suggested) return
          }
          const switchedCompat = switchToCompatibilityMode(t('player.jessibuca.waitFrameTimeout')) // FIXED: 国际化
          if (switchedCompat) return
          const switched = switchToNextCandidate(t('player.jessibuca.longNoFrameSwitch')) // FIXED: 国际化
          if (!switched) {
            uiStatus.value = 'error'
            errorHint.value = t('player.jessibuca.longTimeNoFrame') // FIXED: 国际化
            emit('status', { status: 'error', hint: errorHint.value })
            emit('error', { hint: errorHint.value })
          }
        }, 0)
      })

      // FIX: [2026-07-16 P1] 注册 close 事件监听器，确保流被服务端关闭时 onPlayerClose 正常触发。
      // 违反项目硬约束："Jessibuca 播放必须注册 close 事件监听以确保 onPlayerClose 正常触发"
      jessibuca.on('close', () => {
        emit('status', { status: 'closed' })
        emit('close')
        uiStatus.value = 'error'
        errorHint.value = t('player.streamClosed') // FIXED: 国际化
      })
    }
  } catch { /* ignore */ }

  scheduleWatchdog()
}

const initH265Player = async () => {
  if (!container.value) return false
  const targetUrl = props.hlsUrl || props.videoUrl
  if (!targetUrl) return false
  const seq = (h265webInitSeq.value += 1)
  uiStatus.value = 'loading'
  errorHint.value = t('player.jessibuca.loadingH265Decoder') // FIXED: 国际化
  emit('status', { status: 'loading' })
  let h265ScriptSrc = ''
  try {
    await loadFirstOk([
      '/static/h265web/missile.js',
      '/static/js/h265web/missile.js'
    ])
  } catch { /* cleanup: ignore */ }
  try {
    h265ScriptSrc = await loadFirstOk([
      '/static/h265web/h265webjs.js',
      '/static/js/h265web/h265webjs.js',
      '/static/h265web/h265web.js',
      '/static/js/h265web/h265web.js',
      '/static/h265web/h265webjs-v20221106.js',
      '/static/js/h265web/h265webjs-v20221106.js',
      '/static/h265web.js-master/static/h265web.js',
      '/static/js/h265web.js-master/static/h265web.js',
      '/static/h265web.js-master/static/h265web_wasm.js',
      '/static/js/h265web.js-master/static/h265web_wasm.js'
    ])
  } catch { /* ignore */ }
  if (seq !== h265webInitSeq.value) return false

  const { width, height } = container.value.getBoundingClientRect()
  const conf: Record<string, unknown> = {
    player: 'glplayer',
    width: Math.max(2, Math.floor(width || 960)),
    height: Math.max(2, Math.floor(height || 540)),
    token: (import.meta as Record<string, unknown>)?.env?.VITE_H265WEB_TOKEN || H265WEB_PUBLIC_TOKEN,
    extInfo: {
      autoPlay: true,
      ignoreAudio: 0
    }
  }
  conf.onReadyShowDone = () => {
    uiStatus.value = 'ready'
    errorHint.value = ''
    emit('status', { status: 'ready' })
  }

  try {
    const createFn = (window as Record<string, unknown>).new265webjs
    const module = (window as Record<string, unknown>).H265webjsModule
    if (typeof createFn === 'function') {
      h265Player = createFn(targetUrl, conf)
    } else if (module && typeof module.createPlayer === 'function') {
      h265Player = module.createPlayer(targetUrl, conf)
    } else {
      h265Player = null
    }
  } catch {
    h265Player = null
  }

  if (!h265Player) {
    try {
      const factory = (window as Record<string, unknown>).H265webjsPlayer
      if (typeof factory === 'function') {
        const playerId = `h265web_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
        container.value.id = playerId
        const runtimeBases: string[] = []
        const pushBase = (v: unknown) => {
          const text = String(v || '').trim()
          if (!text) return
          const normalized = text.endsWith('/') ? text : `${text}/`
          if (!runtimeBases.includes(normalized)) runtimeBases.push(normalized)
        }
        if (h265ScriptSrc.includes('/')) {
          pushBase(h265ScriptSrc.slice(0, h265ScriptSrc.lastIndexOf('/') + 1))
        }
        pushBase('/static/h265web.js-master/static/')
        pushBase('/static/js/h265web.js-master/static/')
        pushBase('/static/h265web/')
        pushBase('/static/js/h265web/')
        const instance = factory()
        instance.on_ready_show_done_callback = () => {
          uiStatus.value = 'ready'
          errorHint.value = ''
          emit('status', { status: 'ready' })
        }
        let built = false
        for (const base of runtimeBases) {
          try {
            instance.build({
              player_id: playerId,
              base_url: base,
              wasm_js_uri: 'h265web_wasm.js',
              wasm_wasm_uri: 'h265web_wasm.wasm',
              ext_src_js_uri: 'extjs.js',
              ext_wasm_js_uri: 'extwasm.js',
              width: '100%',
              height: Math.max(2, Math.floor(height || 540)),
              auto_play: true,
              ignore_audio: false
            })
            built = true
            break
          } catch { /* cleanup: ignore */ }
        }
        if (built) {
          if (typeof instance.load_media === 'function') {
            instance.load_media(targetUrl)
          } else if (typeof instance.change_media === 'function') {
            instance.change_media(targetUrl)
          }
          if (typeof instance.play === 'function') {
            instance.play()
          }
          h265Player = instance
        }
      }
    } catch {
      h265Player = null
    }
  }

  if (h265Player) {
    try {
      if (typeof h265Player.play === 'function') h265Player.play()
    } catch { /* ignore */ }
    uiStatus.value = 'ready'
    emit('status', { status: 'ready' })
    return true
  }
  h265VideoEl = document.createElement('video')
  h265VideoEl.src = targetUrl
  h265VideoEl.autoplay = true
  h265VideoEl.controls = false
  h265VideoEl.muted = true
  h265VideoEl.style.width = '100%'
  h265VideoEl.style.height = '100%'
  h265VideoEl.style.objectFit = 'contain'
  h265VideoEl.addEventListener('error', () => {
    uiStatus.value = 'error'
    errorHint.value = t('player.jessibuca.h265PlayFailed') // FIXED: 国际化
    emit('status', { status: 'error', hint: errorHint.value })
    emit('error', { hint: errorHint.value })
  })
  h265VideoEl.addEventListener('playing', () => {
    uiStatus.value = 'ready'
    errorHint.value = ''
    emit('status', { status: 'ready' })
  })
  container.value.appendChild(h265VideoEl)
  h265VideoEl.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
  return true
}

const initByCodec = async () => {
  if (!container.value) return
  const seq = (initSeq.value += 1)
  await destroyPlayers()
  if (candidateIndex.value >= candidates.value.length) {
    candidateIndex.value = 0
  }
  if (!props.videoUrl && !props.hlsUrl) {
    uiStatus.value = 'loading'
    errorHint.value = t('player.jessibuca.signalingInteract') // FIXED: 国际化
    emit('status', { status: 'loading', hint: errorHint.value })
    return
  }
  uiStatus.value = 'loading'
  errorHint.value = decoderMode.value === 'compatibility' ? t('player.jessibuca.switchingCompatMode') : t('player.jessibuca.streamAllocated') // FIXED: 国际化
  const JessibucaCtor = await resolveJessibucaCtor()
  if (!JessibucaCtor) {
    uiStatus.value = 'error'
    errorHint.value = t('player.jessibuca.jessibucaNotFound') // FIXED: 国际化
    emit('status', { status: 'error', hint: errorHint.value })
    emit('error', { hint: errorHint.value })
    return
  }
  if (seq !== initSeq.value) return
  await nextTick()
  if (seq !== initSeq.value) return
  initPlayer(JessibucaCtor)
  
  if (jessibuca) {
    if (props.hasAudio === false) {
      try { jessibuca.mute() } catch { /* cleanup: ignore */ }
    }
  }
}

const retry = () => {
  showStatusDetails.value = false
  candidateIndex.value = 0
  decoderMode.value = 'compatibility'
  initByCodec()
  emit('refreshRequest')
}

const copyDiagnostics = async () => {
  if (!requestDiagnosticsText.value) return
  try {
    await navigator.clipboard.writeText(requestDiagnosticsText.value)
    ElMessage.success(t('player.jessibuca.copiedDiagnostics')) // FIXED: 国际化
  } catch {
    ElMessage.error(t('player.jessibuca.copyFailed')) // FIXED: 国际化
  }
}

const copyUrl = async () => {
  const url = props.videoUrl || props.hlsUrl || ''
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success(t('player.jessibuca.copiedPlayAddress')) // FIXED: 国际化
  } catch {
    ElMessage.error(t('player.jessibuca.copyFailed')) // FIXED: 国际化
  }
}

const openInNewTab = () => {
  const url = props.videoUrl || props.hlsUrl || ''
  if (!url) return
  window.open(url, '_blank')
}

watch(
  () => [props.videoUrl, props.hlsUrl, props.codec],
  () => {
    showStatusDetails.value = false
    candidateIndex.value = 0
    initByCodec()
  }
)

onMounted(() => {
  initByCodec()
})

onBeforeUnmount(() => {
  void destroyPlayers()
})

const performScreenshot = () => {
  if (jessibuca && typeof jessibuca.screenshot === 'function') {
    try {
      jessibuca.screenshot('screenshot_' + Date.now(), 'png', 1)
      ElMessage.success(t('player.screenshotSaved')) // FIXED: 国际化
    } catch {
      ElMessage.error(t('player.jessibuca.copyFailed')) // FIXED: 国际化
    }
  }
}

defineExpose({
  performScreenshot
})
</script>

<style scoped>
.player-with-zoom {
  overflow: hidden;
}
.jessibuca-container {
  width: 100%;
  height: 100%;
  background-color: #000;
}
.player-status-panel {
  width: min(560px, calc(100% - 32px));
  padding: 20px 18px;
  border-radius: 16px;
  background: rgba(2, 6, 23, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.26);
  color: #fff;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.3);
  backdrop-filter: blur(12px);
}
.player-status-panel__title {
  display: flex;
  align-items: center;
  font-size: 16px;
  font-weight: 600;
}
.player-status-panel__desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.92);
}
.player-status-panel__sub {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(226, 232, 240, 0.88);
}
.player-status-panel__progress {
  margin-top: 14px;
}
.player-status-panel__steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}
.player-status-step {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.34);
  border: 1px solid rgba(148, 163, 184, 0.18);
  font-size: 12px;
}
.player-status-step strong {
  font-weight: 600;
}
.player-status-step.is-done strong {
  color: #4ade80;
}
.player-status-step.is-error strong {
  color: #fca5a5;
}
.player-status-step.is-loading strong {
  color: #fcd34d;
}
.player-status-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
.player-status-panel__btn {
  border: none;
  border-radius: 10px;
  padding: 9px 14px;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.2s ease, transform 0.2s ease;
}
.player-status-panel__btn:hover {
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(-1px);
}
.player-status-panel__btn--primary {
  background: linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%);
}
.player-status-panel__btn--primary:hover {
  background: linear-gradient(135deg, #1d4ed8 0%, #0284c7 100%);
}
</style>
