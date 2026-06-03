<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="告警联动规则" description="按优先级、时间段、组织等条件配置联动动作">
          <template #actions>
            <el-button type="primary" @click="openForm()">新增规则</el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard>
      <el-table :data="paginatedRules" border v-loading="loading" :empty-text="'暂无联动规则'">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="优先级范围" width="160">
          <template #default="{ row }">
            <span v-if="row.min_priority || row.max_priority">
              {{ row.min_priority || 1 }} - {{ row.max_priority || 4 }}
            </span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">不限</span>
          </template>
        </el-table-column>
        <el-table-column label="时间段" width="160">
          <template #default="{ row }">
            <span v-if="row.start_time && row.end_time">
              {{ row.start_time }} - {{ row.end_time }}
            </span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">全天</span>
          </template>
        </el-table-column>
        <el-table-column label="星期" width="140">
          <template #default="{ row }">
            <span v-if="row.days">
              {{ renderDays(row.days) }}
            </span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">每天</span>
          </template>
        </el-table-column>
        <el-table-column label="组织限制" min-width="160">
          <template #default="{ row }">
            <span v-if="row.organization_id">{{ row.organization_id }}</span>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">不限</span>
          </template>
        </el-table-column>
        <el-table-column label="联动动作" min-width="200">
          <template #default="{ row }">
            <el-tag v-if="row.link_record" type="success" size="small">录像联动</el-tag>
            <el-tag v-if="row.link_wall" type="warning" size="small" class="ml-1">上墙</el-tag>
            <el-tag v-if="row.link_notify" type="info" size="small" class="ml-1">通知</el-tag>
            <span v-if="!row.link_record && !row.link_wall && !row.link_notify" class="text-xs" style="color: var(--el-text-color-secondary)">
              未配置
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
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
          prev-text="上一页"
          next-text="下一页"
          size="small"
        />
      </div>
    </TableCard>

    <AppDialog v-model="dialogVisible" :title="editingId ? '编辑规则' : '新增规则'" size="small">
      <el-form :model="form" label-width="110px" size="small">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="优先级范围">
          <div class="flex items-center gap-2">
            <el-input-number v-model="form.min_priority" :min="1" :max="4" />
            <span>-</span>
            <el-input-number v-model="form.max_priority" :min="1" :max="4" />
            <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">GB28181 优先级 1~4，数字越小级别越高</span>
          </div>
        </el-form-item>
        <el-form-item label="时间段">
          <div class="flex items-center gap-2">
            <el-time-picker v-model="timeRange" is-range range-separator="至" start-placeholder="开始" end-placeholder="结束" format="HH:mm" value-format="HH:mm" />
            <span class="text-xs" style="color: var(--el-text-color-secondary)">留空则全天</span>
          </div>
        </el-form-item>
        <el-form-item label="星期限制">
          <el-select v-model="daysArray" multiple collapse-tags style="width: 100%" placeholder="不选则每天">
            <el-option v-for="d in dayOptions" :key="d.value" :label="d.label" :value="d.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="组织限制">
          <el-input v-model="form.organization_id" placeholder="可选，按组织 ID 限制；留空不限" />
        </el-form-item>
        <el-form-item label="联动动作">
          <el-checkbox v-model="form.link_record">录像联动</el-checkbox>
          <el-checkbox v-model="form.link_wall">上墙（预留）</el-checkbox>
          <el-checkbox v-model="form.link_notify">通知（预留）</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
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

const dayOptions = [
  { label: '周一', value: 0 },
  { label: '周二', value: 1 },
  { label: '周三', value: 2 },
  { label: '周四', value: 3 },
  { label: '周五', value: 4 },
  { label: '周六', value: 5 },
  { label: '周日', value: 6 }
]

const renderDays = (days: string) => {
  const set = new Set(
    String(days)
      .split(',')
      .map((x) => Number(x))
      .filter((x) => !Number.isNaN(x))
  )
  if (!set.size) return '每天'
  return dayOptions
    .filter((d) => set.has(d.value))
    .map((d) => d.label)
    .join('、')
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
    ElMessage.warning('请输入规则名称')
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
      ElMessage.success('规则已更新')
    } else {
      await api.post('/api/v1/alarms/link-rules', payload)
      ElMessage.success('规则已创建')
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
    await ElMessageBox.confirm(`确认删除规则「${row.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/alarms/link-rules/${row.id}`)
    ElMessage.success('规则已删除')
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

