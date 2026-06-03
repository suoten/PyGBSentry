<template>
  <div class="panel-box">
    <el-button size="small" :loading="loading === 'on'" @click="sendWiper('on')">开启</el-button>
    <el-button size="small" :loading="loading === 'off'" @click="sendWiper('off')">关闭</el-button>
    <el-button size="small" :loading="loading === 'stop'" @click="sendWiper('stop')">停止</el-button>
    <span class="muted-text">雨刷控制为设备兼容能力，部分设备可能不支持。</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../../utils/errorMessage'

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
    ElMessage.success('雨刷命令已发送')
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, '雨刷控制失败'))
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
