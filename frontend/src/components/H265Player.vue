<template>
  <!-- FIX: [2026-07-04] H265Player 原为 stub 空壳，导致 H.265 流播放完全不能用。
       根因：开源版发布时组件未实现，仅保留 9 行 stub。
       修复：使用原生 HTML5 video 元素播放 HLS 流。Safari/iOS 原生支持 H.265 via HLS；
       其他浏览器无法解码 H.265 时触发 error 事件，由上层 fallback 到 jessibuca（wasm 解码 H.265） [全栈工程师] -->
  <div class="h265-player-wrap">
    <video
      ref="videoRef"
      class="h265-video"
      autoplay
      muted
      playsinline
      controls
      @error="handleVideoError"
    />
    <div v-if="errorMsg" class="h265-error-overlay">{{ errorMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { logger } from '@/utils/logger'

const props = defineProps<{
  h265Url: string
}>()

const emit = defineEmits<{
  (e: 'error'): void
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const errorMsg = ref('')
let errored = false
let destroyed = false

// FIX: [2026-07-04] 检测浏览器是否原生支持 H.265/HEVC 播放 [全栈工程师]
function canPlayHevcNatively(): boolean {
  const v = document.createElement('video')
  // Safari/iOS 通过 HLS 或 MP4 容器支持 HEVC
  // HEVC codec strings: hvc1, hev1
  return (
    v.canPlayType('video/mp4; codecs="hvc1.1.6.L93.B0"') !== '' ||
    v.canPlayType('video/mp4; codecs="hev1.1.6.L93.B0"') !== '' ||
    v.canPlayType('application/vnd.apple.mpegurl') !== ''
  )
}

function startPlayback(url: string) {
  if (!videoRef.value) return
  errorMsg.value = ''
  if (!canPlayHevcNatively()) {
    logger.warn('H265Player: browser does not support native HEVC, emit error for fallback')
    emitError('HEVC not supported natively')
    return
  }
  videoRef.value.src = url
  videoRef.value.load()
  videoRef.value.play().catch((e) => {
    logger.warn('H265Player autoplay blocked:', e)
  })
}

function handleVideoError() {
  if (errored || destroyed) return
  const v = videoRef.value
  if (!v) return
  const code = v.error?.code
  logger.warn('H265Player video error, code:', code)
  emitError('H.265 playback error')
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
  const url = String(props.h265Url || '').trim()
  if (!url) {
    emitError('No H.265 URL')
    return
  }
  startPlayback(url)
})

onBeforeUnmount(() => {
  destroyed = true
  cleanup()
})

watch(
  () => props.h265Url,
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
.h265-player-wrap {
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: #000;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.h265-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.h265-error-overlay {
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
