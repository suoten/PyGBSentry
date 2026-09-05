<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('apiKey.title')" :description="t('apiKey.description')">
          <template #actions>
            <el-button type="primary" @click="openCreateDialog">
              <el-icon class="mr-1"><Key /></el-icon>
              {{ t('apiKey.create') }}
            </el-button>
            <el-button @click="loadKeys" :loading="loading">{{ t('common.refresh') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('apiKey.keyList') }}</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('apiKey.totalCount', { count: keys.length }) }}</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && keys.length === 0" :rows="6" />
        <el-table v-else :data="paginatedKeys" border size="small" v-loading="loading" :empty-text="t('apiKey.empty')">
          <template #empty>
            <EmptyStateWithAction :description="t('apiKey.emptyHint')">
              <template #action>
                <el-button type="primary" @click="openCreateDialog">{{ t('apiKey.create') }}</el-button>
              </template>
            </EmptyStateWithAction>
          </template>

          <el-table-column prop="name" :label="t('common.name')" min-width="180" />
          <el-table-column prop="key_prefix" :label="t('apiKey.colPrefix')" width="110">
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.key_prefix }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.status')" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? t('apiKey.statusActive') : t('apiKey.statusRevoked') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('apiKey.colScopes')" min-width="220">
            <template #default="{ row }">
              <div v-if="Array.isArray(row.scopes) && row.scopes.length" class="flex flex-wrap gap-1">
                <el-tag v-for="s in row.scopes" :key="s" size="small" effect="plain">{{ s }}</el-tag>
              </div>
              <span v-else style="color: var(--el-text-color-secondary)">{{ t('apiKey.scopeAll') }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="last_used_at" :label="t('apiKey.colLastUsed')" width="190" />
          <el-table-column prop="created_at" :label="t('common.createTime')" width="190" />
          <el-table-column :label="t('common.action')" width="140" align="center">
            <template #default="{ row }">
              <el-button v-if="row.is_active" size="small" type="danger" plain :loading="revoking === row.id" @click="revoke(row.id)">{{ t('apiKey.revoke') }}</el-button>
              <el-button v-else size="small" disabled>{{ t('apiKey.revoked') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="keys.length > 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="keys.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            :prev-text="t('pagination.prev')"
            :next-text="t('pagination.next')"
            size="small"
          />
        </div>
      </TableCard>

      <AppDialog v-model="createVisible" :title="t('apiKey.createTitle')" size="medium" :icon="Key" icon-color="primary">
        <el-form label-width="90px">
          <el-form-item :label="t('apiKey.formName')" required>
            <el-input v-model="createForm.name" :placeholder="t('apiKey.formNamePlaceholder')" />
          </el-form-item>
          <!-- FIX H-7: scopes 改为多选下拉 + 强制过期时间（最长 90 天） -->
          <el-form-item :label="t('apiKey.formScopes')">
            <el-select v-model="createScopes" multiple filterable allow-create default-first-option :placeholder="t('apiKey.formScopesPlaceholder')" style="width: 100%">
              <el-option v-for="s in availableScopes" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
              {{ t('apiKey.formScopesHint') }}
            </div>
          </el-form-item>
          <el-form-item :label="t('apiKey.formExpiresAt')" required>
            <el-date-picker v-model="createExpiresAt" type="datetime" :placeholder="t('apiKey.formExpiresAtPlaceholder')" :disabled-date="isDisabledExpiryDate" style="width: 100%" value-format="YYYY-MM-DDTHH:mm:ss" />
            <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
              {{ t('apiKey.formExpiresAtHint') }}
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="createKey" :loading="creating">{{ t('apiKey.createBtn') }}</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="secretVisible" :title="t('apiKey.secretDialogTitle')" size="medium" icon-color="warning">
        <el-alert type="warning" show-icon :closable="false" :title="t('apiKey.secretAlertTitle')" />
        <div class="mt-3">
          <el-input v-model="createdSecret" readonly />
          <div class="mt-2 flex gap-2">
            <el-button type="primary" @click="copySecret">
              <el-icon class="mr-1"><DocumentCopy /></el-icon>
              {{ t('apiKey.copy') }}
            </el-button>
            <el-button @click="secretVisible = false">{{ t('common.close') }}</el-button>
          </div>
          <div class="text-xs mt-3" style="color: var(--el-text-color-secondary)">
            {{ t('apiKey.secretHeader', { key: createdSecret }) }}
          </div>
        </div>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Key, DocumentCopy } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { getFriendlyError } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, MaintenanceRecord, StructuredEvent, PluginConfig } from '@/types/models'

const { t } = useI18n()
const loading = ref(false)
const keys = ref<ApiKey[]>([])

const page = ref(1)
const pageSize = ref(10)
const paginatedKeys = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return keys.value.slice(start, end)
})

const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ name: '' })
// FIX H-7: scopes 改为多选数组，新增过期时间（最长 90 天）
const createScopes = ref<string[]>([])
const createExpiresAt = ref('')
const MAX_EXPIRY_DAYS = 90

// FIX H-7: 常用权限范围枚举，供多选下拉
const availableScopes = computed(() => [
  { label: t('apiKey.scopeDevicesRead'), value: 'devices:read' },
  { label: t('apiKey.scopeDevicesWrite'), value: 'devices:write' },
  { label: t('apiKey.scopeChannelsRead'), value: 'channels:read' },
  { label: t('apiKey.scopeChannelsWrite'), value: 'channels:write' },
  { label: t('apiKey.scopeStreamPlay'), value: 'stream:play' },
  { label: t('apiKey.scopeRecordsRead'), value: 'records:read' },
  { label: t('apiKey.scopeAlarmsRead'), value: 'alarms:read' },
  { label: t('apiKey.scopeAlarmsHandle'), value: 'alarms:handle' },
  { label: t('apiKey.scopeAuditRead'), value: 'audit:read' },
  { label: t('apiKey.scopeConfigRead'), value: 'config:read' }
])

// FIX H-7: 禁用超过 90 天的过期日期
const isDisabledExpiryDate = (date: Date): boolean => {
  const max = new Date()
  max.setDate(max.getDate() + MAX_EXPIRY_DAYS)
  return date.getTime() > max.getTime()
}

const secretVisible = ref(false)
const createdSecret = ref('')
const revoking = ref('')

const loadKeys = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/user-api-keys/me')
    keys.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    keys.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  createForm.value = { name: '' }
  createScopes.value = []
  createExpiresAt.value = ''
  createVisible.value = true
}

const createKey = async () => {
  const name = String(createForm.value.name || '').trim()
  if (!name) {
    ElMessage.warning(t('apiKey.nameRequired'))
    return
  }
  // FIX H-7: 校验过期时间必填且不超过 90 天
  const expiresAt = String(createExpiresAt.value || '').trim()
  if (!expiresAt) {
    ElMessage.warning(t('apiKey.expiresAtRequired'))
    return
  }
  const expiryMs = new Date(expiresAt).getTime()
  if (isNaN(expiryMs)) {
    ElMessage.warning(t('apiKey.expiresAtInvalid'))
    return
  }
  const maxMs = Date.now() + MAX_EXPIRY_DAYS * 24 * 60 * 60 * 1000
  if (expiryMs > maxMs) {
    ElMessage.warning(t('apiKey.expiresAtMax', { days: MAX_EXPIRY_DAYS }))
    return
  }
  if (expiryMs <= Date.now()) {
    ElMessage.warning(t('apiKey.expiresAtFuture'))
    return
  }
  creating.value = true
  try {
    const scopes = createScopes.value
    // FIX H-6: 不传 organization_id/tenant_id，由后端从 token 提取机构范围
    const res = await api.post('/api/v1/user-api-keys', { name, scopes, expires_at: expiresAt })
    createdSecret.value = String(res.data?.api_key || '')
    createVisible.value = false
    secretVisible.value = true
    await loadKeys()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    creating.value = false
  }
}

const revoke = async (id: string) => {
  try {
    await ElMessageBox.confirm(t('apiKey.revokeConfirmMsg'), t('common.tips'), { type: 'warning' })
  } catch {
    return
  }
  revoking.value = id
  try {
    await api.post(`/api/v1/user-api-keys/${id}/revoke`)
    ElMessage.success(t('apiKey.revokedSuccess'))
    await loadKeys()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    revoking.value = ''
  }
}

const copySecret = async () => {
  const v = String(createdSecret.value || '')
  if (!v) return
  try {
    await navigator.clipboard.writeText(v)
    ElMessage.success(t('apiKey.copied'))
  } catch {
    await ElMessageBox.alert(v, t('apiKey.secretDialogTitlePlain'), { confirmButtonText: t('common.ok') })
  }
}

onMounted(() => {
  loadKeys()
})
</script>
