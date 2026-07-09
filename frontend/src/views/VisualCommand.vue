<template>
  <div class="app-page h-full flex flex-col">
    <PageHeader :title="t('command.title')" :description="t('command.description')" />

    <div class="visual-map-shell flex-1 relative overflow-hidden rounded-2xl" style="border: 1px solid var(--el-border-color-lighter)">
        <div id="vc-map" class="absolute inset-0"></div>

        <div class="absolute top-4 left-4 z-10 flex items-center gap-2 rounded-lg px-3 py-2 shadow-lg" style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter)">
          <el-tag
            size="small"
            :type="alarmWsConnected ? 'success' : (alarmWsReconnecting ? 'warning' : 'info')"
            effect="plain"
          >
            {{ t('command.alarmStream') }}：{{ alarmWsConnected ? t('command.connected') : (alarmWsReconnecting ? t('command.reconnecting') : t('command.disconnected')) }}
          </el-tag>
          <el-tooltip :content="t('command.measureHint')" placement="bottom">
            <el-button size="small" :type="measureMode ? 'primary' : 'default'" @click="toggleMeasure">
              {{ measureMode ? t('command.cancelMeasure') : t('command.measure') }}
            </el-button>
          </el-tooltip>
          <span v-if="measureResult" class="text-sm" style="color: var(--el-text-color-regular)">{{ t('command.distance') }}: {{ measureResult }}</span>
        </div>

        <div
          v-if="configMessage"
          class="absolute top-4 right-4 z-10 text-sm max-w-xs rounded-lg px-3 py-2 shadow-lg"
          style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-regular)"
        >
          {{ configMessage }}
        </div>

    <!-- 视频联动弹窗 -->
    <div id="vc-popup" class="ol-popup vc-popup" v-show="popupVisible">
      <div class="popup-header vc-popup-header flex justify-between items-center p-2 rounded-t-lg">
        <span class="font-bold truncate max-w-[240px]">{{ popupData.name }}</span>
        <el-icon class="cursor-pointer hover:text-primary transition-colors" @click="closePopup"><Close /></el-icon>
      </div>
      <div class="popup-content bg-black rounded-b-lg overflow-hidden relative" :class="popupContentClass">
        <JessibucaPlayer v-if="popupVisible && popupData.url" :video-url="popupData.url" class="w-full h-full" />
        <div v-else class="w-full h-full flex items-center justify-center text-white/30 bg-slate-950">
           <span v-if="popupData.loading" class="animate-pulse">{{ t('command.requestingStream') }}</span>
           <span v-else>{{ t('command.noVideoSignal') }}</span>
        </div>
      </div>
    </div>

    <!-- 轨迹追踪面板 -->
    <div
      v-if="!isMobileRoute"
      class="absolute bottom-4 left-4 right-4 md:right-auto md:w-80 z-10 max-h-72 overflow-hidden flex flex-col rounded-lg shadow-lg"
      style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter)"
    >
      <div class="p-2 font-medium" style="border-bottom: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-regular)">{{ t('command.trajectoryTracking') }}</div>
      <div class="p-2 flex gap-2" style="border-bottom: 1px solid var(--el-border-color-lighter)">
        <el-input v-model="trajectoryFilterDevice" :placeholder="t('command.deviceIdPlaceholder')" size="small" clearable class="flex-1" />
        <el-input v-model="trajectoryFilterChannel" :placeholder="t('command.channelIdPlaceholder')" size="small" clearable class="flex-1" />
      </div>
      <ul class="overflow-auto flex-1 p-2 text-sm space-y-1">
        <li
          v-for="(item, idx) in filteredTrajectoryList"
          :key="idx"
          class="flex justify-between items-start gap-2 py-1 last:border-0 px-1 rounded transition-colors cursor-pointer"
          style="border-bottom: 1px solid var(--el-border-color-lighter)"
          @click="onTrajectoryItemClick(item)"
        >
          <span class="truncate" style="color: var(--el-text-color-regular)" :title="item.description || item.channel_id">{{ item.description || item.channel_id }}</span>
          <span class="text-xs shrink-0" style="color: var(--el-text-color-secondary)">{{ formatTime(item.time) }}</span>
        </li>
        <li v-if="filteredTrajectoryList.length === 0" class="py-2 text-center" style="color: var(--el-text-color-secondary)">{{ t('command.noTrajectoryData') }}</li>
      </ul>
    </div>

    <!-- 移动端：轨迹抽屉（不遮挡地图） -->
    <el-drawer v-if="isMobileRoute" v-model="trajectoryDrawerVisible" :title="t('command.trajectoryTracking')" direction="btt" size="70%">
      <div class="space-y-3">
        <div class="flex gap-2">
          <el-input v-model="trajectoryFilterDevice" :placeholder="t('command.deviceIdPlaceholder')" size="small" clearable class="flex-1" />
          <el-input v-model="trajectoryFilterChannel" :placeholder="t('command.channelIdPlaceholder')" size="small" clearable class="flex-1" />
        </div>
        <ul class="overflow-auto text-sm space-y-1 max-h-[52vh] pr-1">
          <li
            v-for="(item, idx) in filteredTrajectoryList"
            :key="idx"
            class="flex justify-between items-start gap-2 py-2 last:border-0 px-2 rounded transition-colors cursor-pointer"
            style="border-bottom: 1px solid var(--el-border-color-lighter)"
            @click="onTrajectoryItemClick(item); trajectoryDrawerVisible = false"
          >
            <span class="truncate" style="color: var(--el-text-color-regular)" :title="item.description || item.channel_id">{{ item.description || item.channel_id }}</span>
            <span class="text-xs shrink-0" style="color: var(--el-text-color-secondary)">{{ formatTime(item.time) }}</span>
          </li>
          <li v-if="filteredTrajectoryList.length === 0" class="py-2 text-center" style="color: var(--el-text-color-secondary)">{{ t('command.noTrajectoryDataShort') }}</li>
        </ul>
      </div>
    </el-drawer>

    <div v-if="isMobileRoute" class="fixed right-4 bottom-4 z-10 flex flex-col gap-2">
      <el-button type="primary" circle size="large" @click="trajectoryDrawerVisible = true">{{ t('command.trajectoryBtn') }}</el-button>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRoute } from 'vue-router'
import api from '@/utils/http'
import 'ol/ol.css'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import VectorTileLayer from 'ol/layer/VectorTile'
import VectorTileSource from 'ol/source/VectorTile'
import MVT from 'ol/format/MVT'
import OSM from 'ol/source/OSM'
import XYZ from 'ol/source/XYZ'
import { fromLonLat, toLonLat } from 'ol/proj'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import LineString from 'ol/geom/LineString'
import { Vector as VectorSource } from 'ol/source'
import { Vector as VectorLayer } from 'ol/layer'
import { Icon, Style, Stroke, Fill } from 'ol/style'
import CircleStyle from 'ol/style/Circle'
import Overlay from 'ol/Overlay'
import Draw, { DrawEvent } from 'ol/interaction/Draw'
import { getLength } from 'ol/sphere'
import { Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../utils/errorMessage'
import { buildWsUrlWithTicket } from '@/utils/wsTicket'  // P0-6: ws-ticket 认证
import { showSuccess } from '@/utils/feedback'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import PageHeader from '../components/PageHeader.vue'
import { logger } from '@/utils/logger'

const route = useRoute()
const { t } = useI18n()  // FIXED: 国际化
const isMobileRoute = computed(() => String(route.path || '').startsWith('/m/'))
const popupContentClass = computed(() => {
  // 移动端 WebView：尽量铺满宽度，避免固定 400×300 导致横向滚动
  return isMobileRoute.value ? 'w-[92vw] h-[52vw] max-h-[60vh]' : 'w-[400px] h-[300px]'
})

const trajectoryDrawerVisible = ref(false)

const configMessage = ref('')
const measureMode = ref(false)
const measureResult = ref('')
const popupVisible = ref(false)
const popupData = ref({ name: '', url: '', deviceId: '', channelId: '', loading: false })
const trajectoryList = ref<Array<{ device_id: string; channel_id: string; time: string; description?: string; lng?: number; lat?: number }>>([])
const alarmBlinkSeconds = ref(5)
const trajectoryMaxPoints = ref(50)
const blinkTimerRef = ref<number | null>(null)

let map: Map | null = null
let vectorSource: VectorSource | null = null
let trajectorySource: VectorSource | null = null
let trajectoryLayer: VectorLayer<VectorSource> | null = null
let measureSource: VectorSource | null = null
let measureLayer: VectorLayer<VectorSource> | null = null
let drawInteraction: Draw | null = null
let popupOverlay: Overlay | null = null
let ws: WebSocket | null = null
let wsClosedByUser = false
let wsReconnectTimer: number | null = null
let wsReconnectAttempts = 0
const alarmWsConnected = ref(false)
const alarmWsReconnecting = ref(false)
const channelFeatureMap: Record<string, Feature> = {}
const trajectoryFilterDevice = ref('')
const trajectoryFilterChannel = ref('')
const missingCoordinateCount = ref(0)
const pendingFocus = ref<{ deviceId: string; channelId: string } | null>(null)
const lastAutoOpenedKey = ref('')
const autoOpening = ref(false)
let lastLoadChannelsWarnAt = 0

type VisualChannel = {
  device_id?: string
  gb_id?: string
  channel_id?: string
  name?: string
  status?: number
  longitude?: number
  latitude?: number
}

const filteredTrajectoryList = computed(() => {
  const list = trajectoryList.value
  const dev = (trajectoryFilterDevice.value || '').trim().toLowerCase()
  const ch = (trajectoryFilterChannel.value || '').trim().toLowerCase()
  if (!dev && !ch) return list
  return list.filter((item) => {
    if (dev && !(item.device_id || '').toLowerCase().includes(dev)) return false
    if (ch && !(item.channel_id || '').toLowerCase().includes(ch)) return false
    return true
  })
})

function onTrajectoryItemClick(item: { device_id: string; channel_id: string; lng?: number; lat?: number }) {
  if (!map) return
  const lng = item.lng
  const lat = item.lat
  if (lng != null && lat != null) {
    map.getView().animate({
      center: fromLonLat([lng, lat]),
      zoom: 16,
      duration: 300
    })
    blinkChannel(item.device_id, item.channel_id)
  }
}

function _parseFocusQuery() {
  const q = route.query as Record<string, unknown>
  const deviceId = String(q?.device_id || '').trim()
  const channelId = String(q?.channel_id || '').trim()
  if (!deviceId || !channelId) {
    pendingFocus.value = null
    return
  }
  pendingFocus.value = { deviceId, channelId }
}

function _tryFocusPending() {
  if (!pendingFocus.value || !map) return
  const { deviceId, channelId } = pendingFocus.value
  const feature = channelFeatureMap[key(deviceId, channelId)]
  if (!feature) {
    // 常见原因：通道缺少经纬度，未能在地图生成点位
    if (missingCoordinateCount.value > 0) {
      configMessage.value = t('command.missingCoordinateFocus', { count: missingCoordinateCount.value })
    } else {
      configMessage.value = t('command.channelNotFound')
    }
    return
  }
  const geom = feature.getGeometry() as Point
  if (geom) {
    map.getView().animate({ center: geom.getCoordinates(), zoom: 16, duration: 300 })
  }
  blinkChannel(deviceId, channelId)

  const k = key(deviceId, channelId)
  if (lastAutoOpenedKey.value === k || autoOpening.value) return
  const ch = feature.get('channel') as VisualChannel
  if (!ch) return
  autoOpening.value = true
  Promise.resolve()
    .then(async () => {
      await openChannelPopup(ch, geom.getCoordinates())
      lastAutoOpenedKey.value = k
    })
    .finally(() => {
      autoOpening.value = false
    })
}

const mapConfig = ref({
  provider: 'tianditu',
  api_key: '',
  vector_tile_url: '',
  center_lng: 116.404,
  center_lat: 39.915,
  zoom_level: 12,
  min_zoom: 1,
  max_zoom: 20
})

function getLayer(provider: string, key: string) {
  if (provider === 'vector') {
    const url = mapConfig.value.vector_tile_url || 'https://basemaps.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/tile/{z}/{y}/{x}.pbf'
    return new VectorTileLayer({
      source: new VectorTileSource({
        format: new MVT(),
        url: url
      })
    })
  } else if (provider === 'gaode') {
    return new TileLayer({
      source: new XYZ({
        url: 'http://wprd0{1-4}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}'
      })
    })
  } else if (provider === 'tianditu') {
    const k = key
    if (!k) {
      ElMessage.warning(t('command.tiandituApiKeyMissing'))
      return new TileLayer({ source: new OSM() })
    }
    return new TileLayer({
      source: new XYZ({
        url: `http://t0.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=${k}`
      })
    })
  }
  return new TileLayer({ source: new OSM() })
}

function key(deviceId: string, channelId: string) {
  return `${deviceId}|${channelId}`
}

function initMap() {
  const baseLayer = getLayer(mapConfig.value.provider, mapConfig.value.api_key)
  vectorSource = new VectorSource()
  trajectorySource = new VectorSource()
  trajectoryLayer = new VectorLayer({
    source: trajectorySource,
    style: new Style({
      stroke: new Stroke({ color: '#3399cc', width: 3 })
    }),
    zIndex: 5
  })

  popupOverlay = new Overlay({
    element: document.getElementById('vc-popup')!,
    autoPan: {
      animation: { duration: 250 }
    },
    positioning: 'bottom-center',
    stopEvent: false,
    offset: [0, -10]
  })

  map = new Map({
    target: 'vc-map',
    layers: [
      baseLayer,
      new VectorLayer({ source: vectorSource, zIndex: 10 }),
      trajectoryLayer
    ],
    view: new View({
      center: fromLonLat([mapConfig.value.center_lng, mapConfig.value.center_lat]),
      zoom: mapConfig.value.zoom_level,
      minZoom: mapConfig.value.min_zoom,
      maxZoom: mapConfig.value.max_zoom
    }),
    overlays: [popupOverlay]
  })

  map.on('click', async (evt) => {
    const feature = map!.forEachFeatureAtPixel(evt.pixel, (f) => f)
    if (feature) {
      const ch = feature.get('channel') as VisualChannel
      if (!ch) return
      lastAutoOpenedKey.value = key(String(ch.device_id || ''), String(ch.gb_id || ''))
      const coords = (feature.getGeometry() as Point).getCoordinates()
      await openChannelPopup(ch, coords)
    } else {
      closePopup()
    }
  })
}

function addChannelMarker(ch: VisualChannel, blink = false) {
  if (!vectorSource) return
  let lng = ch.longitude 
  let lat = ch.latitude
  
  if (!lng || !lat || (Math.abs(lng) < 1 && Math.abs(lat) < 1)) {
    missingCoordinateCount.value += 1
    return
  }

  const feature = new Feature(new Point(fromLonLat([lng, lat])))
  feature.set('channel', ch)
  feature.setStyle(new Style({
    image: new Icon({
      src: '/camera-icon.png',
      scale: 0.06,
      color: blink ? '#F56C6C' : (Number(ch.status) === 1 ? '#67C23A' : '#909399'),
      anchor: [0.5, 1]
    })
  }))
  vectorSource.addFeature(feature)
  channelFeatureMap[key(String(ch.device_id || ''), String(ch.gb_id || ''))] = feature
}

function blinkChannel(deviceId: string, channelId: string) {
  const feature = channelFeatureMap[key(deviceId, channelId)]
  if (!feature || !vectorSource) return
  const ch = feature.get('channel') as VisualChannel
  const originalColor = Number(ch?.status) === 1 ? '#67C23A' : '#909399'
  feature.setStyle(new Style({
    image: new Icon({
      src: '/camera-icon.png',
      scale: 0.08,
      color: '#F56C6C',
      anchor: [0.5, 1]
    })
  }))
  if (blinkTimerRef.value != null) window.clearTimeout(blinkTimerRef.value)
  blinkTimerRef.value = window.setTimeout(() => {
    feature.setStyle(new Style({
      image: new Icon({
        src: '/camera-icon.png',
        scale: 0.06,
        color: originalColor,
        anchor: [0.5, 1]
      })
    }))
    blinkTimerRef.value = null
  }, alarmBlinkSeconds.value * 1000)
}

async function loadTrajectory(deviceId: string) {
  try {
    const res = await api.get('/api/v1/map/trajectory', { params: { device_id: deviceId, limit: trajectoryMaxPoints.value } })
    if (res.data && res.data.length > 0) {
      trajectoryList.value = res.data.map((p: Record<string, unknown>) => ({
        device_id: deviceId,
        channel_id: String(p.channel_id || deviceId),
        time: String(p.time || ''),
        description: p.speed ? t('command.speedLabel', { speed: String(p.speed) }) : t('command.historyTrajectory'),
        lng: p.lng != null ? Number(p.lng) : undefined,
        lat: p.lat != null ? Number(p.lat) : undefined
      }))
      updateTrajectoryLine()
    }
  } catch {
    // 轨迹加载失败时保持静默，轨迹面板会为空
  }
}

type VisualAlarm = {
  device_id?: string
  channel_id?: string
  time?: string
  description?: string
}

function pushTrajectory(alarm: VisualAlarm, lng?: number, lat?: number) {
  if (lng == null || lat == null) return
  const list = [...trajectoryList.value]
  list.unshift({
    device_id: String(alarm.device_id || ''),
    channel_id: String(alarm.channel_id || ''),
    time: String(alarm.time || new Date().toISOString()),
    description: alarm.description,
    lng,
    lat
  })
  trajectoryList.value = list.slice(0, trajectoryMaxPoints.value)
  updateTrajectoryLine()
}

async function persistTrajectoryPoint(alarm: VisualAlarm, lng: number, lat: number) {
  try {
    await api.post('/api/v1/map/trajectory', {
      device_id: String(alarm.device_id || ''),
      channel_id: String(alarm.channel_id || ''),
      lng,
      lat,
      time: alarm.time
    })
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('command.trajectoryPushFailed'))
    logger.warn(msg, e)
  }
}

function updateTrajectoryLine() {
  if (!trajectorySource) return
  trajectorySource.clear()
  const points = trajectoryList.value
    .filter((p) => p.lng != null && p.lat != null)
    .map((p) => fromLonLat([p.lng!, p.lat!]))
  if (points.length < 2) return
  const line = new Feature(new LineString(points))
  trajectorySource.addFeature(line)
  
  // Add start/end points
  points.forEach((p) => {
    const pointFeature = new Feature(new Point(p))
    pointFeature.setStyle(new Style({
      image: new Icon({
        src: '/camera-icon.png',
        scale: 0.04,
        color: '#409EFF'
      })
    }))
    trajectorySource!.addFeature(pointFeature)
  })
}

function toggleMeasure() {
  if (!map) return
  measureMode.value = !measureMode.value
  if (drawInteraction) {
    map.removeInteraction(drawInteraction)
    drawInteraction = null
  }
  if (measureSource) measureSource.clear()
  if (measureLayer) {
    map.removeLayer(measureLayer)
    measureLayer = null
  }
  measureResult.value = ''
  if (!measureMode.value) return
  measureSource = new VectorSource()
  measureLayer = new VectorLayer({ 
    source: measureSource,
    zIndex: 20,
    style: new Style({
      fill: new Fill({ color: 'rgba(255, 255, 255, 0.2)' }),
      stroke: new Stroke({ color: '#E6A23C', lineDash: [10, 10], width: 2 }),
      image: new CircleStyle({ radius: 5, fill: new Fill({ color: '#E6A23C' }) })
    })
  })
  map.addLayer(measureLayer)
  drawInteraction = new Draw({ source: measureSource, type: 'LineString' })
  drawInteraction.on('drawend', (e: DrawEvent) => {
    const line = e.feature.getGeometry() as LineString
    const length = getLength(line, { radius: 6371008.8 })
    measureResult.value = length >= 1000 ? (length / 1000).toFixed(2) + ' km' : length.toFixed(0) + ' m'
    
    setTimeout(() => {
        map?.removeInteraction(drawInteraction!)
        drawInteraction = null
        measureMode.value = false
    }, 500)
  })
  map.addInteraction(drawInteraction)
}

function formatTime(iso: string) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function closePopup() {
  popupVisible.value = false
  popupOverlay?.setPosition(undefined)
  popupData.value.url = ''
}

async function openChannelPopup(ch: VisualChannel, coordinates: number[]) {
  if (!popupOverlay) return
  popupData.value.name = ch.name || ch.gb_id || ch.channel_id || t('command.channelDefaultName')
  popupData.value.deviceId = String(ch.device_id || '')
  popupData.value.channelId = String(ch.gb_id || '')
  popupData.value.loading = true
  popupVisible.value = true
  popupOverlay.setPosition(coordinates)
  try {
    const playRes = await api.post(
      `/api/v1/stream/play/${ch.device_id}/${ch.gb_id}`,
      null,
      { params: { stream_type: 'auto' } }
    )
    popupData.value.url = playRes.data.flv || ''
    loadTrajectory(String(ch.device_id || ''))
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, t('command.getVideoStreamFailed')))
    popupData.value.url = ''
  } finally {
    popupData.value.loading = false
  }
}

async function fetchConfig() {
  try {
    const [mapRes, cmdRes] = await Promise.all([
      api.get('/api/v1/map'),
      api.get('/api/v1/map/command-config')
    ])
    if (mapRes.data) mapConfig.value = { ...mapConfig.value, ...mapRes.data }
    configMessage.value = cmdRes.data?.message || ''
    alarmBlinkSeconds.value = cmdRes.data?.alarm_blink_seconds ?? 5
    trajectoryMaxPoints.value = cmdRes.data?.trajectory_max_points ?? 50
  } catch {
    configMessage.value = t('command.defaultConfigMessage')
  }
}

async function loadChannels() {
  try {
    const res = await api.get('/api/v1/devices/channels/flat', { params: { node_type: 'channel', skip: 0, limit: 5000 } })
    const channels = Array.isArray(res.data?.items) ? res.data.items : []
    missingCoordinateCount.value = 0
    for (const k in channelFeatureMap) delete channelFeatureMap[k]
    vectorSource?.clear()
    channels.forEach((ch: VisualChannel) => addChannelMarker(ch))
    if (missingCoordinateCount.value > 0) {
      configMessage.value = t('command.missingCoordinateCount', { count: missingCoordinateCount.value })
    }
    if (map) {
      map.getView().setCenter(fromLonLat([mapConfig.value.center_lng, mapConfig.value.center_lat]))
      map.getView().setZoom(mapConfig.value.zoom_level)
    }
    _tryFocusPending()
  } catch (e: unknown) {
    configMessage.value = getApiErrorMessage(e, t('command.loadChannelsFailed'))
    const now = Date.now()
    if (now - lastLoadChannelsWarnAt > 3000) {
      lastLoadChannelsWarnAt = now
      ElMessage.warning(configMessage.value)
    }
  }
}

async function initAlarmWs() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  if (wsReconnectTimer != null) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  // P0-6: 通过 ws-ticket 认证，消除 URL 暴露 JWT token
  let wsUrl: string
  try {
    wsUrl = await buildWsUrlWithTicket('/api/v1/alarms/ws')
  } catch (e) {
    logger.warn('initAlarmWs: failed to fetch ws-ticket', e)
    return
  }
  ws = new WebSocket(wsUrl)
  ws.onmessage = (event) => {
    try {
      const alarm = JSON.parse(event.data)
      const deviceId = alarm.device_id
      const channelId = alarm.channel_id
      if (deviceId && channelId) {
        blinkChannel(deviceId, channelId)
        const feature = channelFeatureMap[key(deviceId, channelId)]
        let lng: number | undefined
        let lat: number | undefined
        if (feature) {
          const geom = feature.getGeometry() as Point
          if (geom) {
            const [x, y] = toLonLat(geom.getCoordinates())
            lng = x
            lat = y
          }
        }
        if ((lng == null || lat == null) && alarm.longitude && alarm.latitude) {
          lng = Number(alarm.longitude)
          lat = Number(alarm.latitude)
        }
        pushTrajectory(alarm, lng, lat)
        if (lng != null && lat != null) {
          persistTrajectoryPoint(alarm, lng, lat)
        }
      }
    } catch (e) { logger.warn('WebSocket告警消息处理失败:', e) }
  }

  ws.onopen = () => {
    alarmWsConnected.value = true
    alarmWsReconnecting.value = false
    wsReconnectAttempts = 0
  }

  ws.onclose = () => {
    alarmWsConnected.value = false
    if (wsClosedByUser) return
    if (wsReconnectTimer != null) return
    alarmWsReconnecting.value = true
    wsReconnectAttempts += 1
    const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(wsReconnectAttempts, 5)))
    wsReconnectTimer = window.setTimeout(() => {
      wsReconnectTimer = null
      initAlarmWs()
    }, delay)
  }
}

onMounted(async () => {
  await fetchConfig()
  initMap()
  loadChannels()
  initAlarmWs()
  _parseFocusQuery()
  _tryFocusPending()
})

watch(
  () => route.query,
  () => {
    _parseFocusQuery()
    _tryFocusPending()
  }
)

onBeforeUnmount(() => {
  pendingFocus.value = null
  if (blinkTimerRef.value != null) window.clearTimeout(blinkTimerRef.value)
  wsClosedByUser = true
  alarmWsReconnecting.value = false
  if (ws) ws.close()
  if (wsReconnectTimer != null) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
})
</script>

<style scoped>
.vc-popup {
  position: absolute;
  border-radius: 6px;
  filter: none;
}
.visual-map-shell {
  background: var(--el-fill-color-darker);
}
.vc-popup-header {
  background: var(--el-text-color-primary);
  color: var(--el-bg-color-overlay);
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.vc-popup:after, .vc-popup:before {
  top: 100%;
  border: solid transparent;
  content: " ";
  height: 0;
  width: 0;
  position: absolute;
  pointer-events: none;
}
.vc-popup:after {
  border-top-color: var(--el-text-color-primary);
  border-width: 10px;
  left: 50%;
  margin-left: -10px;
}
</style>
