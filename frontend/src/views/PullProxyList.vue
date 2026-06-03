<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="拉流代理" description="管理 RTSP/ONVIF/SDK 接入源并快速预览">
          <template #actions>
            <el-input v-model="keyword" placeholder="搜索名称/地址/流名" clearable style="width: 240px" class="mr-2" />
            <el-select v-model="protocolFilter" placeholder="全部协议" clearable style="width: 140px" class="mr-2">
              <el-option label="RTSP" value="RTSP" />
              <el-option label="ONVIF" value="ONVIF" />
              <el-option label="SDK" value="SDK" />
              <el-option label="RTMP" value="RTMP" />
              <el-option label="GB28181" value="GB28181" />
            </el-select>
            <el-switch v-model="useProxyCompat" active-text="兼容API" inactive-text="原生API" class="mr-2" />
            <el-button type="primary" @click="openDialog()">新增接入源</el-button>
            <el-button @click="loadSources" :loading="loading">刷新</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">接入源列表</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ filteredSources.length }} 条</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && sources.length === 0" :rows="6" />
        <template v-else-if="filteredSources.length === 0">
          <EmptyStateWithAction description="暂无接入源。可在此新增 RTSP/ONVIF/SDK/RTMP 接入源。">
            <template #action>
              <el-button type="primary" @click="openDialog()">新增接入源</el-button>
            </template>
          </EmptyStateWithAction>
        </template>

        <el-table v-else :data="paginatedSources" border size="small" class="sources-table" :empty-text="'暂无接入源'">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="protocol" label="协议" width="100" />
          <el-table-column label="状态" width="120" align="center">
            <template #default="{ row }">
              <el-tooltip v-if="row?.extra?.['runtime.last_play_error']" :content="row.extra['runtime.last_play_error']" placement="top">
                <el-tag type="danger" size="small">异常</el-tag>
              </el-tooltip>
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
          <el-table-column label="地址" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ formatAddress(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="stream_name" label="流名称" min-width="140" />
          <el-table-column label="最近播放" width="170" show-overflow-tooltip>
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
                  {{ row?.extra?.['runtime.proxy.last_seen_at'] || '—' }}
                </div>
                <div v-if="row?.extra?.['runtime.proxy.bytes_speed'] != null" class="text-xs" style="color: var(--el-text-color-secondary)">
                  {{ row?.extra?.['runtime.proxy.bytes_speed'] }} B/s；观看 {{ row?.extra?.['runtime.proxy.reader_count'] || 0 }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="100" align="center">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled !== false" @change="(v: unknown) => setEnabled(row, !!v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" align="center">
            <template #default="{ row }">
              <div class="table-action-inline justify-center">
                <el-button size="small" plain @click="openDialog(row)">编辑</el-button>
                <el-button size="small" type="primary" plain @click="preview(row.id)" :loading="playing[row.id]">预览</el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => handleSourceMoreCommand(row, cmd)">
                  <el-button size="small" plain class="table-action-more">更多</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="test">测试</el-dropdown-item>
                      <el-dropdown-item command="start" :disabled="String(row.protocol || '').toUpperCase() === 'RTMP'">启动</el-dropdown-item>
                      <el-dropdown-item v-if="isRunningEffective(row)" command="stop">停止</el-dropdown-item>
                      <el-dropdown-item v-if="String(row.protocol || '').toUpperCase() === 'RTMP'" command="pushUrl">推流地址</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="filteredSources.length > 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="filteredSources.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            prev-text="上一页"
            next-text="下一页"
            size="small"
          />
        </div>
      </TableCard>

      <AppDialog v-model="dialogVisible" :title="editingId ? '编辑接入源' : '新增接入源'" size="medium">
        <el-form :model="form" ref="formRef" :rules="rules" label-width="110px">
          <el-form-item label="名称" prop="name">
            <el-input v-model="form.name" placeholder="请输入接入源名称，便于识别与管理" />
          </el-form-item>
          <el-form-item label="协议" prop="protocol">
            <el-select v-model="form.protocol" style="width: 100%">
              <el-option label="RTSP" value="RTSP" />
              <el-option label="ONVIF" value="ONVIF" />
              <el-option label="SDK" value="SDK" />
              <el-option label="RTMP" value="RTMP" />
              <el-option label="GB28181" value="GB28181" />
            </el-select>
          </el-form-item>
          <el-form-item label="主机" prop="host">
            <el-input v-model="form.host" placeholder="请输入设备 IP 或域名" />
          </el-form-item>
          <el-form-item label="端口" prop="port">
            <el-input-number v-model="form.port" :min="0" :max="65535" style="width: 100%" />
          </el-form-item>
          <el-form-item label="用户名">
            <el-input v-model="form.username" placeholder="可选，设备启用鉴权时请填写" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" show-password :placeholder="t('stream.newFillEditLeaveEmpty')" />  <!-- FIXED: P3 i18n -->
          </el-form-item>
          <el-form-item label="路径">
            <el-input v-model="form.path" placeholder="例如 Streaming/Channels/101 或 live/test" />
          </el-form-item>
          <el-form-item label="流名称">
            <el-input v-model="form.stream_name" placeholder="可选，不填写则自动生成流名称" />
          </el-form-item>
          <el-form-item label="接入国标">
            <el-switch v-model="form.gb_enabled" />
          </el-form-item>
          <el-form-item v-if="form.gb_enabled" label="国标ID" prop="gb_id">
            <el-input v-model="form.gb_id" placeholder="请输入 20 位国标编码" />
          </el-form-item>
          <el-form-item v-if="form.gb_enabled" label="国标名称">
            <el-input v-model="form.gb_name" placeholder="可选，默认使用接入源名称" />
          </el-form-item>
          <el-form-item v-if="form.gb_enabled" label="父级国标ID">
            <el-input v-model="form.gb_parent_gb_id" placeholder="可选，填写后挂载到对应父节点" />
          </el-form-item>
          <el-form-item label="FFmpeg 模板">
            <el-select v-model="ffmpegCmdKey" clearable filterable placeholder="可选，用于转码、转封装或自定义拉流参数" style="width: 100%">
              <el-option v-for="c in ffmpegCmds" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="扩展参数">
            <el-input v-model="extraJson" type="textarea" :rows="4" placeholder='JSON 格式，例如 {"transport":"tcp"}' />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="save" :loading="saving">保存</el-button>
        </template>
      </AppDialog>

      <StreamPlayerDialog
        v-model="previewVisible"
        v-model:mode="previewMode"
        :title="'预览'"
        :urls="previewStream.urls"
        :play-url="previewStream.url"
        @stop="stopPreview"
        @close="closePreview"
      />
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import StreamPlayerDialog from '../components/StreamPlayerDialog.vue'
import { getFriendlyError } from '../utils/errorMessage'
import AppDialog from '../components/common/AppDialog.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'
import { useI18n } from 'vue-i18n'  // FIXED: P3 i18n

const { t } = useI18n()  // FIXED: P3 i18n

const loading = ref(false)
const sources = ref<StreamProxy[]>([])
const streams = ref<StreamProxy[]>([])
const keyword = ref('')
const protocolFilter = ref<string>('')
const useProxyCompat = ref(false)
const testing = ref<Record<string, boolean>>({})
const playing = ref<Record<string, boolean>>({})
const starting = ref<Record<string, boolean>>({})
const stopping = ref<Record<string, boolean>>({})
const enabling = ref<Record<string, boolean>>({})

const dialogVisible = ref(false)
const editingId = ref('')
const saving = ref(false)
const formRef = ref()
const validatePort = (_rule: Record<string, unknown>, value: number, callback: (...args: unknown[]) => void) => {
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    callback(new Error('请输入 1-65535 之间的端口号'))
    return
  }
  callback()
}
const validateGbId = (_rule: Record<string, unknown>, value: string, callback: (...args: unknown[]) => void) => {
  if (!form.value.gb_enabled) {
    callback()
    return
  }
  const gbId = String(value || '').trim()
  if (!gbId) {
    callback(new Error('已开启国标接入，请填写国标 ID'))
    return
  }
  if (gbId.length !== 20) {
    callback(new Error('国标 ID 长度应为 20 位'))
    return
  }
  callback()
}
const rules = {
  name: [{ required: true, message: '请输入接入源名称', trigger: 'blur' }],
  protocol: [{ required: true, message: '请选择接入协议', trigger: 'change' }],
  host: [{ required: true, message: '请输入主机地址', trigger: 'blur' }],
  port: [{ validator: validatePort, trigger: ['blur', 'change'] }],
  gb_id: [{ validator: validateGbId, trigger: ['blur', 'change'] }]
}
type PullProxyForm = {
  name: string
  protocol: string
  host: string
  port: number
  username: string
  password: string
  path: string
  stream_name: string
  enabled: boolean
  gb_enabled: boolean
  gb_id: string
  gb_name: string
  gb_parent_gb_id: string
  extra: Record<string, unknown>
}

const form = ref<PullProxyForm>({
  name: '',
  protocol: 'RTSP',
  host: '',
  port: 554,
  username: '',
  password: '',
  path: '',
  stream_name: '',
  enabled: true,
  gb_enabled: false,
  gb_id: '',
  gb_name: '',
  gb_parent_gb_id: '',
  extra: {}
})
const extraJson = ref('{}')
const ffmpegCmds = ref<StreamProxy[]>([])
const ffmpegCmdKey = ref<string>('')

const previewVisible = ref(false)
const previewMode = ref<'webrtc' | 'flv' | 'hls' | 'raw'>('webrtc')
const previewStream = ref<{ app: string; stream: string; url: string; urls: { webrtc: string; flv: string; hls: string; raw?: string } }>({
  app: 'live',
  stream: '',
  url: '',
  urls: { webrtc: '', flv: '', hls: '' }
})

const filteredSources = computed(() => {
  const k = (keyword.value || '').trim().toLowerCase()
  const p = (protocolFilter.value || '').trim().toUpperCase()
  return (sources.value || []).filter((row: Record<string, unknown>) => {
    const protocol = String(row.protocol || '').toUpperCase()
    if (p && protocol !== p) return false
    if (!k) return true
    const name = String(row.name || '').toLowerCase()
    const host = String(row.host || '').toLowerCase()
    const path = String(row.path || '').toLowerCase()
    const stream = String(row.stream_name || '').toLowerCase()
    return name.includes(k) || host.includes(k) || path.includes(k) || stream.includes(k)
  })
})

const page = ref(1)
const pageSize = ref(10)
const paginatedSources = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredSources.value.slice(start, end)
})

// reset page when filter changes
watch([keyword, protocolFilter], () => {
  page.value = 1
})

const normalizeStreamName = (row: Record<string, unknown>) => {
  const raw = String(row.stream_name || row.name || row.id || '').replace(/\s+/g, '_')
  const normalized = raw.split('').filter((ch) => /[0-9a-zA-Z_-]/.test(ch)).join('').toLowerCase()
  return normalized || String(row.id || '')
}

const proxyStreamSet = computed(() => {
  const set = new Set<string>()
  for (const s of streams.value || []) {
    if (s && s.is_proxy && s.app === 'live' && s.stream) {
      set.add(String(s.stream))
    }
  }
  return set
})

const isRunning = (row: Record<string, unknown>) => proxyStreamSet.value.has(normalizeStreamName(row))

const isRunningEffective = (row: Record<string, unknown>) => {
  const v = row?.extra?.['runtime.proxy.is_running']
  if (typeof v === 'boolean') return v
  if (String(v || '') === 'true') return true
  if (String(v || '') === 'false') return false
  return isRunning(row)
}

const isUnhealthy = (row: Record<string, unknown>) => {
  const v = row?.extra?.['runtime.proxy.unhealthy']
  if (typeof v === 'boolean') return v
  return String(v || '') === 'true'
}

const desiredState = (row: Record<string, unknown>) => {
  const s = String(row?.extra?.['desired.state'] || '').trim().toLowerCase()
  return s === 'stopped' ? 'stopped' : 'running'
}

const updateDesiredState = async (row: Record<string, unknown>, state: string) => {
  const id = String(row?.id || '')
  if (!id) return
  enabling.value[id] = true
  try {
    await api.post(`/api/v1/integrations/sources/${id}/actions/desired-state`, { state, enforce: false })
    ElMessage.success('已更新期望状态')
    await loadSources()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    enabling.value[id] = false
  }
}

const startProxy = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  starting.value[id] = true
  try {
    if (useProxyCompat.value) {
      await api.post(`/api/v1/proxy/start`, { id })
    } else {
      await api.post(`/api/v1/integrations/sources/${id}/actions/desired-state`, { state: 'running', enforce: true })
    }
    ElMessage.success('已触发启动')
    await loadSources()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    starting.value[id] = false
  }
}

const formatAddress = (row: Record<string, unknown>) => {
  const host = String(row.host || '').trim()
  const port = row.port ?? ''
  const path = String(row.path || '').trim()
  if (!host) return '—'
  if (!path) return `${host}:${port}`
  return `${host}:${port}/${path.replace(/^\/+/, '')}`
}

const loadSources = async () => {
  loading.value = true
  try {
    const [srcRes, streamRes] = await Promise.all([
      api.get(useProxyCompat.value ? '/api/v1/proxy/list' : '/api/v1/integrations/sources'),
      api.get('/api/v1/stream/list')
    ])
    sources.value = Array.isArray(srcRes.data) ? srcRes.data : []
    streams.value = Array.isArray(streamRes.data) ? streamRes.data : []
  } catch (e: unknown) {
    sources.value = []
    streams.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const loadFfmpegCmds = async () => {
  try {
    const res = await api.get(useProxyCompat.value ? '/api/v1/proxy/ffmpeg_cmd/list' : '/api/v1/integrations/ffmpeg_cmd/list')
    ffmpegCmds.value = Array.isArray(res.data) ? res.data : []
  } catch {
    ffmpegCmds.value = []
  }
}

const openDialog = (row?: Record<string, unknown>) => {
  editingId.value = row?.id || ''
  form.value = row ? {
    name: row.name || '',
    protocol: row.protocol || 'RTSP',
    host: row.host || '',
    port: row.port ?? 554,
    username: row.username || '',
    password: '',
    path: row.path || '',
    stream_name: row.stream_name || '',
    enabled: row.enabled !== false,
    gb_enabled: row.gb_enabled === true,
    gb_id: row.gb_id || '',
    gb_name: row.gb_name || '',
    gb_parent_gb_id: row.gb_parent_gb_id || '',
    extra: row.extra || {}
  } : {
    name: '',
    protocol: 'RTSP',
    host: '',
    port: 554,
    username: '',
    password: '',
    path: '',
    stream_name: '',
    enabled: true,
    gb_enabled: false,
    gb_id: '',
    gb_name: '',
    gb_parent_gb_id: '',
    extra: {}
  }
  ffmpegCmdKey.value = String((form.value.extra || {})['ffmpeg_cmd_key'] || '')
  try {
    extraJson.value = JSON.stringify(form.value.extra || {}, null, 2)
  } catch {
    extraJson.value = '{}'
  }
  dialogVisible.value = true
}

watch(dialogVisible, (v) => {
  if (!v) return
  ffmpegCmdKey.value = String((form.value.extra || {})['ffmpeg_cmd_key'] || '')
  try {
    extraJson.value = JSON.stringify(form.value.extra || {}, null, 2)
  } catch {
    extraJson.value = '{}'
  }
})

const save = async () => {
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
  }
  const name = String(form.value.name || '').trim()
  const protocol = String(form.value.protocol || '').trim()
  const host = String(form.value.host || '').trim()
  if (!name || !protocol || !host) {
    ElMessage.warning('请先补全名称、协议和主机地址')
    return
  }
  let extra: Record<string, unknown> = {}
  const extraRaw = String(extraJson.value || '').trim()
  if (extraRaw) {
    try {
      const parsed = JSON.parse(extraRaw)
      extra = parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      ElMessage.warning('扩展参数格式不正确，请输入合法的 JSON')
      return
    }
  }
  if (ffmpegCmdKey.value) {
    extra['ffmpeg_cmd_key'] = String(ffmpegCmdKey.value)
  } else {
    delete extra['ffmpeg_cmd_key']
  }
  saving.value = true
  try {
    const payload: Record<string, unknown> = { ...form.value, extra }
    if (!payload.password) delete payload.password
    if (!payload.username) payload.username = ''
    if (!payload.path) payload.path = ''
    if (!payload.stream_name) payload.stream_name = ''
    if (useProxyCompat.value) {
      const compatPayload: Record<string, unknown> = {
        ...(editingId.value ? { id: editingId.value } : {}),
        name: payload.name,
        protocol: payload.protocol,
        host: payload.host,
        port: payload.port,
        username: payload.username,
        ...(payload.password ? { password: payload.password } : {}),
        path: payload.path,
        stream_name: payload.stream_name,
        enabled: payload.enabled,
        type: ffmpegCmdKey.value ? 'ffmpeg' : 'default',
        ...(ffmpegCmdKey.value ? { ffmpegCmdKey: String(ffmpegCmdKey.value) } : {}),
        gb_enabled: payload.gb_enabled,
        gb_id: payload.gb_id,
        gb_name: payload.gb_name,
        gb_parent_gb_id: payload.gb_parent_gb_id,
        extra: payload.extra || {}
      }
      await api.post('/api/v1/proxy/save', compatPayload)
    } else {
      if (editingId.value) {
        await api.put(`/api/v1/integrations/sources/${editingId.value}`, payload)
      } else {
        await api.post('/api/v1/integrations/sources', payload)
      }
    }
    dialogVisible.value = false
    ElMessage.success(editingId.value ? '接入源已更新' : '接入源已创建')
    await loadSources()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    saving.value = false
  }
}

const testSource = async (id: string) => {
  testing.value[id] = true
  try {
    const res = await api.post(`/api/v1/integrations/sources/${id}/test`)
    ElMessage.success(res.data?.message || '连通性测试已完成')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    testing.value[id] = false
  }
}

const remove = async (id: string) => {
  try {
    await ElMessageBox.confirm('删除后不可恢复，是否继续？', '删除接入源', { type: 'warning' })
  } catch {
    return
  }
  try {
    if (useProxyCompat.value) {
      await api.delete(`/api/v1/proxy/delete?id=${encodeURIComponent(id)}`)
    } else {
      await api.delete(`/api/v1/integrations/sources/${id}`)
    }
    ElMessage.success('接入源已删除')
    await loadSources()
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
    await loadSources()
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
  await loadSources()
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
  await loadSources()
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

const stopProxy = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  const stream = normalizeStreamName(row)
  try {
    await ElMessageBox.confirm(`确认停止代理流 live/${stream} 吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  if (!id) return
  stopping.value[id] = true
  try {
    if (useProxyCompat.value) {
      await api.post(`/api/v1/proxy/stop`, { id })
    } else {
      await api.post(`/api/v1/integrations/sources/${id}/actions/desired-state`, { state: 'stopped', enforce: true })
    }
    ElMessage.success('已发送停流')
    await loadSources()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    stopping.value[id] = false
  }
}

const handleSourceMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'test') {
    await testSource(row.id)
    return
  }
  if (cmd === 'start') {
    await startProxy(row)
    return
  }
  if (cmd === 'stop') {
    await stopProxy(row)
    return
  }
  if (cmd === 'pushUrl') {
    await showPushUrl(row.id)
    return
  }
  if (cmd === 'delete') {
    await remove(row.id)
  }
}

const setEnabled = async (row: Record<string, unknown>, enabled: boolean) => {
  const id = String(row?.id || '')
  if (!id) return
  enabling.value[id] = true
  try {
    await api.post(`/api/v1/integrations/sources/${id}/actions/set-enabled`, { enabled })
    ElMessage.success('已保存')
    await loadSources()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    enabling.value[id] = false
  }
}

onMounted(() => {
  loadSources()
  loadFfmpegCmds()
})

watch(
  () => useProxyCompat.value,
  () => {
    loadSources()
    loadFfmpegCmds()
  }
)
</script>

<style scoped>
.sources-table :deep(.el-table__cell) {
  vertical-align: middle;
}
</style>
