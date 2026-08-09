<template>
  <div class="panel-box">
    <el-button size="small" :loading="loading === 'on'" @click="sendWiper('on')">{{ t('ptzCtrl.turnOn') }}</el-button>
    <el-button size="small" :loading="loading === 'off'" @click="sendWiper('off')">{{ t('ptzCtrl.turnOff') }}</el-button>
    <el-button size="small" :loading="loading === 'stop'" @click="sendWiper('stop')">{{ t('ptzCtrl.stop') }}</el-button>
    <span class="muted-text">{{ t('ptzCtrl.wiperTip') }}</span>
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
  deviceId: string
  channelId: string
}>()

const loading = ref<'' | 'on' | 'off' | 'stop'>('')

const sendWiper = async (command: 'on' | 'off' | 'stop') => {
  if (!props.deviceId || !props.channelId) return
  loading.value = command
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/wiper`, { command })
    ElMessage.success(t('ptzCtrl.wiperCommandSent'))
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('ptzCtrl.wiperControlFailed')))
  } finally {
    loading.value = ''
  }
}
</script>

<style scoped>
.panel-box { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; background: #fcfdff; }
.muted-text { color: #909399; font-size: 12px; }
.panel-box :deep(.el-button) { min-height: 28px; padding: 6px 10px; }
</style>
