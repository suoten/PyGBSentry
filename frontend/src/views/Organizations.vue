<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('org.title')" :description="t('orgPage.description')">
          <template #actions>
            <el-button type="primary" @click="openCreate(null)" class="add-btn">
              <el-icon class="mr-1"><Plus /></el-icon>
              {{ t('orgPage.addRoot') }}
            </el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard class="org-card">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-bold text-slate-700 flex items-center gap-2">
            <el-icon class="text-emerald-500"><OfficeBuilding /></el-icon>
            {{ t('orgPage.orgTree') }}
          </div>
          <div class="text-xs text-slate-400 flex items-center gap-1">
            <el-icon><Rank /></el-icon>
            {{ t('orgPage.dragHint') }}
          </div>
        </div>
      </template>
      <el-tree
        :data="treeData"
        :props="{ label: 'name', children: 'children' }"
        node-key="id"
        default-expand-all
        class="org-tree"
        :expand-on-click-node="false"
        draggable
        :allow-drop="allowDrop"
        @node-drop="handleNodeDrop"
      >
        <template #default="{ node, data }">
          <span class="tree-node">
            <span class="node-content">
              <el-icon class="text-emerald-500"><Folder /></el-icon>
              <span class="node-label">{{ node.label }}</span>
            </span>
            <span class="tree-actions">
              <el-button link type="primary" size="small" @click.stop="openCreate(data.id)" class="action-link">
                <el-icon class="mr-1"><Plus /></el-icon>
                {{ t('orgPage.addChild') }}
              </el-button>
              <el-button link type="primary" size="small" @click.stop="openEdit(data)" class="action-link">
                <el-icon class="mr-1"><Edit /></el-icon>
                {{ t('common.edit') }}
              </el-button>
              <el-button link type="danger" size="small" @click.stop="doDelete(data)" class="action-link">
                <el-icon class="mr-1"><Delete /></el-icon>
                {{ t('common.delete') }}
              </el-button>
            </span>
          </span>
        </template>
      </el-tree>
      <div v-if="!treeData.length && !loading" class="empty-state py-8 text-center">
        <el-icon class="empty-icon"><FolderOpened /></el-icon>
        <div class="empty-text">{{ t('orgPage.emptyHint') }}</div>
      </div>
      <div v-if="loading" class="loading-state py-8 text-center">
        <el-icon class="is-loading loading-icon"><Loading /></el-icon>
        <span class="loading-text">{{ t('common.loading') }}</span>
      </div>
    </TableCard>

    <AppDialog
      v-model="dialogVisible"
      :title="editId ? t('orgPage.editOrg') : t('orgPage.createOrg')"
      size="small"
      :icon="OfficeBuilding"
      icon-color="success"
      @closed="resetForm"
    >
      <el-form :model="form" label-width="100px" class="org-form">
        <el-form-item v-if="parentName" :label="t('orgPage.parentOrg')">
          <div class="input-wrapper">
            <el-icon class="input-icon"><Folder /></el-icon>
            <el-input :model-value="parentName" disabled class="form-input" />
          </div>
        </el-form-item>
        <el-form-item :label="t('common.name')">
          <div class="input-wrapper">
            <el-icon class="input-icon"><EditPen /></el-icon>
            <el-input v-model="form.name" :placeholder="t('orgPage.enterOrgName')" class="form-input" />
          </div>
        </el-form-item>
        <el-form-item v-if="!editId" :label="t('orgPage.sort')">
          <div class="input-wrapper">
            <el-icon class="input-icon"><Sort /></el-icon>
            <el-input-number v-model="form.sort_order" :min="0" class="form-input-number" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false" class="cancel-btn">
          <el-icon class="mr-1"><Close /></el-icon>
          {{ t('common.cancel') }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="submit" class="confirm-btn">
          <el-icon class="mr-1"><Check /></el-icon>
          {{ editId ? t('common.save') : t('common.confirm') }}
        </el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Loading, Plus, OfficeBuilding, Rank, Folder, Edit, Delete, FolderOpened, EditPen, Sort, Close, Check
} from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import type { OrgNode } from '../api/organizations'
import {
  getOrganizationTree,
  createOrganization,
  updateOrganization,
  deleteOrganization
} from '../api/organizations'

const treeData = ref<OrgNode[]>([])
const { t } = useI18n()  // FIXED: 国际化
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editId = ref<string | null>(null)
const parentId = ref<string | null>(null)
const parentName = ref('')
const form = ref({ name: '', sort_order: 0 })

const loadTree = async () => {
  loading.value = true
  try {
    treeData.value = await getOrganizationTree()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

const openCreate = (pid: string | null) => {
  editId.value = null
  parentId.value = pid
  parentName.value = pid ? findNodeName(treeData.value, pid) : ''
  form.value = { name: '', sort_order: 0 }
  dialogVisible.value = true
}

function findNodeName(nodes: OrgNode[], id: string): string {
  for (const n of nodes) {
    if (n.id === id) return n.name
    const found = findNodeName(n.children || [], id)
    if (found) return found
  }
  return ''
}

const openEdit = (data: OrgNode) => {
  editId.value = data.id
  parentId.value = null
  parentName.value = ''
  form.value = { name: data.name, sort_order: data.sort_order ?? 0 }
  dialogVisible.value = true
}

const resetForm = () => {
  editId.value = null
  parentId.value = null
  form.value = { name: '', sort_order: 0 }
}

const submit = async () => {
  const name = (form.value.name || '').trim()
  if (!name) {
    ElMessage.warning(t('orgPage.enterOrgName'))
    return
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateOrganization(editId.value, { name })
      ElMessage.success(t('common.saveSuccess')) // FIXED: 国际化
    } else {
      await createOrganization({ name, parent_id: parentId.value || undefined, sort_order: form.value.sort_order })
      ElMessage.success(t('common.saveSuccess')) // FIXED: 国际化
    }
    dialogVisible.value = false
    await loadTree()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(
      friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : (friendly.message || (editId.value ? t('common.saveFailed') : t('orgPage.createFailed')))
    )
  } finally {
    saving.value = false
  }
}

const doDelete = async (data: OrgNode) => {
  try {
    await ElMessageBox.confirm(t('orgPage.confirmDelete', { name: data.name }), t('orgPage.deleteConfirmTitle'), {
      type: 'warning',
      confirmButtonText: t('orgPage.confirmDeleteBtn'),
      cancelButtonText: t('common.cancel'),
      confirmButtonClass: 'confirm-delete-btn'
    })
  } catch {
    return
  }
  try {
    await deleteOrganization(data.id)
    ElMessage.success(t('common.deleteSuccess'))
    await loadTree()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const allowDrop = (_draggingNode: Record<string, unknown>, _dropNode: Record<string, unknown>, type: string) => {
  return type !== 'inner'
}

const handleNodeDrop = async (
  draggingNode: Record<string, unknown>,
  dropNode: Record<string, unknown>,
  dropType: string,
) => {
  if (dropType === 'inner') return
  const siblings =
    dropType === 'before' || dropType === 'after'
      ? dropNode.parent?.data?.children || dropNode.parent?.data || []
      : []
  if (!Array.isArray(siblings)) return
  const updates: Promise<void>[] = []
  siblings.forEach((child: OrgNode, index: number) => {
    if (child.sort_order !== index) {
      updates.push(updateOrganization(child.id, { sort_order: index }))
    }
  })
  if (updates.length === 0) return
  try {
    await Promise.all(updates)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    await loadTree()
  }
}

onMounted(() => {
  loadTree()
})
</script>

<style scoped>
.add-btn {
  transition: all var(--transition-time-02);
}
.add-btn:hover {
  transform: none;
}

.org-card {
  border-radius: 8px;
}

.org-tree {
  min-height: 200px;
  padding: 8px;
}
.org-tree :deep(.el-tree-node__content) {
  padding: 8px 10px;
  border-radius: 6px;
  transition: all var(--transition-time-02);
  margin-bottom: 4px;
}
.org-tree :deep(.el-tree-node__content:hover) {
  background: var(--el-fill-color-extra-light);
}

.tree-node {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
  width: 100%;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.node-label {
  font-size: 14px;
}

.tree-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition-time-02);
}
.org-tree :deep(.el-tree-node__content:hover) .tree-actions {
  opacity: 1;
}

.action-link {
  padding: 4px 8px;
  border-radius: 6px;
  transition: all var(--transition-time-02);
}
.action-link:hover {
  background: var(--el-fill-color-light);
}

.empty-state,
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.empty-icon,
.loading-icon {
  font-size: 48px;
  color: var(--el-text-color-placeholder);
}

.empty-text,
.loading-text {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.org-form {
  padding: 4px 0;
}

.input-wrapper {
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
.form-input-number :deep(.el-input__wrapper) {
  padding-left: 40px;
  border-radius: 8px;
}

.cancel-btn {
  transition: all var(--transition-time-02);
}
.cancel-btn:hover {
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color);
}

.confirm-btn {
  transition: all var(--transition-time-02);
}
.confirm-btn:hover {
  transform: none;
}

.confirm-delete-btn {
  background: var(--el-color-danger);
  border-color: var(--el-color-danger);
}
</style>
