<template>
  <!-- FIX: [2026-07-04] NativeHlsPlayer 原为 stub 空壳，导致 HLS 播放协议完全不能用。
       根因：开源版发布时组件未实现，仅保留 9 行 stub。
       修复：使用原生 HTML5 video 元素播放 HLS 流。Safari/iOS 原生支持 HLS；
       其他浏览器无法原生播放 HLS 时触发 error 事件，由上层 fallback 到 jessibuca [全栈工程师] -->
  <div class="hls-player-wrap">
    <video
      ref="videoRef"
      class="hls-video"
      autoplay
      muted
      playsinline
      controls
      @error="handleVideoError"
    />
    <div v-if="errorMsg" class="hls-error-overlay">{{ errorMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { logger } from '@/utils/logger'

const props = defineProps<{
  hlsUrl: string
}>()

const emit = defineEmits<{
  (e: 'error'): void
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const errorMsg = ref('')
let errored = false
let destroyed = false

function canPlayHlsNatively(): boolean {
  if (!videoRef.value) return false
  // FIX: [2026-07-04] 检测浏览器是否原生支持 HLS（Safari/iOS、Edge macOS） [全栈工程师]
  const v = document.createElement('video')
  return (
    v.canPlayType('application/vnd.apple.mpegurl') !== '' ||
    v.canPlayType('application/x-mpegURL') !== ''
  )
}

function startPlayback(url: string) {
  if (!videoRef.value) return
  errorMsg.value = ''
  if (!canPlayHlsNatively()) {
    logger.warn('NativeHlsPlayer: browser does not support native HLS, emit error for fallback')
    emitError('Native HLS not supported')
    return
  }
  videoRef.value.src = url
  videoRef.value.load()
  videoRef.value.play().catch((e) => {
    logger.warn('NativeHlsPlayer autoplay blocked:', e)
  })
}

function handleVideoError() {
  if (errored || destroyed) return
  const v = videoRef.value
  if (!v) return
  const code = v.error?.code
  logger.warn('NativeHlsPlayer video error, code:', code)
  emitError('Video playback error')
}

function emitError(msg: string) {
  if (errored || destroyed) return
  errored = true
  errorMsg.value = msg
  emit('error')
}

function cleanup() {
  if (videoRef.value) {
    videoRef.value.pause()
    videoRef.value.removeAttribute('src')
    videoRef.value.load()
  }
}

onMounted(() => {
  const url = String(props.hlsUrl || '').trim()
  if (!url) {
    emitError('No HLS URL')
    return
  }
  startPlayback(url)
})

onBeforeUnmount(() => {
  destroyed = true
  cleanup()
})

watch(
  () => props.hlsUrl,
  (newUrl, oldUrl) => {
    if (newUrl === oldUrl) return
    errored = false
    errorMsg.value = ''
    if (newUrl) {
      startPlayback(newUrl)
    } else {
      cleanup()
    }
  }
)
</script>

<style scoped>
.hls-player-wrap {
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: #000;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hls-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.hls-error-overlay {
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
</style>
