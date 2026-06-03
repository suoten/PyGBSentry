<template>
  <div class="flex-1 flex flex-col bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm transition-shadow duration-200 hover:shadow-md">
    <ChannelToolbar
      :filters="filters"
      :tree-mode="treeMode"
      :selected-node="selectedNode"
      :selected-node-path-label="selectedNodePathLabel"
      :unadded-count="unaddedCount"
      :selected-channels="selectedChannels"
      :can-add-to-selected-node="canAddToSelectedNode"
      :table-density="tableDensity"
      :visible-column-keys="visibleColumnKeys"
      :channel-stream-reset="channelStreamReset"
      :advanced-filter-open="advancedFilterOpen"
      @update:filters="emit('update:filters', $event)"
      @update:table-density="emit('update:tableDensity', $event)"
      @update:visible-column-keys="emit('update:visibleColumnKeys', $event)"
      @update:channel-stream-reset="emit('update:channelStreamReset', $event)"
      @update:advanced-filter-open="emit('update:advancedFilterOpen', $event)"
      @list-scope-change="emit('listScopeChange')"
      @quick-status-change="emit('quickStatusChange')"
      @load-channels="emit('loadChannels')"
      @toolbar-more-command="emit('toolbarMoreCommand', $event)"
      @open-list-civil-filter-picker="emit('openListCivilFilterPicker')"
      @clear-list-civil-filter="emit('clearListCivilFilter')"
      @open-list-business-filter-picker="emit('openListBusinessFilterPicker')"
      @clear-list-business-filter="emit('clearListBusinessFilter')"
      @reset-visible-channels-stream-type="emit('resetVisibleChannelsStreamType')"
      @batch-placement-command="emit('batchPlacementCommand', $event)"
      @batch-add-to-selected-node="emit('batchAddToSelectedNode')"
      @batch-remove-from-node="emit('batchRemoveFromNode')"
    />

    <div class="flex-1 overflow-auto">
      <TableSkeleton v-if="loading && channels.length === 0" :rows="8" />
      <el-table
        v-else
        :key="`${treeMode}-${filters.listScope}-${selectedNode?.id || ''}`"
        :data="filteredChannels"
        ref="channelTableRef"
        v-loading="loading"
        style="width: 100%"
        :class="`custom-table density-${tableDensity}`"
        :empty-text="tableEmptyText"
        @selection-change="emit('selectionChange', $event)"
        @row-contextmenu="emit('channelRowContextMenu', $event)"
        row-key="id"
        class="custom-table density-${tableDensity}"
      >
        <el-table-column width="40" align="center">
          <template #default="{ row }">
            <div class="drag-handle cursor-move text-slate-300 hover:text-sky-500" :data-row-key="row.id">
              <el-icon><Rank /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column type="selection" width="45" :selectable="rowSelectable" />
        <el-table-column v-if="isColumnVisible('device')" prop="device_name" label="所属设备" width="130" show-overflow-tooltip />
        <el-table-column v-if="isColumnVisible('gbId')" prop="gb_id" label="国标ID" width="160">
          <template #default="{ row }">
            <span class="text-xs font-mono text-slate-500">{{ row.gb_id }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('name')" prop="name" :label="t('common.name')">
        <el-table-column v-if="isColumnVisible('vendor')" label="厂家/型号" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="text-xs text-slate-500">{{ row.device_manufacturer || '-' }} / {{ row.device_model || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('type')" :label="t('common.type')">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.node_type === 'directory' ? 'warning' : 'info'">
              {{ row.node_type === 'directory' ? '目录' : '通道' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('status')" :label="t('common.status')">
          <template #default="{ row }">
            <span class="status-dot" :class="Number(row.status) === 1 ? 'online' : 'offline'"></span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('audio')" label="音频" width="60" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.has_audio"
              size="small"
              :disabled="!!channelInlineSaving[String(row.id)]"
              @change="() => emit('saveChannelAudioInline', row)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('stream')" label="默认码流" width="130" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.default_stream_type"
              size="small"
              style="width: 110px"
              :disabled="!!channelInlineSaving[String(row.id)]"
              @change="() => emit('saveChannelStreamTypeInline', row)"
            >
              <el-option label="主码流" value="main" />
              <el-option label="子码流" value="sub" />
              <el-option label="主码流 (通用)" value="stream:0" />
              <el-option label="子码流 (通用)" value="stream:1" />
              <el-option label="主码流 (国标2022)" value="streamnumber:0" />
              <el-option label="子码流 (国标2022)" value="streamnumber:1" />
              <el-option label="主码流 (大华)" value="streamprofile:0" />
              <el-option label="子码流 (大华)" value="streamprofile:1" />
              <el-option label="主码流 (水星/TP)" value="streamMode:MAIN" />
              <el-option label="子码流 (水星/TP)" value="streamMode:SUB" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('mount')" label="挂载" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="catalogParentId(row) ? 'success' : 'info'">
              {{ catalogParentId(row) ? '已挂载' : '未挂载' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isColumnVisible('node')" label="所属节点" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="text-xs text-slate-500">{{ getNodeLabel(catalogParentId(row) || undefined) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action')">
          <template #default="{ row }">
            <div class="flex items-center justify-center gap-1">
              <el-button
                v-if="playingChannelGbId === String(row.gb_id || '')"
                size="small"
                type="danger"
                circle
                @click.stop="emit('closePlayer')"
              >
                <el-icon><CloseBold /></el-icon>
              </el-button>
              <el-tooltip v-else :content="playTooltip(row)" placement="top">
                <span>
                  <el-button
                    size="small"
                    type="primary"
                    circle
                    :disabled="!canPlay(row)"
                    :loading="channelPlayLoading[String(row.gb_id || '')]"
                    @click.stop="emit('playStream', row)"
                  >
                    <el-icon><VideoPlay /></el-icon>
                  </el-button>
                </span>
              </el-tooltip>

              <el-button size="small" circle @click.stop="emit('openChannelEdit', row)">
                <el-icon><Edit /></el-icon>
              </el-button>

              <el-dropdown trigger="click" @command="emit('handleMoreCommand', row, $event)">
                <el-button size="small" class="more-btn">
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="filters.listScope === 'on_node'" command="remove_from_node"><el-icon><Remove /></el-icon>从节点移除</el-dropdown-item>
                    <el-dropdown-item v-if="filters.listScope === 'unadded' && canAddToSelectedNode" command="add_to_node"><el-icon><Plus /></el-icon>添加到节点</el-dropdown-item>
                    <el-dropdown-item command="cloud"><el-icon><VideoCamera /></el-icon>云端录像</el-dropdown-item>
                    <el-dropdown-item command="device"><el-icon><Files /></el-icon>设备录像</el-dropdown-item>
                    <el-dropdown-item command="timeline"><el-icon><Timer /></el-icon>时间轴</el-dropdown-item>
                    <el-dropdown-item command="reset" divided><el-icon><RefreshRight /></el-icon>重置通道信息</el-dropdown-item>
                    <el-dropdown-item command="delete" class="danger"><el-icon><Delete /></el-icon>删除通道</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="p-3 border-t border-slate-200 bg-slate-50/70 flex items-center justify-between">
      <div class="text-sm text-slate-500">
        共 <span class="font-semibold text-slate-700">{{ total }}</span> 条，已选 <span class="font-semibold text-sky-600">{{ selectedChannels.length }}</span> 条
      </div>
      <div class="flex items-center gap-2">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          prev-text="上一页"
          next-text="下一页"
          size="small"
          @current-change="emit('loadChannels')"
          @size-change="emit('pageSizeChange')"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Plus, Delete, VideoCamera, VideoPlay, CloseBold, MoreFilled, Timer, Files, Edit, Remove, RefreshRight, Rank } from '@element-plus/icons-vue'
import TableSkeleton from '../../components/TableSkeleton.vue'
import ChannelToolbar from './ChannelToolbar.vue'
import type { Channel, TreeNode } from '@/types/models'
import { useI18n } from 'vue-i18n' // FIXED: 国际化

const { t } = useI18n() // FIXED: 国际化

const props = defineProps<{
  filters: {
    keyword: string
    listScope: 'unadded' | 'on_node' | 'all'
    status: number | undefined
    resource_type: number | undefined
    listCivilPrefix: string
    listCivilLabel: string
    listBusinessParentGbId: string
    listBusinessParentLabel: string
  }
  treeMode: 'business' | 'region'
  selectedNode: TreeNode
  selectedNodePathLabel: string
  unaddedCount: number
  loading: boolean
  channels: Channel[]
  filteredChannels: Channel[]
  selectedChannels: Channel[]
  total: number
  page: number
  pageSize: number
  canAddToSelectedNode: boolean
  tableDensity: 'compact' | 'comfortable'
  visibleColumnKeys: string[]
  channelInlineSaving: Record<string, boolean>
  channelPlayLoading: Record<string, boolean>
  playingChannelGbId: string
  channelStreamReset: string
  advancedFilterOpen: boolean
  tableEmptyText: string
  catalogParentId: (row: Record<string, unknown>) => string
  getNodeLabel: (parentGbId?: string | null) => string
  rowSelectable: (row: Record<string, unknown>) => boolean
}>()

const emit = defineEmits<{
  (e: 'update:filters', value: typeof props.filters): void
  (e: 'update:tableDensity', value: 'compact' | 'comfortable'): void
  (e: 'update:visibleColumnKeys', value: string[]): void
  (e: 'update:channelStreamReset', value: string): void
  (e: 'update:advancedFilterOpen', value: boolean): void
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
  (e: 'listScopeChange'): void
  (e: 'quickStatusChange'): void
  (e: 'loadChannels'): void
  (e: 'pageSizeChange'): void
  (e: 'toolbarMoreCommand', cmd: string): void
  (e: 'openListCivilFilterPicker'): void
  (e: 'clearListCivilFilter'): void
  (e: 'openListBusinessFilterPicker'): void
  (e: 'clearListBusinessFilter'): void
  (e: 'resetVisibleChannelsStreamType'): void
  (e: 'batchPlacementCommand', cmd: string): void
  (e: 'batchAddToSelectedNode'): void
  (e: 'batchRemoveFromNode'): void
  (e: 'selectionChange', rows: Record<string, unknown>[]): void
  (e: 'channelRowContextMenu', event: Record<string, unknown>): void
  (e: 'saveChannelAudioInline', row: Record<string, unknown>): void
  (e: 'saveChannelStreamTypeInline', row: Record<string, unknown>): void
  (e: 'playStream', row: Record<string, unknown>): void
  (e: 'closePlayer'): void
  (e: 'openChannelEdit', row: Record<string, unknown>): void
  (e: 'handleMoreCommand', row: Record<string, unknown>, cmd: string): void
}>()

const page = ref(props.page)
const pageSize = ref(props.pageSize)

watch(() => props.page, (val) => { page.value = val })
watch(() => props.pageSize, (val) => { pageSize.value = val })
watch(page, (val) => { emit('update:page', val) })
watch(pageSize, (val) => { emit('update:pageSize', val) })

type SelectableTableRef = { clearSelection?: () => void }
const channelTableRef = ref<SelectableTableRef | null>(null)

const isColumnVisible = (key: string) => props.visibleColumnKeys.includes(key)

const canPlay = (row: Record<string, unknown>) => {
  if (row.status !== 1 && Number(row.status) !== 1) return false
  const gbId = String(row?.gb_id || row?.channelId || row?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  const nonVideoTypes = ['133', '134', '135', '136', '137']
  if (nonVideoTypes.includes(typeCode)) return false
  return true
}

const playTooltip = (row: Record<string, unknown>) => {
  if (row.status !== 1 && Number(row.status) !== 1) return '通道离线'
  const gbId = String(row?.gb_id || row?.channelId || row?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  const nonVideoTypes = ['133', '134', '135', '136', '137']
  if (nonVideoTypes.includes(typeCode)) {
    if (typeCode === '133' || typeCode === '134') return '该通道为纯音频输入/输出通道，无视频流'
    if (typeCode === '135' || typeCode === '136') return '该通道为报警输入/输出节点，无法播放'
    if (typeCode === '137') return '该通道为环境监测节点，无法播放'
    return '该通道属于非视频类资源，不支持实时预览'
  }
  return '播放'
}

defineExpose({ channelTableRef })
</script>

<style scoped>
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: var(--el-fill-color-light);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 3px;
  transition: background 0.3s;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--el-text-color-placeholder);
}
.custom-table :deep(.el-table__header th.el-table__cell) {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  font-weight: 600;
  border-bottom-color: var(--el-border-color-lighter);
}
.custom-table :deep(.el-table__row) {
  height: calc((100vh - 350px) / 10);
  min-height: 48px;
}
.custom-table :deep(.el-table__row > td.el-table__cell) {
  border-bottom-color: var(--el-border-color-lighter);
  padding: 10px 0;
}
.custom-table :deep(.el-table__body tr:hover > td.el-table__cell) {
  background: var(--el-fill-color-extra-light) !important;
}
.density-compact :deep(.el-table__header th.el-table__cell) {
  padding-top: 6px;
  padding-bottom: 6px;
}
.density-compact :deep(.el-table__body td.el-table__cell) {
  padding-top: 4px;
  padding-bottom: 4px;
}
.density-comfortable :deep(.el-table__header th.el-table__cell) {
  padding-top: 10px;
  padding-bottom: 10px;
}
.density-comfortable :deep(.el-table__body td.el-table__cell) {
  padding-top: 8px;
  padding-bottom: 8px;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.online {
  background: var(--el-color-success);
  box-shadow: none;
  animation: pulse-simple 2s infinite;
}
.status-dot.offline {
  background: var(--el-border-color);
}
@keyframes pulse-simple {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.9); }
}
.more-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}
/* 修复固定列重叠/透明问题 */
:deep(.el-table__fixed-right),
:deep(.el-table__fixed) {
  height: 100% !important;
  bottom: 0 !important;
  background-color: var(--el-bg-color) !important;
  box-shadow: none;
}
:deep(.el-table__fixed-right .el-table__fixed-body-wrapper),
:deep(.el-table__fixed .el-table__fixed-body-wrapper) {
  background-color: var(--el-bg-color);
}
:deep(.el-table__fixed-right .el-table__cell),
:deep(.el-table__fixed .el-table__cell) {
  background-color: var(--el-bg-color) !important;
}
:deep(.el-table__body tr:hover > td.el-table__cell) {
  background-color: var(--el-fill-color-extra-light) !important;
}
</style>
