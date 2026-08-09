<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('structuredEvent.title')" :description="t('structuredEvent.description')" />
      </template>
      <TableCard>
        <template #header>
          <div class="w-full flex items-center justify-between gap-2">
            <div class="font-medium">{{ t('structuredEvent.searchConditions') }}</div>
            <div class="flex flex-wrap gap-2">
              <el-button size="small" @click="saveCurrentPreset">{{ t('structuredEvent.saveQuery') }}</el-button>
              <el-button size="small" type="primary" :loading="loading" @click="handleSearch">{{ t('structuredEvent.search') }}</el-button>
              <el-button size="small" @click="resetFilters">{{ t('structuredEvent.reset') }}</el-button>
            </div>
          </div>
        </template>
        <div class="mb-4 text-sm" style="color: var(--el-text-color-regular)">
          {{ t('structuredEvent.introPrefix') }}
          <router-link to="/config-center" class="text-sky-600 hover:underline">{{ t('structuredEvent.configCenter') }}</router-link>
          {{ t('structuredEvent.introSuffix') }}
        </div>
        <div class="mb-4 flex flex-wrap items-end gap-3">
          <el-select v-model="selectedPreset" :placeholder="t('structuredEvent.presetPlaceholder')" clearable style="width: 220px" @change="applyPreset">
            <el-option v-for="p in presets" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
          <el-select v-model="filters.event_type" :placeholder="t('structuredEvent.eventTypePlaceholder')" clearable style="width: 120px">
            <el-option :label="t('structuredEvent.face')" value="face" />
            <el-option :label="t('structuredEvent.plate')" value="plate" />
            <el-option :label="t('structuredEvent.behavior')" value="behavior" />
          </el-select>
          <el-input v-model="filters.device_id" :placeholder="t('structuredEvent.deviceIdPlaceholder')" clearable style="width: 140px" />
          <el-input v-model="filters.channel_id" :placeholder="t('structuredEvent.channelIdPlaceholder')" clearable style="width: 140px" />
          <el-date-picker
            v-model="filters.start_time"
            type="datetime"
            :placeholder="t('structuredEvent.startTimePlaceholder')"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 180px"
          />
          <el-date-picker
            v-model="filters.end_time"
            type="datetime"
            :placeholder="t('structuredEvent.endTimePlaceholder')"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 180px"
          />
          <el-button size="small" @click="applyQuickPreset('24h')">{{ t('structuredEvent.last24Hours') }}</el-button>
          <el-button size="small" @click="applyQuickPreset('7d')">{{ t('structuredEvent.last7Days') }}</el-button>
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
            <el-button size="small" text type="primary" @click="search">{{ t('structuredEvent.retry') }}</el-button>
          </template>
        </el-alert>
        <div class="flex flex-wrap justify-between items-center gap-2 mb-3">
          <div class="text-sm" style="color: var(--el-text-color-secondary)">{{ t('structuredEvent.hitCount', { total }) }}</div>
          <div class="flex gap-2">
            <el-button size="small" :disabled="!items.length" @click="exportCurrentCsv">{{ t('structuredEvent.exportCurrentPage') }}</el-button>
            <el-button size="small" :disabled="!selectedPreset" @click="removePreset">{{ t('structuredEvent.removePreset') }}</el-button>
          </div>
        </div>
        <el-table v-loading="loading" :data="items" stripe class="w-full" row-key="id">
          <el-table-column prop="event_type" :label="t('structuredEvent.typeColumn')" width="100" />
          <el-table-column prop="source_plugin" :label="t('structuredEvent.sourcePluginColumn')" width="150" />
          <el-table-column prop="device_id" :label="t('structuredEvent.deviceIdColumn')" width="140" />
          <el-table-column prop="channel_id" :label="t('structuredEvent.channelIdColumn')" width="140" />
          <el-table-column prop="event_time" :label="t('structuredEvent.eventTimeColumn')" width="190" />
          <el-table-column prop="payload_text" :label="t('structuredEvent.eventContentColumn')" min-width="220" show-overflow-tooltip />
          <el-table-column :label="t('structuredEvent.operationColumn')" width="320" fixed="right">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-1">
                <el-button size="small" @click="openDetail(row)">{{ t('structuredEvent.detail') }}</el-button>
                <el-button size="small" type="primary" @click="goMap(row)">{{ t('structuredEvent.mapLink') }}</el-button>
                <el-button size="small" @click="goAlarms(row)">{{ t('structuredEvent.alarmCenter') }}</el-button>
                <el-button size="small" @click="goRecords(row)">{{ t('structuredEvent.recordPlayback') }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && !errorText && !items.length" class="py-8 text-center text-sm" style="color: var(--el-text-color-secondary)">
          {{ t('structuredEvent.noMatchHint') }}
        </div>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="total > 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            :prev-text="t('structuredEvent.prevPage')"
            :next-text="t('structuredEvent.nextPage')"
            size="small"
            @current-change="search"
            @size-change="handleSearch"
          />
        </div>
      </TableCard>
    </PageContainer>
    <el-drawer v-model="drawerVisible" :title="t('structuredEvent.detailTitle')" direction="rtl" size="min(720px, 92vw)">
      <div class="space-y-3">
        <el-descriptions :column="1" border>
          <el-descriptions-item :label="t('structuredEvent.eventId')">{{ activeItem?.id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('structuredEvent.eventTypeLabel')">{{ activeItem?.event_type || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('structuredEvent.sourcePluginLabel')">{{ activeItem?.source_plugin || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('structuredEvent.deviceIdLabel')">{{ activeItem?.device_id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('structuredEvent.channelIdLabel')">{{ activeItem?.channel_id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('structuredEvent.eventTimeLabel')">{{ activeItem?.event_time || '-' }}</el-descriptions-item>
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
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
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
const { t } = useI18n()  // FIXED: 国际化
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
  const name = await ElMessageBox.prompt(t('structuredEvent.promptPresetName'), t('structuredEvent.promptSaveQueryTitle'), {
    confirmButtonText: t('structuredEvent.confirmSave'),
    cancelButtonText: t('structuredEvent.cancel'),
    inputValue: selectedPreset.value || '',
    inputPattern: /\S+/,
    inputErrorMessage: t('structuredEvent.nameRequiredError')
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
  ElMessage.success(t('structuredEvent.presetSaved'))  // FIXED: 硬编码中文→i18n
}

const removePreset = () => {
  const target = selectedPreset.value
  if (!target) return
  presets.value = presets.value.filter((p) => p.name !== target)
  selectedPreset.value = ''
  persistPresets()
  ElMessage.success(t('structuredEvent.presetDeleted'))  // FIXED: 硬编码中文→i18n
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
    errorText.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || t('structuredEvent.searchFailed')  // FIXED: 硬编码中文→i18n
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
