<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('user.title')" :description="t('user.description')">
          <template #actions>
            <el-button type="primary" @click="openCreateUser">
              <el-icon class="mr-1"><Plus /></el-icon>
              {{ t('user.addUser') }}
            </el-button>
            <el-button @click="openRoleManager">
              <el-icon class="mr-1"><Medal /></el-icon>
              {{ t('user.roleManagement') }}
            </el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard class="users-card">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-bold text-slate-700 flex items-center gap-2">
            <el-icon class="text-emerald-500"><User /></el-icon>
            {{ t('user.userList') }}
          </div>
          <div class="text-xs text-slate-500 flex items-center gap-2">
            <el-icon><Document /></el-icon>
            {{ t('user.totalCount', { count: users.length }) }}
          </div>
        </div>
      </template>
      <TableSkeleton v-if="loading && users.length === 0" :rows="5" />
      <el-table v-else :data="paginatedUsers" style="width: 100%" v-loading="loading" :empty-text="t('user.emptyText')" class="users-table" fit>
        <template #empty>
          <EmptyStateWithAction :description="t('user.emptyHint')">
            <template #action>
              <el-button type="primary" @click="openCreateUser">
                <el-icon class="mr-1"><Plus /></el-icon>
                {{ t('user.addUser') }}
              </el-button>
            </template>
          </EmptyStateWithAction>
        </template>
        <el-table-column prop="username" :label="t('common.username')">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><User /></el-icon>
              <span>{{ t('user.colUsername') }}</span>
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
        <el-table-column prop="full_name" :label="t('user.colFullName')" min-width="140">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><UserFilled /></el-icon>
              <span>{{ t('user.colFullName') }}</span>
            </div>
          </template>
          <template #default="scope">
            <div class="name-cell">
              <el-icon v-if="scope.row.full_name" class="text-emerald-400"><CircleCheck /></el-icon>
              <span>{{ scope.row.full_name || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="tenant_id" :label="t('user.colTenant')" width="160">
          <template #header>
            <div class="flex items-center gap-1">
              <el-icon class="text-slate-400"><OfficeBuilding /></el-icon>
              <span>{{ t('user.colTenant') }}</span>
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
              <span>{{ t('user.colRole') }}</span>
            </div>
          </template>
          <template #default="scope">
            <div class="role-cell">
              <el-tag :type="scope.row.is_superuser ? 'danger' : getRoleType(scope.row.role)" size="small" effect="dark" class="role-tag">
                <el-icon class="mr-1" v-if="scope.row.is_superuser"><Star /></el-icon>
                {{ scope.row.is_superuser ? t('common.superAdmin') : roleLabel(scope.row.role) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.status')">
          <template #header>
            <div class="flex items-center justify-center gap-1">
              <el-icon class="text-slate-400"><Switch /></el-icon>
              <span>{{ t('user.colStatus') }}</span>
            </div>
          </template>
          <template #default="scope">
            <div class="status-cell">
              <span class="status-dot" :class="scope.row.is_active ? 'active' : 'inactive'"></span>
              <el-tag :type="scope.row.is_active ? 'success' : 'warning'" size="small" effect="dark">
                {{ scope.row.is_active ? t('user.statusActive') : t('user.statusInactive') }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action')">
          <template #header>
            <div class="flex items-center justify-center gap-1">
              <el-icon class="text-slate-400"><Tools /></el-icon>
              <span>{{ t('common.action') }}</span>
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
          :prev-text="t('common.prevPage')"
          :next-text="t('common.nextPage')"
          size="small"
        />
      </div>
    </TableCard>

    <AppDialog
      v-model="dialogVisible"
      :title="editingId ? t('user.editUser') : t('user.createUser')"
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
        <el-form-item v-if="!editingId" :label="t('user.passwordLabel')" prop="password">
          <div class="input-wrapper">
            <el-icon class="input-icon"><Lock /></el-icon>
            <el-input v-model="form.password" type="password" :placeholder="t('user.initialPasswordPlaceholder')" show-password class="form-input" />
          </div>
        </el-form-item>
        <el-form-item :label="t('user.fullNameLabel')" prop="full_name">
          <div class="input-wrapper">
            <el-icon class="input-icon"><UserFilled /></el-icon>
            <el-input v-model="form.full_name" :placeholder="t('user.namePlaceholder')" class="form-input" />
          </div>
        </el-form-item>
        <!-- FIX H-2: 仅当当前用户为已验证超管时才渲染超管开关，防止 admin 越权授予超管 -->
        <el-form-item v-if="canGrantSuperuser" :label="t('user.superAdminLabel')">
          <div class="switch-wrapper">
            <el-switch v-model="form.is_superuser" class="superuser-switch" />
            <span class="switch-hint text-sm text-slate-500">{{ t('user.superAdminHint') }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="t('user.tenantLabel')" prop="tenant_id">
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
            <span class="switch-hint text-sm text-slate-500">{{ t('user.statusHint') }}</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          <el-icon class="mr-1"><Close /></el-icon>
          {{ t('common.cancel') }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">
          <el-icon class="mr-1"><Check /></el-icon>
          {{ t('common.ok') }}
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
import { logger } from '@/utils/logger'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  Plus, User, Document, OfficeBuilding, Medal, Star, Switch, Tools, Edit, Delete, UserFilled, Lock, Unlock, Check, Close, CircleCheck
} from '@element-plus/icons-vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import { getFriendlyError } from '../utils/errorMessage'
import { getVerifiedRoleInfo, type RoleInfo } from '../utils/auth' // FIX H-2: 后端验证角色控制超管授予
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
  const typeMap: Record<string, 'info' | 'warning' | 'primary' | 'danger'> = {
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
    { code: 'viewer', name: t('user.roleViewer') },
    { code: 'operator', name: t('user.roleOperator') },
    { code: 'admin', name: t('user.roleAdmin') },
    { code: 'owner', name: t('user.roleOwner') }
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
// FIX H-2: 当前用户已验证角色信息，用于控制超管授予开关可见性
const currentRoleInfo = ref<RoleInfo | null>(null)
const canGrantSuperuser = computed(() => !!currentRoleInfo.value?.isSuperuser)
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
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
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
    logger.warn(t('user.fetchMeFailed'), e)
  }
}

const fetchRoles = async () => {
  try {
    const res = await api.get('/api/v1/roles')
    roles.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    roles.value = []
    logger.warn(t('user.fetchRolesFailed'), e)
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
    ElMessage.warning(t('user.cannotDeactivateSelf'))
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
      ElMessage.success(t('user.userUpdated'))
    } else {
      await api.post('/api/v1/users', {
        ...form.value,
        username: String(form.value.username || '').trim(),
        password: String(form.value.password || ''),
        full_name: String(form.value.full_name || '').trim(),
        tenant_id: String(form.value.tenant_id || '').trim(),
        role: String(form.value.role || '').trim()
      })
      ElMessage.success(t('user.userCreated'))
    }
    dialogVisible.value = false
    resetForm()
    await fetchUsers()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    saving.value = false
  }
}

const removeUser = async (row: UserRow) => {
  const id = String(row?.id || '')
  if (!id) return
  if (!canDeleteUser(row)) {
    ElMessage.warning(t('user.cannotDeleteSelf'))
    return
  }
  try {
    await ElMessageBox.confirm(t('user.deleteUserConfirm', { username: row.username }), t('user.confirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/users/${id}`)
    ElMessage.success(t('user.deletedSuccess'))
    await fetchUsers()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  }
}

const unlocking = ref('')

const unlockUser = async (row: UserRow) => {
  const id = String(row?.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm(t('user.unlockUserConfirm', { username: row.username }), t('user.unlockUserTitle'), { type: 'info' })
  } catch { return }
  unlocking.value = id
  try {
    await api.post(`/api/v1/users/${id}/unlock`)
    ElMessage.success(t('user.userUnlocked', { username: row.username }))
    await fetchUsers()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    unlocking.value = ''
  }
}

// FIX H-2: onMounted 改为 async，获取后端验证的当前用户角色以控制超管授予开关
onMounted(async () => {
  currentRoleInfo.value = await getVerifiedRoleInfo()
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
