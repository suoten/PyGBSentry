<template>
  <div class="relative w-full h-full bg-black overflow-hidden">
    <video
      ref="videoRef"
      class="w-full h-full"
      autoplay
      muted
      playsinline
      controls
      style="object-fit: contain; background: rgba(0, 0, 0, 0.85)"
    />
    <div v-if="uiStatus !== 'ready'" class="absolute inset-0 flex items-center justify-center z-20 bg-black/70">
      <div class="text-center text-white p-4">
        <div v-if="uiStatus === 'loading'" class="flex flex-col items-center">
          <el-icon class="is-loading text-3xl mb-2 text-sky-400"><Loading /></el-icon>
          <div class="text-sm">{{ loadingText }}</div>
        </div>
        <div v-else class="flex flex-col items-center">
          <el-icon class="text-3xl mb-2 text-red-500"><Warning /></el-icon>
          <div class="text-sm">{{ errorHint }}</div>
          <div class="mt-3 flex gap-2">
            <button class="px-3 py-1 rounded bg-sky-500 hover:bg-sky-600 text-xs text-white transition-colors" @click="retry">
              重试
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElIcon } from 'element-plus'
import { Loading, Warning } from '@element-plus/icons-vue'

const props = defineProps<{
  hlsUrl: string
  title?: string
}>()

const emit = defineEmits<{
  (e: 'error', hint: string): void
  (e: 'status', status: 'loading' | 'ready' | 'error'): void
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const uiStatus = ref<'loading' | 'ready' | 'error'>('loading')
const errorHint = ref('')
const loadingText = ref('正在连接视频流…')

let hls: Record<string, unknown> = null
let initSeq = 0

const loadHlsJs = () =>
  new Promise<void>((resolve, reject) => {
    const existed = document.querySelector('script[data-hls-js]') as HTMLScriptElement | null
    if (existed) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.dataset['hlsJs'] = '1'
    script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.13/dist/hls.min.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('加载 hls.js 失败'))
    document.head.appendChild(script)
  })

const destroyHls = () => {
  if (hls) {
    try {
      hls.destroy()
    } catch { /* ignore */ }
    hls = null
  }
  if (videoRef.value) {
    try {
      videoRef.value.pause()
      videoRef.value.src = ''
      videoRef.value.load()
    } catch { /* cleanup: ignore */ }
  }
}

const initPlayer = async () => {
  destroyHls()
  const seq = ++initSeq

  const url = String(props.hlsUrl || '').trim()
  if (!url) {
    errorHint.value = '播放地址为空'
    uiStatus.value = 'error'
    emit('error', errorHint.value)
    emit('status', 'error')
    return
  }

  uiStatus.value = 'loading'
  loadingText.value = '正在加载视频流…'
  errorHint.value = ''
  emit('status', 'loading')

  try {
    await nextTick()
    if (!videoRef.value) {
      errorHint.value = '播放器容器未就绪'
      uiStatus.value = 'error'
      emit('error', errorHint.value)
      emit('status', 'error')
      return
    }

    const videoEl = videoRef.value

    // Safari/iOS 原生支持 HLS
    if (videoEl.canPlayType('application/vnd.apple.mpegurl') || videoEl.canPlayType('application/x-mpegURL')) {
      if (seq !== initSeq) return
      videoEl.src = url
      videoEl.addEventListener('playing', onPlaying, { once: true })
      videoEl.addEventListener('error', onError, { once: true })
      videoEl.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
    } else {
      // 尝试加载 hls.js
      try {
        await loadHlsJs()
      } catch {
        if (seq !== initSeq) return
        errorHint.value = '浏览器不支持 HLS'
        uiStatus.value = 'error'
        emit('error', errorHint.value)
        emit('status', 'error')
        return
      }

      if (seq !== initSeq) return
      const Hls = (window as Record<string, unknown>).Hls
      if (Hls && typeof Hls.isSupported === 'function' && Hls.isSupported()) {
        hls = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
          backBufferLength: 10,
          maxBufferLength: 10,
          maxMaxBufferLength: 30,
          liveSyncDurationCount: 2,
          liveMaxLatencyDurationCount: 5,
          liveDurationInfinity: true,
          highBufferWatchdogPeriod: 1,
        })
        hls.loadSource(url)
        hls.attachMedia(videoEl)
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (seq !== initSeq) return
          videoEl.play().catch(() => { /* play() rejected: common on pause/destroy, safe to ignore */ })
        })
        hls.on(Hls.Events.ERROR, (event: Record<string, unknown>, data: Record<string, unknown>) => {
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                hls?.startLoad()
                break
              case Hls.ErrorTypes.MEDIA_ERROR:
                hls?.recoverMediaError()
                break
              default:
                if (seq !== initSeq) return
                errorHint.value = `HLS 播放错误: ${data.details}`
                uiStatus.value = 'error'
                emit('error', errorHint.value)
                emit('status', 'error')
                destroyHls()
                break
            }
          }
        })
        videoEl.addEventListener('playing', onPlaying, { once: true })
        videoEl.addEventListener('error', onError, { once: true })
      } else {
        if (seq !== initSeq) return
        errorHint.value = '当前浏览器不支持 HLS 播放'
        uiStatus.value = 'error'
        emit('error', errorHint.value)
        emit('status', 'error')
      }
    }
  } catch (err: unknown) {
    if (seq !== initSeq) return
    const msg = err instanceof Error ? err.message : String(err || '')
    errorHint.value = `播放失败: ${msg}`
    uiStatus.value = 'error'
    emit('error', errorHint.value)
    emit('status', 'error')
  }
}

const onPlaying = () => {
  uiStatus.value = 'ready'
  errorHint.value = ''
  emit('status', 'ready')
}

const onError = () => {
  const video = videoRef.value
  let msg = '视频播放失败'
  if (video?.error) {
    const code = video.error.code
    switch (code) {
      case 1: msg = '播放被中止'; break
      case 2: msg = '网络错误，请检查网络连接'; break
      case 3: msg = '视频解码错误'; break
      case 4: msg = '播放地址无效或不可用'; break
    }
  }
  errorHint.value = msg
  uiStatus.value = 'error'
  emit('error', msg)
  emit('status', 'error')
}

const retry = () => {
  initPlayer()
}

watch(
  () => props.hlsUrl,
  () => {
    initPlayer()
  }
)

onMounted(() => {
  initPlayer()
})

onBeforeUnmount(() => {
  destroyHls()
})
</script>
