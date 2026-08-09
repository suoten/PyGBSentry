<template>
  <div class="app-page space-y-4" v-loading="loading">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('mobileAppCenter.title')" :description="t('mobileAppCenter.description')" />
      </template>
      <TableCard>
        <template #header><div class="font-medium">{{ t('mobileAppCenter.overview') }}</div></template>
        <div class="space-y-3" style="color: var(--el-text-color-regular)">
        <div class="flex flex-wrap gap-3 items-center">
          <el-tag type="success">{{ t('mobileAppCenter.latestVersion') }}：{{ version.latest_version || '-' }}</el-tag>
          <el-tag :type="version.force_update ? 'danger' : 'info'">{{ t('mobileAppCenter.forceUpdate') }}：{{ version.force_update ? t('common.yes') : t('common.no') }}</el-tag>
          <el-tag type="warning">{{ t('mobileAppCenter.rolloutRatio') }}：{{ version.rollout_ratio ?? 100 }}%</el-tag>
        </div>
        <div class="flex flex-wrap gap-2">
          <el-button v-if="version.android_url" type="primary" @click="openUrl(version.android_url)">{{ t('mobileAppCenter.androidDownload') }}</el-button>
          <el-button v-if="version.ios_url" @click="openUrl(version.ios_url)">{{ t('mobileAppCenter.iosDownload') }}</el-button>
          <el-button @click="reload">{{ t('common.refresh') }}</el-button>
          <el-button v-if="loadError" type="warning" @click="reload">{{ t('common.retry') }}</el-button>
        </div>
        <div class="text-sm">
          <div>{{ t('mobileAppCenter.logs24h') }}：{{ stats.total }}</div>
          <div>{{ t('mobileAppCenter.crashes24h') }}：{{ stats.crash_total }}</div>
        </div>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>{{ t('mobileAppCenter.remoteConfig') }}</template>
          <pre class="text-xs whitespace-pre-wrap">{{ remoteConfigText }}</pre>
        </el-alert>
      </div>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'

const { t } = useI18n()

const loading = ref(false)
const loadError = ref(false)
const version = ref({
  latest_version: '',
  force_update: false,
  rollout_ratio: 100,
  android_url: '',
  ios_url: ''
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
    const [android, ios, logStats, remoteCfg] = await Promise.all([
      api.get('/api/v1/plugins/app-version-check', { params: { plugin_id: 'mobile_app_suite', platform: 'android', current_version: version.value.latest_version || '0.0.0', release_channel: 'stable', device_id: 'web-console' } }),
      api.get('/api/v1/plugins/app-version-check', { params: { plugin_id: 'mobile_app_suite', platform: 'ios', current_version: version.value.latest_version || '0.0.0', release_channel: 'stable', device_id: 'web-console' } }),
      api.get('/api/v1/apps/stats', { params: { plugin_id: 'mobile_app_suite', days: 1 } }),
      api.get('/api/v1/apps/remote-config', { params: { plugin_id: 'mobile_app_suite', app_version: version.value.latest_version || '0.0.0' } })
    ])
    version.value = {
      latest_version: android.data?.latest_version || ios.data?.latest_version || '',
      force_update: Boolean(android.data?.force_update || ios.data?.force_update),
      rollout_ratio: Number(android.data?.rollout_ratio ?? ios.data?.rollout_ratio ?? 100),
      android_url: android.data?.download_url || '',
      ios_url: ios.data?.download_url || ''
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
