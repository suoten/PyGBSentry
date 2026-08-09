<template>
  <AppDialog
    v-model="visible"
    :title="t('catalogSync.title')"
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
      <div v-else class="text-xs" style="color: var(--el-text-color-placeholder)">{{ t('catalogSync.requesting') }}</div>
    </div>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppDialog from '../common/AppDialog.vue'

const { t } = useI18n()

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
    synced: t('catalogSync.tagDone'),
    query_failed: t('catalogSync.tagFailed'),
    query_timeout: t('catalogSync.tagTimeout'),
    partial: t('catalogSync.tagInProgress'),
    response_received: t('catalogSync.tagProcessing'),
    query_sent: t('catalogSync.tagRequesting')
  }
  return map[state] || t('catalogSync.tagWaiting')
})

const subText = computed(() => {
  const runtime = props.runtime || {}
  const state = String(runtime?.['catalog.sync_state'] || '').trim()
  const errorText = String(runtime?.['catalog.last_error'] || '').trim()
  const total = Number(runtime?.['catalog.last_sum_num'] || 0)
  const received = Number(runtime?.['catalog.last_received_total'] || 0)

  const messages: Record<string, string> = {
    synced: total > 0 ? t('catalogSync.syncCompleteWithCount', { received: Math.max(0, received), total }) : t('catalogSync.syncComplete'),
    partial: total > 0 ? t('catalogSync.catalogReceivedWithCount', { received: Math.max(0, received), total }) : t('catalogSync.catalogPartial'),
    query_failed: errorText ? t('catalogSync.queryFailedWithError', { error: errorText }) : t('catalogSync.queryFailed'),
    query_timeout: t('catalogSync.queryTimeout'),
    query_sent: (() => {
      const retryAttempts = Number(runtime?.['catalog.retry_attempts'] || 1)
      return retryAttempts > 1 ? t('catalogSync.requestSentRetry', { round: retryAttempts }) : t('catalogSync.requestSent')
    })(),
    response_received: t('catalogSync.responseReceived')
  }
  if (messages[state]) return messages[state]
  if (errorText) return errorText
  return ''
})

const handleClosed = () => {
  emit('closed')
}
</script>
