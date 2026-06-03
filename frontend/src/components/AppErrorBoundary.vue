<template>
  <slot v-if="!hasError" />
  <div v-else class="app-error-boundary">
    <el-result icon="warning" title="页面加载异常" sub-title="请刷新重试">
      <template #extra>
        <el-button type="primary" @click="retry">刷新页面</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

const hasError = ref(false)

onErrorCaptured((err, instance, info) => {
  console.error('[AppErrorBoundary]', err, info)
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
