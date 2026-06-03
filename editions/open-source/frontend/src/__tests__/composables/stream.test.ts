import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useStreamUrls } from '@/composables/useStreamUrls'
import { useAutoHeal } from '@/composables/useAutoHeal'

describe('useStreamUrls', () => {
  it('normalizes quoted URLs', () => {
    const urls = ref({ flv_url: '"http://example.com/live.flv"' })
    const playUrl = ref(undefined)
    const codec = ref(undefined)
    const { flvUrl } = useStreamUrls(urls, playUrl, codec)
    expect(flvUrl.value).toBe('http://example.com/live.flv')
  })

  it('returns empty for missing URLs', () => {
    const urls = ref({})
    const playUrl = ref(undefined)
    const codec = ref(undefined)
    const { webrtcUrl, flvUrl, hlsUrl } = useStreamUrls(urls, playUrl, codec)
    expect(webrtcUrl.value).toBe('')
    expect(flvUrl.value).toBe('')
    expect(hlsUrl.value).toBe('')
  })

  it('detects hasWebrtc correctly', () => {
    const urls = ref({ webrtc_url: 'ws://host/webrtc/1' })
    const playUrl = ref(undefined)
    const codec = ref(undefined)
    const { hasWebrtc } = useStreamUrls(urls, playUrl, codec)
    expect(hasWebrtc.value).toBe(true)
  })

  it('adds type=play to WHEP endpoints', () => {
    const urls = ref({ webrtc_url: 'ws://host/webrtc/1' })
    const playUrl = ref(undefined)
    const codec = ref(undefined)
    const { webrtcUrl } = useStreamUrls(urls, playUrl, codec)
    expect(webrtcUrl.value).toContain('type=play')
  })

  it('detects H265 from codec string', () => {
    const urls = ref({})
    const playUrl = ref(undefined)
    const codec = ref('H265')
    const { hasH265 } = useStreamUrls(urls, playUrl, codec)
    expect(hasH265.value).toBe(true)
  })
})

describe('useAutoHeal', () => {
  it('initial state allows auto heal', () => {
    const { canAutoHeal, autoHealAttempts, maxAutoHealAttempts } = useAutoHeal()
    expect(canAutoHeal()).toBe(true)
    expect(autoHealAttempts.value).toBe(0)
  })

  it('recordFallback increments attempts', () => {
    const { recordFallback, autoHealAttempts, hasTried } = useAutoHeal()
    recordFallback('webrtc')
    expect(autoHealAttempts.value).toBe(1)
    expect(hasTried('webrtc')).toBe(true)
    expect(hasTried('jessibuca')).toBe(false)
  })

  it('resetAutoHeal clears state', () => {
    const { recordFallback, autoHealAttempts, resetAutoHeal, hasTried } = useAutoHeal()
    recordFallback('webrtc')
    recordFallback('jessibuca')
    resetAutoHeal()
    expect(autoHealAttempts.value).toBe(0)
    expect(hasTried('webrtc')).toBe(false)
  })

  it('respects max attempts', () => {
    const { recordFallback, autoHealAttempts, canAutoHeal, maxAutoHealAttempts } = useAutoHeal()
    for (let i = 0; i < maxAutoHealAttempts; i++) {
      recordFallback(`player_${i}`)
    }
    expect(canAutoHeal()).toBe(false)
  })
})
