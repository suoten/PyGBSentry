<template>
  <el-button 
    :type="isTalking ? 'danger' : 'primary'" 
    :icon="Microphone" 
    circle 
    @mousedown="startTalk" 
    @mouseup="stopTalk" 
    @mouseleave="stopTalk"
    @touchstart.prevent="startTalk"
    @touchend="stopTalk"
    @touchcancel="stopTalk"
    class="talk-btn"
  />
  <!-- FIX: [2026-07-03] 双向对讲接收方向音频播放元素 [全栈工程师] -->
  <audio v-if="mode === 'bidirectional'" ref="audioEl" autoplay style="display:none" />
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { buildWsUrlWithTicket } from '@/utils/wsTicket'  // P0-6: ws-ticket 认证
import { logger } from '@/utils/logger'  // FIX: [2026-07-03] logger 未导入，line 204 调用抛 ReferenceError [全栈工程师]

const { t } = useI18n()  // FIXED: 国际化

const props = withDefaults(defineProps<{
  deviceId: string
  channelId?: string
  // FIX: [2026-07-03] 支持双向对讲模式，修复接收方向音频缺失 [全栈工程师]
  mode?: 'broadcast' | 'bidirectional'
}>(), {
  channelId: '',
  mode: 'broadcast',
})

const isTalking = ref(false)
const audioEl = ref<HTMLAudioElement | null>(null)
let ws: WebSocket | null = null
let audioContext: AudioContext | null = null
let processor: ScriptProcessorNode | null = null
let source: MediaStreamAudioSourceNode | null = null
let currentStream: MediaStream | null = null
let starting = false
let stopped = false
let connectTimer: ReturnType<typeof setTimeout> | null = null
const WS_CONNECT_TIMEOUT = 8000

// FIX: [2026-07-03] 双向对讲 WHEP 拉流相关变量 [全栈工程师]
let recvPc: RTCPeerConnection | null = null

const stopTalk = () => {
  if (stopped) return
  stopped = true
  isTalking.value = false
  if (connectTimer) {
    clearTimeout(connectTimer)
    connectTimer = null
  }
  if (ws) {
    try {
      ws.onclose = null
      ws.close()
    } catch { /* ignore */ }
    ws = null
  }
  if (processor) {
    processor.disconnect()
    processor = null
  }
  if (source) {
    source.disconnect()
    source = null
  }
  if (audioContext) {
    audioContext.close()
    audioContext = null
  }
  if (currentStream) {
    currentStream.getTracks().forEach((t) => t.stop())
    currentStream = null
  }
  // FIX: [2026-07-03] 清理 WHEP 拉流连接 [全栈工程师]
  if (recvPc) {
    try {
      recvPc.getReceivers().forEach((r) => { r.track && r.track.stop() })
      recvPc.close()
    } catch { /* ignore */ }
    recvPc = null
  }
}

const startTalk = async () => {
  if (starting || isTalking.value) return
  starting = true
  stopped = false
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    currentStream = stream

    // P0-6: 通过 ws-ticket 认证，消除 URL 暴露 JWT token
    // FIX: [2026-07-03] 根据模式选择 WebSocket 端点（单向广播 vs 双向对讲） [全栈工程师]
    let wsPath: string
    if (props.mode === 'bidirectional' && props.channelId) {
      wsPath = `/api/v1/talk/talk/bidirectional/${props.deviceId}/${props.channelId}`
    } else {
      wsPath = `/api/v1/talk/ws/talk/${props.deviceId}`
    }
    const wsUrl = await buildWsUrlWithTicket(wsPath)
    ws = new WebSocket(wsUrl)

    connectTimer = setTimeout(() => {
      if (!isTalking.value && ws && ws.readyState !== WebSocket.OPEN) {
        ElMessage.warning(t('talk.connectTimeout'))
        stopTalk()
      }
    }, WS_CONNECT_TIMEOUT)

    ws.onopen = () => {
      if (connectTimer) {
        clearTimeout(connectTimer)
        connectTimer = null
      }
      isTalking.value = true
      startAudioProcessing(stream)
    }

    // FIX: [2026-07-03] 双向对讲模式处理 session_ready 消息，建立 WHEP 拉流 [全栈工程师]
    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'session_ready' && msg.whep_url) {
          await setupWhepReceiver(msg.whep_url)
        }
      } catch {
        // 非 JSON 消息或解析失败，忽略
      }
    }
    
    ws.onerror = () => {
      ElMessage.warning(t('talk.connectFailed'))
      stopTalk()
    }

    ws.onclose = () => {
      stopTalk()
    }
    
  } catch (error) {
    ElMessage.warning(t('talk.micPermissionDenied'))  // FIXED: i18n
    stopTalk()
  } finally {
    starting = false
  }
}

const startAudioProcessing = (stream: MediaStream) => {
  audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 8000 })
  source = audioContext.createMediaStreamSource(stream)
  // Buffer size 2048, 1 input channel, 1 output channel
  processor = audioContext.createScriptProcessor(2048, 1, 1)

  processor.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    const inputData = e.inputBuffer.getChannelData(0)
    // 后端已实现 PCM 16bit → G.711A 转码，前端发送 PCM 16bit LE
    const pcm16 = floatTo16BitPCM(inputData)
    ws.send(pcm16)
  }

  source.connect(processor)
  // FIX: [2026-07-03] 原直接 processor.connect(destination) 会把麦克风音频回放给扬声器造成回声/自激；
  // ScriptProcessorNode 必须连到 destination 才会触发 onaudioprocess，故串入 gain=0 的 GainNode 静音输出 [全栈工程师]
  const silentGain = audioContext.createGain()
  silentGain.gain.value = 0
  processor.connect(silentGain)
  silentGain.connect(audioContext.destination)
}

// FIX: [2026-07-03] WHEP 拉流接收设备回传音频 [全栈工程师]
const setupWhepReceiver = async (whepUrl: string) => {
  try {
    recvPc = new RTCPeerConnection()
    // 仅接收音频（设备→前端方向）
    recvPc.addTransceiver('audio', { direction: 'recvonly' })

    recvPc.ontrack = (event) => {
      const recvStream = event.streams[0]
      if (audioEl.value && recvStream) {
        audioEl.value.srcObject = recvStream
        audioEl.value.play().catch(() => {
          // 自动播放可能被浏览器阻止，忽略
        })
      }
    }

    const offer = await recvPc.createOffer()
    await recvPc.setLocalDescription(offer)

    // 发送 SDP offer 到 WHEP 端点
    const resp = await fetch(whepUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: offer.sdp,
    })

    if (!resp.ok) {
      logger.warn(`WHEP request failed: ${resp.status}`)
      return
    }

    const answerSdp = await resp.text()
    await recvPc.setRemoteDescription({ type: 'answer', sdp: answerSdp })
  } catch (err) {
    // WHEP 拉流失败不影响发送方向
    console.warn('WHEP receiver setup failed:', err)
  }
}

const floatTo16BitPCM = (input: Float32Array) => {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
  }
  return output.buffer
}

onBeforeUnmount(() => {
  stopTalk()
})
</script>

<style scoped>
.talk-btn {
  width: 50px;
  height: 50px;
  font-size: 24px;
}
</style>
