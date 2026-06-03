<template>
  <div class="min-h-screen flex flex-col items-center justify-center p-6">
    <div class="max-w-lg w-full p-8 rounded-2xl" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color);">
      <h1 class="text-2xl font-bold mb-2" style="color: var(--el-text-color-primary)">安装向导</h1>
      <p class="mb-6" style="color: var(--el-text-color-secondary)">首次部署请确认以下服务连通正常，完成后即可使用系统。</p>

      <el-card class="mb-6" shadow="never">
        <template #header><span class="font-medium">连通性检测</span></template>
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span>数据库</span>
            <el-tag size="small" :type="status.db_ok ? 'success' : 'danger'">{{ status.db_ok ? '正常' : '异常' }}</el-tag>
          </div>
            <p v-if="!status.db_ok && status.db_detail" class="text-sm text-red-600">{{ status.db_detail }}</p>
          <div class="flex items-center justify-between">
            <span>流媒体服务（ZLM）</span>
            <el-tag size="small" :type="status.zlm_ok ? 'success' : 'danger'">{{ status.zlm_ok ? '正常' : '异常' }}</el-tag>
          </div>
          <p v-if="!status.zlm_ok && status.zlm_detail" class="text-sm text-red-600">{{ status.zlm_detail }}</p>
          <p v-if="!status.zlm_ok" class="text-sm" style="color: var(--el-text-color-secondary)">当前配置：{{ status.zlm_host }}:{{ status.zlm_http_port }}，请确认 ZLMediaKit 已启动且端口正确。</p>
        </div>
        <el-button class="mt-3" size="small" :loading="loading" @click="loadStatus">重新检测</el-button>
      </el-card>

      <p class="text-sm mb-4" style="color: var(--el-text-color-secondary)">数据库与 ZLM 的地址、端口等需在服务端环境变量或配置文件中修改，修改后重启后端生效。本页仅做连通性检测。</p>

      <div class="flex gap-3">
        <el-button type="primary" :loading="completing" @click="complete">完成配置，进入系统</el-button>
        <el-button @click="$router.push('/dashboard')">稍后再说</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'

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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : (friendly.message || '获取状态失败'))
  } finally {
    loading.value = false
  }
}

const complete = async () => {
  completing.value = true
  try {
    await api.post('/api/v1/setup/complete')
    ElMessage.success('安装向导已完成')
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
