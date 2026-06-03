<template>
  <div class="app-page space-y-4">
    <el-alert
      v-if="!canManageConfig"
      title="当前账号仅可预览差异，发布与回滚需 owner/admin 权限"
      type="warning"
      :closable="false"
      show-icon
    />
    <PageContainer>
      <template #header>
        <PageHeader title="发布中心" :description="`草稿 ${publishForm.draftId || '-'}`" />
      </template>

      <el-tabs v-model="activeTab" type="border-card" class="release-tabs">
        <el-tab-pane label="发布" name="publish">
          <TableCard v-loading="loadingDraft || loadingDiff || publishing || rollingBack">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">发布</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">预览差异后确认发布</div>
              </div>
            </template>
            <QueryFormSection label-width="160px" form-class="max-w-3xl">
              <el-form-item v-for="field in publishFields" :key="field.key" :label="field.label">
                <el-input
                  :model-value="publishForm[field.key]"
                  :placeholder="field.placeholder"
                  :disabled="field.key === 'publishNote' ? !canManageConfig : false"
                  style="max-width: 420px"
                  @update:model-value="(v: string) => setPublishField(field.key, v)"
                />
                <el-button v-if="field.key === 'draftId'" class="ml-2" :loading="loadingDraft" @click="loadCurrentDraft">执行读取草稿</el-button>
              </el-form-item>
              <el-form-item>
                <ActionButtons
                  primary-text="执行预览差异"
                  secondary-text="执行确认发布"
                  secondary-type="success"
                  :primary-loading="loadingDiff"
                  :secondary-loading="publishing"
                  :secondary-disabled="!canManageConfig"
                  @primary="loadDiff"
                  @secondary="publishNow"
                />
              </el-form-item>
              <el-alert type="info" :closable="false" show-icon class="mt-2">
                <template #title>提示</template>
                若本次发布包含<strong>插件配置</strong>（飞书/电视墙/AI 回调等）变更，发布完成后需<strong>重启后端服务</strong>后插件才会加载新配置。
              </el-alert>
            </QueryFormSection>
          </TableCard>
        </el-tab-pane>

        <el-tab-pane label="差异预览" name="diff">
          <TableCard v-loading="loadingDiff">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">差异预览</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">版本 {{ fromRevision }}</div>
              </div>
            </template>
            <el-table :data="paginatedDiffRows" stripe style="width: 100%" empty-text="暂无差异数据">
              <el-table-column prop="module" label="模块" min-width="200" />
              <el-table-column prop="path" label="字段" min-width="160" />
              <el-table-column label="变更前" min-width="220">
                <template #default="{ row }">{{ toText(row.before) }}</template>
              </el-table-column>
              <el-table-column label="变更后" min-width="220">
                <template #default="{ row }">{{ toText(row.after) }}</template>
              </el-table-column>
              <el-table-column prop="risk_level" label="风险级别" width="120" />
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
                prev-text="上一页"
                next-text="下一页"
                size="small"
              />
            </div>
          </TableCard>
        </el-tab-pane>

        <el-tab-pane label="回滚中心" name="rollback">
          <TableCard v-loading="rollingBack">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">回滚中心</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">目标版本 {{ rollbackForm.targetRevision }}</div>
              </div>
            </template>
            <QueryFormSection label-width="160px" form-class="max-w-3xl">
              <el-form-item v-for="field in rollbackFields" :key="field.key" :label="field.label">
                <el-input-number
                  v-if="field.component === 'number'"
                  :model-value="rollbackForm[field.key]"
                  :min="1"
                  :disabled="!canManageConfig"
                  @update:model-value="(v: number) => setRollbackField(field.key, v)"
                />
                <el-input
                  v-else
                  :model-value="rollbackForm[field.key]"
                  :placeholder="field.placeholder"
                  :disabled="!canManageConfig"
                  @update:model-value="(v: string) => setRollbackField(field.key, v)"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="warning" :loading="rollingBack" :disabled="!canManageConfig" @click="rollbackNow">执行版本回滚</el-button>
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
import { getCurrentDraft } from '../api/configCenter'
import { getDraftDiff, publishDraft, rollbackRevision, type DiffItem } from '../api/releaseCenter'
import { getRoleInfo } from '../utils/auth'
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
const roleInfo = getRoleInfo()
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
    ElMessage.success(buildSuccessMessage('加载', '已读取当前草稿'))
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage('加载', error, '草稿读取异常'))
  } finally {
    loadingDraft.value = false
  }
}

const loadDiff = async () => {
  const draftField = releasePublishFields.find(item => item.key === 'draftId')
  const draftMessage = draftField ? validateFieldValue(draftField, publishForm.value.draftId) : null
  if (draftMessage) {
    ElMessage.warning(`校验失败：${draftMessage}`)
    return
  }
  loadingDiff.value = true
  try {
    const diff = await getDraftDiff(publishForm.value.draftId)
    fromRevision.value = diff.from_revision
    diffRows.value = diff.changes || []
    ElMessage.success(buildSuccessMessage('加载', `差异条数 ${diffRows.value.length}`))
    activeTab.value = 'diff'
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage('加载', error, '差异读取异常'))
  } finally {
    loadingDiff.value = false
  }
}

const publishNow = async () => {
  if (!canManageConfig) {
    ElMessage.warning('当前账号无发布权限')
    return
  }
  const draftField = releasePublishFields.find(item => item.key === 'draftId')
  const draftMessage = draftField ? validateFieldValue(draftField, publishForm.value.draftId) : null
  if (draftMessage) {
    ElMessage.warning(`校验失败：${draftMessage}`)
    return
  }
  try {
    await ElMessageBox.confirm(`确认发布草稿 ${publishForm.value.draftId} 吗？`, '发布确认', { type: 'warning' })
  } catch {
    return
  }
  publishing.value = true
  try {
    const result = await publishDraft(publishForm.value.draftId, publishForm.value.publishNote)
    ElMessage.success(buildSuccessMessage('发布', `revision=${result.revision}`))
    rollbackForm.value.targetRevision = result.revision
    await loadDiff()
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage('发布', error))
  } finally {
    publishing.value = false
  }
}

const rollbackNow = async () => {
  if (!canManageConfig) {
    ElMessage.warning('当前账号无回滚权限')
    return
  }
  const revisionField = releaseRollbackFields.find(item => item.key === 'targetRevision')
  const revisionMessage = revisionField ? validateFieldValue(revisionField, rollbackForm.value.targetRevision) : null
  if (revisionMessage) {
    ElMessage.warning(`校验失败：${revisionMessage}`)
    return
  }
  try {
    await ElMessageBox.confirm(`确认回滚到 revision=${rollbackForm.value.targetRevision} 吗？`, '回滚确认', { type: 'warning' })
  } catch {
    return
  }
  rollingBack.value = true
  try {
    await rollbackRevision(rollbackForm.value.targetRevision, rollbackForm.value.reason)
    ElMessage.success(buildSuccessMessage('回滚', `revision=${rollbackForm.value.targetRevision}`))
  } catch (error: unknown) {
    ElMessage.error(buildErrorMessage('回滚', error))
  } finally {
    rollingBack.value = false
  }
}

onMounted(async () => {
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
