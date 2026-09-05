<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('workOrderPage.title')" :description="t('workOrderPage.description')">
          <template #actions>
            <el-button type="primary" @click="openCreate">{{ t('workOrderPage.createOrder') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('workOrderPage.listLabel') }}</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('workOrderPage.totalCount', { count: orders.length }) }}</div>
          </div>
        </template>
      <TableSkeleton v-if="loading && orders.length === 0" :rows="5" />
      <el-table v-else :data="paginatedOrders" v-loading="loading" stripe border style="width: 100%" :empty-text="t('workOrderPage.noOrders')">
        <template #empty>
          <EmptyStateWithAction :description="t('workOrderPage.emptyDesc')">
            <template #action>
              <el-button type="primary" @click="openCreate">{{ t('workOrderPage.createOrder') }}</el-button>
            </template>
          </EmptyStateWithAction>
        </template>
        <el-table-column prop="title" :label="t('workOrderPage.colTitle')" min-width="220" />
        <el-table-column prop="category" :label="t('workOrderPage.colCategory')" width="120">
          <template #default="scope">
            {{ categoryLabel(scope.row.category) }}
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="t('workOrderPage.colPriority')" width="110">
          <template #default="scope">
            <el-tag :type="scope.row.priority === 'high' ? 'danger' : scope.row.priority === 'medium' ? 'warning' : 'info'" size="small">
              {{ priorityLabel(scope.row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="t('common.status')" width="120">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'closed' ? 'success' : scope.row.status === 'resolved' ? 'warning' : 'info'" effect="plain" size="small">
              {{ statusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="alarm_id" :label="t('workOrderPage.colAlarmId')" width="180" />
        <el-table-column prop="assignee_user_id" :label="t('workOrderPage.colAssignee')" width="180" />
        <el-table-column prop="created_at" :label="t('common.createTime')" width="180">
          <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.action')" width="300" fixed="right">
          <template #default="scope">
            <div class="table-action-inline">
              <el-button size="small" @click="openEdit(scope.row)" :disabled="!canEditOrder(scope.row)">{{ t('common.edit') }}</el-button>
              <el-button size="small" type="warning" @click="updateStatus(scope.row.id, 'in_progress')" :disabled="!canSwitchStatus(scope.row, 'in_progress')">{{ t('workOrderPage.btnInProgress') }}</el-button>
              <el-button size="small" type="success" @click="updateStatus(scope.row.id, 'resolved')" :disabled="!canSwitchStatus(scope.row, 'resolved')">{{ t('workOrderPage.btnResolve') }}</el-button>
              <el-dropdown trigger="click" @command="(cmd: string) => handleOrderMoreCommand(scope.row, cmd)">
                <el-button size="small" plain class="table-action-more">{{ t('common.more') }}</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="closed" :disabled="!canSwitchStatus(scope.row, 'closed')">{{ t('common.close') }}</el-dropdown-item>
                    <el-dropdown-item command="delete" divided :disabled="!canDeleteOrder(scope.row)">{{ t('common.delete') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex justify-end mt-4 pagination-wrapper" v-if="orders.length > 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="orders.length"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          :prev-text="t('common.prevPage')"
          :next-text="t('common.nextPage')"
          size="small"
        />
      </div>
      </TableCard>

      <AppDialog v-model="createVisible" :title="t('workOrderPage.createOrderTitle')" size="medium">
        <el-form ref="createFormRef" :model="createForm" :rules="orderFormRules" label-width="100px">
          <el-form-item :label="t('workOrderPage.colTitle')" prop="title"><el-input v-model="createForm.title" :placeholder="t('workOrderPage.titlePlaceholder')" /></el-form-item>
          <el-form-item :label="t('workOrderPage.colCategory')">
            <el-select v-model="createForm.category">
              <el-option :label="t('workOrderPage.categoryTechSupport')" value="tech_support" />
              <el-option v-if="isServerEdition" :label="t('workOrderPage.categoryBilling')" value="billing" />
              <el-option :label="t('workOrderPage.categoryOther')" value="other" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('workOrderPage.colAlarmId')"><el-input v-model="createForm.alarm_id" :placeholder="t('workOrderPage.optionalPlaceholder')" /></el-form-item>
          <el-form-item :label="t('workOrderPage.colPriority')">
            <el-select v-model="createForm.priority">
              <el-option :label="t('workOrderPage.priorityLow')" value="low" />
              <el-option :label="t('workOrderPage.priorityMedium')" value="medium" />
              <el-option :label="t('workOrderPage.priorityHigh')" value="high" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('workOrderPage.colAssignee')"><el-input v-model="createForm.assignee_user_id" :placeholder="t('workOrderPage.assigneePlaceholder')" /></el-form-item>
          <el-form-item :label="t('common.description')" prop="description"><el-input v-model="createForm.description" type="textarea" :rows="4" :placeholder="t('workOrderPage.descriptionPlaceholder')" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="submitCreate" :loading="createSubmitting">{{ t('workOrderPage.btnCreate') }}</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="editVisible" :title="t('workOrderPage.editOrderTitle')" size="medium">
        <el-form ref="editFormRef" :model="editForm" :rules="orderFormRules" label-width="100px">
          <el-form-item :label="t('workOrderPage.colTitle')" prop="title"><el-input v-model="editForm.title" :placeholder="t('workOrderPage.titlePlaceholder')" /></el-form-item>
          <el-form-item :label="t('workOrderPage.colPriority')">
            <el-select v-model="editForm.priority">
              <el-option :label="t('workOrderPage.priorityLow')" value="low" />
              <el-option :label="t('workOrderPage.priorityMedium')" value="medium" />
              <el-option :label="t('workOrderPage.priorityHigh')" value="high" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('workOrderPage.colAssignee')"><el-input v-model="editForm.assignee_user_id" :placeholder="t('workOrderPage.assigneePlaceholder')" /></el-form-item>
          <el-form-item :label="t('common.description')" prop="description"><el-input v-model="editForm.description" type="textarea" :rows="4" :placeholder="t('workOrderPage.descriptionPlaceholder')" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="submitEdit" :loading="editSubmitting">{{ t('common.save') }}</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import { getFriendlyError } from '../utils/errorMessage'
const isServerEdition = (import.meta.env.VITE_APP_EDITION || 'oss') === 'server'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import type { WorkOrder } from '@/types/models'

const { t } = useI18n()

const loading = ref(false)
const orders = ref<WorkOrder[]>([])

const page = ref(1)
const pageSize = ref(10)
const paginatedOrders = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return orders.value.slice(start, end)
})
watch(orders, () => { page.value = 1 })

const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createSubmitting = ref(false)
const createForm = ref({
  title: '',
  alarm_id: '',
  description: '',
  category: 'other',
  priority: 'medium',
  assignee_user_id: ''
})
const editVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editSubmitting = ref(false)
const editForm = ref({
  id: '',
  title: '',
  description: '',
  priority: 'medium',
  assignee_user_id: ''
})

const orderFormRules = computed<FormRules>(() => ({
  title: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('workOrderPage.validateTitleRequired')))
        if (text.length < 2) return callback(new Error(t('workOrderPage.validateTitleMinLength')))
        if (text.length > 255) return callback(new Error(t('workOrderPage.validateTitleMaxLength')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  description: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('workOrderPage.validateDescriptionRequired')))
        if (text.length < 4) return callback(new Error(t('workOrderPage.validateDescriptionMinLength')))
        callback()
      },
      trigger: 'blur'
    }
  ]
}))

const priorityLabel = (p: string) => {
  const map: Record<string, string> = {
    low: t('workOrderPage.priorityLow'),
    medium: t('workOrderPage.priorityMedium'),
    high: t('workOrderPage.priorityHigh')
  }
  return map[p] || p
}
const categoryLabel = (c: string) => {
  const map: Record<string, string> = {
    tech_support: t('workOrderPage.categoryTechSupportShort'),
    billing: t('workOrderPage.categoryBillingShort'),
    other: t('workOrderPage.categoryOther')
  }
  return map[c] || c
}
const statusLabel = (s: string) => {
  const map: Record<string, string> = {
    open: t('workOrderPage.statusOpen'),
    in_progress: t('workOrderPage.statusInProgress'),
    resolved: t('workOrderPage.statusResolved'),
    closed: t('workOrderPage.statusClosed')
  }
  return map[s] || s
}

const fetchOrders = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/work-orders')
    orders.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    orders.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    loading.value = false
  }
}

const updateStatus = async (id: string, status: string) => {
  try {
    await api.put(`/api/v1/work-orders/${id}`, { status })
    ElMessage.success(t('workOrderPage.orderUpdated'))
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  }
}

const canEditOrder = (row: Record<string, unknown>) => {
  const status = String(row?.status || '')
  return ['open', 'in_progress', 'resolved'].includes(status)
}

const canDeleteOrder = (row: Record<string, unknown>) => {
  const status = String(row?.status || '')
  return status === 'closed'
}

const canSwitchStatus = (row: Record<string, unknown>, target: string) => {
  const current = String(row?.status || 'open')
  if (current === target) return false
  const allowed: Record<string, string[]> = {
    open: ['in_progress', 'resolved', 'closed'],
    in_progress: ['open', 'resolved', 'closed'],
    resolved: ['in_progress', 'closed'],
    closed: []
  }
  return (allowed[current] || []).includes(target)
}

const openEdit = (row: Record<string, unknown>) => {
  if (!canEditOrder(row)) {
    ElMessage.warning(t('workOrderPage.cannotEdit'))
    return
  }
  editForm.value = {
    id: String(row?.id || ''),
    title: String(row?.title || ''),
    description: String(row?.description || ''),
    priority: String(row?.priority || 'medium'),
    assignee_user_id: String(row?.assignee_user_id || '')
  }
  editVisible.value = true
}

const submitEdit = async () => {
  const form = editFormRef.value
  if (!form) return
  const ok = await form.validate().catch(() => false)
  if (!ok) return
  editSubmitting.value = true
  try {
    await api.put(`/api/v1/work-orders/${editForm.value.id}`, {
      title: editForm.value.title.trim(),
      description: editForm.value.description.trim(),
      priority: editForm.value.priority,
      assignee_user_id: editForm.value.assignee_user_id.trim() || null
    })
    editVisible.value = false
    ElMessage.success(t('workOrderPage.orderSaved'))
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    editSubmitting.value = false
  }
}

const deleteOrder = async (row: Record<string, unknown>) => {
  if (!canDeleteOrder(row)) {
    ElMessage.warning(t('workOrderPage.onlyClosedCanDelete'))
    return
  }
  try {
    await ElMessageBox.confirm(t('workOrderPage.deleteConfirmMsg'), t('workOrderPage.deleteConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/work-orders/${row.id}`)
    ElMessage.success(t('workOrderPage.orderDeleted'))
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  }
}

const handleOrderMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'closed') {
    if (!canSwitchStatus(row, 'closed')) {
      ElMessage.warning(t('workOrderPage.cannotClose'))
      return
    }
    await updateStatus(String(row.id), 'closed')
  }
  if (cmd === 'delete') {
    await deleteOrder(row)
  }
}

const openCreate = () => {
  createForm.value = { title: '', alarm_id: '', description: '', category: 'other', priority: 'medium', assignee_user_id: '' }
  createVisible.value = true
}

const submitCreate = async () => {
  const form = createFormRef.value
  if (!form) return
  const ok = await form.validate().catch(() => false)
  if (!ok) return
  createSubmitting.value = true
  try {
    await api.post('/api/v1/work-orders', {
      title: createForm.value.title.trim(),
      alarm_id: createForm.value.alarm_id || null,
      description: createForm.value.description.trim(),
      category: createForm.value.category,
      priority: createForm.value.priority,
      assignee_user_id: createForm.value.assignee_user_id.trim() || null
    })
    createVisible.value = false
    createForm.value = { title: '', alarm_id: '', description: '', category: 'other', priority: 'medium', assignee_user_id: '' }
    ElMessage.success(t('workOrderPage.orderCreated'))
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    createSubmitting.value = false
  }
}

const formatDate = (value: string) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  fetchOrders()
})
</script>
