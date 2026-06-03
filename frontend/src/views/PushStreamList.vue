<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="推流列表" description="统一管理推流通道（RTMP）与实时流会话">
          <template #actions>
            <el-input v-model="keyword" placeholder="搜索名称、流名或会话信息" clearable style="width: 260px" class="mr-2" />
            <el-button v-if="activeTab === 'channels'" type="primary" @click="openCreateDialog">创建推流通道</el-button>
            <el-button v-if="activeTab === 'channels'" @click="openBatchDialog">批量创建</el-button>
            <el-button v-if="activeTab === 'channels'" @click="openImportDialog">导入</el-button>
            <el-button @click="refreshAll" :loading="loading">刷新</el-button>
          </template>
        </PageHeader>
      </template>

      <el-tabs v-model="activeTab" class="mb-2">
        <el-tab-pane label="推流通道" name="channels" />
        <el-tab-pane label="流会话" name="streams" />
      </el-tabs>

      <TableCard v-if="activeTab === 'channels'">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">推流通道（RTMP）</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ filteredChannels.length }} 条</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && channels.length === 0" :rows="6" />
        <template v-else-if="filteredChannels.length === 0">
          <EmptyStateWithAction description="暂无推流通道。创建后可获取 RTMP 推流地址并进行预览/停流。">
            <template #action>
              <el-button type="primary" @click="openCreateDialog">创建推流通道</el-button>
            </template>
          </EmptyStateWithAction>
        </template>

        <el-table v-else :data="paginatedChannels" border size="small" :empty-text="'暂无推流通道'">
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column label="流名" min-width="220">
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ normalizeStreamName(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="推流密钥" width="160" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.push_key_enabled" type="success" size="small">{{ row.push_key_hint || '已启用' }}</el-tag>
              <el-tag v-else type="info" size="small">未启用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="入国标" width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="space-y-1">
                <el-tag v-if="row.gb_enabled" type="success" size="small">已启用</el-tag>
                <el-tag v-else type="info" size="small">未启用</el-tag>
                <div v-if="row.gb_enabled" class="text-xs font-mono" style="color: var(--el-text-color-secondary)">
                  {{ row.gb_id || '-' }} {{ row.gb_name ? `(${row.gb_name})` : '' }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag v-if="row?.extra?.['runtime.last_play_error']" type="danger" size="small">异常</el-tag>
              <el-tag v-else-if="isUnhealthy(row)" type="warning" size="small">异常</el-tag>
              <el-tag v-else :type="isRunningEffective(row) ? 'success' : 'info'" size="small">
                {{ isRunningEffective(row) ? '运行中' : '未运行' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="期望" width="150" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="desiredState(row)"
                size="small"
                style="width: 120px"
                @change="(val: unknown) => updateDesiredState(row, String(val || ''))"
              >
                <el-option label="运行" value="running" />
                <el-option label="停止" value="stopped" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="最近播放" width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="text-xs" style="color: var(--el-text-color-secondary)">
                {{ row?.extra?.['runtime.last_play_at'] || '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="健康" width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="space-y-1">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">
                  {{ row?.extra?.['runtime.rtmp.last_seen_at'] || '—' }}
                </div>
                <div v-if="row?.extra?.['runtime.rtmp.bytes_speed'] != null" class="text-xs" style="color: var(--el-text-color-secondary)">
                  {{ row?.extra?.['runtime.rtmp.bytes_speed'] }} B/s；观看 {{ row?.extra?.['runtime.rtmp.reader_count'] || 0 }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="540" align="center">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-2 justify-center">
                <el-button size="small" type="primary" plain @click="openEditDialog(row)">编辑</el-button>
                <el-button size="small" @click="showPushUrl(row.id)">推流地址</el-button>
                <el-button size="small" @click="rotatePushKey(row.id)">重置密钥</el-button>
                <el-button size="small" type="success" plain @click="preview(row.id)" :loading="playing[row.id]">预览</el-button>
                <el-button v-if="!row.gb_enabled" size="small" type="warning" plain @click="saveToGb(row)">保存到国标</el-button>
                <el-button v-if="row.gb_enabled" size="small" type="info" plain @click="removeFromGb(row)">从国标移除</el-button>
                <el-button v-if="desiredState(row) === 'stopped' && isRunningEffective(row)" size="small" type="warning" plain @click="enforceStop(row)" :loading="desiredUpdating[row.id]">纠偏停流</el-button>
                <el-button v-else-if="isRunningEffective(row)" size="small" type="warning" plain @click="stopChannel(row)">停流</el-button>
                <el-button size="small" type="danger" plain @click="remove(row.id)">删除</el-button>
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
            prev-text="上一页"
            next-text="下一页"
            size="small"
          />
        </div>
      </TableCard>

      <TableCard v-else>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">流会话</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ filteredStreams.length }} 条</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && streams.length === 0" :rows="6" />
        <template v-else-if="filteredStreams.length === 0">
          <EmptyStateWithAction description="暂无流会话。可在设备预览、电视墙或接入源播放后查看。">
            <template #action>
              <el-button type="primary" @click="$router.push('/devices')">前往设备列表</el-button>
              <el-button @click="goTvWall">前往电视墙</el-button>
            </template>
          </EmptyStateWithAction>
        </template>

        <el-table v-else :data="paginatedStreams" border size="small" :empty-text="'暂无流会话'" class="streams-table">
          <el-table-column prop="app" label="应用" width="90" />
          <el-table-column label="流ID" min-width="220">
            <template #default="{ row }">
              <div class="flex items-center gap-2">
                <el-tag v-if="row.is_proxy" size="small" type="warning" effect="dark">代理</el-tag>
                <el-tag v-else size="small" type="success" effect="dark">国标</el-tag>
                <span class="font-mono text-xs">{{ row.stream }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="origin_url" label="源地址" min-width="260" show-overflow-tooltip />
          <el-table-column prop="reader_count" label="观看数" width="90" />
          <el-table-column prop="alive_second" label="存活(秒)" width="110" />
          <el-table-column prop="bytes_speed" label="字节/秒" width="120" />
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" plain @click="stopStream(row)" :loading="stopping[`${row.app}:${row.stream}`]">
                停流
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
            prev-text="上一页"
            next-text="下一页"
            size="small"
          />
        </div>
      </TableCard>

      <AppDialog v-model="dialogVisible" :title="editingId ? '编辑推流通道' : '创建推流通道'" size="medium">
        <el-form label-width="90px">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" placeholder="例如：NVR推流 / 车载推流 / 第三方编码器" />
          </el-form-item>
          <el-form-item label="流名">
            <el-input v-model="form.stream_name" placeholder="可选；留空则由名称推导" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="推流密钥">
            <el-switch v-model="form.push_key_enabled" />
          </el-form-item>
          <el-form-item label="入国标">
            <el-switch v-model="form.gb_enabled" />
          </el-form-item>
          <template v-if="form.gb_enabled">
            <el-form-item label="国标ID" required>
              <el-input v-model="form.gb_id" placeholder="20位国标ID" />
            </el-form-item>
            <el-form-item label="国标名称">
              <el-input v-model="form.gb_name" placeholder="可选；默认用名称" />
            </el-form-item>
            <el-form-item label="父目录ID">
              <el-input v-model="form.gb_parent_gb_id" placeholder="可选；默认走资源树当前挂载" />
            </el-form-item>
          </template>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="save" :loading="saving">保存</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="previewVisible" title="预览" size="large" @closed="closePreview">
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
              <el-button size="small" type="danger" plain @click="stopPreview" :disabled="!previewStream.url">停止</el-button>
              <el-button size="small" @click="copyPreviewUrl">复制地址</el-button>
              <el-button size="small" @click="openPreviewUrl">新标签打开</el-button>
            </div>
          </div>
          <JessibucaPlayer :video-url="previewStream.url" />
        </div>
        <div v-else class="text-slate-500 text-sm">暂无预览地址</div>
      </AppDialog>

      <AppDialog v-model="batchVisible" title="批量创建推流通道" size="medium">
        <el-form label-width="110px">
          <el-form-item label="每行一个名称" required>
            <el-input v-model="batchNames" type="textarea" :rows="8" placeholder="例如：\n编码器1\n编码器2\n车载推流A" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="batchEnabled" />
          </el-form-item>
          <el-form-item label="推流密钥">
            <el-switch v-model="batchPushKeyEnabled" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="batchVisible = false">取消</el-button>
          <el-button type="primary" @click="submitBatch" :loading="batchSubmitting">创建</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="importVisible" title="导入推流通道" size="medium">
        <div class="text-sm mb-3" style="color: var(--el-text-color-secondary)">
          支持 csv/xls/xlsx。表头：name,stream_name,enabled,push_key_enabled,gb_enabled,gb_id,gb_name,gb_parent_gb_id
        </div>
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".csv,.xls,.xlsx"
          drag
          :on-change="onImportFileChange"
          :on-remove="onImportFileRemove"
        >
          <div class="text-sm">将文件拖到此处，或点击选择文件</div>
        </el-upload>
        <template #footer>
          <el-button @click="importVisible = false">取消</el-button>
          <el-button type="primary" @click="submitImport" :loading="importSubmitting">开始导入</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import { getFriendlyError } from '../utils/errorMessage'
import { useRouter } from 'vue-router'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

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
    ElMessage.warning('电视墙功能需购买并安装插件后才能使用')
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
  const v = row?.extra?.['runtime.rtmp.is_running']
  if (typeof v === 'boolean') return v
  if (String(v || '') === 'true') return true
  if (String(v || '') === 'false') return false
  return isRunning(row)
}

const isUnhealthy = (row: Record<string, unknown>) => {
  const v = row?.extra?.['runtime.rtmp.unhealthy']
  if (typeof v === 'boolean') return v
  return String(v || '') === 'true'
}

const desiredState = (row: Record<string, unknown>) => {
  const s = String(row?.extra?.['desired.state'] || '').trim().toLowerCase()
  return s === 'stopped' ? 'stopped' : 'running'
}

const desiredUpdating = ref<Record<string, boolean>>({})

const updateDesiredState = async (row: Record<string, unknown>, state: string) => {
  const id = String(row?.id || '')
  if (!id) return
  desiredUpdating.value[id] = true
  try {
    await api.post(`/api/v1/integrations/sources/${id}/actions/desired-state`, { state, enforce: false })
    ElMessage.success('已更新期望状态')
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
    ElMessage.success('已执行纠偏停流')
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
    await ElMessageBox.confirm(`确认停止流 ${key} 吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  stopping.value[key] = true
  try {
    await api.post('/api/v1/stream/stop', { app: row.app, stream: row.stream })
    ElMessage.success('已发送停流')
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

const onImportFileChange = (uploadFile: File) => {
  const raw = uploadFile?.raw
  importFile.value = raw instanceof File ? raw : null
}

const onImportFileRemove = () => {
  importFile.value = null
}

const openEditDialog = (row: Record<string, unknown>) => {
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
    ElMessage.warning('请选择导入文件')
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
        ElMessage.success(`已导入：新建${created}，更新${updated}（共${total}行）；新密钥已复制`)
      } catch {
        await ElMessageBox.alert(lines, `导入结果（新建${created}，更新${updated}，共${total}行）`, { confirmButtonText: '确定' })
      }
    } else {
      ElMessage.success(`已导入：新建${created}，更新${updated}（共${total}行）`)
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
    ElMessage.warning('请填写名称列表')
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
        ElMessage.success('已批量创建；结果已复制（名称/流名/密钥）')
      } catch {
        await ElMessageBox.alert(lines, '批量创建结果（名称/流名/密钥）', { confirmButtonText: '确定' })
      }
    } else {
      ElMessage.success('已批量创建')
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
    ElMessage.warning('请输入名称')
    return
  }
  if (form.value.gb_enabled && !String(form.value.gb_id || '').trim()) {
    ElMessage.warning('启用入国标时请填写国标ID')
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
          ElMessage.success('已创建；推流密钥已复制（仅展示一次）')
        } catch {
          await ElMessageBox.alert(pushKey, '推流密钥（仅展示一次）', { confirmButtonText: '确定' })
        }
      }
    }
    dialogVisible.value = false
    ElMessage.success(editingId.value ? '推流通道已更新' : '推流通道已创建')
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
    await ElMessageBox.confirm('删除后不可恢复，是否继续？', '删除推流通道', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/push-channels/${id}`)
    ElMessage.success('推流通道已删除')
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
      ElMessage.warning('未获取到推流地址')
      return
    }
    try {
      await navigator.clipboard.writeText(pushUrl)
      ElMessage.success('推流地址已复制')
    } catch {
      await ElMessageBox.alert(pushUrl, '推流地址', { confirmButtonText: '确定' })
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const rotatePushKey = async (id: string) => {
  if (!id) return
  try {
    await ElMessageBox.confirm('重置后旧密钥将立即失效，是否继续？', '重置推流密钥', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await api.post(`/api/v1/push-channels/${id}/rotate-push-key`)
    const pushKey = String(res.data?.push_key || '')
    if (!pushKey) {
      ElMessage.success('推流密钥已重置')
      await refreshAll()
      return
    }
    try {
      await navigator.clipboard.writeText(pushKey)
      ElMessage.success('已重置；新密钥已复制（仅展示一次）')
    } catch {
      await ElMessageBox.alert(pushKey, '新推流密钥（仅展示一次）', { confirmButtonText: '确定' })
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
  ElMessage.success('已停止预览')
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
    ElMessage.success('预览地址已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动复制地址')
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
    await ElMessageBox.confirm(`确认停止推流 live/${stream} 吗？停止后需重新推流才能恢复。`, '停止推流', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.post('/api/v1/stream/stop', { app: 'live', stream })
    ElMessage.success('已发送停流指令')
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
      ElMessage.warning('请先编辑推流通道，填写国标ID后再保存到国标')
      return
    }
    await ElMessageBox.confirm(`确定将推流通道「${row.name || id}」保存到国标资源树？国标ID：${gbId}`, '保存到国标', { type: 'info' })
  } catch { return }
  try {
    await api.post(`/api/v1/push-channels/${id}/save_to_gb`, {
      gb_id: String(row.gb_id || '').trim(),
      gb_name: String(row.gb_name || row.name || '').trim(),
      gb_parent_gb_id: String(row.gb_parent_gb_id || '').trim()
    })
    ElMessage.success('已保存到国标')
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
    await ElMessageBox.confirm(`确定将推流通道「${row.name || id}」从国标资源树移除？`, '从国标移除', { type: 'warning' })
  } catch { return }
  try {
    await api.post(`/api/v1/push-channels/${id}/remove_from_gb`)
    ElMessage.success('已从国标移除')
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
