<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('pushStream.title')" :description="t('pushStream.description')">
          <template #actions>
            <el-input v-model="keyword" :placeholder="t('pushStream.searchPlaceholder')" clearable style="width: 260px" class="mr-2" />
            <el-button v-if="activeTab === 'channels'" type="primary" @click="openCreateDialog">{{ t('pushStream.createChannel') }}</el-button>
            <el-button v-if="activeTab === 'channels'" @click="openBatchDialog">{{ t('pushStream.batchCreate') }}</el-button>
            <el-button v-if="activeTab === 'channels'" @click="openImportDialog">{{ t('pushStream.import') }}</el-button>
            <el-button @click="refreshAll" :loading="loading">{{ t('pushStream.refresh') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <el-tabs v-model="activeTab" class="mb-2">
        <el-tab-pane :label="t('pushStream.tabChannels')" name="channels" />
        <el-tab-pane :label="t('pushStream.tabStreams')" name="streams" />
      </el-tabs>

      <TableCard v-if="activeTab === 'channels'">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('pushStream.channelsTitle') }}</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('pushStream.total', { n: filteredChannels.length }) }}</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && channels.length === 0" :rows="6" />
        <template v-else-if="filteredChannels.length === 0">
          <EmptyStateWithAction :description="t('pushStream.emptyChannels')">
            <template #action>
              <el-button type="primary" @click="openCreateDialog">{{ t('pushStream.createChannel') }}</el-button>
            </template>
          </EmptyStateWithAction>
        </template>

        <el-table v-else :data="paginatedChannels" border size="small" :empty-text="t('pushStream.emptyChannelsShort')">
          <el-table-column prop="name" :label="t('pushStream.colName')" min-width="180" />
          <el-table-column :label="t('pushStream.colStreamName')" min-width="220">
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ normalizeStreamName(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colPushKey')" width="160" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.push_key_enabled" type="success" size="small">{{ row.push_key_hint || t('pushStream.pushKeyHintEnabled') }}</el-tag>
              <el-tag v-else type="info" size="small">{{ t('pushStream.pushKeyDisabled') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colGb')" width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="space-y-1">
                <el-tag v-if="row.gb_enabled" type="success" size="small">{{ t('pushStream.gbEnabled') }}</el-tag>
                <el-tag v-else type="info" size="small">{{ t('pushStream.gbDisabled') }}</el-tag>
                <div v-if="row.gb_enabled" class="text-xs font-mono" style="color: var(--el-text-color-secondary)">
                  {{ row.gb_id || '-' }} {{ row.gb_name ? `(${row.gb_name})` : '' }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colStatus')" width="120" align="center">
            <template #default="{ row }">
              <el-tag v-if="row?.extra?.['runtime.last_play_error']" type="danger" size="small">{{ t('pushStream.statusAbnormal') }}</el-tag>
              <el-tag v-else-if="isUnhealthy(row)" type="warning" size="small">{{ t('pushStream.statusAbnormal') }}</el-tag>
              <el-tag v-else :type="isRunningEffective(row) ? 'success' : 'info'" size="small">
                {{ isRunningEffective(row) ? t('pushStream.statusRunning') : t('pushStream.statusStopped') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colDesired')" width="150" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="desiredState(row)"
                size="small"
                style="width: 120px"
                @change="(val: unknown) => updateDesiredState(row, String(val || ''))"
              >
                <el-option :label="t('pushStream.desiredRunning')" value="running" />
                <el-option :label="t('pushStream.desiredStopped')" value="stopped" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colLastPlay')" width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="text-xs" style="color: var(--el-text-color-secondary)">
                {{ row?.extra?.['runtime.last_play_at'] || '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colHealth')" width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="space-y-1">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">
                  {{ row?.extra?.['runtime.rtmp.last_seen_at'] || '—' }}
                </div>
                <div v-if="row?.extra?.['runtime.rtmp.bytes_speed'] != null" class="text-xs" style="color: var(--el-text-color-secondary)">
                  {{ t('pushStream.healthBytesSpeedViewers', { speed: row?.extra?.['runtime.rtmp.bytes_speed'], count: row?.extra?.['runtime.rtmp.reader_count'] || 0 }) }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('pushStream.colAction')" width="540" align="center">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-2 justify-center">
                <el-button size="small" type="primary" plain @click="openEditDialog(row)">{{ t('pushStream.actionEdit') }}</el-button>
                <el-button size="small" @click="showPushUrl(row.id)">{{ t('pushStream.actionPushUrl') }}</el-button>
                <el-button size="small" @click="rotatePushKey(row.id)">{{ t('pushStream.actionRotateKey') }}</el-button>
                <el-button size="small" type="success" plain @click="preview(row.id)" :loading="playing[row.id]">{{ t('pushStream.actionPreview') }}</el-button>
                <el-button v-if="!row.gb_enabled" size="small" type="warning" plain @click="saveToGb(row)">{{ t('pushStream.actionSaveToGb') }}</el-button>
                <el-button v-if="row.gb_enabled" size="small" type="info" plain @click="removeFromGb(row)">{{ t('pushStream.actionRemoveFromGb') }}</el-button>
                <el-button v-if="desiredState(row) === 'stopped' && isRunningEffective(row)" size="small" type="warning" plain @click="enforceStop(row)" :loading="desiredUpdating[row.id]">{{ t('pushStream.actionEnforceStop') }}</el-button>
                <el-button v-else-if="isRunningEffective(row)" size="small" type="warning" plain @click="stopChannel(row)">{{ t('pushStream.actionStop') }}</el-button>
                <el-button size="small" type="danger" plain @click="remove(row.id)">{{ t('pushStream.actionDelete') }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="filteredChannels.length > 0">
          <el-pagination
            v-model:current-page="channelsPage"
            v-model:page-size="channelsPageSize"
            :total="filteredChannels.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            :prev-text="t('pushStream.prevPage')"
            :next-text="t('pushStream.nextPage')"
            size="small"
          />
        </div>
      </TableCard>

      <TableCard v-else>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('pushStream.streamsTitle') }}</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('pushStream.total', { n: filteredStreams.length }) }}</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && streams.length === 0" :rows="6" />
        <template v-else-if="filteredStreams.length === 0">
          <EmptyStateWithAction :description="t('pushStream.emptyStreams')">
            <template #action>
              <el-button type="primary" @click="$router.push('/devices')">{{ t('pushStream.goToDevices') }}</el-button>
              <el-button @click="goTvWall">{{ t('pushStream.goToTvWall') }}</el-button>
            </template>
          </EmptyStateWithAction>
        </template>

        <el-table v-else :data="paginatedStreams" border size="small" :empty-text="t('pushStream.emptyStreamsShort')" class="streams-table">
          <el-table-column prop="app" :label="t('pushStream.colApp')" width="90" />
          <el-table-column :label="t('pushStream.colStreamId')" min-width="220">
            <template #default="{ row }">
              <div class="flex items-center gap-2">
                <el-tag v-if="row.is_proxy" size="small" type="warning" effect="dark">{{ t('pushStream.tagProxy') }}</el-tag>
                <el-tag v-else size="small" type="success" effect="dark">{{ t('pushStream.tagGb') }}</el-tag>
                <span class="font-mono text-xs">{{ row.stream }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="origin_url" :label="t('pushStream.colOriginUrl')" min-width="260" show-overflow-tooltip />
          <el-table-column prop="reader_count" :label="t('pushStream.colReaderCount')" width="90" />
          <el-table-column prop="alive_second" :label="t('pushStream.colAliveSecond')" width="110" />
          <el-table-column prop="bytes_speed" :label="t('pushStream.colBytesSpeed')" width="120" />
          <el-table-column :label="t('pushStream.colAction')" width="140" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" plain @click="stopStream(row)" :loading="stopping[`${row.app}:${row.stream}`]">
                {{ t('pushStream.actionStopStream') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="filteredStreams.length > 0">
          <el-pagination
            v-model:current-page="streamsPage"
            v-model:page-size="streamsPageSize"
            :total="filteredStreams.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            :prev-text="t('pushStream.prevPage')"
            :next-text="t('pushStream.nextPage')"
            size="small"
          />
        </div>
      </TableCard>

      <AppDialog v-model="dialogVisible" :title="editingId ? t('pushStream.editTitle') : t('pushStream.createTitle')" size="medium">
        <el-form label-width="90px">
          <el-form-item :label="t('pushStream.formName')" required>
            <el-input v-model="form.name" :placeholder="t('pushStream.formNamePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('pushStream.formStreamName')">
            <el-input v-model="form.stream_name" :placeholder="t('pushStream.formStreamNamePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('pushStream.formEnabled')">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item :label="t('pushStream.formPushKey')">
            <el-switch v-model="form.push_key_enabled" />
          </el-form-item>
          <el-form-item :label="t('pushStream.formGb')">
            <el-switch v-model="form.gb_enabled" />
          </el-form-item>
          <template v-if="form.gb_enabled">
            <el-form-item :label="t('pushStream.formGbId')" required>
              <el-input v-model="form.gb_id" :placeholder="t('pushStream.formGbIdPlaceholder')" />
            </el-form-item>
            <el-form-item :label="t('pushStream.formGbName')">
              <el-input v-model="form.gb_name" :placeholder="t('pushStream.formGbNamePlaceholder')" />
            </el-form-item>
            <el-form-item :label="t('pushStream.formGbParentId')">
              <el-input v-model="form.gb_parent_gb_id" :placeholder="t('pushStream.formGbParentIdPlaceholder')" />
            </el-form-item>
          </template>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">{{ t('pushStream.btnCancel') }}</el-button>
          <el-button type="primary" @click="save" :loading="saving">{{ t('pushStream.btnSave') }}</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="previewVisible" :title="t('pushStream.previewTitle')" size="large" @closed="closePreview">
        <div v-if="previewStream.url" class="min-h-[360px]">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <el-radio-group v-model="previewMode" size="small">
                <el-radio-button v-if="previewStream.urls.webrtc" value="webrtc">WebRTC</el-radio-button>
                <el-radio-button v-if="previewStream.urls.flv" value="flv">FLV</el-radio-button>
                <el-radio-button v-if="previewStream.urls.hls" value="hls">HLS</el-radio-button>
              </el-radio-group>
            </div>
            <div class="flex items-center gap-2">
              <el-button size="small" type="danger" plain @click="stopPreview" :disabled="!previewStream.url">{{ t('pushStream.btnStop') }}</el-button>
              <el-button size="small" @click="copyPreviewUrl">{{ t('pushStream.btnCopyUrl') }}</el-button>
              <el-button size="small" @click="openPreviewUrl">{{ t('pushStream.btnOpenNewTab') }}</el-button>
            </div>
          </div>
          <JessibucaPlayer :video-url="previewStream.url" />
        </div>
        <div v-else class="text-slate-500 text-sm">{{ t('pushStream.noPreviewUrl') }}</div>
      </AppDialog>

      <AppDialog v-model="batchVisible" :title="t('pushStream.batchTitle')" size="medium">
        <el-form label-width="110px">
          <el-form-item :label="t('pushStream.formNames')" required>
            <el-input v-model="batchNames" type="textarea" :rows="8" :placeholder="t('pushStream.formNamesPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('pushStream.formEnabled')">
            <el-switch v-model="batchEnabled" />
          </el-form-item>
          <el-form-item :label="t('pushStream.formPushKey')">
            <el-switch v-model="batchPushKeyEnabled" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="batchVisible = false">{{ t('pushStream.btnCancel') }}</el-button>
          <el-button type="primary" @click="submitBatch" :loading="batchSubmitting">{{ t('pushStream.btnCreate') }}</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="importVisible" :title="t('pushStream.importTitle')" size="medium">
        <div class="text-sm mb-3" style="color: var(--el-text-color-secondary)">
          {{ t('pushStream.importHint') }}
        </div>
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".csv,.xls,.xlsx"
          drag
          :on-change="onImportFileChange"
          :on-remove="onImportFileRemove"
        >
          <div class="text-sm">{{ t('pushStream.importDrag') }}</div>
        </el-upload>
        <template #footer>
          <el-button @click="importVisible = false">{{ t('pushStream.btnCancel') }}</el-button>
          <el-button type="primary" @click="submitImport" :loading="importSubmitting">{{ t('pushStream.btnStartImport') }}</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadFiles } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import { getFriendlyError } from '../utils/errorMessage'
import { useRouter } from 'vue-router'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, StructuredEvent, PluginConfig } from '@/types/models'

// 推流通道行（/api/v1/push-channels 响应，按实际使用字段定义）
interface PushChannelRow {
  id: string
  name?: string
  stream_name?: string
  enabled?: boolean
  push_key_enabled?: boolean
  gb_enabled?: boolean
  gb_id?: string
  gb_name?: string
  [key: string]: unknown
}

const { t } = useI18n()
const loading = ref(false)
const streams = ref<StreamPush[]>([])
const channels = ref<StreamPush[]>([])
const activeTab = ref<'channels' | 'streams'>('channels')
const keyword = ref('')
const stopping = ref<Record<string, boolean>>({})
const playing = ref<Record<string, boolean>>({})
const dialogVisible = ref(false)
const editingId = ref('')
const saving = ref(false)
type PushChannelForm = {
  name: string
  stream_name: string
  enabled: boolean
  push_key_enabled: boolean
  gb_enabled: boolean
  gb_id: string
  gb_name: string
  gb_parent_gb_id: string
}

const form = ref<PushChannelForm>({
  name: '',
  stream_name: '',
  enabled: true,
  push_key_enabled: true,
  gb_enabled: false,
  gb_id: '',
  gb_name: '',
  gb_parent_gb_id: ''
})
const previewVisible = ref(false)
const previewMode = ref<'webrtc' | 'flv' | 'hls'>('webrtc')
const previewStream = ref<{ app: string; stream: string; url: string; urls: { webrtc: string; flv: string; hls: string } }>({
  app: 'live',
  stream: '',
  url: '',
  urls: { webrtc: '', flv: '', hls: '' }
})
const batchVisible = ref(false)
const batchSubmitting = ref(false)
const batchNames = ref('')
const batchEnabled = ref(true)
const batchPushKeyEnabled = ref(true)
const importVisible = ref(false)
const importSubmitting = ref(false)
const importFile = ref<File | null>(null)
const router = useRouter()

const goTvWall = () => {
  if (!router.hasRoute('TvWall')) {
    ElMessage.warning(t('pushStream.msgTvWallPluginRequired'))
    router.push('/plugins')
    return
  }
  router.push('/tv-wall')
}

const filteredStreams = computed(() => {
  const k = (keyword.value || '').trim().toLowerCase()
  if (!k) return streams.value
  return streams.value.filter((row: Record<string, unknown>) => {
    const app = String(row.app || '').toLowerCase()
    const stream = String(row.stream || '').toLowerCase()
    const origin = String(row.origin_url || row.originUrl || '').toLowerCase()
    return app.includes(k) || stream.includes(k) || origin.includes(k)
  })
})

const channelsPage = ref(1)
const channelsPageSize = ref(10)
const paginatedChannels = computed(() => {
  const start = (channelsPage.value - 1) * channelsPageSize.value
  const end = start + channelsPageSize.value
  return filteredChannels.value.slice(start, end)
})

const streamsPage = ref(1)
const streamsPageSize = ref(10)
const paginatedStreams = computed(() => {
  const start = (streamsPage.value - 1) * streamsPageSize.value
  const end = start + streamsPageSize.value
  return filteredStreams.value.slice(start, end)
})

watch(keyword, () => {
  channelsPage.value = 1
  streamsPage.value = 1
})

const normalizeStreamName = (row: Record<string, unknown>) => {
  const raw = String(row.stream_name || row.name || row.id || '').replace(/\s+/g, '_')
  const normalized = raw.split('').filter((ch) => /[0-9a-zA-Z_-]/.test(ch)).join('').toLowerCase()
  return normalized || String(row.id || '')
}

const proxyStreamSet = computed(() => {
  const set = new Set<string>()
  for (const s of streams.value || []) {
    if (s && s.app === 'live' && s.stream) set.add(String(s.stream))
  }
  return set
})

const isRunning = (row: Record<string, unknown>) => proxyStreamSet.value.has(normalizeStreamName(row))

const isRunningEffective = (row: Record<string, unknown>) => {
  const v = (row?.extra as Record<string, unknown> | undefined)?.['runtime.rtmp.is_running']
  if (typeof v === 'boolean') return v
  if (String(v || '') === 'true') return true
  if (String(v || '') === 'false') return false
  return isRunning(row)
}

const isUnhealthy = (row: Record<string, unknown>) => {
  const v = (row?.extra as Record<string, unknown> | undefined)?.['runtime.rtmp.unhealthy']
  if (typeof v === 'boolean') return v
  return String(v || '') === 'true'
}

const desiredState = (row: Record<string, unknown>) => {
  const s = String((row?.extra as Record<string, unknown> | undefined)?.['desired.state'] || '').trim().toLowerCase()
  return s === 'stopped' ? 'stopped' : 'running'
}

const desiredUpdating = ref<Record<string, boolean>>({})

const updateDesiredState = async (row: Record<string, unknown>, state: string) => {
  const id = String(row?.id || '')
  if (!id) return
  desiredUpdating.value[id] = true
  try {
    await api.post(`/api/v1/integrations/sources/${id}/actions/desired-state`, { state, enforce: false })
    ElMessage.success(t('pushStream.msgDesiredUpdated'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    desiredUpdating.value[id] = false
  }
}

const enforceStop = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  desiredUpdating.value[id] = true
  try {
    await api.post(`/api/v1/integrations/sources/${id}/actions/desired-state`, { state: 'stopped', enforce: true })
    ElMessage.success(t('pushStream.msgEnforceStopped'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    desiredUpdating.value[id] = false
  }
}

const filteredChannels = computed(() => {
  const k = (keyword.value || '').trim().toLowerCase()
  if (!k) return channels.value
  return channels.value.filter((row: Record<string, unknown>) => {
    const name = String(row.name || '').toLowerCase()
    const stream = String(row.stream_name || '').toLowerCase()
    return name.includes(k) || stream.includes(k)
  })
})

const refreshAll = async () => {
  loading.value = true
  try {
    const [streamRes, sourceRes] = await Promise.all([
      api.get('/api/v1/stream/list'),
      api.get('/api/v1/push-channels')
    ])
    streams.value = Array.isArray(streamRes.data) ? streamRes.data : []
    channels.value = Array.isArray(sourceRes.data) ? sourceRes.data : []
  } catch (e: unknown) {
    streams.value = []
    channels.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const stopStream = async (row: Record<string, unknown>) => {
  const key = `${row.app}:${row.stream}`
  try {
    await ElMessageBox.confirm(t('pushStream.confirmStopStream', { key }), t('pushStream.confirmStopStreamTitle'), { type: 'warning' })
  } catch {
    return
  }
  stopping.value[key] = true
  try {
    await api.post('/api/v1/stream/stop', { app: row.app, stream: row.stream })
    ElMessage.success(t('pushStream.msgStopSent'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    stopping.value[key] = false
  }
}

const openCreateDialog = () => {
  editingId.value = ''
  form.value = { name: '', stream_name: '', enabled: true, push_key_enabled: true, gb_enabled: false, gb_id: '', gb_name: '', gb_parent_gb_id: '' }
  dialogVisible.value = true
}

const openBatchDialog = () => {
  batchNames.value = ''
  batchEnabled.value = true
  batchPushKeyEnabled.value = true
  batchVisible.value = true
}

const openImportDialog = () => {
  importFile.value = null
  importVisible.value = true
}

const onImportFileChange = (uploadFile: UploadFile, _uploadFiles: UploadFiles) => {
  const raw = uploadFile?.raw
  importFile.value = raw instanceof File ? raw : null
}

const onImportFileRemove = () => {
  importFile.value = null
}

const openEditDialog = (row: PushChannelRow) => {
  editingId.value = row.id
  form.value = {
    name: row.name || '',
    stream_name: row.stream_name || '',
    enabled: row.enabled !== false,
    push_key_enabled: row.push_key_enabled === true,
    gb_enabled: row.gb_enabled === true,
    gb_id: row.gb_id || '',
    gb_name: row.gb_name || '',
    gb_parent_gb_id: ''
  }
  dialogVisible.value = true
}

const submitImport = async () => {
  if (!importFile.value) {
    ElMessage.warning(t('pushStream.msgSelectImportFile'))
    return
  }
  importSubmitting.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const res = await api.post('/api/v1/push-channels/import', fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    const created = Number(res.data?.created || 0)
    const updated = Number(res.data?.updated || 0)
    const total = Number(res.data?.total || 0)
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    if (items.length) {
      const lines = items.map((it: Record<string, unknown>) => `${it.name}\t${it.stream_name}\t${it.push_key || ''}`).join('\n')
      try {
        await navigator.clipboard.writeText(lines)
        ElMessage.success(t('pushStream.msgImportedWithKey', { created, updated, total }))
      } catch {
        await ElMessageBox.alert(lines, t('pushStream.importResultTitle', { created, updated, total }), { confirmButtonText: t('pushStream.btnOk') })
      }
    } else {
      ElMessage.success(t('pushStream.msgImportedSimple', { created, updated, total }))
    }
    importVisible.value = false
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    importSubmitting.value = false
  }
}

const submitBatch = async () => {
  const names = String(batchNames.value || '')
    .split('\n')
    .map((s) => s.trim())
    .filter((s) => !!s)
  if (!names.length) {
    ElMessage.warning(t('pushStream.msgNamesRequired'))
    return
  }
  batchSubmitting.value = true
  try {
    const res = await api.post('/api/v1/push-channels/batch', {
      items: names.map((name) => ({ name })),
      enabled: batchEnabled.value !== false,
      push_key_enabled: batchPushKeyEnabled.value === true
    })
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    if (items.length) {
      const lines = items
        .map((it: Record<string, unknown>) => `${it.name}\t${it.stream_name}\t${it.push_key || ''}`)
        .join('\n')
      try {
        await navigator.clipboard.writeText(lines)
        ElMessage.success(t('pushStream.msgBatchCreatedWithKey'))
      } catch {
        await ElMessageBox.alert(lines, t('pushStream.batchResultTitle'), { confirmButtonText: t('pushStream.btnOk') })
      }
    } else {
      ElMessage.success(t('pushStream.msgBatchCreatedSimple'))
    }
    batchVisible.value = false
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    batchSubmitting.value = false
  }
}

const save = async () => {
  const name = String(form.value.name || '').trim()
  if (!name) {
    ElMessage.warning(t('pushStream.msgNameRequired'))
    return
  }
  if (form.value.gb_enabled && !String(form.value.gb_id || '').trim()) {
    ElMessage.warning(t('pushStream.msgGbIdRequired'))
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/v1/push-channels/${editingId.value}`, {
        name,
        stream_name: String(form.value.stream_name || '').trim(),
        enabled: !!form.value.enabled,
        push_key_enabled: form.value.push_key_enabled === true,
        gb_enabled: form.value.gb_enabled === true,
        gb_id: String(form.value.gb_id || '').trim(),
        gb_name: String(form.value.gb_name || '').trim(),
        gb_parent_gb_id: String(form.value.gb_parent_gb_id || '').trim()
      })
    } else {
      const res = await api.post('/api/v1/push-channels', {
        name,
        stream_name: String(form.value.stream_name || '').trim(),
        enabled: !!form.value.enabled,
        push_key_enabled: form.value.push_key_enabled === true,
        gb_enabled: form.value.gb_enabled === true,
        gb_id: String(form.value.gb_id || '').trim(),
        gb_name: String(form.value.gb_name || '').trim(),
        gb_parent_gb_id: String(form.value.gb_parent_gb_id || '').trim()
      })
      const pushKey = String(res.data?.push_key || '')
      if (pushKey) {
        try {
          await navigator.clipboard.writeText(pushKey)
          ElMessage.success(t('pushStream.msgCreatedWithKey'))
        } catch {
          await ElMessageBox.alert(pushKey, t('pushStream.pushKeyTitle'), { confirmButtonText: t('pushStream.btnOk') })
        }
      }
    }
    dialogVisible.value = false
    ElMessage.success(editingId.value ? t('pushStream.msgUpdated') : t('pushStream.msgCreated'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    saving.value = false
  }
}

const remove = async (id: string) => {
  try {
    await ElMessageBox.confirm(t('pushStream.msgConfirmDelete'), t('pushStream.msgConfirmDeleteTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/push-channels/${id}`)
    ElMessage.success(t('pushStream.msgDeleted'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const showPushUrl = async (id: string) => {
  try {
    const res = await api.get(`/api/v1/integrations/sources/${id}/push-url`)
    const pushUrl = String(res.data?.push_url || '')
    if (!pushUrl) {
      ElMessage.warning(t('pushStream.msgNoPushUrl'))
      return
    }
    try {
      await navigator.clipboard.writeText(pushUrl)
      ElMessage.success(t('pushStream.msgUrlCopied'))
    } catch {
      await ElMessageBox.alert(pushUrl, t('pushStream.msgPushUrlTitle'), { confirmButtonText: t('pushStream.btnOk') })
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const rotatePushKey = async (id: string) => {
  if (!id) return
  try {
    await ElMessageBox.confirm(t('pushStream.msgConfirmRotateKey'), t('pushStream.msgConfirmRotateKeyTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await api.post(`/api/v1/push-channels/${id}/rotate-push-key`)
    const pushKey = String(res.data?.push_key || '')
    if (!pushKey) {
      ElMessage.success(t('pushStream.msgKeyRotated'))
      await refreshAll()
      return
    }
    try {
      await navigator.clipboard.writeText(pushKey)
      ElMessage.success(t('pushStream.msgKeyRotatedWithNew'))
    } catch {
      await ElMessageBox.alert(pushKey, t('pushStream.newPushKeyTitle'), { confirmButtonText: t('pushStream.btnOk') })
    }
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const preview = async (id: string) => {
  playing.value[id] = true
  try {
    const res = await api.post(`/api/v1/integrations/sources/${id}/play`)
    const urls = {
      webrtc: String(res.data?.webrtc || ''),
      flv: String(res.data?.flv || ''),
      hls: String(res.data?.hls || '')
    }
    const pick = urls.webrtc || urls.flv || urls.hls
    previewMode.value = urls.webrtc ? 'webrtc' : urls.flv ? 'flv' : 'hls'
    previewStream.value = { app: res.data?.app || 'live', stream: res.data?.stream || '', url: pick, urls }
    previewVisible.value = true
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    playing.value[id] = false
  }
}

const closePreview = async () => {
  const cur = previewStream.value
  previewVisible.value = false
  if (cur.stream) {
    try {
      await api.post('/api/v1/stream/stop', { app: cur.app, stream: cur.stream })
    } catch { /* cleanup: ignore */ }
  }
  previewStream.value = { app: 'live', stream: '', url: '', urls: { webrtc: '', flv: '', hls: '' } }
  await refreshAll()
}

const stopPreview = async () => {
  const cur = previewStream.value
  if (cur.stream) {
    try {
      await api.post('/api/v1/stream/stop', { app: cur.app, stream: cur.stream })
    } catch { /* cleanup: ignore */ }
  }
  previewStream.value = { app: cur.app || 'live', stream: '', url: '', urls: { webrtc: '', flv: '', hls: '' } }
  ElMessage.success(t('pushStream.msgPreviewStopped'))
  await refreshAll()
}

watch(
  () => previewMode.value,
  () => {
    const u = previewStream.value.urls
    const next =
      previewMode.value === 'webrtc'
        ? u.webrtc
        : previewMode.value === 'flv'
          ? u.flv
          : u.hls
    if (next) previewStream.value.url = next
  }
)

const copyPreviewUrl = async () => {
  const url = previewStream.value.url
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success(t('pushStream.msgPreviewUrlCopied'))
  } catch {
    ElMessage.error(t('pushStream.msgCopyFailed'))
  }
}

const openPreviewUrl = () => {
  const url = previewStream.value.url
  if (!url) return
  window.open(url, '_blank')
}

const stopChannel = async (row: Record<string, unknown>) => {
  const stream = normalizeStreamName(row)
  try {
    await ElMessageBox.confirm(t('pushStream.msgConfirmStopChannel', { stream }), t('pushStream.msgConfirmStopChannelTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.post('/api/v1/stream/stop', { app: 'live', stream })
    ElMessage.success(t('pushStream.msgStopSentCmd'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const saveToGb = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '').trim()
  if (!id) return
  try {
    const gbId = String(row.gb_id || '').trim()
    const gbName = String(row.gb_name || row.name || '').trim()
    if (!gbId) {
      ElMessage.warning(t('pushStream.msgEditBeforeSaveToGb'))
      return
    }
    await ElMessageBox.confirm(t('pushStream.msgConfirmSaveToGb', { name: row.name || id, gbId }), t('pushStream.msgConfirmSaveToGbTitle'), { type: 'info' })
  } catch { return }
  try {
    await api.post(`/api/v1/push-channels/${id}/save_to_gb`, {
      gb_id: String(row.gb_id || '').trim(),
      gb_name: String(row.gb_name || row.name || '').trim(),
      gb_parent_gb_id: String(row.gb_parent_gb_id || '').trim()
    })
    ElMessage.success(t('pushStream.msgSaveToGb'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const removeFromGb = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '').trim()
  if (!id) return
  try {
    await ElMessageBox.confirm(t('pushStream.msgConfirmRemoveFromGb', { name: row.name || id }), t('pushStream.msgConfirmRemoveFromGbTitle'), { type: 'warning' })
  } catch { return }
  try {
    await api.post(`/api/v1/push-channels/${id}/remove_from_gb`)
    ElMessage.success(t('pushStream.msgRemoveFromGb'))
    await refreshAll()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.streams-table :deep(.el-table__cell) {
  vertical-align: middle;
}
</style>
