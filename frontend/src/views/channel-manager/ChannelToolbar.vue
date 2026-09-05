<template>
  <div class="p-3 border-b border-slate-200 bg-slate-50/80 backdrop-blur-sm flex items-center justify-between">
    <div class="flex items-center gap-2">
      <div class="w-1 h-4 rounded-full bg-sky-500"></div>
      <div class="font-semibold text-slate-700">{{ t('channelToolbar.channelList') }}</div>
      <el-tag v-if="selectedNode" size="small" type="info" effect="plain" round>{{ t('channelToolbar.currentLabel', { name: selectedNodePathLabel }) }}</el-tag>
    </div>
    <div class="flex flex-wrap items-center gap-2 toolbar-actions">
      <div class="flex flex-wrap items-center gap-2">
        <el-input v-model="localFilters.keyword" :placeholder="t('channelToolbar.searchPlaceholder')" clearable style="width: 220px" size="small" />
        <el-select v-model="localFilters.listScope" :placeholder="t('channelToolbar.listScope')" style="width: 128px" size="small" @change="emit('listScopeChange')">
          <el-option :label="t('channelToolbar.allChannels')" value="all" />
          <el-option :label="t('channelToolbar.unaddedWithCount', { n: unaddedCount })" value="unadded" />
          <el-option :label="t('channelToolbar.mounted')" value="on_node" />
        </el-select>
        <el-select v-model="localFilters.status" :placeholder="t('channelToolbar.onlineStatus')" clearable style="width: 112px" size="small" @change="emit('quickStatusChange')">
          <el-option :label="t('channelToolbar.all')" :value="undefined as unknown as number" />
          <el-option :label="t('channelToolbar.online')" :value="1" />
          <el-option :label="t('channelToolbar.offline')" :value="0" />
        </el-select>
        <el-button size="small" @click="advancedFilterOpen = !advancedFilterOpen">
          {{ advancedFilterOpen ? t('channelToolbar.collapseFilter') : t('channelToolbar.advancedFilter') }}
        </el-button>
        <el-radio-group v-model="tableDensity" size="small">
          <el-radio-button value="compact">{{ t('channelToolbar.compact') }}</el-radio-button>
          <el-radio-button value="comfortable">{{ t('channelToolbar.comfortable') }}</el-radio-button>
        </el-radio-group>
        <el-popover placement="bottom" :width="260" trigger="click">
          <template #reference>
            <el-button size="small">{{ t('channelToolbar.columnSettings') }}</el-button>
          </template>
          <el-checkbox-group v-model="visibleColumnKeys" class="grid grid-cols-2 gap-y-2">
            <el-checkbox label="device">{{ t('channelToolbar.colDevice') }}</el-checkbox>
            <el-checkbox label="gbId">{{ t('channelToolbar.colGbId') }}</el-checkbox>
            <el-checkbox label="name">{{ t('channelToolbar.colName') }}</el-checkbox>
            <el-checkbox label="vendor">{{ t('channelToolbar.colVendor') }}</el-checkbox>
            <el-checkbox label="type">{{ t('channelToolbar.colType') }}</el-checkbox>
            <el-checkbox label="status">{{ t('channelToolbar.colStatus') }}</el-checkbox>
            <el-checkbox label="audio">{{ t('channelToolbar.colAudio') }}</el-checkbox>
            <el-checkbox label="stream">{{ t('channelToolbar.colStream') }}</el-checkbox>
            <el-checkbox label="mount">{{ t('channelToolbar.colMount') }}</el-checkbox>
            <el-checkbox label="node">{{ t('channelToolbar.colNode') }}</el-checkbox>
          </el-checkbox-group>
          <div class="mt-2 flex justify-end">
            <el-button link size="small" @click="resetVisibleColumns">{{ t('channelToolbar.resetDefault') }}</el-button>
          </div>
        </el-popover>
        <el-button size="small" type="primary" @click="emit('loadChannels')">{{ t('channelToolbar.query') }}</el-button>
        <el-dropdown trigger="click" @command="emit('toolbarMoreCommand', $event)">
          <el-button size="small">
            {{ t('channelToolbar.more') }}
            <el-icon class="ml-1"><MoreFilled /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">{{ t('channelToolbar.addChannel') }}</el-dropdown-item>
              <el-dropdown-item command="export">{{ t('channelToolbar.exportCsv') }}</el-dropdown-item>
              <el-dropdown-item command="reset">{{ t('channelToolbar.resetFilter') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <el-collapse-transition>
        <div v-show="advancedFilterOpen" class="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white/80 px-2 py-2">
          <div class="flex items-center gap-1">
            <el-input
              :model-value="localFilters.listCivilLabel || localFilters.listCivilPrefix || ''"
              :placeholder="t('channelToolbar.civilCodeFilter')"
              readonly
              style="width: 168px"
              size="small"
            />
            <el-button size="small" @click="emit('openListCivilFilterPicker')">{{ t('channelToolbar.select') }}</el-button>
            <el-button size="small" :disabled="!localFilters.listCivilPrefix" @click="emit('clearListCivilFilter')">{{ t('channelToolbar.clear') }}</el-button>
          </div>
          <div v-if="treeMode === 'business'" class="flex items-center gap-1">
            <el-input
              :model-value="localFilters.listBusinessParentLabel || localFilters.listBusinessParentGbId || ''"
              :placeholder="t('channelToolbar.businessGroupFilter')"
              readonly
              style="width: 168px"
              size="small"
            />
            <el-button size="small" @click="emit('openListBusinessFilterPicker')">{{ t('channelToolbar.select') }}</el-button>
            <el-button size="small" :disabled="!localFilters.listBusinessParentGbId" @click="emit('clearListBusinessFilter')">{{ t('channelToolbar.clear') }}</el-button>
          </div>
          <el-select v-model="localFilters.resource_type" :placeholder="t('channelToolbar.channelType')" clearable style="width: 140px" size="small">
            <el-option :label="t('channelToolbar.all')" :value="undefined as unknown as number" />
            <el-option :label="t('channelToolbar.camera')" :value="1" />
            <el-option :label="t('channelToolbar.alarm')" :value="2" />
            <el-option :label="t('channelToolbar.audio')" :value="3" />
          </el-select>
          <el-select
            v-model="channelStreamReset"
            :placeholder="t('channelToolbar.resetStreamType')"
            style="width: 178px"
            size="small"
            clearable
          >
            <el-option :label="t('channelToolbar.streamMain')" value="main" />
            <el-option :label="t('channelToolbar.streamSub')" value="sub" />
            <el-option :label="t('channelToolbar.streamMainGeneric')" value="stream:0" />
            <el-option :label="t('channelToolbar.streamSubGeneric')" value="stream:1" />
            <el-option :label="t('channelToolbar.streamMainGb2022')" value="streamnumber:0" />
            <el-option :label="t('channelToolbar.streamSubGb2022')" value="streamnumber:1" />
            <el-option :label="t('channelToolbar.streamMainDahua')" value="streamprofile:0" />
            <el-option :label="t('channelToolbar.streamSubDahua')" value="streamprofile:1" />
            <el-option :label="t('channelToolbar.streamMainMercury')" value="streamMode:MAIN" />
            <el-option :label="t('channelToolbar.streamSubMercury')" value="streamMode:SUB" />
          </el-select>
          <el-button size="small" type="warning" :disabled="!channelStreamReset" @click="emit('resetVisibleChannelsStreamType')">
            {{ t('channelToolbar.applyStreamReset') }}
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
          {{ t('channelToolbar.batchOps') }}
          <span class="text-xs opacity-80 ml-1">({{ selectedChannels.length }})</span>
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="batch_region">{{ t('channelToolbar.batchSetRegion') }}</el-dropdown-item>
            <el-dropdown-item command="batch_business">{{ t('channelToolbar.batchSetBusiness') }}</el-dropdown-item>
            <el-dropdown-item command="clear_region" divided>{{ t('channelToolbar.batchUnmountRegion') }}</el-dropdown-item>
            <el-dropdown-item command="clear_business">{{ t('channelToolbar.batchUnmountBusiness') }}</el-dropdown-item>
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
        {{ t('channelToolbar.add') }}
      </el-button>
      <el-button
        v-if="selectedNode && canAddToSelectedNode && localFilters.listScope === 'on_node'"
        size="small"
        type="warning"
        @click="emit('batchRemoveFromNode')"
        :disabled="selectedChannels.length === 0"
      >
        {{ t('channelToolbar.remove') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TreeNode } from '@/types/models'
import { ref, watch, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { MoreFilled, ArrowDown } from '@element-plus/icons-vue'

const { t } = useI18n()

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
