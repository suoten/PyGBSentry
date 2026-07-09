<template>
  <slot v-if="!hasError" />
  <div v-else class="app-error-boundary">
    <el-result icon="warning" :title="t('appError.loadFailed')" :sub-title="t('common.refreshRetry')">
      <template #extra>
        <el-button type="primary" @click="retry">{{ t('common.refreshPage') }}</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { logger } from '@/utils/logger'

const { t } = useI18n()  // FIXED: 国际化

const hasError = ref(false)

onErrorCaptured((err, instance, info) => {
  logger.error('[AppErrorBoundary]', err, info)
  hasError.value = true
  return false
})

function retry() {
  hasError.value = false
  location.reload()
}
</script>

<style scoped>
.app-error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
</style>
