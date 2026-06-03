<template>
  <div class="panel-box">
    <div class="row-line">
      <span class="row-label">扫描组号</span>
      <el-input-number :model-value="scanId" :min="0" :max="255" controls-position="right" @update:model-value="onScanChange" />
      <el-button size="small" :loading="actionLoading === 'set_left'" @click="$emit('action', 'set_left')">左边界</el-button>
      <el-button size="small" :loading="actionLoading === 'set_right'" @click="$emit('action', 'set_right')">右边界</el-button>
      <el-button type="primary" size="small" :loading="actionLoading === 'start'" @click="$emit('action', 'start')">开始扫描</el-button>
      <el-button class="stop-btn" size="small" :loading="actionLoading === 'stop'" @click="$emit('action', 'stop')">停止</el-button>
    </div>
    <div v-if="setSpeedVisible" class="row-line">
      <span class="row-label">扫描速度</span>
      <el-input-number :model-value="speed" :min="1" :max="4095" controls-position="right" @update:model-value="onSpeedChange" />
      <el-button size="small" type="primary" :loading="actionLoading === 'set_speed'" @click="$emit('action', 'set_speed')">保存</el-button>
      <el-button size="small" @click="$emit('cancel-set-speed')">取消</el-button>
    </div>
    <el-button v-else size="small" @click="$emit('show-set-speed')">设置扫描速度</el-button>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  scanId: number
  speed: number
  setSpeedVisible: boolean
  actionLoading: '' | 'start' | 'stop' | 'set_left' | 'set_right' | 'set_speed'
}>()

const emit = defineEmits<{
  (e: 'update:scanId', value: number): void
  (e: 'update:speed', value: number): void
  (e: 'show-set-speed'): void
  (e: 'cancel-set-speed'): void
  (e: 'action', value: 'start' | 'stop' | 'set_left' | 'set_right' | 'set_speed'): void
}>()

const onScanChange = (value: string | number | undefined) => {
  const next = Number(value ?? props.scanId)
  emit('update:scanId', Number.isFinite(next) ? next : props.scanId)
}

const onSpeedChange = (value: string | number | undefined) => {
  const next = Number(value ?? props.speed)
  emit('update:speed', Number.isFinite(next) ? next : props.speed)
}
</script>

<style scoped>
.panel-box { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; display: grid; gap: 8px; background: #fcfdff; }
.row-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.row-label { font-size: 12px; color: #606266; min-width: 66px; text-align: right; }
.stop-btn { background: #f56c6c; color: #fff; border-color: #f56c6c; }
</style>
