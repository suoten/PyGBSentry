import { ref, reactive } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../../utils/errorMessage'
import i18n from '@/locales'
import type { Channel } from '@/types/models'

const normalizePlayUrl = (value: unknown) => { let text = String(value || '').trim(); while (text.length >= 2) { const first = text[0]; const last = text[text.length - 1]; if ((first === '`' && last === '`') || (first === '"' && last === '"') || (first === "'" && last === "'")) { text = text.slice(1, -1).trim(); continue } break } return text }
const isSecurePage = () => window.location.protocol === 'https:'
const MIN_POLL_MS = 150

const toPlayFailureText = (friendly: ReturnType<typeof getFriendlyError>) => {
  const t = i18n.global.t
  const rc = String(friendly.reasonCode || '').trim()
  if (rc === 'media_node_unreachable' || rc === 'media_node_unavailable' || rc === 'media_port_exhausted') return { stage: t('player.mediaServerError'), message: t('player.mediaServerMsg'), suggestion: t('player.mediaServerSuggestion') }
  if (rc === 'invite_send_failed' || rc === 'device_transport_unavailable' || rc === 'sip_service_unavailable') return { stage: t('player.deviceConnectError'), message: t('player.deviceConnectMsg'), suggestion: t('player.deviceConnectSuggestion') }
  if (rc === 'media_stream_not_ready') return { stage: t('player.pullTimeout'), message: t('player.pullTimeoutMsg'), suggestion: t('player.pullTimeoutSuggestion') }
  return { stage: t('player.playFailure'), message: friendly.message, suggestion: friendly.suggestion || '' }
} // FIXED: i18n

export function usePlayer() {
  const playerVisible = ref(false)
  const playUrl = ref('')
  const playCodec = ref('')
  const playApp = ref('')
  const playStreamId = ref('')
  const playMode = ref<'webrtc' | 'flv' | 'hls' | 'raw'>('flv')
  const playUrls = reactive<Record<string, string>>({})
  const playingChannelGbId = ref<string>('')
  const channelPlayLoading = ref<Record<string, boolean>>({})
  const currentDevice = ref<Channel>(null)
  const currentChannel = ref<Channel>(null)
  const playRequest = reactive<{ status: string; stage: string; progress: number; message: string; suggestion: string; retryable: boolean; diagnostics: Record<string, unknown> }>({ status: 'idle', stage: '', progress: 0, message: '', suggestion: '', retryable: true, diagnostics: {} })
  let playRequestAbort: AbortController | null = null
  let playRequestInterval: ReturnType<typeof setInterval> | null = null
  const playRequestTimeouts: Record<string, unknown>[] = []

  const clearPlayRequestTimers = () => { if (playRequestInterval) { clearInterval(playRequestInterval); playRequestInterval = null } while (playRequestTimeouts.length) { const t = playRequestTimeouts.pop(); try { clearTimeout(t) } catch { /* cleanup: ignore */ } } }
  const resetPlayRequest = () => { clearPlayRequestTimers(); if (playRequestAbort) { try { playRequestAbort.abort() } catch { /* cleanup: ignore */ }; playRequestAbort = null } playRequest.status = 'idle'; playRequest.stage = ''; playRequest.progress = 0; playRequest.message = ''; playRequest.suggestion = ''; playRequest.retryable = true; playRequest.diagnostics = {} }

  /** Pick the first non-empty URL from a list of keys, respecting secure-page preference. */
  const pickPreferred = (secureKeys: string[], insecureKeys: string[]) => {
    const keys = isSecurePage() ? secureKeys : insecureKeys
    for (const k of keys) {
      const v = normalizePlayUrl(playUrls[k])
      if (v) return v
    }
    return ''
  }
  const pickPreferredFlv = () => pickPreferred(
    ['wss_flv', 'https_flv', 'ws_flv', 'flv'],
    ['flv', 'ws_flv', 'https_flv', 'wss_flv'],
  )
  const pickPreferredHls = () => pickPreferred(
    ['wss_hls', 'https_hls', 'ws_hls', 'hls'],
    ['hls', 'ws_hls', 'https_hls', 'wss_hls'],
  )
  const pickPreferredWebrtc = () => pickPreferred(
    ['rtcs', 'webrtc', 'rtc'],
    ['webrtc', 'rtc', 'rtcs'],
  )

  /** Determine play mode from the preferred URL or available URLs. */
  const resolvePlayMode = (preferredUrl: string, preferredFlv: string, preferredHls: string): 'webrtc' | 'flv' | 'hls' | 'raw' => {
    const lower = preferredUrl.toLowerCase()
    if (lower.includes('/index/api/webrtc')) return 'webrtc'
    if (lower.includes('.m3u8')) return 'hls'
    if (lower.includes('.flv')) return 'flv'
    if (preferredFlv) return 'flv'
    if (preferredHls) return 'hls'
    if (playUrls.webrtc) return 'webrtc'
    return 'raw'
  }

  /** Select the play URL based on the resolved mode. */
  const resolvePlayUrl = (mode: 'webrtc' | 'flv' | 'hls' | 'raw', preferredFlv: string, preferredHls: string): string => {
    if (mode === 'webrtc') return pickPreferredWebrtc()
    if (mode === 'flv') return preferredFlv
    if (mode === 'hls') return preferredHls
    return normalizePlayUrl(playUrls.raw)
  }

  /** Populate playUrls from the API response data. */
  const populatePlayUrls = (data: Record<string, unknown>) => {
    for (const [k, v] of Object.entries(data)) {
      if (k !== 'codec' && k !== 'app' && k !== 'stream') {
        (playUrls as Record<string, unknown>)[k] = normalizePlayUrl(v)
      }
    }
  }

  /** Poll an async play session until a final response is received. */
  const pollPlaySession = async (sessionId: string): Promise<{ data: Record<string, unknown>; status: number }> => {
    let retryCount = 0
    while (true) {
      if (playRequestAbort?.signal.aborted) throw new DOMException('Aborted', 'AbortError')
      await new Promise(r => setTimeout(r, MIN_POLL_MS))
      const pollRes = await api.get(`/api/v1/stream/play_status/${sessionId}`, { signal: playRequestAbort?.signal })
      if (pollRes.status === 202 && pollRes.data?.data?.status === 'waiting') {
        retryCount++
        if (retryCount > 60) throw new Error(i18n.global.t('player.waitTimeout'))
        continue
      }
      return pollRes
    }
  }

  /** Fetch a snapshot image for the channel (fire-and-forget). */
  const fetchSnapshot = (channelId: string) => {
    try {
      const snapUrl = `/api/v1/devices/channels/${encodeURIComponent(channelId)}/snap?stream_type=auto&prefer_existing=true&allow_invite=false&force=true&ts=${Date.now()}`
      const snapToken = sessionStorage.getItem('token') || ''
      fetch(snapUrl, { headers: { Authorization: `Bearer ${snapToken}` } })
        .then(r => r.blob())
        .then(blob => {
          const img = new Image()
          img.onload = () => {}
          img.onerror = () => {}
          img.src = URL.createObjectURL(blob)
          setTimeout(() => URL.revokeObjectURL(img.src), 30000)
        })
        .catch(() => { /* ignore */ })
    } catch { /* ignore */ }
  }

  /** Handle play-stream errors, distinguishing cancellations from real failures. */
  const handlePlayError = (e: unknown) => {
    clearPlayRequestTimers(); playRequestAbort = null
    const friendly = getFriendlyError(e)
    const errObj = e && typeof e === 'object' ? (e as { name?: unknown; code?: unknown; _isCanceled?: boolean }) : null
    const isCanceled = String(errObj?.name || '').toLowerCase() === 'canceled'
      || String(errObj?.code || '') === 'ERR_CANCELED'
      || Boolean(errObj?._isCanceled)
      || (e as Error)?.name === 'AbortError'
    if (isCanceled) {
      playRequest.status = 'idle'
    } else {
      const failure = toPlayFailureText(friendly)
      playRequest.status = 'error'
      playRequest.stage = failure.stage
      playRequest.progress = 100
      playRequest.message = failure.message
      playRequest.suggestion = failure.suggestion
      playRequest.retryable = Boolean(friendly.retryable ?? true)
      playRequest.diagnostics = friendly.diagnostics || {}
    }
  }

  const playStream = async (row: Record<string, unknown>) => {
    const deviceId = String(row?.device_id || row?.deviceId || '').trim()
    const channelId = String(row?.gb_id || row?.channelId || row?.id || '').trim()
    if (!deviceId || !channelId) return

    currentChannel.value = row
    currentDevice.value = { gb_id: deviceId, name: row.device_name || deviceId }
    const key = channelId
    channelPlayLoading.value[key] = true

    // Reset play state
    for (const k of Object.keys(playUrls)) playUrls[k] = ''
    playCodec.value = ''; playApp.value = ''; playStreamId.value = ''
    playMode.value = 'flv'; playingChannelGbId.value = channelId; playerVisible.value = true

    // Set up request progress UI
    resetPlayRequest()
    playRequest.status = 'requesting'
    playRequest.stage = i18n.global.t('player.sendPlayRequest')
    playRequest.progress = 8
    playRequest.message = i18n.global.t('player.requestingMsg')
    playRequest.diagnostics = { device_id: deviceId, channel_id: channelId }

    // Progress timers
    playRequestTimeouts.push(setTimeout(() => {
      if (playRequest.status !== 'requesting') return
      playRequest.status = 'waiting'
      playRequest.stage = i18n.global.t('player.waitingDevice')
      playRequest.progress = Math.max(playRequest.progress, 22)
      playRequest.message = i18n.global.t('player.waitingDeviceMsg')
    }, 700))
    playRequestTimeouts.push(setTimeout(() => {
      if (playRequest.status !== 'waiting' && playRequest.status !== 'requesting') return
      playRequest.status = 'waiting'
      playRequest.stage = i18n.global.t('player.waitingMedia')
      playRequest.progress = Math.max(playRequest.progress, 48)
      playRequest.message = i18n.global.t('player.waitingMediaMsg')
    }, 2800))
    playRequestInterval = setInterval(() => {
      if (playRequest.status !== 'requesting' && playRequest.status !== 'waiting') return
      playRequest.progress = Math.min(92, playRequest.progress + 2)
    }, 400)

    try {
      playRequestAbort = new AbortController()
      let res = await api.post(`/api/v1/stream/play/${deviceId}/${channelId}`, null, {
        params: { stream_type: 'auto', async_mode: true },
        signal: playRequestAbort.signal,
      })

      // Handle async mode (202 + session_id → poll)
      if (res.status === 202 && res.data?.data?.session_id) {
        res = await pollPlaySession(res.data.data.session_id)
      }

      // Populate URLs from response
      const data = res.data || {}
      populatePlayUrls(data)
      playCodec.value = String(res.data?.codec || '')
      playApp.value = String(res.data?.app || '')
      playStreamId.value = String(res.data?.stream || '')

      // Resolve mode and URL
      const preferredFlv = pickPreferredFlv()
      const preferredHls = pickPreferredHls()
      const preferredUrl = normalizePlayUrl(playUrls.preferred_url || '')
      playMode.value = resolvePlayMode(preferredUrl, preferredFlv, preferredHls)
      playUrl.value = resolvePlayUrl(playMode.value, preferredFlv, preferredHls)

      // Fire-and-forget snapshot fetch
      fetchSnapshot(channelId)

      // Mark ready
      clearPlayRequestTimers()
      playRequestAbort = null
      playRequest.status = 'ready'
      playRequest.stage = i18n.global.t('player.streamReady')
      playRequest.progress = 100
      playRequest.message = ''
      playRequest.suggestion = ''
      playRequest.diagnostics = {}
    } catch (e: unknown) {
      handlePlayError(e)
    } finally {
      channelPlayLoading.value[key] = false
    }
  }

  const closePlayer = async () => { resetPlayRequest(); if (playStreamId.value) { try { await api.post('/api/v1/stream/stop', { app: playApp.value || 'live', stream: playStreamId.value }) } catch { /* cleanup: ignore */ } } playUrl.value = ''; playCodec.value = ''; playApp.value = ''; playStreamId.value = ''; playMode.value = 'webrtc'; playUrls.webrtc = ''; playUrls.flv = ''; playUrls.hls = ''; playUrls.raw = ''; playingChannelGbId.value = ''; playerVisible.value = false }

  const switchingStream = ref(false)
  const switchStreamType = async (targetStreamType: 'main' | 'sub') => {
    if (!playStreamId.value) { ElMessage.warning(i18n.global.t('player.noStreamPlaying')); return } // FIXED: i18n
    switchingStream.value = true
    try {
      const res = await api.post(`/api/v1/stream/play/${playStreamId.value}/switch`, null, { params: { target_stream_type: targetStreamType } })
      const data = res.data || {}
      populatePlayUrls(data)
      playCodec.value = String(data.codec || '')
      playApp.value = String(data.app || '')
      playStreamId.value = String(data.stream || '')
      const preferredFlv = pickPreferredFlv()
      const preferredHls = pickPreferredHls()
      const preferredUrl = normalizePlayUrl(playUrls.preferred_url || '')
      playMode.value = resolvePlayMode(preferredUrl, preferredFlv, preferredHls)
      playUrl.value = resolvePlayUrl(playMode.value, preferredFlv, preferredHls)
      ElMessage.success(targetStreamType === 'main' ? i18n.global.t('player.switchedToMain') : i18n.global.t('player.switchedToSub')) // FIXED: i18n
    } catch (e: unknown) {
      const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
    } finally {
      switchingStream.value = false
    }
  }

  return { playerVisible, playUrl, playCodec, playApp, playStreamId, playMode, playUrls, playingChannelGbId, channelPlayLoading, currentDevice, currentChannel, playRequest, playStream, closePlayer, switchingStream, switchStreamType }
}
