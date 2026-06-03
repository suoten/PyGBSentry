<template>
  <el-dialog v-model="dialogVisible" width="88%" class="record-workspace-dialog" destroy-on-close>
    <template #header>
      <div class="title-wrap">
        <div class="title">设备录像工作台</div>
        <div class="subtitle">{{ deviceName || deviceId || '未选择设备' }}</div>
      </div>
    </template>

    <div class="toolbar">
      <el-select
        :model-value="channelGbId"
        size="small"
        filterable
        class="channel-select"
        placeholder="选择通道"
        @update:model-value="onChannelChange"
      >
        <OptionWithTitle
          v-for="item in channels"
          :key="String(item?.gb_id || item?.id || '')"
          :label="`${item?.name || item?.gb_id || ''} (${item?.gb_id || ''})`"
          :value="String(item?.gb_id || item?.id || '')"
        />
      </el-select>
      <el-button size="small" @click="switchChannel(-1)">上一通道</el-button>
      <el-button size="small" @click="switchChannel(1)">下一通道</el-button>
      <el-select :model-value="windowMinutes" size="small" class="window-select" @update:model-value="onWindowChange">
        <el-option v-for="item in [15, 30, 60, 120]" :key="item" :label="`前后 ${item} 分钟`" :value="item" />
      </el-select>
      <el-date-picker
        :model-value="anchorAt"
        type="datetime"
        size="small"
        value-format="YYYY-MM-DDTHH:mm:ss"
        format="YYYY-MM-DD HH:mm:ss"
        class="time-picker"
        placeholder="定位时间点"
        @update:model-value="onAnchorChange"
      />
      <el-button size="small" @click="setAnchorNow">回到现在</el-button>
    </div>

    <div class="pane">
      <DeviceRecordList
        v-if="dialogVisible && deviceId && channelGbId"
        :key="paneKey"
        :device-id="deviceId"
        :channel-id="channelGbId"
        :initial-start="initialStart"
        @play="$emit('play', $event)"
      />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DeviceRecordList from './DeviceRecordList.vue'
import OptionWithTitle from './OptionWithTitle.vue'

const props = withDefaults(defineProps<{
  visible: boolean
  deviceId: string
  deviceName?: string
  channels: Record<string, unknown>[]
  channelGbId: string
  windowMinutes: number
  anchorAt: string
}>(), {
  deviceName: '',
  channels: () => []
})

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'update:channelGbId', value: string): void
  (e: 'update:windowMinutes', value: number): void
  (e: 'update:anchorAt', value: string): void
  (e: 'play', payload: Record<string, unknown>): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v)
})

const parseAnchor = (raw: string) => {
  const text = String(raw || '').trim()
  if (!text) return new Date()
  const d = new Date(text)
  return Number.isNaN(d.getTime()) ? new Date() : d
}

const initialStart = computed(() => {
  const center = parseAnchor(props.anchorAt)
  const minutes = Math.max(1, Number(props.windowMinutes || 30))
  return new Date(center.getTime() - minutes * 60 * 1000).toISOString()
})

const paneKey = computed(() => {
  return [props.deviceId, props.channelGbId, props.anchorAt, String(props.windowMinutes)].join('|')
})

const onChannelChange = (value: string) => {
  emit('update:channelGbId', String(value || ''))
}

const onWindowChange = (value: number) => {
  emit('update:windowMinutes', Math.max(1, Number(value || 30)))
}

const onAnchorChange = (value: string) => {
  emit('update:anchorAt', String(value || ''))
}

const toAnchor = (date: Date) => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${y}-${m}-${d}T${hh}:${mm}:${ss}`
}

const setAnchorNow = () => {
  emit('update:anchorAt', toAnchor(new Date()))
}

const switchChannel = (step: number) => {
  const list = props.channels || []
  if (!list.length) return
  const currentIdx = list.findIndex((item: Record<string, unknown>) => String(item?.gb_id || item?.id || '') === String(props.channelGbId || ''))
  const base = currentIdx >= 0 ? currentIdx : 0
  const next = (base + step + list.length) % list.length
  emit('update:channelGbId', String(list[next]?.gb_id || list[next]?.id || ''))
}
</script>

<style scoped>
.title-wrap { display: flex; flex-direction: column; gap: 4px; }
.title { font-size: 18px; font-weight: 700; color: #0f172a; }
.subtitle { font-size: 12px; color: #64748b; }
.toolbar {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}
.channel-select { width: 360px; }
.window-select { width: 130px; }
.time-picker { width: 212px; }
.pane {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}
</style>
