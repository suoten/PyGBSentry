<template>
  <div class="panel-box">
    <span class="row-label">辅助ID</span>
    <el-input-number :model-value="auxId" :min="2" :max="255" controls-position="right" @update:model-value="onAuxChange" />
    <el-button size="small" :loading="loading === 'on'" @click="sendAux('on')">开启</el-button>
    <el-button size="small" :loading="loading === 'off'" @click="sendAux('off')">关闭</el-button>
    <span class="muted-text">辅助开关为设备兼容能力，部分设备可能不支持。</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../../utils/errorMessage'

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
    ElMessage.success('辅助开关命令已发送')
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, '辅助开关控制失败'))
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
