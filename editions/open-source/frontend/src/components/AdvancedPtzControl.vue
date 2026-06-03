<template>
  <div class="ptz-wrap">
    <div class="ptz-left">
      <div class="ptz-control-grid">
        <div>
          <div class="control-wrapper">
            <div
              class="control-btn control-top"
              :class="{ 'is-pressed': pressedAction === 'up' }"
              @mousedown="onActionDown('up', () => ptzCamera('up'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon><CaretTop /></el-icon>
              <div class="control-inner-btn control-inner" />
            </div>
            <div
              class="control-btn control-left"
              :class="{ 'is-pressed': pressedAction === 'left' }"
              @mousedown="onActionDown('left', () => ptzCamera('left'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon><CaretLeft /></el-icon>
              <div class="control-inner-btn control-inner" />
            </div>
            <div
              class="control-btn control-bottom"
              :class="{ 'is-pressed': pressedAction === 'down' }"
              @mousedown="onActionDown('down', () => ptzCamera('down'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon><CaretBottom /></el-icon>
              <div class="control-inner-btn control-inner" />
            </div>
            <div
              class="control-btn control-right"
              :class="{ 'is-pressed': pressedAction === 'right' }"
              @mousedown="onActionDown('right', () => ptzCamera('right'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon><CaretRight /></el-icon>
              <div class="control-inner-btn control-inner" />
            </div>
            <div class="control-round" @click="onStopClick">
              <div class="control-round-inner"><el-icon><VideoPause /></el-icon></div>
            </div>

            <div class="contro-speed">
              <el-slider v-model="controSpeed" :max="100" :min="1" />
            </div>

            <div v-if="pressedActionLabel" class="action-hint">{{ pressedActionLabel }}</div>
          </div>
        </div>

        <div class="control-panel">
          <div class="ptz-btn-box">
            <div
              title="变倍+"
              :class="{ 'is-pressed': pressedAction === 'zoomin' }"
              @mousedown="onActionDown('zoomin', () => ptzCamera('zoomin'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon class="control-zoom-btn"><ZoomIn /></el-icon>
            </div>
            <div
              title="变倍-"
              :class="{ 'is-pressed': pressedAction === 'zoomout' }"
              @mousedown="onActionDown('zoomout', () => ptzCamera('zoomout'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon class="control-zoom-btn"><ZoomOut /></el-icon>
            </div>
          </div>

          <div class="ptz-btn-box">
            <div
              title="聚焦+"
              :class="{ 'is-pressed': pressedAction === 'focus_near' }"
              @mousedown="onActionDown('focus_near', () => focusCamera('near'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon class="control-zoom-btn"><Aim /></el-icon>
            </div>
            <div
              title="聚焦-"
              :class="{ 'is-pressed': pressedAction === 'focus_far' }"
              @mousedown="onActionDown('focus_far', () => focusCamera('far'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon class="control-zoom-btn"><View /></el-icon>
            </div>
          </div>

          <div class="ptz-btn-box">
            <div
              title="光圈+"
              :class="{ 'is-pressed': pressedAction === 'iris_in' }"
              @mousedown="onActionDown('iris_in', () => irisCamera('in'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon class="control-zoom-btn"><Plus /></el-icon>
            </div>
            <div
              title="光圈-"
              :class="{ 'is-pressed': pressedAction === 'iris_out' }"
              @mousedown="onActionDown('iris_out', () => irisCamera('out'))"
              @mouseup="onActionUp"
              @mouseleave="onActionUp"
            >
              <el-icon class="control-zoom-btn"><Minus /></el-icon>
            </div>
          </div>
        </div>
      </div>

      <!-- 控制速度已内嵌到方向盘 -->
    </div>

    <div class="ptz-right">
      <div class="ptz-method">
        <span class="ptz-method-label">控制方式</span>
        <el-radio-group v-model="ptzMethod" size="small" class="ptz-method-radio">
          <el-radio-button value="preset">预置点</el-radio-button>
          <el-radio-button value="cruise">巡航组</el-radio-button>
          <el-radio-button value="scan">自动扫描</el-radio-button>
          <el-radio-button value="wiper">雨刷</el-radio-button>
          <el-radio-button value="switch">辅助开关</el-radio-button>
        </el-radio-group>
      </div>
      <PtzPreset
        v-if="ptzMethod === 'preset'"
        :input-visible="presetInputVisible"
        :preset-list="presetList"
        :preset-id="presetForm.preset_id"
        @update:preset-id="onUpdatePresetId"
        @show-add="presetInputVisible = true"
        @cancel-add="presetInputVisible = false"
        @add-item="addPresetFromInput"
        @call-item="onCallPresetItem"
        @remove-item="onRemovePresetItem"
        @set="setPreset"
        @delete="deletePreset"
        @call="callPreset"
      />
      <PtzCruising
        v-if="ptzMethod === 'cruise'"
        :cruise-id="cruiseForm.cruise_id"
        :preset-id="presetForm.preset_id"
        :speed="cruiseForm.speed"
        :stay-time="cruiseForm.stay_time"
        :all-preset-list="presetList"
        :cruise-points="cruisePointList"
        :selected-preset-id="presetForm.preset_id"
        :select-preset-visible="cruiseSelectPresetVisible"
        :set-speed-visible="cruiseSetSpeedVisible"
        :set-time-visible="cruiseSetTimeVisible"
        :action-loading="cruiseActionLoading"
        @update:cruise-id="onUpdateCruiseId"
        @update:preset-id="onUpdatePresetId"
        @update:speed="onUpdateCruiseSpeed"
        @update:stay-time="onUpdateCruiseStayTime"
        @show-add-point="cruiseSelectPresetVisible = true"
        @cancel-add-point="cruiseSelectPresetVisible = false"
        @confirm-add-point="onConfirmAddPoint"
        @remove-point="onRemoveCruisePoint"
        @show-set-speed="cruiseSetSpeedVisible = true"
        @cancel-set-speed="cruiseSetSpeedVisible = false"
        @show-set-time="cruiseSetTimeVisible = true"
        @cancel-set-time="cruiseSetTimeVisible = false"
        @delete-cruise="deleteCruise"
        @action="onCruiseAction"
      />
      <PtzScan
        v-if="ptzMethod === 'scan'"
        :scan-id="scanForm.scan_id"
        :speed="scanForm.speed"
        :set-speed-visible="scanSetSpeedVisible"
        :action-loading="scanActionLoading"
        @update:scan-id="(v) => { scanForm.scan_id = v }"
        @update:speed="(v) => { scanForm.speed = v }"
        @show-set-speed="scanSetSpeedVisible = true"
        @cancel-set-speed="scanSetSpeedVisible = false"
        @action="doScan"
      />
      <PtzWiper v-if="ptzMethod === 'wiper'" :device-id="deviceId || ''" :channel-id="channelId || ''" />
      <PtzSwitch
        v-if="ptzMethod === 'switch'"
        :aux-id="auxId"
        :device-id="deviceId || ''"
        :channel-id="channelId || ''"
        @update:aux-id="(v) => { auxId = v }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { CaretTop, CaretLeft, CaretBottom, CaretRight, VideoPause, ZoomIn, ZoomOut, Aim, View, Plus, Minus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/http'
import { getApiErrorMessage } from '../utils/errorMessage'
import PtzPreset from './ptz/PtzPreset.vue'
import PtzCruising from './ptz/PtzCruising.vue'
import PtzScan from './ptz/PtzScan.vue'
import PtzWiper from './ptz/PtzWiper.vue'
import PtzSwitch from './ptz/PtzSwitch.vue'
import { logger } from '@/utils/logger'

const props = defineProps<{
  deviceId?: string
  channelId?: string
}>()

const controSpeed = ref(30)
const ptzMethod = ref<'preset' | 'cruise' | 'scan' | 'wiper' | 'switch'>('preset')
const auxId = ref(2)
const presetForm = ref({ preset_id: 1 })
const presetInputVisible = ref(false)
const presetList = ref<Array<{ presetId: number; presetName?: string }>>([])
const cruisePointList = ref<Array<{ presetId: number; presetName?: string }>>([])
const cruiseSelectPresetVisible = ref(false)
const cruiseSetSpeedVisible = ref(false)
const cruiseSetTimeVisible = ref(false)
const cruiseActionLoading = ref<'' | 'add' | 'delete' | 'set_speed' | 'set_time' | 'start' | 'stop' | 'delete_group'>('')
const scanSetSpeedVisible = ref(false)
const scanActionLoading = ref<'' | 'start' | 'stop' | 'set_left' | 'set_right' | 'set_speed'>('')
const cruiseForm = ref({
  cruise_id: 1,
  preset_id: 1,
  speed: 128,
  stay_time: 5
})
const scanForm = ref({
  scan_id: 0,
  speed: 128
})

type PresetItem = { presetId: number; presetName?: string }
type RemoveCruisePointPayload = { item: PresetItem; index: number }
type CruiseAction = 'add' | 'delete' | 'set_speed' | 'set_time' | 'start' | 'stop' | 'delete_group'

const onUpdatePresetId = (...args: unknown[]) => {
  const v = args[0]
  presetForm.value.preset_id = Number(v)
}

const onCallPresetItem = (...args: unknown[]) => {
  const item = args[0] as PresetItem
  void callPresetItem(item)
}

const onRemovePresetItem = (...args: unknown[]) => {
  const item = args[0] as PresetItem
  void removePresetItem(item)
}

const onUpdateCruiseId = (...args: unknown[]) => {
  const v = args[0]
  cruiseForm.value.cruise_id = Number(v)
}

const onUpdateCruiseSpeed = (...args: unknown[]) => {
  const v = args[0]
  cruiseForm.value.speed = Number(v)
}

const onUpdateCruiseStayTime = (...args: unknown[]) => {
  const v = args[0]
  cruiseForm.value.stay_time = Number(v)
}

const onConfirmAddPoint = () => {
  void doCruise('add')
}

const onRemoveCruisePoint = (...args: unknown[]) => {
  const payload = args[0] as RemoveCruisePointPayload
  void removeCruisePoint(payload)
}

const onCruiseAction = (...args: unknown[]) => {
  const action = args[0] as CruiseAction
  void doCruise(action)
}

const pressedAction = ref<
  | ''
  | 'up'
  | 'down'
  | 'left'
  | 'right'
  | 'zoomin'
  | 'zoomout'
  | 'focus_near'
  | 'focus_far'
  | 'iris_in'
  | 'iris_out'
>('')

const pressedActionLabel = computed(() => {
  const map: Record<string, string> = {
    up: '上',
    down: '下',
    left: '左',
    right: '右',
    zoomin: '变倍+',
    zoomout: '变倍-',
    focus_near: '聚焦+',
    focus_far: '聚焦-',
    iris_in: '光圈+',
    iris_out: '光圈-'
  }
  return map[pressedAction.value] || ''
})

const onActionDown = (key: typeof pressedAction.value, fn: () => void) => {
  pressedAction.value = key
  fn()
}

const onActionUp = () => {
  pressedAction.value = ''
  void ptzCamera('stop')
  void focusCamera('stop')
  void irisCamera('stop')
}

const onStopClick = () => {
  pressedAction.value = ''
  void ptzCamera('stop')
  void focusCamera('stop')
  void irisCamera('stop')
}

const getPresetStorageKey = () => `ptz-presets:${props.deviceId || 'unknown'}:${props.channelId || 'unknown'}`
const getCruiseStorageKey = () => `ptz-cruise-points:${props.deviceId || 'unknown'}:${props.channelId || 'unknown'}:${cruiseForm.value.cruise_id}`

const loadPresetListFromLocal = () => {
  try {
    const raw = localStorage.getItem(getPresetStorageKey())
    if (!raw) {
      presetList.value = []
      return
    }
    const parsed = JSON.parse(raw) as Array<{ presetId: number; presetName?: string }>
    presetList.value = Array.isArray(parsed) ? parsed : []
  } catch {
    presetList.value = []
  }
}

const savePresetList = () => {
  localStorage.setItem(getPresetStorageKey(), JSON.stringify(presetList.value))
}

const loadCruisePointListFromLocal = () => {
  try {
    const raw = localStorage.getItem(getCruiseStorageKey())
    if (!raw) {
      cruisePointList.value = []
      return
    }
    const parsed = JSON.parse(raw) as Array<{ presetId: number; presetName?: string }>
    cruisePointList.value = Array.isArray(parsed) ? parsed : []
  } catch {
    cruisePointList.value = []
  }
}

const saveCruisePointList = () => {
  localStorage.setItem(getCruiseStorageKey(), JSON.stringify(cruisePointList.value))
}

const loadPresetList = async () => {
  if (!props.deviceId || !props.channelId) {
    presetList.value = []
    return
  }
  try {
    const res = await api.get(`/api/v1/control/${props.deviceId}/${props.channelId}/preset/list`)
    const list = Array.isArray(res?.data?.preset_list) ? res.data.preset_list : []
    presetList.value = list
      .map((item: Record<string, unknown>) => ({
        presetId: Number(item?.preset_id),
        presetName: String(item?.preset_name || item?.preset_id || '')
      }))
      .filter((item: { presetId: number }) => Number.isInteger(item.presetId) && item.presetId >= 1 && item.presetId <= 255)
    savePresetList()
  } catch {
    loadPresetListFromLocal()
  }
}

const loadCruisePointList = async () => {
  if (!props.deviceId || !props.channelId) {
    cruisePointList.value = []
    return
  }
  try {
    const cruiseId = Number(cruiseForm.value.cruise_id)
    const res = await api.get(`/api/v1/control/${props.deviceId}/${props.channelId}/cruise/${cruiseId}/points`)
    const points = Array.isArray(res?.data?.points) ? res.data.points : []
    cruisePointList.value = points
      .map((item: Record<string, unknown>) => ({
        presetId: Number(item?.preset_id),
        presetName: String(item?.preset_name || item?.preset_id || '')
      }))
      .filter((item: { presetId: number }) => Number.isInteger(item.presetId) && item.presetId >= 1 && item.presetId <= 255)
    cruiseForm.value.speed = Number(res?.data?.speed || cruiseForm.value.speed)
    cruiseForm.value.stay_time = Number(res?.data?.stay_time || cruiseForm.value.stay_time)
    saveCruisePointList()
  } catch {
    loadCruisePointListFromLocal()
  }
}

const loadScanConfig = async () => {
  if (!props.deviceId || !props.channelId) return
  try {
    const scanId = Number(scanForm.value.scan_id)
    const res = await api.get(`/api/v1/control/${props.deviceId}/${props.channelId}/scan/${scanId}/config`)
    scanForm.value.speed = Number(res?.data?.speed || scanForm.value.speed)
  } catch {
    // ignore, keep local value
  }
}

const loadControlState = async () => {
  if (!props.deviceId || !props.channelId) {
    presetList.value = []
    cruisePointList.value = []
    return
  }
  try {
    const res = await api.get(`/api/v1/control/${props.deviceId}/${props.channelId}/state`, {
      params: {
        cruise_id: cruiseForm.value.cruise_id,
        scan_id: scanForm.value.scan_id
      }
    })
    const data = res?.data || {}
    const presetRaw = Array.isArray(data?.preset_list) ? data.preset_list : []
    const pointsRaw = Array.isArray(data?.cruise?.points) ? data.cruise.points : []
    presetList.value = presetRaw
      .map((item: Record<string, unknown>) => ({
        presetId: Number(item?.preset_id),
        presetName: String(item?.preset_name || item?.preset_id || '')
      }))
      .filter((item: { presetId: number }) => Number.isInteger(item.presetId) && item.presetId >= 1 && item.presetId <= 255)
    cruisePointList.value = pointsRaw
      .map((item: Record<string, unknown>) => ({
        presetId: Number(item?.preset_id),
        presetName: String(item?.preset_name || item?.preset_id || '')
      }))
      .filter((item: { presetId: number }) => Number.isInteger(item.presetId) && item.presetId >= 1 && item.presetId <= 255)
    cruiseForm.value.speed = Number(data?.cruise?.speed || cruiseForm.value.speed)
    cruiseForm.value.stay_time = Number(data?.cruise?.stay_time || cruiseForm.value.stay_time)
    scanForm.value.speed = Number(data?.scan?.speed || scanForm.value.speed)
    savePresetList()
    saveCruisePointList()
    return true
  } catch {
    return false
  }
}

const syncControlState = async () => {
  if (!props.deviceId || !props.channelId) return
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/state`, {
      preset_list: presetList.value.map((item) => ({
        preset_id: item.presetId,
        preset_name: item.presetName || String(item.presetId)
      })),
      cruise_id: Number(cruiseForm.value.cruise_id),
      cruise_points: cruisePointList.value.map((item) => ({
        preset_id: item.presetId,
        preset_name: item.presetName || String(item.presetId)
      })),
      cruise_speed: Number(cruiseForm.value.speed),
      cruise_stay_time: Number(cruiseForm.value.stay_time),
      scan_id: Number(scanForm.value.scan_id),
      scan_speed: Number(scanForm.value.speed)
    })
  } catch {
    // ignore sync failure
  }
}

const setPreset = async () => {
  if (!props.deviceId || !props.channelId) return
  const presetId = Number(presetForm.value.preset_id)
  if (!Number.isInteger(presetId) || presetId < 1 || presetId > 255) {
    ElMessage.warning('预置位编号必须是 1-255 之间的整数')
    return
  }
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/preset/set`, {
      preset_id: presetId
    })
    const exists = presetList.value.some((item) => item.presetId === presetId)
    if (!exists) {
      presetList.value.push({ presetId, presetName: String(presetId) })
      savePresetList()
    }
    presetInputVisible.value = false
    ElMessage.success('预置位已保存')
    await syncControlState()
    const ok = await loadControlState()
    if (!ok) await loadPresetList()
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, '保存预置位失败'))
  }
}

const callPreset = async () => {
  if (!props.deviceId || !props.channelId) return
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/preset`, {
      preset_id: Number(presetForm.value.preset_id)
    })
    ElMessage.success('调用预置位成功')
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, '调用预置位失败'))
  }
}

const deletePreset = async () => {
  if (!props.deviceId || !props.channelId) return
  const presetId = Number(presetForm.value.preset_id)
  try {
    await ElMessageBox.confirm('确定删除此预置位', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/preset/delete`, {
      preset_id: presetId
    })
    presetList.value = presetList.value.filter((item) => item.presetId !== presetId)
    savePresetList()
    ElMessage.success('预置位已删除')
    await syncControlState()
    const ok = await loadControlState()
    if (!ok) await loadPresetList()
  } catch (e) {
    // ignore cancel
  }
}

const addPresetFromInput = async () => {
  await setPreset()
}

const callPresetItem = async (item: { presetId: number; presetName?: string }) => {
  presetForm.value.preset_id = item.presetId
  await callPreset()
}

const removePresetItem = async (item: { presetId: number; presetName?: string }) => {
  presetForm.value.preset_id = item.presetId
  await deletePreset()
}

const removeCruisePoint = async (payload: { item: { presetId: number; presetName?: string }; index: number }) => {
  presetForm.value.preset_id = payload.item.presetId
  await doCruise('delete')
}

const ptzCamera = async (command: string) => {
  if (!props.deviceId || !props.channelId) return
  const speed = Math.round((controSpeed.value * 255) / 100)
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/ptz`, {
      command,
      speed
    })
  } catch (e) {
    logger.error('PTZ控制失败', e)
    ElMessage.error('云台控制失败')
  }
}

const focusCamera = async (command: string) => {
  if (!props.deviceId || !props.channelId) return
  const speed = Math.round((controSpeed.value * 255) / 100)
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/focus`, {
      command,
      speed
    })
  } catch (e) {
    logger.error('聚焦控制失败', e)
    ElMessage.error('聚焦控制失败')
  }
}

const irisCamera = async (command: string) => {
  if (!props.deviceId || !props.channelId) return
  const speed = Math.round((controSpeed.value * 255) / 100)
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/iris`, {
      command,
      speed
    })
  } catch (e) {
    logger.error('光圈控制失败', e)
    ElMessage.error('光圈控制失败')
  }
}

const doCruise = async (action: 'add' | 'delete' | 'set_speed' | 'set_time' | 'start' | 'stop' | 'delete_group') => {
  if (!props.deviceId || !props.channelId) return
  cruiseActionLoading.value = action
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/cruise`, {
      cruise_id: cruiseForm.value.cruise_id,
      preset_id: presetForm.value.preset_id,
      action,
      speed: cruiseForm.value.speed,
      stay_time: cruiseForm.value.stay_time
    })
    if (action === 'add') {
      const exists = cruisePointList.value.some((item) => item.presetId === presetForm.value.preset_id)
      if (!exists) {
        cruisePointList.value.push({ presetId: presetForm.value.preset_id, presetName: String(presetForm.value.preset_id) })
        saveCruisePointList()
      }
      cruiseSelectPresetVisible.value = false
    }
    if (action === 'delete') {
      cruisePointList.value = cruisePointList.value.filter((item) => item.presetId !== presetForm.value.preset_id)
      saveCruisePointList()
    }
    if (action === 'set_speed') cruiseSetSpeedVisible.value = false
    if (action === 'set_time') cruiseSetTimeVisible.value = false
    if (action === 'delete_group') {
      cruisePointList.value = []
      saveCruisePointList()
    }
    ElMessage.success('巡航命令已发送')
    await syncControlState()
    const ok = await loadControlState()
    if (!ok) await loadCruisePointList()
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, '巡航控制失败'))
  } finally {
    cruiseActionLoading.value = ''
  }
}

const deleteCruise = async () => {
  if (!props.deviceId || !props.channelId) return
  cruiseActionLoading.value = 'delete_group'
  try {
    await ElMessageBox.confirm('确定删除此巡航组', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/cruise`, {
      cruise_id: cruiseForm.value.cruise_id,
      preset_id: 1,
      action: 'delete_group',
      speed: cruiseForm.value.speed,
      stay_time: cruiseForm.value.stay_time
    })
    cruisePointList.value = []
    saveCruisePointList()
    ElMessage.success('巡航组已清空')
    await syncControlState()
    const ok = await loadControlState()
    if (!ok) await loadCruisePointList()
  } catch {
    // ignore cancel
  } finally {
    cruiseActionLoading.value = ''
  }
}

const doScan = async (action: 'start' | 'stop' | 'set_left' | 'set_right' | 'set_speed') => {
  if (!props.deviceId || !props.channelId) return
  scanActionLoading.value = action
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/scan`, {
      scan_id: scanForm.value.scan_id,
      action,
      speed: scanForm.value.speed
    })
    ElMessage.success('扫描命令已发送')
    if (action === 'set_speed') scanSetSpeedVisible.value = false
    await syncControlState()
    const ok = await loadControlState()
    if (!ok) await loadScanConfig()
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, '扫描控制失败'))
  } finally {
    scanActionLoading.value = ''
  }
}

void (async () => {
  const ok = await loadControlState()
  if (!ok) {
    await loadPresetList()
    await loadCruisePointList()
    await loadScanConfig()
  }
})()

watch(
  () => cruiseForm.value.cruise_id,
  () => {
    void (async () => {
      const ok = await loadControlState()
      if (!ok) await loadCruisePointList()
    })()
  }
)

watch(
  () => scanForm.value.scan_id,
  () => {
    void (async () => {
      const ok = await loadControlState()
      if (!ok) await loadScanConfig()
    })()
  }
)

watch(
  () => [props.deviceId, props.channelId],
  () => {
    void (async () => {
      const ok = await loadControlState()
      if (!ok) {
        await loadPresetList()
        await loadCruisePointList()
        await loadScanConfig()
      }
    })()
  }
)
</script>

<style scoped>
.ptz-wrap { display: grid; grid-template-columns: 240px 1fr; gap: 14px; }
.ptz-left {
  padding: 8px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fcfdff;
  height: 180px;
  overflow: hidden;
}

.ptz-control-grid {
  display: grid;
  grid-template-columns: 6.25rem auto;
  height: 180px;
  overflow: hidden;
}
.ptz-right { display: grid; gap: 6px; align-content: start; min-width: 0; }
.ptz-method {
  display: grid;
  grid-template-columns: 62px 1fr;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.ptz-method-label { font-size: 12px; color: #606266; text-align: right; }
.ptz-method-radio { width: 100%; overflow: hidden; }
.ptz-method-radio :deep(.el-radio-button__inner) {
  padding: 6px 10px;
  font-size: 12px;
}
.control-panel {
  text-align: left;
}

.ptz-btn-box {
  display: grid;
  grid-template-columns: 1fr 1fr;
  padding: 0 2rem;
  height: 3rem;
  line-height: 4rem;
}

.ptz-btn-box > div {
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 6px;
  transition: background 0.15s ease, box-shadow 0.15s ease;
}

.ptz-btn-box > div.is-pressed {
  background: rgba(64, 158, 255, 0.14);
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12) inset;
}

.control-zoom-btn {
  font-size: 1.5rem;
  color: #78aee4;
}

.control-wrapper {
  position: relative;
  width: 6.25rem;
  height: 6.25rem;
  max-width: 6.25rem;
  max-height: 6.25rem;
  border-radius: 100%;
  margin-top: 1.5rem;
  margin-left: 0.5rem;
}

.control-btn {
  display: flex;
  justify-content: center;
  align-items: center;
  position: absolute;
  width: 44%;
  height: 44%;
  border-radius: 5px;
  border: 1px solid #78aee4;
  box-sizing: border-box;
  transition: all 0.3s linear;
  cursor: pointer;
  user-select: none;
}

.control-btn:hover {
  cursor: pointer;
}

.control-btn:active {
  background: rgba(120, 174, 228, 0.15);
}

.control-btn.is-pressed {
  background: rgba(64, 158, 255, 0.18);
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12) inset;
}

.action-hint {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 12px;
  color: rgba(64, 158, 255, 0.9);
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(64, 158, 255, 0.25);
  padding: 2px 6px;
  border-radius: 999px;
  pointer-events: none;
  z-index: 3;
}

.control-btn .el-icon {
  font-size: 20px;
  color: #78aee4;
  display: flex;
  justify-content: center;
  align-items: center;
  pointer-events: none;
}

.control-round {
  position: absolute;
  top: 21%;
  left: 21%;
  width: 58%;
  height: 58%;
  background: #fff;
  border-radius: 100%;
}

.control-round-inner {
  position: absolute;
  left: 13%;
  top: 13%;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 70%;
  height: 70%;
  font-size: 40px;
  color: #78aee4;
  border: 1px solid #78aee4;
  border-radius: 100%;
  transition: all 0.3s linear;
}

.control-inner-btn {
  position: absolute;
  width: 60%;
  height: 60%;
  background: #fafafa;
}

.control-top {
  top: -8%;
  left: 27%;
  transform: rotate(-45deg);
  border-radius: 5px 100% 5px 0;
}

.control-top .el-icon {
  transform: rotate(45deg);
}

.control-top .control-inner {
  left: -1px;
  bottom: 0;
  border-top: 1px solid #78aee4;
  border-right: 1px solid #78aee4;
  border-radius: 0 100% 0 0;
}

.control-left {
  top: 27%;
  left: -8%;
  transform: rotate(45deg);
  border-radius: 5px 0 5px 100%;
}

.control-left .el-icon {
  transform: rotate(-45deg);
}

.control-left .control-inner {
  right: -1px;
  top: -1px;
  border-bottom: 1px solid #78aee4;
  border-left: 1px solid #78aee4;
  border-radius: 0 0 0 100%;
}

.control-right {
  top: 27%;
  right: -8%;
  transform: rotate(45deg);
  border-radius: 5px 100% 5px 0;
}

.control-right .el-icon {
  transform: rotate(-45deg);
}

.control-right .control-inner {
  left: -1px;
  bottom: -1px;
  border-top: 1px solid #78aee4;
  border-right: 1px solid #78aee4;
  border-radius: 0 100% 0 0;
}

.control-bottom {
  left: 27%;
  bottom: -8%;
  transform: rotate(45deg);
  border-radius: 0 5px 100% 5px;
}

.control-bottom .el-icon {
  transform: rotate(-45deg);
}

.control-bottom .control-inner {
  top: -1px;
  left: -1px;
  border-bottom: 1px solid #78aee4;
  border-right: 1px solid #78aee4;
  border-radius: 0 0 100% 0;
}

.contro-speed {
  position: absolute;
  left: 4px;
  top: 7rem;
  width: 6.25rem;
}

.contro-speed :deep(.el-slider) {
  width: 100%;
}
</style>
