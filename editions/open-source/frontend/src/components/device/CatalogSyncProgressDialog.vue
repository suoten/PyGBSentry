<template>
  <AppDialog
    v-model="visible"
    title="目录同步"
    size="small"
    @closed="handleClosed"
  >
    <div class="flex flex-col items-center gap-4 py-2">
      <div class="text-sm text-center" style="color: var(--el-text-color-regular)">
        <template v-if="deviceName">
          <span class="font-medium">{{ deviceName }}</span>
          <span v-if="gbId" class="font-mono" style="color: var(--el-text-color-secondary)">（{{ gbId }}）</span>
        </template>
        <template v-else>
          <span class="font-mono font-medium">{{ gbId }}</span>
        </template>
      </div>
      <el-progress
        type="circle"
        :percentage="progressPercent"
        :width="120"
        :stroke-width="10"
        :status="progressStatus"
      >
        <span class="text-sm font-medium">{{ tagText }}</span>
      </el-progress>
      <div
        v-if="subText"
        class="text-xs text-center px-2 leading-relaxed"
        style="max-width: 400px; color: var(--el-text-color-secondary)"
      >
        {{ subText }}
      </div>
      <div v-else class="text-xs" style="color: var(--el-text-color-placeholder)">正在向设备请求目录，请稍候…</div>
    </div>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppDialog from '../common/AppDialog.vue'

interface Props {
  modelValue: boolean
  gbId: string
  deviceName: string
  runtime: Record<string, unknown>
  progressStatus: 'success' | 'exception' | undefined
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'closed'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const progressPercent = computed(() => {
  const runtime = props.runtime || {}
  const value = Number(runtime?.['catalog.progress'])
  if (Number.isFinite(value)) {
    return Math.max(0, Math.min(100, Math.round(value)))
  }
  const total = Number(runtime?.['catalog.last_sum_num'] || 0)
  const received = Number(runtime?.['catalog.last_received_total'] || 0)
  if (total > 0 && received >= 0) {
    return Math.max(0, Math.min(100, Math.round((received * 100) / total)))
  }
  const state = String(runtime?.['catalog.sync_state'] || '').trim()
  if (state === 'synced' || state === 'query_failed' || state === 'query_timeout') return 100
  if (state === 'query_sent') return 10
  if (state === 'response_received' || state === 'partial') return 80
  return 0
})

const tagText = computed(() => {
  const state = String(props.runtime?.['catalog.sync_state'] || '').trim()
  const map: Record<string, string> = {
    synced: '完成',
    query_failed: '失败',
    query_timeout: '超时',
    partial: '进行中',
    response_received: '处理中',
    query_sent: '请求中'
  }
  return map[state] || '等待中'
})

const subText = computed(() => {
  const runtime = props.runtime || {}
  const state = String(runtime?.['catalog.sync_state'] || '').trim()
  const errorText = String(runtime?.['catalog.last_error'] || '').trim()
  const total = Number(runtime?.['catalog.last_sum_num'] || 0)
  const received = Number(runtime?.['catalog.last_received_total'] || 0)

  const messages: Record<string, string> = {
    synced: total > 0 ? `目录同步完成（${Math.max(0, received)}/${total}）` : '目录同步完成',
    partial: total > 0 ? `已接收目录（${Math.max(0, received)}/${total}）` : '已收到部分目录，正在继续处理',
    query_failed: errorText ? `目录查询失败：${errorText}` : '目录查询失败',
    query_timeout: '目录查询超时，请稍后重试',
    query_sent: (() => {
      const retryAttempts = Number(runtime?.['catalog.retry_attempts'] || 1)
      return retryAttempts > 1 ? `已发起目录请求（第 ${retryAttempts} 次）` : '已发起目录请求，等待设备响应'
    })(),
    response_received: '已收到设备响应，正在处理目录数据'
  }
  if (messages[state]) return messages[state]
  if (errorText) return errorText
  return ''
})

const handleClosed = () => {
  emit('closed')
}
</script>
