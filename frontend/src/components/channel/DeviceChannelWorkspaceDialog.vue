<template>
  <el-dialog
    :model-value="modelValue"
    width="88%"
    class="channels-dialog"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <template #header>
      <div class="channels-dialog-header">
        <div class="channels-dialog-title-group">
          <div class="channels-dialog-title">通道工作区</div>
          <div class="channels-dialog-subtitle">
            {{ currentDevice?.name || currentDevice?.gb_id || '未选择设备' }}
          </div>
        </div>
        <div class="channels-dialog-metrics">
          <span class="channels-dialog-metric">
            <strong>{{ channelTotal }}</strong>
            通道
          </span>
          <span class="channels-dialog-metric">
            <strong>{{ channelOnlineTotal }}</strong>
            在线
          </span>
        </div>
      </div>
    </template>

    <div class="channel-context-bar">
      <div class="channel-context-info">
        <span class="channel-context-chip channel-context-device">设备：{{ currentDevice?.name || currentDevice?.gb_id || '未选择设备' }}</span>
        <span class="channel-context-chip channel-context-channel">通道：{{ currentChannel?.name || currentChannel?.gb_id || '请选择通道进行预览/录像' }}</span>
      </div>
      <div class="channel-context-actions">
        <el-tooltip :content="playTooltip?.(currentChannel)" placement="top">
          <span>
            <el-button
              size="small"
              type="primary"
              class="context-btn context-btn--primary"
              :disabled="!canPreviewChannel?.(currentChannel)"
              @click="playStream?.(currentChannel)"
            >
              <el-icon class="mr-1"><VideoPlay /></el-icon>
              实时预览
            </el-button>
          </span>
        </el-tooltip>
      </div>
    </div>

    <div class="channels-toolbar dialog-toolbar mt-3">
      <div class="dialog-toolbar-title">通道筛选</div>
      <div class="dialog-toolbar-actions">
        <el-input
          v-model="localFilters.keyword"
          placeholder="搜索通道ID/名称"
          clearable
          size="small"
          style="width: 240px"
        />
        <el-select
          v-model="localFilters.status"
          placeholder="在线状态"
          clearable
          size="small"
          style="width: 140px"
        >
          <el-option label="全部" :value="undefined" />
          <el-option label="在线" :value="1" />
          <el-option label="离线" :value="0" />
        </el-select>
        <el-select
          v-model="localFilters.resource_type"
          placeholder="通道类型"
          clearable
          size="small"
          style="width: 140px"
        >
          <el-option label="全部" :value="undefined" />
          <el-option label="摄像头" :value="1" />
          <el-option label="报警" :value="2" />
          <el-option label="音频" :value="3" />
        </el-select>
        <el-select
          v-model="channelStreamResetModel"
          placeholder="重置码流类型"
          size="small"
          style="width: 180px"
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
        <el-tooltip
          :content="channelStreamReset ? '将当前页可见通道默认码流重置为所选类型' : '请选择重置码流类型后再执行重置'"
          placement="top"
        >
          <span>
            <el-button size="small" type="warning" :disabled="!channelStreamReset" @click="resetVisibleChannelsStreamType?.()">
              应用码流
            </el-button>
          </span>
        </el-tooltip>
        <el-button size="small" type="primary" @click="loadChannelsDialog?.()">查询</el-button>
        <el-button size="small" @click="resetChannelDialogFilters?.()">重置</el-button>
        <el-button size="small" :loading="refreshingSnapshots" @click="refreshChannelSnapshots?.()">
          刷新快照
        </el-button>
      </div>
    </div>

    <el-table
      :data="channels"
      style="width: 100%; margin-top: 12px"
      :empty-text="'该设备暂无通道'"
      class="channels-table"
      size="small"
      header-row-class-name="channels-table-header-row"
      :row-class-name="getChannelRowClassName"
      row-key="gb_id"
      fit
      v-loading="channelsLoading"
    >
      <el-table-column prop="gb_id" label="通道国标ID" width="180">
        <template #default="scope">
          <div class="channel-id-cell">
            <el-tag size="small" type="info" effect="plain">{{ scope.row.gb_id }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="快照" width="110" align="center">
        <template #default="scope">
          <el-image
            :src="getChannelSnapSrc?.(scope.row)"
            :preview-src-list="getChannelSnapSrc?.(scope.row) ? [getChannelSnapSrc?.(scope.row)] : []"
            :initial-index="0"
            :z-index="9999"
            style="width: 90px; height: 50px"
            fit="cover"
            class="rounded shadow-sm cursor-zoom-in channel-snap-image"
            preview-teleported
            :hide-on-click-modal="true"
          >
            <template #error>
              <div class="text-slate-400 text-[10px] bg-slate-50 w-full h-full flex items-center justify-center">无快照</div>
            </template>
          </el-image>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
      <el-table-column label="预览" width="90" align="center">
        <template #default="scope">
          <div class="preview-status-cell">
            <template v-if="channelStreamStatusLoading">
              <el-icon class="is-loading" style="font-size: 14px; color: #94a3b8;"><Loading /></el-icon>
            </template>
            <template v-else-if="getChannelPreviewStatus">
              <el-tooltip :content="getChannelPreviewStatus(scope.row)?.label || ''" placement="top">
                <el-tag
                  size="small"
                  :type="getChannelPreviewStatus(scope.row)?.type || 'info'"
                  effect="light"
                  style="cursor: default; font-size: 11px;"
                >
                  <el-icon style="margin-right: 3px;" :size="10">
                    <VideoPlay v-if="getChannelPreviewStatus(scope.row)?.icon === 'VideoPlay'" />
                    <Microphone v-else-if="getChannelPreviewStatus(scope.row)?.icon === 'Microphone'" />
                    <CloseBold v-else-if="getChannelPreviewStatus(scope.row)?.icon === 'CloseBold'" />
                    <Warning v-else-if="getChannelPreviewStatus(scope.row)?.icon === 'Warning'" />
                    <InfoFilled v-else />
                  </el-icon>
                  {{ getChannelPreviewStatus(scope.row)?.label || '未知' }}
                </el-tag>
              </el-tooltip>
            </template>
            <template v-else>
              <el-tag size="small" type="info" effect="light" style="cursor: default; font-size: 11px;">
                <el-icon style="margin-right: 3px;" :size="10"><InfoFilled /></el-icon>
                未知
              </el-tag>
            </template>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="厂家" prop="device_manufacturer" width="100" show-overflow-tooltip />
      <el-table-column label="类型" width="80" align="center">
        <template #default="scope">
          <el-tooltip :content="`通道类型：${getResourceTypeLabel?.(scope.row)}`" placement="top">
            <span>
              <el-tag size="small" :type="getResourceTypeTagType?.(scope.row)" effect="plain">
                {{ getResourceTypeLabel?.(scope.row) }}
              </el-tag>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="云台类型" width="90" align="center">
        <template #default="scope">
          <el-tag size="small" effect="plain" :type="getPtzTypeTagType?.(scope.row)">
            {{ getPtzTypeLabel?.(scope.row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="位置" width="120">
        <template #default="scope">
          <div v-if="scope.row.longitude != null && scope.row.latitude != null" class="text-[10px] text-slate-500 leading-tight">
            <div>Lon: {{ Number(scope.row.longitude).toFixed(4) }}</div>
            <div>Lat: {{ Number(scope.row.latitude).toFixed(4) }}</div>
          </div>
          <span v-else class="text-slate-400 text-xs">无</span>
        </template>
      </el-table-column>
      <el-table-column label="音频" width="90" align="center">
        <template #default="scope">
          <el-tooltip
            :content="channelInlineSaving[scope.row.id] ? '保存中，请稍候…' : '开启/关闭音频能力'"
            placement="top"
          >
            <span>
              <el-switch
                v-model="scope.row.has_audio"
                size="small"
                inline-prompt
                active-text="开"
                inactive-text="关"
                class="pretty-switch"
                :disabled="!!channelInlineSaving[scope.row.id]"
                @change="() => saveChannelAudioInline?.(scope.row)"
              />
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="默认码流" width="158" align="center">
        <template #default="scope">
          <el-tooltip
            :content="channelInlineSaving[scope.row.id] ? '保存中，请稍候…' : '设置默认码流类型'"
            placement="top"
          >
            <span>
              <el-select
                v-model="scope.row.default_stream_type"
                size="small"
                style="width: 110px"
                :disabled="!!channelInlineSaving[scope.row.id]"
                @change="() => saveChannelStreamTypeInline?.(scope.row)"
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
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="76" align="center">
        <template #default="scope">
          <el-tooltip :content="Number(scope.row.status) === 1 ? '在线' : '离线'" placement="top">
            <span class="status-wrap">
              <span class="status-dot" :class="Number(scope.row.status) === 1 ? 'online' : 'offline'"></span>
              <span class="status-text" :class="Number(scope.row.status) === 1 ? 'online' : 'offline'">{{ Number(scope.row.status) === 1 ? '在线' : '离线' }}</span>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" min-width="300">
        <template #default="scope">
          <div class="channel-actions">
            <el-button
              v-if="playerVisible && currentChannel && currentChannel.gb_id === scope.row.gb_id"
              size="small"
              type="danger"
              plain
              @click="closePlayer?.()"
              class="channel-action-btn channel-action-btn--danger"
            >
              <el-icon class="mr-1"><CloseBold /></el-icon>
              关闭播放
            </el-button>
            <el-tooltip
              v-else
              :content="playTooltip?.(scope.row)"
              placement="top"
            >
              <span>
                <el-button
                  type="primary"
                  size="small"
                  plain
                  @click="playStream?.(scope.row)"
                  class="channel-action-btn channel-action-btn--preview"
                  :disabled="!canPlay?.(scope.row)"
                >
                  <el-icon class="mr-1"><VideoPlay /></el-icon>
                  实时预览
                </el-button>
              </span>
            </el-tooltip>

            <el-tooltip content="编辑通道字段" placement="top">
              <span>
                <el-button size="small" plain @click="openChannelEdit?.(scope.row)" class="channel-action-btn channel-action-btn--edit">
                  <el-icon class="mr-1"><Edit /></el-icon>编辑
                </el-button>
              </span>
            </el-tooltip>
            <el-dropdown
              trigger="click"
              @command="(cmd: string) => handleRecordMenuCommand?.(scope.row, String(cmd || ''))"
            >
              <el-button size="small" plain class="channel-action-btn channel-action-btn--more">
                更多
                <el-icon class="ml-1"><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="cloud" :disabled="Number(scope.row.status) !== 1">
                    <el-icon><VideoCamera /></el-icon>云端录像
                  </el-dropdown-item>
                  <el-dropdown-item command="device" :disabled="Number(scope.row.status) !== 1">
                    <el-icon><Files /></el-icon>设备录像
                  </el-dropdown-item>
                  <el-dropdown-item command="timeline" :disabled="Number(scope.row.status) !== 1">
                    <el-icon><Timer /></el-icon>时间轴
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4 pagination-wrapper">
      <el-pagination
        v-model:current-page="channelPageModel"
        v-model:page-size="channelPageSizeModel"
        :total="channelTotal"
        layout="total, sizes, prev, pager, next, jumper"
        :page-sizes="[10, 20, 50, 100]"
        prev-text="上一页"
        next-text="下一页"
        size="small"
        @current-change="loadChannelsDialog?.()"
        @size-change="onPageSizeChange"
      />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CloseBold, Edit, Files, MoreFilled, Timer, VideoCamera, VideoPlay, Microphone, Warning, InfoFilled, Loading } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: boolean
  currentDevice: Record<string, unknown>
  currentChannel: Record<string, unknown>
  channelTotal: number
  channelOnlineTotal: number
  channelFilters: Record<string, unknown>
  channelStreamReset: string
  refreshingSnapshots: boolean
  channels: Record<string, unknown>[]
  channelSnapReloadToken: number
  channelsLoading: boolean
  playerVisible: boolean
  channelInlineSaving: Record<string, boolean>
  channelPage: number
  channelPageSize: number
  playTooltip?: (row: Record<string, unknown>) => string
  canPreviewChannel?: (row: Record<string, unknown>) => boolean
  getChannelPreviewStatus?: (row: Record<string, unknown>) => { label: string; type: string; icon: string } | null
  channelStreamStatusLoading?: boolean
  playStream?: (row: Record<string, unknown>) => void
  closePlayer?: () => void
  loadChannelsDialog?: () => void
  resetChannelDialogFilters?: () => void
  refreshChannelSnapshots?: () => void
  getChannelRowClassName?: ({ row }: { row: Record<string, unknown> }) => string
  getChannelSnapSrc?: (row: Record<string, unknown>) => string
  getResourceTypeLabel?: (row: Record<string, unknown>) => string
  getResourceTypeTagType?: (row: Record<string, unknown>) => string
  getPtzTypeTagType?: (row: Record<string, unknown>) => string
  getPtzTypeLabel?: (row: Record<string, unknown>) => string
  saveChannelAudioInline?: (row: Record<string, unknown>) => void
  saveChannelStreamTypeInline?: (row: Record<string, unknown>) => void
  openChannelEdit?: (row: Record<string, unknown>) => void
  handleRecordMenuCommand?: (row: Record<string, unknown>, cmd: string) => void
  canPlay?: (row: Record<string, unknown>) => boolean
  resetVisibleChannelsStreamType?: () => void
  onClosed?: () => void
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:channelStreamReset', v: string): void
  (e: 'update:channelPage', v: number): void
  (e: 'update:channelPageSize', v: number): void
  (e: 'update:channelFilters', v: { keyword: string; status?: number; resource_type?: number }): void
}>()

const channelStreamResetModel = computed({
  get: () => props.channelStreamReset,
  set: (v: string) => emit('update:channelStreamReset', v)
})

const channelPageModel = computed({
  get: () => Number(props.channelPage || 1),
  set: (v: number) => emit('update:channelPage', Number(v || 1))
})

const channelPageSizeModel = computed({
  get: () => Number(props.channelPageSize || 10),
  set: (v: number) => emit('update:channelPageSize', Number(v || 10))
})

const localFilters = computed({
  get: () => props.channelFilters || { keyword: '', status: undefined, resource_type: undefined },
  set: (v) => emit('update:channelFilters', v)
})

const onPageSizeChange = () => {
  emit('update:channelPage', 1)
  props.loadChannelsDialog?.()
}

const onClosed = () => {
  props.onClosed?.()
}
</script>

<style scoped>
.channels-dialog-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.channels-dialog-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.channels-dialog-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}
.channels-dialog-subtitle {
  font-size: 12px;
  color: #64748b;
}
.channels-dialog-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.channels-dialog-metric {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fff;
  color: #64748b;
  font-size: 12px;
}
.channels-dialog-metric strong {
  color: #0f172a;
}
.channels-dialog :deep(.el-dialog) {
  border-radius: 10px;
  overflow: hidden;
}
.channels-dialog :deep(.el-dialog__header) {
  padding: 14px 18px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.channels-dialog :deep(.el-dialog__body) {
  padding: 14px 18px 16px;
}
.channel-context-bar {
  margin-top: 10px;
  margin-bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  box-shadow: none;
}
.channel-context-info,
.channel-context-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.channel-context-chip {
  border: 1px solid #dbeafe;
  border-radius: 6px;
  padding: 5px 10px;
  background: #eff6ff;
  color: #1e40af;
  font-size: 12px;
  font-weight: 600;
}
.channel-context-channel {
  border-color: #d1fae5;
  background: #ecfdf5;
  color: #047857;
}
.context-btn {
  height: 32px;
  padding: 0 12px;
  border-radius: 6px;
  font-weight: 600;
}
.context-btn--primary {
  box-shadow: none;
}
.status-wrap {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.status-dot.online {
  background: var(--el-color-success);
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15);
}
.status-dot.offline {
  background: var(--el-border-color);
}
.status-text {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
}
.status-text.online {
  color: #10b981;
}
.status-text.offline {
  color: #94a3b8;
}
.channels-table :deep(.el-table__fixed-right),
.channels-table :deep(.el-table__fixed) {
  background-color: #fff;
}
.channels-table :deep(.el-table__fixed-right .el-table__cell),
.channels-table :deep(.el-table__fixed .el-table__cell) {
  background-color: #fff;
}
.channels-table-header-row :deep(.el-table__cell) {
  background-color: #f8fafc;
  color: #334155;
  font-weight: 600;
}
.channels-table :deep(.el-table__cell) {
  padding: 8px 0;
  font-size: 12px;
  line-height: 1.2;
}
.channels-table :deep(.el-table__body tr:hover > td.el-table__cell) {
  background-color: #f8fafc;
}
.channels-table :deep(.el-table__body tr.is-current-channel > td.el-table__cell) {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.08) 0%, rgba(14, 165, 233, 0.05) 100%);
}
.dialog-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}
.dialog-toolbar-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #475569;
}
.dialog-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.channel-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 4px 0;
}
.channel-action-btn {
  min-width: 64px;
  height: 30px;
  margin-left: 0;
  padding: 0 8px;
  border-radius: 6px;
  border-color: #e2e8f0;
  background: #fff;
  color: #334155;
  font-weight: 600;
  transition: all 0.18s ease;
}
.channel-action-btn:hover {
  transform: none;
  box-shadow: none;
}
.channel-action-btn--preview {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}
.channel-action-btn--edit {
  border-color: #a7f3d0;
  background: #ecfdf5;
  color: #0f766e;
}
.channel-action-btn--danger {
  border-color: #fecaca;
  background: #fef2f2;
  color: #dc2626;
}
.pretty-switch :deep(.el-switch__core) {
  width: 42px !important;
  height: 20px;
}
.pretty-switch :deep(.el-switch__core .el-switch__action) {
  width: 16px;
  height: 16px;
  top: 1px;
  left: 1px;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.16);
}
.pretty-switch :deep(.el-switch__inner .is-text) {
  font-size: 11px;
  font-weight: 700;
}
.preview-status-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
}
@media (max-width: 960px) {
  .channels-dialog-header {
    align-items: flex-start;
  }
}
</style>

<style>
.el-image-viewer__wrapper {
  z-index: 3000 !important;
}
</style>
