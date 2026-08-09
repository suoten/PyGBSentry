<template>
  <div class="min-h-screen flex flex-col items-center justify-center p-6">
    <div class="max-w-lg w-full p-8 rounded-2xl" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
      <h1 class="text-2xl font-bold mb-2" style="color: var(--el-text-color-primary)">{{ t('setupPage.title') }}</h1>
      <p class="mb-6" style="color: var(--el-text-color-secondary)">{{ t('setupPage.intro') }}</p>

      <el-card class="mb-6" shadow="never">
        <template #header><span class="font-medium">{{ t('setupPage.connectivityCheck') }}</span></template>
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span>{{ t('setupPage.database') }}</span>
            <el-tag size="small" :type="status.db_ok ? 'success' : 'danger'">{{ status.db_ok ? t('setupPage.normal') : t('setupPage.abnormal') }}</el-tag>
          </div>
            <p v-if="!status.db_ok && status.db_detail" class="text-sm text-red-600">{{ status.db_detail }}</p>
          <div class="flex items-center justify-between">
            <span>{{ t('setupPage.zlmService') }}</span>
            <el-tag size="small" :type="status.zlm_ok ? 'success' : 'danger'">{{ status.zlm_ok ? t('setupPage.normal') : t('setupPage.abnormal') }}</el-tag>
          </div>
          <p v-if="!status.zlm_ok && status.zlm_detail" class="text-sm text-red-600">{{ status.zlm_detail }}</p>
          <p v-if="!status.zlm_ok" class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('setupPage.zlmHint', { host: status.zlm_host, port: status.zlm_http_port }) }}</p>
        </div>
        <el-button class="mt-3" size="small" :loading="loading" @click="loadStatus">{{ t('setupPage.recheck') }}</el-button>
      </el-card>

      <p class="text-sm mb-4" style="color: var(--el-text-color-secondary)">{{ t('setupPage.configHint') }}</p>

      <div class="flex gap-3">
        <el-button type="primary" :loading="completing" @click="complete">{{ t('setupPage.completeAndEnter') }}</el-button>
        <el-button @click="$router.push('/dashboard')">{{ t('setupPage.later') }}</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const completing = ref(false)
const status = ref({
  wizard_completed: false,
  db_ok: false,
  db_detail: '',
  zlm_ok: false,
  zlm_detail: '',
  zlm_host: '',
  zlm_http_port: 0
})

const loadStatus = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/setup/status')
    status.value = {
      wizard_completed: res.data?.wizard_completed ?? false,
      db_ok: res.data?.db_ok ?? false,
      db_detail: res.data?.db_detail ?? '',
      zlm_ok: res.data?.zlm_ok ?? false,
      zlm_detail: res.data?.zlm_detail ?? '',
      zlm_host: res.data?.zlm_host ?? '',
      zlm_http_port: res.data?.zlm_http_port ?? 0
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : (friendly.message || t('setupPage.loadStatusFailed')))
  } finally {
    loading.value = false
  }
}

const complete = async () => {
  completing.value = true
  try {
    await api.post('/api/v1/setup/complete')
    ElMessage.success(t('setupPage.wizardCompleted'))
    router.replace('/dashboard')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    completing.value = false
  }
}

onMounted(() => {
  loadStatus()
})
</script>
