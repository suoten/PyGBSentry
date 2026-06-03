import { computed } from 'vue'
import type { Ref } from 'vue'

interface StreamUrls {
  webrtc_url?: string
  flv_url?: string
  hls_url?: string
  ws_flv_url?: string
  jessibuca_url?: string
  raw_url?: string
  [key: string]: unknown
}

/**
 * 流地址规范化与派生计算
 * 从 props.urls / props.playUrl 中提取各协议可用地址
 */
export function useStreamUrls(
  urls: Ref<StreamUrls | undefined>,
  playUrl: Ref<string | undefined>,
  codec: Ref<string | undefined>,
) {
  const normalizePlayUrl = (url: string | undefined | null): string => {
    if (!url) return ''
    let u = url.trim()
    if ((u.startsWith('"') && u.endsWith('"')) || (u.startsWith("'") && u.endsWith("'"))) {
      u = u.slice(1, -1)
    }
    return u
  }

  const isSecurePage = computed(() => typeof window !== 'undefined' && window.location.protocol === 'https:')

  const webrtcUrl = computed(() => {
    const raw = normalizePlayUrl(urls.value?.webrtc_url || '')
    if (!raw) return ''
    // WHEP 端点支持
    if (raw.includes('/webrtc/') && !raw.includes('type=play')) {
      const sep = raw.includes('?') ? '&' : '?'
      return raw + sep + 'type=play'
    }
    return raw
  })

  const flvUrl = computed(() => {
    if (isSecurePage.value) {
      return normalizePlayUrl(urls.value?.ws_flv_url || urls.value?.flv_url || '')
    }
    return normalizePlayUrl(urls.value?.flv_url || '')
  })

  const hlsUrl = computed(() => normalizePlayUrl(urls.value?.hls_url || ''))
  const rawUrl = computed(() => normalizePlayUrl(playUrl.value || ''))
  const jessibucaUrl = computed(() => normalizePlayUrl(urls.value?.jessibuca_url || urls.value?.ws_flv_url || ''))

  const hasWebrtc = computed(() => !!webrtcUrl.value)
  const hasJessibuca = computed(() => !!jessibucaUrl.value)
  const hasHlsUrl = computed(() => !!hlsUrl.value)
  const hasH265 = computed(() => (codec.value || '').toLowerCase().includes('h265') || (codec.value || '').toLowerCase().includes('hevc'))
  const h265Url = computed(() => jessibucaUrl.value || '')

  const jessibucaMixedContentRisk = computed(() => isSecurePage.value && jessibucaUrl.value && jessibucaUrl.value.startsWith('ws://'))

  const webrtcHint = computed(() => {
    if (!hasWebrtc.value) return ''
    if (isSecurePage.value && webrtcUrl.value.startsWith('ws://')) return '当前为 HTTPS 页面，WebRTC (ws://) 可能被浏览器阻止'
    return ''
  })

  return {
    normalizePlayUrl,
    isSecurePage,
    webrtcUrl,
    flvUrl,
    hlsUrl,
    rawUrl,
    jessibucaUrl,
    h265Url,
    hasWebrtc,
    hasJessibuca,
    hasHlsUrl,
    hasH265,
    jessibucaMixedContentRisk,
    webrtcHint,
  }
}
