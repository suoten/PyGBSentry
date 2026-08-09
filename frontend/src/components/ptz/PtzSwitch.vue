<template>
  <div class="panel-box">
    <span class="row-label">{{ t('ptzCtrl.auxId') }}</span>
    <el-input-number :model-value="auxId" :min="2" :max="255" controls-position="right" @update:model-value="onAuxChange" />
    <el-button size="small" :loading="loading === 'on'" @click="sendAux('on')">{{ t('ptzCtrl.turnOn') }}</el-button>
    <el-button size="small" :loading="loading === 'off'" @click="sendAux('off')">{{ t('ptzCtrl.turnOff') }}</el-button>
    <span class="muted-text">{{ t('ptzCtrl.auxSwitchTip') }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../../utils/errorMessage'

const { t } = useI18n()

const props = defineProps<{
  auxId: number
  deviceId: string
  channelId: string
}>()

const emit = defineEmits<{
  (e: 'update:auxId', value: number): void
}>()

const onAuxChange = (value: string | number | undefined) => {
  const next = Number(value ?? props.auxId)
  emit('update:auxId', Number.isFinite(next) ? next : props.auxId)
}

const loading = ref<'' | 'on' | 'off'>('')

const sendAux = async (command: 'on' | 'off') => {
  if (!props.deviceId || !props.channelId) return
  loading.value = command
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/aux`, {
      aux_id: props.auxId,
      command
    })
    ElMessage.success(t('ptzCtrl.auxCommandSent'))
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('ptzCtrl.auxControlFailed')))
  } finally {
    loading.value = ''
  }
}
</script>

<style scoped>
.panel-box { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; background: #fcfdff; }
.row-label { font-size: 12px; color: #606266; }
.muted-text { color: #909399; font-size: 12px; }
.panel-box :deep(.el-button) { min-height: 28px; padding: 6px 10px; }
.panel-box :deep(.el-input-number) { width: 120px; }
</style>
