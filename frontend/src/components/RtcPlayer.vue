<template>
  <!-- FIX: [2026-07-04] RtcPlayer 原为 stub 空壳，导致 WebRTC 播放协议完全不能用。
       根因：开源版发布时组件未实现，仅保留 9 行 stub。
       修复：基于 WHEP 协议（RFC 草案）实现 WebRTC 拉流播放器，参考 TalkButton.vue 的 WHEP 模式 [全栈工程师] -->
  <div class="rtc-player-wrap">
    <video
      ref="videoRef"
      class="rtc-video"
      autoplay
      muted
      playsinline
    />
    <div v-if="errorMsg" class="rtc-error-overlay">{{ errorMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { logger } from '@/utils/logger'

const props = defineProps<{
  webrtcUrl: string
}>()

const emit = defineEmits<{
  (e: 'error'): void
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const errorMsg = ref('')
let pc: RTCPeerConnection | null = null
let errored = false
let destroyed = false

// FIX: [2026-07-04] WHEP 拉流：创建 RTCPeerConnection，发送 offer SDP，接收 answer SDP [全栈工程师]
async function startWhep(url: string) {
  if (!videoRef.value) return
  errorMsg.value = ''
  try {
    pc = new RTCPeerConnection()
    // 仅接收音视频（设备→前端方向）
    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })

    pc.ontrack = (event) => {
      const stream = event.streams[0]
      if (videoRef.value && stream) {
        videoRef.value.srcObject = stream
        videoRef.value.play().catch((e) => {
          logger.warn('RtcPlayer autoplay blocked:', e)
        })
      }
    }

    // FIX: [2026-07-04] ICE 连接失败时上报错误，触发上层 fallback [全栈工程师]
    pc.oniceconnectionstatechange = () => {
      if (!pc || errored) return
      const state = pc.iceConnectionState
      if (state === 'failed' || state === 'disconnected') {
        logger.warn('RtcPlayer ICE state:', state)
        emitError('WebRTC connection ' + state)
      }
    }

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    // FIX: [2026-07-04] 等待 ICE 收集完成，保证 SDP 包含完整候选 [全栈工程师]
    await waitForIceGathering(pc)

    // 发送 SDP offer 到 WHEP 端点
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription?.sdp,
    })

    if (!resp.ok) {
      logger.warn('RtcPlayer WHEP request failed:', resp.status)
      emitError(`WHEP request failed: ${resp.status}`)
      return
    }

    const answerSdp = await resp.text()
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp })
  } catch (e) {
    logger.error('RtcPlayer WHEP setup failed:', e)
    emitError('WebRTC setup failed')
  }
}

function waitForIceGathering(connection: RTCPeerConnection): Promise<void> {
  if (connection.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve) => {
    const checkState = () => {
      if (connection.iceGatheringState === 'complete') {
        connection.removeEventListener('icegatheringstatechange', checkState)
        resolve()
      }
    }
    connection.addEventListener('icegatheringstatechange', checkState)
    // FIX: [2026-07-04] 兜底超时，避免 ICE 收集卡住播放启动 [全栈工程师]
    setTimeout(() => {
      connection.removeEventListener('icegatheringstatechange', checkState)
      resolve()
    }, 2000)
  })
}

function emitError(msg: string) {
  if (errored || destroyed) return
  errored = true
  errorMsg.value = msg
  emit('error')
}

function cleanup() {
  if (pc) {
    try {
      pc.getReceivers().forEach((r) => { r.track && r.track.stop() })
      pc.close()
    } catch { /* ignore */ }
    pc = null
  }
  if (videoRef.value) {
    videoRef.value.srcObject = null
  }
}

onMounted(() => {
  const url = String(props.webrtcUrl || '').trim()
  if (!url) {
    emitError('No WebRTC URL')
    return
  }
  // FIX: [2026-07-04] 仅支持 http/https WHEP 端点；ws/wss 非标准 WHEP 信令，报错触发 fallback [全栈工程师]
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    logger.warn('RtcPlayer unsupported scheme:', url)
    emitError('Unsupported WebRTC URL scheme')
    return
  }
  startWhep(url)
})

onBeforeUnmount(() => {
  destroyed = true
  cleanup()
})

watch(
  () => props.webrtcUrl,
  (newUrl, oldUrl) => {
    if (newUrl === oldUrl) return
    errored = false
    errorMsg.value = ''
    cleanup()
    if (newUrl) {
      startWhep(newUrl)
    }
  }
)
</script>

<style scoped>
.rtc-player-wrap {
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: #000;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rtc-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.rtc-error-overlay {
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
