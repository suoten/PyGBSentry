<template>
  <div class="relative w-full h-full bg-black overflow-hidden">
    <div ref="containerRef" class="w-full h-full"></div>
    <video v-show="videoFallbackVisible" ref="videoRef" class="w-full h-full" autoplay muted playsinline controls style="object-fit: contain" />
    <div v-if="uiStatus !== 'ready'" class="absolute inset-0 flex items-center justify-center z-20">
      <div class="max-w-[520px] px-4 py-3 rounded-lg bg-black/65 text-white">
        <div class="text-sm font-medium">{{ uiStatus === 'loading' ? t('h265Player.connecting') : t('h265Player.playFailed') }}</div>
        <div class="text-xs mt-1 text-white/80">{{ errorHint || t('h265Player.retryHint') }}</div>
        <div class="flex flex-wrap gap-2 mt-3">
          <button class="px-3 py-1.5 rounded bg-white/15 hover:bg-white/25 text-xs transition-colors" @click="retry">{{ t('h265Player.retryConnect') }}</button>
        </div>
      </div>
    </div>
    <button class="absolute right-3 bottom-3 z-30 px-2 py-1 rounded bg-black/55 text-white text-xs hover:bg-black/75 transition-colors" @click="showDiagnostics = !showDiagnostics">
      {{ showDiagnostics ? t('h265Player.hideDiagnostics') : t('h265Player.showDiagnostics') }}
    </button>
    <div v-if="showDiagnostics" class="absolute left-3 right-3 bottom-12 z-30 rounded bg-black/70 text-white text-xs p-3 space-y-1">
      <div>{{ t('h265Player.diagStatus') }}: {{ uiStatus }}</div>
      <div>{{ t('h265Player.diagEngine') }}: {{ diagnostics.engine }}</div>
      <div>{{ t('h265Player.diagPhase') }}: {{ diagnostics.phase }}</div>
      <div>{{ t('h265Player.diagCurrentUrl') }}: {{ diagnostics.currentUrl || '-' }}</div>
      <div>{{ t('h265Player.diagScriptSrc') }}: {{ diagnostics.scriptSrc || '-' }}</div>
      <div>{{ t('h265Player.diagBasePaths') }}: {{ diagnostics.basePaths.length ? diagnostics.basePaths.join(' | ') : '-' }}</div>
      <div>{{ t('h265Player.diagLastError') }}: {{ diagnostics.lastError || '-' }}</div>
      <div>{{ t('h265Player.diagLastSuccess') }}: {{ diagnostics.lastSuccessAt || '-' }}</div>
      <div>{{ t('h265Player.diagAttempts') }}: {{ diagnostics.attempts.length ? diagnostics.attempts.join(' -> ') : '-' }}</div>
      <div class="max-h-24 overflow-auto leading-5">
        <div v-for="(item, idx) in diagnostics.events" :key="`${idx}-${item}`">{{ item }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// window 上挂载的 h265web 播放器相关全局对象的最小类型声明（按本组件实际用到的 API）
type H265WebJsPlayerInstance = {
  on_ready_show_done_callback?: () => void
  on_error_callback?: (e: unknown) => void
  build(config: Record<string, unknown>): boolean
  load_media?(url: string): void
  change_media?(url: string): void
  play?(): void
}
type H265LegacyPlayerFactory = (url: string, conf: Record<string, unknown>) => Record<string, unknown>

const props = defineProps<{
  h265Url: string
}>()

const emit = defineEmits<{
  (e: 'error', hint: string): void
  (e: 'status', status: 'loading' | 'ready' | 'error'): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const videoRef = ref<HTMLVideoElement | null>(null)
const videoFallbackVisible = ref(false)
const uiStatus = ref<'loading' | 'ready' | 'error'>('loading')
const errorHint = ref('')
const showDiagnostics = ref(false)
const diagnostics = ref({
  engine: '',
  phase: '',
  currentUrl: '',
  scriptSrc: '',
  basePaths: [] as string[],
  attempts: [] as string[],
  lastError: '',
  lastSuccessAt: '',
  events: [] as string[]
})

let h265Player: Record<string, unknown> | null = null
let scriptSrcUsed = ''
let previousEmscriptenModule: Record<string, unknown> | null = null
let hasPatchedEmscriptenModule = false
let initSeq = 0

const nowLabel = () => new Date().toLocaleTimeString()

const pushDiagEvent = (text: string) => {
  const row = `[${nowLabel()}] ${text}`
  const arr = diagnostics.value.events
  arr.push(row)
  if (arr.length > 30) arr.shift()
}

const setDiagEngine = (engine: string) => {
  diagnostics.value.engine = engine
}

const setDiagPhase = (phase: string) => {
  diagnostics.value.phase = phase
}

const markReady = () => {
  uiStatus.value = 'ready'
  errorHint.value = ''
  diagnostics.value.lastSuccessAt = nowLabel()
  setDiagPhase('ready')
  emit('status', 'ready')
}

const markError = (hint: string) => {
  uiStatus.value = 'error'
  errorHint.value = hint
  diagnostics.value.lastError = hint
  setDiagPhase('error')
  emit('status', 'error')
  emit('error', hint)
}

const resetDiagnostics = (inputUrl: string) => {
  diagnostics.value.engine = ''
  diagnostics.value.phase = 'init'
  diagnostics.value.currentUrl = inputUrl
  diagnostics.value.scriptSrc = ''
  diagnostics.value.basePaths = []
  diagnostics.value.attempts = []
  diagnostics.value.lastError = ''
  diagnostics.value.lastSuccessAt = ''
  diagnostics.value.events = []
  pushDiagEvent(t('h265Player.diagEventStartInit', { url: inputUrl }))
}

const addDiagAttempt = (engine: string, url: string) => {
  diagnostics.value.attempts.push(`${engine}@${url}`)
  if (diagnostics.value.attempts.length > 12) diagnostics.value.attempts.shift()
}

const loadScript = (src: string) =>
  new Promise<void>((resolve, reject) => {
    const existed = document.querySelector(`script[src="${src}"]`) as HTMLScriptElement | null
    if (existed) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error(`load script failed: ${src}`))
    document.head.appendChild(script)
  })

const loadFirstOk = async (srcList: string[]) => {
  let lastErr: Record<string, unknown> | null = null
  for (const src of srcList) {
    try {
      await loadScript(src)
      scriptSrcUsed = src
      diagnostics.value.scriptSrc = src
      pushDiagEvent(t('h265Player.diagEventScriptLoaded', { src }))
      return src
    } catch (e) {
      pushDiagEvent(t('h265Player.diagEventScriptLoadFailed', { src }))
      lastErr = e as Record<string, unknown>
    }
  }
  throw lastErr || new Error('load script failed')
}

const releasePlayer = async () => {
  const player = h265Player
  h265Player = null
  if (player && typeof player.destroy === 'function') {
    try {
      const ret = player.destroy()
      if (ret && typeof ret.then === 'function') await ret.catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
    } catch { /* cleanup: ignore */ }
  } else if (player && typeof player.release === 'function') {
    try {
      const ret = player.release()
      if (ret && typeof ret.then === 'function') await ret.catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
    } catch { /* cleanup: ignore */ }
  }
  if (videoRef.value) {
    try {
      videoRef.value.pause()
      videoRef.value.src = ''
    } catch { /* cleanup: ignore */ }
  }
  if (hasPatchedEmscriptenModule) {
    try {
      if (previousEmscriptenModule === null) {
        delete (window as unknown as Record<string, unknown>).Module
      } else {
        ;(window as unknown as Record<string, unknown>).Module = previousEmscriptenModule
      }
    } catch { /* ignore */ } finally {
      previousEmscriptenModule = null
      hasPatchedEmscriptenModule = false
    }
  }
}

const attachFallbackVideo = (url: string) =>
  new Promise<boolean>((resolve) => {
    if (!videoRef.value) {
      resolve(false)
      return
    }
    videoFallbackVisible.value = true
    const el = videoRef.value
    let settled = false
    const cleanup = () => {
      el.onplaying = null
      el.onerror = null
      el.oncanplay = null
    }
    const done = (ok: boolean, hint = '') => {
      if (settled) return
      settled = true
      cleanup()
      if (ok) {
        pushDiagEvent(t('h265Player.diagEventNativeFallbackOk'))
        markReady()
      } else {
        const message = hint || t('h265Player.nativeFallbackFailed')
        pushDiagEvent(t('h265Player.diagEventNativeFallbackFailed', { msg: message }))
        markError(message)
      }
      resolve(ok)
    }
    el.onplaying = () => done(true)
    el.oncanplay = () => done(true)
    el.onerror = () => done(false, t('h265Player.nativeFallbackFailed'))
    try {
      el.src = url
      el.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
      window.setTimeout(() => {
        if (!settled) done(false, t('h265Player.nativeFallbackTimeout'))
      }, 8000)
    } catch {
      done(false, t('h265Player.nativeFallbackFailed'))
    }
  })

const buildRuntimeBases = () => {
  const bases: string[] = []
  const push = (value: string) => {
    const text = String(value || '').trim()
    if (!text) return
    const normalized = text.endsWith('/') ? text : `${text}/`
    if (!bases.includes(normalized)) bases.push(normalized)
  }
  if (scriptSrcUsed.includes('/')) {
    push(scriptSrcUsed.slice(0, scriptSrcUsed.lastIndexOf('/') + 1))
  }
  push('/static/h265web/')
  return bases
}

const initByH265webjsPlayer = async (url: string) => {
  setDiagEngine('h265webjs')
  setDiagPhase('h265webjs_init')
  addDiagAttempt('h265webjs', url)
  diagnostics.value.currentUrl = url
  const factory = (window as unknown as { H265webjsPlayer?: () => H265WebJsPlayerInstance }).H265webjsPlayer
  if (typeof factory !== 'function' || !containerRef.value) {
    pushDiagEvent(t('h265Player.diagEventFactoryMissing'))
    return false
  }
  const canUseSharedArrayBuffer = (window as unknown as Record<string, unknown>).crossOriginIsolated === true && typeof SharedArrayBuffer !== 'undefined'
  const playerId = `h265_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  containerRef.value.id = playerId
  const instance = factory()
  let ready = false
  let runtimeError = ''
  const readyPromise = new Promise<boolean>((resolve) => {
    instance.on_ready_show_done_callback = () => {
      ready = true
      pushDiagEvent(t('h265Player.diagEventReadyTriggered'))
      resolve(true)
    }
    instance.on_error_callback = (e: unknown) => {
      runtimeError = t('h265Player.diagEventInternalError', {
        detail: typeof e === 'object' && e !== null ? JSON.stringify(e) : String(e)
      })
      pushDiagEvent(runtimeError)
      resolve(false)
    }
  })
  let built = false
  const basePaths = buildRuntimeBases()
  diagnostics.value.basePaths = basePaths
  pushDiagEvent(t('h265Player.diagEventTryBasePaths', { paths: basePaths.join(' | ') }))
  
  const H265WEB_PUBLIC_TOKEN = (import.meta.env as Record<string, unknown>).VITE_H265WEB_TOKEN || ''

  for (const base of basePaths) {
    try {
      const config = {
        player_id: playerId,
        base_url: base,
        wasm_js_uri: 'h265web_wasm.js',
        wasm_wasm_uri: 'h265web_wasm.wasm',
        width: 960,
        height: 540,
        color: 'black',
        auto_play: true,
        ignore_audio: false,
        token: (import.meta.env as Record<string, unknown>).VITE_H265WEB_TOKEN || H265WEB_PUBLIC_TOKEN
      }
      if (canUseSharedArrayBuffer) {
        ;(config as Record<string, unknown>).ext_src_js_uri = 'extjs.js'
        ;(config as Record<string, unknown>).ext_wasm_js_uri = 'extwasm.js'
      }
      
      const buildOk = instance.build(config)
      if (buildOk) {
        built = true
        pushDiagEvent(t('h265Player.diagEventBuildOk', { base }))
        break
      } else {
        pushDiagEvent(t('h265Player.diagEventBuildFalse', { base }))
      }
    } catch {
      pushDiagEvent(t('h265Player.diagEventBuildError', { base }))
    }
  }
  if (!built) {
    pushDiagEvent(t('h265Player.diagEventBuildAllFailed'))
    return false
  }
  if (typeof instance.load_media === 'function') {
    instance.load_media(url)
  } else if (typeof instance.change_media === 'function') {
    instance.change_media(url)
  }
  if (typeof instance.play === 'function') {
    instance.play()
  }
  const ok = await Promise.race([
    readyPromise,
    new Promise<boolean>((resolve) => window.setTimeout(() => resolve(false), 9000))
  ])
  if (!ok && runtimeError) {
    diagnostics.value.lastError = runtimeError
    return false
  }
  if (!ok && !ready) {
    pushDiagEvent(t('h265Player.diagEventReadyTimeout'))
    return false
  }
  markReady()
  h265Player = instance
  return true
}

const initByLegacyApi = async (url: string) => {
  setDiagEngine('legacy_api')
  setDiagPhase('legacy_init')
  addDiagAttempt('legacy', url)
  diagnostics.value.currentUrl = url
  const createFn = (window as unknown as { new265webjs?: H265LegacyPlayerFactory }).new265webjs
  const module = (window as unknown as { H265webjsModule?: { createPlayer?: H265LegacyPlayerFactory } }).H265webjsModule

  const H265WEB_PUBLIC_TOKEN = (import.meta.env as Record<string, unknown>).VITE_H265WEB_TOKEN || ''

  let ready = false
  const conf: Record<string, unknown> = {
    player: 'glplayer',
    width: 960,
    height: 540,
    token: (import.meta.env as Record<string, unknown>).VITE_H265WEB_TOKEN || H265WEB_PUBLIC_TOKEN,
    extInfo: {
      autoPlay: true,
      ignoreAudio: 0
    },
    onReadyShowDone: () => {
      ready = true
    }
  }
  try {
    if (typeof createFn === 'function') {
      h265Player = createFn(url, conf)
      pushDiagEvent(t('h265Player.diagEventLegacyCreated'))
    } else if (module && typeof module.createPlayer === 'function') {
      h265Player = module.createPlayer(url, conf)
      pushDiagEvent(t('h265Player.diagEventLegacyModuleCreated'))
    } else {
      pushDiagEvent(t('h265Player.diagEventLegacyMissing'))
    }
  } catch {
    pushDiagEvent(t('h265Player.diagEventLegacyInitError'))
  }
  if (!h265Player) {
    pushDiagEvent(t('h265Player.diagEventLegacyUnavailable'))
    return false
  }
  await new Promise<void>((resolve) => window.setTimeout(() => resolve(), 1200))
  if (!ready && typeof h265Player.play === 'function') {
    try {
      h265Player.play()
    } catch {
      pushDiagEvent(t('h265Player.diagEventLegacyPlayError'))
    }
  }
  if (!ready) {
    pushDiagEvent(t('h265Player.diagEventLegacyNoReady'))
  }
  markReady()
  return true
}

const patchEmscriptenModuleForH265web = () => {
  if (hasPatchedEmscriptenModule) return
  const w = window as unknown as Record<string, unknown>
  previousEmscriptenModule = Object.prototype.hasOwnProperty.call(w, 'Module') ? (w.Module as Record<string, unknown> | null) : null
  const base = w.Module && typeof w.Module === 'object' ? w.Module : {}
  w.Module = {
    ...base,
    print: () => {},
    printErr: () => {}
  }
  hasPatchedEmscriptenModule = true
}

const initPlayer = async () => {
  const seq = ++initSeq
  const url = String(props.h265Url || '').trim()
  resetDiagnostics(url)
  if (!url) {
    markError(t('h265Player.urlEmpty'))
    return
  }
  await releasePlayer()
  videoFallbackVisible.value = false
  uiStatus.value = 'loading'
  errorHint.value = ''
  setDiagPhase('loading')
  emit('status', 'loading')
  patchEmscriptenModuleForH265web()
  
  // 增加缺失的 js 文件加载 fallback
  try {
    await loadFirstOk([
      '/static/h265web/h265web.js',
      '/static/js/h265web/h265web.js',
      '/static/h265web.js-master/static/h265web.js',
      '/static/js/h265web.js-master/static/h265web.js'
    ])
  } catch {
    pushDiagEvent(t('h265Player.diagEventCoreScriptPreloadFailed'))
  }
  if (seq !== initSeq) return
  const urlCandidates = [url]
  if (url.startsWith('wss://')) {
    urlCandidates.push(`https://${url.slice(6)}`)
  } else if (url.startsWith('ws://')) {
    urlCandidates.push(`http://${url.slice(5)}`)
    urlCandidates.push(`https://${url.slice(5)}`)
  } else if (url.startsWith('http://')) {
    urlCandidates.push(`https://${url.slice(7)}`)
  }
  const uniqueCandidates = [...new Set(urlCandidates.filter(Boolean))]
  for (const candidate of uniqueCandidates) {
    if (seq !== initSeq) return
    pushDiagEvent(t('h265Player.diagEventTryUrl', { url: candidate }))
    if (await initByH265webjsPlayer(candidate)) return
    if (seq !== initSeq) return
    if (await initByLegacyApi(candidate)) return
    if (seq !== initSeq) return
  }
  if (seq !== initSeq) return
  setDiagEngine('native_video')
  setDiagPhase('native_fallback')
  addDiagAttempt('native', uniqueCandidates[0] || url)
  diagnostics.value.currentUrl = uniqueCandidates[0] || url
  await attachFallbackVideo(uniqueCandidates[0] || url)
}

const retry = () => {
  initPlayer()
}

watch(
  () => props.h265Url,
  () => {
    initPlayer()
  }
)

onMounted(() => {
  initPlayer()
})

onBeforeUnmount(() => {
  releasePlayer()
})
</script>
