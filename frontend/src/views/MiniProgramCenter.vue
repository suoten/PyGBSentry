<template>
  <div class="app-page space-y-4" v-loading="loading">
    <PageContainer>
      <template #header>
        <PageHeader title="微信小程序" description="版本发布、远程配置与运行日志概览" />
      </template>
      <TableCard>
        <template #header><div class="font-medium">概览</div></template>
        <div class="space-y-3" style="color: var(--el-text-color-regular)">
        <div class="flex flex-wrap gap-3 items-center">
          <el-tag type="success">最新版本：{{ version.latest_version || '-' }}</el-tag>
          <el-tag :type="version.force_update ? 'danger' : 'info'">强制更新：{{ version.force_update ? '是' : '否' }}</el-tag>
          <el-tag type="warning">灰度比例：{{ version.rollout_ratio ?? 100 }}%</el-tag>
        </div>
        <div class="flex gap-2">
          <el-button v-if="version.miniprogram_url" type="primary" @click="openUrl(version.miniprogram_url)">打开链接</el-button>
          <el-button @click="reload">刷新</el-button>
          <el-button v-if="loadError" type="warning" @click="reload">重试</el-button>
        </div>
        <div class="text-sm">
          <div>最近 24h 日志：{{ stats.total }}</div>
          <div>最近 24h 崩溃：{{ stats.crash_total }}</div>
        </div>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>远程配置</template>
          <pre class="text-xs whitespace-pre-wrap">{{ remoteConfigText }}</pre>
        </el-alert>
      </div>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'

const loading = ref(false)
const loadError = ref(false)

const version = ref({
  latest_version: '',
  force_update: false,
  rollout_ratio: 100,
  miniprogram_url: ''
})
const stats = ref({ total: 0, crash_total: 0 })
const remoteConfigText = ref('{}')

const openUrl = (url: string) => {
  window.open(url, '_blank')
}

const reload = async () => {
  loading.value = true
  loadError.value = false
  try {
    const [versionRes, logStats, remoteCfg] = await Promise.all([
      api.get('/api/v1/plugins/app-version-check', { params: { plugin_id: 'mini_program_suite', platform: 'miniprogram', current_version: version.value.latest_version || '0.0.0', release_channel: 'stable', device_id: 'web-console' } }),
      api.get('/api/v1/apps/stats', { params: { plugin_id: 'mini_program_suite', days: 1 } }),
      api.get('/api/v1/apps/remote-config', { params: { plugin_id: 'mini_program_suite', app_version: version.value.latest_version || '0.0.0' } })
    ])
    version.value = {
      latest_version: versionRes.data?.latest_version || '',
      force_update: Boolean(versionRes.data?.force_update),
      rollout_ratio: Number(versionRes.data?.rollout_ratio ?? 100),
      miniprogram_url: versionRes.data?.download_url || ''
    }
    stats.value = {
      total: Number(logStats.data?.total || 0),
      crash_total: Number(logStats.data?.crash_total || 0)
    }
    remoteConfigText.value = JSON.stringify(remoteCfg.data?.config || {}, null, 2)
  } catch (e: unknown) {
    loadError.value = true
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>
