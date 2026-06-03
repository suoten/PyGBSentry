<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="用户管理" description="管理系统用户、角色与状态">
          <template #actions>
            <el-button type="primary" @click="openCreateUser">
              <el-icon class="mr-1"><Plus /></el-icon>
              新增用户
            </el-button>
            <el-button @click="openRoleManager">
              <el-icon class="mr-1"><Medal /></el-icon>
              角色管理
            </el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard class="users-card">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-bold text-slate-700 flex items-center gap-2">
            <el-icon class="text-emerald-500"><User /></el-icon>
            用户列表
          </div>
          <div class="text-xs text-slate-500 flex items-center gap-2">
            <el-icon><Document /></el-icon>
            共 {{ users.length }} 条
          </div>
        </div>
      </template>
      <TableSkeleton v-if="loading && users.length === 0" :rows="5" />
      <el-table v-else :data="paginatedUsers" style="width: 100%" v-loading="loading" :empty-text="'暂无用户'" class="users-table" fit>
        <template #empty>
          <EmptyStateWithAction description="暂无用户，请点击「新增用户」添加第一个用户（当前登录账号由系统创建）。">
            <template #action>
              <el-button type="primary" @click="openCreateUser">
                <el-icon class="mr-1"><Plus /></el-icon>
                新增用户
              </el-button>
            </template>
          </EmptyStateWithAction>
        </template>
        <el-table-column prop="username" :label="t('common.username')">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><User /></el-icon>
              <span>用户名</span>
            </div>
          </template>
          <template #default="scope">
            <div class="username-cell">
              <div class="avatar-wrapper">
                <span class="avatar-text">{{ scope.row.username.charAt(0).toUpperCase() }}</span>
              </div>
              <span class="username-text">{{ scope.row.username }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="full_name" label="姓名" min-width="140">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><UserFilled /></el-icon>
              <span>姓名</span>
            </div>
          </template>
          <template #default="scope">
            <div class="name-cell">
              <el-icon v-if="scope.row.full_name" class="text-emerald-400"><CircleCheck /></el-icon>
              <span>{{ scope.row.full_name || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="tenant_id" label="租户" width="160">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><OfficeBuilding /></el-icon>
              <span>租户</span>
            </div>
          </template>
          <template #default="scope">
            <el-tag size="small" type="info" effect="plain" class="tenant-tag">
              {{ scope.row.tenant_id }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.type')">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><Medal /></el-icon>
              <span>角色</span>
            </div>
          </template>
          <template #default="scope">
            <div class="role-cell">
              <el-tag :type="scope.row.is_superuser ? 'danger' : getRoleType(scope.row.role)" size="small" effect="dark" class="role-tag">
                <el-icon class="mr-1" v-if="scope.row.is_superuser"><Star /></el-icon>
                {{ scope.row.is_superuser ? '超级管理员' : roleLabel(scope.row.role) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.status')">
          <template #header>
            <div class="flex items-center justify-center gap-1">
              <el-icon class="text-slate-400"><Switch /></el-icon>
              <span>状态</span>
            </div>
          </template>
          <template #default="scope">
            <div class="status-cell">
              <span class="status-dot" :class="scope.row.is_active ? 'active' : 'inactive'"></span>
              <el-tag :type="scope.row.is_active ? 'success' : 'warning'" size="small" effect="dark">
                {{ scope.row.is_active ? '正常' : '停用' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action')">
          <template #header>
            <div class="flex items-center justify-center gap-1">
              <el-icon class="text-slate-400"><Tools /></el-icon>
              <span>操作</span>
            </div>
          </template>
          <template #default="scope">
            <div class="action-buttons">
              <el-button v-if="scope.row.is_locked" size="small" type="warning" plain @click="unlockUser(scope.row)" :loading="unlocking === String(scope.row.id)">
                <el-icon><Unlock /></el-icon>
              </el-button>
              <el-button size="small" type="primary" plain @click="openEdit(scope.row)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button size="small" type="danger" plain :disabled="!canDeleteUser(scope.row)" @click="removeUser(scope.row)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex justify-end mt-4 pagination-wrapper" v-if="users.length > 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="users.length"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          prev-text="上一页"
          next-text="下一页"
          size="small"
        />
      </div>
    </TableCard>

    <AppDialog
      v-model="dialogVisible"
      :title="editingId ? '编辑用户' : '新增用户'"
      size="medium"
      :icon="UserFilled"
      icon-color="success"
    >
      <el-form ref="formRef" :model="form" :rules="userFormRules" label-width="100px" class="user-form">
        <el-form-item :label="t('common.username')">
          <div class="input-wrapper">
            <el-icon class="input-icon"><User /></el-icon>
            <el-input v-model="form.username" :placeholder="t('user.loginNamePlaceholder')" class="form-input" :disabled="!!editingId" />
          </div>
        </el-form-item>
        <el-form-item v-if="!editingId" label="密码" prop="password">
          <div class="input-wrapper">
            <el-icon class="input-icon"><Lock /></el-icon>
            <el-input v-model="form.password" type="password" :placeholder="t('user.initialPasswordPlaceholder')" show-password class="form-input" />
          </div>
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <div class="input-wrapper">
            <el-icon class="input-icon"><UserFilled /></el-icon>
            <el-input v-model="form.full_name" :placeholder="t('user.namePlaceholder')" class="form-input" />
          </div>
        </el-form-item>
        <el-form-item label="超级管理员">
          <div class="switch-wrapper">
            <el-switch v-model="form.is_superuser" class="superuser-switch" />
            <span class="switch-hint text-sm text-slate-500">开启后将拥有系统最高权限</span>
          </div>
        </el-form-item>
        <el-form-item label="租户" prop="tenant_id">
          <div class="input-wrapper">
            <el-icon class="input-icon"><OfficeBuilding /></el-icon>
            <el-input v-model="form.tenant_id" placeholder="default" class="form-input" />
          </div>
        </el-form-item>
        <el-form-item :label="t('common.type')">
          <div class="select-wrapper">
            <el-icon class="input-icon"><Medal /></el-icon>
            <el-select v-model="form.role" class="form-select" :placeholder="t('user.selectRole')" filterable>
              <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item v-if="editingId" :label="t('common.status')">
          <div class="switch-wrapper">
            <el-switch v-model="form.is_active" />
            <span class="switch-hint text-sm text-slate-500">停用后将无法登录</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          <el-icon class="mr-1"><Close /></el-icon>
          取消
        </el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">
          <el-icon class="mr-1"><Check /></el-icon>
          确定
        </el-button>
      </template>
    </AppDialog>

    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  Plus, User, Document, OfficeBuilding, Medal, Star, Switch, Tools, Edit, Delete, UserFilled, Lock, Unlock, Check, Close, CircleCheck
} from '@element-plus/icons-vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'

const { t } = useI18n()  // FIXED: 国际化
const page = ref(1)
const pageSize = ref(10)
const paginatedUsers = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return users.value.slice(start, end)
})

const roleLabel = (r: string) => {
  const code = String(r || '').toLowerCase()
  const builtIn = ({ viewer: t('user.roleViewer'), operator: t('user.roleOperator'), admin: t('user.roleAdmin'), owner: t('user.roleOwner') } as Record<string, string>)  // FIXED: 硬编码中文→t()
  const custom = roles.value.find((item: UserRoleRow) => String(item?.code || '').toLowerCase() === code)
  return custom?.name || builtIn[code] || r
}

const getRoleType = (role: string) => {
  const typeMap: Record<string, unknown> = {
    'viewer': 'info',
    'operator': 'warning',
    'admin': 'primary',
    'owner': 'danger'
  }
  return typeMap[role] || 'info'
}

const router = useRouter()
type UserRow = {
  id?: string
  username?: string
  full_name?: string
  is_superuser?: boolean
  is_active?: boolean
  is_locked?: boolean
  tenant_id?: string
  role?: string
}

type UserRoleRow = {
  code?: string
  name?: string
}

const users = ref<UserRow[]>([])
const roles = ref<UserRoleRow[]>([])
const roleOptions = computed(() => {
  const builtIn = [
    { code: 'viewer', name: '查看者' },
    { code: 'operator', name: '操作员' },
    { code: 'admin', name: '管理员' },
    { code: 'owner', name: '所有者' }
  ]
  const merged = new Map<string, { code: string; name: string }>()
  for (const item of builtIn) merged.set(item.code, item)
  for (const item of roles.value || []) {
    const code = String(item?.code || '').trim()
    if (!code) continue
    merged.set(code, { code, name: String(item?.name || code) })
  }
  return Array.from(merged.values())
})

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref<string>('')
const currentUserId = ref('')
const currentUsername = ref('')
const formRef = ref<FormInstance>()
const form = ref({
  username: '',
  password: '',
  full_name: '',
  is_superuser: false,
  is_active: true,
  tenant_id: 'default',
  role: 'viewer'
})
const userFormRules: FormRules = {
  username: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('user.usernameRequired')))
        if (text.length < 3 || text.length > 32) return callback(new Error(t('user.usernameLength')))
        if (!/^[a-zA-Z0-9_\-.]+$/.test(text)) return callback(new Error(t('user.usernameFormat')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  password: [
    {
      validator: (_rule, value, callback) => {
        if (editingId.value) return callback()
        const text = String(value || '')
        if (!text.trim()) return callback(new Error(t('user.passwordRequired')))
        if (text.length < 6) return callback(new Error(t('user.passwordMinLength')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  full_name: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (text.length > 64) return callback(new Error(t('user.nameMaxLength')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  tenant_id: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('user.tenantRequired')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  role: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('user.roleRequired')))
        callback()
      },
      trigger: 'change'
    }
  ]
}

const fetchUsers = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/users')
    users.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    users.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const fetchMe = async () => {
  try {
    const res = await api.get('/api/v1/users/me')
    currentUserId.value = String(res.data?.id || '')
    currentUsername.value = String(res.data?.username || '')
  } catch (e: unknown) {
    currentUserId.value = ''
    currentUsername.value = ''
    console.warn('获取当前用户信息失败', e)
  }
}

const fetchRoles = async () => {
  try {
    const res = await api.get('/api/v1/roles')
    roles.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    roles.value = []
    console.warn('加载角色列表失败', e)
  }
}

const openEdit = (row: UserRow) => {
  editingId.value = String(row?.id || '')
  form.value = {
    username: row.username || '',
    password: '',
    full_name: row.full_name || '',
    is_superuser: !!row.is_superuser,
    is_active: row.is_active !== false,
    tenant_id: row.tenant_id || 'default',
    role: row.role || 'viewer'
  }
  dialogVisible.value = true
}

const openCreateUser = () => {
  resetForm()
  dialogVisible.value = true
}

const openRoleManager = () => {
  router.push('/roles')
}

const resetForm = () => {
  editingId.value = ''
  form.value = { username: '', password: '', full_name: '', is_superuser: false, is_active: true, tenant_id: 'default', role: 'viewer' }
  formRef.value?.clearValidate?.()
}

const canDeleteUser = (row: UserRow) => {
  const id = String(row?.id || '')
  const username = String(row?.username || '')
  if (id && currentUserId.value && id === currentUserId.value) return false
  if (username && currentUsername.value && username === currentUsername.value) return false
  if (row?.is_superuser) {
    const superCount = users.value.filter((item: UserRow) => !!item?.is_superuser).length
    if (superCount <= 1) return false
  }
  return true
}

const saveUser = async () => {
  const validated = await formRef.value?.validate().catch(() => false)
  if (!validated) return
  if (editingId.value && currentUserId.value && editingId.value === currentUserId.value && !form.value.is_active) {
    ElMessage.warning('Cannot deactivate the current logged-in account') // FIXED: 硬编码中文→英文
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/v1/users/${editingId.value}`, {
        full_name: String(form.value.full_name || '').trim(),
        email: null,
        is_active: form.value.is_active,
        is_superuser: form.value.is_superuser,
        tenant_id: String(form.value.tenant_id || '').trim(),
        role: String(form.value.role || '').trim()
      })
      ElMessage.success('User updated') // FIXED: 硬编码中文→英文
    } else {
      await api.post('/api/v1/users', {
        ...form.value,
        username: String(form.value.username || '').trim(),
        password: String(form.value.password || ''),
        full_name: String(form.value.full_name || '').trim(),
        tenant_id: String(form.value.tenant_id || '').trim(),
        role: String(form.value.role || '').trim()
      })
      ElMessage.success('User created successfully') // FIXED: 硬编码中文→英文
    }
    dialogVisible.value = false
    resetForm()
    await fetchUsers()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    saving.value = false
  }
}

const removeUser = async (row: UserRow) => {
  const id = String(row?.id || '')
  if (!id) return
  if (!canDeleteUser(row)) {
    ElMessage.warning('Current user cannot be deleted') // FIXED: 硬编码中文→英文
    return
  }
  try {
    await ElMessageBox.confirm(`Delete user "${row.username}"?`, 'Confirm', { type: 'warning' }) // FIXED: 硬编码中文→英文
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/users/${id}`)
    ElMessage.success('Deleted successfully') // FIXED: 硬编码中文→英文
    await fetchUsers()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const unlocking = ref('')

const unlockUser = async (row: UserRow) => {
  const id = String(row?.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm(`Unlock user "${row.username}"?`, 'Unlock user', { type: 'info' }) // FIXED: 硬编码中文→英文
  } catch { return }
  unlocking.value = id
  try {
    await api.post(`/api/v1/users/${id}/unlock`)
    ElMessage.success(`User "${row.username}" unlocked`) // FIXED: 硬编码中文→英文
    await fetchUsers()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    unlocking.value = ''
  }
}

onMounted(() => {
  fetchMe()
  fetchUsers()
  fetchRoles()
})
</script>

<style scoped>
.users-card {
  border-radius: 4px;
}

.users-table {
  border-radius: 4px;
  overflow: hidden;
}

.username-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar-wrapper {
  width: 30px;
  height: 30px;
  border-radius: 4px;
  background: var(--el-color-primary-light-8);
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-text {
  color: var(--el-color-primary);
  font-weight: 600;
  font-size: 13px;
}

.username-text {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tenant-tag {
  font-family: 'Consolas', 'Monaco', monospace;
  border-radius: 3px;
}

.role-tag {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  font-weight: 500;
}
.role-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
}
.role-tag :deep(.el-tag__content) {
  display: inline-flex;
  align-items: center;
  line-height: 1.2;
}

.status-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.status-dot.active {
  background: var(--el-color-success);
}
.status-dot.inactive {
  background: var(--el-color-warning);
}

.action-buttons {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.user-form {
  padding: 2px 0;
}

.input-wrapper,
.select-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 12px;
  z-index: 10;
  color: var(--el-text-color-secondary);
  font-size: 18px;
}

.form-input :deep(.el-input__wrapper),
.form-select :deep(.el-input__wrapper) {
  padding-left: 40px;
  border-radius: 3px;
}

.switch-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

</style>
