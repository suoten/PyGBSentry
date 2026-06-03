<template>
  <div class="app-page h-full flex flex-col">
    <PageHeader :title="t('gis.title')" :description="t('gis.description')" />

    <div class="flex-1 relative overflow-hidden rounded-2xl" style="border: 1px solid var(--el-border-color-lighter); background: #0b1220">
      <div id="map" class="absolute inset-0"></div>

      <div v-if="thinnedHint" class="absolute bottom-14 left-4 px-2 py-1 rounded text-sm z-10" style="background: #fef3c7; color: #92400e">
        {{ thinnedHint }}
      </div>
    
    <!-- 图层控制 -->
    <div
      class="absolute bottom-4 left-4 px-3 py-2 z-10 flex flex-col gap-1 rounded-lg shadow-lg"
      style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter)"
    >
      <span class="text-xs font-semibold" style="color: var(--el-text-color-secondary)">图层控制</span>
      <el-checkbox v-model="layerVisible.base" @change="toggleBaseLayer" size="small">底图</el-checkbox>
      <el-checkbox v-model="layerVisible.markers" @change="toggleMarkersLayer" size="small">监控点位</el-checkbox>
    </div>

    <!-- 测距工具 -->
    <div
      class="absolute top-4 left-4 px-3 py-2 z-10 flex gap-2 items-center rounded-lg shadow-lg"
      style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter)"
    >
      <el-button-group size="small">
        <el-button :type="measureMode === 'line' ? 'primary' : 'default'" @click="toggleMeasure('line')">测距</el-button>
        <el-button :type="measureMode === 'area' ? 'primary' : 'default'" @click="toggleMeasure('area')">测面</el-button>
        <el-button v-if="measureMode" @click="toggleMeasure(null)">清除</el-button>
      </el-button-group>
      <span v-if="measureResult" class="text-sm font-mono ml-2" style="color: var(--el-text-color-regular)">{{ measureResult }}</span>
    </div>
    
    <!-- Map Config Panel -->
    <div
      class="absolute top-4 right-4 p-4 z-10 w-80 rounded-lg shadow-lg"
      style="background: rgba(255,255,255,.92); border: 1px solid var(--el-border-color-lighter)"
    >
      <div class="flex justify-between items-center mb-3">
        <h3 class="font-semibold" style="color: var(--el-text-color-regular)">地图设置</h3>
        <div class="flex items-center gap-2">
          <el-button link type="primary" size="small" @click="goMapConfig">地图配置</el-button>
          <el-button link type="primary" size="small" @click="saveConfig">保存当前视图</el-button>
        </div>
      </div>
      <el-alert
        v-if="showApiKeyAlert"
        type="warning"
        :closable="false"
        show-icon
        class="mb-3"
      >
        <template #title>
          当前地图方案未配置 API Key，部分底图可能无法加载
        </template>
        <template #default>
          <el-button link type="primary" size="small" @click="goMapConfig">去地图配置</el-button>
        </template>
      </el-alert>
      
      <el-form :model="config" size="small" label-position="top">
        <el-form-item :label="t('gis.mapScheme')">
          <el-select v-model="selectedProfileId" @change="onProfileChange" class="w-full">
            <el-option v-for="p in mapProfiles" :key="p.id" :label="`${p.name}${p.is_default ? '（默认）' : ''}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('gis.currentBaseMap')">
          <el-input :model-value="providerLabel" disabled />
        </el-form-item>

        <div class="grid grid-cols-2 gap-2">
          <el-form-item :label="t('gis.minZoom')">
            <el-input-number v-model="config.min_zoom" :min="0" :max="20" controls-position="right" class="w-full" />
          </el-form-item>
          <el-form-item :label="t('gis.maxZoom')">
            <el-input-number v-model="config.max_zoom" :min="0" :max="22" controls-position="right" class="w-full" />
          </el-form-item>
        </div>

        <el-form-item :label="t('gis.auxFunctions')">
          <el-checkbox v-model="overviewVisible" @change="toggleOverview">显示鹰眼概览图</el-checkbox>
        </el-form-item>
      </el-form>

      <div class="mt-4 pt-3" style="border-top: 1px solid var(--el-border-color-lighter)">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-semibold" style="color: var(--el-text-color-regular)">轨迹查询</span>
          <el-button link type="primary" size="small" @click="clearTrajectory">清除</el-button>
        </div>
        <el-form size="small" label-position="top">
          <el-form-item :label="t('common.device')">
            <el-select v-model="trajectoryForm.device_id" filterable :placeholder="t('common.selectDevice')" class="w-full">
              <el-option v-for="d in devicesForTrajectory" :key="d.gb_id" :label="`${d.name || d.gb_id}（${d.gb_id}）`" :value="d.gb_id" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('common.timeRange')">
            <el-date-picker v-model="trajectoryForm.range" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" class="w-full" />
          </el-form-item>
          <div class="grid grid-cols-2 gap-2">
            <el-button type="primary" :loading="trajectoryLoading" :disabled="!trajectoryForm.device_id" @click="loadTrajectory">查询轨迹</el-button>
            <el-button :loading="subscribeLoading" :disabled="!trajectoryForm.device_id" @click="subscribePosition">订阅定位</el-button>
          </div>
          <div v-if="trajectorySummary" class="mt-2 text-xs whitespace-pre-wrap" style="color: var(--el-text-color-secondary)">{{ trajectorySummary }}</div>
        </el-form>
      </div>
    </div>

    <!-- Video Popup -->
    <div id="popup" class="ol-popup" v-show="popupVisible">
      <div
        class="popup-header flex justify-between items-center px-3 py-2 rounded-t-lg"
        style="background: rgba(255,255,255,.94); color: var(--el-text-color-regular); border-bottom: 1px solid var(--el-border-color-lighter)"
      >
        <span class="font-bold truncate max-w-[240px]">{{ popupData.name }}</span>
        <el-icon class="cursor-pointer transition-colors" @click="closePopup"><Close /></el-icon>
      </div>
      <div class="px-3 py-2 flex items-center justify-between gap-2" style="background: rgba(255,255,255,.94); border-bottom: 1px solid var(--el-border-color-lighter)">
        <div class="flex items-center gap-2 flex-wrap">
          <el-button size="small" :loading="popupData.actionLoading" @click="popupSubscribePosition">订阅定位</el-button>
          <el-button size="small" type="primary" :loading="trajectoryLoading" @click="popupQueryTrajectory">轨迹查询</el-button>
          <el-button size="small" type="success" :disabled="!popupData.channel_id" @click="popupGoPlayback">设备回放</el-button>
          <el-button size="small" :loading="popupData.refreshPositionLoading" @click="popupRefreshPosition">刷新点位</el-button>
          <el-button size="small" :loading="popupData.refreshStreamLoading" :disabled="!popupData.channel_id" @click="popupRefreshStream">刷新视频</el-button>
          <el-button size="small" @click="popupCopyOpsInfo">复制排障信息</el-button>
          <el-checkbox v-model="channelFilters.onlineOnly" size="small">仅在线</el-checkbox>
          <el-checkbox v-model="channelFilters.hasAudioOnly" size="small">仅有音频</el-checkbox>
          <el-select
            v-if="filteredChannels.length"
            v-model="popupData.channel_id"
            filterable
            size="small"
            style="width: 240px"
            :placeholder="t('common.selectChannel')"
            @change="popupSelectChannel"
          >
            <el-option v-for="ch in filteredChannels" :key="ch.gb_id" :label="formatChannelLabel(ch)" :value="String(ch.gb_id || '')" />
          </el-select>
        </div>
        <div class="text-xs truncate" style="color: var(--el-text-color-secondary)">
          {{ popupMeta }}
        </div>
      </div>
      <div v-if="popupOpsDetail" class="px-3 py-2 text-xs whitespace-pre-wrap" style="background: rgba(255,255,255,.94); border-bottom: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-secondary)">
        {{ popupOpsDetail }}
      </div>
      <div class="popup-content w-[520px] h-[292px] bg-black rounded-b-lg overflow-hidden relative">
        <JessibucaPlayer 
          v-if="popupVisible && popupData.url" 
          :video-url="popupData.url"
          class="w-full h-full" 
        />
        <div v-else class="w-full h-full flex items-center justify-center text-white/30 bg-slate-950">
           <span v-if="popupData.loading" class="animate-pulse">正在请求视频流...</span>
           <span v-else>暂无视频信号</span>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, reactive, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { useRouter, useRoute } from 'vue-router'
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
import Polygon from 'ol/geom/Polygon'
import { Vector as VectorSource } from 'ol/source'
import Cluster from 'ol/source/Cluster'
import { Vector as VectorLayer } from 'ol/layer'
import { Icon, Style, Stroke, Fill, Circle, Text } from 'ol/style'
import Overlay from 'ol/Overlay'
import OverviewMap from 'ol/control/OverviewMap'
import Draw, { DrawEvent } from 'ol/interaction/Draw'
import type MapBrowserEvent from 'ol/MapBrowserEvent'
import type { Pixel } from 'ol/pixel'
import { getLength, getArea } from 'ol/sphere'
import { Close } from '@element-plus/icons-vue'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../utils/errorMessage'
import PageHeader from '../components/PageHeader.vue'
import { parseDeviceChannelsResponse } from '../utils/deviceApi'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const { t } = useI18n()  // FIXED: 国际化
const router = useRouter()
const route = useRoute()

// State
const layerVisible = ref({ base: true, markers: true })
const overviewVisible = ref(false)
const measureMode = ref<'line' | 'area' | null>(null)
const measureResult = ref('')
const thinnedHint = ref('')

// Config
const config = ref({
  id: '',
  name: '',
  provider: 'tianditu',
  api_key: '',
  vector_tile_url: '',
  center_lng: 116.404,
  center_lat: 39.915,
  zoom_level: 12,
  min_zoom: 1,
  max_zoom: 20
})
type MapProfile = {
  id?: string
  name?: string
  is_default?: boolean
  provider?: string
  api_key?: string
  [key: string]: unknown
}

type PopupChannel = {
  gb_id?: string
  channelId?: string
  id?: string
  name?: string
  status?: number
  has_audio?: boolean
}

const mapProfiles = ref<MapProfile[]>([])
const selectedProfileId = ref('')
const providersNeedApiKey = new Set(['tianditu', 'gaode', 'tencent', 'baidu'])
const providerLabel = computed(() => {
  const p = String(config.value.provider || '').toLowerCase()
  if (p === 'tianditu') return '天地图 (TianDiTu)'
  if (p === 'gaode') return '高德地图 (Gaode)'
  if (p === 'baidu') return '百度地图 (Baidu)'
  if (p === 'osm') return 'OpenStreetMap'
  if (p === 'vector') return '自定义矢量瓦片 (MVT)'
  return p || '-'
})
const showApiKeyAlert = computed(() => {
  const provider = String(config.value.provider || '').toLowerCase()
  if (!providersNeedApiKey.has(provider)) return false
  return !String(config.value.api_key || '').trim()
})

// Map Objects
let map: Map | null = null
type BaseMapLayer = TileLayer<OSM | XYZ> | VectorTileLayer<VectorTileSource>
let baseLayer: BaseMapLayer | null = null
let markerLayer: VectorLayer<VectorSource> | null = null
let markerSource: VectorSource | null = null
let trajectoryLayer: VectorLayer<VectorSource> | null = null
let trajectorySource: VectorSource | null = null
let popupOverlay: Overlay | null = null
let overviewControl: OverviewMap | null = null
let drawInteraction: Draw | null = null
let measureSource: VectorSource | null = null
let measureLayer: VectorLayer<VectorSource> | null = null

// Popup State
const popupVisible = ref(false)
const popupData = ref({
  name: '',
  url: '',
  loading: false,
  actionLoading: false,
  refreshPositionLoading: false,
  refreshStreamLoading: false,
  device_id: '',
  channel_id: '',
  channels: [] as PopupChannel[],
  status: null as number | null,
  longitude: null as number | null,
  latitude: null as number | null,
  time: '' as string | null,
  speed: null as number | null,
  direction: null as number | null,
  altitude: null as number | null,
  play_codec: '' as string | null,
  play_app: '' as string | null,
  play_stream: '' as string | null,
  last_play_attempt_time: '' as string | null,
  last_play_error_time: '' as string | null,
  last_play_error: '' as string | null,
  update_interval_seconds: null as number | null,
  stats_points: null as number | null,
  stats_start_time: '' as string | null,
  stats_end_time: '' as string | null
})
const popupMeta = ref('')
const popupOpsDetail = ref('')
let popupFeature: Feature | null = null
const channelFilters = reactive({ onlineOnly: false, hasAudioOnly: false })
const routeFocusDone = ref(false)

const filteredChannels = computed(() => {
  const list = Array.isArray(popupData.value.channels) ? popupData.value.channels : []
  return list.filter((ch: PopupChannel) => {
    if (channelFilters.onlineOnly && Number(ch?.status) !== 1) return false
    if (channelFilters.hasAudioOnly && !ch?.has_audio) return false
    return true
  })
})

const devicesForTrajectory = ref<Device[]>([])
const trajectoryForm = reactive<{ device_id: string; range: [Date, Date] | [] }>({ device_id: '', range: [] })
const trajectoryLoading = ref(false)
const trajectorySummary = ref('')
const subscribeLoading = ref(false)
const subscribeIntervalSeconds = ref(60)

// Initialization
const initMap = () => {
  // 1. Create Sources
  markerSource = new VectorSource()
  const clusterSource = new Cluster({
    distance: 50,
    source: markerSource,
  })
  markerLayer = new VectorLayer({
    source: clusterSource,
    style: (feature) => {
      const size = feature.get('features')?.length || 1
      if (size > 1) {
        return new Style({
          image: new Circle({
            radius: Math.min(20, 10 + Math.sqrt(size)),
            fill: new Fill({ color: 'rgba(59,130,246,0.8)' }),
            stroke: new Stroke({ color: '#fff', width: 2 })
          }),
          text: new Text({
            text: String(size),
            fill: new Fill({ color: '#fff' }),
            font: 'bold 12px sans-serif'
          })
        })
      }
      const singleFeature = feature.get('features')?.[0]
      if (singleFeature) {
        return singleFeature.getStyle()
      }
      return new Style({
        image: new Circle({ radius: 6, fill: new Fill({ color: '#3b82f6' }) })
      })
    },
    zIndex: 10
  })

  trajectorySource = new VectorSource()
  trajectoryLayer = new VectorLayer({
    source: trajectorySource,
    style: (feature) => {
      const kind = feature.get('kind')
      if (kind === 'trajectory-point') {
        return new Style({
          image: new Circle({
            radius: 4,
            fill: new Fill({ color: 'rgba(59,130,246,0.9)' }),
            stroke: new Stroke({ color: 'rgba(255,255,255,0.9)', width: 1 })
          })
        })
      }
      return new Style({
        stroke: new Stroke({ color: 'rgba(59,130,246,0.9)', width: 3 })
      })
    },
    zIndex: 15
  })

  measureSource = new VectorSource()
  measureLayer = new VectorLayer({
    source: measureSource,
    style: new Style({
      fill: new Fill({ color: 'rgba(255, 255, 255, 0.2)' }),
      stroke: new Stroke({ color: '#ffcc33', width: 2 }),
      image: new Circle({ radius: 7, fill: new Fill({ color: '#ffcc33' }) })
    }),
    zIndex: 20
  })

  // 2. Create Base Layer
  baseLayer = createBaseLayer()

  // 3. Create Overlay
  popupOverlay = new Overlay({
    element: document.getElementById('popup')!,
    autoPan: {
      animation: { duration: 250 }
    },
    positioning: 'bottom-center',
    stopEvent: true,
    offset: [0, -10]
  })

  // 4. Create Overview
  overviewControl = new OverviewMap({
    collapsed: false,
    collapsible: true,
    layers: [ createBaseLayer(true) ] // Simplified layer for overview
  })

  // 5. Create Map
  map = new Map({
    target: 'map',
    layers: [baseLayer, markerLayer, trajectoryLayer, measureLayer],
    view: new View({
      center: fromLonLat([config.value.center_lng, config.value.center_lat]),
      zoom: config.value.zoom_level,
      minZoom: config.value.min_zoom,
      maxZoom: config.value.max_zoom
    }),
    overlays: [popupOverlay],
    controls: [] // Reset default controls if needed, but we keep defaults usually
  })

  if (overviewVisible.value) {
    map.addControl(overviewControl)
  }

  // 6. Bind Events
  map.on('click', handleMapClick)
  
  // 7. Initial Load
  loadDevices()
}

const createBaseLayer = (isOverview = false): BaseMapLayer => {
  const provider = config.value.provider
  const key = config.value.api_key || ''
  
  if (provider === 'vector') {
    const url = config.value.vector_tile_url || 'https://basemaps.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/tile/{z}/{y}/{x}.pbf'
    return new VectorTileLayer({
      source: new VectorTileSource({
        format: new MVT(),
        url: url
      }),
      visible: layerVisible.value.base
    })
  } else if (provider === 'gaode') {
    return new TileLayer({
      source: new XYZ({
        url: 'http://wprd0{1-4}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}'
      }),
      visible: layerVisible.value.base
    })
  } else if (provider === 'baidu') {
    // 百度地图瓦片
    const ak = key
    if (!ak) {
      ElMessage.warning(t('gis.baiduApiKeyMissing'))
      return new TileLayer({ source: new OSM(), visible: layerVisible.value.base })
    }
    return new TileLayer({
      source: new XYZ({
        // 使用百度地图开放平台瓦片服务
        url: `https://maponline2.bdimg.com/tile/?qt=tile&x={x}&y={y}&z={z}&styles=pl&scaler=1&ak=${ak}`,
        projection: 'BD-MERCATOR'
      }),
      visible: layerVisible.value.base
    })
  } else if (provider === 'osm') {
    return new TileLayer({
      source: new OSM(),
      visible: layerVisible.value.base
    })
  } else {
    // TianDiTu
    const tk = key || ''
    return new TileLayer({
      source: new XYZ({
        url: `https://t0.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILECOL={x}&TILEROW={y}&TILEMATRIX={z}&tk=${tk}`
      }),
      visible: layerVisible.value.base
    })
  }
}

const updateMapLayer = () => {
  if (!map) return
  
  const newLayer = createBaseLayer()
  
  // Replace base layer (index 0)
  const layers = map.getLayers()
  layers.setAt(0, newLayer)
  baseLayer = newLayer
  
  // Update overview if exists
  if (overviewControl) {
    // OverviewMap is tricky to update dynamically without recreating, 
    // but for now we focus on main map.
    // Ideally we recreate the control.
    map.removeControl(overviewControl)
    overviewControl = new OverviewMap({
      collapsed: false,
      layers: [ createBaseLayer(true) ]
    })
    if (overviewVisible.value) map.addControl(overviewControl)
  }
}

const toggleBaseLayer = () => {
  if (baseLayer) baseLayer.setVisible(layerVisible.value.base)
}

const toggleMarkersLayer = () => {
  if (markerLayer) markerLayer.setVisible(layerVisible.value.markers)
}

const toggleOverview = () => {
  if (!map) return
  if (overviewVisible.value) {
    if (!overviewControl) {
       overviewControl = new OverviewMap({ collapsed: false, layers: [ createBaseLayer(true) ] })
    }
    map.addControl(overviewControl)
  } else {
    if (overviewControl) map.removeControl(overviewControl)
  }
}

const toggleMeasure = (mode: 'line' | 'area' | null) => {
  measureMode.value = mode
  measureResult.value = ''
  
  if (drawInteraction) {
    map?.removeInteraction(drawInteraction)
    drawInteraction = null
  }
  
  if (mode === null) {
    measureSource?.clear()
    return
  }
  
  if (!map || !measureSource) return
  
  drawInteraction = new Draw({
    source: measureSource,
    type: mode === 'line' ? 'LineString' : 'Polygon',
    style: new Style({
      fill: new Fill({ color: 'rgba(255, 255, 255, 0.2)' }),
      stroke: new Stroke({ color: 'rgba(0, 0, 0, 0.5)', lineDash: [10, 10], width: 2 }),
      image: new Circle({ radius: 5, stroke: new Stroke({ color: 'rgba(0, 0, 0, 0.7)' }), fill: new Fill({ color: 'rgba(255, 255, 255, 0.2)' }) })
    })
  })
  
  drawInteraction.on('drawend', (evt: DrawEvent) => {
    const geom = evt.feature.getGeometry()
    if (mode === 'line') {
      const length = getLength(geom as LineString, { radius: 6371008.8 })
      measureResult.value = length > 1000 ? `${(length / 1000).toFixed(2)} km` : `${length.toFixed(1)} m`
    } else {
      const area = getArea(geom as Polygon, { radius: 6371008.8 })
      measureResult.value = area > 1000000 ? `${(area / 1000000).toFixed(2)} km²` : `${area.toFixed(1)} m²`
    }
    // Auto finish
    setTimeout(() => {
        map?.removeInteraction(drawInteraction!)
        drawInteraction = null
        measureMode.value = null // Reset mode but keep result visible until cleared
    }, 100)
  })
  
  map.addInteraction(drawInteraction)
}

type MapClickLike = MapBrowserEvent | { pixel: Pixel }

const handleMapClick = async (evt: MapClickLike) => {
  if (drawInteraction) return // Don't popup when measuring
  
  const feature = map?.forEachFeatureAtPixel(evt.pixel, (f) => f)
  if (feature && feature.get('device')) {
    const device = feature.get('device')
    const geom = feature.getGeometry() as Point
    popupFeature = feature instanceof Feature ? feature : null
    
    popupData.value = {
      name: device.name || device.gb_id,
      url: '',
      loading: true,
      actionLoading: false,
      refreshPositionLoading: false,
      refreshStreamLoading: false,
      device_id: String(device.gb_id || ''),
      channel_id: '',
      channels: [],
      status: device.status != null ? Number(device.status) : null,
      longitude: device.longitude != null ? Number(device.longitude) : null,
      latitude: device.latitude != null ? Number(device.latitude) : null,
      time: device.time ? String(device.time) : null,
      speed: device.speed != null ? Number(device.speed) : null,
      direction: device.direction != null ? Number(device.direction) : null,
      altitude: device.altitude != null ? Number(device.altitude) : null,
      play_codec: null,
      play_app: null,
      play_stream: null,
      last_play_attempt_time: null,
      last_play_error_time: null,
      last_play_error: null,
      update_interval_seconds: null,
      stats_points: null,
      stats_start_time: null,
      stats_end_time: null
    }
    popupMeta.value = buildPopupMeta()
    popupOpsDetail.value = buildPopupOpsDetail()
    popupVisible.value = true
    popupOverlay?.setPosition(geom.getCoordinates())
    
    try {
      const chRes = await api.get(`/api/v1/devices/${device.gb_id}/channels`)
      const chs = parseDeviceChannelsResponse(chRes.data)
      popupData.value.channels = normalizeChannels(chs)
      if (chs.length > 0) {
        const first = popupData.value.channels[0]
        popupData.value.channel_id = String(first?.gb_id || '')
        await playPopupStream(String(device.gb_id || ''), String(first?.gb_id || ''))
      }
    } catch (e: unknown) {
      const friendly = getPlayFriendly(e)
      ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    } finally {
      popupData.value.loading = false
      popupMeta.value = buildPopupMeta()
      popupOpsDetail.value = buildPopupOpsDetail()
      await loadPopupOpsStats()
    }
  } else {
    closePopup()
  }
}

const closePopup = () => {
  popupVisible.value = false
  popupOverlay?.setPosition(undefined)
  popupData.value.url = ''
  popupMeta.value = ''
  popupOpsDetail.value = ''
  popupFeature = null
}

const formatAge = (iso: string | null) => {
  if (!iso) return ''
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return ''
  const diff = Date.now() - t.getTime()
  if (!Number.isFinite(diff) || diff < 0) return ''
  const s = Math.floor(diff / 1000)
  if (s < 30) return '刚刚'
  if (s < 60) return `${s}s前`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m前`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h}h前`
  const d = Math.floor(h / 24)
  return `${d}d前`
}

const buildPopupMeta = () => {
  const statusText = Number(popupData.value.status) === 1 ? '在线' : Number(popupData.value.status) === 0 ? '离线' : ''
  const ageText = formatAge(popupData.value.time)
  const timeText = popupData.value.time ? `定位：${popupData.value.time}` : ''
  const coordText =
    Number.isFinite(popupData.value.longitude) && Number.isFinite(popupData.value.latitude)
      ? `${Number(popupData.value.longitude).toFixed(6)}, ${Number(popupData.value.latitude).toFixed(6)}`
      : ''
  return [statusText, ageText, timeText, coordText].filter(Boolean).join(' | ')
}

const buildPopupOpsDetail = () => {
  const source = '来源：GB28181 MobilePosition'
  const ch = (popupData.value.channels || []).find((x: PopupChannel) => String(x?.gb_id || '') === String(popupData.value.channel_id || ''))
  const channelLine = ch ? `通道：${formatChannelLabel(ch)}` : ''
  const speed = popupData.value.speed != null ? `速度：${popupData.value.speed}` : ''
  const direction = popupData.value.direction != null ? `航向：${popupData.value.direction}°` : ''
  const altitude = popupData.value.altitude != null ? `海拔：${popupData.value.altitude}` : ''
  const codecLine =
    popupData.value.play_codec || popupData.value.play_app || popupData.value.play_stream
      ? `码流：${[popupData.value.play_codec || '', popupData.value.play_app && popupData.value.play_stream ? `${popupData.value.play_app}/${popupData.value.play_stream}` : '']
          .filter(Boolean)
          .join(' ')}`
      : ''
  const freq =
    popupData.value.update_interval_seconds != null && popupData.value.update_interval_seconds > 0
      ? `更新频率：约 ${Math.round(popupData.value.update_interval_seconds)}s/次（近${popupData.value.stats_points}点）`
      : ''
  const span =
    popupData.value.stats_start_time && popupData.value.stats_end_time
      ? `轨迹跨度：${popupData.value.stats_start_time} → ${popupData.value.stats_end_time}`
      : ''
  const lastAttempt = popupData.value.last_play_attempt_time ? `最近拉流：${popupData.value.last_play_attempt_time}` : ''
  const lastError =
    popupData.value.last_play_error && popupData.value.last_play_error_time
      ? `最近错误：${popupData.value.last_play_error_time} ${popupData.value.last_play_error}`
      : popupData.value.last_play_error
        ? `最近错误：${popupData.value.last_play_error}`
        : ''
  return [source, channelLine, codecLine, speed, direction, altitude, freq, span, lastAttempt, lastError].filter(Boolean).join('\n')
}

const makeDeviceMarkerStyle = (status: unknown) => {
  return new Style({
    image: new Icon({
      src: '/camera-icon.png',
      scale: 0.05,
      color: Number(status) === 1 ? '#67C23A' : '#F56C6C',
      anchor: [0.5, 1]
    })
  })
}

const formatChannelLabel = (ch: PopupChannel) => {
  const name = String(ch?.name || ch?.gb_id || '').trim()
  const id = String(ch?.gb_id || '').trim()
  const statusText = Number(ch?.status) === 1 ? '在线' : Number(ch?.status) === 0 ? '离线' : ''
  return `${name}${id && name !== id ? `（${id}）` : ''}${statusText ? ` [${statusText}]` : ''}`
}

const normalizeChannels = (channels: PopupChannel[]) => {
  const list = Array.isArray(channels) ? channels.slice() : []
  list.sort((a: PopupChannel, b: PopupChannel) => {
    const sa = Number(a?.status) === 1 ? 1 : 0
    const sb = Number(b?.status) === 1 ? 1 : 0
    if (sa !== sb) return sb - sa
    const aa = a?.has_audio ? 1 : 0
    const ab = b?.has_audio ? 1 : 0
    if (aa !== ab) return ab - aa
    const na = String(a?.name || '').toLowerCase()
    const nb = String(b?.name || '').toLowerCase()
    if (na !== nb) return na.localeCompare(nb)
    return String(a?.gb_id || '').localeCompare(String(b?.gb_id || ''))
  })
  return list
}

const getPlayFriendly = (e: unknown) => {
  const status = axios.isAxiosError(e) ? Number(e.response?.status || 0) : 0
  const detailStr = getApiErrorMessage(e, '')
  if (status === 401 || status === 403) return { message: '无权限播放该通道', suggestion: '确认账号权限/租户是否正确' }
  if (status === 404) return { message: '设备或通道不存在', suggestion: '检查设备ID/通道ID是否正确' }
  if (status === 409) return { message: '设备忙或正在会话中', suggestion: '稍后重试或先停止现有会话' }
  if (status === 503) return { message: '流媒体服务不可用', suggestion: '检查流媒体服务/网关是否在线' }
  if (detailStr.includes('离线') || detailStr.includes('offline')) return { message: '设备/通道离线，无法拉流', suggestion: '先恢复在线或切换在线通道' }
  if (detailStr.includes('超时') || detailStr.includes('timeout')) return { message: '拉流超时', suggestion: '检查网络与SIP链路，或尝试刷新视频' }
  return { message: '拉流失败', suggestion: detailStr ? detailStr : '检查设备在线与通道状态' }
}

const recordPlayFailure = (e: unknown) => {
  const friendly = getPlayFriendly(e)
  popupData.value.last_play_error_time = new Date().toISOString()
  popupData.value.last_play_error = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message
  popupOpsDetail.value = buildPopupOpsDetail()
  return friendly
}

const playPopupStream = async (deviceId: string, channelId: string) => {
  const did = String(deviceId || '').trim()
  const cid = String(channelId || '').trim()
  if (!did || !cid) return
  popupData.value.last_play_attempt_time = new Date().toISOString()
  const playRes = await api.post(
    `/api/v1/stream/play/${did}/${cid}`,
    null,
    { params: { stream_type: 'auto' } }
  )
  const webrtc = String(playRes.data?.webrtc || '')
  const flv = String(playRes.data?.flv || '')
  const hls = String(playRes.data?.hls || '')
  popupData.value.play_codec = playRes.data?.codec != null ? String(playRes.data.codec) : null
  popupData.value.play_app = playRes.data?.app != null ? String(playRes.data.app) : null
  popupData.value.play_stream = playRes.data?.stream != null ? String(playRes.data.stream) : null
  popupData.value.url = flv || webrtc || hls || ''
  popupData.value.last_play_error_time = null
  popupData.value.last_play_error = null
}

const popupSelectChannel = async () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  const channelId = String(popupData.value.channel_id || '').trim()
  if (!deviceId || !channelId) return
  popupData.value.refreshStreamLoading = true
  popupData.value.loading = true
  try {
    await playPopupStream(deviceId, channelId)
    popupMeta.value = buildPopupMeta()
    popupOpsDetail.value = buildPopupOpsDetail()
  } catch (e: unknown) {
    const friendly = recordPlayFailure(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    popupData.value.loading = false
    popupData.value.refreshStreamLoading = false
  }
}

watch(
  () => filteredChannels.value.map((c: PopupChannel) => String(c?.gb_id || '')),
  (ids) => {
    if (!popupVisible.value) return
    if (!ids.length) return
    const cur = String(popupData.value.channel_id || '')
    if (!cur || !ids.includes(cur)) {
      popupData.value.channel_id = ids[0]
      popupMeta.value = buildPopupMeta()
      popupOpsDetail.value = buildPopupOpsDetail()
    }
  },
  { immediate: true }
)

const loadPopupOpsStats = async () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  if (!deviceId) return
  try {
    const end = new Date()
    const start = new Date(end.getTime() - 6 * 60 * 60 * 1000)
    const res = await api.get('/api/v1/map/trajectory', {
      params: { device_id: deviceId, start_time: start.toISOString(), end_time: end.toISOString(), limit: 200 }
    })
    const rows = Array.isArray(res.data) ? res.data : []
    const times = rows.map((r: Record<string, unknown>) => String(r?.time || '')).filter((t: string) => !!t)
    if (times.length >= 2) {
      const parsed = times.map((t: string) => new Date(t)).filter((d: Date) => !Number.isNaN(d.getTime()))
      if (parsed.length >= 2) {
        const deltas: number[] = []
        for (let i = 1; i < parsed.length; i++) {
          const ds = (parsed[i].getTime() - parsed[i - 1].getTime()) / 1000
          if (Number.isFinite(ds) && ds > 0) deltas.push(ds)
        }
        const avg = deltas.length ? deltas.reduce((a, b) => a + b, 0) / deltas.length : 0
        popupData.value.update_interval_seconds = avg > 0 ? avg : null
        popupData.value.stats_points = parsed.length
        popupData.value.stats_start_time = parsed[0].toISOString()
        popupData.value.stats_end_time = parsed[parsed.length - 1].toISOString()
      }
    }
  } catch (e) {
    console.warn('GisMap: failed to load map config', e)  // FIXED: 空catch块→日志记录
    popupMeta.value = buildPopupMeta()
    popupOpsDetail.value = buildPopupOpsDetail()
  }
}

const popupRefreshPosition = async () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  if (!deviceId) {
    ElMessage.warning(t('gis.missingDeviceId'))
    return
  }
  popupData.value.refreshPositionLoading = true
  try {
    const res = await api.get('/api/v1/map/device-latest-position', { params: { device_id: deviceId } })
    const row = res.data || {}
    popupData.value.longitude = row.longitude != null ? Number(row.longitude) : null
    popupData.value.latitude = row.latitude != null ? Number(row.latitude) : null
    popupData.value.time = row.time ? String(row.time) : null
    popupData.value.status = row.status
    popupData.value.speed = row.speed
    popupData.value.direction = row.direction
    popupData.value.altitude = row.altitude
    if (popupFeature && popupData.value.longitude != null && popupData.value.latitude != null) {
      const geom = popupFeature.getGeometry() as Point
      geom.setCoordinates(fromLonLat([Number(popupData.value.longitude), Number(popupData.value.latitude)]))
      popupOverlay?.setPosition(geom.getCoordinates())
      popupFeature.set('device', { ...(popupFeature.get('device') || {}), ...row })
      popupFeature.setStyle(makeDeviceMarkerStyle(row.status))
    }
    popupMeta.value = buildPopupMeta()
    popupOpsDetail.value = buildPopupOpsDetail()
    ElMessage.success(t('gis.pointRefreshed'))
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('gis.refreshFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('gis.refreshFailed'))
  } finally {
    popupData.value.refreshPositionLoading = false
  }
}

const popupRefreshStream = async () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  const channelId = String(popupData.value.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('gis.missingDeviceChannel'))
    return
  }
  popupData.value.refreshStreamLoading = true
  popupData.value.loading = true
  try {
    await playPopupStream(deviceId, channelId)
    popupOpsDetail.value = buildPopupOpsDetail()
    ElMessage.success(t('gis.streamRefreshed'))
  } catch (e: unknown) {
    const friendly = recordPlayFailure(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    popupData.value.loading = false
    popupData.value.refreshStreamLoading = false
  }
}

const buildOpsCopyText = () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  const channelId = String(popupData.value.channel_id || '').trim()
  const ch = (popupData.value.channels || []).find((x: PopupChannel) => String(x?.gb_id || '') === channelId)
  const header = `PyGBSentry GIS 排障信息`
  const lines = [
    header,
    `复制时间：${new Date().toISOString()}`,
    deviceId ? `device_id：${deviceId}` : '',
    popupData.value.name ? `device_name：${popupData.value.name}` : '',
    channelId ? `channel_id：${channelId}` : '',
    ch ? `channel_name：${String(ch?.name || '')}` : '',
    popupData.value.status != null ? `device_status：${Number(popupData.value.status) === 1 ? 'online' : 'offline'}` : '',
    popupData.value.time ? `last_position_time：${popupData.value.time}` : '',
    popupData.value.longitude != null && popupData.value.latitude != null ? `position：${popupData.value.longitude}, ${popupData.value.latitude}` : '',
    popupData.value.speed != null ? `speed：${popupData.value.speed}` : '',
    popupData.value.direction != null ? `direction：${popupData.value.direction}` : '',
    popupData.value.altitude != null ? `altitude：${popupData.value.altitude}` : '',
    popupData.value.play_codec ? `codec：${popupData.value.play_codec}` : '',
    popupData.value.play_app && popupData.value.play_stream ? `stream：${popupData.value.play_app}/${popupData.value.play_stream}` : '',
    popupData.value.last_play_attempt_time ? `last_play_attempt：${popupData.value.last_play_attempt_time}` : '',
    popupData.value.last_play_error_time ? `last_play_error_time：${popupData.value.last_play_error_time}` : '',
    popupData.value.last_play_error ? `last_play_error：${popupData.value.last_play_error}` : ''
  ].filter(Boolean)
  return lines.join('\n')
}

const popupCopyOpsInfo = async () => {
  const text = buildOpsCopyText()
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('gis.troubleshootCopied'))
  } catch (e) {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.setAttribute('readonly', 'true')
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      ElMessage.success(t('gis.troubleshootCopied'))
    } catch (e2) {
      ElMessage.error(t('gis.copyFailed'))
    }
  }
}

const setTrajectoryRangeAround = (centerIso: string | null, minutes: number) => {
  const center = centerIso ? new Date(centerIso) : new Date()
  const t = Number.isNaN(center.getTime()) ? new Date() : center
  const m = Math.min(24 * 60, Math.max(1, Math.floor(minutes)))
  const start = new Date(t.getTime() - m * 60 * 1000)
  const end = new Date(t.getTime() + m * 60 * 1000)
  trajectoryForm.range = [start, end]
}

const popupSubscribePosition = async () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  if (!deviceId) {
    ElMessage.warning(t('gis.missingDeviceIdSubscribe'))
    return
  }
  popupData.value.actionLoading = true
  try {
    await api.post('/api/v1/map/mobile-position/subscribe', {
      device_id: deviceId,
      interval: subscribeIntervalSeconds.value
    })
    ElMessage.success(t('gis.locationSubscribed'))
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('gis.subscribeFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('gis.subscribeFailed'))
  } finally {
    popupData.value.actionLoading = false
  }
}

const popupQueryTrajectory = async () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  if (!deviceId) {
    ElMessage.warning(t('gis.missingDeviceIdTrack'))
    return
  }
  trajectoryForm.device_id = deviceId
  if (!Array.isArray(trajectoryForm.range) || trajectoryForm.range.length < 2) {
    setTrajectoryRangeAround(popupData.value.time, 60)
  }
  await loadTrajectory()
}

const popupGoPlayback = () => {
  const deviceId = String(popupData.value.device_id || '').trim()
  const channelId = String(popupData.value.channel_id || '').trim()
  if (!deviceId || !channelId) {
    ElMessage.warning(t('gis.missingDeviceChannelPlayback'))
    return
  }
  const time = popupData.value.time ? String(popupData.value.time) : new Date().toISOString()
  router.push({
    path: '/devices',
    query: { device_id: deviceId, channel_id: channelId, time, tab: 'timeline', window_minutes: '30' }
  })
}

const loadDevices = async () => {
  try {
    const res = await api.get('/api/v1/map/devices-latest-positions', { params: { limit: 2000 } })
    let items = Array.isArray(res.data) ? res.data : []
    
    thinnedHint.value = ''
    // Simple thinning for performance if too many points
    if (items.length > 1000) {
        thinnedHint.value = `显示 ${items.length} 个设备 (已优化)`
    }

    devicesForTrajectory.value = items
    
    markerSource?.clear()
    
    // Batch add features
    const features: Feature[] = []
    items.forEach((dev: Record<string, unknown>) => {
      const lng = Number(dev.longitude)
      const lat = Number(dev.latitude)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return
      const feature = new Feature(new Point(fromLonLat([lng, lat])))
      feature.set('device', dev)
      
      feature.setStyle(makeDeviceMarkerStyle(dev.status))
      features.push(feature)
    })
    
    markerSource?.addFeatures(features)
    await focusDeviceFromRouteQuery()
    
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('gis.loadDevicesFailed'))
    ElMessage.warning(typeof msg === 'string' ? msg : t('gis.loadDevicesFailed'))
  }
}

const focusDeviceFromRouteQuery = async () => {
  if (routeFocusDone.value || !map || !markerSource) return
  const q = route.query || {}
  const target = String(q.device_id || q.deviceId || '').trim()
  if (!target) {
    routeFocusDone.value = true
    return
  }
  const feature = markerSource
    .getFeatures()
    .find((f: Feature) => String(f?.get?.('device')?.gb_id || '').trim() === target)
  if (!feature) return
  const geom = feature.getGeometry() as Point
  const coord = geom.getCoordinates()
  map.getView().animate({ center: coord, zoom: Math.max(map.getView().getZoom() || 12, 15), duration: 350 })
  const pixel = map.getPixelFromCoordinate(coord)
  await handleMapClick({ pixel })
  routeFocusDone.value = true
}

const clearTrajectory = () => {
  trajectorySource?.clear()
  trajectorySummary.value = ''
}

const loadTrajectory = async () => {
  if (!trajectoryForm.device_id) return
  trajectoryLoading.value = true
  try {
    const params: Record<string, string | number> = { device_id: trajectoryForm.device_id, limit: 5000 }
    if (Array.isArray(trajectoryForm.range) && trajectoryForm.range.length >= 2) {
      const [s, e] = trajectoryForm.range as [Date, Date]
      params.start_time = s.toISOString()
      params.end_time = e.toISOString()
    }
    const res = await api.get('/api/v1/map/trajectory', { params })
    const rows = Array.isArray(res.data) ? res.data : []
    clearTrajectory()
    if (!rows.length) {
      trajectorySummary.value = '暂无轨迹点'
      return
    }
    const coords: number[][] = []
    const pointFeatures: Feature[] = []
    for (const r of rows) {
      const lng = Number(r.lng)
      const lat = Number(r.lat)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
      const c = fromLonLat([lng, lat])
      coords.push(c)
      const f = new Feature(new Point(c))
      f.set('kind', 'trajectory-point')
      f.set('time', r.time)
      pointFeatures.push(f)
    }
    if (coords.length >= 2) {
      const line = new Feature(new LineString(coords))
      line.set('kind', 'trajectory-line')
      trajectorySource?.addFeature(line)
      trajectorySource?.addFeatures(pointFeatures)
      const lengthM = getLength(line.getGeometry() as LineString)
      const first = rows[0]?.time || ''
      const last = rows[rows.length - 1]?.time || ''
      trajectorySummary.value = `点数：${coords.length}\n距离：${(lengthM / 1000).toFixed(2)} km\n起：${first}\n止：${last}`
      const extent = (line.getGeometry() as LineString).getExtent()
      map?.getView().fit(extent, { padding: [80, 80, 80, 80], duration: 250, maxZoom: 18 })
    } else {
      trajectorySource?.addFeatures(pointFeatures)
      trajectorySummary.value = `点数：${coords.length}`
    }
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('gis.trackQueryFailed'))
    ElMessage.warning(typeof msg === 'string' ? msg : t('gis.trackQueryFailed'))
  } finally {
    trajectoryLoading.value = false
  }
}

const subscribePosition = async () => {
  if (!trajectoryForm.device_id) return
  subscribeLoading.value = true
  try {
    await api.post('/api/v1/map/mobile-position/subscribe', {
      device_id: trajectoryForm.device_id,
      interval: subscribeIntervalSeconds.value
    })
    ElMessage.success(t('gis.locationSubscribed'))
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('gis.subscribeFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('gis.subscribeFailed'))
  } finally {
    subscribeLoading.value = false
  }
}

const applyConfig = (cfg: MapProfile) => {
  config.value = { ...config.value, ...cfg }
  selectedProfileId.value = String(cfg?.id || '')
}

const fetchMapProfiles = async () => {
  try {
    const res = await api.get('/api/v1/map/providers')
    const items = Array.isArray(res?.data?.items) ? res.data.items : []
    mapProfiles.value = items
    if (items.length) {
      const active = items.find((x: MapProfile) => x.is_default) || items[0]
      applyConfig(active)
    }
  } catch (e: unknown) {
    ElMessage.error(t('gis.loadConfigFailed'))
  } // FIXED: 裸await api调用包裹try-catch
}

const onProfileChange = (id: string) => {
  const hit = mapProfiles.value.find((x: MapProfile) => String(x.id) === String(id))
  if (!hit) return
  applyConfig(hit)
  if (providersNeedApiKey.has(String(hit?.provider || '').toLowerCase()) && !String(hit?.api_key || '').trim()) {
    ElMessage.warning('当前地图方案未配置 API Key，可点“地图配置”前往设置')
  }
  updateMapLayer()
  const view = map?.getView()
  if (view) {
    view.setMinZoom(Number(config.value.min_zoom || 1))
    view.setMaxZoom(Number(config.value.max_zoom || 20))
    view.animate({
      center: fromLonLat([Number(config.value.center_lng || 116.404), Number(config.value.center_lat || 39.915)]),
      zoom: Number(config.value.zoom_level || 12),
      duration: 350
    })
  }
}

const goMapConfig = () => {
  router.push('/map-providers')
}

const saveConfig = async () => {
  if (!map) return
  const view = map.getView()
  const center = toLonLat(view.getCenter() as number[])
  
  config.value.center_lng = center[0]
  config.value.center_lat = center[1]
  config.value.zoom_level = Math.round(view.getZoom() || 12)
  
  try {
    await api.post('/api/v1/map', {
      ...config.value,
      profile_id: selectedProfileId.value || undefined
    })
    await fetchMapProfiles()
    ElMessage.success(t('gis.configSaved'))
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('gis.saveFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('gis.saveFailed'))
  }
}

onMounted(async () => {
  try {
    await fetchMapProfiles()
  } catch (_e) {
    console.warn('GisMap: failed to fetch map profiles', _e)  // FIXED: 空catch块→日志记录
  }
  initMap()
})

onBeforeUnmount(() => {
  if (drawInteraction && map) {
    map.removeInteraction(drawInteraction)
    drawInteraction = null
  }
  if (overviewControl && map) {
    map.removeControl(overviewControl)
    overviewControl = null
  }
  if (popupOverlay && map) {
    map.removeOverlay(popupOverlay)
    popupOverlay = null
  }
  markerSource?.clear()
  trajectorySource?.clear()
  measureSource?.clear()
  if (map) {
    map.setTarget(undefined)
    map.dispose()
    map = null
  }
  baseLayer = null
  markerLayer = null
  markerSource = null
  trajectoryLayer = null
  trajectorySource = null
  measureLayer = null
  measureSource = null
})
</script>

<style scoped>
.ol-popup {
  position: absolute;
  border-radius: 8px;
  filter: drop-shadow(0 1px 4px rgba(0,0,0,0.5));
}
.ol-popup:after, .ol-popup:before {
  top: 100%;
  border: solid transparent;
  content: " ";
  height: 0;
  width: 0;
  position: absolute;
  pointer-events: none;
}
.ol-popup:after {
  border-top-color: rgba(255,255,255,.94);
  border-width: 10px;
  left: 50%;
  margin-left: -10px;
}
</style>
