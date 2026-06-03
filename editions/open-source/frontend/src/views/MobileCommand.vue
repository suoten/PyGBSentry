<template>
  <div class="app-page h-full">
    <PageContainer class="h-full flex flex-col">
      <template #header>
        <PageHeader title="移动指挥" description="移动单兵与车载终端实时监控、位置追踪与视频指挥" />
      </template>

      <!-- 会商：近期报警 + 发起会商 -->
      <TableCard class="shrink-0 mb-4">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">会商会话</div>
            <div class="flex gap-2">
              <el-button link size="small" @click="loadActiveSessions">刷新会话</el-button>
              <el-button type="primary" link size="small" @click="loadRecentAlarms">刷新报警</el-button>
            </div>
          </div>
        </template>
        <div class="flex gap-4 flex-wrap">
          <div class="min-w-[280px] max-w-md">
            <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">进行中的会商</div>
            <div v-if="activeSessionsLoading" style="color: var(--el-text-color-secondary)">加载中...</div>
            <ul v-else class="space-y-2 max-h-32 overflow-y-auto">
              <li
                v-for="s in activeSessions"
                :key="s.id"
                class="flex justify-between items-center gap-2 p-2 rounded cursor-pointer"
                style="background: var(--el-fill-color-light)"
                @click="joinExistingSession(s)"
              >
                <span class="truncate text-sm">{{ s.title || s.id }}</span>
                <el-tag size="small" type="success">{{ s.participant_count || 0 }}人</el-tag>
              </li>
              <li v-if="!activeSessions.length" class="text-sm" style="color: var(--el-text-color-secondary)">暂无进行中的会商</li>
            </ul>
          </div>
          <div class="min-w-[280px] max-w-md">
            <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">近期未确认报警（点击发起会商）</div>
            <div v-if="recentAlarmsLoading" style="color: var(--el-text-color-secondary)">加载中...</div>
            <ul v-else class="space-y-2 max-h-32 overflow-y-auto">
              <li
                v-for="a in recentAlarms"
                :key="a.id"
                class="flex justify-between items-center gap-2 p-2 rounded cursor-pointer"
                style="background: var(--el-fill-color-light)"
                @click="openConference(a)"
              >
                <span class="truncate text-sm">{{ a.description || a.device_id }}</span>
                <el-button size="small" type="primary" @click.stop="openConference(a)">发起会商</el-button>
              </li>
              <li v-if="!recentAlarms.length" class="text-sm" style="color: var(--el-text-color-secondary)">暂无</li>
            </ul>
          </div>
        </div>
      </TableCard>
      
      <div class="flex-1 flex gap-4 overflow-hidden min-h-0">
        <!-- Left Panel: Mobile Units List -->
        <div class="w-80 flex flex-col rounded-lg overflow-hidden shrink-0" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
          <div class="p-3 font-medium flex justify-between items-center shrink-0" style="border-bottom: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light);">
            <span>在线移动设备 ({{ onlineMobileCount }})</span>
            <el-button type="primary" link size="small" @click="loadChannels">刷新</el-button>
          </div>
          <div class="flex-1 overflow-y-auto p-2 space-y-2 min-h-0">
            <div v-if="loading" class="py-4 text-center" style="color: var(--el-text-color-secondary)">加载中...</div>
            <div v-else-if="!mobileChannels.length" class="py-4 text-center" style="color: var(--el-text-color-secondary)">
              暂无在线移动设备
              <div class="text-xs mt-1">请确保设备已开启 GPS 上报</div>
            </div>
            
            <div 
              v-for="ch in mobileChannels" 
              :key="ch.gb_id"
              class="p-3 rounded cursor-pointer border border-transparent hover:border-primary transition-colors"
              :style="{ background: 'var(--el-fill-color-light)' }"
              :class="{ 'border-primary': selectedChannel?.gb_id === ch.gb_id }"
              @click="selectChannel(ch)"
            >
              <div class="flex justify-between items-start mb-1">
                <span class="font-medium truncate" :title="ch.name">{{ ch.name || ch.gb_id }}</span>
                <el-tag size="small" effect="plain" type="success">在线</el-tag>
              </div>
              <div class="text-xs flex flex-col gap-1" style="color: var(--el-text-color-secondary)">
                <span>ID: {{ ch.gb_id }}</span>
                <span v-if="ch.longitude && ch.latitude">
                  Loc: {{ ch.longitude.toFixed(6) }}, {{ ch.latitude.toFixed(6) }}
                </span>
              </div>
              <div class="mt-2 flex gap-2">
                <el-button size="small" type="primary" plain @click.stop="callDevice(ch)">
                  <el-icon class="mr-1"><VideoCamera /></el-icon> 视频
                </el-button>
                <el-button size="small" type="warning" plain @click.stop="trackDevice(ch)">
                  <el-icon class="mr-1"><Position /></el-icon> 轨迹
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Panel: Map -->
        <div class="flex-1 relative rounded-lg overflow-hidden shadow-lg min-h-0" style="border: 1px solid var(--el-border-color-lighter); background: #0b1220">
          <div id="mc-map" class="w-full h-full"></div>
          
          <!-- Video Popup -->
          <div id="mc-popup" class="ol-popup mc-popup" v-show="popupVisible">
            <div class="popup-header flex justify-between items-center p-2 rounded-t-lg" style="background: #0b1220; color: rgba(255,255,255,.92); border-bottom: 1px solid rgba(255,255,255,.08);">
              <span class="font-bold truncate max-w-[200px]">{{ popupData.name }}</span>
              <el-icon class="cursor-pointer hover:text-primary" @click="closePopup"><Close /></el-icon>
            </div>
            <div class="popup-content w-[400px] h-[260px] bg-black rounded-b-lg overflow-hidden relative">
              <JessibucaPlayer v-if="popupVisible && popupData.url" :video-url="popupData.url" class="w-full h-full" />
              <div v-else class="h-full flex items-center justify-center text-white/30 bg-slate-950">
                {{ popupData.loading ? '正在请求视频流...' : '暂无视频' }}
              </div>
            </div>
          </div>

          <!-- Trajectory Info -->
          <div v-if="trackingChannel" class="absolute top-4 right-4 z-10 p-3 rounded text-sm shadow-lg" style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter)">
            <div class="font-bold mb-1 text-primary">正在追踪: {{ trackingChannel.name }}</div>
            <div class="text-xs mb-2" style="color: var(--el-text-color-secondary)">显示最近 50 个轨迹点</div>
            <el-button size="small" link type="info" @click="clearTrack">停止追踪</el-button>
          </div>
        </div>
      </div>

      <!-- 会商抽屉 -->
      <el-drawer v-model="conferenceDrawerVisible" title="会商会话" size="420" direction="rtl">
        <div v-if="conferenceAlarm" class="space-y-4">
          <div class="text-sm" style="color: var(--el-text-color-regular)">
            <p><strong>报警</strong> {{ conferenceAlarm.device_id }} / {{ conferenceAlarm.description }}</p>
            <p class="mt-1" style="color: var(--el-text-color-secondary)">会话ID: {{ conferenceSession?.id || conferenceAlarm.id }}</p>
          </div>
          <div class="h-48 bg-black rounded overflow-hidden">
            <JessibucaPlayer v-if="conferencePlayUrl" :video-url="conferencePlayUrl" class="w-full h-full" />
            <div v-else class="h-full flex items-center justify-center" style="color: rgba(255,255,255,.6)">报警通道预览</div>
          </div>
          <div>
            <div class="text-sm font-medium mb-2">参会成员</div>
            <div class="space-y-1 max-h-24 overflow-y-auto mb-3">
              <div v-for="p in conferenceParticipants" :key="p.id" class="text-xs" style="color: var(--el-text-color-regular)">
                {{ p.username }}（{{ p.role }}）
              </div>
              <div v-if="!conferenceParticipants.length" class="text-sm" style="color: var(--el-text-color-secondary)">暂无参会成员</div>
            </div>
            <div class="text-sm font-medium mb-2">会商指令</div>
            <div class="space-y-2 max-h-48 overflow-y-auto mb-3">
              <div v-for="inst in conferenceInstructions" :key="inst.id" class="p-2 rounded bg-white/5 text-sm">
                {{ inst.content }}
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ inst.created_at }}</span>
              </div>
              <div v-if="!conferenceInstructions.length" class="text-sm" style="color: var(--el-text-color-secondary)">暂无指令</div>
            </div>
            <el-input v-model="newInstructionText" type="textarea" :rows="2" placeholder="输入指令并发布" />
            <div class="mt-2 flex gap-2">
              <el-button type="primary" size="small" @click="publishInstruction">发布指令</el-button>
              <el-button type="success" size="small" @click="closeConference">结束会商</el-button>
            </div>
          </div>
        </div>
      </el-drawer>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onBeforeUnmount } from 'vue'
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
import { fromLonLat } from 'ol/proj'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import LineString from 'ol/geom/LineString'
import { Vector as VectorSource } from 'ol/source'
import { Vector as VectorLayer } from 'ol/layer'
import { Icon, Style, Stroke, Fill } from 'ol/style'
import CircleStyle from 'ol/style/Circle'
import Overlay from 'ol/Overlay'
import { VideoCamera, Close, Position } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../utils/errorMessage'
import { showSuccess } from '@/utils/feedback'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'
import { logger } from '@/utils/logger'

// State
const loading = ref(false)
const channels = ref<Channel[]>([])
const selectedChannel = ref<Channel | null>(null)
const trackingChannel = ref<Channel | null>(null)
const popupVisible = ref(false)
const popupData = ref({ name: '', url: '', loading: false })

// 会商
const recentAlarms = ref<Alarm[]>([])
const recentAlarmsLoading = ref(false)

// 会商
const conferenceDrawerVisible = ref(false)
const conferenceAlarm = ref<Alarm | null>(null)
const conferencePlayUrl = ref('')
const conferenceInstructions = ref<{ id: string; content: string; created_at?: string }[]>([])
const activeSessions = ref<{ id: string; title: string; participant_count: number; status: string }[]>([])
const activeSessionsLoading = ref(false)
const newInstructionText = ref('')
const conferenceSession = ref<ConferenceSession | null>(null)
const conferenceParticipants = ref<{ id: string; username: string; role: string }[]>([])

// Map
let map: Map | null = null
let vectorSource: VectorSource | null = null
let trajectorySource: VectorSource | null = null
let popupOverlay: Overlay | null = null

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

// Computed
const mobileChannels = computed(() => {
  return channels.value.filter(ch => 
    Number(ch.status) === 1 &&
    ch.longitude && ch.latitude && 
    (Math.abs(ch.longitude) > 0.1 || Math.abs(ch.latitude) > 0.1)
  )
})

const onlineMobileCount = computed(() => mobileChannels.value.length)

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
  } else if (provider === 'baidu') {
    // 百度地图瓦片（使用高德坐标系的 WebGL 瓦片服务，无需特殊 AK）
    return new TileLayer({
      source: new XYZ({
        url: 'https://maponline2.bdimg.com/tile/?qt=tile&x={x}&y={y}&z={z}&styles=pl&scaler=1'
      })
    })
  } else if (provider === 'tianditu') {
    const k = key
    if (!k) {
      ElMessage.warning('天地图未配置 API Key，请在地图配置中设置')
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

// Methods
async function loadChannels() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/devices/channels/flat', { params: { node_type: 'channel', skip: 0, limit: 5000 } })
    channels.value = Array.isArray(res.data?.items) ? res.data.items : (Array.isArray(res.data) ? res.data : [])
    updateMapMarkers()
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载移动设备失败'))
  } finally {
    loading.value = false
  }
}

async function fetchConfig() {
  try {
    const res = await api.get('/api/v1/map')
    if (res.data) mapConfig.value = { ...mapConfig.value, ...res.data }
  } catch (e) {
    // defaults
  }
}

function initMap() {
  const baseLayer = getLayer(mapConfig.value.provider, mapConfig.value.api_key)
  vectorSource = new VectorSource()
  trajectorySource = new VectorSource()
  
  popupOverlay = new Overlay({
    element: document.getElementById('mc-popup')!,
    autoPan: {
      animation: { duration: 250 }
    },
    positioning: 'bottom-center',
    stopEvent: false,
    offset: [0, -10]
  })

  map = new Map({
    target: 'mc-map',
    layers: [
      baseLayer,
      new VectorLayer({
        source: trajectorySource,
        style: new Style({
          stroke: new Stroke({ color: '#E6A23C', width: 4 }),
          image: new CircleStyle({
            radius: 4,
            fill: new Fill({ color: '#E6A23C' })
          })
        }),
        zIndex: 5
      }),
      new VectorLayer({ source: vectorSource, zIndex: 10 })
    ],
    view: new View({
      center: fromLonLat([mapConfig.value.center_lng, mapConfig.value.center_lat]),
      zoom: mapConfig.value.zoom_level,
      minZoom: mapConfig.value.min_zoom,
      maxZoom: mapConfig.value.max_zoom
    }),
    overlays: [popupOverlay]
  })
}

function updateMapMarkers() {
  if (!vectorSource) return
  vectorSource.clear()
  
  mobileChannels.value.forEach(ch => {
    const feature = new Feature(new Point(fromLonLat([ch.longitude, ch.latitude])))
    feature.set('channel', ch)
    
    feature.setStyle(new Style({
      image: new Icon({
        src: '/camera-icon.png',
        scale: 0.08,
        color: selectedChannel.value?.gb_id === ch.gb_id ? '#409EFF' : '#67C23A',
        anchor: [0.5, 1]
      })
    }))
    
    vectorSource!.addFeature(feature)
  })
}

function selectChannel(ch: Record<string, unknown>) {
  selectedChannel.value = ch
  if (map) {
    map.getView().animate({
      center: fromLonLat([ch.longitude, ch.latitude]),
      zoom: 15,
      duration: 500
    })
    updateMapMarkers() // To update color
  }
}

async function callDevice(ch: Record<string, unknown>) {
  selectChannel(ch)
  popupData.value = { name: ch.name || ch.gb_id, url: '', loading: true }
  popupVisible.value = true
  // Set popup position
  if (popupOverlay) {
    popupOverlay.setPosition(fromLonLat([ch.longitude, ch.latitude]))
  }
  
  try {
    const res = await api.post(
      `/api/v1/stream/play/${ch.device_id}/${ch.gb_id}`,
      null,
      { params: { stream_type: 'auto' } }
    )
    popupData.value.url = res.data.flv || ''
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '获取视频流失败，请检查设备在线'))
    popupData.value.url = ''
  } finally {
    popupData.value.loading = false
  }
}

function closePopup() {
  popupVisible.value = false
  popupData.value.url = ''
}

async function trackDevice(ch: Record<string, unknown>) {
  selectChannel(ch)
  trackingChannel.value = ch
  if (!trajectorySource) return
  trajectorySource.clear()
  
  try {
    const res = await api.get('/api/v1/map/trajectory', { 
      params: { 
        device_id: ch.device_id,
        limit: 50 
      } 
    })
    
    if (Array.isArray(res.data) && res.data.length > 0) {
      const points = res.data
        .filter((p: Record<string, unknown>) => p.lng && p.lat)
        .map((p: Record<string, unknown>) => fromLonLat([p.lng, p.lat]))
      
      if (points.length > 1) {
        const line = new Feature(new LineString(points))
        trajectorySource.addFeature(line)
        
        points.forEach((p) => {
          trajectorySource!.addFeature(new Feature(new Point(p)))
        })
        
        if (map) {
          const extent = trajectorySource.getExtent()
          if (extent && extent.length === 4 && extent[0] !== Infinity) {
            map.getView().fit(extent, { padding: [50, 50, 50, 50], duration: 500 })
          }
        }
      }
    }
  } catch (e) {
    ElMessage.warning('轨迹加载失败，请稍后重试')
  }
}

function clearTrack() {
  trackingChannel.value = null
  trajectorySource?.clear()
}

async function loadRecentAlarms() {
  recentAlarmsLoading.value = true
  try {
    const res = await api.get('/api/v1/alarms', { params: { limit: 10, escalation_state: 'open' } })
    recentAlarms.value = Array.isArray(res.data?.items) ? res.data.items : []
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载报警失败'))
  } finally {
    recentAlarmsLoading.value = false
  }
}

async function loadActiveSessions() {
  activeSessionsLoading.value = true
  try {
    const res = await api.get('/api/v1/command/sessions', { params: { status: 'active' } })
    activeSessions.value = Array.isArray(res.data) ? res.data : (Array.isArray(res.data?.items) ? res.data.items : [])
  } catch (e: unknown) {
    activeSessions.value = []
  } finally {
    activeSessionsLoading.value = false
  }
}

async function joinExistingSession(session: Record<string, unknown>) {
  conferenceAlarm.value = null
  conferenceDrawerVisible.value = true
  conferencePlayUrl.value = ''
  newInstructionText.value = ''
  conferenceParticipants.value = []
  conferenceSession.value = session
  try {
    await api.post(`/api/v1/command/sessions/${session.id}/join`, { role: 'participant' })
  } catch (e: unknown) {
    logger.warn('加入会话失败', e)
  }
  try {
    await loadConferenceParticipants()
    await loadConferenceInstructions()
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载会商信息失败'))
  }
}

async function loadConferenceInstructions() {
  if (!conferenceSession.value?.id) return
  try {
    const res = await api.get('/api/v1/command/instructions', { params: { session_id: conferenceSession.value.id } })
    conferenceInstructions.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载会商指令失败'))
  }
}

async function loadConferenceParticipants() {
  if (!conferenceSession.value?.id) return
  try {
    const res = await api.get(`/api/v1/command/sessions/${conferenceSession.value.id}/participants`)
    conferenceParticipants.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载参会成员失败'))
  }
}

async function openConference(alarm: Record<string, unknown>) {
  conferenceAlarm.value = alarm
  conferenceDrawerVisible.value = true
  conferencePlayUrl.value = ''
  newInstructionText.value = ''
  conferenceParticipants.value = []
  try {
    const sessionRes = await api.post('/api/v1/command/sessions', {
      alarm_id: alarm.id,
      title: alarm.description || `报警会商 ${alarm.id}`
    })
    conferenceSession.value = sessionRes.data
    showSuccess('会商已发起')
    if (conferenceSession.value?.id) {
      await api.post(`/api/v1/command/sessions/${conferenceSession.value.id}/join`, { role: 'participant' })
    }
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '发起会商失败'))
    conferenceSession.value = { id: alarm.id }
  }
  try {
    await loadConferenceParticipants()
    await loadConferenceInstructions()
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载会商信息失败'))
  }
  try {
    const dev = alarm.device_id || alarm.channel_id
    const ch = alarm.channel_id || alarm.device_id
    if (dev && ch) {
      const res = await api.post(
        `/api/v1/stream/play/${dev}/${ch}`,
        null,
        { params: { stream_type: 'auto' } }
      )
      conferencePlayUrl.value = res.data?.flv || ''
    }
  } catch (e: unknown) {
    ElMessage.warning('会商视频加载失败，请检查设备在线')
  }
}

async function publishInstruction() {
  const text = newInstructionText.value?.trim()
  if (!text || !conferenceSession.value?.id) return
  try {
    await api.post('/api/v1/command/instructions', { session_id: conferenceSession.value.id, content: text })
    showSuccess('指令已发布')
    newInstructionText.value = ''
    await loadConferenceInstructions()
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '发布指令失败'))
  }
}

async function closeConference() {
  if (!conferenceSession.value?.id) return
  try {
    await api.post(`/api/v1/command/sessions/${conferenceSession.value.id}/close`, {
      summary: `会商结束（操作人：当前用户）`
    })
    showSuccess('会商已结束')
    conferenceDrawerVisible.value = false
    conferenceSession.value = null
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '结束会商失败'))
  }
}

onMounted(async () => {
  try {
    await fetchConfig()
  } catch (e: unknown) {
    ElMessage.warning(getApiErrorMessage(e, '加载配置失败'))
  }
  initMap()
  loadChannels()
  loadRecentAlarms()
  loadActiveSessions()
})

onBeforeUnmount(() => {
  if (map) {
    map.setTarget(undefined)
  }
})
</script>

<style scoped>
.mc-popup {
  position: absolute;
  border-radius: 8px;
  filter: drop-shadow(0 1px 4px rgba(0,0,0,0.5));
}
.mc-popup:after, .mc-popup:before {
  top: 100%;
  border: solid transparent;
  content: " ";
  height: 0;
  width: 0;
  position: absolute;
  pointer-events: none;
}
.mc-popup:after {
  border-top-color: #0f172a; /* matches slate-900 */
  border-width: 10px;
  left: 50%;
  margin-left: -10px;
}
</style>
