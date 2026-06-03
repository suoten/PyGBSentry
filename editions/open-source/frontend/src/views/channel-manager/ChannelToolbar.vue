<template>
  <div class="p-3 border-b border-slate-200 bg-slate-50/80 backdrop-blur-sm flex items-center justify-between">
    <div class="flex items-center gap-2">
      <div class="w-1 h-4 rounded-full bg-sky-500"></div>
      <div class="font-semibold text-slate-700">通道列表</div>
      <el-tag v-if="selectedNode" size="small" type="info" effect="plain" round>当前：{{ selectedNodePathLabel }}</el-tag>
    </div>
    <div class="flex flex-wrap items-center gap-2 toolbar-actions">
      <div class="flex flex-wrap items-center gap-2">
        <el-input v-model="localFilters.keyword" placeholder="搜索名称 / 国标ID" clearable style="width: 220px" size="small" />
        <el-select v-model="localFilters.listScope" placeholder="列表范围" style="width: 128px" size="small" @change="emit('listScopeChange')">
          <el-option label="全部通道" value="all" />
          <el-option :label="`未挂载 (${unaddedCount})`" value="unadded" />
          <el-option label="已挂载" value="on_node" />
        </el-select>
        <el-select v-model="localFilters.status" placeholder="在线状态" clearable style="width: 112px" size="small" @change="emit('quickStatusChange')">
          <el-option label="全部" :value="undefined" />
          <el-option label="在线" :value="1" />
          <el-option label="离线" :value="0" />
        </el-select>
        <el-button size="small" @click="advancedFilterOpen = !advancedFilterOpen">
          {{ advancedFilterOpen ? '收起筛选' : '高级筛选' }}
        </el-button>
        <el-radio-group v-model="tableDensity" size="small">
          <el-radio-button value="compact">紧凑</el-radio-button>
          <el-radio-button value="comfortable">舒适</el-radio-button>
        </el-radio-group>
        <el-popover placement="bottom" :width="260" trigger="click">
          <template #reference>
            <el-button size="small">列设置</el-button>
          </template>
          <el-checkbox-group v-model="visibleColumnKeys" class="grid grid-cols-2 gap-y-2">
            <el-checkbox label="device">所属设备</el-checkbox>
            <el-checkbox label="gbId">国标ID</el-checkbox>
            <el-checkbox label="name">名称</el-checkbox>
            <el-checkbox label="vendor">厂家/型号</el-checkbox>
            <el-checkbox label="type">类型</el-checkbox>
            <el-checkbox label="status">状态</el-checkbox>
            <el-checkbox label="audio">音频</el-checkbox>
            <el-checkbox label="stream">默认码流</el-checkbox>
            <el-checkbox label="mount">挂载</el-checkbox>
            <el-checkbox label="node">所属节点</el-checkbox>
          </el-checkbox-group>
          <div class="mt-2 flex justify-end">
            <el-button link size="small" @click="resetVisibleColumns">恢复默认</el-button>
          </div>
        </el-popover>
        <el-button size="small" type="primary" @click="emit('loadChannels')">查询</el-button>
        <el-dropdown trigger="click" @command="emit('toolbarMoreCommand', $event)">
          <el-button size="small">
            更多
            <el-icon class="ml-1"><MoreFilled /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">新增通道</el-dropdown-item>
              <el-dropdown-item command="export">导出 CSV</el-dropdown-item>
              <el-dropdown-item command="reset">重置筛选</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <el-collapse-transition>
        <div v-show="advancedFilterOpen" class="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white/80 px-2 py-2">
          <div class="flex items-center gap-1">
            <el-input
              :model-value="localFilters.listCivilLabel || localFilters.listCivilPrefix || ''"
              placeholder="行政区划筛选"
              readonly
              style="width: 168px"
              size="small"
            />
            <el-button size="small" @click="emit('openListCivilFilterPicker')">选择</el-button>
            <el-button size="small" :disabled="!localFilters.listCivilPrefix" @click="emit('clearListCivilFilter')">清除</el-button>
          </div>
          <div v-if="treeMode === 'business'" class="flex items-center gap-1">
            <el-input
              :model-value="localFilters.listBusinessParentLabel || localFilters.listBusinessParentGbId || ''"
              placeholder="业务分组筛选"
              readonly
              style="width: 168px"
              size="small"
            />
            <el-button size="small" @click="emit('openListBusinessFilterPicker')">选择</el-button>
            <el-button size="small" :disabled="!localFilters.listBusinessParentGbId" @click="emit('clearListBusinessFilter')">清除</el-button>
          </div>
          <el-select v-model="localFilters.resource_type" placeholder="通道类型" clearable style="width: 140px" size="small">
            <el-option label="全部" :value="undefined" />
            <el-option label="摄像头" :value="1" />
            <el-option label="报警" :value="2" />
            <el-option label="音频" :value="3" />
          </el-select>
          <el-select
            v-model="channelStreamReset"
            placeholder="重置码流类型"
            style="width: 178px"
            size="small"
            clearable
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
          <el-button size="small" type="warning" :disabled="!channelStreamReset" @click="emit('resetVisibleChannelsStreamType')">
            应用码流重置
          </el-button>
        </div>
      </el-collapse-transition>

      <el-dropdown
        v-if="localFilters.listScope === 'all' || localFilters.listScope === 'on_node' || localFilters.listScope === 'unadded'"
        trigger="click"
        size="small"
        :disabled="selectedChannels.length === 0"
        @command="emit('batchPlacementCommand', $event)"
      >
        <el-button size="small" :disabled="selectedChannels.length === 0">
          批量操作
          <span class="text-xs opacity-80 ml-1">({{ selectedChannels.length }})</span>
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="batch_region">批量设置到行政区划节点</el-dropdown-item>
            <el-dropdown-item command="batch_business">批量设置到业务分组节点</el-dropdown-item>
            <el-dropdown-item command="clear_region" divided>批量卸下行政区划挂载</el-dropdown-item>
            <el-dropdown-item command="clear_business">批量卸下业务分组挂载</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button
        v-if="selectedNode && canAddToSelectedNode && (localFilters.listScope === 'unadded' || localFilters.listScope === 'all')"
        size="small"
        type="primary"
        @click="emit('batchAddToSelectedNode')"
        :disabled="selectedChannels.length === 0"
      >
        添加
      </el-button>
      <el-button
        v-if="selectedNode && canAddToSelectedNode && localFilters.listScope === 'on_node'"
        size="small"
        type="warning"
        @click="emit('batchRemoveFromNode')"
        :disabled="selectedChannels.length === 0"
      >
        移除
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TreeNode } from '@/types/models'
import { ref, watch, reactive } from 'vue'
import { MoreFilled, ArrowDown } from '@element-plus/icons-vue'

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
  selectedChannels: Record<string, unknown>[]
  canAddToSelectedNode: boolean
  tableDensity: 'compact' | 'comfortable'
  visibleColumnKeys: string[]
  channelStreamReset: string
  advancedFilterOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'update:filters', value: typeof props.filters): void
  (e: 'update:tableDensity', value: 'compact' | 'comfortable'): void
  (e: 'update:visibleColumnKeys', value: string[]): void
  (e: 'update:channelStreamReset', value: string): void
  (e: 'update:advancedFilterOpen', value: boolean): void
  (e: 'listScopeChange'): void
  (e: 'quickStatusChange'): void
  (e: 'loadChannels'): void
  (e: 'toolbarMoreCommand', cmd: string): void
  (e: 'openListCivilFilterPicker'): void
  (e: 'clearListCivilFilter'): void
  (e: 'openListBusinessFilterPicker'): void
  (e: 'clearListBusinessFilter'): void
  (e: 'resetVisibleChannelsStreamType'): void
  (e: 'batchPlacementCommand', cmd: string): void
  (e: 'batchAddToSelectedNode'): void
  (e: 'batchRemoveFromNode'): void
}>()

const localFilters = reactive({ ...props.filters })
const tableDensity = ref(props.tableDensity)
const visibleColumnKeys = ref([...props.visibleColumnKeys])
const channelStreamReset = ref(props.channelStreamReset)
const advancedFilterOpen = ref(props.advancedFilterOpen)

const defaultVisibleColumnKeys = ['device', 'gbId', 'name', 'vendor', 'type', 'status', 'audio', 'stream', 'mount', 'node']

const resetVisibleColumns = () => {
  visibleColumnKeys.value = [...defaultVisibleColumnKeys]
}

// Sync local → parent
watch(localFilters, (val) => { emit('update:filters', { ...val }) }, { deep: true })
watch(tableDensity, (val) => { emit('update:tableDensity', val) })
watch(visibleColumnKeys, (val) => { emit('update:visibleColumnKeys', [...val]) }, { deep: true })
watch(channelStreamReset, (val) => { emit('update:channelStreamReset', val) })
watch(advancedFilterOpen, (val) => { emit('update:advancedFilterOpen', val) })

// Sync parent → local
watch(() => props.filters, (val) => { Object.assign(localFilters, val) }, { deep: true })
watch(() => props.tableDensity, (val) => { tableDensity.value = val })
watch(() => props.visibleColumnKeys, (val) => { visibleColumnKeys.value = [...val] }, { deep: true })
watch(() => props.channelStreamReset, (val) => { channelStreamReset.value = val })
watch(() => props.advancedFilterOpen, (val) => { advancedFilterOpen.value = val })
</script>

<style scoped>
.toolbar-actions :deep(.el-button) {
  transition: all 0.18s ease;
}
.toolbar-actions :deep(.el-button:not(.is-disabled):hover) {
  transform: none;
  box-shadow: none;
}
.toolbar-actions :deep(.el-button:not(.is-disabled):active) {
  transform: translateY(0);
  box-shadow: none;
}
</style>
