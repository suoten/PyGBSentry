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

  const pickPreferredFlv = () => isSecurePage() ? normalizePlayUrl(playUrls.wss_flv || playUrls.https_flv || playUrls.ws_flv || playUrls.flv || '') : normalizePlayUrl(playUrls.flv || playUrls.ws_flv || playUrls.https_flv || playUrls.wss_flv || '')
  const pickPreferredHls = () => isSecurePage() ? normalizePlayUrl(playUrls.wss_hls || playUrls.https_hls || playUrls.ws_hls || playUrls.hls || '') : normalizePlayUrl(playUrls.hls || playUrls.ws_hls || playUrls.https_hls || playUrls.wss_hls || '')
  const pickPreferredWebrtc = () => isSecurePage() ? normalizePlayUrl(playUrls.rtcs || playUrls.webrtc || playUrls.rtc || '') : normalizePlayUrl(playUrls.webrtc || playUrls.rtc || playUrls.rtcs || '')

  const playStream = async (row: Record<string, unknown>) => {
    const deviceId = String(row?.device_id || row?.deviceId || '').trim(); const channelId = String(row?.gb_id || row?.channelId || row?.id || '').trim(); if (!deviceId || !channelId) return
    currentChannel.value = row; currentDevice.value = { gb_id: deviceId, name: row.device_name || deviceId }
    const key = channelId; channelPlayLoading.value[key] = true
    for (const k of Object.keys(playUrls)) playUrls[k] = ''
    playCodec.value = ''; playApp.value = ''; playStreamId.value = ''; playMode.value = 'flv'; playingChannelGbId.value = channelId; playerVisible.value = true
    resetPlayRequest(); playRequest.status = 'requesting'; playRequest.stage = i18n.global.t('player.sendPlayRequest'); playRequest.progress = 8; playRequest.message = i18n.global.t('player.requestingMsg'); playRequest.suggestion = ''; playRequest.retryable = true; playRequest.diagnostics = { device_id: deviceId, channel_id: channelId }
    playRequestTimeouts.push(setTimeout(() => { if (playRequest.status !== 'requesting') return; playRequest.status = 'waiting'; playRequest.stage = i18n.global.t('player.waitingDevice'); playRequest.progress = Math.max(playRequest.progress, 22); playRequest.message = i18n.global.t('player.waitingDeviceMsg') }, 700))
    playRequestTimeouts.push(setTimeout(() => { if (playRequest.status !== 'waiting' && playRequest.status !== 'requesting') return; playRequest.status = 'waiting'; playRequest.stage = i18n.global.t('player.waitingMedia'); playRequest.progress = Math.max(playRequest.progress, 48); playRequest.message = i18n.global.t('player.waitingMediaMsg') }, 2800)) // FIXED: i18n
    playRequestInterval = setInterval(() => { if (playRequest.status !== 'requesting' && playRequest.status !== 'waiting') return; playRequest.progress = Math.min(92, playRequest.progress + 2) }, 400)
    try {
      playRequestAbort = new AbortController(); let res = await api.post(`/api/v1/stream/play/${deviceId}/${channelId}`, null, { params: { stream_type: 'auto', async_mode: true }, signal: playRequestAbort.signal })
      if (res.status === 202 && res.data?.data?.session_id) { const sessionId = res.data.data.session_id; let retryCount = 0; // FIXED: 移除非空断言!，外层if已守卫 while (true) { if (playRequestAbort.signal.aborted) throw new DOMException('Aborted', 'AbortError'); await new Promise(r => setTimeout(r, MIN_POLL_MS)); const pollRes = await api.get(`/api/v1/stream/play_status/${sessionId}`, { signal: playRequestAbort.signal }); if (pollRes.status === 202 && pollRes.data?.data?.status === 'waiting') { retryCount++; if (retryCount > 60) throw new Error(i18n.global.t('player.waitTimeout')); continue } res = pollRes; break } }
      const data = res.data || {}
      for (const [k, v] of Object.entries(data)) { if (k !== 'codec' && k !== 'app' && k !== 'stream') (playUrls as Record<string, unknown>)[k] = normalizePlayUrl(v) }
      playCodec.value = String(res.data?.codec || ''); playApp.value = String(res.data?.app || ''); playStreamId.value = String(res.data?.stream || '')
      const preferredFlv = pickPreferredFlv(); const preferredHls = pickPreferredHls(); const preferredUrl = normalizePlayUrl(playUrls.preferred_url || ''); const preferredLower = preferredUrl.toLowerCase(); const preferredMode = preferredLower.includes('/index/api/webrtc') ? 'webrtc' : preferredLower.includes('.m3u8') ? 'hls' : preferredLower.includes('.flv') ? 'flv' : ''
      playMode.value = (preferredMode as Record<string, unknown>) || (preferredFlv ? 'flv' : preferredHls ? 'hls' : playUrls.webrtc ? 'webrtc' : 'raw')
      playUrl.value = playMode.value === 'webrtc' ? pickPreferredWebrtc() : playMode.value === 'flv' ? preferredFlv : playMode.value === 'hls' ? preferredHls : normalizePlayUrl(playUrls.raw)
      try { const token = localStorage.getItem('token') || ''; const img = new Image(); img.onload = () => {}; img.onerror = () => {}; img.src = `/api/v1/devices/channels/${encodeURIComponent(channelId)}/snap?stream_type=auto&prefer_existing=true&allow_invite=false&force=true&ts=${Date.now()}&token=${token}` } catch { /* ignore */ }
      clearPlayRequestTimers(); playRequestAbort = null; playRequest.status = 'ready'; playRequest.stage = i18n.global.t('player.streamReady'); playRequest.progress = 100; playRequest.message = ''; playRequest.suggestion = ''; playRequest.retryable = true; playRequest.diagnostics = {} // FIXED: i18n
    } catch (e: unknown) { clearPlayRequestTimers(); playRequestAbort = null; const friendly = getFriendlyError(e); const errObj = e && typeof e === 'object' ? (e as { name?: unknown; code?: unknown; _isCanceled?: boolean }) : null; if (String(errObj?.name || '').toLowerCase() === 'canceled' || String(errObj?.code || '') === 'ERR_CANCELED' || errObj?._isCanceled || (e as Error)?.name === 'AbortError') { playRequest.status = 'idle' } else { const failure = toPlayFailureText(friendly); playRequest.status = 'error'; playRequest.stage = failure.stage; playRequest.progress = 100; playRequest.message = failure.message; playRequest.suggestion = failure.suggestion; playRequest.retryable = Boolean(friendly.retryable ?? true); playRequest.diagnostics = friendly.diagnostics || {} } } finally { channelPlayLoading.value[key] = false }
  }

  const closePlayer = async () => { resetPlayRequest(); if (playStreamId.value) { try { await api.post('/api/v1/stream/stop', { app: playApp.value || 'live', stream: playStreamId.value }) } catch { /* cleanup: ignore */ } } playUrl.value = ''; playCodec.value = ''; playApp.value = ''; playStreamId.value = ''; playMode.value = 'webrtc'; playUrls.webrtc = ''; playUrls.flv = ''; playUrls.hls = ''; playUrls.raw = ''; playingChannelGbId.value = ''; playerVisible.value = false }

  const switchingStream = ref(false)
  const switchStreamType = async (targetStreamType: 'main' | 'sub') => {
    if (!playStreamId.value) { ElMessage.warning(i18n.global.t('player.noStreamPlaying')); return } // FIXED: i18n
    switchingStream.value = true
    try {
      const res = await api.post(`/api/v1/stream/play/${playStreamId.value}/switch`, null, { params: { target_stream_type: targetStreamType } })
      const data = res.data || {}
      for (const [k, v] of Object.entries(data)) { if (k !== 'codec' && k !== 'app' && k !== 'stream') (playUrls as Record<string, unknown>)[k] = normalizePlayUrl(v) }
      playCodec.value = String(data.codec || '')
      playApp.value = String(data.app || '')
      playStreamId.value = String(data.stream || '')
      const preferredFlv = pickPreferredFlv(); const preferredHls = pickPreferredHls()
      const preferredUrl = normalizePlayUrl(playUrls.preferred_url || ''); const preferredLower = preferredUrl.toLowerCase()
      const preferredMode = preferredLower.includes('/index/api/webrtc') ? 'webrtc' : preferredLower.includes('.m3u8') ? 'hls' : preferredLower.includes('.flv') ? 'flv' : ''
      playMode.value = (preferredMode as Record<string, unknown>) || (preferredFlv ? 'flv' : preferredHls ? 'hls' : playUrls.webrtc ? 'webrtc' : 'raw')
      playUrl.value = playMode.value === 'webrtc' ? pickPreferredWebrtc() : playMode.value === 'flv' ? preferredFlv : playMode.value === 'hls' ? preferredHls : normalizePlayUrl(playUrls.raw)
      ElMessage.success(targetStreamType === 'main' ? i18n.global.t('player.switchedToMain') : i18n.global.t('player.switchedToSub')) // FIXED: i18n
    } catch (e: unknown) {
      const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
    } finally {
      switchingStream.value = false
    }
  }

  return { playerVisible, playUrl, playCodec, playApp, playStreamId, playMode, playUrls, playingChannelGbId, channelPlayLoading, currentDevice, currentChannel, playRequest, playStream, closePlayer, switchingStream, switchStreamType }
}
