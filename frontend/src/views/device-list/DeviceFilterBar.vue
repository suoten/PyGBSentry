<template>
  <QueryFormSection title="筛选" :default-collapsed="true" class="mb-6">
    <el-form-item label="组织">
      <el-select v-model="filterOrganizationId" placeholder="全部组织" clearable class="filter-control filter-control--wide" @change="onFilterChange">
        <el-option label="全部" value="" />
        <el-option v-for="opt in organizationOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="搜索">
      <el-input ref="deviceKeywordInputRef" v-model="deviceKeyword" placeholder="设备国标ID/名称/厂家" clearable class="filter-control filter-control--wide" @keyup.enter="triggerKeywordSearch" @clear="triggerKeywordSearch" />
    </el-form-item>
    <el-form-item label="在线状态">
      <el-select v-model="deviceStatus" class="filter-control" clearable placeholder="全部" @change="onFilterChange">
        <el-option label="全部" value="" />
        <el-option label="在线" :value="1" />
        <el-option label="离线" :value="0" />
      </el-select>
    </el-form-item>
    <el-form-item :label="t('common.action')">
      <ActionButtons primary-text="查询设备" secondary-text="重置筛选" @primary="triggerKeywordSearch" @secondary="resetFilters" />
    </el-form-item>
    <div class="filter-summary-panel md:col-span-2">
      <div class="filter-summary-header">
        <span class="filter-summary-title">当前筛选</span>
        <span class="filter-summary-meta">双击设备行可进入通道工作区</span>
      </div>
      <div class="filter-summary-chips">
        <span class="filter-summary-chip">组织<strong>{{ activeOrganizationLabel }}</strong></span>
        <span class="filter-summary-chip">状态<strong>{{ activeDeviceStatusLabel }}</strong></span>
        <span class="filter-summary-chip">关键词<strong>{{ deviceKeyword.trim() || '未设置' }}</strong></span>
        <span class="filter-summary-chip filter-summary-chip--accent">当前结果<strong>{{ totalDisplay }}</strong></span>
      </div>
    </div>
  </QueryFormSection>

  <div class="device-stats-grid mb-4">
    <button class="stats-card" :class="{ active: deviceStatus === '' }" @click="setStatusFilter('')">
      <span class="stats-label">全部设备</span><span class="stats-value">{{ deviceStatsTotal }}</span>
    </button>
    <button class="stats-card" :class="{ active: deviceStatus === 1 }" @click="setStatusFilter(1)">
      <span class="stats-label">在线设备</span><span class="stats-value text-emerald-600">{{ deviceStatsOnline }}</span>
    </button>
    <button class="stats-card" :class="{ active: deviceStatus === 0 }" @click="setStatusFilter(0)">
      <span class="stats-label">离线设备</span><span class="stats-value text-slate-500">{{ deviceStatsOffline }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import QueryFormSection from '../../components/QueryFormSection.vue'
import ActionButtons from '../../components/ActionButtons.vue'
import { useI18n } from 'vue-i18n' // FIXED: 国际化

const props = defineProps<{
  organizationOptions: { id: string; label: string }[]
  totalDisplay: number
  deviceStatsTotal: number
  deviceStatsOnline: number
  deviceStatsOffline: number
  pageSize: number
}>()
const { t } = useI18n() // FIXED: 国际化

const emit = defineEmits<{
  (e: 'search'): void
}>()

const DEVICE_FILTER_PREFS_KEY = 'pygbsentry:devices:filters:v1'
const filterOrganizationId = ref<string>('')
const deviceKeyword = ref<string>('')
const deviceStatus = ref<number | ''>('')
const restoredPageSize = ref(10) // only used to communicate initial pageSize back to parent

type FocusableInputRef = { focus?: () => void }
const deviceKeywordInputRef = ref<FocusableInputRef | null>(null)

const activeOrganizationLabel = computed(() => {
  const cur = props.organizationOptions.find((item) => item.id === filterOrganizationId.value)
  return cur?.label || '全部组织'
})
const activeDeviceStatusLabel = computed(() => {
  if (deviceStatus.value === 1) return '仅在线'
  if (deviceStatus.value === 0) return '仅离线'
  return '全部状态'
})

const persistFilterPrefs = () => {
  try {
    localStorage.setItem(DEVICE_FILTER_PREFS_KEY, JSON.stringify({
      organization_id: String(filterOrganizationId.value || ''),
      keyword: String(deviceKeyword.value || ''),
      status: deviceStatus.value === '' ? '' : Number(deviceStatus.value),
      page_size: Number(props.pageSize) || 10
    }))
  } catch { /* cleanup: ignore */ }
}
const restoreFilterPrefs = () => {
  try {
    const raw = localStorage.getItem(DEVICE_FILTER_PREFS_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    filterOrganizationId.value = String(parsed?.organization_id || '')
    deviceKeyword.value = String(parsed?.keyword || '')
    deviceStatus.value = parsed?.status === '' || parsed?.status == null ? '' : Number(parsed.status)
    const nextPageSize = Number(parsed?.page_size || 10)
    restoredPageSize.value = nextPageSize > 0 ? nextPageSize : 10
  } catch { /* cleanup: ignore */ }
}

const onFilterChange = () => emit('search')
const triggerKeywordSearch = () => emit('search')
const resetFilters = () => { filterOrganizationId.value = ''; deviceKeyword.value = ''; deviceStatus.value = ''; emit('search') }
const setStatusFilter = (status: '' | 0 | 1) => { deviceStatus.value = status; emit('search') }

watch([filterOrganizationId, deviceKeyword, deviceStatus, () => props.pageSize], () => persistFilterPrefs())

onMounted(() => restoreFilterPrefs())

defineExpose({
  filterOrganizationId, deviceKeyword, deviceStatus, restoredPageSize,
  focusKeywordInput: () => deviceKeywordInputRef.value?.focus?.(),
  restoreFilterPrefs
})
</script>

<style scoped>
.filter-control { width: 180px; }
.filter-control--wide { width: 240px; }
.filter-actions-item :deep(.el-form-item__content) { align-items: center; }
.filter-summary-panel { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border: 1px solid rgba(226, 232, 240, 0.88); border-radius: 6px; background: #fafafa; box-shadow: none; }
.filter-summary-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.filter-summary-title { font-size: 13px; font-weight: 700; color: var(--el-text-color-primary); }
.filter-summary-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.filter-summary-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.filter-summary-chip { display: inline-flex; align-items: center; gap: 6px; min-height: 26px; padding: 0 10px; border: 1px solid var(--el-border-color); border-radius: 3px; background: var(--el-bg-color); color: var(--el-text-color-secondary); font-size: 12px; }
.filter-summary-chip strong { color: var(--el-text-color-primary); font-weight: 700; }
.filter-summary-chip--accent { border-color: var(--el-color-primary-light-7); background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.device-stats-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.stats-card { border: 1px solid rgba(226, 232, 240, 0.88); border-radius: 6px; background: #ffffff; min-height: 48px; padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; gap: 10px; cursor: pointer; box-shadow: none; transition: transform var(--transition-time-02), box-shadow var(--transition-time-02), border-color var(--transition-time-02), background-color var(--transition-time-02); }
.stats-card:hover { border-color: var(--el-color-primary-light-7); transform: none; box-shadow: none; }
.stats-card.active { border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); box-shadow: none; }
.stats-card:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 1px; box-shadow: none; }
.stats-label { font-size: 12px; line-height: 1.2; color: var(--el-text-color-secondary); font-weight: 500; }
.stats-value { font-size: 16px; line-height: 1.2; font-weight: 700; color: var(--el-text-color-primary); white-space: nowrap; }
@media (max-width: 1200px) { .device-stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 960px) { .filter-control, .filter-control--wide { width: 100%; } .device-stats-grid { grid-template-columns: 1fr; } .filter-summary-header { align-items: flex-start; } }
</style>
