<template>
  <AdvancedVideoPlayerDialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="playerDialogTitle"
    :subtitle="playerDialogSubtitle"
    :request="playRequest || undefined"
    :urls="playUrls"
    :play-url="playUrl"
    :codec="playCodec"
    :app="playApp"
    :stream="playStreamId"
    :device-id="deviceId"
    :channel-id="channelId"
    :device-status="deviceStatus"
    @close="closePlayer"
    @refresh="refreshStream"
  />
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import api from '@/utils/http'
import { getFriendlyError } from '../../utils/errorMessage'
import AdvancedVideoPlayerDialog from '../AdvancedVideoPlayerDialog.vue'

const props = defineProps<{
  visible: boolean
  deviceId: string
  channelId: string
  deviceName?: string
  channelName?: string
  deviceStatus?: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>()

interface PlayRequestUi {
  status: 'idle' | 'requesting' | 'waiting' | 'ready' | 'error'
  stage: string
  message?: string
  progress: number
  retryable?: boolean
  diagnostics?: Record<string, unknown>
  urlAvailability?: Record<string, boolean | null>
  hlsProbeDetail?: Record<string, unknown>
}

const playUrl = ref('')
const playCodec = ref('')
const playApp = ref('')
const playStreamId = ref('')
const playUrls = reactive({ webrtc: '', flv: '', hls: '', raw: '' })
const playMode = ref<'webrtc' | 'flv' | 'hls' | 'raw'>('webrtc')
const playRequest = ref<PlayRequestUi | null>(null)
const playSessionId = ref('')
const playSeq = ref(0)
const playDiag = reactive<{
  zlm_probe_ok: boolean
  zlm_stream_ready: boolean
  invite_sdp_ip: string
  invite_media_port: number | null
  invite_media_protocol: string
  rtp_port_range: string
}>({
  zlm_probe_ok: false,
  zlm_stream_ready: false,
  invite_sdp_ip: '',
  invite_media_port: null,
  invite_media_protocol: '',
  rtp_port_range: ''
})

const stopCurrentStream = async () => {
  if (!playApp.value || !playStreamId.value) return
  try {
    await api.post('/api/v1/stream/stop', {
      app: String(playApp.value || 'live').trim() || 'live',
      stream: String(playStreamId.value || '').trim()
    })
  } catch { /* cleanup: ignore */ }
}

const playerDialogTitle = computed(() => {
  const d = props.deviceName || props.deviceId || '设备'
  const c = props.channelName || props.channelId || '通道'
  return `${d} / ${c}`
})

const playerDialogSubtitle = computed(() => {
  if (!props.deviceId || !props.channelId) return ''
  return `${props.deviceId} / ${props.channelId}`
})

const pickPreferredWebrtc = () => {
  const raw = String(playUrls.webrtc || '').trim()
  if (!raw) return ''
  if (!raw.includes(',')) return raw
  const arr = raw.split(',').map((x) => x.trim()).filter(Boolean)
  if (!arr.length) return ''
  const httpsOrWss = arr.find((x) => x.startsWith('https://') || x.startsWith('wss://'))
  if (httpsOrWss) return httpsOrWss
  return arr[0]
}

const normalizePlayUrl = (u: string | null | undefined) => {
  if (!u) return ''
  const s = String(u).trim()
  if (!s.includes(',')) return s
  const arr = s.split(',').map((x) => x.trim()).filter(Boolean)
  if (!arr.length) return ''
  const secure = arr.find((x) => x.startsWith('https://') || x.startsWith('wss://'))
  if (secure) return secure
  return arr[0]
}

const toPlayFailureText = (friendly: { message: string; suggestion?: string }) => {
  const msg = String(friendly.message || '').trim()
  const lowerMsg = msg.toLowerCase()
  let stage = '点播失败'
  let outMessage = msg
  if (lowerMsg.includes('timeout') || lowerMsg.includes('超时')) {
    stage = '设备响应超时'
    outMessage = '设备未在规定时间内回复INVITE或推流，请检查设备网络或下级平台状态。'
  } else if (lowerMsg.includes('offline') || lowerMsg.includes('离线')) {
    stage = '设备离线'
    outMessage = '设备当前处于离线状态，无法发起实时点播。'
  } else if (lowerMsg.includes('busy') || lowerMsg.includes('繁忙')) {
    stage = '设备繁忙'
    outMessage = '设备正在处理其他任务，暂无法响应新的点播请求。'
  } else if (lowerMsg.includes('auth') || lowerMsg.includes('认证') || lowerMsg.includes('401') || lowerMsg.includes('403')) {
    stage = '设备拒绝'
    outMessage = '设备返回认证失败或拒绝访问。'
  } else if (lowerMsg.includes('port') || lowerMsg.includes('端口')) {
    stage = '流媒体资源不足'
    outMessage = '服务器RTP收流端口已耗尽，请稍后重试或扩大端口范围。'
  } else if (lowerMsg.includes('network') || lowerMsg.includes('网络')) {
    stage = '网络异常'
    outMessage = '服务内部网络请求失败，请检查ZLM流媒体组件状态。'
  }
  if (friendly.suggestion) {
    outMessage += ` (${friendly.suggestion})`
  }
  return { stage, message: outMessage }
}

const playStream = async () => {
  if (!props.deviceId || !props.channelId) return
  const seq = (playSeq.value += 1)
  playSessionId.value = ''
  playRequest.value = {
    status: 'requesting',
    stage: '正在发起点播…',
    progress: 5,
    retryable: true,
    diagnostics: {
      device_id: String(props.deviceId || ''),
      channel_id: String(props.channelId || '')
    }
  }
  playUrl.value = ''
  playCodec.value = ''
  playApp.value = ''
  playStreamId.value = ''
  playUrls.webrtc = ''
  playUrls.flv = ''
  playUrls.hls = ''
  playUrls.raw = ''
  playDiag.zlm_probe_ok = false
  playDiag.zlm_stream_ready = false
  playDiag.invite_sdp_ip = ''
  playDiag.invite_media_port = null
  playDiag.invite_media_protocol = ''
  playDiag.rtp_port_range = ''
  try {
    const res = await api.post(
      `/api/v1/stream/play/${props.deviceId}/${props.channelId}`,
      null,
      { params: { stream_type: 'auto', async_mode: true } }
    )
    if (seq !== playSeq.value) return
    const maybeSessionId = String(res.data?.data?.session_id || '').trim()
    if (!maybeSessionId) {
      throw new Error('invalid_play_session')
    }
    playSessionId.value = maybeSessionId
    playRequest.value = {
      status: 'waiting',
      stage: '等待媒体流就绪…',
      progress: 15,
      retryable: true,
      diagnostics: {
        ...((playRequest.value && playRequest.value.diagnostics) || {}),
        session_id: playSessionId.value,
        node_id: String(res.data?.data?.node_id || ''),
        app: String(res.data?.data?.app || ''),
        stream: String(res.data?.data?.stream || '')
      }
    }
    const startAt = Date.now()
    const initialTimeout = Number(res.data?.data?.timeout_recommend_ms)
    const timeoutMs = Number.isFinite(initialTimeout) ? Math.max(20000, Math.min(90000, Math.round(initialTimeout))) : 45000
    let attempts = 0
    while (Date.now() - startAt < timeoutMs) {
      if (seq !== playSeq.value) return
      attempts += 1
      const statusRes = await api.get(`/api/v1/stream/play_status/${encodeURIComponent(playSessionId.value)}`)
      if (seq !== playSeq.value) return
      if (statusRes.status === 202) {
        const suggestedPoll = Number(statusRes.data?.data?.next_poll_ms)
        const pollMs = Number.isFinite(suggestedPoll) ? Math.max(300, Math.min(2000, Math.round(suggestedPoll))) : 600
        const zlmProbeOk = !!statusRes.data?.data?.zlm_probe_ok
        const zlmStreamReady = !!statusRes.data?.data?.zlm_stream_ready
        const probe = statusRes.data?.data?.probe
        const streamFound = probe && typeof probe === 'object' ? Boolean((probe as Record<string, unknown>).stream_found) : false
        const playable = probe && typeof probe === 'object' ? Boolean((probe as Record<string, unknown>).playable) : false
        playDiag.zlm_probe_ok = zlmProbeOk
        playDiag.zlm_stream_ready = zlmStreamReady
        const progress = Math.min(90, 15 + attempts * 5)
        playRequest.value = {
          status: 'waiting',
          stage: !zlmProbeOk ? '正在检查流媒体服务器…' : !streamFound ? '正在等待设备推流…' : !playable ? '视频流已到达，正在准备播放…' : '正在等待视频流就绪…',
          progress,
          retryable: true,
          message: !zlmProbeOk
            ? '流媒体服务器连接异常，请检查网络或服务状态'
            : !streamFound
              ? '流媒体服务器已连通，但暂未收到设备视频流'
              : !playable
                ? '视频流已到达，但暂时无法播放'
                : '视频流准备中，请稍候',
          diagnostics: {
            ...((playRequest.value && playRequest.value.diagnostics) || {}),
            zlm_probe_ok: zlmProbeOk,
            zlm_stream_ready: zlmStreamReady,
            probe
          }
        }
        await new Promise((r) => setTimeout(r, pollMs))
        continue
      }
      const data = statusRes.data || {}
      playDiag.zlm_probe_ok = !!data?.zlm_probe_ok
      playDiag.zlm_stream_ready = !!data?.zlm_stream_ready
      playUrls.webrtc = String(data?.webrtc || '')
      playUrls.flv = String(data?.flv || '')
      playUrls.hls = String(data?.hls || '')
      playUrls.raw = String(data?.raw || '')
      playCodec.value = String(data?.codec || '')
      playApp.value = String(data?.app || '')
      playStreamId.value = String(data?.stream || '')
      
      const preferredWebrtc = pickPreferredWebrtc()
      const preferredFlv = normalizePlayUrl(playUrls.flv)
      const preferredHls = normalizePlayUrl(playUrls.hls)
      
      // 优先检查后端返回的 preferred_url，决定播放模式
      const backendPreferredUrl = String(data?.preferred_url || data?.preferredUrl || '').toLowerCase()
      const userPref = String(localStorage.getItem('pygbsentry:player-pref') || '').toLowerCase()
      
      // 后端优先返回 HLS 时，优先使用 HLS
      if (backendPreferredUrl.includes('.m3u8') || backendPreferredUrl.includes('/hls/')) {
        playMode.value = 'hls'
      } else if (backendPreferredUrl.includes('.flv') || backendPreferredUrl.includes('/live/')) {
        playMode.value = 'flv'
      } else if (userPref === 'webrtc') {
        playMode.value = 'webrtc'
      } else if (userPref.includes('.m3u8')) {
        playMode.value = 'hls'
      } else if (userPref.includes('.flv')) {
        playMode.value = 'flv'
      } else {
        // 默认：优先 HLS，其次 FLV，最后 WebRTC
        playMode.value = preferredHls ? 'hls' : preferredFlv ? 'flv' : playUrls.webrtc ? 'webrtc' : 'raw'
      }

      playUrl.value =
        playMode.value === 'webrtc'
          ? preferredWebrtc
          : playMode.value === 'flv'
          ? preferredFlv
          : playMode.value === 'hls'
            ? preferredHls
            : normalizePlayUrl(playUrls.raw)

      playRequest.value = {
        status: 'ready',
        stage: '点播成功',
        progress: 100,
        retryable: true,
        urlAvailability: (data?.urlAvailability as Record<string, boolean | null>) || undefined,
        hlsProbeDetail: (data?.hlsProbeDetail as Record<string, unknown>) || undefined,
        diagnostics: {
          ...((playRequest.value && playRequest.value.diagnostics) || {}),
          invite_media_protocol: String(data?.invite_media_protocol || ''),
          diagnostics: data?.diagnostics || {},
          auto_heal_profile: data?.auto_heal_profile || ((data?.diagnostics || {}) as Record<string, unknown>)?.autoHealProfile || {}
        }
      }
      return
    }
    throw new Error('play_status_timeout')
  } catch (e: unknown) {
    const err = e as Record<string, unknown> | undefined
    if (err?.name === 'CanceledError' || err?.name === 'AbortError' || err?.code === 'ERR_CANCELED' || err?._isCanceled) {
      playRequest.value = { status: 'idle', stage: '', progress: -1, message: '', retryable: true, diagnostics: {} }
      return
    }
    const friendly = getFriendlyError(e)
    const failure = toPlayFailureText(friendly)
    playRequest.value = {
      status: 'error',
      stage: failure.stage,
      progress: -1,
      message: failure.message,
      retryable: true,
      diagnostics: playRequest.value?.diagnostics || {}
    }
  }
}

const closePlayer = async () => {
  playSeq.value += 1
  await stopCurrentStream()
  playSessionId.value = ''
  playUrl.value = ''
  playStreamId.value = ''
  playRequest.value = null
  emit('update:visible', false)
}

const refreshStream = async () => {
  await stopCurrentStream()
  await playStream()
}

watch(() => props.visible, (val) => {
  if (val) {
    playStream()
  } else {
    closePlayer()
  }
})

onBeforeUnmount(() => {
  if (playApp.value && playStreamId.value) {
    void stopCurrentStream()
  }
})
</script>
