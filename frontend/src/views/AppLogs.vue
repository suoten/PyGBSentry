<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('appLogs.title')" :description="t('appLogs.description')">
          <template #actions>
            <el-button type="primary" :loading="loading" @click="reload">{{ t('common.refresh') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <QueryFormSection :title="t('appLogs.filter')" :default-collapsed="true">
        <el-form-item :label="t('appLogs.appLabel')">
          <el-select v-model="pluginId" :placeholder="t('appLogs.appPlaceholder')" clearable style="width: 160px">
            <el-option :label="t('common.all')" :value="''" />
            <el-option :label="t('appLogs.mobileApp')" value="mobile_app_suite" />
            <el-option :label="t('appLogs.miniProgram')" value="mini_program_suite" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('common.platform')">
          <el-select v-model="platform" :placeholder="t('appLogs.platformPlaceholder')" clearable style="width: 120px">
            <el-option :label="t('common.all')" :value="''" />
            <el-option :label="t('appLogs.android')" value="android" />
            <el-option label="iOS" value="ios" />
            <el-option :label="t('appLogs.miniProgram')" value="miniprogram" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('common.type')">
          <el-select v-model="logType" :placeholder="t('appLogs.typePlaceholder')" clearable style="width: 120px">
            <el-option :label="t('common.all')" :value="''" />
            <el-option :label="t('appLogs.crash')" value="crash" />
            <el-option :label="t('appLogs.behavior')" value="behavior" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('common.timeRange')">
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            :range-separator="t('appLogs.rangeSeparator')"
            :start-placeholder="t('appLogs.startPlaceholder')"
            :end-placeholder="t('appLogs.endPlaceholder')"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="reload" :loading="loading" type="primary">{{ t('common.search') }}</el-button>
        </el-form-item>
      </QueryFormSection>

      <TableCard class="mt-4">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('appLogs.list') }}</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('appLogs.totalCount', { n: total }) }}</div>
          </div>
        </template>
      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="created_at" :label="t('common.time')" width="180" />
        <el-table-column prop="plugin_id" :label="t('appLogs.appLabel')" width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ row.plugin_id === 'mini_program_suite' ? t('appLogs.miniProgram') : t('appLogs.mobileApp') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="app_version" :label="t('common.version')" width="100" />
        <el-table-column prop="platform" :label="t('common.platform')" width="100" />
        <el-table-column prop="log_type" :label="t('common.type')" width="80">
          <template #default="{ row }">
            <el-tag :type="row.log_type === 'crash' ? 'danger' : 'info'" size="small">
              {{ row.log_type === 'crash' ? t('appLogs.crash') : t('appLogs.behavior') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" :label="t('appLogs.content')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="extra" :label="t('appLogs.extra')" width="120" show-overflow-tooltip />
      </el-table>
      <div class="flex justify-end mt-4">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          :prev-text="t('appLogs.prevPage')"
          :next-text="t('appLogs.nextPage')"
          size="small"
          @current-change="handlePageChange"
          @size-change="() => { page = 1; fetchLogs() }"
        />
      </div>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import QueryFormSection from '../components/QueryFormSection.vue'

const { t } = useI18n()

interface LogItem {
  id: string
  tenant_id: string
  plugin_id: string
  app_version: string
  platform: string
  log_type: string
  message?: string
  extra?: string
  created_at: string
}

const loading = ref(false)
const items = ref<LogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const pluginId = ref<string | ''>('')
const platform = ref<string | ''>('')
const logType = ref<string | ''>('')
const timeRange = ref<[string, string] | null>(null)

const fetchLogs = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (pluginId.value) params.plugin_id = pluginId.value
    if (platform.value) params.platform = platform.value
    if (logType.value) params.log_type = logType.value
    if (timeRange.value && timeRange.value.length === 2) {
      params.start_time = timeRange.value[0]
      params.end_time = timeRange.value[1]
    }
    const res = await api.get('/api/v1/apps/logs', { params })
    items.value = Array.isArray(res.data?.items) ? res.data.items : []
    total.value = Number(res.data?.total ?? 0)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const reload = () => {
  page.value = 1
  fetchLogs()
}

const handlePageChange = (p: number) => {
  page.value = p
  fetchLogs()
}

onMounted(() => {
  fetchLogs()
})
</script>
