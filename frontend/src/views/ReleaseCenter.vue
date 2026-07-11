<template>
  <div class="app-page space-y-4">
    <el-alert
      v-if="!canManageConfig"
      :title="t('releaseCenter.previewOnlyAlert')"
      type="warning"
      :closable="false"
      show-icon
    />
    <PageContainer>
      <template #header>
        <PageHeader :title="t('releaseCenter.title')" :description="t('releaseCenter.draftDescription', { id: publishForm.draftId || '-' })" />
      </template>

      <el-tabs v-model="activeTab" type="border-card" class="release-tabs">
        <el-tab-pane :label="t('releaseCenter.tabPublish')" name="publish">
          <TableCard v-loading="loadingDraft || loadingDiff || publishing || rollingBack">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('releaseCenter.publishHeader') }}</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('releaseCenter.previewDiffHint') }}</div>
              </div>
            </template>
            <QueryFormSection label-width="160px" form-class="max-w-3xl">
              <el-form-item v-for="field in publishFields" :key="field.key" :label="t(field.label)">
                <el-input
                  :model-value="publishForm[field.key]"
                  :placeholder="field.placeholder ? t(field.placeholder) : undefined"
                  :disabled="field.key === 'publishNote' ? !canManageConfig : false"
                  style="max-width: 420px"
                  @update:model-value="(v: string) => setPublishField(field.key, v)"
                />
                <el-button v-if="field.key === 'draftId'" class="ml-2" :loading="loadingDraft" @click="loadCurrentDraft">{{ t('releaseCenter.loadDraft') }}</el-button>
              </el-form-item>
              <el-form-item>
                <ActionButtons
                  :primary-text="t('releaseCenter.previewDiff')"
                  :secondary-text="t('releaseCenter.confirmPublish')"
                  secondary-type="success"
                  :primary-loading="loadingDiff"
                  :secondary-loading="publishing"
                  :secondary-disabled="!canManageConfig"
                  @primary="loadDiff"
                  @secondary="publishNow"
                />
              </el-form-item>
              <el-alert type="info" :closable="false" show-icon class="mt-2">
                <template #title>{{ t('releaseCenter.tip') }}</template>
                <span v-html="sanitizeHtml(t('releaseCenter.pluginConfigRestartHint'))"></span>
              </el-alert>
            </QueryFormSection>
          </TableCard>
        </el-tab-pane>

        <el-tab-pane :label="t('releaseCenter.tabDiff')" name="diff">
          <TableCard v-loading="loadingDiff">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('releaseCenter.diffHeader') }}</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('releaseCenter.versionLabel', { version: fromRevision }) }}</div>
              </div>
            </template>
            <el-table :data="paginatedDiffRows" stripe style="width: 100%" :empty-text="t('releaseCenter.noDiffData')">
              <el-table-column prop="module" :label="t('releaseCenter.colModule')" min-width="200" />
              <el-table-column prop="path" :label="t('releaseCenter.colField')" min-width="160" />
              <el-table-column :label="t('releaseCenter.colBefore')" min-width="220">
                <template #default="{ row }">{{ toText(row.before) }}</template>
              </el-table-column>
              <el-table-column :label="t('releaseCenter.colAfter')" min-width="220">
                <template #default="{ row }">{{ toText(row.after) }}</template>
              </el-table-column>
              <el-table-column prop="risk_level" :label="t('releaseCenter.colRiskLevel')" width="120" />
              <template #empty>
                <el-empty :description="EMPTY_TEXT" />
              </template>
            </el-table>
            <div class="flex justify-end mt-4 pagination-wrapper" v-if="diffRows.length > 0">
              <el-pagination
                v-model:current-page="page"
                v-model:page-size="pageSize"
                :total="diffRows.length"
                layout="total, sizes, prev, pager, next, jumper"
                :page-sizes="[10, 20, 50, 100]"
                :prev-text="t('releaseCenter.prevPage')"
                :next-text="t('releaseCenter.nextPage')"
                size="small"
              />
            </div>
          </TableCard>
        </el-tab-pane>

        <el-tab-pane :label="t('releaseCenter.tabRollback')" name="rollback">
          <TableCard v-loading="rollingBack">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('releaseCenter.rollbackHeader') }}</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('releaseCenter.targetVersionLabel', { version: rollbackForm.targetRevision }) }}</div>
              </div>
            </template>
            <QueryFormSection label-width="160px" form-class="max-w-3xl">
              <el-form-item v-for="field in rollbackFields" :key="field.key" :label="t(field.label)">
                <el-input-number
                  v-if="field.component === 'number'"
                  :model-value="(rollbackForm[field.key] as number)"
                  :min="1"
                  :disabled="!canManageConfig"
                  @update:model-value="(v: number | undefined) => setRollbackField(field.key, v as number)"
                />
                <el-input
                  v-else
                  :model-value="rollbackForm[field.key]"
                  :placeholder="field.placeholder ? t(field.placeholder) : undefined"
                  :disabled="!canManageConfig"
                  @update:model-value="(v: string) => setRollbackField(field.key, v)"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="warning" :loading="rollingBack" :disabled="!canManageConfig" @click="rollbackNow">{{ t('releaseCenter.executeRollback') }}</el-button>
              </el-form-item>
            </QueryFormSection>
          </TableCard>
        </el-tab-pane>
      </el-tabs>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getCurrentDraft } from '../api/configCenter'
import { getDraftDiff, publishDraft, rollbackRevision, type DiffItem } from '../api/releaseCenter'
import { getCachedRoleInfo, getVerifiedRoleInfo, EMPTY_ROLE_INFO, type RoleInfo } from '../utils/auth' // FIX C-3: 改用后端验证角色
import { EMPTY_TEXT, buildErrorMessage, buildSuccessMessage } from '../utils/ui'
import QueryFormSection from '../components/QueryFormSection.vue'
import ActionButtons from '../components/ActionButtons.vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import {
  releasePublishFields,
  releaseRollbackFields,
  type ReleasePublishFieldKey,
  type ReleaseRollbackFieldKey
} from '../configs/center-fields'
import { validateFieldValue } from '../utils/field-validation'
import { sanitizeHtml } from '../utils/sanitize'

const { t } = useI18n()

const activeTab = ref('publish')
const fromRevision = ref(0)
const diffRows = ref<DiffItem[]>([])
const page = ref(1)
const pageSize = ref(10)
const paginatedDiffRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return diffRows.value.slice(start, end)
})
watch(diffRows, () => { page.value = 1 })

const publishForm = ref({
  draftId: '',
  publishNote: ''
})
const rollbackForm = ref({
  targetRevision: 1,
  reason: ''
})
const publishFields = releasePublishFields
const rollbackFields = releaseRollbackFields

const loadingDraft = ref(false)
const loadingDiff = ref(false)
const publishing = ref(false)
const rollingBack = ref(false)
// FIX C-3: 使用后端验证的缓存角色信息，不再客户端解码 JWT
const roleInfo = getCachedRoleInfo() ?? EMPTY_ROLE_INFO
const canManageConfig = roleInfo.canManageConfig

const toText = (value: unknown) => {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const setPublishField = (key: ReleasePublishFieldKey, value: string) => {
  publishForm.value[key] = value
}

const setRollbackField = (key: ReleaseRollbackFieldKey, value: string | number) => {
  ;(rollbackForm.value as Record<string, unknown>)[key] = value
}

const loadCurrentDraft = async () => {
  loadingDraft.value = true
  try {
    const draft = await getCurrentDraft()
    publishForm.value.draftId = draft.draft_id
    ElMessage.success(buildSuccessMessage(t('releaseCenter.loadAction'), t('releaseCenter.draftLoaded')))
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage(t('releaseCenter.loadAction'), error, t('releaseCenter.draftLoadError')))
  } finally {
    loadingDraft.value = false
  }
}

const loadDiff = async () => {
  const draftField = releasePublishFields.find(item => item.key === 'draftId')
  const draftMessage = draftField ? validateFieldValue(draftField, publishForm.value.draftId) : null
  if (draftMessage) {
    ElMessage.warning(t('releaseCenter.validateFailed', { msg: draftMessage }))
    return
  }
  loadingDiff.value = true
  try {
    const diff = await getDraftDiff(publishForm.value.draftId)
    fromRevision.value = diff.from_revision
    diffRows.value = diff.changes || []
    ElMessage.success(buildSuccessMessage(t('releaseCenter.loadAction'), t('releaseCenter.diffCount', { count: diffRows.value.length })))
    activeTab.value = 'diff'
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage(t('releaseCenter.loadAction'), error, t('releaseCenter.diffLoadError')))
  } finally {
    loadingDiff.value = false
  }
}

const publishNow = async () => {
  if (!canManageConfig) {
    ElMessage.warning(t('releaseCenter.noPublishPermission'))
    return
  }
  const draftField = releasePublishFields.find(item => item.key === 'draftId')
  const draftMessage = draftField ? validateFieldValue(draftField, publishForm.value.draftId) : null
  if (draftMessage) {
    ElMessage.warning(t('releaseCenter.validateFailed', { msg: draftMessage }))
    return
  }
  try {
    await ElMessageBox.confirm(t('releaseCenter.publishConfirm', { id: publishForm.value.draftId }), t('releaseCenter.publishConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  publishing.value = true
  try {
    const result = await publishDraft(publishForm.value.draftId)
    ElMessage.success(buildSuccessMessage(t('releaseCenter.publishAction'), t('releaseCenter.revisionLabel', { revision: result.revision })))
    rollbackForm.value.targetRevision = result.revision
    await loadDiff()
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage(t('releaseCenter.publishAction'), error))
  } finally {
    publishing.value = false
  }
}

const rollbackNow = async () => {
  if (!canManageConfig) {
    ElMessage.warning(t('releaseCenter.noRollbackPermission'))
    return
  }
  const revisionField = releaseRollbackFields.find(item => item.key === 'targetRevision')
  const revisionMessage = revisionField ? validateFieldValue(revisionField, rollbackForm.value.targetRevision) : null
  if (revisionMessage) {
    ElMessage.warning(t('releaseCenter.validateFailed', { msg: revisionMessage }))
    return
  }
  try {
    await ElMessageBox.confirm(t('releaseCenter.rollbackConfirm', { revision: rollbackForm.value.targetRevision }), t('releaseCenter.rollbackConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  rollingBack.value = true
  try {
    await rollbackRevision(rollbackForm.value.targetRevision as any)
    ElMessage.success(buildSuccessMessage(t('releaseCenter.rollbackAction'), t('releaseCenter.revisionLabel', { revision: rollbackForm.value.targetRevision })))
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage(t('releaseCenter.rollbackAction'), error))
  } finally {
    rollingBack.value = false
  }
}

onMounted(async () => {
  void getVerifiedRoleInfo() // FIX C-3: 刷新后端验证角色缓存
  await loadCurrentDraft()
})
</script>

<style scoped>
.release-tabs {
  margin-top: 16px;
}
.release-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px 0;
}
.release-tabs :deep(.el-tabs__content) {
  padding-top: 0;
}
</style>
