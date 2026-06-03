<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="角色管理" description="管理系统角色与菜单权限">
          <template #actions>
            <el-button type="primary" @click="openCreateRole">
              <el-icon class="mr-1"><Plus /></el-icon>
              新增角色
            </el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard v-loading="loading">
        <template #header>
          <div class="role-toolbar">
            <div class="role-toolbar-title font-bold text-slate-700 flex items-center gap-2">
              <el-icon class="text-emerald-500"><Medal /></el-icon>
              角色列表
            </div>
            <el-alert class="role-toolbar-alert" title="超级管理员由用户的“超级管理员”开关控制，不支持在角色管理中编辑。" type="info" :closable="false" show-icon />
          </div>
        </template>

        <el-table :data="paginatedRoles" size="small">
          <el-table-column prop="code" label="code" width="180" />
          <el-table-column prop="name" label="名称" />
          <el-table-column label="权限">
            <template #default="{ row }">
              <div class="role-permission-tags">
                <el-tag v-for="code in row.permission_codes || []" :key="code" size="small" effect="plain" type="success">
                  {{ code === '*' ? '全部权限' : (permissionNameMap[code] || code) }}
                </el-tag>
                <span v-if="!(row.permission_codes || []).length" class="text-slate-400">无</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="120" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_system ? 'info' : 'success'">{{ row.is_system ? '系统' : '自定义' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" align="center">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain :disabled="row.is_super_admin" @click="editRole(row)">编辑</el-button>
              <el-button size="small" type="danger" plain :disabled="row.is_system || row.is_super_admin" @click="deleteRole(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="flex justify-end mt-4 pagination-wrapper" v-if="roleRows.length > 0">
          <el-pagination
            v-model:current-page="rolesPage"
            v-model:page-size="rolesPageSize"
            :total="roleRows.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            prev-text="上一页"
            next-text="下一页"
            size="small"
          />
        </div>
      </TableCard>

      <AppDialog
        v-model="roleEditorVisible"
        :title="roleEditingId ? '编辑角色' : '新增角色'"
        size="large"
        :icon="Medal"
        icon-color="primary"
        @closed="resetRoleForm"
      >
        <div class="role-editor">
          <div class="role-editor-row">
            <el-input v-model="roleForm.code" :disabled="!!roleEditingId" placeholder="code（如 custom_role）" class="role-editor-input" />
            <el-input v-model="roleForm.name" placeholder="名称" class="role-editor-input" />
          </div>
          <el-tree
            ref="treeRef"
            :data="rolePermissionTree"
            show-checkbox
            node-key="code"
            :props="{ children: 'children', label: 'label' }"
            default-expand-all
            class="role-permission-tree"
          />
        </div>
        <template #footer>
          <el-button @click="roleEditorVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveRole">{{ roleEditingId ? '保存' : '创建' }}</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Medal, Plus } from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'
import { getRoleInfo, hasPermission } from '../utils/auth'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'

const router = useRouter()
type RoleRow = {
  id: string
  code: string
  name: string
  permission_codes?: unknown
  is_system?: boolean
  is_super_admin?: boolean
}

type PermissionNode = {
  code: string
  label: string
  children?: PermissionNode[]
}

const roles = ref<RoleRow[]>([])
const pluginMenus = ref<{ plugin_id: string; title: string; path: string }[]>([])
const loading = ref(false)
const saving = ref(false)
const rolesPage = ref(1)
const rolesPageSize = ref(10)
const roleEditorVisible = ref(false)
const roleEditingId = ref<string>('')
const roleEditingIsSystem = ref(false)
const roleForm = ref({ code: '', name: '', permission_codes: [] as string[] })
type PermissionTreeRef = {
  setCheckedKeys?: (keys: string[]) => void
  getCheckedKeys?: (leafOnly?: boolean) => unknown[]
}

const treeRef = ref<PermissionTreeRef | null>(null)

const visiblePluginMenus = computed(() => {
  const roleInfo = getRoleInfo()
  if (roleInfo.isSuperuser || roleInfo.permissions.includes('*')) return pluginMenus.value
  return pluginMenus.value.filter((p) => hasPermission(roleInfo.permissions, `plugin_${p.plugin_id}.view`))
})

const normalizePermissionCodes = (codes: unknown) => {
  if (!Array.isArray(codes)) return []
  const result: string[] = []
  const exists = new Set<string>()
  for (const item of codes) {
    const code = String(item || '').trim()
    if (!code || exists.has(code)) continue
    exists.add(code)
    result.push(code)
  }
  return result
}

const getDefaultPermissionCodes = (roleCode: string) => {
  const code = String(roleCode || '').trim().toLowerCase()
  if (code === 'viewer') return ['dashboard.view', 'monitor.view', 'channels.view']
  if (code === 'operator') return ['dashboard.view', 'monitor.view', 'channels.view', 'records.view', 'alarms.handle']
  if (code === 'admin') return ['dashboard.view', 'monitor.view', 'channels.view', 'records.view', 'alarms.handle', 'devices.manage', 'config.manage', 'audit.view', 'users.manage', 'roles.manage']
  if (code === 'owner') return ['*']
  return []
}

const roleRows = computed(() => {
  const superAdminRole = {
    id: 'super_admin',
    code: 'super_admin',
    name: '超级管理员',
    permission_codes: ['*'],
    is_system: true,
    is_super_admin: true
  }
  return [superAdminRole, ...roles.value]
})

const paginatedRoles = computed(() => {
  const start = (rolesPage.value - 1) * rolesPageSize.value
  const end = start + rolesPageSize.value
  return roleRows.value.slice(start, end)
})

const rolePermissionTree = computed(() => {
  const tree: PermissionNode[] = []
  const legacyMap: Record<string, string> = {
    Devices: 'devices.manage',
    Alarms: 'alarms.handle',
    ConfigCenter: 'config.manage',
    Users: 'users.manage',
    Roles: 'roles.manage',
    AuditCenter: 'audit.view',
    RecordSchedule: 'records.view',
    DeviceRecords: 'records.view',
    CloudRecords: 'records.view'
  }

  const getCode = (routeName: string) => legacyMap[routeName] || `${routeName.toLowerCase()}.view`
  const groupsDef = [
    { title: '概览', names: ['Dashboard', 'PluginCenter'] },
    { title: '业务', names: ['Monitor', 'TvWall', 'Devices', 'PushStreams', 'PullProxies', 'Channels', 'ChannelsLegacy', 'ChannelsRegion', 'ChannelsGroup', 'DeviceRecords', 'CloudRecords', 'RecordSchedule', 'LegacyGateway', 'CascadePlatforms'] },
    { title: '告警', names: ['Alarms', 'AlarmNotifications', 'AlarmLinkRules', 'WorkOrders'] },
    { title: '可视化', names: ['Map', 'VisualCommand', 'MobileCommand'] },
    { title: '运维', names: ['Health', 'SLA', 'Operations', 'AppLogs', 'Network', 'AssetManagement'] },
    { title: '系统', names: ['Users', 'Roles', 'ApiKeys', 'Organizations', 'MapProviders', 'ConfigCenter', 'ReleaseCenter', 'AuditCenter', 'Reports', 'AccountSecurity', 'Help'] }
  ]
  const routes = router.getRoutes()
  const usedNames = new Set<string>()

  for (const g of groupsDef) {
    const children: PermissionNode[] = []
    for (const name of g.names) {
      const r = routes.find(rt => rt.name === name)
      if (r && r.meta && r.meta.title && !r.meta.hiddenInMenu) {
        children.push({ code: getCode(name), label: String(r.meta.title || '') })
        usedNames.add(name)
      }
    }
    if (children.length > 0) {
      const uniqueChildren: PermissionNode[] = []
      const seenCodes = new Set<string>()
      for (const c of children) {
        if (seenCodes.has(c.code)) continue
        seenCodes.add(c.code)
        uniqueChildren.push(c)
      }
      tree.push({ code: `group_${g.title}`, label: g.title, children: uniqueChildren })
    }
  }

  const otherChildren: PermissionNode[] = []
  const skipNames = new Set(['Login', 'Register', 'NotFound', 'SetupWizard', 'PluginDetail', 'PluginRuntime', 'MobileReports', 'MobileTvWall', 'MobileVisualCommand', 'MobileFaceRecognition', 'MobilePlateRecognition', 'MobileBehaviorRecognition'])
  for (const r of routes) {
    const name = String(r.name || '')
    if (!name || usedNames.has(name) || skipNames.has(name)) continue
    if (r.meta?.hiddenInMenu || !r.meta?.title) continue
    otherChildren.push({ code: getCode(name), label: String(r.meta.title || '') })
  }
  if (otherChildren.length > 0) {
    const uniqueChildren: PermissionNode[] = []
    const seenCodes = new Set<string>()
    for (const c of otherChildren) {
      if (seenCodes.has(c.code)) continue
      seenCodes.add(c.code)
      uniqueChildren.push(c)
    }
    tree.push({ code: 'group_other', label: '其他功能', children: uniqueChildren })
  }

  if (visiblePluginMenus.value.length > 0) {
    const pluginChildren = visiblePluginMenus.value.map(p => ({ code: `plugin_${p.plugin_id}.view`, label: String(p.title || '') }))
    tree.push({ code: 'group_plugins', label: '扩展插件', children: pluginChildren })
  }

  return tree
})

const permissionNameMap = computed(() => {
  const map: Record<string, string> = {}
  const walk = (nodes: PermissionNode[]) => {
    for (const node of nodes) {
      if (node.children) walk(node.children)
      else map[node.code] = node.label
    }
  }
  walk(rolePermissionTree.value)
  return map
})

const fetchRoles = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/roles')
    const rows = Array.isArray(res.data) ? res.data : []
    roles.value = rows.map((item: RoleRow) => {
      const permissionCodes = normalizePermissionCodes(item?.permission_codes)
      return {
        ...item,
        permission_codes: permissionCodes
      }
    })
  } catch (e: unknown) {
    roles.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const loadPluginMenus = async () => {
  try {
    const res = await api.get('/api/v1/plugins/menus')
    pluginMenus.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    pluginMenus.value = []
    console.warn('加载插件菜单失败', e)
  }
}

const resetRoleForm = () => {
  roleEditingId.value = ''
  roleEditingIsSystem.value = false
  roleForm.value = { code: '', name: '', permission_codes: [] }
  treeRef.value?.setCheckedKeys?.([])
}

const openCreateRole = () => {
  resetRoleForm()
  roleEditorVisible.value = true
}

const editRole = (row: RoleRow) => {
  if (row?.is_super_admin) return
  roleEditingId.value = String(row?.id || '')
  roleEditingIsSystem.value = !!row?.is_system
  roleForm.value = {
    code: String(row?.code || ''),
    name: String(row?.name || ''),
    permission_codes: normalizePermissionCodes(row?.permission_codes)
  }
  roleEditorVisible.value = true
  setTimeout(() => treeRef.value?.setCheckedKeys?.(roleForm.value.permission_codes), 0)
}

const saveRole = async () => {
  const code = String(roleForm.value.code || '').trim()
  const name = String(roleForm.value.name || '').trim()
  if (!code || !name) {
    ElMessage.warning('请填写 code 和名称')
    return
  }
  const checkedKeys = treeRef.value?.getCheckedKeys?.(true) || []
  const permission_codes = normalizePermissionCodes(checkedKeys)
  saving.value = true
  try {
    if (roleEditingId.value) {
      if (roleEditingIsSystem.value) {
        try {
          await ElMessageBox.confirm(
            '你正在修改系统角色权限，此操作会影响当前租户下所有使用该角色的用户。是否继续？',
            '修改系统角色',
            { type: 'warning', confirmButtonText: '继续保存', cancelButtonText: '取消' }
          )
        } catch {
          return
        }
      }
      await api.put(`/api/v1/roles/${roleEditingId.value}`, { code, name, description: '', permission_codes })
      ElMessage.success('角色已更新')
    } else {
      await api.post('/api/v1/roles', { code, name, description: '', permission_codes })
      ElMessage.success('角色已创建')
    }
    roleEditorVisible.value = false
    resetRoleForm()
    await fetchRoles()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    saving.value = false
  }
}

const deleteRole = async (row: RoleRow) => {
  if (row?.is_super_admin || row?.is_system) return
  try {
    await ElMessageBox.confirm(`确定删除角色「${row.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/roles/${row.id}`)
    ElMessage.success('已删除')
    await fetchRoles()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

onMounted(() => {
  fetchRoles()
  loadPluginMenus()
})
</script>

<style scoped>
.role-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.role-toolbar-title {
  flex: 0 0 auto;
  white-space: nowrap;
}

.role-toolbar-alert {
  flex: 1 1 auto;
  min-width: 320px;
}

@media (max-width: 900px) {
  .role-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
  .role-toolbar-alert {
    width: 100%;
    min-width: 0;
  }
}

.role-editor {
  margin-bottom: 14px;
  padding: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: #fafafa;
}

.role-editor-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.role-editor-input {
  width: 100%;
}

.role-permission-tree {
  margin-top: 10px;
  max-height: 360px;
  overflow-y: auto;
  padding: 8px 0;
  border-top: 1px solid var(--el-border-color-lighter);
}

.role-permission-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.pagination-wrapper {
  padding: 10px 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

@media (max-width: 760px) {
  .role-editor-row {
    grid-template-columns: 1fr;
  }
}
</style>
