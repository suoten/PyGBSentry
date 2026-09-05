<template>
  <el-dialog
    v-model="dialogVisible"
    width="min(1600px, 94vw)"
    top="3vh"
    :close-on-click-modal="false"
    :destroy-on-close="true"
    :show-close="false"
    class="player-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="dialog-header">
        <div class="dialog-header__main">
          <div class="dialog-header__title-row">
            <div class="dialog-header__title">{{ titleText }}</div>
            <span class="dialog-badge" :class="isPlayback ? 'dialog-badge--danger' : 'dialog-badge--success'">{{ sceneLabel }}</span>
            <span class="dialog-badge">{{ currentPlayerLabel }}</span>
            <span class="dialog-badge dialog-badge--info">{{ currentProtocolLabel }}</span>
          </div>
          <div v-if="subtitleText" class="dialog-header__subtitle">{{ subtitleText }}</div>
          <div class="dialog-header__metrics">
            <span class="dialog-metric">
              {{ t('player.availableProtocols') }}
              <strong>{{ availableProtocolCount }}</strong>
            </span>
            <span class="dialog-metric">
              {{ t('player.currentAddress') }}
              <strong>{{ currentPlayUrl ? t('player.ready') : t('player.unavailable') }}</strong>
            </span>
            <span class="dialog-metric">
              {{ t('player.ptzTalk') }}
              <strong>{{ hasDeviceChannel ? t('player.available') : t('player.unavailable') }}</strong>
            </span>
          </div>
        </div>
        <div class="dialog-header__actions">
          <el-button size="small" class="header-btn" :type="isImmersive ? 'primary' : 'default'" @click="isImmersive = !isImmersive">
            <el-icon class="mr-1"><FullScreen /></el-icon>
            {{ isImmersive ? t('player.exitImmersive') : t('player.immersiveMode') }}
          </el-button>
          <el-button size="small" class="header-btn" @click="emit('refresh')">
            <el-icon class="mr-1"><Refresh /></el-icon>
            {{ t('player.refreshStream') }}
          </el-button>
          <el-button size="small" type="success" plain class="header-btn" :disabled="activePlayerType !== 'jessibuca' || !currentPlayUrl" @click="takeScreenshot">
            <el-icon class="mr-1"><Camera /></el-icon>
            {{ t('player.localScreenshot') }}
          </el-button>
          <el-button size="small" class="header-btn" :disabled="!currentPlayUrl" @click="openPlayUrl">
            {{ t('player.openInNewTab') }}
          </el-button>
          <el-button size="small" type="primary" class="header-btn" :disabled="!currentPlayUrl" @click="copyToClipboard(currentPlayUrl)">
            {{ t('player.copyAddress') }}
          </el-button>
          <button class="dialog-close-btn" @click="handleClose">{{ t('common.close') }}</button>
        </div>
      </div>
    </template>
    <div class="player-layout" :class="{ 'is-immersive': isImmersive }">
      <section class="player-card">
        <div class="player-toolbar">
          <div class="toolbar-left">
            <div class="toolbar-label">{{ t('player.playChannel') }}</div>
            <div class="protocol-list">
              <button
                v-for="item in playerTypeOptions"
                :key="item.value"
                class="protocol-chip"
                :class="{ 'is-active': activePlayerType === item.value, 'is-disabled': item.disabled }"
                :disabled="item.disabled"
                @click="handlePlayerTypeChange(item.value)"
              >
                {{ item.label }}
              </button>
            </div>
          </div>
          <div class="toolbar-right">
            <span class="playback-note">{{ playbackStatusText }}</span>
          </div>
        </div>
        <div v-if="webrtcHint" class="webrtc-hint">{{ webrtcHint }}</div>
        
        <div class="player-stage" :class="{ 'is-loading-stage': requestStatus !== 'ready' && !currentPlayUrl }">
          <template v-if="requestStatus !== 'ready' && !currentPlayUrl">
            <div class="skeleton-player">
              <div class="skeleton-icon">
                <el-icon v-if="requestStatus === 'error'" color="#f56c6c"><Warning /></el-icon>
                <el-icon v-else class="is-loading"><Loading /></el-icon>
              </div>
              
              <div v-if="requestStatus === 'error'" class="skeleton-error-content">
                <div class="skeleton-text text-danger">{{ requestTitle || t('player.playFailure') }}</div>
                <div class="skeleton-subtext">{{ requestMessage }}</div>
                <div v-if="requestSuggestion" class="skeleton-subtext skeleton-suggestion">{{ requestSuggestion }}</div>
                <el-button v-if="requestRetryable" size="small" type="primary" plain @click="emit('refresh')" style="margin-top: 16px;">{{ t('player.retryRequest') }}</el-button>
              </div>
              
              <div v-else class="skeleton-loading-content">
                <div class="skeleton-text">{{ requestTitle || t('player.waitingResource') }}</div>
                <el-progress 
                  class="skeleton-progress" 
                  :percentage="requestProgress" 
                  :show-text="false" 
                  :stroke-width="4"
                  status="success" 
                />
                <div class="skeleton-subtext">{{ requestMessage || titleText }}</div>
                <div v-if="requestSuggestion" class="skeleton-subtext skeleton-suggestion">{{ requestSuggestion }}</div>
              </div>
            </div>
          </template>
          <template v-else-if="activePlayerType === 'jessibuca'">
            <JessibucaPlayer
              ref="jessibucaPlayerRef"
              v-if="requestStatus !== 'ready' || hasJessibuca"
              :video-url="jessibucaUrl"
              :candidates="flvCandidates"
              :hls-url="hlsUrl"
              :codec="codec || ''"
              :request="request"
              :suggested-player="jessibucaSuggestedPlayer"
              @refresh-request="emit('refresh')"
              @suggest-switch="handleSuggestedSwitch"
              @error="handlePlayerError('jessibuca')"
            />
            <div v-else class="player-empty">{{ t('player.currentUnavailable') }}</div>
          </template>
          <template v-else-if="activePlayerType === 'h265'">
            <H265Player 
              v-if="requestStatus !== 'ready' || hasH265" 
              :h265-url="h265Url" 
              @error="handlePlayerError('h265')"
            />
            <div v-else class="player-empty">{{ t('player.h265webUnavailable') }}</div>
          </template>
          <template v-else-if="activePlayerType === 'native_hls'">
            <NativeHlsPlayer 
              v-if="requestStatus !== 'ready' || hasHlsUrl" 
              :hls-url="hlsUrl" 
              @error="handlePlayerError('native_hls')"
            />
            <div v-else class="player-empty">{{ t('player.hlsUnavailable') }}</div>
          </template>
          <template v-else-if="activePlayerType === 'webrtc'">
            <RtcPlayer 
              v-if="hasWebrtc" 
              :webrtc-url="webrtcUrl" 
              @error="handlePlayerError('webrtc')"
            />
            <div v-else class="player-empty">{{ webrtcHint || t('player.webrtcUnavailable') }}</div>
          </template>
        </div>
        <div class="stage-footer">
          <div class="stage-footer__meta">
            <span class="stage-pill">{{ currentPlayerLabel }}</span>
            <span class="stage-pill">{{ currentProtocolLabel }}</span>
            <span class="stage-pill" :class="currentPlayUrl ? 'stage-pill--success' : 'stage-pill--muted'">
              {{ currentPlayUrl ? t('player.streamUrlPrepared') : t('player.noPlayableAddress') }}
            </span>
            <span v-if="deviceStatus !== undefined" class="stage-pill" :class="deviceStatus === 1 ? 'stage-pill--success' : 'stage-pill--danger'">
              {{ t('common.device') }}{{ deviceStatus === 1 ? t('common.online') : t('common.offline') }}
            </span>
          </div>
          <div class="stage-footer__actions">
            <el-button size="small" class="header-btn" :disabled="!sharedUrl" @click="copyToClipboard(sharedUrl)">{{ t('player.copyShareLink') }}</el-button>
            <el-button size="small" class="header-btn" @click="advancedExpanded = !advancedExpanded">
              {{ advancedExpanded ? t('player.collapseAdvanced') : t('player.expandAdvanced') }}
            </el-button>
          </div>
        </div>
      </section>

      <section v-show="!isImmersive" class="tabs-card">
        <el-tabs v-model="activeTab" type="border-card" class="feature-tabs">
          <el-tab-pane :label="isPlayback ? t('player.playbackInfo') : t('player.playInfo')" name="media">
            <div class="media-box">
              <div class="media-summary">
                <div class="media-summary-card">
                  <div class="line-label">{{ t('player.mainPlayAddress') }}</div>
                  <div class="line-value">{{ currentPlayUrl || t('player.noPlayableAddressForProtocol') }}</div>
                  <div class="line-actions">
                    <el-button size="small" type="primary" plain :disabled="!currentPlayUrl" @click="copyToClipboard(currentPlayUrl)">{{ t('player.copy') }}</el-button>
                    <el-button size="small" :disabled="!currentPlayUrl" @click="openPlayUrl">{{ t('player.open') }}</el-button>
                  </div>
                </div>
                <div class="media-summary-card">
                  <div class="line-label">{{ t('player.shareLink') }}</div>
                  <div class="line-value">{{ sharedUrl || t('player.noShareAddress') }}</div>
                  <div class="line-actions">
                    <el-button size="small" type="primary" plain :disabled="!sharedUrl" @click="copyToClipboard(sharedUrl)">{{ t('player.copy') }}</el-button>
                  </div>
                </div>
              </div>
              <div class="source-grid">
                <div
                  v-for="item in protocolCards"
                  :key="item.label"
                  class="source-card"
                  :class="{
                    'source-card--disabled': !item.available,
                    'source-card--unverified': item.available && !item.verified,
                    'source-card--verified-ok': item.available && item.verified,
                  }"
                >
                  <div class="source-card__header">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.available ? t('player.available') : t('player.unavailable') }}</strong>
                    <span v-if="item.verified" class="source-card__verify source-card__verify--ok">{{ t('player.verified') }}</span>
                    <span v-else-if="item.available && !item.verified" class="source-card__verify source-card__verify--warn">{{ t('player.unverified') }}</span>
                  </div>
                  <div class="source-card__value">{{ item.value || t('player.noAddressCurrent') }}</div>
                </div>
              </div>
              <div v-if="advancedExpanded" class="advanced-info">
                <div class="line-item">
                  <div class="line-label">iframe</div>
                  <el-input :model-value="sharedIframe" readonly>
                    <template #append><el-button @click="copyToClipboard(sharedIframe)">{{ t('player.copy') }}</el-button></template>
                  </el-input>
                </div>
                <div class="line-item">
                  <div class="line-label">{{ t('player.currentPlayAddress') }}</div>
                  <el-input :model-value="currentPlayUrl" readonly>
                    <template #append><el-button @click="copyToClipboard(currentPlayUrl)">{{ t('player.copy') }}</el-button></template>
                  </el-input>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('player.ptzControl')" name="control">
            <AdvancedPtzControl v-if="hasDeviceChannel" :device-id="deviceId || ''" :channel-id="channelId || ''" />
            <el-empty v-else :image-size="56" :description="t('player.noDeviceChannelForPtz')" />
          </el-tab-pane>

          <el-tab-pane :label="t('player.videoInfo')" name="codec" :lazy="true">
            <CodecInfo ref="codecInfoRef" :app="app" :stream="stream" />
          </el-tab-pane>

          <el-tab-pane :label="t('player.voiceTalk')" name="broadcast">
            <TalkControl v-if="hasDeviceChannel" :device-id="deviceId || ''" :channel-id="channelId || ''" />
            <el-empty v-else :image-size="56" :description="t('player.noDeviceChannelForTalk')" />
          </el-tab-pane>
        </el-tabs>
      </section>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Loading, Warning, VideoCamera, FullScreen, VideoPause, Refresh, Camera } from '@element-plus/icons-vue'
import JessibucaPlayer from './JessibucaPlayer.vue'
import H265Player from './H265Player.vue'
import RtcPlayer from './RtcPlayer.vue'
import NativeHlsPlayer from './NativeHlsPlayer.vue'
import AdvancedPtzControl from './AdvancedPtzControl.vue'
import CodecInfo from './CodecInfo.vue'
import TalkControl from './TalkControl.vue'

const { t } = useI18n()

type StreamUrls = Record<string, string | undefined>
// FIX: [2026-07-10] auto-heal profile.preferredPlayer 可能返回 'hls'，
// 原联合类型缺少 'hls' 导致 TS2322 [全栈工程师]
type PlayerType = 'jessibuca' | 'h265' | 'webrtc' | 'native_hls' | 'hls'
type UrlAvailability = Record<string, boolean | null>
type PlayRequestUi = {
  status: 'idle' | 'requesting' | 'waiting' | 'ready' | 'error'
  stage?: string
  progress?: number
  message?: string
  suggestion?: string
  retryable?: boolean
  diagnostics?: Record<string, unknown>
  urlAvailability?: UrlAvailability
  hlsProbeDetail?: Record<string, unknown>
}

const props = defineProps<{
  modelValue?: boolean
  visible?: boolean
  title?: string
  subtitle?: string
  urls?: StreamUrls
  playUrl?: string
  codec?: string
  app?: string
  stream?: string
  deviceId?: string
  channelId?: string
  deviceStatus?: number
  request?: PlayRequestUi
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:visible', v: boolean): void
  (e: 'close'): void
  (e: 'refresh'): void
}>()

const activeTab = ref<'media' | 'control' | 'codec' | 'broadcast'>('media')
const activePlayerType = ref<PlayerType>('jessibuca')
type CodecInfoExpose = { fetchInfo?: () => void }

const codecInfoRef = ref<CodecInfoExpose | null>(null)
const advancedExpanded = ref(false)
const isImmersive = ref(false) // 沉浸模式开关
// SECURITY: 非敏感 UI 偏好（播放器类型偏好 jessibuca/h265/webrtc）— 仅存设备+通道→播放器类型映射，
// 不含用户身份或鉴权信息，可安全存入 localStorage 跨会话保留。读取见 getStoredPlayerType，写入见 savePlayerType。
const PLAYER_PREF_KEY = 'pygbsentry:player-pref'

type JessibucaExpose = { performScreenshot?: () => void }

const jessibucaPlayerRef = ref<JessibucaExpose | null>(null)

const takeScreenshot = () => {
  if (jessibucaPlayerRef.value && typeof jessibucaPlayerRef.value.performScreenshot === 'function') {
    jessibucaPlayerRef.value.performScreenshot()
  } else {
    ElMessage.warning(t('player.screenshotNotReady'))
  }
}

const dialogVisible = computed({
  get: () => Boolean(props.modelValue ?? props.visible ?? false),
  set: (value: boolean) => {
    emit('update:modelValue', value)
    emit('update:visible', value)
  }
})

const titleText = computed(() => props.title || t('player.liveView'))
const subtitleText = computed(() => props.subtitle || '')
const hasDeviceChannel = computed(() => !!String(props.deviceId || '').trim() && !!String(props.channelId || '').trim())
const isPlayback = computed(() => String(props.app || '').toLowerCase() === 'playback')
const sceneLabel = computed(() => (isPlayback.value ? t('player.recordPlayback') : t('player.livePreview')))

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

const normalizedUrls = computed<StreamUrls>(() => {
  const urls = props.urls || {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(urls)) {
    out[k] = normalizePlayUrl(v)
  }
  return out
})

const firstNotEmpty = (...list: Array<string | undefined>) => {
  for (const item of list) {
    const value = String(item || '').trim()
    if (value) return value
  }
  return ''
}

const webrtcUrl = computed(() => {
  const securePage = isSecurePage.value
  let candidates: string[] = []
  
  if (securePage) {
    candidates = [
      normalizedUrls.value.rtcs ?? '',
      normalizedUrls.value.webrtc ?? '',
      normalizedUrls.value.rtc ?? ''
    ]
  } else {
    candidates = [
      normalizedUrls.value.webrtc ?? '',
      normalizedUrls.value.rtc ?? '',
      normalizedUrls.value.rtcs ?? ''
    ]
  }
  
  // 过滤并处理 WHEP 端点和标准 WebRTC 地址
  for (const candidate of candidates) {
    if (!candidate) continue
    const value = String(candidate).trim()
    if (!value) continue
    
    // 检查是否是 HTTP/HTTPS 的 WHEP 端点（GB28181 通用格式）
    // 例如: http://xxx/index/api/whep?app=rtp&stream=xxx
    if (value.startsWith('http://') || value.startsWith('https://')) {
      // 对于 WHEP 端点，RtcPlayer 组件可以直接使用
      return value
    }
    
    // 标准 ws/wss WebRTC 地址
    if (value.startsWith('ws://') || value.startsWith('wss://')) {
      return value
    }
  }
  
  return ''
})
const flvUrl = computed(() => {
  const securePage = isSecurePage.value
  
  // 安全页面优先使用 HTTPS/WSS 地址
  if (securePage) {
    return firstNotEmpty(
      normalizedUrls.value.wss_flv,
      normalizedUrls.value.https_flv,
      normalizedUrls.value.ws_flv,
      normalizedUrls.value.flv
    )
  }
  
  // 非安全页面直接使用任何可用的 FLV 地址
  return firstNotEmpty(
    normalizedUrls.value.flv,
    normalizedUrls.value.ws_flv,
    normalizedUrls.value.https_flv,
    normalizedUrls.value.wss_flv
  ) || ''
})
const flvCandidates = computed(() => {
  const list: string[] = []
  const push = (v: unknown) => {
    const value = String(v || '').trim()
    if (!value) return
    if (!list.includes(value)) list.push(value)
  }
  
  // 安全页面优先使用 HTTPS/WSS 地址，非安全页面直接使用所有可用地址
  const securePage = isSecurePage.value
  
  if (securePage) {
    // HTTPS 页面：优先使用安全地址
    push(normalizedUrls.value.wss_flv)
    push(normalizedUrls.value.https_flv)
    push(normalizedUrls.value.ws_flv)
    push(normalizedUrls.value.flv)
  } else {
    // HTTP 页面：直接使用所有可用地址
    push(normalizedUrls.value.flv)
    push(normalizedUrls.value.ws_flv)
    push(normalizedUrls.value.https_flv)
    push(normalizedUrls.value.wss_flv)
  }
  
  // 如果没有找到任何 FLV 格式地址，检查是否有包含 .live.flv 的 fullUrl
  const fullUrl = props.playUrl || ''
  if (fullUrl && (fullUrl.includes('.flv') || fullUrl.includes('/live/'))) {
    const value = String(fullUrl).trim()
    if (value && !list.includes(value)) {
      list.unshift(value) // 将主播放地址放在最前面
    }
  }
  
  return list
})
const hlsUrl = computed(() =>
  isSecurePage.value
    ? firstNotEmpty(normalizedUrls.value.wss_hls, normalizedUrls.value.https_hls, normalizedUrls.value.ws_hls, normalizedUrls.value.hls)
    : firstNotEmpty(normalizedUrls.value.hls, normalizedUrls.value.ws_hls, normalizedUrls.value.https_hls, normalizedUrls.value.wss_hls)
)
const rawUrl = computed(() => String(props.playUrl || '').trim())
const webrtcHint = computed(() => firstNotEmpty(normalizedUrls.value.webrtc_hint, normalizedUrls.value.webrtc_message))

const hasWebrtc = computed(() => {
  // 如果有 ws/wss 格式的 WebRTC 地址
  const wsUrls = [
    normalizedUrls.value.webrtc,
    normalizedUrls.value.rtc,
    normalizedUrls.value.rtcs
  ].filter(Boolean)
  
  // 检查是否有任何有效的 WebRTC 相关地址
  // 包括：ws://, wss://, 以及 http://https:// 格式的 WHEP 端点
  if (!wsUrls.some(url => {
    if (!url) return false
    const value = String(url).trim()
    return value.startsWith('ws://') || 
           value.startsWith('wss://') ||
           value.startsWith('http://') || 
           value.startsWith('https://')
  })) {
    return false
  }

  // 有后端验证数据时，以验证结果为准
  const avail = props.request?.urlAvailability
  if (avail) {
    const rtcKeys = ['rtc', 'rtcs']
    return rtcKeys.some(k => avail[k] === true)
  }
  return true
})
const hasJessibuca = computed(() => {
  if (!flvUrl.value && !rawUrl.value) return false
  // 有后端验证数据时，以验证结果为准
  const avail = props.request?.urlAvailability
  if (avail) {
    const flvKeys = ['flv', 'https_flv', 'ws_flv', 'wss_flv']
    const isAvail = flvKeys.some(k => avail[k] === true)
    if (isAvail) return true
    // 如果已验证全部不可用，即使 URL 存在也不选
    const allChecked = flvKeys.every(k => avail[k] === false || avail[k] === null)
    if (allChecked && !flvUrl.value) return false
  }
  return !!(flvUrl.value || rawUrl.value)
})
const isSecurePage = computed(() => window.location.protocol === 'https:')

const jessibucaUrl = computed(() => flvUrl.value || rawUrl.value || '')
const hasSecureJessibucaCandidate = computed(() =>
  flvCandidates.value.some((item) => {
    const url = String(item || '').toLowerCase()
    return url.startsWith('https://') || url.startsWith('wss://')
  })
)
const jessibucaMixedContentRisk = computed(() => {
  if (!isSecurePage.value || !hasJessibuca.value) return false
  const url = String(jessibucaUrl.value || '').toLowerCase()
  if (!url) return false
  return (url.startsWith('http://') || url.startsWith('ws://')) && !hasSecureJessibucaCandidate.value
})
const hasH265 = computed(() => !!hlsUrl.value)
const hasHlsUrl = computed(() => {
  if (!hlsUrl.value) return false
  // 有后端验证数据时，以验证结果为准
  const avail = props.request?.urlAvailability
  if (avail) {
    const hlsKeys = ['hls', 'https_hls', 'ws_hls', 'wss_hls']
    return hlsKeys.some(k => avail[k] === true)
  }
  return !!hlsUrl.value
})
const h265Url = computed(() => hlsUrl.value || '')
const jessibucaSuggestedPlayer = computed<'h265' | 'webrtc' | ''>(() => {
  if (hasH265.value) return 'h265'
  if (hasWebrtc.value) return 'webrtc'
  return ''
})
const playerPrefStorageKey = computed(() => {
  const device = String(props.deviceId || '').trim()
  const channel = String(props.channelId || '').trim()
  if (!device || !channel) return ''
  return `${PLAYER_PREF_KEY}:${device}:${channel}`
})
const getStoredPlayerType = (): PlayerType | '' => {
  const key = playerPrefStorageKey.value
  if (!key) return ''
  try {
    const value = String(localStorage.getItem(key) || '')
    return value === 'jessibuca' || value === 'h265' || value === 'webrtc' ? value : ''
  } catch {
    return ''
  }
}
const savePlayerType = (value: PlayerType) => {
  const key = playerPrefStorageKey.value
  if (!key) return
  try {
    localStorage.setItem(key, value)
  } catch { /* cleanup: ignore */ }
}
const preflightDecision = computed<{ player?: PlayerType; reason: string }>(() => {
  if (jessibucaMixedContentRisk.value) {
    if (hasH265.value) return { player: 'h265', reason: t('player.autoAvoidBlockedFlv') }
    if (hasWebrtc.value) return { player: 'webrtc', reason: t('player.autoAvoidBlockedFlv') }
  }
  if (!hasJessibuca.value && hasH265.value) {
    return { player: 'h265', reason: t('player.autoSwitchSuitablePlayer') }
  }
  if (!hasJessibuca.value && !hasH265.value && hasWebrtc.value) {
    return { player: 'webrtc', reason: t('player.autoSwitchSuitablePlayer') }
  }
  return { reason: '' }
})

const currentPlayUrl = computed(() => {
  if (activePlayerType.value === 'webrtc') return webrtcUrl.value || ''
  if (activePlayerType.value === 'h265') return h265Url.value || ''
  if (activePlayerType.value === 'native_hls') return hlsUrl.value || ''
  return jessibucaUrl.value || ''
})
const currentProtocolLabel = computed(() => {
  if (activePlayerType.value === 'webrtc') return t('player.lowLatencyLine')
  if (activePlayerType.value === 'h265') return t('player.hdCompatLine')
  if (activePlayerType.value === 'native_hls') return t('player.hlsLine')
  const url = currentPlayUrl.value || ''
  const lower = url.toLowerCase()
  if (lower.startsWith('wss://') || lower.startsWith('ws://')) return t('player.realtimeLine')
  if (lower.startsWith('https://') || lower.startsWith('http://')) return t('player.standardLine')
  return t('player.standardLine')
})
const currentPlayerLabel = computed(() => {
  if (activePlayerType.value === 'webrtc') return 'webRtc'
  if (activePlayerType.value === 'h265') return 'H265web'
  if (activePlayerType.value === 'native_hls') return t('player.nativeHls')
  return 'Jessibuca'
})

const playerTypeOptions = computed(() => {
  const list: Array<{ label: string; value: PlayerType; disabled?: boolean }> = [
    { label: 'Jessibuca', value: 'jessibuca', disabled: false },
    { label: 'HLS', value: 'native_hls', disabled: !hasHlsUrl.value },
    { label: 'H265web', value: 'h265', disabled: !hasH265.value },
    { label: 'webRtc', value: 'webrtc', disabled: !hasWebrtc.value }
  ]
  return list
})
const protocolCards = computed(() => {
  const avail = props.request?.urlAvailability
  const flvKeys = ['flv', 'https_flv', 'ws_flv', 'wss_flv']
  const hlsKeys = ['hls', 'https_hls', 'ws_hls', 'wss_hls']
  const rtcKeys = ['rtc', 'rtcs']
  const flvAvail = avail ? flvKeys.some(k => avail[k] === true) : !!flvUrl.value
  const hlsAvail = avail ? hlsKeys.some(k => avail[k] === true) : !!hlsUrl.value
  const rtcAvail = avail ? rtcKeys.some(k => avail[k] === true) : !!webrtcUrl.value
  return [
    { label: t('player.lowLatencyLine'), value: webrtcUrl.value, available: rtcAvail, verified: avail ? rtcKeys.some(k => avail[k] !== null) : false },
    { label: t('player.standardLine'), value: flvUrl.value, available: flvAvail, verified: avail ? flvKeys.some(k => avail[k] !== null) : false },
    { label: t('player.hdLine'), value: hlsUrl.value, available: hlsAvail, verified: avail ? hlsKeys.some(k => avail[k] !== null) : false },
    { label: t('player.backupLine'), value: rawUrl.value, available: !!rawUrl.value, verified: false }
  ]
})
const availableProtocolCount = computed(() => protocolCards.value.filter((item) => item.available).length)
const playbackStatusText = computed(() => {
  if (preflightDecision.value.reason) return preflightDecision.value.reason
  const stored = getStoredPlayerType()
  if (stored && stored === activePlayerType.value) return t('player.openedByLastChoice')
  if (isPlayback.value) return t('player.playbackCanCopyShare')
  if (hasJessibuca.value) return t('player.preferredJessibuca')
  if (hasH265.value) return t('player.switchedToH265webShort')
  return t('player.switchedToWebRtcShort')
})

const requestStatus = computed(() => props.request?.status || 'idle')
const requestVisible = computed(() => requestStatus.value !== 'idle' && requestStatus.value !== 'ready')
const requestTitle = computed(() => {
  const stage = String(props.request?.stage || '').trim()
  if (stage) return stage
  if (requestStatus.value === 'requesting') return t('player.startingInvite')
  if (requestStatus.value === 'waiting') return t('player.waitingStreamReady')
  if (requestStatus.value === 'error') return t('player.playFailure')
  return t('player.inviting')
})
const requestProgress = computed(() => {
  const value = props.request?.progress
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.min(100, Math.round(value)))
  }
  return requestStatus.value === 'error' ? -1 : 0
})
const requestMessage = computed(() => String(props.request?.message || '').trim())
const requestSuggestion = computed(() => String(props.request?.suggestion || '').trim())
const requestRetryable = computed(() => Boolean(props.request?.retryable ?? true))
const autoHealProfile = computed<Record<string, unknown>>(() => {
  const diagnostics = (props.request?.diagnostics || {}) as Record<string, unknown>
  const inner = (diagnostics.diagnostics || {}) as Record<string, unknown>
  const profile = diagnostics.auto_heal_profile || inner.autoHealProfile || diagnostics.autoHealProfile || {}
  return (typeof profile === 'object' && profile ? profile : {}) as Record<string, unknown>
})
const profilePreferredPlayer = computed<PlayerType | ''>(() => {
  const player = String(autoHealProfile.value.preferredPlayer || '').trim().toLowerCase()
  if (player === 'h265') return 'h265'
  if (player === 'webrtc') return 'webrtc'
  if (player === 'jessibuca') return 'jessibuca'
  if (player === 'hls') return 'native_hls'
  return ''
})
const profilePreferStability = computed(() => Boolean(autoHealProfile.value.preferStability))
const profileMaxAutoHealAttempts = computed(() => {
  const raw = Number(autoHealProfile.value.maxAutoHealAttempts)
  if (!Number.isFinite(raw)) return 2
  return Math.max(1, Math.min(4, Math.round(raw)))
})
const profileWaitingHealMs = computed(() => {
  const raw = Number(autoHealProfile.value.waitingHealMs)
  if (!Number.isFinite(raw)) return 14000
  return Math.max(6000, Math.min(30000, Math.round(raw)))
})
const requestDiagnosticsText = computed(() => {
  const d = props.request?.diagnostics
  if (!d || typeof d !== 'object') return ''
  try {
    const payload = JSON.stringify(d, null, 2)
    return payload.length > 0 ? payload : ''
  } catch {
    return ''
  }
})

const sharedUrl = computed(() => `${window.location.origin}/#/play/${encodeURIComponent(currentPlayUrl.value)}`)
const sharedIframe = computed(() => `<iframe src="${sharedUrl.value}" width="960" height="540" frameborder="0" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin"></iframe>`)

const copyToClipboard = async (text: string) => {
  const value = String(text || '').trim()
  if (!value) {
    ElMessage.warning(t('player.noAddressToCopy'))
    return
  }
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success(t('player.copiedToClipboard'))
  } catch {
    ElMessage.error(t('player.copyFailed'))
  }
}

const openPlayUrl = () => {
  const url = String(currentPlayUrl.value || '').trim()
  if (!url) {
    ElMessage.warning(t('player.noAddressToOpen'))
    return
  }
  try {
    window.open(url, '_blank')
  } catch {
    ElMessage.error(t('player.openFailed'))
  }
}

const handleClose = () => {
  dialogVisible.value = false
  emit('close')
}

const fallbackState = ref({
  tried: new Set<PlayerType>()
})
const autoHealAttempts = ref(0)
const autoHealCooldownMs = 8000
const autoHealLastAt = ref(0)
let requestWaitingTimer: ReturnType<typeof setTimeout> | null = null

const triggerAutoHealRefresh = (reason: string) => {
  if (!dialogVisible.value) return false
  if (!['requesting', 'waiting', 'ready'].includes(requestStatus.value)) return false
  if (!requestRetryable.value) return false
  const now = Date.now()
  if (autoHealAttempts.value >= profileMaxAutoHealAttempts.value) return false
  if (now - autoHealLastAt.value < autoHealCooldownMs) return false
  autoHealAttempts.value += 1
  autoHealLastAt.value = now
  ElMessage.warning(t('player.autoHealing', { reason, current: autoHealAttempts.value, max: profileMaxAutoHealAttempts.value }))
  emit('refresh')
  return true
}

const resetRequestWaitingTimer = () => {
  if (!requestWaitingTimer) return
  clearTimeout(requestWaitingTimer)
  requestWaitingTimer = null
}

const scheduleRequestWaitingHeal = () => {
  resetRequestWaitingTimer()
  if (!dialogVisible.value) return
  if (!['requesting', 'waiting'].includes(requestStatus.value)) return
  if (!requestRetryable.value) return
  requestWaitingTimer = setTimeout(() => {
    requestWaitingTimer = null
    triggerAutoHealRefresh(t('player.mediaStreamWaitTimeout'))
  }, profileWaitingHealMs.value)
}

const handlePlayerTypeChange = (value: PlayerType) => {
  // FIX: [2026-07-03] H.265 码流选择 WebRTC 时提示兼容性风险 [全栈工程师]
  const _isHevc = String(props.codec || '').toLowerCase() === 'h265' || String(props.codec || '').toLowerCase() === 'hevc'
  if (value === 'webrtc' && _isHevc) {
    ElMessage.warning(t('player.h265WebRtcWarning'))
  }
  activePlayerType.value = value
  fallbackState.value.tried.clear()
}

const handlePlayerError = (failedPlayer: PlayerType) => {
  fallbackState.value.tried.add(failedPlayer)
  let switched = false
  
  const isHevc = String(props.codec || '').toLowerCase() === 'h265' || String(props.codec || '').toLowerCase() === 'hevc'
  
  if (isHevc) {
    if (failedPlayer === 'h265') {
      if (hasJessibuca.value && !fallbackState.value.tried.has('jessibuca')) {
        activePlayerType.value = 'jessibuca'
        ElMessage.warning(t('player.switchedToJessibuca'))
        switched = true
      } else if (hasWebrtc.value && !fallbackState.value.tried.has('webrtc')) {
        activePlayerType.value = 'webrtc'
        ElMessage.warning(t('player.h265webToWebRtc'))
        switched = true
      }
    } else if (failedPlayer === 'jessibuca') {
      if (hasWebrtc.value && !fallbackState.value.tried.has('webrtc')) {
        activePlayerType.value = 'webrtc'
        ElMessage.warning(t('player.switchedToWebRtc'))
        switched = true
      }
    }
  } else {
    if (failedPlayer === 'jessibuca') {
      if (profilePreferStability.value && hasHlsUrl.value && !fallbackState.value.tried.has('native_hls')) {
        activePlayerType.value = 'native_hls'
        ElMessage.warning(t('player.switchedToHls'))
        switched = true
      } else if (hasWebrtc.value && !fallbackState.value.tried.has('webrtc')) {
        activePlayerType.value = 'webrtc'
        ElMessage.warning(t('player.switchedToWebRtc'))
        switched = true
      } else if (hasH265.value && !fallbackState.value.tried.has('h265')) {
        activePlayerType.value = 'h265'
        ElMessage.warning(t('player.switchedToH265web'))
      }
    } else if (failedPlayer === 'webrtc') {
      if (hasHlsUrl.value && !fallbackState.value.tried.has('native_hls')) {
        activePlayerType.value = 'native_hls'
        ElMessage.warning(t('player.webRtcToHls'))
        switched = true
      } else if (hasH265.value && !fallbackState.value.tried.has('h265')) {
        activePlayerType.value = 'h265'
        ElMessage.warning(t('player.webRtcToH265web'))
      }
    } else if (failedPlayer === 'native_hls') {
      if (hasJessibuca.value && !fallbackState.value.tried.has('jessibuca')) {
        activePlayerType.value = 'jessibuca'
        ElMessage.warning(t('player.hlsToJessibuca'))
        switched = true
      } else if (hasWebrtc.value && !fallbackState.value.tried.has('webrtc')) {
        activePlayerType.value = 'webrtc'
        ElMessage.warning(t('player.hlsToWebRtc'))
        switched = true
      } else if (hasH265.value && !fallbackState.value.tried.has('h265')) {
        activePlayerType.value = 'h265'
        ElMessage.warning(t('player.hlsToH265web'))
      }
    }
  }
  if (!switched) {
    triggerAutoHealRefresh(t('player.persistentPlaybackError'))
  }
}

const handleSuggestedSwitch = (player: 'h265' | 'webrtc') => {
  handlePlayerError('jessibuca') // Reuse the fallback logic by treating this as jessibuca error
}

const selectPreferredPlayer = () => {
  if (!webrtcUrl.value && !hlsUrl.value && !flvUrl.value && !rawUrl.value) {
    activePlayerType.value = 'jessibuca'
    return
  }

  if (preflightDecision.value.player) {
    activePlayerType.value = preflightDecision.value.player
    return
  }
  if (profilePreferredPlayer.value) {
    const option = playerTypeOptions.value.find((item) => item.value === profilePreferredPlayer.value)
    if (option && !option.disabled) {
      activePlayerType.value = profilePreferredPlayer.value
      return
    }
  }
  const stored = getStoredPlayerType()
  if (stored) {
    const option = playerTypeOptions.value.find((item) => item.value === stored)
    if (option && !option.disabled) {
      activePlayerType.value = stored
      return
    }
  }

  const mainPlayUrl = String(props.playUrl || '').toLowerCase()
  const isFlvPreferred = mainPlayUrl.includes('.flv') || mainPlayUrl.includes('/live/')
  const isHlsPreferred = mainPlayUrl.includes('.m3u8') || mainPlayUrl.includes('/hls/')

  if (isFlvPreferred && hasJessibuca.value) {
    activePlayerType.value = 'jessibuca'
    return
  }
  if (hasJessibuca.value) {
    activePlayerType.value = 'jessibuca'
    return
  }
  if (hasHlsUrl.value || isHlsPreferred) {
    activePlayerType.value = 'native_hls'
    return
  }
  if (hasH265.value) {
    activePlayerType.value = 'h265'
    return
  }

  activePlayerType.value = 'jessibuca'
}

watch(
  () => [activePlayerType.value, dialogVisible.value] as const,
  ([player, visible]) => {
    if (!visible) return
    savePlayerType(player)
  }
)

watch(
  () => [
    hasWebrtc.value,
    hasJessibuca.value,
    hasH265.value,
    String(props.codec || '').toLowerCase(),
    String(props.app || '').toLowerCase(),
    dialogVisible.value
  ],
  ([, , , , , visible]) => {
    if (!visible) return
    selectPreferredPlayer()
  },
  { immediate: true }
)

watch(
  () => dialogVisible.value,
  (visible) => {
    if (!visible) {
      resetRequestWaitingTimer()
      return
    }
    advancedExpanded.value = false
    activeTab.value = 'media'
    fallbackState.value.tried.clear()
    autoHealAttempts.value = 0
    autoHealLastAt.value = 0
    scheduleRequestWaitingHeal()
  }
)

watch(
  () => requestStatus.value,
  (status) => {
    if (status === 'ready' || status === 'requesting') {
      fallbackState.value.tried.clear()
    }
    if (status === 'ready') {
      autoHealAttempts.value = 0
    }
    if (status === 'ready' || status === 'error' || status === 'idle') {
      resetRequestWaitingTimer()
    } else {
      scheduleRequestWaitingHeal()
    }
  }
)

watch(
  () => requestRetryable.value,
  () => {
    if (!requestRetryable.value) {
      resetRequestWaitingTimer()
      return
    }
    scheduleRequestWaitingHeal()
  }
)

watch(
  () => activeTab.value,
  (tab) => {
    if (tab === 'codec' && codecInfoRef.value?.fetchInfo) {
      codecInfoRef.value.fetchInfo()
    }
  }
)
</script>

<style scoped>
.player-dialog :deep(.el-dialog) {
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16);
}

.player-dialog :deep(.el-dialog__header) {
  padding: 14px 18px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}

.player-dialog :deep(.el-dialog__body) {
  padding: 14px;
  background: #f8fafc;
}

.dialog-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.dialog-header__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dialog-header__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.dialog-header__title {
  font-size: 20px;
  line-height: 1.2;
  font-weight: 700;
  color: #0f172a;
}

.dialog-header__subtitle {
  font-size: 13px;
  color: #64748b;
}

.dialog-header__metrics,
.dialog-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.dialog-badge,
.dialog-metric {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.dialog-badge--success {
  border-color: #a7f3d0;
  background: #ecfdf5;
  color: #047857;
}

.dialog-badge--danger {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.dialog-badge--info {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.dialog-metric strong {
  color: #0f172a;
}

.header-btn {
  border-radius: 6px;
}

.dialog-close-btn {
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 6px;
  background: #0f172a;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.player-layout {
  display: grid;
  /* FIX [2026-09-04]: 视频区占满剩余宽度，侧栏定宽 340px（原 0.9fr 在宽屏上被拉得过宽） */
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 12px;
  transition: all 0.3s ease;
}

.player-layout.is-immersive {
  grid-template-columns: 1fr;
}

.player-layout.is-immersive .player-stage {
  height: min(82vh, 900px);
  aspect-ratio: auto;
  max-height: none;
}

.request-banner {
  margin: 0 18px 12px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.request-banner--error {
  border-color: #fecaca;
  background: linear-gradient(180deg, #fef2f2 0%, #ffffff 100%);
}

.request-banner__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.request-banner__title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.request-banner__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.request-banner__progress {
  margin-top: 10px;
}

.request-banner__hint {
  margin-top: 8px;
  font-size: 12px;
  color: #334155;
  line-height: 1.5;
}

.request-banner__hint--sub {
  color: #64748b;
}

.player-card,
.tabs-card {
  border: 1px solid #dbe2ea;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 10px 32px rgba(15, 23, 42, 0.06);
}

.player-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid #e2e8f0;
}

.toolbar-left {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toolbar-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.protocol-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.playback-note {
  font-size: 12px;
  color: #64748b;
}

.protocol-chip {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid #dbe2ea;
  border-radius: 9999px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.protocol-chip.is-active {
  border-color: #60a5fa;
  background: #eff6ff;
  color: #1d4ed8;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.12);
}

.protocol-chip.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.player-stage {
  /* FIX [2026-09-04]: 原固定高度 min(62vh, 620px) 在 16:9 画面下方留出大片黑底。
     改为随宽度按 16:9 自适应、仅用 max-height 封顶，画面上下左右不再留白。 */
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: min(66vh, 700px);
  min-height: 280px;
  background: #000;
  border-radius: 0;
  overflow: hidden;
  position: relative;
}

.is-loading-stage {
  background: #1e293b;
}

.skeleton-player {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  color: #fff;
  animation: pulse-bg 2s infinite ease-in-out;
}

@keyframes pulse-bg {
  0% { opacity: 0.8; }
  50% { opacity: 1; }
  100% { opacity: 0.8; }
}

.skeleton-icon {
  font-size: 48px;
  color: #3b82f6;
  margin-bottom: 16px;
  animation: bounce 2s infinite;
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.skeleton-loading-content, .skeleton-error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  max-width: 80%;
}

.skeleton-progress {
  width: 200px;
  margin: 12px 0;
}

.skeleton-text {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  letter-spacing: 1px;
}

.skeleton-subtext {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 4px;
}

.skeleton-suggestion {
  font-size: 12px;
  opacity: 0.8;
}

.player-empty {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 13px;
}

.stage-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px 18px;
}

.stage-footer__meta,
.stage-footer__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.stage-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 9999px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.stage-pill--success {
  background: #ecfdf5;
  color: #047857;
}

.stage-pill--muted {
  background: #f8fafc;
  color: #94a3b8;
}

.tabs-card {
  padding: 10px;
}

.feature-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}

.feature-tabs :deep(.el-tabs__nav-wrap) {
  border-radius: 6px;
}

.feature-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  font-weight: 600;
}

.media-box {
  display: grid;
  gap: 14px;
}

.media-summary {
  display: grid;
  gap: 12px;
}

.media-summary-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.line-value {
  color: #0f172a;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.line-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.source-card {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 14px;
  background: #f8fbff;
}

.source-card--disabled {
  border-color: #e2e8f0;
  background: #f8fafc;
}

.source-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  flex-wrap: wrap;
}

.source-card__header strong {
  color: #2563eb;
}

.source-card--disabled .source-card__header strong {
  color: #94a3b8;
}

.source-card__verify {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 4px;
}

.source-card__verify--ok {
  background: #dcfce7;
  color: #166534;
}

.source-card__verify--warn {
  background: #fef3c7;
  color: #92400e;
}

.source-card--unverified {
  border-color: #fbbf24;
}

.source-card--verified-ok {
  border-color: #86efac;
}

.source-card__value {
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
  word-break: break-all;
}

.advanced-info {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px dashed #cbd5e1;
  border-radius: 14px;
  background: #fff;
}

.line-item {
  display: grid;
  gap: 6px;
}

.line-label {
  font-size: 13px;
  color: #606266;
}

.webrtc-hint {
  margin: 8px 18px 0;
  padding: 10px 12px;
  border: 1px solid #fde68a;
  border-radius: 12px;
  background: #fffbeb;
  color: #b45309;
  font-size: 12px;
}

@media (max-width: 1080px) {
  .player-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .player-dialog :deep(.el-dialog) {
    width: 96vw !important;
    margin-top: 2vh;
  }

  .dialog-header,
  .player-toolbar,
  .stage-footer {
    align-items: flex-start;
  }

  .source-grid {
    grid-template-columns: 1fr;
  }
}
</style>
