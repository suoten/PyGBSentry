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
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  deviceId: string
}>()

const isTalking = ref(false)
let ws: WebSocket | null = null
let audioContext: AudioContext | null = null
let processor: ScriptProcessorNode | null = null
let source: MediaStreamAudioSourceNode | null = null
let currentStream: MediaStream | null = null
let starting = false
let stopped = false
let connectTimer: ReturnType<typeof setTimeout> | null = null
const WS_CONNECT_TIMEOUT = 8000

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
}

const startTalk = async () => {
  if (starting || isTalking.value) return
  starting = true
  stopped = false
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    currentStream = stream
    
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const host = location.host
    // FIXED-P1: R3-02 对讲WebSocket连接添加token认证参数
    ws = new WebSocket(`${protocol}://${host}/api/v1/talk/ws/talk/${props.deviceId}?token=${encodeURIComponent(localStorage.getItem('token') || '')}`)
    
    connectTimer = setTimeout(() => {
      if (!isTalking.value && ws && ws.readyState !== WebSocket.OPEN) {
        ElMessage.warning('对讲连接超时，请稍后重试')
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
    
    ws.onerror = () => {
      ElMessage.warning('对讲连接失败，请检查网络或设备对讲能力')
      stopTalk()
    }

    ws.onclose = () => {
      stopTalk()
    }
    
  } catch (error) {
    ElMessage.warning('无法获取麦克风权限，请在浏览器设置中允许麦克风')
    stopTalk()
  } finally {
    starting = false
  }
}

const startAudioProcessing = (stream: MediaStream) => {
  audioContext = new (window.AudioContext || (window as Record<string, unknown>).webkitAudioContext)({ sampleRate: 8000 })
  source = audioContext.createMediaStreamSource(stream)
  // Buffer size 2048, 1 input channel, 1 output channel
  processor = audioContext.createScriptProcessor(2048, 1, 1)
  
  processor.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    
    const inputData = e.inputBuffer.getChannelData(0)
    // Convert Float32 to PCMA (G.711A) or just send PCM 16bit and let backend handle
    // For simplicity, we send PCM 16bit Little Endian
    const pcm16 = floatTo16BitPCM(inputData)
    ws.send(pcm16)
  }
  
  source.connect(processor)
  processor.connect(audioContext.destination)
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
