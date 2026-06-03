<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="结构化事件中心" description="统一检索人脸/车牌/行为事件，支持详情查看、联动跳转与导出" />
      </template>
      <TableCard>
        <template #header>
          <div class="w-full flex items-center justify-between gap-2">
            <div class="font-medium">检索条件</div>
            <div class="flex flex-wrap gap-2">
              <el-button size="small" @click="saveCurrentPreset">保存查询</el-button>
              <el-button size="small" type="primary" :loading="loading" @click="handleSearch">检索</el-button>
              <el-button size="small" @click="resetFilters">重置</el-button>
            </div>
          </div>
        </template>
        <div class="mb-4 text-sm" style="color: var(--el-text-color-regular)">
          人脸识别、车牌识别、行为识别插件可在
          <router-link to="/config-center" class="text-sky-600 hover:underline">配置中心</router-link>
          分别配置回调，事件会统一汇聚到本页进行检索与联动。
        </div>
        <div class="mb-4 flex flex-wrap items-end gap-3">
          <el-select v-model="selectedPreset" placeholder="查询预设" clearable style="width: 220px" @change="applyPreset">
            <el-option v-for="p in presets" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
          <el-select v-model="filters.event_type" placeholder="事件类型" clearable style="width: 120px">
            <el-option label="人脸" value="face" />
            <el-option label="车牌" value="plate" />
            <el-option label="行为" value="behavior" />
          </el-select>
          <el-input v-model="filters.device_id" placeholder="设备ID" clearable style="width: 140px" />
          <el-input v-model="filters.channel_id" placeholder="通道ID" clearable style="width: 140px" />
          <el-date-picker
            v-model="filters.start_time"
            type="datetime"
            placeholder="开始时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 180px"
          />
          <el-date-picker
            v-model="filters.end_time"
            type="datetime"
            placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 180px"
          />
          <el-button size="small" @click="applyQuickPreset('24h')">近24小时</el-button>
          <el-button size="small" @click="applyQuickPreset('7d')">近7天</el-button>
        </div>
        <el-alert
          v-if="errorText"
          type="error"
          show-icon
          :closable="false"
          class="mb-4"
          :title="errorText"
        >
          <template #default>
            <el-button size="small" text type="primary" @click="search">重试</el-button>
          </template>
        </el-alert>
        <div class="flex flex-wrap justify-between items-center gap-2 mb-3">
          <div class="text-sm" style="color: var(--el-text-color-secondary)">命中 {{ total }} 条事件</div>
          <div class="flex gap-2">
            <el-button size="small" :disabled="!items.length" @click="exportCurrentCsv">导出当前页</el-button>
            <el-button size="small" :disabled="!selectedPreset" @click="removePreset">删除预设</el-button>
          </div>
        </div>
        <el-table v-loading="loading" :data="items" stripe class="w-full" row-key="id">
          <el-table-column prop="event_type" label="类型" width="100" />
          <el-table-column prop="source_plugin" label="来源插件" width="150" />
          <el-table-column prop="device_id" label="设备ID" width="140" />
          <el-table-column prop="channel_id" label="通道ID" width="140" />
          <el-table-column prop="event_time" label="事件时间" width="190" />
          <el-table-column prop="payload_text" label="事件内容" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="320" fixed="right">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-1">
                <el-button size="small" @click="openDetail(row)">详情</el-button>
                <el-button size="small" type="primary" @click="goMap(row)">地图联动</el-button>
                <el-button size="small" @click="goAlarms(row)">告警中心</el-button>
                <el-button size="small" @click="goRecords(row)">录像回放</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && !errorText && !items.length" class="py-8 text-center text-sm" style="color: var(--el-text-color-secondary)">
          暂无匹配事件，可调整筛选条件后重试。
        </div>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="total > 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            prev-text="上一页"
            next-text="下一页"
            size="small"
            @current-change="search"
            @size-change="handleSearch"
          />
        </div>
      </TableCard>
    </PageContainer>
    <el-drawer v-model="drawerVisible" title="事件详情" direction="rtl" size="min(720px, 92vw)">
      <div class="space-y-3">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="事件ID">{{ activeItem?.id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="事件类型">{{ activeItem?.event_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源插件">{{ activeItem?.source_plugin || '-' }}</el-descriptions-item>
          <el-descriptions-item label="设备ID">{{ activeItem?.device_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="通道ID">{{ activeItem?.channel_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="事件时间">{{ activeItem?.event_time || '-' }}</el-descriptions-item>
        </el-descriptions>
        <el-input type="textarea" :rows="12" readonly :model-value="activePayloadText" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getFriendlyError } from '../utils/errorMessage'

type StructuredRow = {
  id?: string
  event_type?: string
  source_plugin?: string
  device_id?: string
  channel_id?: string
  event_time?: string
  payload?: unknown
  payload_text?: string
}

type SearchPreset = {
  name: string
  event_type: string
  device_id: string
  channel_id: string
}

const PRESET_KEY = 'ai_vision_search_presets_v1'
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorText = ref('')
const items = ref<StructuredRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const drawerVisible = ref(false)
const activeItem = ref<StructuredRow | null>(null)
const selectedPreset = ref('')
const presets = ref<SearchPreset[]>([])

const filters = reactive({
  event_type: '',
  device_id: '',
  channel_id: '',
  start_time: '',
  end_time: ''
})
let querySyncReady = false

const activePayloadText = computed(() => {
  if (!activeItem.value) return ''
  const payload = activeItem.value.payload
  if (typeof payload === 'string') return payload
  try {
    return JSON.stringify(payload ?? {}, null, 2)
  } catch {
    return String(payload ?? '')
  }
})

const loadPresets = () => {
  try {
    const raw = localStorage.getItem(PRESET_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    presets.value = Array.isArray(parsed) ? parsed.filter((x) => x && x.name) : []
  } catch {
    presets.value = []
  }
}

const persistPresets = () => {
  localStorage.setItem(PRESET_KEY, JSON.stringify(presets.value))
}

const applyPreset = () => {
  const hit = presets.value.find((p) => p.name === selectedPreset.value)
  if (!hit) return
  filters.event_type = hit.event_type || ''
  filters.device_id = hit.device_id || ''
  filters.channel_id = hit.channel_id || ''
  handleSearch()
}

const applyQuickPreset = (kind: '24h' | '7d') => {
  const end = new Date()
  const start = new Date(end)
  if (kind === '24h') {
    start.setHours(start.getHours() - 24)
  } else {
    start.setDate(start.getDate() - 7)
  }
  const fmt = (d: Date) => {
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  }
  filters.start_time = fmt(start)
  filters.end_time = fmt(end)
  handleSearch()
}

const saveCurrentPreset = async () => {
  const name = await ElMessageBox.prompt('输入预设名称', '保存查询', {
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputValue: selectedPreset.value || '',
    inputPattern: /\S+/,
    inputErrorMessage: '名称不能为空'
  }).then((res) => res.value).catch(() => '')
  const trimmed = String(name || '').trim()
  if (!trimmed) return
  const next: SearchPreset = {
    name: trimmed,
    event_type: filters.event_type,
    device_id: filters.device_id,
    channel_id: filters.channel_id
  }
  const idx = presets.value.findIndex((p) => p.name === trimmed)
  if (idx >= 0) {
    presets.value[idx] = next
  } else {
    presets.value.push(next)
  }
  selectedPreset.value = trimmed
  persistPresets()
  ElMessage.success('查询预设已保存')
}

const removePreset = () => {
  const target = selectedPreset.value
  if (!target) return
  presets.value = presets.value.filter((p) => p.name !== target)
  selectedPreset.value = ''
  persistPresets()
  ElMessage.success('预设已删除')
}

const resetFilters = () => {
  filters.event_type = ''
  filters.device_id = ''
  filters.channel_id = ''
  filters.start_time = ''
  filters.end_time = ''
  page.value = 1
  errorText.value = ''
  handleSearch()
}

const restoreStateFromQuery = () => {
  const q = route.query as Record<string, unknown>
  filters.event_type = String(q.event_type || '')
  filters.device_id = String(q.device_id || '')
  filters.channel_id = String(q.channel_id || '')
  filters.start_time = String(q.start_time || '')
  filters.end_time = String(q.end_time || '')
  const queryPage = Number(q.page || 1)
  const queryPageSize = Number(q.page_size || 10)
  page.value = Number.isFinite(queryPage) && queryPage > 0 ? queryPage : 1
  pageSize.value = Number.isFinite(queryPageSize) && queryPageSize > 0 ? queryPageSize : 10
  querySyncReady = true
}

const syncQuery = () => {
  if (!querySyncReady) return
  const next: Record<string, string> = {}
  if (filters.event_type) next.event_type = filters.event_type
  if (filters.device_id) next.device_id = filters.device_id
  if (filters.channel_id) next.channel_id = filters.channel_id
  if (filters.start_time) next.start_time = filters.start_time
  if (filters.end_time) next.end_time = filters.end_time
  if (page.value > 1) next.page = String(page.value)
  if (pageSize.value !== 10) next.page_size = String(pageSize.value)
  router.replace({ path: route.path, query: next })
}

async function search() {
  loading.value = true
  errorText.value = ''
  try {
    const params: Record<string, string | number | undefined> = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (filters.event_type) params.event_type = filters.event_type
    if (filters.device_id) params.device_id = filters.device_id
    if (filters.channel_id) params.channel_id = filters.channel_id
    if (filters.start_time) params.start_time = filters.start_time
    if (filters.end_time) params.end_time = filters.end_time
    const res = await api.get('/api/v1/structured/search', { params })
    items.value = (Array.isArray(res.data?.items) ? res.data.items : []).map((r: StructuredRow) => ({
      ...r,
      event_time: String(r.event_time || ''),
      payload_text: typeof r.payload === 'string' ? r.payload : JSON.stringify(r.payload ?? {})
    }))
    total.value = Number(res.data?.total || 0)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    errorText.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '检索失败'
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  search()
}

const openDetail = (row: StructuredRow) => {
  activeItem.value = row
  drawerVisible.value = true
}

const goMap = (row: StructuredRow) => {
  router.push({
    path: '/map',
    query: {
      device_id: String(row.device_id || ''),
      channel_id: String(row.channel_id || '')
    }
  })
}

const goAlarms = (row: StructuredRow) => {
  router.push({
    path: '/alarms',
    query: {
      device_id: String(row.device_id || ''),
      channel_id: String(row.channel_id || '')
    }
  })
}

const goRecords = (row: StructuredRow) => {
  router.push({
    path: '/device-records',
    query: {
      device_id: String(row.device_id || ''),
      channel_id: String(row.channel_id || ''),
      start_time: filters.start_time || '',
      end_time: filters.end_time || ''
    }
  })
}

const exportCurrentCsv = () => {
  const header = ['event_type', 'source_plugin', 'device_id', 'channel_id', 'event_time', 'payload']
  const rows = items.value.map((row) => [
    row.event_type || '',
    row.source_plugin || '',
    row.device_id || '',
    row.channel_id || '',
    row.event_time || '',
    row.payload_text || ''
  ])
  const escapeCsv = (val: string) => {
    const text = String(val ?? '')
    if (text.includes('"') || text.includes(',') || text.includes('\n')) {
      return `"${text.replace(/"/g, '""')}"`
    }
    return text
  }
  const csv = [header.join(','), ...rows.map((r) => r.map((x) => escapeCsv(String(x))).join(','))].join('\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `structured-events-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  loadPresets()
  restoreStateFromQuery()
  search()
})

watch(
  () => [filters.event_type, filters.device_id, filters.channel_id, filters.start_time, filters.end_time, page.value, pageSize.value],
  () => syncQuery(),
  { deep: false }
)
</script>
