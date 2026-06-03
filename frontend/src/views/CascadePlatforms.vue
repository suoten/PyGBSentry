<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="国标级联" description="配置上级平台、推送范围与注册保活（含运行态诊断）">
          <template #actions>
            <el-button type="primary" size="small" @click="openForm()">新增</el-button>
            <el-button size="small" @click="loadList" :loading="loading">刷新</el-button>
          </template>
        </PageHeader>
      </template>

    <TableCard v-loading="loading">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-medium">列表</div>
          <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ list.length }} 条</div>
        </div>
      </template>
      <el-table :data="paginatedList" stripe size="small" :empty-text="'暂无国标级联，点击「新增」添加'">
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="server_gb_id" label="上级平台国标ID" width="180" />
        <el-table-column label="上级地址" width="160">
          <template #default="{ row }">{{ row.server_ip }}:{{ row.server_port }}</template>
        </el-table-column>
        <el-table-column label="传输" width="80">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ String(row.transport || 'UDP').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="client_gb_id" label="本平台国标ID" width="180" />
        <el-table-column label="连接状态" width="120">
          <template #default="{ row }">
            <div class="flex items-center gap-1">
              <span v-if="!row.enable" class="text-xs" style="color:var(--el-text-color-secondary)">已禁用</span>
              <template v-else-if="row.is_online">
                <span class="text-sm">🟢</span>
                <span class="text-xs">已连接</span>
              </template>
              <template v-else-if="runtimeRegisterOk(row)">
                <span class="text-sm">🟡</span>
                <el-tooltip :content="'注册成功但当前离线，可能保活丢失'" placement="top">
                  <span class="text-xs">曾连接</span>
                </el-tooltip>
              </template>
              <template v-else-if="runtimeField(row, 'register.last_sent_at')">
                <span class="text-sm">🔴</span>
                <el-tooltip :content="runtimeError(row) || '注册未成功'" placement="top">
                  <span class="text-xs">连接失败</span>
                </el-tooltip>
              </template>
              <template v-else>
                <span class="text-xs" style="color:var(--el-text-color-secondary)">未连接</span>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="保活" width="100">
          <template #default="{ row }">
            <template v-if="!row.enable || !row.is_online">
              <span class="text-xs" style="color:var(--el-text-color-secondary)">—</span>
            </template>
            <template v-else-if="toInt(runtimeField(row, 'keepalive.miss_count')) === 0">
              <el-tag type="success" size="small">正常</el-tag>
            </template>
            <template v-else>
              <el-tooltip :content="`已连续 ${runtimeField(row, 'keepalive.miss_count')} 次未收到心跳回复`" placement="top">
                <el-tag type="warning" size="small">丢失 {{ runtimeField(row, 'keepalive.miss_count') }} 次</el-tag>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="目录推送" width="120">
          <template #default="{ row }">
            <template v-if="!row.enable || !row.is_online">
              <span class="text-xs" style="color:var(--el-text-color-secondary)">—</span>
            </template>
            <template v-else-if="String(runtimeField(row, 'catalog.last_push_ok')) === 'true'">
              <el-tag type="success" size="small">已推送</el-tag>
            </template>
            <template v-else-if="String(runtimeField(row, 'catalog.last_push_ok')) === 'false' && runtimeField(row, 'catalog.last_push_finished_at')">
              <el-tooltip :content="runtimeField(row, 'catalog.last_push_error') || '推送失败'" placement="top">
                <el-tag type="danger" size="small">推送失败</el-tag>
              </el-tooltip>
            </template>
            <template v-else-if="runtimeField(row, 'catalog.last_push_started_at')">
              <el-tag type="warning" size="small">推送中</el-tag>
            </template>
            <template v-else>
              <el-tooltip content="尚未推送过目录，点击「更多→推送目录」触发" placement="top">
                <el-tag type="info" size="small">未推送</el-tag>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag :type="row.enable ? 'success' : 'info'" size="small" effect="plain">
              {{ row.enable ? '开' : '关' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <div class="table-action-inline">
              <el-button link type="primary" size="small" @click="openForm(row)">编辑</el-button>
              <el-button link type="primary" size="small" @click="openDiagnosis(row)" :loading="actionLoading[row.id]?.diagnosis">诊断</el-button>
              <el-dropdown trigger="click" @command="(cmd: string) => handlePlatformMoreCommand(row, cmd)">
                <el-button link type="primary" size="small">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="catalogRange">推送范围</el-dropdown-item>
                    <el-dropdown-item command="register" :disabled="!row.enable">立即注册</el-dropdown-item>
                    <el-dropdown-item command="pushCatalog" :disabled="!row.enable">推送目录</el-dropdown-item>
                    <el-dropdown-item command="logs">联动日志</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
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
          prev-text="上一页"
          next-text="下一页"
          size="small"
        />
      </div>
    </TableCard>

    <AppDialog v-model="dialogVisible" :title="editingId ? '编辑国标级联' : '新增国标级联'" size="small">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="120px" size="small">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="上级平台名称" />
        </el-form-item>
        <el-form-item label="上级国标ID" prop="server_gb_id">
          <el-input v-model="form.server_gb_id" placeholder="20位国标ID" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="上级IP" prop="server_ip">
          <el-input v-model="form.server_ip" placeholder="192.168.1.100" />
        </el-form-item>
        <el-form-item label="上级端口" prop="server_port">
          <el-input-number v-model="form.server_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="传输方式">
          <el-select v-model="form.transport" style="width: 160px">
            <el-option label="UDP" value="UDP" />
            <el-option label="TCP" value="TCP" />
          </el-select>
        </el-form-item>
        <el-form-item label="本平台国标ID" prop="client_gb_id">
          <el-input v-model="form.client_gb_id" placeholder="本机作为下级时的国标ID" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" :placeholder="t('cascade.assignedPassword')" show-password />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item label="注册间隔(秒)">
          <el-input-number v-model="form.register_interval" :min="60" />
        </el-form-item>
        <el-form-item label="保活间隔(秒)">
          <el-input-number v-model="form.keepalive_interval" :min="30" />
        </el-form-item>
        <el-form-item label="目录批大小">
          <el-input-number v-model="form.catalog_batch_size" :min="0" :max="5000" />
        </el-form-item>
        <el-form-item label="推送延迟(秒)">
          <el-input-number v-model="form.catalog_push_delay_seconds" :min="0" :max="3600" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enable" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="catalogVisible" title="目录推送范围" size="medium" @open="loadCatalogData">
      <p class="text-sm mb-2" style="color: var(--el-text-color-secondary)">不选或清空表示向该上级平台推送全部通道；选择部分通道则仅推送所选通道。</p>
      <el-select
        v-model="catalogResourceIds"
        multiple
        filterable
        placeholder="选择要推送的通道（不选=全部）"
        style="width: 100%"
        :loading="catalogChannelsLoading"
      >
        <el-option
          v-for="ch in catalogChannels"
          :key="ch.id"
          :label="catalogOptionLabel(ch)"
          :value="ch.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="catalogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCatalogResources" :loading="catalogSaving">保存</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="diagnosisVisible" title="级联诊断" size="large">
      <div v-if="diagnosisLoading" class="h-24 flex items-center justify-center" style="color: var(--el-text-color-secondary)">加载中…</div>
      <template v-else>
        <div class="flex items-center justify-between mb-3">
          <div class="text-sm">
            <span class="font-medium">{{ diagnosisData?.platform?.name || '—' }}</span>
            <span class="ml-2 text-xs" style="color: var(--el-text-color-secondary)">
              {{ diagnosisData?.platform?.server_ip }}:{{ diagnosisData?.platform?.server_port }} / {{ String(diagnosisData?.platform?.transport || 'UDP').toUpperCase() }}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <el-button size="small" @click="copyDiagnosis">复制诊断</el-button>
            <el-button size="small" @click="refreshDiagnosis" :loading="diagnosisLoading">刷新</el-button>
          </div>
        </div>

        <!-- 总体状态 -->
        <div v-if="diagnosisData" class="cascade-diag-banner mb-4" :class="'cascade-diag-' + (diagnosisData.level === 'error' ? 'error' : diagnosisData.level === 'warn' ? 'warn' : 'ok')">
          <div class="cascade-diag-icon">{{ diagnosisData.level === 'error' ? '🔴' : diagnosisData.level === 'warn' ? '🟡' : '🟢' }}</div>
          <div>
            <div class="cascade-diag-title">{{ diagnosisData.level === 'error' ? '级联存在异常' : diagnosisData.level === 'warn' ? '级联需要注意' : '级联状态正常' }}</div>
            <div class="cascade-diag-desc">{{ diagBannerDesc }}</div>
          </div>
        </div>

        <!-- 注册流程步骤条 -->
        <div v-if="diagnosisData" class="mb-4">
          <div class="text-sm font-semibold mb-3">注册流程检查</div>
          <el-steps :active="diagStepActive" finish-status="success" :process-status="diagStepProcessStatus" align-center>
            <el-step title="发送注册请求" :description="diagStep1Desc" />
            <el-step title="身份验证" :description="diagStep2Desc" />
            <el-step title="注册成功" :description="diagStep3Desc" />
            <el-step title="心跳保活" :description="diagStep4Desc" />
          </el-steps>
        </div>

        <!-- 诊断结论（卡片式） -->
        <div v-if="(diagnosisData?.diagnostics || []).length > 0" class="mb-4">
          <div class="text-sm font-semibold mb-2">诊断结果</div>
          <div class="space-y-2">
            <div v-for="d in diagnosisData.diagnostics" :key="d.key" class="p-3 rounded" :style="{
                background: d.level === 'error' ? 'var(--el-color-danger-light-9)' : d.level === 'warn' ? 'var(--el-color-warning-light-9)' : 'var(--el-color-success-light-9)',
                border: '1px solid ' + (d.level === 'error' ? 'var(--el-color-danger-light-5)' : d.level === 'warn' ? 'var(--el-color-warning-light-5)' : 'var(--el-color-success-light-5)')
              }">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-lg">{{ d.level === 'error' ? '🔴' : d.level === 'warn' ? '🟡' : '🟢' }}</span>
                <span class="text-sm font-medium">{{ d.title }}</span>
              </div>
              <div class="text-xs mb-2" style="color: var(--el-text-color-regular)">{{ d.detail }}</div>
              <div class="text-xs p-2 rounded" style="background:var(--el-fill-color); color: var(--el-color-primary)">
                <strong>怎么办：</strong>{{ d.suggestion }}
              </div>
            </div>
          </div>
        </div>

        <!-- 高级详情（默认折叠） -->
        <el-collapse>
          <el-collapse-item title="高级详情（技术数据）" name="advanced">
            <el-collapse v-if="diagnosisData?.recent_trace_by_trace_id && Object.keys(diagnosisData.recent_trace_by_trace_id).length">
              <el-collapse-item title="最近 SIP 信令事件" name="traces">
                <div v-for="(events, traceId) in diagnosisData.recent_trace_by_trace_id" :key="traceId" class="mb-3">
                  <div class="text-xs font-medium mb-1">会话: {{ traceId }}</div>
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
              <el-collapse-item title="SIP 配置" name="sip_config">
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="SIP_ID">{{ diagnosisData.sip_config.sip_id || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="SIP_DOMAIN">{{ diagnosisData.sip_config.sip_domain || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="SIP_IP">{{ diagnosisData.sip_config.sip_ip || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="SIP_PORT">{{ diagnosisData.sip_config.sip_port || '—' }}</el-descriptions-item>
                </el-descriptions>
              </el-collapse-item>
            </el-collapse>

            <el-collapse v-if="diagnosisData?.recent_trace_events_count">
              <el-collapse-item title="事件统计" name="stats">
                <div class="flex gap-2 flex-wrap">
                  <el-tag type="info" size="small">发送注册: {{ diagnosisData.recent_trace_events_count.platform_register_sent || 0 }}</el-tag>
                  <el-tag type="warning" size="small">收到401质询: {{ diagnosisData.recent_trace_events_count.platform_register_401 || 0 }}</el-tag>
                  <el-tag type="success" size="small">注册成功: {{ diagnosisData.recent_trace_events_count.platform_register_ok || 0 }}</el-tag>
                  <el-tag type="danger" size="small">注册失败: {{ diagnosisData.recent_trace_events_count.platform_register_failed || 0 }}</el-tag>
                </div>
              </el-collapse-item>
            </el-collapse>

            <el-collapse>
              <el-collapse-item title="运行态原始数据" name="runtime">
                <pre class="text-xs whitespace-pre-wrap break-all p-3 rounded" style="background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter);">{{ JSON.stringify(diagnosisData?.runtime || {}, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </el-collapse-item>
        </el-collapse>
      </template>
      <template #footer>
        <el-button @click="diagnosisVisible = false">关闭</el-button>
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
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  server_gb_id: [
    { required: true, message: '请输入上级国标ID', trigger: 'blur' },
    { len: 20, message: '国标ID应为20位', trigger: 'blur' }
  ],
  server_ip: [{ required: true, message: '请输入上级IP', trigger: 'blur' }],
  client_gb_id: [
    { required: true, message: '请输入本平台国标ID', trigger: 'blur' },
    { len: 20, message: '国标ID应为20位', trigger: 'blur' }
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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
const diagnosisData = ref<CascadePlatform>(null)

const triggerRegister = async (row: Record<string, unknown>) => {
  const id = String(row.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm(`确认向「${row.name || '该平台'}」发送注册请求？`, '立即注册', { type: 'warning' })
  } catch {
    return
  }
  actionLoading.value[id] = { ...(actionLoading.value[id] || {}), register: true }
  try {
    await api.post(`/api/v1/platforms/${id}/actions/register`)
    ElMessage.success('已触发注册')
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    actionLoading.value[id] = { ...(actionLoading.value[id] || {}), register: false }
  }
}

const triggerCatalog = async (row: Record<string, unknown>) => {
  const id = String(row.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm(`确认向「${row.name || '该平台'}」推送目录？推送期间可能影响上级平台已有目录数据。`, '推送目录', { type: 'warning' })
  } catch {
    return
  }
  actionLoading.value[id] = { ...(actionLoading.value[id] || {}), catalog: true }
  try {
    await api.post(`/api/v1/platforms/${id}/actions/push-catalog`)
    ElMessage.success('已触发目录推送')
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    editingId.value = row.id
    form.name = row.name
    form.server_gb_id = row.server_gb_id
    form.server_ip = row.server_ip
    form.server_port = row.server_port
    form.transport = String(row.transport || 'UDP').toUpperCase()
    form.client_gb_id = row.client_gb_id
    form.register_interval = row.register_interval
    form.keepalive_interval = row.keepalive_interval
    form.catalog_batch_size = row.catalog_batch_size || 0
    form.catalog_push_delay_seconds = row.catalog_push_delay_seconds || 0
    form.enable = row.enable
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
      ElMessage.success('已更新')
    } else {
      try {
        const existsRes = await api.get(`/api/v1/platforms/exist/${encodeURIComponent(String(form.server_gb_id || '').trim())}`)
        if (existsRes.data?.exists) {
          await ElMessageBox.confirm('该上级平台国标ID已存在，仍要继续新增吗？', '提示', { type: 'warning' })
        }
      } catch {
        // ignore
      }
      await api.post('/api/v1/platforms', form)
      ElMessage.success('已添加')
    }
    dialogVisible.value = false
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(`确定删除国标级联「${row.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/platforms/${row.id}`)
    ElMessage.success('已删除')
    await loadList()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    catalogChannels.value = []
    catalogResourceIds.value = []
  } finally {
    catalogChannelsLoading.value = false
  }
}

const catalogOptionLabel = (ch: Record<string, unknown>) => {
  const t = Number(ch?.channel_type ?? 0)
  if (t === 1) return `推流 / ${ch?.name || ch?.gb_id || '—'}`
  if (t === 2) return `拉流代理(${ch?.protocol || '—'}) / ${ch?.name || ch?.gb_id || '—'}`
  const dev = ch?.device_name || ch?.device_id || '—'
  return `${dev} / ${ch?.name || ch?.gb_id || '—'}`
}

const openCatalogDialog = (row: Record<string, unknown>) => {
  catalogPlatformId.value = row.id
  catalogVisible.value = true
}

const saveCatalogResources = async () => {
  if (!catalogPlatformId.value) return
  catalogSaving.value = true
  try {
    await api.put(`/api/v1/platforms/${catalogPlatformId.value}/catalog-resources`, {
      resource_ids: catalogResourceIds.value || []
    })
    ElMessage.success('已保存')
    catalogVisible.value = false
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
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
    'register_received': '收到注册',
    'register_401_challenge': '要求验证身份',
    'register_ok_platform': '平台注册成功',
    'register_ok_device': '设备注册成功',
    'register_auth_failed': '验证失败',
    'platform_register_sent': '发送注册请求',
    'platform_register_401': '收到身份质询',
    'platform_register_ok': '注册成功',
    'platform_register_failed': '注册失败',
    'platform_keepalive_sent': '发送心跳',
    'platform_keepalive_ack': '收到心跳确认',
    'platform_catalog_sent': '推送目录',
  }
  return map[event] || event
}

const diagBannerDesc = computed(() => {
  if (!diagnosisData.value) return ''
  const diags = diagnosisData.value.diagnostics || []
  const errorCount = diags.filter((d: Record<string, unknown>) => d.level === 'error').length
  const warnCount = diags.filter((d: Record<string, unknown>) => d.level === 'warn').length
  if (errorCount === 0 && warnCount === 0) return '注册和保活均正常'
  const parts = []
  if (errorCount > 0) parts.push(`${errorCount} 个异常`)
  if (warnCount > 0) parts.push(`${warnCount} 个警告`)
  return parts.join('，')
})

const diagStepActive = computed(() => {
  if (!diagnosisData.value) return 0
  const rt = diagnosisData.value.runtime || {}
  const diags = diagnosisData.value.diagnostics || []
  if (rt['register.last_ok_at']) {
    const missCount = parseInt(rt['keepalive.miss_count'] || '0')
    if (missCount === 0 && !diags.some((d: Record<string, unknown>) => d.key?.startsWith('keepalive'))) return 4
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
  if (rt['register.last_sent_at']) return '已发送'
  return '未发送'
})

const diagStep2Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  const code = rt['register.last_status_code']
  if (code === '401') return '收到质询，正在认证'
  if (rt['register.last_has_auth']) return '已通过'
  return '—'
})

const diagStep3Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  if (rt['register.last_ok_at']) return '注册成功'
  const code = rt['register.last_status_code']
  if (code === '403') return '被拒绝(403)'
  if (rt['register.last_error']) return '注册失败'
  return '—'
})

const diagStep4Desc = computed(() => {
  if (!diagnosisData.value) return '—'
  const rt = diagnosisData.value.runtime || {}
  const miss = parseInt(rt['keepalive.miss_count'] || '0')
  if (rt['keepalive.last_ack_at']) return '心跳正常'
  if (miss > 0) return `${miss} 次未响应`
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
