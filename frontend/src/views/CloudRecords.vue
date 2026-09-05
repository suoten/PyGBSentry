<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader :title="t('cloudRecordPage.title')" :description="t('cloudRecordPage.description')">
          <template #actions>
            <el-button @click="verifySelected" :disabled="!selectedIds.length" :loading="bulkVerifying">{{ t('cloudRecordPage.batchVerify') }}</el-button>
            <el-button @click="repairSelected" :disabled="!selectedIds.length" :loading="bulkRepairing">{{ t('cloudRecordPage.batchRepair') }}</el-button>
            <el-button type="danger" plain @click="deleteBadSelected" :disabled="!badSelectedIds.length" :loading="bulkDeleting">{{ t('cloudRecordPage.batchDeleteBad') }}</el-button>
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
              {{ t('cloudRecordPage.deviceDirectory') }}
            </div>
            <el-button link type="primary" size="small" @click="fetchTree">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
          <el-radio-group v-model="treeMode" size="small" @change="fetchTree">
            <el-radio-button value="business">{{ t('cloudRecordPage.businessGroup') }}</el-radio-button>
            <el-radio-button value="region">{{ t('cloudRecordPage.regionGroup') }}</el-radio-button>
          </el-radio-group>
          <el-input v-model="filterText" :placeholder="t('cloudRecordPage.searchPlaceholder')" size="small" clearable />
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
            <div class="font-semibold text-slate-700">{{ t('cloudRecordPage.recordList') }}</div>
            <el-tag v-if="selectedNode" size="small" type="info" effect="plain" round class="ml-2">
              {{ t('cloudRecordPage.currentNode', { label: selectedNode.label }) }}
            </el-tag>
            <el-tag v-if="selectedNode" size="small" type="success" effect="plain" round>
              {{ t('cloudRecordPage.channelCount', { count: selectedChannelIds.length }) }}
            </el-tag>
          </div>
          <div class="flex items-center gap-2">
            <el-date-picker
              v-model="dateRange"
              type="datetimerange"
              :range-separator="t('cloudRecordPage.rangeSeparator')"
              :start-placeholder="t('cloudRecordPage.startTimePlaceholder')"
              :end-placeholder="t('cloudRecordPage.endTimePlaceholder')"
              size="small"
              style="width: 320px"
            />
            <el-checkbox v-model="onlyBad" size="small" class="ml-2">{{ t('cloudRecordPage.onlyAbnormal') }}</el-checkbox>
            <el-button type="primary" size="small" @click="() => { page = 1; search(); }" :loading="loading">{{ t('cloudRecordPage.query') }}</el-button>
          </div>
        </div>

        <div class="flex-1 overflow-auto p-3">
          <el-table :data="filteredRows" border size="small" v-loading="loading" :empty-text="t('cloudRecordPage.noRecords')" row-key="id" @selection-change="onSelectionChange" class="h-full">
            <el-table-column type="selection" width="50" />
            <el-table-column prop="start_time" :label="t('cloudRecordPage.startTimeColumn')" width="160" />
            <el-table-column prop="end_time" :label="t('cloudRecordPage.endTimeColumn')" width="160" />
            <el-table-column :label="t('cloudRecordPage.durationColumn')" width="100">
              <template #default="{ row }">
                {{ formatDuration(row.duration) }}
              </template>
            </el-table-column>
            <el-table-column prop="file_size" :label="t('cloudRecordPage.sizeColumn')" width="100">
              <template #default="{ row }">
                {{ formatSize(row.file_size) }}
              </template>
            </el-table-column>
            <el-table-column :label="t('cloudRecordPage.sourceColumn')" width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-xs font-mono">{{ row.record_app || '-' }} {{ row.media_node_id ? `@${row.media_node_id}` : '' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('cloudRecordPage.deviceChannelColumn')" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-xs">{{ row.device_name || row.device_id }} / {{ row.channel_name || row.channel_id }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('cloudRecordPage.statusColumn')" width="90" align="center">
              <template #default="{ row }">
                <el-tooltip v-if="row.url_ok === false" :content="row.url_error || t('cloudRecordPage.unknownError')" placement="top">
                  <el-tag type="danger" size="small">{{ t('cloudRecordPage.abnormal') }}</el-tag>
                </el-tooltip>
                <el-tag v-else-if="row.url_checked_at" type="success" size="small">{{ t('cloudRecordPage.verified') }}</el-tag>
                <el-tag v-else type="info" size="small">{{ t('cloudRecordPage.notVerified') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('cloudRecordPage.operationColumn')" width="220" align="center" fixed="right">
              <template #default="{ row }">
                <div class="flex items-center justify-center gap-1">
                  <el-button size="small" type="primary" link @click="play(row)">{{ t('cloudRecordPage.playback') }}</el-button>
                  <el-button size="small" link @click="download(row)">{{ t('cloudRecordPage.download') }}</el-button>
                  <el-dropdown trigger="click" @command="(cmd: string) => handleRecordMoreCommand(row, cmd)">
                    <el-button size="small" type="info" link>{{ t('cloudRecordPage.more') }}<el-icon class="el-icon--right"><arrow-down /></el-icon></el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="copyUrl">{{ t('cloudRecordPage.copyLink') }}</el-dropdown-item>
                        <el-dropdown-item command="verify">{{ t('cloudRecordPage.verify') }}</el-dropdown-item>
                        <el-dropdown-item command="repair" :disabled="!row.media_node_id">{{ t('cloudRecordPage.repairLink') }}</el-dropdown-item>
                        <el-dropdown-item command="remove" divided class="text-red-500">{{ t('cloudRecordPage.deleteIndex') }}</el-dropdown-item>
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

      <AppDialog v-model="previewVisible" :title="t('cloudRecordPage.playbackTitle')" size="large">
        <div v-if="previewUrl" class="min-h-[360px]">
          <div class="flex items-center justify-end gap-2 mb-2">
            <el-button size="small" @click="fetchVodSources" :loading="vodSourcesLoading">{{ t('cloudRecordPage.getPlaySources') }}</el-button>
            <el-button size="small" @click="fetchVodOptimizedUrl" :loading="vodOptimizedLoading">{{ t('cloudRecordPage.optimizedUrl') }}</el-button>
            <el-button size="small" @click="copyPreviewUrl">{{ t('cloudRecordPage.copyAddress') }}</el-button>
            <el-button size="small" @click="openPreviewUrl">{{ t('cloudRecordPage.openInNewTab') }}</el-button>
            <el-button v-if="previewRecordId" size="small" type="primary" @click="downloadPreview">{{ t('cloudRecordPage.download') }}</el-button>
          </div>
          <div v-if="vodSources.length" class="mb-2">
            <el-select v-model="selectedVodSource" :placeholder="t('cloudRecordPage.selectSourcePlaceholder')" size="small" @change="switchVodSource" style="width: 100%">
              <el-option v-for="(src, idx) in vodSources" :key="idx" :label="`${src.protocol?.toUpperCase() || t('cloudRecordPage.unknown')} - ${src.type || ''} ${src.health_score ? '(' + src.health_score + t('cloudRecordPage.scoreSuffix') + ')' : ''}`" :value="idx" />
            </el-select>
          </div>
          <SmartVideoPlayer :video-url="previewUrl" />
        </div>
        <div v-else class="text-slate-500 text-sm">{{ t('cloudRecordPage.noPlaybackUrl') }}</div>
      </AppDialog>
    </div>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { getFriendlyError } from '../utils/errorMessage'
import { VideoCamera, Refresh, Loading, ArrowDown } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import SmartVideoPlayer from '../components/SmartVideoPlayer.vue'
import AppDialog from '../components/common/AppDialog.vue'
import SharedChannelTree from '../components/channel/SharedChannelTree.vue'
import { useChannelTreeStats } from '../utils/channelTreeStats'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, StructuredEvent, PluginConfig } from '@/types/models'

// 设备树节点（/api/v1/devices/tree 响应，按实际使用字段定义）
interface DeviceTreeNode {
  id: string
  label?: string
  nodeType?: string
  children?: unknown[]
  [key: string]: unknown
}

const treeMode = ref<'business' | 'region'>('business')
const { t } = useI18n()  // FIXED: 国际化
type FilterableTreeRef = {
  filter?: (keyword: string) => void
}

const treeRef = ref<FilterableTreeRef | null>(null)
const treeData = ref<DeviceTreeNode[]>([])
const loadingTree = ref(false)
const filterText = ref('')
const selectedNode = ref<DeviceTreeNode | null>(null)

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
    // FIX: [2026-08-22 PN] 后端 vod 双前缀已修复（/api/v1/vod/vod → /api/v1/vod）
    const res = await api.get(`/api/v1/vod/sources/${id}`)
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
    // FIX: [2026-08-22 PN] 后端 vod 双前缀已修复（/api/v1/vod/vod → /api/v1/vod）
    const res = await api.get(`/api/v1/vod/optimized-url/${id}`)
    const url = res.data?.url
    if (url) {
      previewUrl.value = url
      ElMessage.success(t('cloudRecordPage.switchedOptimizedUrl', { protocol: res.data?.protocol || 'auto' }))  // FIXED: 硬编码中文→i18n
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
const isPlayableTreeChannel = (node: Record<string, unknown>) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  if (nodeType !== 'channel' && nodeType !== 'source_stream') return false
  if (Number(node?.status) !== 1) return false
  const gbId = String(node?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  return ['131', '132', '111', '112', '118'].includes(typeCode)
}
const shouldShowStatusBadge = (node: Record<string, unknown>) => {
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
    ElMessage.error(friendly.message || t('cloudRecordPage.loadTreeFailed'))  // FIXED: 硬编码中文→i18n
  } finally {
    loadingTree.value = false
  }
}

const collectChannelIds = (node: Record<string, unknown>): string[] => {
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
  selectedNode.value = data as DeviceTreeNode
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
    ElMessage.error(friendly.message || t('cloudRecordPage.getDownloadLinkFailed'))  // FIXED: 硬编码中文→i18n
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
    ElMessage.error(t('cloudRecordPage.getDownloadLinkFailed'))  // FIXED: 硬编码中文→i18n
  }
}

const verify = async (row: Record<string, unknown>) => {
  const id = String(row?.id || '')
  if (!id) return
  verifying.value[id] = true
  try {
    const res = await api.post(`/api/v1/record/verify/${id}`)
    const ok = !!res.data?.ok
    ElMessage.success(ok ? t('cloudRecordPage.verifyPassed') : t('cloudRecordPage.verifyFailed'))  // FIXED: 硬编码中文→i18n
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
        ElMessage.success(t('cloudRecordPage.linkFixedAndCopied'))  // FIXED: 硬编码中文→i18n
      } catch {
        ElMessage.success(t('cloudRecordPage.linkFixed'))  // FIXED: 硬编码中文→i18n
      }
    } else {
      ElMessage.success(t('cloudRecordPage.linkFixed'))  // FIXED: 硬编码中文→i18n
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
    await ElMessageBox.confirm(t('cloudRecordPage.confirmDeleteIndex'), t('cloudRecordPage.tipTitle'), { type: 'warning' })  // FIXED: 硬编码中文→i18n
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
    ElMessage.success(t('cloudRecordPage.batchVerifyResult', { ok: res.data?.ok || 0, failed: res.data?.failed || 0 }))  // FIXED: 硬编码中文→i18n
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
    await ElMessageBox.confirm(t('cloudRecordPage.confirmRepairBatch', { count: ids.length }), t('cloudRecordPage.batchRepairTitle'), { type: 'warning', confirmButtonText: t('cloudRecordPage.confirmRepair'), cancelButtonText: t('cloudRecordPage.cancel') })  // FIXED: 硬编码中文→i18n
  } catch {
    return
  }
  bulkRepairing.value = true
  try {
    const res = await api.post('/api/v1/record/repair-url-batch', { ids })
    ElMessage.success(t('cloudRecordPage.batchRepairResult', { repaired: res.data?.repaired || 0 }))  // FIXED: 硬编码中文→i18n
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
    await ElMessageBox.confirm(t('cloudRecordPage.confirmDeleteBadBatch', { count: ids.length }), t('cloudRecordPage.tipTitle'), { type: 'warning' })  // FIXED: 硬编码中文→i18n
  } catch {
    return
  }
  bulkDeleting.value = true
  try {
    const res = await api.post('/api/v1/record/delete-batch', { ids })
    ElMessage.success(t('cloudRecordPage.batchDeleteResult', { deleted: res.data?.deleted || 0 }))  // FIXED: 硬编码中文→i18n
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
