import { ref, onMounted, onBeforeUnmount } from 'vue'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import XYZ from 'ol/source/XYZ'
import { fromLonLat } from 'ol/proj'
import { Vector as VectorSource } from 'ol/source'
import { Vector as VectorLayer } from 'ol/layer'
import Cluster from 'ol/source/Cluster'
import { Style, Fill, Stroke, Circle, Text } from 'ol/style'
import Overlay from 'ol/Overlay'
import { ElMessage } from 'element-plus'
import i18n from '@/locales'

const t = i18n.global.t

export interface MapConfig {
  provider: string
  api_key: string
  center_lng: number
  center_lat: number
  zoom_level: number
  min_zoom: number
  max_zoom: number
  vector_tile_url?: string
}

export function useOlMap(targetId: string, config: MapConfig) {
  let map: Map | null = null
  let baseLayer: TileLayer | null = null
  const markerSource = ref<VectorSource | null>(null)
  const markerLayer = ref<VectorLayer | null>(null)
  const popupOverlay = ref<Overlay | null>(null)

  const createBaseLayer = (key: string = ''): TileLayer => {
    const provider = config.provider
    if (provider === 'gaode') {
      return new TileLayer({
        source: new XYZ({
          url: 'http://wprd0{1-4}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}'
        })
      })
    } else if (provider === 'baidu') {
      if (!key) {
        ElMessage.warning(t('gis.baiduApiKeyMissing'))
        return new TileLayer({ source: new OSM() })
      }
      return new TileLayer({
        source: new XYZ({
          url: `https://maponline2.bdimg.com/tile/?qt=tile&x={x}&y={y}&z={z}&styles=pl&scaler=1&ak=${key}`
        })
      })
    } else if (provider === 'tianditu') {
      if (!key) {
        ElMessage.warning(t('gis.tiandituApiKeyMissing'))
        return new TileLayer({ source: new OSM() })
      }
      return new TileLayer({
        source: new XYZ({
          url: `http://t0.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=${key}`
        })
      })
    }
    return new TileLayer({ source: new OSM() })
  }

  const initMap = () => {
    const src = new VectorSource()
    markerSource.value = src

    const clusterSource = new Cluster({ distance: 50, source: src })
    markerLayer.value = new VectorLayer({
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
            text: new Text({ text: String(size), fill: new Fill({ color: '#fff' }), font: 'bold 12px sans-serif' })
          })
        }
        const singleFeature = feature.get('features')?.[0]
        if (singleFeature) return singleFeature.getStyle()
        return new Style({ image: new Circle({ radius: 6, fill: new Fill({ color: '#3b82f6' }) }) })
      },
      zIndex: 10
    })

    baseLayer = createBaseLayer(config.api_key)

    popupOverlay.value = new Overlay({
      element: document.getElementById('popup')!,
      autoPan: { animation: { duration: 250 } },
      positioning: 'bottom-center',
      stopEvent: true,
    })

    map = new Map({
      target: targetId,
      layers: [baseLayer, markerLayer.value as VectorLayer],
      view: new View({
        center: fromLonLat([config.center_lng, config.center_lat]),
        zoom: config.zoom_level,
        minZoom: config.min_zoom,
        maxZoom: config.max_zoom
      }),
      overlays: popupOverlay.value ? [popupOverlay.value as Overlay] : [],
      controls: []
    })
  }

  const destroyMap = () => {
    markerSource.value?.clear()
    if (map) {
      map.setTarget(undefined)
      map.dispose()
      map = null
    }
    baseLayer = null
    markerLayer.value = null
    markerSource.value = null
    popupOverlay.value = null
  }

  const getMap = () => map

  return { map: getMap, markerSource, markerLayer, popupOverlay, initMap, destroyMap, createBaseLayer }
}
