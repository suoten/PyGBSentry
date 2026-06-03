<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader title="云端录像" description="按通道检索云端录像，并支持回放与下载">
          <template #actions>
            <el-button @click="verifySelected" :disabled="!selectedIds.length" :loading="bulkVerifying">批量校验</el-button>
            <el-button @click="repairSelected" :disabled="!selectedIds.length" :loading="bulkRepairing">批量修复链接</el-button>
            <el-button type="danger" plain @click="deleteBadSelected" :disabled="!badSelectedIds.length" :loading="bulkDeleting">批量删异常</el-button>
          </template>
        </PageHeader>
      </template>

      <div class="flex-1 flex gap-3 overflow-hidden mt-3">
      <!-- Device Tree Sidebar -->
      <div class="w-72 flex-shrink-0 flex flex-col bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        <div class="p-3 border-b border-slate-200 bg-slate-50 flex flex-col gap-3">
          <div class="flex items-center justify-between">
            <div class="font-bold text-slate-800 flex items-center gap-2">
              <el-icon class="text-sky-500"><VideoCamera /></el-icon>
              设备目录
            </div>
            <el-button link type="primary" size="small" @click="fetchTree">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
          <el-radio-group v-model="treeMode" size="small" @change="fetchTree">
            <el-radio-button value="business">业务分组</el-radio-button>
            <el-radio-button value="region">行政区划</el-radio-button>
          </el-radio-group>
          <el-input v-model="filterText" placeholder="搜索设备/通道..." size="small" clearable />
        </div>
        <div class="flex-1 overflow-auto p-2 bg-slate-50/50 min-h-0">
          <div v-if="loadingTree" class="flex justify-center py-12 text-slate-400">
            <el-icon class="animate-spin text-2xl text-sky-500"><Loading /></el-icon>
          </div>
          <SharedChannelTree
            v-else
            ref="treeRef"
            :data="treeData"
            :props-config="defaultProps"
            node-key="id"
            :default-expand-all="true"
            :current-node-key="selectedNode?.id"
            :highlight-current="true"
            :filter-node-method="filterNode"
            @node-click="handleNodeClick"
            tree-class="channel-tree"
            :truncate-text="true"
            :show-status-badge="shouldShowStatusBadge"
            :show-node-stats="shouldShowNodeStats"
            :get-node-stats="getNodeStats"
            :get-node-stats-tone="getNodeStatsTone"
          />
        </div>
      </div>

      <!-- Right Content -->
      <div class="flex-1 flex flex-col min-w-0 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        <div class="p-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between flex-wrap gap-3">
          <div class="flex items-center gap-2">
            <div class="w-1 h-4 rounded-full bg-sky-500"></div>
            <div class="font-semibold text-slate-700">录像列表</div>
            <el-tag v-if="selectedNode" size="small" type="info" effect="plain" round class="ml-2">
              当前：{{ selectedNode.label }}
            </el-tag>
            <el-tag v-if="selectedNode" size="small" type="success" effect="plain" round>
              通道数：{{ selectedChannelIds.length }}
            </el-tag>
          </div>
          <div class="flex items-center gap-2">
            <el-date-picker 
              v-model="dateRange" 
              type="datetimerange" 
              range-separator="至" 
              start-placeholder="开始时间" 
              end-placeholder="结束时间"
              size="small"
              style="width: 320px"
            />
            <el-checkbox v-model="onlyBad" size="small" class="ml-2">仅异常</el-checkbox>
            <el-button type="primary" size="small" @click="() => { page = 1; search(); }" :loading="loading">查询</el-button>
          </div>
        </div>

        <div class="flex-1 overflow-auto p-3">
          <el-table :data="filteredRows" border size="small" v-loading="loading" :empty-text="'暂无录像'" row-key="id" @selection-change="onSelectionChange" class="h-full">
            <el-table-column type="selection" width="50" />
            <el-table-column prop="start_time" label="开始时间" width="160" />
            <el-table-column prop="end_time" label="结束时间" width="160" />
            <el-table-column label="时长(秒)" width="100">
              <template #default="{ row }">
                {{ formatDuration(row.duration) }}
              </template>
            </el-table-column>
            <el-table-column prop="file_size" label="大小" width="100">
              <template #default="{ row }">
                {{ formatSize(row.file_size) }}
              </template>
            </el-table-column>
            <el-table-column label="来源" width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-xs font-mono">{{ row.record_app || '-' }} {{ row.media_node_id ? `@${row.media_node_id}` : '' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="设备/通道" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-xs">{{ row.device_name || row.device_id }} / {{ row.channel_name || row.channel_id }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tooltip v-if="row.url_ok === false" :content="row.url_error || '未知错误'" placement="top">
                  <el-tag type="danger" size="small">异常</el-tag>
                </el-tooltip>
                <el-tag v-else-if="row.url_checked_at" type="success" size="small">已校验</el-tag>
                <el-tag v-else type="info" size="small">未校验</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220" align="center" fixed="right">
              <template #default="{ row }">
                <div class="flex items-center justify-center gap-1">
                  <el-button size="small" type="primary" link @click="play(row)">回放</el-button>
                  <el-button size="small" link @click="download(row)">下载</el-button>
                  <el-dropdown trigger="click" @command="(cmd: string) => handleRecordMoreCommand(row, cmd)">
                    <el-button size="small" type="info" link>更多<el-icon class="el-icon--right"><arrow-down /></el-icon></el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="copyUrl">复制链接</el-dropdown-item>
                        <el-dropdown-item command="verify">校验</el-dropdown-item>
                        <el-dropdown-item command="repair" :disabled="!row.media_node_id">修复链接</el-dropdown-item>
                        <el-dropdown-item command="remove" divided class="text-red-500">删索引</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        
        <div class="p-3 border-t border-slate-200 flex justify-end bg-white">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[50, 100, 200, 500]"
            size="small"
            @current-change="search"
            @size-change="() => { page = 1; search() }"
          />
        </div>
      </div>

      <AppDialog v-model="previewVisible" title="回放" size="large">
        <div v-if="previewUrl" class="min-h-[360px]">
          <div class="flex items-center justify-end gap-2 mb-2">
            <el-button size="small" @click="fetchVodSources" :loading="vodSourcesLoading">获取播放源</el-button>
            <el-button size="small" @click="fetchVodOptimizedUrl" :loading="vodOptimizedLoading">最优地址</el-button>
            <el-button size="small" @click="copyPreviewUrl">复制地址</el-button>
            <el-button size="small" @click="openPreviewUrl">新标签打开</el-button>
            <el-button v-if="previewRecordId" size="small" type="primary" @click="downloadPreview">下载</el-button>
          </div>
          <div v-if="vodSources.length" class="mb-2">
            <el-select v-model="selectedVodSource" placeholder="选择播放源" size="small" @change="switchVodSource" style="width: 100%">
              <el-option v-for="(src, idx) in vodSources" :key="idx" :label="`${src.protocol?.toUpperCase() || '未知'} - ${src.type || ''} ${src.health_score ? '(' + src.health_score + '分)' : ''}`" :value="idx" />
            </el-select>
          </div>
          <SmartVideoPlayer :video-url="previewUrl" />
        </div>
        <div v-else class="text-slate-500 text-sm">暂无回放地址</div>
      </AppDialog>
    </div>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import { VideoCamera, Refresh, Loading, ArrowDown } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import SmartVideoPlayer from '../components/SmartVideoPlayer.vue'
import AppDialog from '../components/common/AppDialog.vue'
import SharedChannelTree from '../components/channel/SharedChannelTree.vue'
import { useChannelTreeStats } from '../utils/channelTreeStats'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const treeMode = ref<'business' | 'region'>('business')
type FilterableTreeRef = {
  filter?: (keyword: string) => void
}

const treeRef = ref<FilterableTreeRef | null>(null)
const treeData = ref<VideoRecord[]>([])
const loadingTree = ref(false)
const filterText = ref('')
const selectedNode = ref<VideoRecord | null>(null)

const selectedDeviceId = ref('')
const selectedChannelIds = ref<string[]>([])
const dateRange = ref<[Date, Date] | []>([])
const rows = ref<VideoRecord[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(100)
const previewVisible = ref(false)
const previewUrl = ref('')
const previewRecordId = ref('')

const vodSources = ref<any[]>([])
const selectedVodSource = ref<number>(-1)
const vodSourcesLoading = ref(false)
const vodOptimizedLoading = ref(false)

const fetchVodSources = async () => {
  const id = String(previewRecordId.value || '')
  if (!id) return
  vodSourcesLoading.value = true
  try {
    const res = await api.get(`/api/v1/vod/vod/sources/${id}`)
    const sources = Array.isArray(res.data?.sources) ? res.data.sources : []
    vodSources.value = sources
    if (sources.length && selectedVodSource.value < 0) {
      const rec = res.data?.recommended
      if (rec) {
        const idx = sources.findIndex((s: Record<string, unknown>) => s.url === rec.url)
        selectedVodSource.value = idx >= 0 ? idx : 0
      } else {
        selectedVodSource.value = 0
      }
      previewUrl.value = sources[selectedVodSource.value]?.url || previewUrl.value
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    vodSourcesLoading.value = false
  }
}

const fetchVodOptimizedUrl = async () => {
  const id = String(previewRecordId.value || '')
  if (!id) return
  vodOptimizedLoading.value = true
  try {
    const res = await api.get(`/api/v1/vod/vod/optimized-url/${id}`)
    const url = res.data?.url
    if (url) {
      previewUrl.value = url
      ElMessage.success(`已切换到最优地址（${res.data?.protocol || 'auto'}）`)
    } else {
      ElMessage.warning(t('cloudRecord.noOptimizedUrl'))  // FIXED: 硬编码中文→i18n
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    vodOptimizedLoading.value = false
  }
}

const switchVodSource = (idx: number) => {
  const src = vodSources.value[idx]
  if (src?.url) previewUrl.value = src.url
}
const onlyBad = ref(false)
const verifying = ref<Record<string, boolean>>({})
const removing = ref<Record<string, boolean>>({})
const bulkVerifying = ref(false)
const bulkDeleting = ref(false)
const repairing = ref<Record<string, boolean>>({})
const bulkRepairing = ref(false)
const selectedIds = ref<string[]>([])
const isPlayableTreeChannel = (node: TreeNode) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  if (nodeType !== 'channel' && nodeType !== 'source_stream') return false
  if (Number(node?.status) !== 1) return false
  const gbId = String(node?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  return ['131', '132', '111', '112', '118'].includes(typeCode)
}
const shouldShowStatusBadge = (node: TreeNode) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  return nodeType === 'channel' || nodeType === 'source_stream'
}
const {
  rebuildTreeNodeStats,
  shouldShowNodeStats,
  getNodeStats,
  getNodeStatsTone
} = useChannelTreeStats(treeData, {
  countableNodeTypes: ['channel', 'source_stream'],
  statsVisibleNodeTypes: ['root', 'directory', 'region', 'source_root', 'source_protocol'],
  isPlayableChannel: isPlayableTreeChannel
})

const badSelectedIds = computed(() => {
  const s = new Set(selectedIds.value)
  return (rows.value || []).filter((r: Record<string, unknown>) => r && s.has(String(r.id)) && r.url_ok === false).map((r: Record<string, unknown>) => String(r.id))
})

const filteredRows = computed(() => {
  if (!onlyBad.value) return rows.value
  return (rows.value || []).filter((r: Record<string, unknown>) => r && r.url_ok === false)
})

const formatSize = (v: unknown) => {
  const n = Number(v || 0)
  if (!Number.isFinite(n) || n <= 0) return '0 MB'
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

const formatDuration = (v: unknown) => {
  const n = Number(v || 0)
  if (!Number.isFinite(n) || n <= 0) return '0.00'
  return n.toFixed(2)
}

const defaultProps = {
  children: 'children',
  label: 'label',
  isLeaf: (data: Record<string, unknown>) => data.nodeType === 'channel'
}

watch(filterText, (val) => {
  treeRef.value?.filter?.(val)
})

const filterNode = (value: string, data: Record<string, unknown>) => {
  if (!value) return true
  return String(data.label || '').includes(value)
}

const fetchTree = async () => {
  loadingTree.value = true
  try {
    const treeUrl = treeMode.value === 'business' 
      ? '/api/v1/devices/tree/business' 
      : '/api/v1/devices/tree'
    const res = await api.get(treeUrl)
    treeData.value = Array.isArray(res.data) ? res.data : []
    rebuildTreeNodeStats()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message || '加载设备树失败')
  } finally {
    loadingTree.value = false
  }
}

const collectChannelIds = (node: TreeNode): string[] => {
  const ids = new Set<string>()
  const walk = (item: Record<string, unknown>) => {
    if (!item || typeof item !== 'object') return
    const nodeType = String(item.nodeType || '').toLowerCase()
    if (nodeType === 'channel' || nodeType === 'source_stream') {
      const cid = String(item.channelId || item.id || '').trim()
      if (cid) ids.add(cid)
      return
    }
    const children = Array.isArray(item.children) ? item.children : []
    children.forEach((child: Record<string, unknown>) => walk(child))
  }
  walk(node)
  return Array.from(ids)
}

const handleNodeClick = (data: Record<string, unknown>) => {
  selectedNode.value = data
  page.value = 1
  if (data.nodeType === 'channel' || data.nodeType === 'source_stream') {
    selectedChannelIds.value = [String(data.channelId || data.id || '')].filter((v) => !!v)
    selectedDeviceId.value = String(data.deviceId || '')
    search()
  } else {
    selectedChannelIds.value = collectChannelIds(data)
    selectedDeviceId.value = ''
    search()
  }
}

const search = async () => {
  if (!Array.isArray(dateRange.value) || dateRange.value.length < 2) {
    ElMessage.warning(t('cloudRecord.selectTimeRange'))  // FIXED: 硬编码中文→i18n
    return
  }

  if (selectedNode.value && selectedChannelIds.value.length === 0) {
    rows.value = []
    total.value = 0
    return
  }

  loading.value = true
  try {
    const [start, end] = dateRange.value as [Date, Date]
    const params: Record<string, string | number> = {
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (selectedChannelIds.value.length === 1) {
      params.channel_id = selectedChannelIds.value[0]
      if (selectedDeviceId.value) {
        params.device_id = selectedDeviceId.value
      }
    } else if (selectedChannelIds.value.length > 1) {
      params.channel_ids = selectedChannelIds.value.join(',')
    }
    const res = await api.get('/api/v1/record/search', { params })
    rows.value = Array.isArray(res.data?.items) ? res.data.items : []
    total.value = Number(res.data?.total) || 0
  } catch (e: unknown) {
    rows.value = []
    total.value = 0
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const play = async (row: Record<string, unknown>) => {
  try {
    const { url, id } = await resolvePlayableUrl(row)
    if (!url) {
      ElMessage.warning(t('cloudRecord.cannotResolveUrl'))  // FIXED: 硬编码中文→i18n
      return
    }
    previewUrl.value = url
    previewRecordId.value = id
    vodSources.value = []
    selectedVodSource.value = -1
    previewVisible.value = true
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const download = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) {
    ElMessage.warning(t('cloudRecord.missingRecordId'))  // FIXED: 硬编码中文→i18n
    return
  }
  // 使用签名 URL 下载，避免 token 暴露在 URL 中
  try {
    const res = await api.get(`/api/v1/record/download/sign/${id}`, { params: { ttl_seconds: 300 } })
    const signedUrl = res.data?.signed_url || res.data?.url
    if (signedUrl) {
      window.open(signedUrl, '_blank')
    } else {
      ElMessage.error(t('cloudRecord.downloadFailed'))  // FIXED: 硬编码中文→i18n
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message || '获取下载链接失败')
  }
}

const copyUrl = async (row: Record<string, unknown>) => {
  try {
    const { url } = await resolvePlayableUrl(row)
    if (!url) return
    await navigator.clipboard.writeText(url)
    ElMessage.success(t('cloudRecord.copied'))  // FIXED: 硬编码中文→i18n
  } catch {
    ElMessage.warning(t('cloudRecord.copyFailedManual'))  // FIXED: 硬编码中文→i18n
  }
}

const resolvePlayableUrl = async (row: Record<string, unknown>): Promise<{ url: string; id: string }> => {
  const id = String(row?.id || '')
  if (!id) {
    ElMessage.warning(t('cloudRecord.missingRecordId'))  // FIXED: 硬编码中文→i18n
    return { url: '', id: '' }
  }
  // 使用签名 URL，避免 token 暴露在 URL 中
  try {
    const res = await api.get(`/api/v1/record/download/sign/${id}`, { params: { inline: true, ttl_seconds: 300 } })
    const signedUrl = res.data?.signed_url || res.data?.url || ''
    return { url: signedUrl, id }
  } catch {
    return { url: '', id }
  }
}

const copyPreviewUrl = async () => {
  if (!previewUrl.value) return
  try {
    await navigator.clipboard.writeText(previewUrl.value)
    ElMessage.success(t('cloudRecord.copied'))  // FIXED: 硬编码中文→i18n
  } catch {
    ElMessage.warning(t('cloudRecord.copyFailedManual'))  // FIXED: 硬编码中文→i18n
  }
}

const openPreviewUrl = () => {
  if (!previewUrl.value) return
  window.open(previewUrl.value, '_blank')
}

const downloadPreview = async () => {
  const id = String(previewRecordId.value || '')
  if (!id) return
  // 使用签名 URL 下载，避免 token 暴露在 URL 中
  try {
    const res = await api.get(`/api/v1/record/download/sign/${id}`, { params: { ttl_seconds: 300 } })
    const signedUrl = res.data?.signed_url || res.data?.url
    if (signedUrl) window.open(signedUrl, '_blank')
  } catch {
    ElMessage.error('获取下载链接失败')
  }
}

const verify = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  verifying.value[id] = true
  try {
    const res = await api.post(`/api/v1/record/verify/${id}`)
    const ok = !!res.data?.ok
    ElMessage.success(ok ? '校验通过' : '校验失败')
    await search()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    verifying.value[id] = false
  }
}

const repair = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  repairing.value[id] = true
  try {
    const res = await api.post(`/api/v1/record/repair-url/${id}`)
    const newUrl = String(res.data?.new || '')
    if (newUrl) {
      try {
        await navigator.clipboard.writeText(newUrl)
        ElMessage.success('已修复链接并复制')
      } catch {
        ElMessage.success('已修复链接')
      }
    } else {
      ElMessage.success('已修复链接')
    }
    await search()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    repairing.value[id] = false
  }
}

const remove = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  try {
    await ElMessageBox.confirm('确认删除该录像索引？不会删除实际文件。', '提示', { type: 'warning' })
  } catch {
    return
  }
  removing.value[id] = true
  try {
    await api.delete(`/api/v1/record/${id}`)
    ElMessage.success(t('cloudRecord.indexDeleted'))  // FIXED: 硬编码中文→i18n
    await search()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    removing.value[id] = false
  }
}

const handleRecordMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  try {
    if (cmd === 'copyUrl') {
      await copyUrl(row)
      return
    }
    if (cmd === 'verify') {
      await verify(row)
      return
    }
    if (cmd === 'repair') {
      await repair(row)
      return
    }
    if (cmd === 'remove') {
      await remove(row)
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const onSelectionChange = (list: Record<string, unknown>[]) => {
  selectedIds.value = (list || []).map((r: Record<string, unknown>) => String(r?.id || '')).filter((id) => !!id)
}

const verifySelected = async () => {
  const ids = selectedIds.value.slice(0, 200)
  if (!ids.length) return
  bulkVerifying.value = true
  try {
    const res = await api.post('/api/v1/record/verify-batch', { ids })
    ElMessage.success(`已校验：${res.data?.ok || 0} 成功，${res.data?.failed || 0} 失败`)
    await search()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    bulkVerifying.value = false
  }
}

const repairSelected = async () => {
  const ids = selectedIds.value.slice(0, 200)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确认修复 ${ids.length} 条录像链接？此操作将重新生成链接地址。`, '批量修复', { type: 'warning', confirmButtonText: '确定修复', cancelButtonText: '取消' })
  } catch {
    return
  }
  bulkRepairing.value = true
  try {
    const res = await api.post('/api/v1/record/repair-url-batch', { ids })
    ElMessage.success(`已修复：${res.data?.repaired || 0}`)
    await search()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    bulkRepairing.value = false
  }
}

const deleteBadSelected = async () => {
  const ids = badSelectedIds.value.slice(0, 500)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确认删除 ${ids.length} 条异常索引？不会删除实际文件。`, '提示', { type: 'warning' })
  } catch {
    return
  }
  bulkDeleting.value = true
  try {
    const res = await api.post('/api/v1/record/delete-batch', { ids })
    ElMessage.success(`已删除索引：${res.data?.deleted || 0}`)
    selectedIds.value = []
    await search()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    bulkDeleting.value = false
  }
}

onMounted(async () => {
  try {
    await fetchTree()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 3600 * 1000 * 24)
  dateRange.value = [start, end]
  search()
})
</script>
