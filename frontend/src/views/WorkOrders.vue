<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="工单管理" description="告警升级与人工创建的处置工单">
          <template #actions>
            <el-button type="primary" @click="openCreate">创建工单</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">列表</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ orders.length }} 条</div>
          </div>
        </template>
      <TableSkeleton v-if="loading && orders.length === 0" :rows="5" />
      <el-table v-else :data="paginatedOrders" v-loading="loading" stripe border style="width: 100%" :empty-text="'暂无工单'">
        <template #empty>
          <EmptyStateWithAction description="暂无工单，可点击右上角「创建工单」新建，或从告警中心升级告警自动创建。">
            <template #action>
              <el-button type="primary" @click="openCreate">创建工单</el-button>
            </template>
          </EmptyStateWithAction>
        </template>
        <el-table-column prop="title" label="标题" min-width="220" />
        <el-table-column prop="category" label="分类" width="120">
          <template #default="scope">
            {{ categoryLabel(scope.row.category) }}
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="110">
          <template #default="scope">
            <el-tag :type="scope.row.priority === 'high' ? 'danger' : scope.row.priority === 'medium' ? 'warning' : 'info'" size="small">
              {{ priorityLabel(scope.row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'closed' ? 'success' : scope.row.status === 'resolved' ? 'warning' : 'info'" effect="plain" size="small">
              {{ statusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="alarm_id" label="关联报警ID" width="180" />
        <el-table-column prop="assignee_user_id" label="经办人" width="180" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="scope">
            <div class="table-action-inline">
              <el-button size="small" @click="openEdit(scope.row)" :disabled="!canEditOrder(scope.row)">编辑</el-button>
              <el-button size="small" type="warning" @click="updateStatus(scope.row.id, 'in_progress')" :disabled="!canSwitchStatus(scope.row, 'in_progress')">进行中</el-button>
              <el-button size="small" type="success" @click="updateStatus(scope.row.id, 'resolved')" :disabled="!canSwitchStatus(scope.row, 'resolved')">解决</el-button>
              <el-dropdown trigger="click" @command="(cmd: string) => handleOrderMoreCommand(scope.row, cmd)">
                <el-button size="small" plain class="table-action-more">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="closed" :disabled="!canSwitchStatus(scope.row, 'closed')">关闭</el-dropdown-item>
                    <el-dropdown-item command="delete" divided :disabled="!canDeleteOrder(scope.row)">删除</el-dropdown-item>
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
          prev-text="上一页"
          next-text="下一页"
          size="small"
        />
      </div>
      </TableCard>

      <AppDialog v-model="createVisible" title="创建工单" size="medium">
        <el-form ref="createFormRef" :model="createForm" :rules="orderFormRules" label-width="100px">
          <el-form-item label="标题" prop="title"><el-input v-model="createForm.title" placeholder="工单标题" /></el-form-item>
          <el-form-item label="工单分类">
            <el-select v-model="createForm.category">
              <el-option label="技术支持 (Tech Support)" value="tech_support" />
              <el-option v-if="isServerEdition" label="账单与授权 (Billing)" value="billing" />
              <el-option label="其他 (Other)" value="other" />
            </el-select>
          </el-form-item>
          <el-form-item label="关联报警ID"><el-input v-model="createForm.alarm_id" placeholder="可选" /></el-form-item>
          <el-form-item label="优先级">
            <el-select v-model="createForm.priority">
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
            </el-select>
          </el-form-item>
          <el-form-item label="经办人"><el-input v-model="createForm.assignee_user_id" placeholder="可选，填写用户ID" /></el-form-item>
          <el-form-item label="描述" prop="description"><el-input v-model="createForm.description" type="textarea" :rows="4" placeholder="请填写处置描述（至少4个字）" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCreate" :loading="createSubmitting">创建</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="editVisible" title="编辑工单" size="medium">
        <el-form ref="editFormRef" :model="editForm" :rules="orderFormRules" label-width="100px">
          <el-form-item label="标题" prop="title"><el-input v-model="editForm.title" placeholder="工单标题" /></el-form-item>
          <el-form-item label="优先级">
            <el-select v-model="editForm.priority">
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
            </el-select>
          </el-form-item>
          <el-form-item label="经办人"><el-input v-model="editForm.assignee_user_id" placeholder="可选，填写用户ID" /></el-form-item>
          <el-form-item label="描述" prop="description"><el-input v-model="editForm.description" type="textarea" :rows="4" placeholder="请填写处置描述（至少4个字）" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" @click="submitEdit" :loading="editSubmitting">保存</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
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
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

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

const orderFormRules: FormRules = {
  title: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error('请填写标题'))
        if (text.length < 2) return callback(new Error('标题至少2个字符'))
        if (text.length > 255) return callback(new Error('标题不能超过255个字符'))
        callback()
      },
      trigger: 'blur'
    }
  ],
  description: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error('请填写描述'))
        if (text.length < 4) return callback(new Error('描述至少4个字符'))
        callback()
      },
      trigger: 'blur'
    }
  ]
}

const priorityLabel = (p: string) => ({ low: '低', medium: '中', high: '高' }[p] || p)
const categoryLabel = (c: string) => ({ tech_support: '技术支持', billing: '账单授权', other: '其他' }[c] || c)
const statusLabel = (s: string) => ({ open: '待处理', in_progress: '进行中', resolved: '已解决', closed: '已关闭' }[s] || s)

const fetchOrders = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/work-orders')
    orders.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    orders.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const updateStatus = async (id: string, status: string) => {
  try {
    await api.put(`/api/v1/work-orders/${id}`, { status })
    ElMessage.success('工单已更新')
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    ElMessage.warning('当前状态不允许编辑')
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
    ElMessage.success('工单已保存')
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    editSubmitting.value = false
  }
}

const deleteOrder = async (row: Record<string, unknown>) => {
  if (!canDeleteOrder(row)) {
    ElMessage.warning('仅已关闭工单可删除')
    return
  }
  try {
    await ElMessageBox.confirm('删除后不可恢复，确认删除该工单？', '删除工单', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/work-orders/${row.id}`)
    ElMessage.success('工单已删除')
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const handleOrderMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'closed') {
    if (!canSwitchStatus(row, 'closed')) {
      ElMessage.warning('当前状态不可关闭')
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
    ElMessage.success('工单创建成功')
    await fetchOrders()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
