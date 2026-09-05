<template>
  <div class="w-80 flex flex-col bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm transition-shadow duration-200 hover:shadow-md">
    <div class="p-3 border-b border-slate-200 bg-slate-50/80 backdrop-blur-sm">
      <el-radio-group :model-value="props.treeMode" size="small" @update:model-value="(v: string | number | boolean | undefined) => { emit('update:treeMode', v as 'business' | 'region'); emit('loadTree') }">
        <el-radio-button value="business">{{ t('channelTree.businessGroup') }}</el-radio-button>
        <el-radio-button value="region">{{ t('channelTree.region') }}</el-radio-button>
      </el-radio-group>
    </div>

    <div class="flex-1 flex flex-col min-h-0">
      <div class="p-2 border-b border-slate-200 bg-white/90">
        <div class="flex gap-2 mb-2">
          <el-button size="small" @click="emit('openCreateDirectory')">
            <el-icon><Plus /></el-icon> {{ t('channelTree.createNode') }}
          </el-button>
          <el-button v-if="selectedNode?.nodeType === 'directory'" size="small" type="danger" @click="handleDeleteDirectory">
            <el-icon><Delete /></el-icon> {{ t('channelTree.delete') }}
          </el-button>
        </div>
        <el-input v-model="treeSearchKeyword" :placeholder="t('channelTree.searchPlaceholder')" size="small" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>

      <div class="flex-1 overflow-auto p-2">
        <div v-if="loadingTree" class="flex justify-center py-8">
          <el-icon class="animate-spin text-2xl text-sky-500"><Loading /></el-icon>
        </div>
        <SharedChannelTree
          v-else
          ref="treeRef"
          :data="treeData"
          :props-config="defaultProps"
          node-key="id"
          :filter-node-method="filterNode"
          :default-expanded-keys="expandedTreeKeys"
          :current-node-key="selectedNode?.id"
          :highlight-current="true"
          @node-click="emit('nodeClick', $event)"
          @node-expand="emit('nodeExpand', $event)"
          @node-collapse="emit('nodeCollapse', $event)"
          :tree-class="['channel-tree', { 'tree-contrast': highContrastTree }]"
          :folder-predicate="isChannelTreeFolderNode"
          :show-status-badge="shouldShowStatusBadge"
          :show-node-stats="shouldShowNodeStats"
          :get-node-stats="getNodeStats"
          :get-node-stats-tone="getNodeStatsTone"
          :truncate-text="true"
          :enable-context-menu="true"
          @node-contextmenu="emit('nodeContextmenu', $event)"
        />
      </div>
    </div>
  </div>

  <div
    v-if="contextMenu.visible"
    class="tree-context-menu"
    :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
    @mousedown.stop
    @click.stop
  >
    <template v-if="getContextMenuTargetType(contextMenu.node) === 'channel'">
      <div class="menu-item" v-if="canPlay(contextMenu.node)" @click="emit('playStream', contextMenu.node)">
        <el-icon class="menu-item-icon"><VideoPlay /></el-icon>
        {{ t('channelTree.play') }}
      </div>
      <div
        class="menu-item danger"
        v-if="playingChannelGbId === getChannelGbIdForNode(contextMenu.node)"
        @click="emit('closePlayer')"
      >
        <el-icon class="menu-item-icon"><CloseBold /></el-icon>
        {{ t('channelTree.stop') }}
      </div>
      <div class="menu-item" @click="emit('openRecordTab', contextMenu.node, 'cloud')"><el-icon class="menu-item-icon"><VideoCamera /></el-icon>{{ t('channelTree.cloudRecord') }}</div>
      <div class="menu-item" @click="emit('openRecordTab', contextMenu.node, 'device')"><el-icon class="menu-item-icon"><Files /></el-icon>{{ t('channelTree.deviceRecord') }}</div>
      <div class="menu-item" @click="emit('openRecordTab', contextMenu.node, 'timeline')"><el-icon class="menu-item-icon"><Timer /></el-icon>{{ t('channelTree.timeline') }}</div>
    </template>
    <template v-else>
      <div v-if="contextMenu.node?.nodeType === 'device'" class="menu-item" @click="emit('syncCatalog', contextMenu.node)"><el-icon class="menu-item-icon"><Setting /></el-icon>{{ t('channelTree.updateChannel') }}</div>
      <div class="menu-item" @click="emit('contextCreateChild')"><el-icon class="menu-item-icon"><Plus /></el-icon>{{ t('channelTree.createChildNode') }}</div>
      <div class="menu-item" @click="emit('contextRenameNode')"><el-icon class="menu-item-icon"><Edit /></el-icon>{{ t('channelTree.rename') }}</div>
      <div class="menu-item danger" @click="handleContextDeleteNode"><el-icon class="menu-item-icon"><Delete /></el-icon>{{ t('channelTree.deleteNode') }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Delete, Loading, VideoCamera, VideoPlay, CloseBold, Timer, Files, Edit, Setting, Search } from '@element-plus/icons-vue'
import SharedChannelTree from '../../components/channel/SharedChannelTree.vue'
import type { Channel, TreeNode } from '@/types/models'
import { confirmDangerous } from '../../utils/feedback'

const { t } = useI18n()

const props = defineProps<{
  treeMode: 'business' | 'region'
  loadingTree: boolean
  treeData: Channel[]
  selectedNode: Channel | null
  expandedTreeKeys: string[]
  highContrastTree: boolean
  contextMenu: { visible: boolean; x: number; y: number; node: Record<string, unknown> }
  playingChannelGbId: string
  shouldShowStatusBadge: (node: TreeNode) => boolean
  shouldShowNodeStats: (node: TreeNode) => boolean
  getNodeStats: (node: TreeNode) => any
  getNodeStatsTone: (node: TreeNode) => string
}>()

const emit = defineEmits<{
  (e: 'update:treeMode', value: 'business' | 'region'): void
  (e: 'update:treeSearchKeyword', value: string): void
  (e: 'loadTree'): void
  (e: 'openCreateDirectory'): void
  (e: 'deleteDirectory'): void
  (e: 'nodeClick', data: Record<string, unknown>): void
  (e: 'nodeExpand', data: Record<string, unknown>): void
  (e: 'nodeCollapse', data: Record<string, unknown>): void
  (e: 'nodeContextmenu', event: MouseEvent): void
  (e: 'playStream', row: Record<string, unknown>): void
  (e: 'closePlayer'): void
  (e: 'openRecordTab', row: Record<string, unknown>, tab: 'cloud' | 'device' | 'timeline'): void
  (e: 'syncCatalog', node: Record<string, unknown>): void
  (e: 'contextCreateChild'): void
  (e: 'contextRenameNode'): void
  (e: 'contextDeleteNode'): void
}>()

const treeSearchKeyword = ref('')
const defaultProps = { children: 'children', label: 'label' }

type ChannelTreeRef = {
  filter?: (keyword: string) => void
  getNode?: (key: string) => { data?: Record<string, unknown> } | null
}
const treeRef = ref<ChannelTreeRef | null>(null)

const filterNode = (value: string, data: Record<string, unknown>) => {
  if (!value) return true
  return String(data.label || '').toLowerCase().includes(value.toLowerCase())
}

const isChannelTreeFolderNode = (node: TreeNode) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  return nodeType === 'directory' || nodeType === 'root' || nodeType === 'region'
}

const shouldShowStatusBadgeLocal = (node: TreeNode) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  return ['channel', 'device'].includes(nodeType)
}

const canPlay = (row: Record<string, unknown>) => {
  if (row.status !== 1 && Number(row.status) !== 1) return false
  const gbId = String(row?.gb_id || row?.channelId || row?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  const nonVideoTypes = ['133', '134', '135', '136', '137']
  if (nonVideoTypes.includes(typeCode)) return false
  return true
}

const getChannelGbIdForNode = (node: Record<string, unknown>) => String(node?.gb_id || node?.channelId || node?.id || '').trim()

type ContextMenuTargetType = 'channel' | 'directory'
const getContextMenuTargetType = (node: Record<string, unknown>): ContextMenuTargetType => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  if (!nodeType) return 'channel'
  return nodeType === 'channel' ? 'channel' : 'directory'
}

watch(treeSearchKeyword, (val) => {
  emit('update:treeSearchKeyword', val)
  treeRef.value?.filter?.(val)
})

async function handleDeleteDirectory() {
  try {
    await confirmDangerous(t('channelTree.deleteDirectory'), String(props.selectedNode?.label || ''))
  } catch { return }
  emit('deleteDirectory')
}

async function handleContextDeleteNode() {
  try {
    await confirmDangerous(t('channelTree.deleteNodeAction'))
  } catch { return }
  emit('contextDeleteNode')
}

defineExpose({ treeRef })
</script>

<style scoped>
.channel-tree {
  background: transparent;
}
.channel-tree :deep(.el-tree-node__content) {
  height: 36px;
  border-radius: 6px;
  margin: 2px 0;
  transition: all 0.2s;
}
.channel-tree :deep(.el-tree-node__content:hover) {
  background: var(--el-fill-color-extra-light);
}
.channel-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: var(--el-color-primary-light-9);
}
.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding-right: 8px;
}
.tree-label {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tree-text {
  color: var(--el-text-color-regular);
}
.tree-status-pill {
  min-width: 44px;
  text-align: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
}
.tree-status-pill--online {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.tree-status-pill--offline {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.tree-stats-badge {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 16px;
  font-weight: 600;
}
.tree-stats-badge--good {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.tree-stats-badge--warn {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.tree-stats-badge--bad {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.tree-stats-badge--muted {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.tree-context-menu {
  position: fixed;
  z-index: 3000;
  min-width: 130px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  padding: 6px 0;
}
.menu-item-icon {
  margin-right: 6px;
}
.menu-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  display: flex;
  align-items: center;
}
.menu-item:hover {
  background: var(--el-fill-color-light);
}
.menu-item.disabled {
  color: var(--el-text-color-placeholder);
  cursor: not-allowed;
}
.menu-item.disabled:hover {
  background: transparent;
}
.menu-item.danger {
  color: var(--el-color-danger);
  font-weight: 500;
}
</style>
