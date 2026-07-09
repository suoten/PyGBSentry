<template>
  <!-- FIX: [2026-07-04] JessibucaPlayer 原为 stub 空壳，导致实时预览/录像回放完全不能播放。
       根因：开源版发布时播放器组件未实现，仅保留 11 行 stub。
       修复：基于本地 public/static/jessibuca/ 资源实现完整的 jessibuca 播放器组件 [全栈工程师] -->
  <div ref="containerRef" class="jessibuca-container"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { logger } from '@/utils/logger'

// FIX: [2026-07-04] 通过全局 window.Jessibuca 访问动态加载的 jessibuca.js [全栈工程师]
declare global {
  interface Window {
    Jessibuca?: JessibucaConstructor
  }
}

// FIX: [2026-07-04] jessibuca 构造函数与实例类型（基于 public/static/jessibuca/jessibuca.d.ts） [全栈工程师]
interface JessibucaConfig {
  container: HTMLElement | string
  decoder?: string
  videoBuffer?: number
  isResize?: boolean
  isFullResize?: boolean
  isFlv?: boolean
  hasAudio?: boolean
  debug?: boolean
  timeout?: number
  heartTimeout?: number
  loadingTimeout?: number
  loadingTimeoutReplay?: boolean
  loadingTimeoutReplayTimes?: number
  heartTimeoutReplay?: boolean
  heartTimeoutReplayTimes?: number
  operateBtns?: {
    fullscreen?: boolean
    screenshot?: boolean
    play?: boolean
    audio?: boolean
    record?: boolean
  }
  forceNoOffscreen?: boolean
  keepScreenOn?: boolean
  isNotMute?: boolean
  showBandwidth?: boolean
  supportDblclickFullscreen?: boolean
  autoWasm?: boolean
  useMSE?: boolean
  useWCS?: boolean
}

interface JessibucaInstance {
  play(url?: string, options?: { headers: object }): Promise<void>
  pause(): Promise<void>
  close(): void
  destroy(): void
  on(event: string, callback: (...args: unknown[]) => void): void
  screenshot(filename?: string, format?: string, quality?: number, type?: string): unknown
  setScaleMode(mode: number): void
  isPlaying(): boolean
  mute(): void
  cancelMute(): void
  setVolume(volume: number): void
  setFullscreen(flag: boolean): void
  resize(): void
}

type JessibucaConstructor = new (config?: JessibucaConfig) => JessibucaInstance

type PlayRequestUi = {
  status?: 'idle' | 'requesting' | 'waiting' | 'ready' | 'error'
  stage?: string
  progress?: number
  message?: string
  suggestion?: string
  retryable?: boolean
  diagnostics?: Record<string, unknown>
  urlAvailability?: Record<string, boolean | null>
  hlsProbeDetail?: Record<string, unknown>
}

const props = withDefaults(defineProps<{
  videoUrl: string
  hlsUrl?: string
  codec?: string
  candidates?: string[]
  request?: PlayRequestUi
  suggestedPlayer?: 'h265' | 'webrtc' | ''
  hasAudio?: boolean
  autoPlay?: boolean
}>(), {
  hlsUrl: '',
  codec: '',
  candidates: () => [],
  suggestedPlayer: '',
  hasAudio: true,
  autoPlay: true,
})

const emit = defineEmits<{
  (e: 'refresh-request'): void
  (e: 'suggest-switch', player: 'h265' | 'webrtc'): void
  (e: 'error'): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let jessibuca: JessibucaInstance | null = null
let errored = false
let destroyed = false

// FIX: [2026-07-04] 动态加载 jessibuca.js 脚本，保证只加载一次 [全栈工程师]
const JESSIBUCA_SCRIPT_URL = '/static/jessibuca/jessibuca.js'
const JESSIBUCA_DECODER_URL = '/static/jessibuca/decoder.js'
const SCRIPT_LOAD_PROMISE_KEY = '__jessibuca_script_loading__'

function loadJessibucaScript(): Promise<void> {
  if (window.Jessibuca) return Promise.resolve()
  // FIX: [2026-07-04] window 需先转 unknown 再转 Record，避免 TS2352 类型不兼容 [全栈工程师]
  const winStore = window as unknown as Record<string, unknown>
  const existing = winStore[SCRIPT_LOAD_PROMISE_KEY] as Promise<void> | undefined
  if (existing) return existing
  const promise = new Promise<void>((resolve, reject) => {
    const existingScript = document.querySelector(`script[src="${JESSIBUCA_SCRIPT_URL}"]`)
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve())
      existingScript.addEventListener('error', () => reject(new Error('jessibuca.js load failed')))
      return
    }
    const script = document.createElement('script')
    script.src = JESSIBUCA_SCRIPT_URL
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('jessibuca.js load failed'))
    document.head.appendChild(script)
  })
  winStore[SCRIPT_LOAD_PROMISE_KEY] = promise
  promise.catch(() => {
    // 加载失败时清除标记，允许后续重试
    delete winStore[SCRIPT_LOAD_PROMISE_KEY]
  })
  return promise
}

function isHevc(): boolean {
  const c = String(props.codec || '').toLowerCase()
  return c === 'h265' || c === 'hevc'
}

function createInstance(): JessibucaInstance | null {
  if (!window.Jessibuca || !containerRef.value) return null
  const config: JessibucaConfig = {
    container: containerRef.value,
    decoder: JESSIBUCA_DECODER_URL,
    videoBuffer: 0.2,
    isResize: true,
    isFlv: true,
    hasAudio: props.hasAudio,
    debug: false,
    timeout: 30,
    heartTimeout: 30,
    loadingTimeout: 20,
    loadingTimeoutReplay: true,
    loadingTimeoutReplayTimes: 3,
    heartTimeoutReplay: true,
    heartTimeoutReplayTimes: 3,
    autoWasm: true,
    operateBtns: {
      fullscreen: true,
      screenshot: true,
      play: true,
      audio: true,
      record: false,
    },
    forceNoOffscreen: false,
    keepScreenOn: true,
    isNotMute: props.hasAudio,
    showBandwidth: false,
    supportDblclickFullscreen: true,
  }
  return new window.Jessibuca(config)
}

function bindEvents(instance: JessibucaInstance) {
  instance.on('error', (err: unknown) => {
    const errStr = String(err)
    logger.warn('Jessibuca error:', err)
    // FIX: [2026-07-04] H265 不支持时建议切换到 h265 播放器（wasm 解码） [全栈工程师]
    if (errStr === 'webcodecsH265NotSupport' || errStr === 'mediaSourceH265NotSupport' || errStr === 'wasmDecodeError') {
      if (props.suggestedPlayer === 'h265' || isHevc()) {
        emit('suggest-switch', 'h265')
      }
    }
    if (!errored) {
      errored = true
      emit('error')
    }
  })
  instance.on('timeout', (err: unknown) => {
    logger.warn('Jessibuca timeout:', err)
    if (!errored) {
      errored = true
      emit('error')
    }
  })
  instance.on('load', () => {
    logger.debug('Jessibuca loaded')
  })
}

async function startPlayback() {
  if (!containerRef.value) return
  const url = String(props.videoUrl || '').trim()
  if (!url) return
  try {
    await loadJessibucaScript()
  } catch (e) {
    logger.error('Failed to load jessibuca.js:', e)
    if (!errored) {
      errored = true
      emit('error')
    }
    return
  }
  if (destroyed) return
  if (!jessibuca) {
    jessibuca = createInstance()
    if (!jessibuca) {
      logger.error('Jessibuca constructor unavailable')
      if (!errored) {
        errored = true
        emit('error')
      }
      return
    }
    bindEvents(jessibuca)
  }
  try {
    await jessibuca.play(url)
  } catch (e) {
    logger.error('Jessibuca play failed:', e)
    if (!errored) {
      errored = true
      emit('error')
    }
  }
}

function destroyInstance() {
  if (jessibuca) {
    try {
      jessibuca.destroy()
    } catch (e) {
      logger.warn('Jessibuca destroy error:', e)
    }
    jessibuca = null
  }
}

// FIX: [2026-07-04] 暴露截图方法供父组件调用 [全栈工程师]
const performScreenshot = () => {
  if (!jessibuca) {
    logger.warn('Jessibuca not ready for screenshot')
    return
  }
  try {
    const ts = new Date().getTime()
    jessibuca.screenshot(`screenshot_${ts}`, 'png', 0.92, 'download')
  } catch (e) {
    logger.error('Jessibuca screenshot failed:', e)
  }
}

defineExpose({ performScreenshot })

onMounted(() => {
  if (props.autoPlay) {
    startPlayback()
  }
})

onBeforeUnmount(() => {
  destroyed = true
  destroyInstance()
})

// FIX: [2026-07-04] 监听 URL 变化，自动重建播放 [全栈工程师]
watch(
  () => props.videoUrl,
  (newUrl, oldUrl) => {
    if (newUrl === oldUrl) return
    errored = false
    if (jessibuca && newUrl) {
      try {
        jessibuca.close()
      } catch { /* ignore */ }
      startPlayback()
    } else if (newUrl) {
      startPlayback()
    } else {
      destroyInstance()
    }
  }
)
</script>

<style scoped>
.jessibuca-container {
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: #000;
  display: block;
}
</style>
