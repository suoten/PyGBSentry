<template>
  <el-tree
    ref="innerTreeRef"
    :data="data"
    :props="propsConfig"
    :node-key="nodeKey"
    :filter-node-method="filterNodeMethod"
    :default-expanded-keys="defaultExpandedKeys"
    :current-node-key="currentNodeKey"
    :highlight-current="highlightCurrent"
    :default-expand-all="defaultExpandAll"
    :draggable="draggable"
    :class="treeClass"
    @node-click="onNodeClick"
    @node-expand="onNodeExpand"
    @node-collapse="onNodeCollapse"
    @node-drag-start="onNodeDragStart"
  >
    <template #default="{ node, data: nodeData }">
      <span class="custom-tree-node group">
        <span
          class="tree-label"
          @contextmenu.prevent.stop="onNodeContextmenu($event, nodeData)"
        >
          <el-icon v-if="isFolderNode(nodeData)" :class="folderIconClass">
            <Folder />
          </el-icon>
          <el-icon
            v-else
            :class="channelIconClass(nodeData)"
            :style="channelIconStyle(nodeData)"
          >
            <VideoCamera />
          </el-icon>
          <span
            class="tree-text"
            :class="treeTextClass(nodeData)"
            :style="treeTextStyle(nodeData)"
            :title="String(node?.label || '')"
          >{{ node.label }}</span>
          <span
            v-if="shouldShowNodeStats(nodeData)"
            class="tree-stats-badge"
            :class="`tree-stats-badge--${getNodeStatsToneSafe(nodeData)}`"
          >
            {{ getNodeStatsSafe(nodeData).online }}/{{ getNodeStatsSafe(nodeData).total }}
          </span>
          <span v-if="showPlayingTag && isPlayingNode(nodeData)" class="playing-tag">{{ t('sharedChannelTree.playing') }}</span>
        </span>
      </span>
    </template>
  </el-tree>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Folder, VideoCamera } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  data: Record<string, unknown>[]
  propsConfig: Record<string, unknown>
  nodeKey?: string
  filterNodeMethod?: (value: string, data: Record<string, unknown>, node?: TreeNode) => boolean
  defaultExpandedKeys?: Record<string, unknown>[]
  currentNodeKey?: string | number | null
  highlightCurrent?: boolean
  defaultExpandAll?: boolean
  draggable?: boolean
  treeClass?: string | Record<string, unknown>
  folderIconClass?: string
  folderNodeTypes?: string[]
  folderPredicate?: (data: Record<string, unknown>) => boolean
  baseChannelIconClass?: string
  showStatusBadge?: (data: Record<string, unknown>) => boolean
  showNodeStats?: (data: Record<string, unknown>) => boolean
  getNodeStats?: (data: Record<string, unknown>) => { online: number; total: number }
  getNodeStatsTone?: (data: Record<string, unknown>) => string
  showPlayingTag?: boolean
  isChannelPlaying?: (channelId: string) => boolean
  truncateText?: boolean
  enableContextMenu?: boolean
}>(), {
  nodeKey: 'id',
  defaultExpandedKeys: () => [],
  currentNodeKey: undefined,
  highlightCurrent: true,
  defaultExpandAll: false,
  draggable: false,
  treeClass: '',
  folderIconClass: 'text-amber-500',
  folderNodeTypes: () => ['directory', 'root', 'region'],
  baseChannelIconClass: 'text-emerald-500',
  showPlayingTag: false,
  truncateText: false,
  enableContextMenu: false
})

const emit = defineEmits<{
  (e: 'node-click', data: Record<string, unknown>, node: TreeNode, comp: Record<string, unknown>, ev: MouseEvent): void
  (e: 'node-expand', data: Record<string, unknown>, node: TreeNode, comp: Record<string, unknown>): void
  (e: 'node-collapse', data: Record<string, unknown>, node: TreeNode, comp: Record<string, unknown>): void
  (e: 'node-drag-start', node: TreeNode, ev: DragEvent): void
  (e: 'node-contextmenu', ev: MouseEvent, data: Record<string, unknown>): void
}>()

type InnerTreeRef = {
  filter?: (value: string) => void
  getNode?: (key: unknown) => unknown
  setCurrentKey?: (key: unknown) => void
}

const innerTreeRef = ref<InnerTreeRef | null>(null)

const isFolderNode = (data: Record<string, unknown>) => {
  if (props.folderPredicate) return !!props.folderPredicate(data)
  const nodeType = String(data?.nodeType || '').toLowerCase()
  return props.folderNodeTypes.includes(nodeType)
}

const isStatusOnline = (data: Record<string, unknown>) => Number(data?.status) === 1 || String(data?.status) === '1'

const shouldShowStatusBadge = (data: Record<string, unknown>) => {
  if (!props.showStatusBadge) return false
  return !!props.showStatusBadge(data)
}

const channelIconClass = (data: Record<string, unknown>) => {
  if (!shouldShowStatusBadge(data)) return props.baseChannelIconClass
  return isStatusOnline(data) ? '' : 'text-slate-400'
}

const channelIconStyle = (data: Record<string, unknown>) => {
  if (!shouldShowStatusBadge(data)) return undefined
  if (!isStatusOnline(data)) return undefined
  return { color: 'var(--el-color-primary)' }
}

const treeTextClass = (data: Record<string, unknown>) => {
  const classes: Array<string | false> = []
  if (props.truncateText) classes.push('truncate', 'max-w-[145px]')
  if (shouldShowStatusBadge(data)) {
    if (isStatusOnline(data)) classes.push('font-semibold')
    else classes.push('text-slate-400')
  }
  if (props.showPlayingTag && isPlayingNode(data)) classes.push('is-playing')
  return classes
}

const treeTextStyle = (data: Record<string, unknown>) => {
  if (shouldShowStatusBadge(data) && isStatusOnline(data)) {
    return { color: 'var(--el-color-primary)' }
  }
  return undefined
}

const shouldShowNodeStats = (data: Record<string, unknown>) => !!props.showNodeStats?.(data)

const getNodeStatsSafe = (data: Record<string, unknown>) => {
  const s = props.getNodeStats?.(data)
  return s || { online: 0, total: 0 }
}

const getNodeStatsToneSafe = (data: Record<string, unknown>) => props.getNodeStatsTone?.(data) || 'muted'

const isPlayingNode = (data: Record<string, unknown>) => {
  const channelId = String(data?.id || '')
  if (!channelId || !props.isChannelPlaying) return false
  return !!props.isChannelPlaying(channelId)
}

const onNodeClick = (...args: unknown[]) => emit('node-click', args[0], args[1], args[2], args[3])
const onNodeExpand = (...args: unknown[]) => emit('node-expand', args[0], args[1], args[2])
const onNodeCollapse = (...args: unknown[]) => emit('node-collapse', args[0], args[1], args[2])
const onNodeDragStart = (...args: unknown[]) => emit('node-drag-start', args[0], args[1])
const onNodeContextmenu = (ev: MouseEvent, data: Record<string, unknown>) => {
  if (!props.enableContextMenu) return
  emit('node-contextmenu', ev, data)
}

const filter = (value: string) => innerTreeRef.value?.filter?.(value)
const getNode = (key: Record<string, unknown>) => innerTreeRef.value?.getNode?.(key)
const setCurrentKey = (key: Record<string, unknown>) => innerTreeRef.value?.setCurrentKey?.(key)

defineExpose({
  filter,
  getNode,
  setCurrentKey,
  innerTreeRef
})
</script>

<style scoped>
.custom-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-width: 0;
  gap: 8px;
}
.tree-label {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
}
.tree-text {
  min-width: 0;
}
.tree-text.is-playing {
  color: var(--el-color-primary);
  font-weight: 700;
}
.playing-tag {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 9999px;
  font-size: 10px;
  font-weight: 700;
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}
.tree-stats-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  border: 1px solid transparent;
}
.tree-stats-badge--good {
  background: #ecfdf5;
  color: #047857;
  border-color: #a7f3d0;
}
.tree-stats-badge--warn {
  background: #fffbeb;
  color: #b45309;
  border-color: #fcd34d;
}
.tree-stats-badge--bad {
  background: #fef2f2;
  color: #b91c1c;
  border-color: #fecaca;
}
.tree-stats-badge--muted {
  background: #f8fafc;
  color: #64748b;
  border-color: #e2e8f0;
}
</style>
