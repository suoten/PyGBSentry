<template>
  <div class="relative w-full h-full bg-black overflow-hidden">
    <video ref="videoEl" class="w-full h-full" :muted="isMuted" autoplay playsinline controls style="object-fit: contain" />
    
    <div v-if="uiStatus !== 'ready'" class="absolute inset-0 flex items-center justify-center z-20">
      <div class="max-w-[520px] px-4 py-3 rounded-lg bg-black/65 text-white">
        <div class="text-sm font-medium">
          <el-icon v-if="uiStatus === 'loading'" class="is-loading mr-1"><Loading /></el-icon>
          <el-icon v-else color="#f56c6c" class="mr-1"><Warning /></el-icon>
          {{ uiStatus === 'loading' ? '正在连接 WebRTC…' : '播放失败' }}
        </div>
        <div v-if="uiStatus === 'loading'" class="text-xs mt-1 text-white/80">
          正在进行 ICE 协商与 DTLS 握手，若长时间无画面，可能是设备未推流或端口受限
        </div>
        <div v-else class="text-xs mt-1 text-white/80">
          {{ friendlyErrorHint }}
        </div>
        <div class="flex flex-wrap gap-2 mt-3">
          <button class="px-3 py-1.5 rounded bg-white/15 hover:bg-white/25 text-xs transition-colors" @click="retry">
            重试连接
          </button>
        </div>
      </div>
    </div>

    <!-- 静音播放提示 -->
    <div v-if="uiStatus === 'ready' && isMuted && showUnmuteTip" class="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/50 text-white text-xs border border-white/10 shadow-lg cursor-pointer hover:bg-black/70 transition-all" @click="unmute">
      <el-icon><Microphone /></el-icon>
      浏览器拦截了自动播放声音，点击取消静音
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import api from '@/utils/http'
import { Loading, Warning, Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { logger } from '@/utils/logger'
import { showError } from '../utils/feedback'

const props = withDefaults(
  defineProps<{
    webrtcUrl: string
    audio?: boolean
    video?: boolean
  }>(),
  {
    audio: true,
    video: true
  }
)

const emit = defineEmits<{
  (e: 'status', v: { status: 'loading' | 'ready' | 'error'; hint?: string }): void
  (e: 'error', v: { hint: string }): void
}>()

const videoEl = ref<HTMLVideoElement | null>(null)
const uiStatus = ref<'loading' | 'ready' | 'error'>('loading')
const errorHint = ref('')
const isMuted = ref(true) // 默认静音以绕过浏览器自动播放策略
const showUnmuteTip = ref(true)
const normalizePlayUrl = (value: unknown) => {
  let text = String(value || '').trim()
  while (text.length >= 2) {
    const first = text[0]
    const last = text[text.length - 1]
    if (
      (first === '`' && last === '`') ||
      (first === '"' && last === '"') ||
      (first === "'" && last === "'")
    ) {
      text = text.slice(1, -1).trim()
      continue
    }
    break
  }
  return text
}

let pc: RTCPeerConnection | null = null
let retryTimer: number | null = null
let watchdogTimer: number | null = null
let retryCount = 0
const maxRetry = 8

const friendlyErrorHint = computed(() => {
  const hint = errorHint.value || 'WebRTC 建链失败'
  if (hint.includes('ICE')) return '网络连接受限，建议检查防火墙或切换到 FLV 协议'
  if (hint.includes('流不存在')) return '设备可能已停止推送，请尝试重新发起点播'
  if (hint.includes('超时')) return '媒体服务器响应超时，请检查节点负载'
  return hint
})

const unmute = () => {
  if (videoEl.value) {
    videoEl.value.muted = false
    isMuted.value = false
    showUnmuteTip.value = false
  }
}

const clearWatchdog = () => {
  if (watchdogTimer != null) {
    window.clearInterval(watchdogTimer)
    watchdogTimer = null
  }
}

const startWatchdog = () => {
  clearWatchdog()
  let lastTime = -1
  let stuckCount = 0
  
  watchdogTimer = window.setInterval(() => {
    if (!videoEl.value || uiStatus.value !== 'ready') return
    const current = videoEl.value.currentTime
    if (current === lastTime && !videoEl.value.paused) {
      stuckCount++
      if (stuckCount >= 5) { // 画面卡住约 5 秒
        logger.warn('WebRTC 画面卡死，尝试自动重连...')
        stuckCount = 0
        retry()
      }
    } else {
      stuckCount = 0
      lastTime = current
    }
  }, 1000)
}

const clearRetry = () => {
  if (retryTimer != null) {
    window.clearTimeout(retryTimer)
    retryTimer = null
  }
}

const destroy = () => {
  clearRetry()
  clearWatchdog()
  retryCount = 0
  if (videoEl.value) {
    try {
      ;(videoEl.value as Record<string, unknown>).srcObject = null
    } catch { /* cleanup: ignore */ }
  }
  if (pc) {
    try {
      pc.onicecandidate = null
      pc.onicecandidateerror = null
      pc.ontrack = null
      pc.onconnectionstatechange = null
      pc.close()
    } catch { /* ignore */ }
    pc = null
  }
}

const setError = (hint: string) => {
  uiStatus.value = 'error'
  errorHint.value = hint
  emit('status', { status: 'error', hint })
  emit('error', { hint })
}

const play = async (url: string) => {
  destroy()
  const targetUrl = normalizePlayUrl(url)
  if (!targetUrl) {
    setError('暂无播放地址')
    return
  }
  uiStatus.value = 'loading'
  errorHint.value = ''
  emit('status', { status: 'loading' })

  if (!('RTCPeerConnection' in window)) {
    setError('当前浏览器不支持 WebRTC')
    return
  }

  pc = new RTCPeerConnection()
  pc.onicecandidateerror = () => {
    setError('ICE 协商失败')
  }
  pc.onconnectionstatechange = () => {
    const st = pc?.connectionState
    if (!st) return
    if (st === 'failed') setError('连接失败')
  }
  pc.ontrack = (event) => {
    if (!videoEl.value) return
    const stream = event.streams?.[0] || new MediaStream([event.track])
    try {
      ;(videoEl.value as Record<string, unknown>).srcObject = stream
      uiStatus.value = 'ready'
      errorHint.value = ''
      
      // 尝试自动播放
      videoEl.value.play().catch(err => {
        logger.warn('Auto-play prevented by browser:', err)
        isMuted.value = true // 被拦截后强制静音
        videoEl.value?.play() // 再次尝试静音播放
      })
      
      startWatchdog()
      emit('status', { status: 'ready' })
    } catch { /* cleanup: ignore */ }
  }

  try {
    if (typeof pc.addTransceiver === 'function') {
      if (props.video) pc.addTransceiver('video', { direction: 'recvonly' })
      if (props.audio) pc.addTransceiver('audio', { direction: 'recvonly' })
    }
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const resp = await api.post(targetUrl, offer.sdp, {
      headers: { 'Content-Type': 'text/plain;charset=utf-8' }
    })
    const ret = resp?.data || {}
    if (Number(ret?.code) !== 0) {
      const msg = String(ret?.msg || ret?.message || 'offer/answer 交换失败')
      if (Number(ret?.code) === -400 && msg === '流不存在' && retryCount < maxRetry) {
        retryCount += 1
        clearRetry()
        retryTimer = window.setTimeout(() => {
          play(url)
        }, 120)
        return
      }
      setError(msg)
      return
    }
    const answer = { type: 'answer', sdp: String(ret?.sdp || '') } as RTCSessionDescriptionInit
    await pc.setRemoteDescription(answer)
  } catch (e: unknown) {
    const hint = e instanceof Error ? e.message : String(e || 'WebRTC 建链失败')
    setError(hint)
  }
}

const retry = () => {
  retryCount = 0
  play(normalizePlayUrl(props.webrtcUrl))
}

watch(
  () => props.webrtcUrl,
  (v) => {
    retryCount = 0
    play(normalizePlayUrl(v))
  }
)

onMounted(() => {
  play(normalizePlayUrl(props.webrtcUrl))
})

onBeforeUnmount(() => {
  destroy()
})
</script>
