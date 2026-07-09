<template>
  <div class="app-page h-full flex flex-col">
    <PageContainer flex class="flex-1 min-h-0">
      <template #header>
        <PageHeader
          :title="t('channel.manager.title')"
          :description="t('channel.manager.description')"
        >
          <template #actions>
            <el-button @click="refreshAll">{{ t('common.refresh') }}</el-button>  <!-- FIXED: i18n -->
          </template>
        </PageHeader>
      </template>
      
      <div class="flex-1 flex gap-4 overflow-hidden mt-4">
      <!-- 左侧：节点树 -->
      <div class="w-80 flex flex-col bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm transition-shadow duration-200 hover:shadow-md">
        <div class="p-3 border-b border-slate-200 bg-slate-50/80 backdrop-blur-sm">
          <el-radio-group v-model="treeMode" size="small" @change="loadTree">
            <el-radio-button value="business">{{ t('channel.manager.businessGroup') }}</el-radio-button>  <!-- FIXED: i18n -->
            <el-radio-button value="region">{{ t('channel.manager.adminRegion') }}</el-radio-button>  <!-- FIXED: i18n -->
          </el-radio-group>
        </div>
        
        <div class="flex-1 flex flex-col min-h-0">
          <div class="p-2 border-b border-slate-200 bg-white/90">
            <div class="flex gap-2 mb-2">
              <el-button size="small" @click="openCreateDirectoryDialog">
                <el-icon><Plus /></el-icon> {{ t('channel.manager.createNode') }}  <!-- FIXED: i18n -->
              </el-button>
              <el-button v-if="selectedNode?.nodeType === 'directory'" size="small" type="danger" @click="deleteDirectory">
                <el-icon><Delete /></el-icon> {{ t('channel.manager.deleteNode') }}  <!-- FIXED: i18n -->
              </el-button>
            </div>
            <el-input v-model="treeSearchKeyword" :placeholder="t('channel.manager.searchTree')" size="small" clearable>  <!-- FIXED: i18n -->
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
              @node-click="handleNodeClick"
              @node-expand="handleNodeExpand"
              @node-collapse="handleNodeCollapse"
              :tree-class="['channel-tree', { 'tree-contrast': highContrastTree }]"
              :folder-predicate="isChannelTreeFolderNode"
              :show-status-badge="shouldShowStatusBadge"
              :show-node-stats="shouldShowNodeStats"
              :get-node-stats="getNodeStats"
              :get-node-stats-tone="getNodeStatsTone"
              :truncate-text="true"
              :enable-context-menu="true"
              @node-contextmenu="openNodeContextMenu"
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
          <div class="menu-item" v-if="canPlay(contextMenu.node)" @click="playStream(contextMenu.node)">
            <el-icon class="menu-item-icon"><VideoPlay /></el-icon>
            {{ t('channel.manager.play') }}  <!-- FIXED: i18n -->
          </div>
          <div
            class="menu-item danger"
            v-if="playingChannelGbId === getChannelGbIdForNode(contextMenu.node)"
            @click="closePlayer"
          >
            <el-icon class="menu-item-icon"><CloseBold /></el-icon>
            {{ t('channel.manager.stop') }}  <!-- FIXED: i18n -->
          </div>
          <div class="menu-item" @click="openDeviceListWithRecordTab(contextMenu.node, 'cloud')"><el-icon class="menu-item-icon"><VideoCamera /></el-icon>{{ t('common.cloudRecord') }}</div>  <!-- FIXED: i18n -->
          <div class="menu-item" @click="openDeviceListWithRecordTab(contextMenu.node, 'device')"><el-icon class="menu-item-icon"><Files /></el-icon>{{ t('common.deviceRecord') }}</div>  <!-- FIXED: i18n -->
          <div class="menu-item" @click="openDeviceListWithRecordTab(contextMenu.node, 'timeline')"><el-icon class="menu-item-icon"><Timer /></el-icon>{{ t('channel.manager.timeline') }}</div>  <!-- FIXED: i18n -->
        </template>
        <template v-else>
          <div v-if="contextMenu.node?.nodeType === 'device'" class="menu-item" @click="syncCatalog(contextMenu.node)"><el-icon class="menu-item-icon"><Setting /></el-icon>{{ t('channel.manager.updateChannels') }}</div>  <!-- FIXED: i18n -->
          <div class="menu-item" @click="contextCreateChild"><el-icon class="menu-item-icon"><Plus /></el-icon>{{ t('channel.manager.addChildNode') }}</div>  <!-- FIXED: i18n -->
          <div class="menu-item" @click="contextRenameNode"><el-icon class="menu-item-icon"><Edit /></el-icon>{{ t('channel.manager.rename') }}</div>  <!-- FIXED: i18n -->
          <div class="menu-item danger" @click="contextDeleteNode"><el-icon class="menu-item-icon"><Delete /></el-icon>{{ t('channel.manager.deleteNodeLabel') }}</div>  <!-- FIXED: i18n -->
        </template>
      </div>
      
      <!-- 右侧：设备列表 -->
      <div class="flex-1 flex flex-col bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm transition-shadow duration-200 hover:shadow-md">
        <div class="p-3 border-b border-slate-200 bg-slate-50/80 backdrop-blur-sm flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="w-1 h-4 rounded-full bg-sky-500"></div>
            <div class="font-semibold text-slate-700">{{ t('channel.manager.channelList') }}</div>  <!-- FIXED: i18n -->
            <el-tag v-if="selectedNode" size="small" type="info" effect="plain" round>{{ t('channel.manager.currentLabel') }}{{ selectedNodePathLabel }}</el-tag>  <!-- FIXED: i18n -->
          </div>
          <div class="flex flex-wrap items-center gap-2 toolbar-actions">
            <div class="flex flex-wrap items-center gap-2">
              <el-input v-model="filters.keyword" :placeholder="t('channel.manager.searchName')" clearable style="width: 220px" size="small" />  <!-- FIXED: i18n -->
              <el-select v-model="filters.listScope" :placeholder="t('channel.manager.listScope')" style="width: 128px" size="small" @change="onListScopeChange">  <!-- FIXED: i18n -->
                <el-option :label="t('channel.manager.allChannels')" value="all" />  <!-- FIXED: i18n -->
                <el-option :label="`${t('channel.manager.unmounted')} (${unaddedCount})`" value="unadded" />  <!-- FIXED: i18n -->
                <el-option :label="t('channel.manager.mounted')" value="on_node" />  <!-- FIXED: i18n -->
              </el-select>
              <el-select v-model="filters.status" :placeholder="t('channel.manager.onlineStatus')" clearable style="width: 112px" size="small" @change="onQuickStatusChange">  <!-- FIXED: i18n -->
                <el-option :label="t('common.all')" :value="undefined" />  <!-- FIXED: i18n -->
                <el-option :label="t('common.online')" :value="1" />  <!-- FIXED: i18n -->
                <el-option :label="t('common.offline')" :value="0" />  <!-- FIXED: i18n -->
              </el-select>
              <el-button size="small" @click="advancedFilterOpen = !advancedFilterOpen">
                {{ advancedFilterOpen ? t('channel.manager.collapseFilter') : t('channel.manager.advancedFilter') }}  <!-- FIXED: i18n -->
              </el-button>
              <el-radio-group v-model="tableDensity" size="small">
                <el-radio-button value="compact">{{ t('channel.manager.compact') }}</el-radio-button>  <!-- FIXED: i18n -->
                <el-radio-button value="comfortable">{{ t('channel.manager.comfortable') }}</el-radio-button>  <!-- FIXED: i18n -->
              </el-radio-group>
              <el-popover placement="bottom" :width="260" trigger="click">
                <template #reference>
                  <el-button size="small">{{ t('channel.manager.columnSettings') }}</el-button>  <!-- FIXED: i18n -->
                </template>
                <el-checkbox-group v-model="visibleColumnKeys" class="grid grid-cols-2 gap-y-2">
                  <el-checkbox label="device">{{ t('channel.manager.colDevice') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="gbId">{{ t('channel.manager.colGbId') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="name">{{ t('channel.manager.colName') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="vendor">{{ t('channel.manager.colVendor') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="type">{{ t('channel.manager.colType') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="status">{{ t('channel.manager.colStatus') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="audio">{{ t('channel.manager.colAudio') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="stream">{{ t('channel.manager.colStream') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="mount">{{ t('channel.manager.colMount') }}</el-checkbox>  <!-- FIXED: i18n -->
                  <el-checkbox label="node">{{ t('channel.manager.colNode') }}</el-checkbox>  <!-- FIXED: i18n -->
                </el-checkbox-group>
                <div class="mt-2 flex justify-end">
                  <el-button link size="small" @click="resetVisibleColumns">{{ t('channel.manager.restoreDefault') }}</el-button>  <!-- FIXED: i18n -->
                </div>
              </el-popover>
              <el-button size="small" type="primary" @click="loadChannels">{{ t('common.query') }}</el-button>  <!-- FIXED: i18n -->
              <el-dropdown trigger="click" @command="handleToolbarMoreCommand">
                <el-button size="small">
                  {{ t('common.more') }}  <!-- FIXED: i18n -->
                  <el-icon class="ml-1"><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="add">{{ t('channel.manager.addChannel') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                    <el-dropdown-item command="export">{{ t('channel.manager.exportCsv') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                    <el-dropdown-item command="reset">{{ t('channel.manager.resetFilter') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <el-collapse-transition>
              <div v-show="advancedFilterOpen" class="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white/80 px-2 py-2">
                <div class="flex items-center gap-1">
                  <el-input
                    :model-value="filters.listCivilLabel || filters.listCivilPrefix || ''"
                    :placeholder="t('channel.manager.regionFilter')"
                    readonly
                    style="width: 168px"
                    size="small"
                  />
                  <el-button size="small" @click="openListCivilFilterPicker">{{ t('channel.manager.select') }}</el-button>  <!-- FIXED: i18n -->
                  <el-button size="small" :disabled="!filters.listCivilPrefix" @click="clearListCivilFilter">{{ t('channel.manager.clear') }}</el-button>  <!-- FIXED: i18n -->
                </div>
                <div v-if="treeMode === 'business'" class="flex items-center gap-1">
                  <el-input
                    :model-value="filters.listBusinessParentLabel || filters.listBusinessParentGbId || ''"
                    :placeholder="t('channel.manager.groupFilter')"
                    readonly
                    style="width: 168px"
                    size="small"
                  />
                  <el-button size="small" @click="openListBusinessFilterPicker">{{ t('channel.manager.select') }}</el-button>  <!-- FIXED: i18n -->
                  <el-button size="small" :disabled="!filters.listBusinessParentGbId" @click="clearListBusinessFilter">{{ t('channel.manager.clear') }}</el-button>  <!-- FIXED: i18n -->
                </div>
                <el-select v-model="filters.resource_type" :placeholder="t('channel.manager.channelType')" clearable style="width: 140px" size="small">  <!-- FIXED: i18n -->
                  <el-option :label="t('common.all')" :value="undefined" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.camera')" :value="1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.alarmType')" :value="2" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.audioType')" :value="3" />  <!-- FIXED: i18n -->
                </el-select>
                <el-select
                  v-model="channelStreamReset"
                  :placeholder="t('channel.manager.resetStreamType')"
                  style="width: 178px"
                  size="small"
                  clearable
                >
                  <el-option :label="t('channel.manager.mainStream')" value="main" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStream')" value="sub" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamGeneric')" value="stream:0" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamGeneric')" value="stream:1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamGB2022')" value="streamnumber:0" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamGB2022')" value="streamnumber:1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamDahua')" value="streamprofile:0" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamDahua')" value="streamprofile:1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamMercury')" value="streamMode:MAIN" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamMercury')" value="streamMode:SUB" />  <!-- FIXED: i18n -->
                </el-select>
                <el-button size="small" type="warning" :disabled="!channelStreamReset" @click="resetVisibleChannelsStreamType">
                  {{ t('channel.manager.applyStreamReset') }}  <!-- FIXED: i18n -->
                </el-button>
              </div>
            </el-collapse-transition>

            <el-dropdown
              v-if="filters.listScope === 'all' || filters.listScope === 'on_node' || filters.listScope === 'unadded'"
              trigger="click"
              size="small"
              :disabled="selectedChannels.length === 0"
              @command="onBatchPlacementCommand"
            >
              <el-button size="small" :disabled="selectedChannels.length === 0">
                {{ t('common.batchOps') }}  <!-- FIXED: i18n -->
                <span class="text-xs opacity-80 ml-1">({{ selectedChannels.length }})</span>
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="batch_region">{{ t('channel.manager.batchSetRegion') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                  <el-dropdown-item command="batch_business">{{ t('channel.manager.batchSetBusiness') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                  <el-dropdown-item command="clear_region" divided>{{ t('channel.manager.batchUnmountRegion') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                  <el-dropdown-item command="clear_business">{{ t('channel.manager.batchUnmountBusiness') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="selectedNode && canAddToSelectedNode && (filters.listScope === 'unadded' || filters.listScope === 'all')"
              size="small"
              type="primary"
              @click="batchAddToSelectedNode"
              :disabled="selectedChannels.length === 0"
            >
              {{ t('channel.manager.add') }}  <!-- FIXED: i18n -->
            </el-button>
            <el-button
              v-if="selectedNode && canAddToSelectedNode && filters.listScope === 'on_node'"
              size="small"
              type="warning"
              @click="batchRemoveFromNode"
              :disabled="selectedChannels.length === 0"
            >
              {{ t('channel.manager.remove') }}  <!-- FIXED: i18n -->
            </el-button>
          </div>
        </div>
        
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
              @selection-change="handleSelectionChange"
              @row-contextmenu="onChannelTableRowContextMenu"
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
            <el-table-column v-if="isColumnVisible('device')" prop="device_name" :label="t('channel.manager.colDevice')" width="130" show-overflow-tooltip />  <!-- FIXED: i18n -->
            <el-table-column v-if="isColumnVisible('gbId')" prop="gb_id" :label="t('channel.manager.colGbId')" width="160">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <span class="text-xs font-mono text-slate-500">{{ row.gb_id }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('name')" prop="name" :label="t('channel.manager.colName')" min-width="150" show-overflow-tooltip />  <!-- FIXED: i18n -->
            <el-table-column v-if="isColumnVisible('vendor')" :label="t('channel.manager.colVendor')" width="120" show-overflow-tooltip>  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <span class="text-xs text-slate-500">{{ row.device_manufacturer || '-' }} / {{ row.device_model || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('type')" :label="t('channel.manager.colType')" width="70" align="center">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="row.node_type === 'directory' ? 'warning' : 'info'">
                  {{ row.node_type === 'directory' ? t('channel.manager.directory') : t('channel.manager.channelLabel') }}  <!-- FIXED: i18n -->
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('status')" :label="t('channel.manager.colStatus')" width="60" align="center">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <span class="status-dot" :class="row.status === 1 ? 'online' : 'offline'"></span>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('audio')" :label="t('channel.manager.colAudio')" width="60" align="center">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <el-switch
                  v-model="row.has_audio"
                  size="small"
                  :disabled="!!channelInlineSaving[String(row.id)]"
                  @change="() => saveChannelAudioInline(row)"
                />
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('stream')" :label="t('channel.manager.colStream')" width="130" align="center">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <el-select
                  v-model="row.default_stream_type"
                  size="small"
                  style="width: 110px"
                  :disabled="!!channelInlineSaving[String(row.id)]"
                  @change="() => saveChannelStreamTypeInline(row)"
                >
                  <el-option :label="t('channel.manager.mainStream')" value="main" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStream')" value="sub" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamGeneric')" value="stream:0" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamGeneric')" value="stream:1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamGB2022')" value="streamnumber:0" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamGB2022')" value="streamnumber:1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamDahua')" value="streamprofile:0" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamDahua')" value="streamprofile:1" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.mainStreamMercury')" value="streamMode:MAIN" />  <!-- FIXED: i18n -->
                  <el-option :label="t('channel.manager.subStreamMercury')" value="streamMode:SUB" />  <!-- FIXED: i18n -->
                </el-select>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('mount')" :label="t('channel.manager.colMount')" width="80" align="center">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="catalogParentId(row) ? 'success' : 'info'">
                  {{ catalogParentId(row) ? t('channel.manager.mounted') : t('channel.manager.unmounted') }}  <!-- FIXED: i18n -->
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('node')" :label="t('channel.manager.colNode')" width="120" show-overflow-tooltip>  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <span class="text-xs text-slate-500">{{ getNodeLabel(catalogParentId(row) || undefined) }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action')" width="120" align="center">  <!-- FIXED: i18n -->
              <template #default="{ row }">
                <div class="flex items-center justify-center gap-1">
                  <el-button
                    v-if="playingChannelGbId === String(row.gb_id || '')"
                    size="small"
                    type="danger"
                    circle
                    @click.stop="closePlayer"
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
                      @click.stop="playStream(row)"
                    >
                      <el-icon><VideoPlay /></el-icon>
                    </el-button>
                  </span>
                </el-tooltip>
                  
                  <el-button size="small" circle @click.stop="openChannelEdit(row)">
                    <el-icon><Edit /></el-icon>
                  </el-button>
                  
                  <el-dropdown trigger="click" @command="handleMoreCommand(row, $event)">
                    <el-button size="small" class="more-btn">
                      <el-icon><MoreFilled /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item v-if="filters.listScope === 'on_node'" command="remove_from_node"><el-icon><Remove /></el-icon>{{ t('channel.manager.removeFromNode') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                        <el-dropdown-item v-if="filters.listScope === 'unadded' && canAddToSelectedNode" command="add_to_node"><el-icon><Plus /></el-icon>{{ t('channel.manager.addToNode') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                        <el-dropdown-item command="cloud"><el-icon><VideoCamera /></el-icon>{{ t('common.cloudRecord') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                        <el-dropdown-item command="device"><el-icon><Files /></el-icon>{{ t('common.deviceRecord') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                        <el-dropdown-item command="timeline"><el-icon><Timer /></el-icon>{{ t('channel.manager.timeline') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                        <el-dropdown-item command="reset" divided><el-icon><RefreshRight /></el-icon>{{ t('channel.manager.resetChannelInfo') }}</el-dropdown-item>  <!-- FIXED: i18n -->
                        <el-dropdown-item command="delete" class="danger"><el-icon><Delete /></el-icon>{{ t('channel.manager.deleteChannel') }}</el-dropdown-item>  <!-- FIXED: i18n -->
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
            {{ t('channel.manager.totalSelected', { total, selected: selectedChannels.length }) }}  <!-- FIXED: i18n -->
          </div>
          <div class="flex items-center gap-2">
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="total"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
              :prev-text="t('channel.manager.prevPage')"
              :next-text="t('channel.manager.nextPage')"
              size="small"
              @current-change="loadChannels"
              @size-change="() => { page = 1; loadChannels() }"
            />
          </div>
        </div>
      </div>
    </div>

        <ChannelPlayerDialog
      v-model:visible="playerVisible"
      :device-id="currentDevice?.gb_id"
      :channel-id="currentChannel?.gb_id"
      :device-name="currentDevice?.name"
      :channel-name="currentChannel?.name"
      :device-status="currentDevice?.status"
    />
    
    <!-- 通道编辑对话框 -->
    <ChannelEditDialog
      v-model:visible="channelEditDialogVisible"
      :channel-data="channelEditData"
      @success="loadChannels"
    />
    
    <!-- 创建目录对话框 -->
    <CreateDirectoryDialog
      v-model:visible="createDirectoryDialogVisible"
      :tree-data="treeData"
      :node-label-map="nodeLabelMap"
      :tree-mode="treeMode"
      :business-root-id="businessRootId"
      :init-parent-id="createDirectoryInitParentId"
      :init-region-code="createDirectoryInitRegionCode"
      @success="loadTree"
    />

    <el-dialog v-model="renameDirectoryDialogVisible" :title="t('channel.manager.renameNode')" width="420px" class="cm-rename-dialog" destroy-on-close>  <!-- FIXED: i18n -->
      <el-form :model="renameDirectoryForm" label-width="90px">
        <el-form-item :label="t('channel.manager.nodeName')">  <!-- FIXED: i18n -->
          <el-input v-model="renameDirectoryForm.name" :placeholder="t('channel.manager.enterNodeName')" />  <!-- FIXED: i18n -->
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameDirectoryDialogVisible = false">{{ t('common.cancel') }}</el-button>  <!-- FIXED: i18n -->
        <el-button type="primary" :loading="renamingDirectory" @click="renameDirectory">{{ t('common.confirm') }}</el-button>  <!-- FIXED: i18n -->
      </template>
    </el-dialog>

    <!-- 新增通道对话框 -->
    <AddChannelDialog
      v-model:visible="addChannelDialogVisible"
      @success="loadChannels"
    />

    <el-dialog v-model="civilCodeDialogVisible" :title="civilCodeDialogTitle" width="520px" class="cm-civil-code-dialog" destroy-on-close>
      <el-form :model="civilCodeForm" label-width="100px">
        <el-form-item :label="t('channel.manager.province')">  <!-- FIXED: i18n -->
          <el-select v-model="civilCodeForm.province" filterable :placeholder="t('channel.manager.selectProvinceCode')" style="width: 100%">  <!-- FIXED: i18n -->
            <el-option v-for="item in provinceOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('channel.manager.cityCode')">  <!-- FIXED: i18n -->
          <el-select v-model="civilCodeForm.city" filterable allow-create default-first-option :placeholder="t('channel.manager.selectCityCode')" style="width: 100%">  <!-- FIXED: i18n -->
            <el-option v-for="item in cityOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('channel.manager.districtCode')">  <!-- FIXED: i18n -->
          <el-select v-model="civilCodeForm.district" filterable allow-create default-first-option :placeholder="t('channel.manager.selectDistrictCode')" style="width: 100%">  <!-- FIXED: i18n -->
            <el-option v-for="item in districtOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('channel.manager.lastTwoDigits')">  <!-- FIXED: i18n -->
          <el-input v-model="civilCodeForm.suffix" maxlength="2" :placeholder="t('channel.manager.twoDigitsPlaceholder')" />  <!-- FIXED: i18n -->
        </el-form-item>
        <el-form-item :label="t('channel.manager.codePreview')">  <!-- FIXED: i18n -->
          <div class="civil-code-preview">
            <div class="preview-code">{{ civilCodePreviewDisplay }}</div>
            <div class="preview-name">{{ civilCodeNamePreview }}</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="civilCodeDialogVisible = false">{{ t('common.cancel') }}</el-button>  <!-- FIXED: i18n -->
        <el-button
          type="primary"
          :loading="batchPlacementLoading && civilPickerTarget === 'batch_region'"
          @click="applyCivilCode"
        >
          {{ civilCodeDialogConfirmLabel }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="listBusinessFilterDialogVisible" :title="t('channel.manager.filterBusinessGroup')" width="420px" class="cm-business-filter-dialog" destroy-on-close>  <!-- FIXED: i18n -->
      <div v-if="loadingBusinessPickerTree" class="py-6 flex justify-center">
        <el-icon class="animate-spin text-2xl text-sky-500"><Loading /></el-icon>
      </div>
      <el-tree
        v-else
        :data="businessPickerTreeData"
        :props="defaultProps"
        node-key="id"
        highlight-current
        default-expand-all
        class="max-h-80 overflow-auto"
        @node-click="onListBusinessFilterTreeClick"
      />
      <template #footer>
        <el-button @click="listBusinessFilterDialogVisible = false">{{ t('common.cancel') }}</el-button>  <!-- FIXED: i18n -->
        <el-button type="primary" @click="confirmListBusinessFilter">{{ t('common.ok') }}</el-button>  <!-- FIXED: i18n -->
      </template>
    </el-dialog>

    <el-dialog v-model="batchBusinessDialogVisible" :title="t('channel.manager.batchSetBusinessGroup')" width="420px" class="cm-batch-business-dialog" destroy-on-close>  <!-- FIXED: i18n -->
      <div v-if="loadingBusinessPickerTree" class="py-6 flex justify-center">
        <el-icon class="animate-spin text-2xl text-sky-500"><Loading /></el-icon>
      </div>
      <el-tree
        v-else
        :data="businessPickerTreeData"
        :props="defaultProps"
        node-key="id"
        highlight-current
        default-expand-all
        class="max-h-80 overflow-auto"
        @node-click="onBatchBusinessTreeClick"
      />
      <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">
        {{ t('channel.manager.batchBusinessHint') }}  <!-- FIXED: i18n -->
      </div>
      <template #footer>
        <el-button @click="batchBusinessDialogVisible = false">{{ t('common.cancel') }}</el-button>  <!-- FIXED: i18n -->
        <el-button type="primary" :loading="batchPlacementLoading" @click="confirmBatchBusinessPlacement">{{ t('common.ok') }}</el-button>  <!-- FIXED: i18n -->
      </template>
    </el-dialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick, reactive } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: i18n - added useI18n import
import http from '../utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Delete, Loading, Folder, VideoCamera, VideoPlay, CloseBold, MoreFilled, Timer, Files, Edit, Setting, Remove, RefreshRight, ArrowDown, Search, Rank } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import { useRouter, useRoute } from 'vue-router'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import { getFriendlyError } from '../utils/errorMessage'
import ChannelPlayerDialog from '../components/channel/ChannelPlayerDialog.vue'
import ChannelEditDialog from '../components/channel/ChannelEditDialog.vue'
import AddChannelDialog from '../components/channel/AddChannelDialog.vue'
import CreateDirectoryDialog from '../components/channel/CreateDirectoryDialog.vue'
import SharedChannelTree from '../components/channel/SharedChannelTree.vue'
import { useChannelTreeStats } from '../utils/channelTreeStats'

// P2-9: 逐步补充类型 — 定义局部接口替代 bare any
// TreeNodeData: 树节点（业务分组/行政区划/设备/通道）
interface TreeNodeData {
  id: string
  nodeType?: string
  gb_id?: string
  channelId?: string
  name?: string
  status?: number | string
  children?: TreeNodeData[]
  code?: string
  parentId?: string
  [key: string]: unknown  // 动态属性（API 返回的额外字段）
}

// ChannelRow: 通道表格行数据
interface ChannelRow {
  id: string
  gb_id?: string
  channelId?: string
  name?: string
  status?: number | string
  stream_type?: string
  audio?: string
  device_id?: string
  device_name?: string
  [key: string]: unknown  // 动态属性（API 返回的额外字段）
}

// CivilCodeOption: 行政区划选项（省/市/区）
interface CivilCodeOption {
  code: string
  name: string
  children?: CivilCodeOption[]
}

const { t } = useI18n()  // FIXED: i18n - added useI18n destructuring

const treeMode = ref<'business' | 'region'>('business')
const loadingTree = ref(false)
const treeDropHandler = async (evt: DragEvent) => {
  const toNodeEl = evt.to.closest('.el-tree-node')
  if (!toNodeEl) return
  const nodeKey = toNodeEl.dataset.key
  const targetNode = treeRef.value?.getNode(nodeKey)
  if (!targetNode || !targetNode.data) return

  const nType = String(targetNode.data.nodeType || '').toLowerCase()
  if (!['directory', 'root', 'region'].includes(nType)) {
    ElMessage.warning(t('channel.manager.dragMountOnly'))  // FIXED: 硬编码中文→t() using existing key
    return
  }

  const rowId = evt.item.dataset.rowKey
  const row = channels.value.find(c => String(c.id) === String(rowId))
  if (!row) return

  let toAdd = [row]
  if (selectedChannels.value.some(c => String(c.id) === String(rowId))) {
    toAdd = selectedChannels.value
  }

  const tid = String(targetNode.data.id || '').trim()
  const key = treeMode.value === 'region' ? 'region_parent_gb_id' : 'parent_gb_id'

  const alreadyMounted = toAdd.filter(ch => {
    const pid = key === 'region_parent_gb_id' ? ch.region_parent_gb_id : ch.parent_gb_id
    return pid && pid !== tid
  })

  if (alreadyMounted.length > 0) {
    try {
      await ElMessageBox.confirm(
        t('channel.manager.dragConfirmMsg', { total: toAdd.length, mounted: alreadyMounted.length }),  // FIXED: i18n
        t('common.tips'),  // FIXED: i18n
        {
          type: 'warning',
          confirmButtonText: t('channel.manager.continueMove'),  // FIXED: i18n
          cancelButtonText: t('common.cancel')  // FIXED: i18n
        }
      )
    } catch {
      return
    }
  }

  try {
    await http.post('/api/v1/devices/channels/batch-placement', {
      resource_ids: toAdd.map(ch => ch.id),
      placement: key === 'region_parent_gb_id' ? 'region' : 'business',
      target_id: tid
    })
    ElMessage.success(t('channel.manager.dragMountSuccess', { count: toAdd.length, name: targetNode.data.label }))  // FIXED: i18n
    toAdd.forEach(ch => {
      if (key === 'region_parent_gb_id') ch.region_parent_gb_id = tid
      else ch.parent_gb_id = tid
    })
    selectedChannels.value = []
    channelTableRef.value?.clearSelection?.()
    await loadTree()
    await loadUnaddedCount()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  }
}

let sortableInstance: Sortable | null = null
const initSortable = () => {
  const el = document.querySelector('.custom-table .el-table__body-wrapper tbody') as HTMLElement
  if (!el) return
  sortableInstance = new Sortable(el, {
    handle: '.drag-handle',
    animation: 150,
    group: {
      name: 'channels',
      pull: 'clone',
      put: false
    },
    onEnd: (evt) => {
      const itemEl = evt.item
      if (itemEl.parentNode === el) {
        // Did not drop into another list (the tree), revert visually
        const nextSibling = evt.nextSibling
        if (nextSibling) {
          el.insertBefore(itemEl, nextSibling)
        } else {
          el.appendChild(itemEl)
        }
      }
    }
  })
}
const selectedNode = ref<TreeNodeData | null>(null)
const treeRef = ref<any>(null)  // P2-9: 组件 ref 保留 any（InstanceType 过于复杂）
const expandedTreeKeys = ref<string[]>([])
const treeSearchKeyword = ref('')
// 兼容旧模板/缓存产物：保留 highContrastTree，避免运行时变量缺失
// SECURITY: 非敏感 UI 偏好（设备树状态高对比度开关）— 仅 'true'/'false'，不含敏感信息，可安全存入 localStorage
const highContrastTree = ref(localStorage.getItem('tree_status_high_contrast') === 'true')

const treeData = ref<TreeNodeData[]>([])
const {
  rebuildTreeNodeStats,
  shouldShowNodeStats,
  getNodeStats,
  getNodeStatsTone
} = useChannelTreeStats(treeData, {
  countableNodeTypes: ['channel'],
  statsVisibleNodeTypes: ['root', 'directory', 'region'],
  isPlayableChannel: (node: TreeNodeData) => {
    const nodeType = String(node?.nodeType || '').toLowerCase()
    if (nodeType !== 'channel') return false
    if (Number(node?.status) !== 1) return false
    const gbId = String(node?.id || '')
    const typeCode = gbId ? gbId.substring(10, 13) : ''
    return ['131', '132', '111', '112', '118'].includes(typeCode)
  }
})
const loading = ref(false)
const channels = ref<ChannelRow[]>([])
const selectedChannels = ref<ChannelRow[]>([])
const channelTableRef = ref<any>(null)  // P2-9: 组件 ref 保留 any
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const unaddedCount = ref(0)
const loadUnaddedCount = async () => {
  try {
    const placement = treeMode.value === 'region' ? 'region' : 'business'
    const res = await http.get('/api/v1/devices/channels/flat', {
      params: {
        placement,
        added_status: 'unadded',
        limit: 1,
        skip: 0
      }
    })
    unaddedCount.value = Number(res.data?.total || 0)
  } catch (e) {
    unaddedCount.value = 0
  }
}
const channelSnapReloadToken = ref<number>(Date.now())
const channelInlineSaving = ref<Record<string, boolean>>({})
const channelStreamReset = ref<string>('')
const advancedFilterOpen = ref(false)
const tableDensity = ref<'compact' | 'comfortable'>('comfortable')
const defaultVisibleColumnKeys = ['device', 'gbId', 'name', 'vendor', 'type', 'status', 'audio', 'stream', 'mount', 'node']
const visibleColumnKeys = ref<string[]>([...defaultVisibleColumnKeys])
const router = useRouter()

const route = useRoute()
// 实时预览（播放/停止）
const playerVisible = ref(false)
const playUrl = ref('')
const playCodec = ref('')
const playApp = ref('')
const playStreamId = ref('')
const playMode = ref<'webrtc' | 'flv' | 'hls' | 'raw'>('flv')
const playUrls = reactive<Record<string, string>>({})
const normalizePlayUrl = (value: unknown) => {
  let text = String(value || '').trim()
  while (text.length >= 2) {
    const first = text[0]
    const last = text[text.length - 1]
    if (
      (first === '`' && last === '`') ||
      (first === '"' && last === '"') ||
      (first === "'" && last === "'")
    ) {
      text = text.slice(1, -1).trim()
      continue
    }
    break
  }
  return text
}
const isSecurePage = () => window.location.protocol === 'https:'
const pickPreferredFlv = () =>
  isSecurePage()
    ? normalizePlayUrl(playUrls.wss_flv || playUrls.https_flv || playUrls.ws_flv || playUrls.flv || '')
    : normalizePlayUrl(playUrls.flv || playUrls.ws_flv || playUrls.https_flv || playUrls.wss_flv || '')
const pickPreferredHls = () =>
  isSecurePage()
    ? normalizePlayUrl(playUrls.wss_hls || playUrls.https_hls || playUrls.ws_hls || playUrls.hls || '')
    : normalizePlayUrl(playUrls.hls || playUrls.ws_hls || playUrls.https_hls || playUrls.wss_hls || '')
const pickPreferredWebrtc = () =>
  isSecurePage()
    ? normalizePlayUrl(playUrls.rtcs || playUrls.webrtc || playUrls.rtc || '')
    : normalizePlayUrl(playUrls.webrtc || playUrls.rtc || playUrls.rtcs || '')
const playingChannelGbId = ref<string>('')
const channelPlayLoading = ref<Record<string, boolean>>({})
const currentDevice = ref<TreeNodeData | null>(null)
const currentChannel = ref<ChannelRow | null>(null)
const playRequest = reactive<{
  status: 'idle' | 'requesting' | 'waiting' | 'ready' | 'error'
  stage: string
  progress: number
  message: string
  suggestion: string
  retryable: boolean
  diagnostics: Record<string, unknown>
}>({
  status: 'idle',
  stage: '',
  progress: 0,
  message: '',
  suggestion: '',
  retryable: true,
  diagnostics: {}
})
let playRequestAbort: AbortController | null = null
let playRequestInterval: ReturnType<typeof setInterval> | null = null
const playRequestTimeouts: ReturnType<typeof setTimeout>[] = []

const clearPlayRequestTimers = () => {
  if (playRequestInterval) {
    clearInterval(playRequestInterval)
    playRequestInterval = null
  }
  while (playRequestTimeouts.length) {
    const tid = playRequestTimeouts.pop()  // FIXED: 重命名t→tid避免覆盖i18n的t函数
    try {
      clearTimeout(tid)
    } catch { /* clearTimeout best-effort */ }
  }
}

const resetPlayRequest = () => {
  clearPlayRequestTimers()
  if (playRequestAbort) {
    try {
      playRequestAbort.abort()
    } catch { /* abort best-effort */ }
    playRequestAbort = null
  }
  playRequest.status = 'idle'
  playRequest.stage = ''
  playRequest.progress = 0
  playRequest.message = ''
  playRequest.suggestion = ''
  playRequest.retryable = true
  playRequest.diagnostics = {}
}

// 通道编辑
const channelEditDialogVisible = ref(false)
const channelEditData = ref<ChannelRow | null>(null)

const openChannelEdit = (row: ChannelRow) => {
  channelEditData.value = row
  channelEditDialogVisible.value = true
}

const filters = ref({
  keyword: '',
  /** 未挂载池 / 当前节点已挂载 / 全部（默认 all，表格式一览，接近参考平台通道列表） */
  listScope: 'all' as 'unadded' | 'on_node' | 'all',
  status: undefined as number | undefined,
  resource_type: undefined as number | undefined,
  /** 列表行政区码前缀筛选（传给 flat 的 civil_code_prefix，与左侧树无关） */
  listCivilPrefix: '',
  listCivilLabel: '',
  /** 业务分组筛选：父节点 gb_id（仅业务 Tab 下展示；若填写则 flat 查询优先于左侧目录节点） */
  listBusinessParentGbId: '',
  listBusinessParentLabel: ''
})
// 已移除：验收清单相关 UI/状态

const createDirectoryDialogVisible = ref(false)
const createDirectoryInitParentId = ref('')
const createDirectoryInitRegionCode = ref('')
const renameDirectoryDialogVisible = ref(false)
const renamingDirectory = ref(false)
const renameDirectoryForm = ref({
  gb_id: '',
  name: ''
})

const addChannelDialogVisible = ref(false)

const openAddChannelDialog = () => {
  addChannelDialogVisible.value = true
}

const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  node: null as TreeNodeData | null
})
const CONTEXT_MENU_WIDTH = 186
const CONTEXT_MENU_HEIGHT = 118
const civilCodeDialogVisible = ref(false)
/** create：新建目录；list_filter：通道列表行政区筛选；batch_region：批量挂到行政区 */
const civilPickerTarget = ref<'create' | 'list_filter' | 'batch_region'>('create')
const civilCodeDialogTitle = computed(() => {
  switch (civilPickerTarget.value) {
    case 'list_filter':
      return t('channel.manager.civilCodeFilter')  // FIXED: i18n
    case 'batch_region':
      return t('channel.manager.batchSetRegionCode')  // FIXED: i18n
    default:
      return t('channel.manager.generateCivilCode')  // FIXED: i18n
  }
})
const civilCodeDialogConfirmLabel = computed(() => {
  switch (civilPickerTarget.value) {
    case 'list_filter':
      return t('common.ok')  // FIXED: i18n
    case 'batch_region':
      return t('channel.manager.confirmApply')  // FIXED: i18n
    default:
      return t('channel.manager.generateAndUse')  // FIXED: i18n
  }
})

const businessPickerTreeData = ref<CivilCodeOption[]>([])
const loadingBusinessPickerTree = ref(false)
const listBusinessFilterDialogVisible = ref(false)
const listBusinessFilterPickId = ref('')
const listBusinessFilterPickLabel = ref('')
const batchBusinessDialogVisible = ref(false)
const batchBusinessPickId = ref('')
const batchPlacementLoading = ref(false)

const civilCodeForm = ref({
  province: '',
  city: '',
  district: '',
  suffix: '01'
})
const systemSipId = ref('')
const regionTreeOptions = ref<CivilCodeOption[]>([])
const provinceOptions = [
  { name: '北京', code: '11' },
  { name: '天津', code: '12' },
  { name: '河北', code: '13' },
  { name: '山西', code: '14' },
  { name: '内蒙古', code: '15' },
  { name: '辽宁', code: '21' },
  { name: '吉林', code: '22' },
  { name: '黑龙江', code: '23' },
  { name: '上海', code: '31' },
  { name: '江苏', code: '32' },
  { name: '浙江', code: '33' },
  { name: '安徽', code: '34' },
  { name: '福建', code: '35' },
  { name: '江西', code: '36' },
  { name: '山东', code: '37' },
  { name: '河南', code: '41' },
  { name: '湖北', code: '42' },
  { name: '湖南', code: '43' },
  { name: '广东', code: '44' },
  { name: '广西', code: '45' },
  { name: '海南', code: '46' },
  { name: '重庆', code: '50' },
  { name: '四川', code: '51' },
  { name: '贵州', code: '52' },
  { name: '云南', code: '53' },
  { name: '西藏', code: '54' },
  { name: '陕西', code: '61' },
  { name: '甘肃', code: '62' },
  { name: '青海', code: '63' },
  { name: '宁夏', code: '64' },
  { name: '新疆', code: '65' },
  { name: '台湾', code: '71' },
  { name: '香港', code: '81' },
  { name: '澳门', code: '82' }
]
const cityOptionsMap: Record<string, Array<{ name: string; code: string }>> = {
  '11': [{ name: '北京市', code: '01' }],
  '12': [{ name: '天津市', code: '01' }],
  '31': [{ name: '上海市', code: '01' }],
  '50': [{ name: '重庆市', code: '01' }],
  '44': [
    { name: '广州市', code: '01' },
    { name: '深圳市', code: '03' },
    { name: '珠海市', code: '04' },
    { name: '佛山市', code: '06' }
  ],
  '32': [
    { name: '南京市', code: '01' },
    { name: '无锡市', code: '02' },
    { name: '徐州市', code: '03' },
    { name: '苏州市', code: '05' }
  ],
  '33': [
    { name: '杭州市', code: '01' },
    { name: '宁波市', code: '02' },
    { name: '温州市', code: '03' }
  ]
}
const districtOptionsMap: Record<string, Array<{ name: string; code: string }>> = {
  '11-01': [
    { name: '东城区', code: '01' },
    { name: '西城区', code: '02' },
    { name: '朝阳区', code: '05' },
    { name: '海淀区', code: '08' }
  ],
  '31-01': [
    { name: '黄浦区', code: '01' },
    { name: '徐汇区', code: '04' },
    { name: '浦东新区', code: '15' }
  ],
  '44-01': [
    { name: '越秀区', code: '04' },
    { name: '天河区', code: '06' },
    { name: '白云区', code: '11' }
  ],
  '44-03': [
    { name: '罗湖区', code: '03' },
    { name: '福田区', code: '04' },
    { name: '南山区', code: '05' }
  ]
}
const fallbackCityOptions = computed(() => cityOptionsMap[civilCodeForm.value.province] || [])
const fallbackDistrictOptions = computed(() => {
  const key = `${civilCodeForm.value.province}-${civilCodeForm.value.city}`
  return districtOptionsMap[key] || []
})
const dynamicProvinceOptions = computed(() => {
  return (regionTreeOptions.value || [])
    .map((item: CivilCodeOption) => ({
      name: String(item?.name || ''),
      code: String(item?.code || '').slice(0, 2),
      children: Array.isArray(item?.children) ? item.children : []
    }))
    .filter((item: CivilCodeOption) => /^\d{2}$/.test(item.code))
})
const cityOptions = computed(() => {
  const province = dynamicProvinceOptions.value.find((item: CivilCodeOption) => item.code === civilCodeForm.value.province)
  if (!province) return fallbackCityOptions.value
  return (province.children || [])
    .map((item: CivilCodeOption) => ({
      name: String(item?.name || ''),
      code: String(item?.code || '').slice(2, 4),
      children: Array.isArray(item?.children) ? item.children : []
    }))
    .filter((item: CivilCodeOption) => /^\d{2}$/.test(item.code))
})
const districtOptions = computed(() => {
  const province = dynamicProvinceOptions.value.find((item: CivilCodeOption) => item.code === civilCodeForm.value.province)
  if (!province) return fallbackDistrictOptions.value
  const city = (province.children || []).find((item: CivilCodeOption) => String(item?.code || '').slice(2, 4) === civilCodeForm.value.city)
  if (!city) return fallbackDistrictOptions.value
  return (city.children || [])
    .map((item: CivilCodeOption) => ({
      name: String(item?.name || ''),
      code: String(item?.code || '').slice(4, 6)
    }))
    .filter((item: CivilCodeOption) => /^\d{2}$/.test(item.code))
})
const selectedProvinceName = computed(() => {
  const found = provinceOptions.find((item: CivilCodeOption) => item.code === civilCodeForm.value.province)
  return found?.name || t('channel.manager.unselectedProvince')  // FIXED: i18n
})
const selectedCityName = computed(() => {
  const found = cityOptions.value.find((item: CivilCodeOption) => item.code === civilCodeForm.value.city)
  return found?.name || (civilCodeForm.value.city ? t('channel.manager.cityCodeLabel', { code: civilCodeForm.value.city }) : t('channel.manager.unselectedCity'))  // FIXED: i18n
})
const selectedDistrictName = computed(() => {
  const found = districtOptions.value.find((item: CivilCodeOption) => item.code === civilCodeForm.value.district)
  return found?.name || (civilCodeForm.value.district ? t('channel.manager.districtCodeLabel', { code: civilCodeForm.value.district }) : t('channel.manager.unselectedDistrict'))  // FIXED: i18n
})
const civilCodePreview = computed(() => {
  const p = String(civilCodeForm.value.province || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const c = String(civilCodeForm.value.city || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const d = String(civilCodeForm.value.district || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  return `${p}${c}${d}`
})
const civilCodeSuffix = computed(() => String(civilCodeForm.value.suffix || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0'))
const civilCodePreviewDisplay = computed(() => {
  const code = civilCodePreview.value
  return `${code.slice(0, 2)} ${code.slice(2, 4)} ${code.slice(4, 6)} ${civilCodeSuffix.value}  =>  ${code}${civilCodeSuffix.value}`
})
const civilCodeNamePreview = computed(() => `${selectedProvinceName.value} / ${selectedCityName.value} / ${selectedDistrictName.value}`)

const defaultProps = {
  children: 'children',
  label: 'label'
}

const selectedNodePathLabel = computed(() => {
  if (!selectedNode.value) return ''
  const targetId = String(selectedNode.value.id || '').trim()
  if (!targetId) return selectedNode.value.label || ''
  
  const path: string[] = []
  let found = false
  
  const walk = (nodes: TreeNodeData[], currentPath: string[]) => {
    if (found) return
    for (const node of nodes || []) {
      if (found) return
      const nodeLabel = String(node?.label || '')
      const id = String(node?.id || '').trim()
      const newPath = [...currentPath, nodeLabel]
      if (id === targetId) {
        path.push(...newPath)
        found = true
        return
      }
      if (Array.isArray(node?.children) && node.children.length > 0) {
        walk(node.children, newPath)
      }
    }
  }
  
  walk(treeData.value, [])
  return path.join(' / ')
})

const nodeLabelMap = computed(() => {
  const map = new Map<string, string>()
  const walk = (nodes: TreeNodeData[]) => {
    for (const node of nodes || []) {
      const id = String(node?.id || '').trim()
      if (id) {
        map.set(id, String(node?.label || id))
      }
      if (Array.isArray(node?.children) && node.children.length > 0) {
        walk(node.children)
      }
    }
  }
  walk(treeData.value)
  return map
})

const getNodeLabel = (parentGbId?: string | null) => {
  const key = String(parentGbId || '').trim()
  if (!key) return '-'
  return nodeLabelMap.value.get(key) || key
}

const isMountableNodeType = (nodeType: string) => {
  const type = String(nodeType || '').toLowerCase()
  return type === 'directory' || type === 'root' || type === 'region'
}

const findTreeNodeById = (targetId: string): TreeNodeData | null => {
  const id = String(targetId || '').trim()
  if (!id) return null
  const stack = [...(treeData.value || [])]
  while (stack.length) {
    const current = stack.shift()
    if (!current) continue
    if (String(current.id || '').trim() === id) return current
    const children = Array.isArray(current.children) ? current.children : []
    if (children.length) stack.push(...children)
  }
  return null
}

const resolveSelectedNodeForList = (data: TreeNodeData, node?: TreeNodeData) => {
  const currentType = String(data?.nodeType || '').toLowerCase()
  if (currentType !== 'channel') return data

  // 优先取树组件里的祖先目录节点，确保右侧列表按挂载父节点展示
  let parent = node?.parent
  while (parent?.data) {
    const parentType = String(parent.data?.nodeType || '').toLowerCase()
    if (isMountableNodeType(parentType)) {
      return parent.data
    }
    parent = parent.parent
  }

  // 兜底：按通道自身挂载字段定位父节点
  const mountedId =
    treeMode.value === 'region'
      ? String(data?.region_parent_gb_id || data?.regionParentGbId || '').trim()
      : String(data?.parent_gb_id || '').trim()
  if (!mountedId) return data

  const treeNode = treeRef.value?.getNode?.(mountedId)
  if (treeNode?.data) return treeNode.data
  return findTreeNodeById(mountedId) || data
}

/** 当前 Tab（业务/行政区）下通道挂载父节点 ID */
const catalogParentId = (row: ChannelRow) => {
  const raw =
    treeMode.value === 'region'
      ? row?.region_parent_gb_id ?? row?.regionParentGbId
      : row?.parent_gb_id
  const key = String(raw || '').trim()
  if (!key) return ''
  if (nodeLabelMap.value.has(key)) return key
  return ''
}

const placementPayloadKey = computed(() =>
  treeMode.value === 'region' ? 'region_parent_gb_id' : 'parent_gb_id'
)

const onListScopeChange = () => {
  page.value = 1
  selectedChannels.value = []
  channelTableRef.value?.clearSelection?.()
  loadChannels()
}

const onQuickStatusChange = () => {
  page.value = 1
  selectedChannels.value = []
  channelTableRef.value?.clearSelection?.()
  loadChannels()
}

const isColumnVisible = (key: string) => visibleColumnKeys.value.includes(key)

const resetVisibleColumns = () => {
  visibleColumnKeys.value = [...defaultVisibleColumnKeys]
}

const handleToolbarMoreCommand = (cmd: string) => {
  if (cmd === 'add') {
    openAddChannelDialog()
    return
  }
  if (cmd === 'export') {
    exportVisibleChannelsCsv()
    return
  }
  if (cmd === 'reset') {
    resetQuickFilters()
  }
}

const resetQuickFilters = () => {
  filters.value.keyword = ''
  filters.value.listScope = 'all'
  filters.value.status = undefined
  filters.value.resource_type = undefined
  filters.value.listCivilPrefix = ''
  filters.value.listCivilLabel = ''
  filters.value.listBusinessParentGbId = ''
  filters.value.listBusinessParentLabel = ''
  channelStreamReset.value = ''
  advancedFilterOpen.value = false
  page.value = 1
  selectedChannels.value = []
  channelTableRef.value?.clearSelection?.()
  loadChannels()
}

const escapeCsvField = (v: unknown) => {
  const s = v == null ? '' : String(v)
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

/** 导出当前页可见通道（与表格一致，非全库） */
const exportVisibleChannelsCsv = () => {
  const rows = filteredChannels.value
  if (!rows.length) {
    ElMessage.warning(t('channel.manager.noExportChannels'))  // FIXED: 硬编码中文→t() using existing key
    return
  }
  const headers = [
    'device_id',
    'device_name',
    'channel_gb_id',
    'channel_name',
    'online',
    'resource_type',
    'civil_code',
    'business_parent_gb_id',
    'region_parent_gb_id',
    'current_tree',
    'mount_parent_id',
    'mount_parent_label',
    'default_stream_type',
    'has_audio'
  ]
  const treeLabel = treeMode.value === 'region' ? t('channel.manager.adminRegion') : t('channel.manager.businessGroup')  // FIXED: i18n
  const lines: string[] = [headers.join(',')]
  for (const row of rows) {
    const mountId = catalogParentId(row)
    const mountLabel = mountId ? nodeLabelMap.value.get(mountId) || mountId : ''
    lines.push(
      [
        escapeCsvField(row.device_id),
        escapeCsvField(row.device_name),
        escapeCsvField(row.gb_id),
        escapeCsvField(row.name),
        row.status === 1 ? '1' : '0',
        escapeCsvField(row.resource_type),
        escapeCsvField(row.civil_code),
        escapeCsvField(row.parent_gb_id),
        escapeCsvField(row.region_parent_gb_id),
        escapeCsvField(treeLabel),
        escapeCsvField(mountId),
        escapeCsvField(mountLabel),
        escapeCsvField(row.default_stream_type),
        row.has_audio ? '1' : '0'
      ].join(',')
    )
  }
  const blob = new Blob([`\uFEFF${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `channels_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(t('channel.manager.exportSuccess', { count: rows.length }))  // FIXED: i18n
}

const filteredChannels = computed(() => {
  return channels.value.filter(ch => {
    return true
  })
})

const tableEmptyText = computed(() => {
  if (loading.value) return t('common.loading')  // FIXED: i18n
  if (filters.value.listScope === 'on_node') return t('channel.manager.emptyOnNode')  // FIXED: i18n
  if (filters.value.listScope === 'unadded') return t('channel.manager.emptyUnadded')  // FIXED: i18n
  return t('channel.manager.emptyNoData')  // FIXED: i18n
})

const getChannelSnapSrc = (row: ChannelRow) => {
  const channelKey = String(row?.id ?? row?.gb_id ?? '').trim()
  if (!channelKey) return ''
  if (Number(row?.status) !== 1) return ''
  // 硬约束 #1: 禁止通过 URL 查询参数暴露 JWT token — 截图改由 HttpOnly cookie 认证
  // （login 已设置 access_token cookie，后端 snap 接口支持 cookie 鉴权）
  return `/api/v1/devices/channels/${encodeURIComponent(channelKey)}/snap?stream_type=auto&ts=${channelSnapReloadToken.value}`
}

const businessRootId = computed(() => {
  const root = (treeData.value && treeData.value[0]) || null
  return String(root?.id || '').trim()
})

const canAddToSelectedNode = computed(() => {
  const nodeType = String(selectedNode.value?.nodeType || '').toLowerCase()
  return nodeType === 'directory' || nodeType === 'root' || nodeType === 'region'
})

const rowSelectable = (row: ChannelRow) => {
  const scope = filters.value.listScope
  const pid = catalogParentId(row)
  // 未选左侧节点时仍可勾选（全表筛选 + 批量区划/分组）
  if (!selectedNode.value) {
    return scope === 'all' || scope === 'unadded'
  }
  const nodeType = String(selectedNode.value?.nodeType || '').toLowerCase()
  const nid = String(selectedNode.value.id || '').trim()
  const devId = String(selectedNode.value?.deviceId || '').trim() || (nodeType === 'device' ? nid : '')
  if (filters.value.listScope === 'on_node' && nodeType === 'device' && devId) {
    return String(row?.device_id || '').trim() === devId
  }
  if (filters.value.listScope === 'all' && nodeType === 'device' && devId) {
    return String(row?.device_id || '').trim() === devId
  }
  if (!canAddToSelectedNode.value) return false
  if (filters.value.listScope === 'unadded') return !pid
  if (filters.value.listScope === 'on_node') return !!pid && pid === nid
  // 全部：可选任意通道行，便于批量设置区划/业务分组
  if (filters.value.listScope === 'all') return true
  return false
}

const saveChannelAudioInline = async (row: ChannelRow) => {
  if (!row?.id) return
  const id = String(row.id)
  channelInlineSaving.value[id] = true
  try {
    await http.put(`/api/v1/devices/channels/${id}`, {
      has_audio: !!row.has_audio
    })
    ElMessage.success(t('channel.audioSwitchUpdated'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
    row.has_audio = !row.has_audio
  } finally {
    channelInlineSaving.value[id] = false
  }
}

const saveChannelStreamTypeInline = async (row: ChannelRow) => {
  if (!row?.id) return
  const id = String(row.id)
  channelInlineSaving.value[id] = true
  try {
    const v = row.default_stream_type || 'main'
    await http.put(`/api/v1/devices/channels/${id}`, {
      default_stream_type: v
    })
    row.default_stream_type = v
    ElMessage.success(t('channel.defaultStreamUpdated'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    channelInlineSaving.value[id] = false
  }
}

const resetVisibleChannelsStreamType = async () => {
  if (!channelStreamReset.value) return
  const target = channelStreamReset.value
  try {
    await ElMessageBox.confirm(t('channel.manager.batchResetConfirm', { target }), t('channel.manager.batchReset'), {  // FIXED: i18n
      confirmButtonText: t('common.confirm'),  // FIXED: i18n
      cancelButtonText: t('common.cancel'),  // FIXED: i18n
      type: 'warning',
      center: true
    })

    // FIXED: 使用Promise.allSettled防止单个失败导致整体reject
    const results = await Promise.allSettled(
      (channels.value || []).map(async ch => {
        if (!ch?.id) return
        await http.put(`/api/v1/devices/channels/${String(ch.id)}`, { default_stream_type: target })
      })
    )
    const failedCount = results.filter(r => r.status === 'rejected').length
    if (failedCount > 0) {
      ElMessage.warning(t('channel.manager.batchResetPartial', { count: failedCount }))  // FIXED: i18n
    } else {
      ElMessage.success(t('channel.streamTypeReset'))  // FIXED: 硬编码中文→i18n
    }
    channelStreamReset.value = ''
    await loadChannels()
  } catch {
    channelStreamReset.value = ''
  }
}

const getPlayerSubtitle = () => {
  if (currentDevice.value && currentChannel.value) {
    return `${currentDevice.value.name || currentDevice.value.gb_id} / ${currentChannel.value.name || currentChannel.value.gb_id}`
  }
  return ''
}

const refreshStream = async () => {
  if (currentChannel.value) {
    await playStream(currentChannel.value)
  }
}

const canPlay = (row: ChannelRow) => {
  if (row.status !== 1 && Number(row.status) !== 1) {
    return false
  }
  const gbId = String(row?.gb_id || row?.channelId || row?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  const nonVideoTypes = ['133', '134', '135', '136', '137']
  if (nonVideoTypes.includes(typeCode)) {
    return false
  }
  return true
}

const playTooltip = (row: ChannelRow) => {
  if (row.status !== 1 && Number(row.status) !== 1) {
    return t('channel.manager.channelOffline')  // FIXED: i18n
  }
  const gbId = String(row?.gb_id || row?.channelId || row?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  const nonVideoTypes = ['133', '134', '135', '136', '137']
  if (nonVideoTypes.includes(typeCode)) {
    if (typeCode === '133' || typeCode === '134') return t('channel.manager.audioOnlyChannel')  // FIXED: i18n
    if (typeCode === '135' || typeCode === '136') return t('channel.manager.alarmChannel')  // FIXED: i18n
    if (typeCode === '137') return t('channel.manager.envMonitorChannel')  // FIXED: i18n
    return t('channel.manager.nonVideoChannel')  // FIXED: i18n
  }
  return t('channel.manager.play')  // FIXED: i18n
}

const toPlayFailureText = (friendly: ReturnType<typeof getFriendlyError>) => {
  const reasonCode = String(friendly.reasonCode || '').trim()
  if (reasonCode === 'media_node_unreachable' || reasonCode === 'media_node_unavailable' || reasonCode === 'media_port_exhausted') {
    return {
      stage: t('player.mediaServerError'),  // FIXED: i18n
      message: t('player.mediaServerMsg'),  // FIXED: i18n
      suggestion: t('player.mediaServerSuggestion')  // FIXED: i18n
    }
  }
  if (reasonCode === 'invite_send_failed' || reasonCode === 'device_transport_unavailable' || reasonCode === 'sip_service_unavailable') {
    return {
      stage: t('player.deviceConnectError'),  // FIXED: i18n
      message: t('player.deviceConnectMsg'),  // FIXED: i18n
      suggestion: t('player.deviceConnectSuggestion')  // FIXED: i18n
    }
  }
  if (reasonCode === 'media_stream_not_ready') {
    return {
      stage: t('player.pullTimeout'),  // FIXED: i18n
      message: t('player.pullTimeoutMsg'),  // FIXED: i18n
      suggestion: t('player.pullTimeoutSuggestion')  // FIXED: i18n
    }
  }
  return {
    stage: t('player.playFailure'),  // FIXED: i18n
    message: friendly.message,
    suggestion: friendly.suggestion || ''
  }
}

const playStream = async (row: ChannelRow) => {
  const deviceId = String(row?.device_id || row?.deviceId || '').trim()
  const channelId = String(row?.gb_id || row?.channelId || row?.id || '').trim()
  if (!deviceId || !channelId) return

  currentChannel.value = row
  currentDevice.value = {
    gb_id: deviceId,
    name: row.device_name || deviceId
  }

  const key = channelId
  channelPlayLoading.value[key] = true
  
  // “先弹框后加载” 模式
  // 清空之前的 URL，并打上特殊标记，让播放器组件显示加载态
  for (const k of Object.keys(playUrls)) {
    playUrls[k] = ''
  }
  playCodec.value = ''
  playApp.value = ''
  playStreamId.value = ''
  playMode.value = 'flv'
  playingChannelGbId.value = channelId
  playerVisible.value = true // 立即显示弹窗
  resetPlayRequest()
  playRequest.status = 'requesting'
  playRequest.stage = t('player.sendPlayRequest')  // FIXED: i18n
  playRequest.progress = 8
  playRequest.message = t('player.requestingMsg')  // FIXED: i18n
  playRequest.suggestion = ''
  playRequest.retryable = true
  playRequest.diagnostics = { device_id: deviceId, channel_id: channelId }

  playRequestTimeouts.push(
    setTimeout(() => {
      if (playRequest.status !== 'requesting') return
      playRequest.status = 'waiting'
      playRequest.stage = t('player.waitingDevice')  // FIXED: i18n
      playRequest.progress = Math.max(playRequest.progress, 22)
      playRequest.message = t('player.waitingDeviceMsg')  // FIXED: i18n
    }, 700)
  )
  playRequestTimeouts.push(
    setTimeout(() => {
      if (playRequest.status !== 'waiting' && playRequest.status !== 'requesting') return
      playRequest.status = 'waiting'
      playRequest.stage = t('player.waitingMedia')  // FIXED: i18n
      playRequest.progress = Math.max(playRequest.progress, 48)
      playRequest.message = t('player.waitingMediaMsg')  // FIXED: i18n
    }, 2800)
  )
  playRequestInterval = setInterval(() => {
    if (playRequest.status !== 'requesting' && playRequest.status !== 'waiting') return
    const next = playRequest.progress + 2
    playRequest.progress = Math.min(92, next)
  }, 400)
  
  try {
    playRequestAbort = new AbortController()
    let res = await http.post(
      `/api/v1/stream/play/${deviceId}/${channelId}`,
      null,
      {
        params: { stream_type: 'auto', async_mode: true },
        signal: playRequestAbort.signal
      }
    )
    
    if (res.status === 202 && res.data?.data?.session_id) {
      const sessionId = res.data.data.session_id // FIXED: 非空断言!改为隐式依赖外层if守卫
      let retryCount = 0
      while (true) {
        if (playRequestAbort.signal.aborted) {
          throw new Error(t('channel.manager.requestCanceled'))  // FIXED: i18n
        }
        await new Promise(r => setTimeout(r, 600))
        const pollRes = await http.post(`/api/v1/stream/play_status`, {  // FIXED-P2: W-10 session_id从URL路径改为请求体，防止URL泄露
          session_id: sessionId,
        }, {
          signal: playRequestAbort.signal
        })
        if (pollRes.status === 202 && pollRes.data?.data?.status === 'waiting') {
          retryCount++
          if (retryCount > 40) {
            throw new Error(t('channel.manager.waitStreamTimeout'))  // FIXED: i18n
          }
          continue
        }
        res = pollRes
        break
      }
    }

    const data = res.data || {}
    playUrls.webrtc = normalizePlayUrl(data.webrtc || data.rtc)
    playUrls.rtc = normalizePlayUrl(data.rtc)
    playUrls.rtcs = normalizePlayUrl(data.rtcs)
    playUrls.webrtc_hint = normalizePlayUrl(data.webrtc_hint || data.webrtcHint)
    playUrls.flv = normalizePlayUrl(data.flv)
    playUrls.https_flv = normalizePlayUrl(data.https_flv)
    playUrls.ws_flv = normalizePlayUrl(data.ws_flv)
    playUrls.wss_flv = normalizePlayUrl(data.wss_flv)
    playUrls.hls = normalizePlayUrl(data.hls)
    playUrls.https_hls = normalizePlayUrl(data.https_hls)
    playUrls.ws_hls = normalizePlayUrl(data.ws_hls)
    playUrls.wss_hls = normalizePlayUrl(data.wss_hls)
    playUrls.fmp4 = normalizePlayUrl(data.fmp4)
    playUrls.https_fmp4 = normalizePlayUrl(data.https_fmp4)
    playUrls.ws_fmp4 = normalizePlayUrl(data.ws_fmp4)
    playUrls.wss_fmp4 = normalizePlayUrl(data.wss_fmp4)
    playUrls.preferred_url = normalizePlayUrl(data.preferred_url || data.preferredUrl)
    playCodec.value = String(res.data?.codec || '')
    playApp.value = String(res.data?.app || '')
    playStreamId.value = String(res.data?.stream || '')
    const preferredFlv = pickPreferredFlv()
    const preferredHls = pickPreferredHls()
    const preferredUrl = normalizePlayUrl(playUrls.preferred_url || '')
    const preferredLower = preferredUrl.toLowerCase()
    const preferredMode =
      preferredLower.includes('/index/api/webrtc')
        ? 'webrtc'
        : preferredLower.includes('.m3u8')
          ? 'hls'
          : preferredLower.includes('.flv')
            ? 'flv'
            : ''
    playMode.value = (preferredMode as any) || (preferredFlv ? 'flv' : preferredHls ? 'hls' : playUrls.webrtc ? 'webrtc' : 'raw')
    playUrl.value =
      playMode.value === 'webrtc'
        ? pickPreferredWebrtc()
        : playMode.value === 'flv'
        ? preferredFlv
        : playMode.value === 'hls'
          ? preferredHls
          : normalizePlayUrl(playUrls.raw)
    try {
      // 硬约束 #1: 禁止通过 URL 查询参数暴露 JWT token
      // FIX: 使用 fetch + Authorization 头加载截图，避免 token 暴露在 URL/日志/Referrer 中
      const snapUrl = `/api/v1/devices/channels/${encodeURIComponent(channelId)}/snap?stream_type=auto&prefer_existing=true&allow_invite=false&force=true&ts=${Date.now()}`
      const snapToken = sessionStorage.getItem('token') || ''
      fetch(snapUrl, { headers: { Authorization: `Bearer ${snapToken}` } })
        .then(r => r.blob())
        .then(blob => {
          const img = new Image()
          img.onload = () => {
            channelSnapReloadToken.value = Date.now()
          }
          img.src = URL.createObjectURL(blob)
          setTimeout(() => URL.revokeObjectURL(img.src), 30000)
        })
        .catch(() => { /* snap reload best-effort */ })
    } catch { /* snap reload best-effort */ }
    clearPlayRequestTimers()
    playRequestAbort = null
    playRequest.status = 'ready'
    playRequest.stage = t('player.streamReady')  // FIXED: i18n
    playRequest.progress = 100
    playRequest.message = ''
    playRequest.suggestion = ''
    playRequest.retryable = true
    playRequest.diagnostics = {}
  } catch (e: unknown) {
    clearPlayRequestTimers()
    playRequestAbort = null
    const friendly = getFriendlyError(e)
    if (String(e?.name || '').toLowerCase() === 'canceled' || String(e?.code || '') === 'ERR_CANCELED') {
      playRequest.status = 'idle'
    } else {
      const failure = toPlayFailureText(friendly)
      playRequest.status = 'error'
      playRequest.stage = failure.stage
      playRequest.progress = 100
      playRequest.message = failure.message
      playRequest.suggestion = failure.suggestion
      playRequest.retryable = Boolean(friendly.retryable ?? true)
      playRequest.diagnostics = friendly.diagnostics || {}
    }
  } finally {
    channelPlayLoading.value[key] = false
  }
}

const closePlayer = async () => {
  resetPlayRequest()
  if (playStreamId.value) {
    try {
      await http.post('/api/v1/stream/stop', { app: playApp.value || 'live', stream: playStreamId.value })
    } catch {
      // ignore
    }
  }
  playUrl.value = ''
  playCodec.value = ''
  playApp.value = ''
  playStreamId.value = ''
  playMode.value = 'webrtc'
  playUrls.webrtc = ''
  playUrls.flv = ''
  playUrls.hls = ''
  playUrls.raw = ''
  playingChannelGbId.value = ''
  playerVisible.value = false
}

const openDeviceListWithRecordTab = (row: ChannelRow, tab: 'cloud' | 'device' | 'timeline') => {
  const deviceId = String(row?.device_id || row?.deviceId || '').trim()
  const channelGbId = String(row?.gb_id || row?.channelId || row?.id || '').trim()
  if (!deviceId || !channelGbId) return
  // 对齐参考平台：点击“录像”通常以“当前时刻”为中心拉取一段时间窗口
  const nowIso = new Date().toISOString()
  router.push({
    path: '/devices',
    query: {
      device_id: deviceId,
      channel_id: channelGbId,
      tab,
      time: nowIso,
      window_minutes: 30
    }
  })
}

const getChannelGbIdForNode = (node: TreeNodeData) => String(node?.gb_id || node?.channelId || node?.id || '').trim()

type ContextMenuTargetType = 'channel' | 'directory'
const getContextMenuTargetType = (node: TreeNodeData): ContextMenuTargetType => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  if (!nodeType) return 'channel' // table row often doesn't carry nodeType
  return nodeType === 'channel' ? 'channel' : 'directory'
}

const handleMoreCommand = async (row: ChannelRow, cmd: string) => {
  if (cmd === 'remove_from_node') {
    await removeFromNode(row)
    return
  }
  if (cmd === 'add_to_node') {
    selectedChannels.value = [row]
    await batchAddToSelectedNode()
    return
  }
  if (cmd === 'reset') {
    try {
      await ElMessageBox.confirm(t('channel.manager.resetConfirmMsg'), t('common.tips'), {  // FIXED: i18n
        confirmButtonText: t('common.confirm'),  // FIXED: i18n
        cancelButtonText: t('common.cancel'),  // FIXED: i18n
        type: 'warning'
      })
      await http.post(`/api/v1/devices/channels/${row.id}/reset`)
      ElMessage.success(t('channel.channelInfoReset'))  // FIXED: 硬编码中文→i18n
      await loadChannels()
    } catch (e: unknown) {
      if (e !== 'cancel') {
        const friendly = getFriendlyError(e)
        ElMessage.error(friendly.message)
      }
    }
    return
  }
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(t('channel.manager.deleteConfirmMsg'), t('channel.manager.deleteChannel'), {  // FIXED: i18n
        confirmButtonText: t('common.confirm'),  // FIXED: i18n
        cancelButtonText: t('common.cancel'),  // FIXED: i18n
        type: 'warning'
      })
      await http.delete(`/api/v1/devices/channels/${row.id}`)
      ElMessage.success(t('channel.channelDeleted'))  // FIXED: 硬编码中文→i18n
      await loadChannels()
    } catch (e: unknown) {
      if (e !== 'cancel') {
        const friendly = getFriendlyError(e)
        ElMessage.error(friendly.message)
      }
    }
    return
  }
  // el-dropdown command 不参与 TS 类型推断，这里做一次兜底转换
  openDeviceListWithRecordTab(row, cmd as any)
}

const loadTree = async () => {
  loadingTree.value = true
  try {
    const url = treeMode.value === 'business' 
      ? '/api/v1/devices/tree/business' 
      : '/api/v1/devices/tree'
    const res = await http.get(url)
    treeData.value = Array.isArray(res.data) ? res.data : []
    rebuildTreeNodeStats()
    if (expandedTreeKeys.value.length === 0 && treeData.value.length > 0) {
      expandedTreeKeys.value = treeData.value.map((n: TreeNodeData) => String(n.id))
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    loadingTree.value = false
  }
}

const handleNodeExpand = (data: TreeNodeData) => {
  const id = String(data?.id || '').trim()
  if (id && !expandedTreeKeys.value.includes(id)) {
    expandedTreeKeys.value.push(id)
  }
}

const handleNodeCollapse = (data: TreeNodeData) => {
  const id = String(data?.id || '').trim()
  if (id) {
    expandedTreeKeys.value = expandedTreeKeys.value.filter(k => k !== id)
  }
}

const shouldShowStatusBadge = (node: TreeNodeData) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  return ['channel', 'device'].includes(nodeType)
}

const isChannelTreeFolderNode = (node: TreeNodeData) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  return nodeType === 'directory' || nodeType === 'root' || nodeType === 'region'
}

const getNodeStatusTone = (node: TreeNodeData) => {
  return Number(node?.status) === 1 ? 'online' : 'offline'
}

const getNodeStatusText = (node: TreeNodeData) => {
  return Number(node?.status) === 1 ? t('common.online') : t('common.offline')  // FIXED: i18n
}

const loadChannels = async () => {
  loading.value = true
  channelSnapReloadToken.value = Date.now()
  try {
    const placement = treeMode.value === 'region' ? 'region' : 'business'
    const scope = filters.value.listScope
    const selectedNodeType = String(selectedNode.value?.nodeType || '').toLowerCase()
    const selectedNodeId = String(selectedNode.value?.id || '').trim()
    const deviceGbId = String(selectedNode.value?.deviceId || '').trim()
    const effectiveDeviceId =
      selectedNodeType === 'device' ? (deviceGbId || selectedNodeId) : ''
    const mountable =
      !!selectedNode.value &&
      (selectedNodeType === 'directory' || selectedNodeType === 'root' || selectedNodeType === 'region')

    const params: Record<string, any> = {
      keyword: filters.value.keyword,
      placement,
      node_type: 'channel',
      status: filters.value.status,
      resource_type: filters.value.resource_type,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    }

    const cPre = String(filters.value.listCivilPrefix || '').replace(/\D/g, '')
    if (cPre) {
      params.civil_code_prefix = cPre
    }
    const listBizParent = String(filters.value.listBusinessParentGbId || '').trim()
    if (placement === 'business' && listBizParent) {
      params.parent_gb_id = listBizParent
    }

    if (scope === 'on_node') {
      if (!selectedNodeId) {
        channels.value = []
        total.value = 0
        return
      }
      if (selectedNodeType === 'device' && effectiveDeviceId) {
        params.device_id = effectiveDeviceId
      } else if (mountable && !(placement === 'business' && listBizParent)) {
        params.parent_gb_id = selectedNodeId
      } else if (mountable && placement === 'business' && listBizParent) {
        /* 已用列表业务筛选作为 parent_gb_id */
      } else if (!mountable) {
        channels.value = []
        total.value = 0
        return
      }
    } else if (scope === 'unadded') {
      params.added_status = 'unadded'
    }
    // scope === 'all'：始终显示全量通道（由筛选条件决定，不按左侧设备节点收窄）

    const res = await http.get('/api/v1/devices/channels/flat', { params })
    channels.value = Array.isArray(res.data?.items) ? res.data.items : []
    total.value = Number(res.data?.total || 0)
  } catch (e: unknown) {
    channels.value = []
    total.value = 0
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    loading.value = false
  }
}

const refreshAll = () => {
  page.value = 1
  loadTree()
  loadChannels()
  loadUnaddedCount()
}

const applyTreeNodeSelection = (data: TreeNodeData) => {
  selectedNode.value = data
  filters.value.listBusinessParentGbId = ''
  filters.value.listBusinessParentLabel = ''
  if (data && data.nodeType !== 'root') {
    filters.value.listScope = 'on_node'
  } else {
    filters.value.listScope = 'all'
  }
  page.value = 1
  selectedChannels.value = []
  channelTableRef.value?.clearSelection?.()
  loadChannels()
}

const handleNodeClick = (data: TreeNodeData, node: TreeNodeData) => {
  const target = resolveSelectedNodeForList(data, node)
  applyTreeNodeSelection(target)
}

const handleSelectionChange = (rows: ChannelRow[]) => {
  selectedChannels.value = Array.isArray(rows) ? rows : []
}

const onChannelTableRowContextMenu = (row: ChannelRow, ev: MouseEvent) => {
  ev.preventDefault()
  ev.stopPropagation()
  const maxX = Math.max(8, window.innerWidth - CONTEXT_MENU_WIDTH - 8)
  const maxY = Math.max(8, window.innerHeight - CONTEXT_MENU_HEIGHT - 8)
  const safeX = Math.min(Math.max(8, ev.clientX), maxX)
  const safeY = Math.min(Math.max(8, ev.clientY), maxY)
  contextMenu.value = {
    visible: true,
    x: safeX,
    y: safeY,
    node: row
  }
}

const onGlobalKeyDown = (e: KeyboardEvent) => {
  // 输入框/可编辑区不要抢键
  const target = e.target as HTMLElement | null
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return

  if (e.key === 'Escape') {
    // ESC：停止实时预览（如果正在播放）
    void closePlayer()
    if (contextMenu.value.visible) hideContextMenu()
    return
  }

  if (e.key !== 'Enter') return

  // Enter：如果只选中了 1 个通道，则播放
  const only = Array.isArray(selectedChannels.value) && selectedChannels.value.length === 1 ? selectedChannels.value[0] : null
  if (!only) return
  if (Number(only?.status) !== 1) return
  void playStream(only)
}

const hideContextMenu = () => {
  contextMenu.value.visible = false
}

const hideContextMenuByPointer = (ev: PointerEvent) => {
  const target = ev.target as HTMLElement | null
  if (target?.closest('.tree-context-menu')) return
  hideContextMenu()
}

const hideContextMenuByContextmenu = (ev: MouseEvent) => {
  const target = ev.target as HTMLElement | null
  if (target?.closest('.tree-context-menu')) return
  hideContextMenu()
}

const openNodeContextMenu = (ev: MouseEvent, nodeData: TreeNodeData) => {
  const nodeType = String(nodeData?.nodeType || '').toLowerCase()
  const isBusiness = treeMode.value === 'business'
  const isRegion = treeMode.value === 'region'
  // 行政区划（region tab）下也需要支持你手工创建的目录节点（directory）：
  // 系统标准区划节点（region）仍然在“重命名/删除”动作里做禁用。
  // 通道节点：右键直接打开“播放/录像”入口，不触发左侧节点切换/列表重载
  if (nodeType === 'channel') {
    const maxX = Math.max(8, window.innerWidth - CONTEXT_MENU_WIDTH - 8)
    const maxY = Math.max(8, window.innerHeight - CONTEXT_MENU_HEIGHT - 8)
    const safeX = Math.min(Math.max(8, ev.clientX), maxX)
    const safeY = Math.min(Math.max(8, ev.clientY), maxY)
    contextMenu.value = {
      visible: true,
      x: safeX,
      y: safeY,
      node: nodeData
    }
    return
  }

  const canOpen =
    (isBusiness && (nodeType === 'directory' || nodeType === 'root')) ||
    (isRegion && (nodeType === 'region' || nodeType === 'root' || nodeType === 'directory'))
  if (!canOpen) return
  applyTreeNodeSelection(nodeData)
  const maxX = Math.max(8, window.innerWidth - CONTEXT_MENU_WIDTH - 8)
  const maxY = Math.max(8, window.innerHeight - CONTEXT_MENU_HEIGHT - 8)
  const safeX = Math.min(Math.max(8, ev.clientX), maxX)
  const safeY = Math.min(Math.max(8, ev.clientY), maxY)
  contextMenu.value = {
    visible: true,
    x: safeX,
    y: safeY,
    node: nodeData
  }
}

const syncCatalog = async (node: TreeNodeData) => {
  const gbId = String(node?.deviceId || node?.id || '').trim()
  if (!gbId) return
  try {
    await http.post(`/api/v1/devices/${gbId}/sync`)
    ElMessage.success(t('channel.catalogSyncSent'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  }
}

const contextCreateChild = () => {
  const parent = contextMenu.value.node
  hideContextMenu()
  if (!parent) return
  // 下一帧再打开对话框，避免与 window 的 click 关闭菜单等逻辑抢同一轮更新
  void nextTick(() => {
    openCreateDirectoryDialog(parent)
  })
}

const contextRenameNode = () => {
  const node = contextMenu.value.node
  hideContextMenu()
  if (!node) return
  const nodeType = String(node.nodeType || '').toLowerCase()
  if (nodeType === 'region') {
    ElMessage.warning(t('channel.regionNodeCannotRename'))  // FIXED: 硬编码中文→i18n
    return
  }
  renameDirectoryForm.value = {
    gb_id: String(node.id || ''),
    name: String(node.label || '')
  }
  renameDirectoryDialogVisible.value = true
}

const contextDeleteNode = () => {
  selectedNode.value = contextMenu.value.node
  hideContextMenu()
  const nodeType = String(selectedNode.value?.nodeType || '').toLowerCase()  // FIXED: 重命名t→nodeType避免覆盖i18n的t函数
  if (nodeType === 'root') {
    ElMessage.warning(t('channel.rootGroupCannotDelete'))  // FIXED: 硬编码中文→i18n
    return
  }
  if (nodeType === 'region') {
    ElMessage.warning(t('channel.regionNodeCannotDelete'))  // FIXED: 硬编码中文→i18n
    return
  }
  deleteDirectory()
}

/** @param explicitParent 若传入则作为父节点（例如右键菜单「新增子节点」），否则使用当前选中的树节点 */
const openCreateDirectoryDialog = (explicitParent?: TreeNodeData) => {
  const parent = explicitParent !== undefined && explicitParent !== null ? explicitParent : selectedNode.value

  if (explicitParent !== undefined && explicitParent !== null) {
    selectedNode.value = explicitParent
  }

  const nodeType = String(parent?.nodeType || '').toLowerCase()
  const selectedId = String(parent?.id || '').trim()
  const regionCode = nodeType === 'region' ? selectedId.replace(/^region:/, '').replace(/\D/g, '').slice(0, 6) : ''
  const mode = treeMode.value === 'region' ? 'region' : 'business'
  const businessParentId = mode === 'business' ? (selectedId || businessRootId.value || '') : ''
  const defaultRegionParent = mode === 'region' && !selectedId ? 'region:root' : ''
  const initParentId = mode === 'business' ? businessParentId : (defaultRegionParent || (['directory', 'root', 'region'].includes(nodeType) ? selectedId : ''))
  
  createDirectoryInitParentId.value = String(initParentId || '').trim()
  createDirectoryInitRegionCode.value = mode === 'region' ? regionCode : ''
  createDirectoryDialogVisible.value = true
}

const openListCivilFilterPicker = () => {
  civilPickerTarget.value = 'list_filter'
  const fb = String(filters.value.listCivilPrefix || '').replace(/\D/g, '').slice(0, 6)
  const sip = String(systemSipId.value || '').replace(/\D/g, '').slice(0, 6)
  const base = fb.length >= 6 ? fb : sip
  civilCodeForm.value = {
    province: base.slice(0, 2),
    city: base.slice(2, 4),
    district: base.slice(4, 6),
    suffix: '01'
  }
  civilCodeDialogVisible.value = true
}

const clearListCivilFilter = () => {
  filters.value.listCivilPrefix = ''
  filters.value.listCivilLabel = ''
  page.value = 1
  loadChannels()
}

const loadBusinessPickerTree = async () => {
  loadingBusinessPickerTree.value = true
  try {
    const res = await http.get('/api/v1/devices/tree/business')
    businessPickerTreeData.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    businessPickerTreeData.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    loadingBusinessPickerTree.value = false
  }
}

const openListBusinessFilterPicker = async () => {
  listBusinessFilterPickId.value = String(filters.value.listBusinessParentGbId || '').trim()
  listBusinessFilterPickLabel.value = String(filters.value.listBusinessParentLabel || '').trim()
  listBusinessFilterDialogVisible.value = true
  await loadBusinessPickerTree()
}

const onListBusinessFilterTreeClick = (data: TreeNodeData) => {
  listBusinessFilterPickId.value = String(data?.id || '').trim()
  listBusinessFilterPickLabel.value = String(data?.label || listBusinessFilterPickId.value || '').trim()
}

const confirmListBusinessFilter = () => {
  const id = String(listBusinessFilterPickId.value || '').trim()
  if (!id) {
    ElMessage.warning(t('channel.selectGroupNode'))  // FIXED: 硬编码中文→i18n
    return
  }
  filters.value.listBusinessParentGbId = id
  filters.value.listBusinessParentLabel = String(listBusinessFilterPickLabel.value || id).trim()
  listBusinessFilterDialogVisible.value = false
  page.value = 1
  loadChannels()
}

const clearListBusinessFilter = () => {
  filters.value.listBusinessParentGbId = ''
  filters.value.listBusinessParentLabel = ''
  page.value = 1
  loadChannels()
}

const openBatchRegionPicker = () => {
  if (!selectedChannels.value.length) {
    ElMessage.warning(t('channel.selectChannelsFirst'))  // FIXED: 硬编码中文→i18n
    return
  }
  civilPickerTarget.value = 'batch_region'
  const fb = String(systemSipId.value || '').replace(/\D/g, '').slice(0, 6)
  civilCodeForm.value = {
    province: fb.slice(0, 2),
    city: fb.slice(2, 4),
    district: fb.slice(4, 6),
    suffix: '01'
  }
  civilCodeDialogVisible.value = true
}

const onBatchPlacementCommand = async (cmd: string) => {
  if (!selectedChannels.value.length) {
    ElMessage.warning(t('channel.selectChannels'))  // FIXED: 硬编码中文→i18n
    return
  }
  const ids = selectedChannels.value.map((c: ChannelRow) => String(c?.id || '').trim()).filter(Boolean)
  if (!ids.length) return

  if (cmd === 'batch_region') {
    openBatchRegionPicker()
    return
  }
  if (cmd === 'batch_business') {
    batchBusinessPickId.value = ''
    batchBusinessDialogVisible.value = true
    await loadBusinessPickerTree()
    return
  }
  if (cmd === 'clear_region') {
    try {
      await ElMessageBox.confirm(t('channel.manager.unmountRegionConfirm'), t('channel.manager.unmountRegionLabel'), {  // FIXED: i18n
        confirmButtonText: t('common.confirm'),  // FIXED: i18n
        cancelButtonText: t('common.cancel'),  // FIXED: i18n
        type: 'warning'
      })
      batchPlacementLoading.value = true
      await http.post('/api/v1/devices/channels/batch-placement', {
        resource_ids: ids,
        placement: 'region',
        target_id: ''
      })
      ElMessage.success(t('channel.regionMountRemoved'))  // FIXED: i18n
      selectedChannels.value = []
      channelTableRef.value?.clearSelection?.()
    await Promise.all([loadTree(), loadChannels(), loadUnaddedCount()])
  } catch (e: unknown) {
      if (e !== 'cancel') {
        const friendly = getFriendlyError(e)
        ElMessage.error(friendly.message)
      }
    } finally {
      batchPlacementLoading.value = false
    }
    return
  }
  if (cmd === 'clear_business') {
    try {
      await ElMessageBox.confirm(t('channel.manager.unmountBusinessConfirm'), t('channel.manager.unmountGroupLabel'), {  // FIXED: i18n
        confirmButtonText: t('common.confirm'),  // FIXED: i18n
        cancelButtonText: t('common.cancel'),  // FIXED: i18n
        type: 'warning'
      })
      batchPlacementLoading.value = true
      await http.post('/api/v1/devices/channels/batch-placement', {
        resource_ids: ids,
        placement: 'business',
        target_id: ''
      })
      ElMessage.success(t('channel.businessMountRemoved'))  // FIXED: 硬编码中文→i18n
      selectedChannels.value = []
      channelTableRef.value?.clearSelection?.()
    await Promise.all([loadTree(), loadChannels(), loadUnaddedCount()])
  } catch (e: unknown) {
      if (e !== 'cancel') {
        const friendly = getFriendlyError(e)
        ElMessage.error(friendly.message)
      }
    } finally {
      batchPlacementLoading.value = false
    }
  }
}

const handlePrimaryBatchAction = async () => {
  if (!selectedChannels.value.length) {
    ElMessage.warning(t('channel.selectChannels'))  // FIXED: 硬编码中文→i18n
    return
  }
  if (filters.value.listScope === 'on_node') {
    await batchRemoveFromNode()
    return
  }
  if (!selectedNode.value || !canAddToSelectedNode.value) {
    ElMessage.warning(t('channel.selectMountNode'))  // FIXED: 硬编码中文→i18n
    return
  }
  await batchAddToSelectedNode()
}

const onBatchBusinessTreeClick = (data: TreeNodeData) => {
  batchBusinessPickId.value = String(data?.id || '').trim()
}

const confirmBatchBusinessPlacement = async () => {
  const tid = String(batchBusinessPickId.value || '').trim()
  if (!tid) {
    ElMessage.warning(t('channel.selectBusinessGroup'))  // FIXED: 硬编码中文→i18n
    return
  }
  const ids = selectedChannels.value.map((c: ChannelRow) => String(c?.id || '').trim()).filter(Boolean)
  if (!ids.length) return
  batchPlacementLoading.value = true
  try {
    await http.post('/api/v1/devices/channels/batch-placement', {
      resource_ids: ids,
      placement: 'business',
      target_id: tid
    })
    ElMessage.success(t('channel.businessGroupSet'))  // FIXED: 硬编码中文→i18n
    batchBusinessDialogVisible.value = false
    selectedChannels.value = []
    channelTableRef.value?.clearSelection?.()
    await Promise.all([loadTree(), loadChannels(), loadUnaddedCount()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    batchPlacementLoading.value = false
  }
}

const loadRegionTreeOptions = async () => {
  try {
    const res = await http.get('/api/v1/regions/tree')
    regionTreeOptions.value = Array.isArray(res.data) ? res.data : []
  } catch {
    regionTreeOptions.value = []
  }
}

const applyCivilCode = async () => {
  if (!String(civilCodeForm.value.province || '').trim()) {
    ElMessage.warning(t('channel.selectProvince'))  // FIXED: i18n
    return
  }
  if (!String(civilCodeForm.value.city || '').trim()) {
    ElMessage.warning(t('channel.selectCity'))  // FIXED: 硬编码中文→i18n
    return
  }
  if (!String(civilCodeForm.value.district || '').trim()) {
    ElMessage.warning(t('channel.selectDistrict'))  // FIXED: 硬编码中文→i18n
    return
  }

  const target = civilPickerTarget.value
  const six = civilCodePreview.value

  if (target === 'list_filter') {
    filters.value.listCivilPrefix = six
    filters.value.listCivilLabel = civilCodeNamePreview.value
    civilCodeDialogVisible.value = false
    page.value = 1
    await loadChannels()
    return
  }

  if (target === 'batch_region') {
    if (!selectedChannels.value.length) {
      ElMessage.warning(t('channel.selectChannelsFirst'))  // FIXED: 硬编码中文→i18n
      return
    }
    const ids = selectedChannels.value.map((c: ChannelRow) => String(c?.id || '').trim()).filter(Boolean)
    if (!ids.length) return
    batchPlacementLoading.value = true
    try {
      await http.post('/api/v1/devices/channels/batch-placement', {
        resource_ids: ids,
        placement: 'region',
        target_id: `region:${six}`,
        civil_code: six
      })
      ElMessage.success(t('channel.batchRegionSet'))  // FIXED: 硬编码中文→i18n
      civilCodeDialogVisible.value = false
      selectedChannels.value = []
      channelTableRef.value?.clearSelection?.()
      await Promise.all([loadTree(), loadChannels()])
    } catch (e: unknown) {
      const friendly = getFriendlyError(e)
      ElMessage.error(friendly.message)
    } finally {
      batchPlacementLoading.value = false
    }
    return
  }

  if (!String(civilCodeForm.value.suffix || '').trim()) {
    ElMessage.warning(t('channel.enterLastTwoDigits'))  // FIXED: 硬编码中文→i18n
    return
  }
  createDirectoryForm.value.civil_code = civilCodePreview.value
  if (!String(createDirectoryForm.value.gb_id || '').trim()) {
    createDirectoryForm.value.gb_id = `${civilCodePreview.value}${civilCodeSuffix.value}`
  }
  civilCodeDialogVisible.value = false
}

const loadSystemSipId = async () => {
  try {
    const res = await http.get('/api/v1/system-config/system-info')
    systemSipId.value = String(res.data?.sip_id || '').trim()
  } catch {
    systemSipId.value = ''
  }
}



const deleteDirectory = async () => {
  if (!selectedNode.value || String(selectedNode.value.nodeType || '').toLowerCase() !== 'directory') return
  
  try {
    await ElMessageBox.confirm(t('channel.manager.deleteEmptyNode'), t('channel.manager.deleteNodeLabel'), {  // FIXED: i18n
        confirmButtonText: t('common.confirm'),  // FIXED: i18n
        cancelButtonText: t('common.cancel'),  // FIXED: i18n
      type: 'warning'
    })
    
    await http.delete('/api/v1/devices/directories', {
      data: { gb_id: selectedNode.value.id }
    })
    ElMessage.success(t('channel.nodeDeleted'))  // FIXED: 硬编码中文→i18n
    selectedNode.value = null
    loadTree()
  } catch (e: unknown) {
    if (e !== 'cancel') {
      const friendly = getFriendlyError(e)
      ElMessage.error(friendly.message)
    }
  }
}

const renameDirectory = async () => {
  const gbId = renameDirectoryForm.value.gb_id.trim()
  const name = renameDirectoryForm.value.name.trim()
  if (!gbId || !name) {
    ElMessage.warning(t('channel.fillNodeName'))  // FIXED: 硬编码中文→i18n
    return
  }
  renamingDirectory.value = true
  try {
    await http.put('/api/v1/devices/directories', { gb_id: gbId, name })
    ElMessage.success(t('channel.nodeNameUpdated'))  // FIXED: 硬编码中文→i18n
    renameDirectoryDialogVisible.value = false
    await loadTree()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    renamingDirectory.value = false
  }
}

const addToSelectedNode = async (channel: ChannelRow) => {
  if (!selectedNode.value || !canAddToSelectedNode.value) return

  try {
    const key = placementPayloadKey.value
    await http.put(`/api/v1/devices/channels/${channel.id}`, {
      [key]: selectedNode.value.id
    })
    ElMessage.success(t('channel.channelMountSuccess'))  // FIXED: 硬编码中文→i18n
    if (key === 'region_parent_gb_id') {
      channel.region_parent_gb_id = selectedNode.value.id
    } else {
      channel.parent_gb_id = selectedNode.value.id
    }
    await Promise.all([loadTree(), loadChannels()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  }
}

const batchAddToSelectedNode = async () => {
  if (!selectedNode.value || !canAddToSelectedNode.value || selectedChannels.value.length === 0) return

  const key = placementPayloadKey.value
  const nid = String(selectedNode.value.id || '').trim()
  const toAdd = selectedChannels.value

  const alreadyMounted = toAdd.filter(ch => {
    const pid = key === 'region_parent_gb_id' ? ch.region_parent_gb_id : ch.parent_gb_id
    return pid && pid !== nid
  })

  if (alreadyMounted.length > 0) {
    try {
      await ElMessageBox.confirm(
        t('channel.manager.dragConfirmMsg', { total: toAdd.length, mounted: alreadyMounted.length }),  // FIXED: i18n
        t('common.tips'),  // FIXED: i18n
        {
          type: 'warning',
          confirmButtonText: t('channel.manager.continueMove'),  // FIXED: i18n
          cancelButtonText: t('common.cancel')  // FIXED: i18n
        }
      )
    } catch {
      return
    }
  }

  try {
    await http.post('/api/v1/devices/channels/batch-placement', {
      resource_ids: toAdd.map(ch => ch.id),
      placement: key === 'region_parent_gb_id' ? 'region' : 'business',
      target_id: nid
    })
    ElMessage.success(t('channel.manager.batchAddSuccess', { count: toAdd.length }))  // FIXED: i18n
    toAdd.forEach(ch => {
      if (key === 'region_parent_gb_id') ch.region_parent_gb_id = nid
      else ch.parent_gb_id = nid
    })
    selectedChannels.value = []
    await Promise.all([loadTree(), loadChannels(), loadUnaddedCount()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  }
}

const batchRemoveFromNode = async () => {
  if (!selectedNode.value || !canAddToSelectedNode.value || selectedChannels.value.length === 0) return

  const key = placementPayloadKey.value
  const nid = String(selectedNode.value.id || '').trim()
  const toRm = selectedChannels.value.filter(ch => catalogParentId(ch) === nid)
  if (!toRm.length) {
    ElMessage.warning(t('channel.channelNotInNode'))  // FIXED: 硬编码中文→i18n
    return
  }

  try {
    await http.post('/api/v1/devices/channels/batch-placement', {
      resource_ids: toRm.map(ch => ch.id),
      placement: key === 'region_parent_gb_id' ? 'region' : 'business',
      target_id: ''
    })
    ElMessage.success(t('channel.manager.batchRemoveSuccess', { count: toRm.length }))  // FIXED: i18n
    toRm.forEach(ch => {
      if (key === 'region_parent_gb_id') ch.region_parent_gb_id = null
      else ch.parent_gb_id = null
    })
    selectedChannels.value = []
    await Promise.all([loadTree(), loadChannels(), loadUnaddedCount()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  }
}

const removeFromNode = async (channel: ChannelRow) => {
  try {
    const key = placementPayloadKey.value
    await http.put(`/api/v1/devices/channels/${channel.id}`, {
      [key]: null
    })
    ElMessage.success(t('channel.removeSuccess'))  // FIXED: 硬编码中文→i18n
    if (key === 'region_parent_gb_id') channel.region_parent_gb_id = null
    else channel.parent_gb_id = null
    await Promise.all([loadTree(), loadChannels()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  }
}

onMounted(() => {
  loadTree()
  loadChannels()
  loadUnaddedCount()
  loadSystemSipId()
  loadRegionTreeOptions()
  window.addEventListener('click', hideContextMenu)
  window.addEventListener('pointerdown', hideContextMenuByPointer)
  window.addEventListener('contextmenu', hideContextMenuByContextmenu)
  window.addEventListener('resize', hideContextMenu)
  window.addEventListener('keydown', onGlobalKeyDown)
  
  // init sortable
  setTimeout(() => {
    initSortable()
  }, 1000)

  const eid = String(route.query.edit || '').trim()
  if (eid) {
    void axios
      .get('/api/v1/devices/channels/flat', {
        params: { node_type: 'channel', limit: 800, skip: 0, placement: 'business' }
      })
      .then(res => {
        const items = Array.isArray(res.data?.items) ? res.data.items : []
        const row = items.find((x: ChannelRow) => String(x?.id || '') === eid)
        if (row) openChannelEdit(row)
      })
      .catch(() => {})
  }
})

const filterNode = (value: string, data: TreeNodeData) => {
  if (!value) return true
  return String(data.label || '').toLowerCase().includes(value.toLowerCase())
}

watch(treeSearchKeyword, (val) => {
  treeRef.value?.filter(val)
})

watch(highContrastTree, (val) => {
  localStorage.setItem('tree_status_high_contrast', val ? 'true' : 'false')
})


watch(treeMode, () => {
  selectedNode.value = null
  page.value = 1
  filters.value.listScope = 'all'
  filters.value.listBusinessParentGbId = ''
  filters.value.listBusinessParentLabel = ''
  selectedChannels.value = []
  treeSearchKeyword.value = ''
  channelTableRef.value?.clearSelection?.()
  loadChannels()
  loadUnaddedCount()
})

watch(
  () => civilCodeForm.value.province,
  () => {
    civilCodeForm.value.city = ''
    civilCodeForm.value.district = ''
  }
)

watch(
  () => civilCodeForm.value.city,
  () => {
    civilCodeForm.value.district = ''
  }
)

watch(
  () => civilCodeForm.value.suffix,
  (val) => {
    civilCodeForm.value.suffix = String(val || '').replace(/\D/g, '').slice(0, 2)
  }
)

onBeforeUnmount(() => {
  window.removeEventListener('click', hideContextMenu)
  window.removeEventListener('pointerdown', hideContextMenuByPointer)
  window.removeEventListener('contextmenu', hideContextMenuByContextmenu)
  window.removeEventListener('resize', hideContextMenu)
  window.removeEventListener('keydown', onGlobalKeyDown)
  // 离开页面时兜底停止实时预览，避免流会话占用
  try {
    if (playStreamId.value) {
      void closePlayer()
    }
  } catch {
    // ignore
  }
})
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
.civil-code-preview {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
}
.preview-code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.preview-name {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.acceptance-list {
  display: grid;
  gap: 10px;
}
.acceptance-progress {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-light);
  font-size: 13px;
  color: var(--el-text-color-regular);
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

.cm-rename-dialog :deep(.el-dialog),
.cm-civil-code-dialog :deep(.el-dialog),
.cm-business-filter-dialog :deep(.el-dialog),
.cm-batch-business-dialog :deep(.el-dialog) {
  border-radius: 10px;
}

.cm-rename-dialog :deep(.el-dialog__header),
.cm-civil-code-dialog :deep(.el-dialog__header),
.cm-business-filter-dialog :deep(.el-dialog__header),
.cm-batch-business-dialog :deep(.el-dialog__header) {
  padding: 14px 18px 12px;
  background: #f8fafc;
}

.cm-rename-dialog :deep(.el-dialog__body),
.cm-civil-code-dialog :deep(.el-dialog__body),
.cm-business-filter-dialog :deep(.el-dialog__body),
.cm-batch-business-dialog :deep(.el-dialog__body) {
  padding: 14px 18px;
}

.cm-rename-dialog :deep(.el-dialog__footer),
.cm-civil-code-dialog :deep(.el-dialog__footer),
.cm-business-filter-dialog :deep(.el-dialog__footer),
.cm-batch-business-dialog :deep(.el-dialog__footer) {
  padding: 10px 18px 14px;
  background: #fbfcfe;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(34, 197, 94, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
  }
}
</style>
