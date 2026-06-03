<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="应用日志" description="移动端与小程序上报的崩溃与行为日志">
          <template #actions>
            <el-button type="primary" :loading="loading" @click="reload">刷新</el-button>
          </template>
        </PageHeader>
      </template>

      <QueryFormSection title="筛选" :default-collapsed="true">
        <el-form-item label="应用">
          <el-select v-model="pluginId" placeholder="应用" clearable style="width: 160px">
            <el-option label="全部" :value="''" />
            <el-option label="手机版" value="mobile_app_suite" />
            <el-option label="小程序" value="mini_program_suite" />
          </el-select>
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="platform" placeholder="平台" clearable style="width: 120px">
            <el-option label="全部" :value="''" />
            <el-option label="安卓" value="android" />
            <el-option label="iOS" value="ios" />
            <el-option label="小程序" value="miniprogram" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="logType" placeholder="类型" clearable style="width: 120px">
            <el-option label="全部" :value="''" />
            <el-option label="崩溃" value="crash" />
            <el-option label="行为" value="behavior" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="reload" :loading="loading" type="primary">查询</el-button>
        </el-form-item>
      </QueryFormSection>

      <TableCard class="mt-4">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">列表</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ total }} 条</div>
          </div>
        </template>
      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="plugin_id" label="应用" width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ row.plugin_id === 'mini_program_suite' ? '小程序' : '手机版' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="app_version" label="版本" width="100" />
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="log_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="row.log_type === 'crash' ? 'danger' : 'info'" size="small">
              {{ row.log_type === 'crash' ? '崩溃' : '行为' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="extra" label="扩展" width="120" show-overflow-tooltip />
      </el-table>
      <div class="flex justify-end mt-4">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          prev-text="上一页"
          next-text="下一页"
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
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import QueryFormSection from '../components/QueryFormSection.vue'

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
