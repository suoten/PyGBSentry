<template>
  <div class="panel-box">
    <div class="row-line">
      <span class="row-label">{{ t('ptzCtrl.cruiseId') }}</span>
      <el-input-number :model-value="cruiseId" :min="1" :max="255" controls-position="right" @update:model-value="(v: number | undefined) => emitValue('update:cruiseId', v, cruiseId)" />
    </div>

    <div class="points-wrap">
      <div class="points-title">{{ t('ptzCtrl.presetPoint') }}</div>
      <div v-if="cruisePoints.length" class="points-list">
        <el-tag
          v-for="(item, index) in cruisePoints"
          :key="`${item.presetId}-${index}`"
          closable
          class="point-tag"
          @close="$emit('remove-point', { item, index })"
        >
          {{ item.presetName || item.presetId }}
        </el-tag>
      </div>
      <div v-else class="points-empty">{{ t('ptzCtrl.cruisePointEmpty') }}</div>
    </div>

    <div v-if="selectPresetVisible" class="row-line row-line--form">
      <span class="row-label">{{ t('ptzCtrl.presetPoint') }}</span>
      <el-select class="row-control" :model-value="selectedPresetId" :placeholder="t('ptzCtrl.presetPlaceholder')" @update:model-value="onSelectPreset">
        <el-option
          v-for="item in allPresetList"
          :key="item.presetId"
          :label="item.presetName || String(item.presetId)"
          :value="item.presetId"
        />
      </el-select>
      <div class="row-actions">
        <el-button type="primary" size="small" :loading="actionLoading === 'add'" @click="$emit('confirm-add-point')">{{ t('common.save') }}</el-button>
        <el-button size="small" @click="$emit('cancel-add-point')">{{ t('common.cancel') }}</el-button>
      </div>
    </div>
    <div v-else class="row-line row-line--trigger">
      <span class="row-label">{{ t('ptzCtrl.presetPoint') }}</span>
      <div class="row-control row-control--text">{{ t('ptzCtrl.currentSelection') }}{{ selectedPresetId }}</div>
      <div class="row-actions">
        <el-button size="small" @click="$emit('show-add-point')">{{ t('ptzCtrl.addCruisePoint') }}</el-button>
      </div>
    </div>

    <div v-if="setSpeedVisible" class="row-line row-line--form">
      <span class="row-label">{{ t('ptzCtrl.cruiseSpeed') }}</span>
      <el-input-number
        class="row-control"
        :model-value="speed"
        :min="1"
        :max="4095"
        controls-position="right"
        @update:model-value="(v: number | undefined) => emitValue('update:speed', v, speed)"
      />
      <div class="row-actions">
        <el-button type="primary" size="small" :loading="actionLoading === 'set_speed'" @click="$emit('action', 'set_speed')">{{ t('common.save') }}</el-button>
        <el-button size="small" @click="$emit('cancel-set-speed')">{{ t('common.cancel') }}</el-button>
      </div>
    </div>
    <div v-else class="row-line row-line--trigger">
      <span class="row-label">{{ t('ptzCtrl.cruiseSpeed') }}</span>
      <div class="row-control row-control--text">{{ speed }}</div>
      <div class="row-actions">
        <el-button size="small" @click="$emit('show-set-speed')">{{ t('ptzCtrl.setCruiseSpeed') }}</el-button>
      </div>
    </div>

    <div v-if="setTimeVisible" class="row-line row-line--form">
      <span class="row-label">{{ t('ptzCtrl.stayTime') }}</span>
      <el-input-number
        class="row-control"
        :model-value="stayTime"
        :min="1"
        :max="4095"
        controls-position="right"
        @update:model-value="(v: number | undefined) => emitValue('update:stayTime', v, stayTime)"
      />
      <div class="row-actions">
        <el-button type="primary" size="small" :loading="actionLoading === 'set_time'" @click="$emit('action', 'set_time')">{{ t('common.save') }}</el-button>
        <el-button size="small" @click="$emit('cancel-set-time')">{{ t('common.cancel') }}</el-button>
      </div>
    </div>
    <div v-else class="row-line row-line--trigger">
      <span class="row-label">{{ t('ptzCtrl.stayTime') }}</span>
      <div class="row-control row-control--text">{{ stayTime }} s</div>
      <div class="row-actions">
        <el-button size="small" @click="$emit('show-set-time')">{{ t('ptzCtrl.setCruiseTime') }}</el-button>
      </div>
    </div>

    <div class="row-line">
      <el-button size="small" type="primary" :loading="actionLoading === 'start'" @click="$emit('action', 'start')">{{ t('ptzCtrl.startCruise') }}</el-button>
      <el-button size="small" :loading="actionLoading === 'stop'" @click="$emit('action', 'stop')">{{ t('ptzCtrl.stopCruise') }}</el-button>
      <el-button size="small" type="danger" :loading="actionLoading === 'delete_group'" @click="$emit('delete-cruise')">{{ t('ptzCtrl.deleteCruise') }}</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  cruiseId: number
  presetId: number
  speed: number
  stayTime: number
  allPresetList: Array<{ presetId: number; presetName?: string }>
  cruisePoints: Array<{ presetId: number; presetName?: string }>
  selectedPresetId: number
  selectPresetVisible: boolean
  setSpeedVisible: boolean
  setTimeVisible: boolean
  actionLoading: '' | 'add' | 'delete' | 'set_speed' | 'set_time' | 'start' | 'stop' | 'delete_group'
}>()

const emit = defineEmits<{
  (e: 'update:cruiseId', value: number): void
  (e: 'update:presetId', value: number): void
  (e: 'update:speed', value: number): void
  (e: 'update:stayTime', value: number): void
  (e: 'show-add-point'): void
  (e: 'cancel-add-point'): void
  (e: 'confirm-add-point'): void
  (e: 'remove-point', value: { item: { presetId: number; presetName?: string }; index: number }): void
  (e: 'show-set-speed'): void
  (e: 'cancel-set-speed'): void
  (e: 'show-set-time'): void
  (e: 'cancel-set-time'): void
  (e: 'delete-cruise'): void
  (e: 'action', value: 'add' | 'delete' | 'set_speed' | 'set_time' | 'start' | 'stop' | 'delete_group'): void
}>()

const emitValue = (eventName: 'update:cruiseId' | 'update:presetId' | 'update:speed' | 'update:stayTime', value: string | number | undefined, fallback: number) => {
  const next = Number(value ?? fallback)
  ;(emit as (e: 'update:cruiseId' | 'update:presetId' | 'update:speed' | 'update:stayTime', value: number) => void)(eventName, Number.isFinite(next) ? next : fallback)
}

const onSelectPreset = (value: string | number | undefined) => {
  const next = Number(value ?? props.selectedPresetId)
  emit('update:presetId', Number.isFinite(next) ? next : props.selectedPresetId)
}
</script>

<style scoped>
.panel-box {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 12px;
  display: grid;
  gap: 10px;
  background: #fcfdff;
  max-width: 760px;
}
.row-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.row-label { font-size: 12px; color: #606266; min-width: 66px; text-align: right; }
.point-tag { margin-right: 8px; margin-bottom: 6px; }
.point-tag:hover { opacity: 0.9; }
.panel-box :deep(.el-button) { min-height: 28px; padding: 6px 10px; }
.panel-box :deep(.el-input-number) { width: 120px; }
.panel-box :deep(.el-select) { min-width: 180px; }

.row-line--form,
.row-line--trigger {
  display: grid;
  grid-template-columns: 66px 1fr auto;
  align-items: center;
  gap: 8px;
}

.row-control {
  width: 100%;
  min-width: 0;
}

.row-control--text {
  height: 28px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fff;
  color: #303133;
  font-size: 12px;
}

.row-actions {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-start;
  white-space: nowrap;
}

.points-wrap {
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
}

.points-title {
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}

.points-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.points-empty {
  font-size: 12px;
  color: #909399;
  padding: 4px 0 2px;
}
</style>
