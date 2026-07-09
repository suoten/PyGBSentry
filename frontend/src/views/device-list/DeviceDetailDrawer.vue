<template>
  <DeviceChannelWorkspaceDialog
    v-model="dialogVisibleModel"
    :current-device="currentDevice"
    :current-channel="currentChannel"
    :channel-total="channelTotal"
    :channel-online-total="channelOnlineTotal"
    :channel-filters="channelFilters"
    :channel-stream-reset="channelStreamReset"
    :refreshing-snapshots="refreshingSnapshots"
    :channels="channels"
    :channel-snap-reload-token="channelSnapReloadToken"
    :channels-loading="channelsLoading"
    :player-visible="playerVisible"
    :channel-inline-saving="channelInlineSaving"
    :channel-page="channelPage"
    :channel-page-size="channelPageSize"
    :play-tooltip="playTooltip"
    :can-preview-channel="canPreviewChannel"
    :get-channel-preview-status="getChannelPreviewStatus"
    :channel-stream-status-loading="channelStreamStatusLoading"
    :play-stream="playStream"
    :close-player="closePlayer"
    :load-channels-dialog="loadChannelsDialog"
    :reset-channel-dialog-filters="resetChannelDialogFilters"
    :refresh-channel-snapshots="refreshChannelSnapshots"
    :get-channel-row-class-name="getChannelRowClassName"
    :get-channel-snap-src="getChannelSnapSrc"
    :get-resource-type-label="getResourceTypeLabel"
    :get-resource-type-tag-type="getResourceTypeTagType"
    :get-ptz-type-tag-type="getPtzTypeTagType"
    :get-ptz-type-label="getPtzTypeLabel"
    :save-channel-audio-inline="saveChannelAudioInline"
    :save-channel-stream-type-inline="saveChannelStreamTypeInline"
    :open-channel-edit="openChannelEdit"
    :handle-record-menu-command="handleRecordMenuCommand"
    :can-play="canPlay"
    :reset-visible-channels-stream-type="resetVisibleChannelsStreamType"
    :on-closed="handleChannelsDialogClosed"
    @update:channel-stream-reset="(v) => { emit('update:channelStreamReset', v) }"
    @update:channel-page="(v) => { emit('update:channelPage', v) }"
    @update:channel-page-size="(v) => { emit('update:channelPageSize', v) }"
    @update:channel-filters="(v) => { channelFilters.value = v }"
  />

  <CloudRecordWorkspaceDialog
    v-model:visible="cloudRecordDialogVisible"
    :device-id="String(currentDevice?.gb_id || '')"
    :device-name="String(currentDevice?.name || '')"
    :channels="recordChannelOptions"
    :channel-gb-id="recordDialogChannelGbId"
    :window-minutes="recordWindowMinutes"
    :anchor-at="recordAnchorAt"
    @update:channel-gb-id="onRecordDialogChannelChange"
    @update:window-minutes="onRecordWindowChange"
    @update:anchor-at="onRecordAnchorChange"
    @play="handleRecordPlay"
  />
  <DeviceRecordWorkspaceDialog
    v-model:visible="deviceRecordDialogVisible"
    :device-id="String(currentDevice?.gb_id || '')"
    :device-name="String(currentDevice?.name || '')"
    :channels="recordChannelOptions"
    :channel-gb-id="recordDialogChannelGbId"
    :window-minutes="recordWindowMinutes"
    :anchor-at="recordAnchorAt"
    @update:channel-gb-id="onRecordDialogChannelChange"
    @update:window-minutes="onRecordWindowChange"
    @update:anchor-at="onRecordAnchorChange"
    @play="handleRecordPlay"
  />
  <TimelineRecordWorkspaceDialog
    v-model:visible="timelineRecordDialogVisible"
    :device-id="String(currentDevice?.gb_id || '')"
    :device-name="String(currentDevice?.name || '')"
    :channels="recordChannelOptions"
    :channel-gb-id="recordDialogChannelGbId"
    :window-minutes="recordWindowMinutes"
    :anchor-at="recordAnchorAt"
    @update:channel-gb-id="onRecordDialogChannelChange"
    @update:window-minutes="onRecordWindowChange"
    @update:anchor-at="onRecordAnchorChange"
    @play="handleRecordPlay"
  />

  <ChannelEditDialog
    v-model:visible="channelEditDialogVisible"
    :channel-data="channelEditData"
    @success="loadChannelsDialog"
  />

  <ChannelPlayerDialog
    v-model:visible="playerVisibleModel"
    :device-id="currentDevice?.gb_id"
    :channel-id="currentChannel?.gb_id"
    :device-name="currentDevice?.name"
    :channel-name="currentChannel?.name"
    :device-status="currentDevice?.status"
  />
  <StreamPlayerDialog
    v-model="recordPlaybackVisible"
    width="84vw"
    :title="t('device.videoPlayback')"
    :subtitle="recordPlaybackSubtitle"
    :urls="recordPlaybackUrls"
    :play-url="recordPlaybackPlayUrl"
    :mode="recordPlaybackMode"
    :codec="recordPlaybackCodec"
  />
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import ChannelEditDialog from '../../components/channel/ChannelEditDialog.vue'
import ChannelPlayerDialog from '../../components/channel/ChannelPlayerDialog.vue'
import DeviceChannelWorkspaceDialog from '../../components/channel/DeviceChannelWorkspaceDialog.vue'
import CloudRecordWorkspaceDialog from '../../components/CloudRecordWorkspaceDialog.vue'
import DeviceRecordWorkspaceDialog from '../../components/DeviceRecordWorkspaceDialog.vue'
import TimelineRecordWorkspaceDialog from '../../components/TimelineRecordWorkspaceDialog.vue'
import StreamPlayerDialog from '../../components/StreamPlayerDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'
import { parseDeviceChannelsResponse } from '../../utils/deviceApi'
import type { Device } from '@/types/models'

const { t } = useI18n()

const props = defineProps<{
  currentDevice: Device | null
  currentChannel: Device | null
  dialogVisible: boolean
  playerVisible: boolean
  channelStreamReset: string
  channelPage: number
  channelPageSize: number
  devices: Device[]
}>()

const emit = defineEmits<{
  (e: 'update:dialogVisible', value: boolean): void
  (e: 'update:playerVisible', value: boolean): void
  (e: 'update:currentChannel', value: Device | null): void
  (e: 'update:channelStreamReset', value: string): void
  (e: 'update:channelPage', value: number): void
  (e: 'update:channelPageSize', value: number): void
  (e: 'fetchDevices'): void
}>()

// Two-way bindings for props
const dialogVisibleModel = computed({ get: () => props.dialogVisible, set: (v) => emit('update:dialogVisible', v) })
const playerVisibleModel = computed({ get: () => props.playerVisible, set: (v) => emit('update:playerVisible', v) })

// ━━ 频道列表状态 ━━
const channels = ref<Device[]>([])
const channelsLoading = ref(false)
const channelTotal = ref(0)
const channelOnlineTotal = ref(0)
const channelFilters = ref<{ keyword: string; status?: number; resource_type?: number }>({
  keyword: '',
  status: undefined,
  resource_type: undefined
})
const channelEditDialogVisible = ref(false)
const channelEditData = ref<Device>(null)
const channelInlineSaving = ref<Record<string, boolean>>({})
const channelSnapReloadToken = ref<number>(Date.now())
const openChannelEdit = (row: Record<string, unknown>) => {
  channelEditData.value = { ...row }
  channelEditDialogVisible.value = true
}
const refreshingSnapshots = ref(false)

// ━━ 录像回放状态 ━━
const cloudRecordDialogVisible = ref(false)
const deviceRecordDialogVisible = ref(false)
const timelineRecordDialogVisible = ref(false)
const recordPlaybackVisible = ref(false)
const recordPlaybackMode = ref<'webrtc' | 'flv' | 'hls' | 'raw'>('raw')
const recordPlaybackCodec = ref('')
const recordPlaybackPlayUrl = ref('')
const recordPlaybackSubtitle = ref('')
const recordPlaybackUrls = reactive<{ webrtc?: string; flv?: string; hls?: string; raw?: string }>({
  webrtc: '',
  flv: '',
  hls: '',
  raw: ''
})
const recordChannelOptions = ref<Device[]>([])
const recordDialogChannelGbId = ref('')
const recordWindowMinutes = ref<number>(30)
const recordAnchorAt = ref<string>('')

// ━━ 播放状态 ━━
const playSeq = ref(0)
const playSessionId = ref('')
const playRequest = ref<Device>(null)
const playStreamId = ref('')
const playApp = ref('live')
const playUrl = ref('')
const playCodec = ref('')
const playUrls = reactive<{ webrtc: string; flv: string; hls: string; raw: string }>({
  webrtc: '',
  flv: '',
  hls: '',
  raw: ''
})
const playDiag = reactive({
  zlm_probe_ok: false,
  zlm_stream_ready: false,
  invite_sdp_ip: '',
  invite_media_port: null as null | number,
  invite_media_protocol: '',
  rtp_port_range: ''
})
const playMode = ref<'webrtc' | 'flv' | 'hls' | 'raw'>('flv')
const playbackPaused = ref(false)
const playbackSpeed = ref<number>(1)
const playbackSeekAt = ref<Date | null>(null)
const playbackActionLoading = ref(false)
// FIX: [2026-07-03] 增加 16x 倍速选项 [全栈工程师]
const playbackSpeedOptions = [0.25, 0.5, 1, 2, 4, 8, 16]
const playbackCursorSec = ref<number | null>(null)

// ━━ 流状态缓存 ━━
const channelStreamStatusCache = ref<Record<string, Record<string, unknown>>>({})
const channelStreamStatusLoading = ref(false)

const loadChannelStreamStatus = async (channelList: Record<string, unknown>[]) => {
  if (!channelList || !channelList.length) return
  const ids = channelList.map((c: Record<string, unknown>) => String(c?.id || c?.gb_id || '')).filter(Boolean)
  if (!ids.length) return
  channelStreamStatusLoading.value = true
  try {
    const res = await api.get('/api/common/channel/stream-status', {
      params: { ids: ids.join(',') },
      timeout: 10000,
    })
    const data = res.data?.channels || []
    const newCache: Record<string, Record<string, unknown>> = {}
    for (const item of data) {
      if (item.resourceId) newCache[String(item.resourceId)] = item
      if (item.channelGbId) newCache[String(item.channelGbId)] = item
      if (item.channelId != null) newCache[String(item.channelId)] = item
    }
    channelStreamStatusCache.value = { ...channelStreamStatusCache.value, ...newCache }
  } catch {
    //  ━━ 流状态检查不影响通道列表显示 ━━
  } finally {
    channelStreamStatusLoading.value = false
  }
}

const _lookupStreamStatus = (row: Record<string, unknown>): Record<string, unknown> => {
  const cache = channelStreamStatusCache.value
  const keys = [String(row?.id || ''), String(row?.gb_id || '')].filter(Boolean)
  for (const k of keys) {
    if (cache[k]) return cache[k]
  }
  return null
}

const getChannelPreviewStatus = (row: Record<string, unknown>) => {
  const cache = channelStreamStatusCache.value
  const keys = [String(row?.id || ''), String(row?.gb_id || '')].filter(Boolean)
  let status: Record<string, unknown> | null = null
  for (const k of keys) {
    if (cache[k]) { status = cache[k]; break }
  }
  if (!status) return { label: t('common.unknown'), type: 'info', icon: 'InfoFilled' }
  if (status.streamActive && status.hasVideo) {
    return { label: t('common.online'), type: 'success', icon: 'VideoPlay' }
  }
  if (status.streamActive && !status.hasVideo) {
    return { label: t('device.audioOnly'), type: 'warning', icon: 'Microphone' }
  }
  if (!status.streamActive && status.hasVideo === false) {
    return { label: t('common.offline'), type: 'danger', icon: 'CloseBold' }
  }
  if (!status.streamActive && status.reason === 'no_active_stream') {
    return { label: t('device.noActiveStream'), type: 'default', icon: 'VideoPlay' }
  }
  if (!status.streamActive) {
    return { label: t('device.unknownStatus'), type: 'warning', icon: 'Warning' }
  }
  return { label: t('device.noStream'), type: 'info', icon: 'InfoFilled' }
}

const canPreviewChannel = (row: Record<string, unknown>) => {
  if (Number(row?.status) !== 1) return false
  if (row?.hasVideo === false) return false
  const ss = _lookupStreamStatus(row)
  if (ss && ss.streamActive === false && ss.hasVideo === false) return false
  return true
}

const playTooltip = (row: Record<string, unknown>) => {
  const ss = _lookupStreamStatus(row)
  if (!ss) return t('device.streamStatusNotFetched')
  if (ss.streamActive && ss.hasVideo) return t('device.channelLiveVideo')
  if (ss.streamActive && !ss.hasVideo) return t('device.audioOnlyTip')
  if (ss.hasVideo === false) return t('device.channelNoVideo')
  if (ss.reason === 'zlm_unreachable') return t('device.mediaServerUnreachable')
  if (ss.reason === 'stream_not_found_in_zlm') return t('device.channelNotFoundInMedia')
  return t('device.onlineChannelPreviewable')
}

// ━━ 频道加载 ━━
const loadChannelsDialog = async () => {
  const gbId = String(props.currentDevice?.gb_id || '').trim()
  if (!gbId) {
    channels.value = []
    channelTotal.value = 0
    return
  }
  channelsLoading.value = true
  try {
    const res = await api.get(`/api/v1/devices/${gbId}/channels`, { params: { limit: 10000 } })
    const all = parseDeviceChannelsResponse(res.data)
    const keyword = String(channelFilters.value.keyword || '').trim().toLowerCase()
    const status = channelFilters.value.status
    const resourceType = channelFilters.value.resource_type
    const filtered = all.filter((item: Record<string, unknown>) => {
      if (keyword) {
        const gb = String(item?.gb_id || '').toLowerCase()
        const name = String(item?.name || '').toLowerCase()
        if (!gb.includes(keyword) && !name.includes(keyword)) return false
      }
      if (status !== undefined && status !== null && Number(item?.status) !== Number(status)) return false
      if (resourceType !== undefined && resourceType !== null && Number(item?.resource_type) !== Number(resourceType)) return false
      return true
    })
    recordChannelOptions.value = filtered
    if (recordDialogChannelGbId.value) {
      const matched = filtered.some((item: Record<string, unknown>) => String(item?.gb_id || item?.id || '').trim() === recordDialogChannelGbId.value)
      if (!matched) {
        recordDialogChannelGbId.value = filtered.length ? String(filtered[0]?.gb_id || filtered[0]?.id || '') : ''
      }
    }
    channelTotal.value = filtered.length
    channelOnlineTotal.value = filtered.filter((item: Record<string, unknown>) => Number(item?.status) === 1).length
    const start = (Number(props.channelPage) - 1) * Number(props.channelPageSize)
    channels.value = filtered.slice(start, start + Number(props.channelPageSize))
    await loadChannelStreamStatus(channels.value)
  } catch (e: unknown) {
    channels.value = []
    recordChannelOptions.value = []
    recordDialogChannelGbId.value = ''
    channelTotal.value = 0
    channelOnlineTotal.value = 0
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}，${friendly.suggestion}` : friendly.message)
  } finally {
    channelsLoading.value = false
  }
}

// ━━ 录像回放常用 ━━
const toRecordAnchorValue = (date: Date) => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${y}-${m}-${d}T${hh}:${mm}:${ss}`
}

const onRecordWindowChange = (value: number) => {
  recordWindowMinutes.value = Math.max(1, Number(value || 30))
}
const onRecordAnchorChange = (value: string) => {
  const text = String(value || '').trim()
  recordAnchorAt.value = text || toRecordAnchorValue(new Date())
}

const inferRecordUrls = (payload: Record<string, unknown>) => {
  const input = payload?.urls || {}
  const raw = String(input?.raw || '').trim()
  let webrtc = String(input?.webrtc || '').trim()
  let flv = String(input?.flv || '').trim()
  let hls = String(input?.hls || '').trim()

  if (raw) {
    const lower = raw.toLowerCase()
    if (!webrtc && lower.includes('/index/api/webrtc')) webrtc = raw
    if (!hls && /\.m3u8(?:\?|$)/i.test(raw)) hls = raw
    if (!flv && /\.flv(?:\?|$)/i.test(raw)) flv = raw
  }

  return { raw, webrtc, flv, hls }
}

const handleRecordPlay = (payload: Record<string, unknown>) => {
  const { raw, webrtc, flv, hls } = inferRecordUrls(payload)
  const direct = String(webrtc || flv || hls || raw).trim()
  if (!direct) {
    ElMessage.warning(t('device.noPlayableAddress'))
    return
  }
  recordPlaybackUrls.raw = raw
  recordPlaybackUrls.webrtc = webrtc
  recordPlaybackUrls.flv = flv
  recordPlaybackUrls.hls = hls
  recordPlaybackPlayUrl.value = direct
  recordPlaybackCodec.value = String(payload?.codec || '')
  recordPlaybackMode.value = webrtc ? 'webrtc' : flv ? 'flv' : hls ? 'hls' : 'raw'
  const deviceName = String(props.currentDevice?.name || props.currentDevice?.gb_id || t('device.unknownDevice'))
  const channelName = String(props.currentChannel?.name || props.currentChannel?.gb_id || t('device.unknownChannel'))
  recordPlaybackSubtitle.value = `${deviceName} / ${channelName}`
  recordPlaybackVisible.value = true
}

// ━━ 播放流 ━━
const playStream = async (row: Record<string, unknown>) => {
  if (!row?.gb_id || !props.currentDevice?.gb_id) return
  emit('update:currentChannel', row)
  emit('update:playerVisible', true)
}

const closePlayer = async () => {
  playSeq.value += 1
  playSessionId.value = ''
  playRequest.value = null
  if (playStreamId.value) {
    try {
      await api.post('/api/v1/stream/stop', { app: playApp.value || 'live', stream: playStreamId.value })
    } catch { /* cleanup: ignore */ }
  }
  playUrl.value = ''
  playCodec.value = ''
  playUrls.webrtc = ''
  playUrls.flv = ''
  playUrls.hls = ''
  playUrls.raw = ''
  playApp.value = ''
  playStreamId.value = ''
  playDiag.zlm_probe_ok = false
  playDiag.zlm_stream_ready = false
  playDiag.invite_sdp_ip = ''
  playDiag.invite_media_port = null
  playDiag.invite_media_protocol = ''
  playDiag.rtp_port_range = ''
  playbackPaused.value = false
  playbackSpeed.value = 1
  playbackSeekAt.value = null
  playbackActionLoading.value = false
  playbackCursorSec.value = null
  playMode.value = 'webrtc'
  emit('update:playerVisible', false)
}

// ━━ 频道常用 ━━
const canPlay = (row: Record<string, unknown>) => !!row?.gb_id && Number(row?.status) === 1

const refreshChannelSnapshots = async () => {
  refreshingSnapshots.value = true
  channelSnapReloadToken.value = Date.now()
  await loadChannelsDialog()
  refreshingSnapshots.value = false
}

const getChannelRowClassName = ({ row }: { row: Record<string, unknown> }) => Number(row?.status) === 1 ? 'channel-row--online' : 'channel-row--offline'

const getChannelSnapSrc = (row: Record<string, unknown>) => {
  if (row?.snap_url) return String(row.snap_url)
  const channelKey = String(row?.id ?? row?.gb_id ?? '').trim()
  if (!channelKey) return ''
  // P0-6: 移除 URL 中的 token 查询参数，改由 HttpOnly cookie 认证（login 已设置 access_token cookie）
  // 硬约束 #1: 禁止通过 URL 查询参数暴露 JWT token
  const snapUrl = `/api/v1/devices/channels/${encodeURIComponent(channelKey)}/snap?allow_invite=false&t=${channelSnapReloadToken.value}`
  return snapUrl
}

const getResourceTypeLabel = (row: Record<string, unknown>) => {
  const rt = Number(row?.resource_type)
  if (rt === 2) return t('device.alarmInput')
  if (rt === 3) return t('device.alarmOutput')
  return t('device.video')
}
const getResourceTypeTagType = (row: Record<string, unknown>) => {
  const rt = Number(row?.resource_type)
  if (rt === 2) return 'warning'
  if (rt === 3) return 'info'
  return 'success'
}
const getPtzTypeLabel = (row: Record<string, unknown>) => {
  const pt = Number(row?.ptz_type)
  if (pt === 1) return t('device.ptz')
  if (pt === 2) return t('device.hemisphere')
  return t('device.noPtz')
}
const getPtzTypeTagType = (row: Record<string, unknown>) => Number(row?.ptz_type) === 1 ? 'success' : 'info'

const saveChannelAudioInline = async (row: Record<string, unknown>) => {
  const channelId = String(row?.id || '').trim()
  if (!channelId) {
    ElMessage.warning(t('device.selectChannelFirst'))
    return
  }
  const oldValue = !row.has_audio
  channelInlineSaving.value = { ...channelInlineSaving.value, [channelId]: true }
  try {
    await api.put(`/api/v1/devices/channels/${encodeURIComponent(channelId)}`, {
      has_audio: !!row.has_audio
    })
    ElMessage.success(t('device.streamTypeUpdateSuccess'))
  } catch (e: unknown) {
    row.has_audio = oldValue
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    channelInlineSaving.value = { ...channelInlineSaving.value, [channelId]: false }
  }
}

const saveChannelStreamTypeInline = async (row: Record<string, unknown>) => {
  const channelId = String(row?.id || '').trim()
  if (!channelId) {
    ElMessage.warning(t('device.selectChannelFirst'))
    return
  }
  const oldValue = String(row?.default_stream_type || 'main')
  channelInlineSaving.value = { ...channelInlineSaving.value, [channelId]: true }
  try {
    await api.put(`/api/v1/devices/channels/${encodeURIComponent(channelId)}`, {
      default_stream_type: String(row?.default_stream_type || 'main')
    })
    ElMessage.success(t('device.audioUpdateSuccess'))
  } catch (e: unknown) {
    row.default_stream_type = oldValue
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    channelInlineSaving.value = { ...channelInlineSaving.value, [channelId]: false }
  }
}

const resetVisibleChannelsStreamType = async () => {
  if (!props.channelStreamReset) return
  const rows = [...channels.value]
  if (!rows.length) return
  let success = 0
  let failed = 0
  for (const row of rows) {
    const channelId = String(row?.id || '').trim()
    if (!channelId) {
      failed += 1
      continue
    }
    const prev = String(row?.default_stream_type || 'main')
    row.default_stream_type = props.channelStreamReset
    try {
      await api.put(`/api/v1/devices/channels/${encodeURIComponent(channelId)}`, {
        default_stream_type: props.channelStreamReset
      })
      success += 1
    } catch {
      row.default_stream_type = prev
      failed += 1
    }
  }
  if (failed === 0) {
    ElMessage.success(t('device.streamTypeChanged', { count: success }))
  } else if (success > 0) {
    ElMessage.warning(t('device.partialSuccess', { success, failed }))
  } else {
    ElMessage.error(t('device.streamTypeSaveFailed'))
  }
}

const resetChannelDialogFilters = () => {
  channelFilters.value = {
    keyword: '',
    status: undefined,
    resource_type: undefined
  }
  emit('update:channelStreamReset', '')
  emit('update:channelPage', 1)
  loadChannelsDialog()
}

const handleChannelsDialogClosed = () => {
  if (props.playerVisible) {
    void closePlayer()
  }
  emit('update:currentChannel', null)
  cloudRecordDialogVisible.value = false
  deviceRecordDialogVisible.value = false
  timelineRecordDialogVisible.value = false
  recordPlaybackVisible.value = false
  recordAnchorAt.value = ''
}

// ━━ 频道列表状态 ━━光偓━━ 频道列表状态 ━━光偓 VideoRecord tab ━━ 频道列表状态 ━━光偓━━ 频道列表状态 ━━光偓
type RecordTab = 'cloud' | 'device' | 'timeline'

const openRecordTab = async (row: Record<string, unknown>, tab: RecordTab) => {
  if (!props.currentDevice) return
  if (props.playerVisible) {
    try {
      await closePlayer()
    } catch {
      // ignore
    }
  }
  emit('update:currentChannel', row)
  if (!recordChannelOptions.value.length) {
    await loadChannelsDialog()
  }
  recordDialogChannelGbId.value = String(row?.gb_id || row?.id || '').trim()
  if (!recordAnchorAt.value) {
    recordAnchorAt.value = toRecordAnchorValue(new Date())
  }
  cloudRecordDialogVisible.value = tab === 'cloud'
  deviceRecordDialogVisible.value = tab === 'device'
  timelineRecordDialogVisible.value = tab === 'timeline'
}

const handleRecordMenuCommand = async (row: Record<string, unknown>, cmd: string) => {
  const tab: RecordTab = cmd === 'cloud' || cmd === 'device' || cmd === 'timeline' ? cmd : 'timeline'
  await openRecordTab(row, tab)
}

const onRecordDialogChannelChange = (gbId: string) => {
  recordDialogChannelGbId.value = String(gbId || '').trim()
  const current = recordChannelOptions.value.find((item: Record<string, unknown>) => String(item?.gb_id || item?.id || '').trim() === recordDialogChannelGbId.value)
  if (!current) return
  emit('update:currentChannel', current)
}

// ━━ 对外提供 ━━
defineExpose({
  loadChannelsDialog,
  toRecordAnchorValue,
  openRecordTab,
  closePlayer,
  resetChannelDialogFilters,
  recordAnchorAt,
  recordWindowMinutes,
  cloudRecordDialogVisible,
  deviceRecordDialogVisible,
  timelineRecordDialogVisible,
  channelFilters,
  channelPage: computed(() => props.channelPage),
  channelPageSize: computed(() => props.channelPageSize),
  channels,
  channelTotal,
  channelOnlineTotal,
  recordChannelOptions,
  recordDialogChannelGbId,
  recordWindowMinutesRef: recordWindowMinutes,
  recordAnchorAtRef: recordAnchorAt,
})
</script>

<style scoped>
.record-pane {
  margin-top: 10px;
  padding: 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: var(--el-bg-color);
}

.record-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 4px;
}
.record-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}
.record-tabs :deep(.el-tabs__nav-scroll) {
  width: 100%;
}
.record-tabs :deep(.el-tabs__nav) {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
  float: none;
}
.record-tabs :deep(.el-tabs__item) {
  height: 32px;
  border-radius: 3px;
  margin: 0;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--el-text-color-regular);
  font-weight: 600;
  transition: all 0.18s ease;
}
.record-tabs :deep(.el-tabs__item:hover) {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.record-tabs :deep(.el-tabs__item.is-active) {
  background: var(--el-bg-color);
  color: var(--el-color-primary);
  box-shadow: none;
}
</style>
