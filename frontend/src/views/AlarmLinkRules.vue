<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('alarmRule.title')" :description="t('alarmRule.description')">
          <template #actions>
            <el-button type="primary" @click="openForm()">{{ t('alarmRule.addRule') }}</el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard>
      <el-table :data="paginatedRules" border v-loading="loading" :empty-text="t('alarmRule.emptyText')">
        <el-table-column prop="name" :label="t('alarmRule.nameColumn')" min-width="160" />
        <el-table-column :label="t('alarmRule.enabledColumn')" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? t('alarmRule.yes') : t('alarmRule.no') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('alarmRule.priorityRangeColumn')" width="160">
          <template #default="{ row }">
            <span v-if="row.min_priority || row.max_priority">
              {{ row.min_priority || 1 }} - {{ row.max_priority || 4 }}
            </span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('alarmRule.unlimited') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('alarmRule.timeRangeColumn')" width="160">
          <template #default="{ row }">
            <span v-if="row.start_time && row.end_time">
              {{ row.start_time }} - {{ row.end_time }}
            </span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('alarmRule.allDay') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('alarmRule.weekColumn')" width="140">
          <template #default="{ row }">
            <span v-if="row.days">
              {{ renderDays(row.days) }}
            </span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('alarmRule.everyday') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('alarmRule.orgLimitColumn')" min-width="160">
          <template #default="{ row }">
            <span v-if="row.organization_id">{{ row.organization_id }}</span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('alarmRule.unlimited') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('alarmRule.linkActionsColumn')" min-width="200">
          <template #default="{ row }">
            <el-tag v-if="row.link_record" type="success" size="small">{{ t('alarmRule.linkRecord') }}</el-tag>
            <el-tag v-if="row.link_wall" type="warning" size="small" class="ml-1">{{ t('alarmRule.linkWall') }}</el-tag>
            <el-tag v-if="row.link_notify" type="info" size="small" class="ml-1">{{ t('alarmRule.linkNotify') }}</el-tag>
            <span v-if="!row.link_record && !row.link_wall && !row.link_notify" class="text-xs" style="color: var(--el-text-color-secondary)">
              {{ t('alarmRule.notConfigured') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('alarmRule.operationColumn')" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">{{ t('alarmRule.edit') }}</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">{{ t('alarmRule.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex justify-end mt-4 pagination-wrapper" v-if="rules.length > 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="rules.length"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          :prev-text="t('alarmRule.prevPage')"
          :next-text="t('alarmRule.nextPage')"
          size="small"
        />
      </div>
    </TableCard>

    <AppDialog v-model="dialogVisible" :title="editingId ? t('alarmRule.editRuleTitle') : t('alarmRule.addRuleTitle')" size="small">
      <el-form :model="form" label-width="110px" size="small">
        <el-form-item :label="t('alarmRule.nameColumn')" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="t('alarmRule.enabledColumn')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item :label="t('alarmRule.priorityRangeColumn')">
          <div class="flex items-center gap-2">
            <el-input-number v-model="form.min_priority" :min="1" :max="4" />
            <span>-</span>
            <el-input-number v-model="form.max_priority" :min="1" :max="4" />
            <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('alarmRule.priorityHint') }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="t('alarmRule.timeRangeColumn')">
          <div class="flex items-center gap-2">
            <el-time-picker v-model="timeRange" is-range :range-separator="t('alarmRule.rangeSeparator')" :start-placeholder="t('alarmRule.startPlaceholder')" :end-placeholder="t('alarmRule.endPlaceholder')" format="HH:mm" value-format="HH:mm" />
            <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('alarmRule.allDayHint') }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="t('alarmRule.weekLimitLabel')">
          <el-select v-model="daysArray" multiple collapse-tags style="width: 100%" :placeholder="t('alarmRule.weekPlaceholder')">
            <el-option v-for="d in dayOptions" :key="d.value" :label="d.label" :value="d.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('alarmRule.orgLimitColumn')">
          <el-input v-model="form.organization_id" :placeholder="t('alarmRule.orgPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('alarmRule.linkActionsColumn')">
          <el-checkbox v-model="form.link_record">{{ t('alarmRule.linkRecord') }}</el-checkbox>
          <el-checkbox v-model="form.link_wall">{{ t('alarmRule.linkWallReserved') }}</el-checkbox>
          <el-checkbox v-model="form.link_notify">{{ t('alarmRule.linkNotifyReserved') }}</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('alarmRule.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">{{ t('alarmRule.save') }}</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'

type AlarmLinkRule = {
  id: string
  name: string
  enabled?: boolean
  min_priority?: number | null
  max_priority?: number | null
  start_time?: string
  end_time?: string
  days?: string
  organization_id?: string
  link_record?: boolean
  link_wall?: boolean
  link_notify?: boolean
}

const rules = ref<AlarmLinkRule[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)
const { t } = useI18n()  // FIXED: 国际化

const page = ref(1)
const pageSize = ref(10)
const paginatedRules = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return rules.value.slice(start, end)
})
watch(rules, () => { page.value = 1 })

const form = reactive({
  name: '',
  enabled: true,
  min_priority: null as number | null,
  max_priority: null as number | null,
  start_time: '',
  end_time: '',
  days: '',
  organization_id: '',
  link_record: true,
  link_wall: false,
  link_notify: false
})

const timeRange = ref<[string, string] | null>(null)
const daysArray = ref<number[]>([])

const dayOptions = computed(() => [  // FIXED: 静态 rules/columnOptions 改为 computed
  { label: t('alarmRule.monday'), value: 0 },
  { label: t('alarmRule.tuesday'), value: 1 },
  { label: t('alarmRule.wednesday'), value: 2 },
  { label: t('alarmRule.thursday'), value: 3 },
  { label: t('alarmRule.friday'), value: 4 },
  { label: t('alarmRule.saturday'), value: 5 },
  { label: t('alarmRule.sunday'), value: 6 }
])

const renderDays = (days: string) => {
  const set = new Set(
    String(days)
      .split(',')
      .map((x) => Number(x))
      .filter((x) => !Number.isNaN(x))
  )
  if (!set.size) return t('alarmRule.everyday')  // FIXED: 硬编码中文→i18n
  return dayOptions.value
    .filter((d) => set.has(d.value))
    .map((d) => d.label)
    .join(`、`)
}

const resetForm = () => {
  form.name = ''
  form.enabled = true
  form.min_priority = null
  form.max_priority = null
  form.start_time = ''
  form.end_time = ''
  form.days = ''
  form.organization_id = ''
  form.link_record = true
  form.link_wall = false
  form.link_notify = false
  timeRange.value = null
  daysArray.value = []
}

const fetchRules = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/alarms/link-rules')
    rules.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    rules.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const openForm = (row?: AlarmLinkRule) => {
  if (row) {
    editingId.value = row.id
    form.name = row.name
    form.enabled = !!row.enabled
    form.min_priority = row.min_priority ?? null
    form.max_priority = row.max_priority ?? null
    form.start_time = row.start_time || ''
    form.end_time = row.end_time || ''
    form.days = row.days || ''
    form.organization_id = row.organization_id || ''
    form.link_record = !!row.link_record
    form.link_wall = !!row.link_wall
    form.link_notify = !!row.link_notify
    timeRange.value = form.start_time && form.end_time ? [form.start_time, form.end_time] : null
    daysArray.value = form.days
      ? form.days
          .split(',')
          .map((x) => Number(x))
          .filter((x) => !Number.isNaN(x))
      : []
  } else {
    editingId.value = null
    resetForm()
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!form.name.trim()) {
    ElMessage.warning(t('alarmRule.inputNameWarning'))  // FIXED: 硬编码中文→i18n
    return
  }
  if (timeRange.value && timeRange.value.length === 2) {
    form.start_time = timeRange.value[0]
    form.end_time = timeRange.value[1]
  } else {
    form.start_time = ''
    form.end_time = ''
  }
  form.days = daysArray.value.length ? daysArray.value.join(',') : ''

  const payload: Record<string, string | number | boolean | null> = {
    name: form.name.trim(),
    enabled: form.enabled,
    min_priority: form.min_priority,
    max_priority: form.max_priority,
    start_time: form.start_time || null,
    end_time: form.end_time || null,
    days: form.days || null,
    organization_id: form.organization_id || null,
    link_record: form.link_record,
    link_wall: form.link_wall,
    link_notify: form.link_notify
  }

  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/v1/alarms/link-rules/${editingId.value}`, payload)
      ElMessage.success(t('alarmRule.ruleUpdated'))  // FIXED: 硬编码中文→i18n
    } else {
      await api.post('/api/v1/alarms/link-rules', payload)
      ElMessage.success(t('alarmRule.ruleCreated'))  // FIXED: 硬编码中文→i18n
    }
    dialogVisible.value = false
    await fetchRules()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    saving.value = false
  }
}

const handleDelete = async (row: AlarmLinkRule) => {
  try {
    await ElMessageBox.confirm(t('alarmRule.confirmDeleteRule', { name: row.name }), t('alarmRule.tipTitle'), { type: 'warning' })  // FIXED: 硬编码中文→i18n
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/alarms/link-rules/${row.id}`)
    ElMessage.success(t('alarmRule.ruleDeleted'))  // FIXED: 硬编码中文→i18n
    await fetchRules()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

onMounted(() => {
  fetchRules()
})
</script>

