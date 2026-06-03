<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="多协议接入" description="汇总 RTSP/ONVIF/SDK 接入源与代理流">
          <template #actions>
            <el-button @click="refreshAll" :loading="loading">刷新</el-button>
          </template>
        </PageHeader>
      </template>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <el-card class="stats-card">
        <div class="mb-1 text-sm" style="color: var(--el-text-color-secondary)">接入源数量</div>
        <div class="text-2xl font-bold text-sky-400">{{ sources.length }}</div>
      </el-card>
      <el-card class="stats-card">
        <div class="mb-1 text-sm" style="color: var(--el-text-color-secondary)">代理流数量</div>
        <div class="text-2xl font-bold text-amber-300">{{ proxyStreams.length }}</div>
      </el-card>
      <el-card class="stats-card">
        <div class="mb-1 text-sm" style="color: var(--el-text-color-secondary)">总流数</div>
        <div class="text-2xl font-bold text-emerald-400">{{ streams.length }}</div>
      </el-card>
    </div>

    <div class="mb-6">
      <TableCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">接入源（RTSP/ONVIF/SDK）</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">在运维中心添加后，这里会汇总展示</div>
          </div>
        </template>
        <TableSkeleton v-if="loading && sources.length === 0" :rows="4" />
        <template v-else-if="sources.length === 0">
          <EmptyStateWithAction description="暂无接入源。请前往「运维中心」在「多协议接入源」中添加 RTSP/ONVIF 等源。">
            <template #action>
              <el-button type="primary" @click="$router.push('/ops')">前往运维中心</el-button>
            </template>
          </EmptyStateWithAction>
        </template>
        <el-table v-else :data="paginatedSources" border size="small" height="260" :empty-text="'暂无接入源，请在运维中心添加'">
          <el-table-column prop="name" :label="t('common.name')" min-width="140" />
          <el-table-column prop="protocol" label="协议" width="100" />
          <el-table-column label="地址" min-width="220">
            <template #default="{ row }">
              {{ row.host }}:{{ row.port }}{{ row.path ? '/' + row.path : '' }}
            </template>
          </el-table-column>
          <el-table-column prop="stream_name" label="流名称" min-width="140" />
          <el-table-column label="启用" width="90">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div class="mt-4 flex justify-end" v-if="sources.length > 0">
          <el-pagination
            v-model:current-page="sourcesPage"
            v-model:page-size="sourcesPageSize"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="sources.length"
          />
        </div>
      </TableCard>
    </div>

    <TableCard>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-medium">代理流（来自多协议接入源）</div>
          <div class="text-xs" style="color: var(--el-text-color-secondary)">展示拉流代理的会话与吞吐</div>
        </div>
      </template>
      <el-table :data="paginatedProxyStreams" border size="small" :empty-text="'当前无代理流'">
        <el-table-column prop="app" label="应用" width="90" />
        <el-table-column prop="stream" label="流ID" min-width="200" />
        <el-table-column prop="origin_url" label="源地址" min-width="260" show-overflow-tooltip />
        <el-table-column prop="reader_count" label="观看数" width="90" />
        <el-table-column prop="alive_second" label="存活(秒)" width="110" />
        <el-table-column prop="bytes_speed" label="字节/秒" width="120" />
      </el-table>
      <div class="mt-4 flex justify-end" v-if="proxyStreams.length > 0">
        <el-pagination
          v-model:current-page="proxyPage"
          v-model:page-size="proxyPageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="proxyStreams.length"
        />
      </div>
    </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const loading = ref(false)
const { t } = useI18n()  // FIXED: 国际化
const sources = ref<StreamProxy[]>([])
const streams = ref<StreamProxy[]>([])

const proxyStreams = computed(() => streams.value.filter((item) => item.is_proxy))

const sourcesPage = ref(1)
const sourcesPageSize = ref(10)
const paginatedSources = computed(() => {
  const start = (sourcesPage.value - 1) * sourcesPageSize.value
  return sources.value.slice(start, start + sourcesPageSize.value)
})
watch(() => sources.value, () => { sourcesPage.value = 1 })

const proxyPage = ref(1)
const proxyPageSize = ref(10)
const paginatedProxyStreams = computed(() => {
  const start = (proxyPage.value - 1) * proxyPageSize.value
  return proxyStreams.value.slice(start, start + proxyPageSize.value)
})
watch(() => proxyStreams.value, () => { proxyPage.value = 1 })

const refreshAll = async () => {
  loading.value = true
  try {
    const [srcRes, streamRes] = await Promise.all([
      api.get('/api/v1/integrations/sources'),
      api.get('/api/v1/stream/list')
    ])
    sources.value = Array.isArray(srcRes.data) ? srcRes.data : []
    streams.value = Array.isArray(streamRes.data) ? streamRes.data : []
  } catch (e: unknown) {
    sources.value = []
    streams.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.stats-card {
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.3s ease;
}

.stats-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border-color: #cbd5e1;
}
</style>

