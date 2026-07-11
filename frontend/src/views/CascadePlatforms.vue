<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('cascade.headerTitle')" :description="t('cascade.headerDesc')">
          <template #actions>
            <el-button type="primary" size="small" @click="openForm()">{{ t('cascade.add') }}</el-button>
            <el-button size="small" @click="loadList" :loading="loading">{{ t('cascade.refresh') }}</el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard v-loading="loading">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-medium">{{ t('cascade.list') }}</div>
          <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('cascade.totalRecords', { total: list.length }) }}</div>
        </div>
      </template>
      <el-table :data="paginatedList" stripe size="small" :empty-text="t('cascade.emptyHint')">
        <el-table-column prop="name" :label="t('cascade.name')" min-width="120" />
        <el-table-column prop="server_gb_id" :label="t('cascade.upstreamGbId')" width="180" />
        <el-table-column :label="t('cascade.upstreamAddress')" width="160">
          <template #default="{ row }">{{ row.server_ip }}:{{ row.server_port }}</template>
        </el-table-column>
        <el-table-column :label="t('cascade.transport')" width="80">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ String(row.transport || 'UDP').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="client_gb_id" :label="t('cascade.localGbId')" width="180" />
        <el-table-column :label="t('cascade.connectStatus')" width="120">
          <template #default="{ row }">
            <div class="flex items-center gap-1">
              <span v-if="!row.enable" class="text-xs" style="color:var(--el-text-color-secondary)">{{ t('cascade.disabled') }}</span>
              <template v-else-if="row.is_online">
                <span class="text-sm">🟢</span>
                <span class="text-xs">{{ t('cascade.connected') }}</span>
              </template>
              <template v-else-if="runtimeRegisterOk(row)">
                <span class="text-sm">🟡</span>
                <el-tooltip :content="t('cascade.registerOkButOffline')" placement="top">
                  <span class="text-xs">{{ t('cascade.everConnected') }}</span>
                </el-tooltip>
              </template>
              <template v-else-if="runtimeField(row, 'register.last_sent_at')">
                <span class="text-sm">🔴</span>
                <el-tooltip :content="runtimeError(row) || t('cascade.registerNotSuccessful')" placement="top">
                  <span class="text-xs">{{ t('cascade.connectFailed') }}</span>
                </el-tooltip>
              </template>
              <template v-else>
                <span class="text-xs" style="color:var(--el-text-color-secondary)">{{ t('cascade.notConnected') }}</span>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('cascade.keepalive')" width="100">
          <template #default="{ row }">
            <template v-if="!row.enable || !row.is_online">
              <span class="text-xs" style="color:var(--el-text-color-secondary)">—</span>
            </template>
            <template v-else-if="toInt(runtimeField(row, 'keepalive.miss_count')) === 0">
              <el-tag type="success" size="small">{{ t('cascade.normal') }}</el-tag>
            </template>
            <template v-else>
              <el-tooltip :content="t('cascade.keepaliveMissTip', { count: runtimeField(row, 'keepalive.miss_count') })" placement="top">
                <el-tag type="warning" size="small">{{ t('cascade.keepaliveMissCount', { count: runtimeField(row, 'keepalive.miss_count') }) }}</el-tag>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <el-table-column :label="t('cascade.catalogPush')" width="120">
          <template #default="{ row }">
            <template v-if="!row.enable || !row.is_online">
              <span class="text-xs" style="color:var(--el-text-color-secondary)">—</span>
            </template>
            <template v-else-if="String(runtimeField(row, 'catalog.last_push_ok')) === 'true'">
              <el-tag type="success" size="small">{{ t('cascade.pushed') }}</el-tag>
            </template>
            <template v-else-if="String(runtimeField(row, 'catalog.last_push_ok')) === 'false' && runtimeField(row, 'catalog.last_push_finished_at')">
              <el-tooltip :content="runtimeField(row, 'catalog.last_push_error') || t('cascade.pushFailed')" placement="top">
                <el-tag type="danger" size="small">{{ t('cascade.pushFailed') }}</el-tag>
              </el-tooltip>
            </template>
            <template v-else-if="runtimeField(row, 'catalog.last_push_started_at')">
              <el-tag type="warning" size="small">{{ t('cascade.pushing') }}</el-tag>
            </template>
            <template v-else>
              <el-tooltip :content="t('cascade.notPushedHint')" placement="top">
                <el-tag type="info" size="small">{{ t('cascade.notPushed') }}</el-tag>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <el-table-column :label="t('cascade.enable')" width="70">
          <template #default="{ row }">
            <el-tag :type="row.enable ? 'success' : 'info'" size="small" effect="plain">
              {{ row.enable ? t('cascade.on') : t('cascade.off') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('cascade.action')" width="240" fixed="right">
          <template #default="{ row }">
            <div class="table-action-inline">
              <el-button link type="primary" size="small" @click="openForm(row)">{{ t('cascade.edit') }}</el-button>
              <el-button link type="primary" size="small" @click="openDiagnosis(row)" :loading="actionLoading[row.id]?.diagnosis">{{ t('cascade.diagnosis') }}</el-button>
              <el-dropdown trigger="click" @command="(cmd: string) => handlePlatformMoreCommand(row, cmd)">
                <el-button link type="primary" size="small">{{ t('cascade.more') }}</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="catalogRange">{{ t('cascade.catalogRange') }}</el-dropdown-item>
                    <el-dropdown-item command="register" :disabled="!row.enable">{{ t('cascade.registerNow') }}</el-dropdown-item>
                    <el-dropdown-item command="pushCatalog" :disabled="!row.enable">{{ t('cascade.pushCatalog') }}</el-dropdown-item>
                    <el-dropdown-item command="logs">{{ t('cascade.linkedLogs') }}</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>{{ t('cascade.delete') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex justify-end mt-4 pagination-wrapper" v-if="list.length > 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="list.length"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          :prev-text="t('cascade.prevPage')"
          :next-text="t('cascade.nextPage')"
          size="small"
        />
      </div>
    </TableCard>

    <AppDialog v-model="dialogVisible" :title="editingId ? t('cascade.editTitle') : t('cascade.addTitle')" size="small">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="120px" size="small">
        <el-form-item :label="t('cascade.name')" prop="name">
          <el-input v-model="form.name" :placeholder="t('cascade.upstreamPlatformName')" />
        </el-form-item>
        <el-form-item :label="t('cascade.upstreamGbIdLabel')" prop="server_gb_id">
          <el-input v-model="form.server_gb_id" :placeholder="t('cascade.gbIdPlaceholder')" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item :label="t('cascade.upstreamIp')" prop="server_ip">
          <el-input v-model="form.server_ip" placeholder="192.168.1.100" />
        </el-form-item>
        <el-form-item :label="t('cascade.upstreamPort')" prop="server_port">
          <el-input-number v-model="form.server_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item :label="t('cascade.transportMode')">
          <el-select v-model="form.transport" style="width: 160px">
            <el-option label="UDP" value="UDP" />
            <el-option label="TCP" value="TCP" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('cascade.localGbId')" prop="client_gb_id">
          <el-input v-model="form.client_gb_id" :placeholder="t('cascade.localGbIdPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('cascade.password')">
          <el-input v-model="form.password" type="password" :placeholder="t('cascade.assignedPassword')" show-password />
        </el-form-item>
        <el-form-item :label="t('cascade.registerInterval')">
          <el-input-number v-model="form.register_interval" :min="60" />
        </el-form-item>
        <el-form-item :label="t('cascade.keepaliveInterval')">
          <el-input-number v-model="form.keepalive_interval" :min="30" />
        </el-form-item>
        <el-form-item :label="t('cascade.catalogBatchSize')">
          <el-input-number v-model="form.catalog_batch_size" :min="0" :max="5000" />
        </el-form-item>
        <el-form-item :label="t('cascade.pushDelay')">
          <el-input-number v-model="form.catalog_push_delay_seconds" :min="0" :max="3600" />
        </el-form-item>
        <el-form-item :label="t('cascade.enable')">
          <el-switch v-model="form.enable" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('cascade.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('cascade.confirm') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="catalogVisible" :title="t('cascade.catalogRangeTitle')" size="medium" @open="loadCatalogData">
      <p class="text-sm mb-2" style="color: var(--el-text-color-secondary)">{{ t('cascade.catalogRangeHint') }}</p>
      <el-select
        v-model="catalogResourceIds"
        multiple
        filterable
        :placeholder="t('cascade.catalogRangePlaceholder')"
        style="width: 100%"
        :loading="catalogChannelsLoading"
      >
        <el-option
          v-for="ch in catalogChannels"
          :key="ch.id"
          :label="catalogOptionLabel(ch)"
          :value="ch.id || ''"
        />
      </el-select>
      <template #footer>
        <el-button @click="catalogVisible = false">{{ t('cascade.cancel') }}</el-button>
        <el-button type="primary" @click="saveCatalogResources" :loading="catalogSaving">{{ t('cascade.save') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="diagnosisVisible" :title="t('cascade.diagnosisTitle')" size="large">
      <div v-if="diagnosisLoading" class="h-24 flex items-center justify-center" style="color: var(--el-text-color-secondary)">{{ t('cascade.loading') }}</div>
      <template v-else>
        <div class="flex items-center justify-between mb-3">
          <div class="text-sm">
            <span class="font-medium">{{ diagnosisData?.platform?.name || '—' }}</span>
            <span class="ml-2 text-xs" style="color: var(--el-text-color-secondary)">
              {{ diagnosisData?.platform?.server_ip }}:{{ diagnosisData?.platform?.server_port }} / {{ String(diagnosisData?.platform?.transport || 'UDP').toUpperCase() }}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <el-button size="small" @click="copyDiagnosis">{{ t('cascade.copyDiagnosis') }}</el-button>
            <el-button size="small" @click="refreshDiagnosis" :loading="diagnosisLoading">{{ t('cascade.refresh') }}</el-button>
          </div>
        </div>

        <!-- 总体状态 -->
        <div v-if="diagnosisData" class="cascade-diag-banner mb-4" :class="'cascade-diag-' + (diagnosisData.level === 'error' ? 'error' : diagnosisData.level === 'warn' ? 'warn' : 'ok')">
          <div class="cascade-diag-icon">{{ diagnosisData.level === 'error' ? '🔴' : diagnosisData.level === 'warn' ? '🟡' : '🟢' }}</div>
          <div>
            <div class="cascade-diag-title">{{ diagnosisData.level === 'error' ? t('cascade.diagLevelError') : diagnosisData.level === 'warn' ? t('cascade.diagLevelWarn') : t('cascade.diagLevelOk') }}</div>
            <div class="cascade-diag-desc">{{ diagBannerDesc }}</div>
          </div>
        </div>

        <!-- 注册流程步骤条 -->
        <div v-if="diagnosisData" class="mb-4">
          <div class="text-sm font-semibold mb-3">{{ t('cascade.diagRegisterFlow') }}</div>
          <el-steps :active="diagStepActive" finish-status="success" :process-status="diagStepProcessStatus" align-center>
            <el-step :title="t('cascade.diagStep1')" :description="diagStep1Desc" />
            <el-step :title="t('cascade.diagStep2')" :description="diagStep2Desc" />
            <el-step :title="t('cascade.diagStep3')" :description="diagStep3Desc" />
            <el-step :title="t('cascade.diagStep4')" :description="diagStep4Desc" />
          </el-steps>
        </div>

        <!-- 诊断结论（卡片式） -->
        <div v-if="(diagnosisData?.diagnostics || []).length > 0" class="mb-4">
          <div class="text-sm font-semibold mb-2">{{ t('cascade.diagResult') }}</div>
          <div class="space-y-2">
            <div v-for="d in diagnosisData?.diagnostics" :key="d.key" class="p-3 rounded" :style="{
                background: d.level === 'error' ? 'var(--el-color-danger-light-9)' : d.level === 'warn' ? 'var(--el-color-warning-light-9)' : 'var(--el-color-success-light-9)',
                border: '1px solid ' + (d.level === 'error' ? 'var(--el-color-danger-light-5)' : d.level === 'warn' ? 'var(--el-color-warning-light-5)' : 'var(--el-color-success-light-5)')
              }">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-lg">{{ d.level === 'error' ? '🔴' : d.level === 'warn' ? '🟡' : '🟢' }}</span>
                <span class="text-sm font-medium">{{ d.title }}</span>
              </div>
              <div class="text-xs mb-2" style="color: var(--el-text-color-regular)">{{ d.detail }}</div>
              <div class="text-xs p-2 rounded" style="background:var(--el-fill-color); color: var(--el-color-primary)">
                <strong>{{ t('cascade.diagHowToFix') }}</strong>{{ d.suggestion }}
              </div>
            </div>
          </div>
        </div>

        <!-- 高级详情（默认折叠） -->
        <el-collapse>
          <el-collapse-item :title="t('cascade.diagAdvanced')" name="advanced">
            <el-collapse v-if="diagnosisData?.recent_trace_by_trace_id && Object.keys(diagnosisData.recent_trace_by_trace_id).length">
              <el-collapse-item :title="t('cascade.diagRecentSip')" name="traces">
                <div v-for="(events, traceId) in diagnosisData.recent_trace_by_trace_id" :key="traceId" class="mb-3">
                  <div class="text-xs font-medium mb-1">{{ t('cascade.diagSession', { id: traceId }) }}</div>
                  <el-timeline>
                    <el-timeline-item v-for="(evt, idx) in events" :key="idx" :color="getTraceColor(evt.event)">
                      <div class="text-xs">
                        <el-tag :type="getTraceTagType(evt.event)" size="small">{{ diagEventLabel(evt.event) }}</el-tag>
                        <span class="ml-2" style="color: var(--el-text-color-secondary)">{{ evt.created_at }}</span>
                        <div v-if="evt.payload && Object.keys(evt.payload).length" class="mt-1" style="color: var(--el-text-color-secondary)">
                          <pre class="text-xs whitespace-pre-wrap break-all">{{ JSON.stringify(evt.payload, null, 2) }}</pre>
                        </div>
                      </div>
                    </el-timeline-item>
                  </el-timeline>
                </div>
              </el-collapse-item>
            </el-collapse>

            <el-collapse v-if="diagnosisData?.sip_config">
              <el-collapse-item :title="t('cascade.diagSipConfig')" name="sip_config">
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="SIP_ID">{{ diagnosisData.sip_config.sip_id || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="SIP_DOMAIN">{{ diagnosisData.sip_config.sip_domain || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="SIP_IP">{{ maskSipIp(diagnosisData.sip_config.sip_ip) || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="SIP_PORT">{{ diagnosisData.sip_config.sip_port || '—' }}</el-descriptions-item>
                </el-descriptions>
              </el-collapse-item>
            </el-collapse>

            <el-collapse v-if="diagnosisData?.recent_trace_events_count">
              <el-collapse-item :title="t('cascade.diagEventStats')" name="stats">
                <div class="flex gap-2 flex-wrap">
                  <el-tag type="info" size="small">{{ t('cascade.diagStatRegisterSent', { count: diagnosisData.recent_trace_events_count.platform_register_sent || 0 }) }}</el-tag>
                  <el-tag type="warning" size="small">{{ t('cascade.diagStat401', { count: diagnosisData.recent_trace_events_count.platform_register_401 || 0 }) }}</el-tag>
                  <el-tag type="success" size="small">{{ t('cascade.diagStatRegisterOk', { count: diagnosisData.recent_trace_events_count.platform_register_ok || 0 }) }}</el-tag>
                  <el-tag type="danger" size="small">{{ t('cascade.diagStatRegisterFailed', { count: diagnosisData.recent_trace_events_count.platform_register_failed || 0 }) }}</el-tag>
                </div>
              </el-collapse-item>
            </el-collapse>

            <el-collapse>
              <el-collapse-item :title="t('cascade.diagRuntimeRaw')" name="runtime">
                <pre class="text-xs whitespace-pre-wrap break-all p-3 rounded" style="background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter);">{{ JSON.stringify(diagnosisData?.runtime || {}, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </el-collapse-item>
        </el-collapse>
      </template>
      <template #footer>
        <el-button @click="diagnosisVisible = false">{{ t('cascade.close') }}</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import { maskSipIp } from '../utils/sipMask' // FIX H-10: SIP IP 脱敏
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { useRouter } from 'vue-router'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'
import { useI18n } from 'vue-i18n'  // FIXED: P3 i18n

const { t } = useI18n()  // FIXED: P3 i18n

const list = ref<CascadePlatform[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<string | null>(null)
const router = useRouter()

const page = ref(1)
const pageSize = ref(10)
const paginatedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return list.value.slice(start, end)
})
watch(list, () => { page.value = 1 })

const formRef = ref<FormInstance>()
const form = reactive({
  name: '',
  server_gb_id: '',
  server_ip: '',
  server_port: 5060,
  transport: 'UDP',
  client_gb_id: '',
  password: '',
  register_interval: 3600,
  keepalive_interval: 60,
  catalog_batch_size: 0,
  catalog_push_delay_seconds: 0,
  enable: true
})

const formRules = reactive<FormRules>({
  name: [{ required: true, message: t('cascade.nameRequired'), trigger: 'blur' }],
  server_gb_id: [
    { required: true, message: t('cascade.upstreamGbIdRequired'), trigger: 'blur' },
    { len: 20, message: t('cascade.gbIdLength'), trigger: 'blur' }
  ],
  server_ip: [{ required: true, message: t('cascade.upstreamIpRequired'), trigger: 'blur' }],
  client_gb_id: [
    { required: true, message: t('cascade.localGbIdRequired'), trigger: 'blur' },
    { len: 20, message: t('cascade.gbIdLength'), trigger: 'blur' }
  ],
})

const loadList = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/platforms')
    list.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    list.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    loading.value = false
  }
}

type RuntimeLikeRow = { runtime?: unknown } & Record<string, unknown>

const runtimeField = (row: RuntimeLikeRow, key: string) => {
  const rt = row?.runtime
  if (!rt || typeof rt !== 'object') return ''
  return String((rt as Record<string, unknown>)[key] || '')
}

const runtimeError = (row: Record<string, unknown>) => {
  const err = runtimeField(row, 'catalog.last_push_error') || runtimeField(row, 'register.last_error') || ''
  return err
}

const runtimeRegisterOk = (row: Record<string, unknown>) => {
  const code = runtimeField(row, 'register.last_status_code')
  return String(code) === '200'
}

const toInt = (v: unknown) => {
  const n = parseInt(String(v ?? '').trim(), 10)
  return Number.isFinite(n) ? n : 0
}

const catalogProgressText = (row: Record<string, unknown>) => {
  const idx = toInt(runtimeField(row, 'catalog.batch_idx'))
  const total = toInt(runtimeField(row, 'catalog.batch_total'))
  if (!total) return ''
  if (!idx) return `0/${total}`
  return `${Math.min(idx, total)}/${total}`
}

const catalogAckText = (row: Record<string, unknown>) => {
  const ok = toInt(runtimeField(row, 'catalog.ack_ok_count'))
  const total = toInt(runtimeField(row, 'catalog.ack_total'))
  if (!total) return ''
  return `${Math.min(ok, total)}/${total}`
}

const openLogs = (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  router.push({ path: '/ops', query: { tab: 'trace', platform_id: id } })
}

const actionLoading = ref<Record<string, { register?: boolean; catalog?: boolean; diagnosis?: boolean }>>({})
const diagnosisVisible = ref(false)
const diagnosisLoading = ref(false)
const diagnosisData = ref<CascadePlatform | null>(null)

const triggerRegister = async (row: Record<string, unknown>) => {
  const id = String(row.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm(t('cascade.registerConfirm', { name: row.name || t('cascade.thisPlatform') }), t('cascade.registerNow'), { type: 'warning' })
  } catch {
    return
  }
  actionLoading.value[id] = { ...(actionLoading.value[id] || {}), register: true }
  try {
    await api.post(`/api/v1/platforms/${id}/actions/register`)
    ElMessage.success(t('cascade.registerTriggered'))
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    actionLoading.value[id] = { ...(actionLoading.value[id] || {}), register: false }
  }
}

const triggerCatalog = async (row: Record<string, unknown>) => {
  const id = String(row.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm(t('cascade.pushCatalogConfirm', { name: row.name || t('cascade.thisPlatform') }), t('cascade.pushCatalog'), { type: 'warning' })
  } catch {
    return
  }
  actionLoading.value[id] = { ...(actionLoading.value[id] || {}), catalog: true }
  try {
    await api.post(`/api/v1/platforms/${id}/actions/push-catalog`)
    ElMessage.success(t('cascade.pushCatalogTriggered'))
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    actionLoading.value[id] = { ...(actionLoading.value[id] || {}), catalog: false }
  }
}

const resetForm = () => {
  form.name = ''
  form.server_gb_id = ''
  form.server_ip = ''
  form.server_port = 5060
  form.transport = 'UDP'
  form.client_gb_id = ''
  form.password = ''
  form.register_interval = 3600
  form.keepalive_interval = 60
  form.catalog_batch_size = 0
  form.catalog_push_delay_seconds = 0
  form.enable = true
  editingId.value = null
}

const openForm = (row?: Record<string, unknown>) => {
  resetForm()
  if (row) {
    editingId.value = String(row.id || '')
    form.name = String(row.name || '')
    form.server_gb_id = String(row.server_gb_id || '')
    form.server_ip = String(row.server_ip || '')
    form.server_port = Number(row.server_port || 5060)
    form.transport = String(row.transport || 'UDP').toUpperCase()
    form.client_gb_id = String(row.client_gb_id || '')
    form.register_interval = Number(row.register_interval || 3600)
    form.keepalive_interval = Number(row.keepalive_interval || 60)
    form.catalog_batch_size = Number(row.catalog_batch_size || 0)
    form.catalog_push_delay_seconds = Number(row.catalog_push_delay_seconds || 0)
    form.enable = Boolean(row.enable)
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value) {
      const payload: Record<string, unknown> = {
        name: form.name,
        server_gb_id: form.server_gb_id,
        server_ip: form.server_ip,
        server_port: form.server_port,
        transport: form.transport,
        client_gb_id: form.client_gb_id,
        password: form.password,
        register_interval: form.register_interval,
        keepalive_interval: form.keepalive_interval,
        catalog_batch_size: form.catalog_batch_size,
        catalog_push_delay_seconds: form.catalog_push_delay_seconds,
        enable: form.enable
      }
      if (!String(form.password || '').trim()) delete payload.password
      await api.put(`/api/v1/platforms/${editingId.value}`, payload)
      ElMessage.success(t('cascade.updated'))
    } else {
      try {
        const existsRes = await api.get(`/api/v1/platforms/exist/${encodeURIComponent(String(form.server_gb_id || '').trim())}`)
        if (existsRes.data?.exists) {
          await ElMessageBox.confirm(t('cascade.gbIdExistsConfirm'), t('cascade.notice'), { type: 'warning' })
        }
      } catch {
        // ignore
      }
      await api.post('/api/v1/platforms', form)
      ElMessage.success(t('cascade.added'))
    }
    dialogVisible.value = false
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(t('cascade.deleteConfirm', { name: row.name }), t('cascade.confirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/platforms/${row.id}`)
    ElMessage.success(t('cascade.deleted'))
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  }
}

const handlePlatformMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'catalogRange') {
    openCatalogDialog(row)
    return
  }
  if (cmd === 'register') {
    await triggerRegister(row)
    return
  }
  if (cmd === 'pushCatalog') {
    await triggerCatalog(row)
    return
  }
  if (cmd === 'logs') {
    openLogs(row)
    return
  }
  if (cmd === 'delete') {
    await handleDelete(row)
  }
}

const catalogVisible = ref(false)
const catalogPlatformId = ref<string | null>(null)
const catalogChannels = ref<CascadePlatform[]>([])
const catalogChannelsLoading = ref(false)
const catalogResourceIds = ref<string[]>([])
const catalogSaving = ref(false)

const loadCatalogData = async () => {
  if (!catalogPlatformId.value) return
  catalogChannelsLoading.value = true
  try {
    const [d0, d1, d2, crRes] = await Promise.all([
      api.get('/api/v1/platforms/channels/flat', { params: { channel_type: 0, skip: 0, limit: 5000 } }),
      api.get('/api/v1/platforms/channels/flat', { params: { channel_type: 1, skip: 0, limit: 5000 } }),
      api.get('/api/v1/platforms/channels/flat', { params: { channel_type: 2, skip: 0, limit: 5000 } }),
      api.get(`/api/v1/platforms/${catalogPlatformId.value}/catalog-resources`)
    ])
    const a0 = Array.isArray(d0.data?.items) ? d0.data.items : []
    const a1 = Array.isArray(d1.data?.items) ? d1.data.items : []
    const a2 = Array.isArray(d2.data?.items) ? d2.data.items : []
    catalogChannels.value = [...a0, ...a1, ...a2]
    catalogResourceIds.value = Array.isArray(crRes.data?.resource_ids) ? crRes.data.resource_ids : []
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
    catalogChannels.value = []
    catalogResourceIds.value = []
  } finally {
    catalogChannelsLoading.value = false
  }
}

const catalogOptionLabel = (ch: Record<string, unknown>) => {
  const chType = Number(ch?.channel_type ?? 0)
  if (chType === 1) return t('cascade.catalogOptStream', { name: ch?.name || ch?.gb_id || '—' })
  if (chType === 2) return t('cascade.catalogOptProxy', { protocol: ch?.protocol || '—', name: ch?.name || ch?.gb_id || '—' })
  const dev = ch?.device_name || ch?.device_id || '—'
  return t('cascade.catalogOptDevice', { device: dev, name: ch?.name || ch?.gb_id || '—' })
}

const openCatalogDialog = (row: Record<string, unknown>) => {
  catalogPlatformId.value = String(row.id || '')
  catalogVisible.value = true
}

const saveCatalogResources = async () => {
  if (!catalogPlatformId.value) return
  catalogSaving.value = true
  try {
    await api.put(`/api/v1/platforms/${catalogPlatformId.value}/catalog-resources`, {
      resource_ids: catalogResourceIds.value || []
    })
    ElMessage.success(t('cascade.saved'))
    catalogVisible.value = false
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    catalogSaving.value = false
  }
}

const refreshDiagnosis = async () => {
  const id = String(diagnosisData.value?.platform_id || diagnosisData.value?.platform?.id || '')
  if (!id) return
  diagnosisLoading.value = true
  try {
    const res = await api.get(`/api/v1/platforms/${id}/diagnosis`)
    diagnosisData.value = res.data || null
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    diagnosisLoading.value = false
  }
}

const openDiagnosis = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  actionLoading.value[id] = { ...(actionLoading.value[id] || {}), diagnosis: true }
  diagnosisVisible.value = true
  diagnosisLoading.value = true
  diagnosisData.value = null
  try {
    const res = await api.get(`/api/v1/platforms/${id}/diagnosis`)
    diagnosisData.value = res.data || null
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('cascade.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
    diagnosisVisible.value = false
  } finally {
    diagnosisLoading.value = false
    actionLoading.value[id] = { ...(actionLoading.value[id] || {}), diagnosis: false }
  }
}

const copyDiagnosis = async () => {
  if (!diagnosisData.value) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(diagnosisData.value, null, 2))
    ElMessage.success(t('cascade.copied'))
  } catch {
    ElMessage.error(t('cascade.copyFailed'))
  }
}

// 获取特定平台ID关联的trace事件
const getTracesForPlatform = (platformId: string) => {
  if (!diagnosisData.value?.recent_trace_by_trace_id) return []
  const traces: Record<string, unknown>[] = []
  const traces_by_id = diagnosisData.value.recent_trace_by_trace_id as Record<string, any[]>
  for (const tid in traces_by_id) {
    for (const evt of traces_by_id[tid]) {
      if (evt.payload?.platform_id === platformId || evt.payload?.gb_id) {
        traces.push(evt)
      }
    }
  }
  return traces.slice(0, 10) // 最多显示10条
}

// 获取trace事件的颜色
const getTraceColor = (event: string) => {
  if (event.includes('failed') || event.includes('error')) return '#F56C6C'
  if (event.includes('ok') || event.includes('success')) return '#67C23A'
  if (event.includes('401') || event.includes('challenge')) return '#E6A23C'
  return '#409EFF'
}

const getTraceTagType = (event: string) => {
  if (event.includes('ok') || event.includes('success')) return 'success'
  if (event.includes('failed') || event.includes('error')) return 'danger'
  if (event.includes('401') || event.includes('challenge')) return 'warning'
  return 'info'
}

const diagEventLabel = (event: string) => {
  const map: Record<string, string> = {
    'register_received': t('cascade.evtRegisterReceived'),
    'register_401_challenge': t('cascade.evtRegister401Challenge'),
    'register_ok_platform': t('cascade.evtRegisterOkPlatform'),
    'register_ok_device': t('cascade.evtRegisterOkDevice'),
    'register_auth_failed': t('cascade.evtRegisterAuthFailed'),
    'platform_register_sent': t('cascade.evtPlatformRegisterSent'),
    'platform_register_401': t('cascade.evtPlatformRegister401'),
    'platform_register_ok': t('cascade.evtPlatformRegisterOk'),
    'platform_register_failed': t('cascade.evtPlatformRegisterFailed'),
    'platform_keepalive_sent': t('cascade.evtPlatformKeepaliveSent'),
    'platform_keepalive_ack': t('cascade.evtPlatformKeepaliveAck'),
    'platform_catalog_sent': t('cascade.evtPlatformCatalogSent'),
  }
  return map[event] || event
}

const diagBannerDesc = computed(() => {
  if (!diagnosisData.value) return ''
  const diags = diagnosisData.value.diagnostics || []
  const errorCount = diags.filter((d: Record<string, unknown>) => d.level === 'error').length
  const warnCount = diags.filter((d: Record<string, unknown>) => d.level === 'warn').length
  if (errorCount === 0 && warnCount === 0) return t('cascade.diagAllOk')
  const parts = []
  if (errorCount > 0) parts.push(t('cascade.diagErrorCount', { count: errorCount }))
  if (warnCount > 0) parts.push(t('cascade.diagWarnCount', { count: warnCount }))
  return parts.join(t('cascade.diagListSeparator'))
})

const diagStepActive = computed(() => {
  if (!diagnosisData.value) return 0
  const rt = diagnosisData.value.runtime || {}
  const diags = diagnosisData.value.diagnostics || []
  if (rt['register.last_ok_at']) {
    const missCount = parseInt(rt['keepalive.miss_count'] || '0')
    if (missCount === 0 && !diags.some((d: Record<string, unknown>) => String(d.key || '').startsWith('keepalive'))) return 4
    return 3
  }
  if (rt['register.last_status_code']) return 2
  if (rt['register.last_sent_at']) return 1
  return 0
})

const diagStepProcessStatus = computed(() => {
  if (!diagnosisData.value) return 'process'
  const diags = diagnosisData.value.diagnostics || []
  if (diags.some((d: Record<string, unknown>) => d.level === 'error')) return 'error'
  return 'process'
})

const diagStep1Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  if (rt['register.last_sent_at']) return t('cascade.diagStep1Sent')
  return t('cascade.diagStep1NotSent')
})

const diagStep2Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  const code = rt['register.last_status_code']
  if (code === '401') return t('cascade.diagStep2Challenged')
  if (rt['register.last_has_auth']) return t('cascade.diagStep2Passed')
  return '—'
})

const diagStep3Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  if (rt['register.last_ok_at']) return t('cascade.diagStep3Success')
  const code = rt['register.last_status_code']
  if (code === '403') return t('cascade.diagStep3Rejected')
  if (rt['register.last_error']) return t('cascade.diagStep3Failed')
  return '—'
})

const diagStep4Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  const miss = parseInt(rt['keepalive.miss_count'] || '0')
  if (rt['keepalive.last_ack_at']) return t('cascade.diagStep4Normal')
  if (miss > 0) return t('cascade.diagStep4Missed', { count: miss })
  return '—'
})

let pollTimer: number | null = null
onMounted(() => {
  loadList()
  pollTimer = window.setInterval(() => {
    loadList()
  }, 5000)
})

onBeforeUnmount(() => {
  if (pollTimer != null) window.clearInterval(pollTimer)
  pollTimer = null
})
</script>

<style scoped>
.cascade-diag-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid;
}
.cascade-diag-banner.cascade-diag-ok {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
}
.cascade-diag-banner.cascade-diag-warn {
  background: var(--el-color-warning-light-9);
  border-color: var(--el-color-warning-light-5);
}
.cascade-diag-banner.cascade-diag-error {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-5);
}
.cascade-diag-icon {
  font-size: 32px;
  line-height: 1;
}
.cascade-diag-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 2px;
}
.cascade-diag-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
