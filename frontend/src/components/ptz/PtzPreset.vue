<template>
  <div class="panel-box">
    <el-tag
      v-for="item in presetList"
      :key="item.presetId"
      closable
      size="small"
      class="preset-tag"
      @close="handleRemoveItem(item)"
      @click="$emit('call-item', item)"
    >
      {{ item.presetName || item.presetId }}
    </el-tag>

    <div v-if="inputVisible" class="row-line">
      <span class="row-label">{{ t('ptzCtrl.presetPoint') }}</span>
      <el-input-number
        :model-value="presetId"
        :min="1"
        :max="255"
        controls-position="right"
        @update:model-value="onPresetChange"
      />
      <el-button size="small" type="primary" @click="$emit('add-item')">{{ t('common.save') }}</el-button>
      <el-button size="small" @click="$emit('cancel-add')">{{ t('common.cancel') }}</el-button>
    </div>

    <el-button v-else size="small" @click="$emit('show-add')">+ {{ t('common.add') }}</el-button>

    <div class="row-line">
      <span class="row-label">{{ t('ptzCtrl.presetPoint') }}</span>
      <el-input-number
        :model-value="presetId"
        :min="1"
        :max="255"
        controls-position="right"
        @update:model-value="onPresetChange"
      />
      <el-button size="small" @click="$emit('set')">{{ t('ptzCtrl.setBtn') }}</el-button>
      <el-button size="small" @click="handleDelete">{{ t('common.delete') }}</el-button>
      <el-button type="primary" size="small" @click="$emit('call')">{{ t('ptzCtrl.callBtn') }}</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { confirmDangerous } from '../../utils/feedback'

const { t } = useI18n()

const props = defineProps<{
  presetId: number
  inputVisible: boolean
  presetList: Array<{ presetId: number; presetName?: string }>
}>()

const emit = defineEmits<{
  (e: 'update:presetId', value: number): void
  (e: 'show-add'): void
  (e: 'cancel-add'): void
  (e: 'add-item'): void
  (e: 'call-item', value: { presetId: number; presetName?: string }): void
  (e: 'remove-item', value: { presetId: number; presetName?: string }): void
  (e: 'set'): void
  (e: 'delete'): void
  (e: 'call'): void
}>()

const onPresetChange = (value: string | number | undefined) => {
  const next = Number(value ?? props.presetId)
  emit('update:presetId', Number.isFinite(next) ? next : 1)
}

async function handleRemoveItem(item: { presetId: number; presetName?: string }) {
  try {
    await confirmDangerous(t('ptzCtrl.deletePresetTitle'), item.presetName || String(item.presetId))
  } catch { return }
  emit('remove-item', item)
}

async function handleDelete() {
  try {
    await confirmDangerous(t('ptzCtrl.deletePresetTitle'))
  } catch { return }
  emit('delete')
}
</script>

<style scoped>
.panel-box { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; display: grid; gap: 8px; background: #fcfdff; }
.row-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.row-label { font-size: 12px; color: #606266; min-width: 66px; text-align: right; }
.preset-tag { margin-right: 8px; margin-bottom: 6px; cursor: pointer; }
.preset-tag:hover { opacity: 0.9; }
</style>
