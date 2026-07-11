<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader :title="t('channel.list.title')" :description="t('channel.list.description')">
          <template #actions>
            <el-tooltip :content="t('channel.list.refreshTip')" placement="bottom">
              <el-button @click="loadList">
                <el-icon class="mr-1"><RefreshRight /></el-icon>
                {{ t('common.refresh') }}
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('channel.list.addChannelTip')" placement="bottom">
              <el-button type="primary" @click="openAdd">{{ t('channel.list.addChannel') }}</el-button>
            </el-tooltip>
            <el-button @click="$router.push('/channels/legacy')">{{ t('channel.list.legacyResource') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard class="flex-1 flex flex-col min-h-0" body-class="flex-1 flex flex-col min-h-0 p-4">
        <el-form :inline="true" size="small" class="mb-2 flex flex-wrap gap-1 items-center">
        <el-form-item :label="t('common.search')">
          <el-input v-model="searchStr" :placeholder="t('channel.list.keywordPlaceholder')" clearable style="width: 220px" @keyup.enter="search">
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item :label="t('channel.list.onlineStatus')">
          <el-select v-model="online" style="width: 120px" @change="search">
            <el-option :label="t('common.all')" value="" />
            <el-option :label="t('common.online')" value="true" />
            <el-option :label="t('common.offline')" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('common.type')">
          <el-select v-model="channelType" style="width: 130px" @change="loadList">
            <el-option :label="t('common.all')" value="" />
            <el-option v-for="opt in typeOptions" :key="opt.id" :label="opt.name" :value="String(opt.id)" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('channel.list.civilCode')">
          <el-input v-model="civilCodeName" :placeholder="t('common.pleaseSelect')" readonly style="width: 200px">
            <template #append>
              <el-button @click="openCivilForFilter">{{ t('channel.manager.select') }}</el-button>
            </template>
          </el-input>
          <el-button v-if="civilCodeDeviceId" link type="danger" class="ml-1" @click="clearCivil">{{ t('channel.manager.clear') }}</el-button>
        </el-form-item>
        <el-form-item :label="t('channel.list.businessGroup')">
          <el-input v-model="groupName" :placeholder="t('common.pleaseSelect')" readonly style="width: 200px">
            <template #append>
              <el-button @click="openGroupForFilter">{{ t('channel.manager.select') }}</el-button>
            </template>
          </el-input>
          <el-button v-if="groupDeviceId" link type="danger" class="ml-1" @click="clearGroup">{{ t('channel.manager.clear') }}</el-button>
        </el-form-item>
        <el-form-item>
          <el-dropdown trigger="click" @command="onBatchCommand">
            <el-tooltip
              :content="canBatchOperate ? t('channel.list.batchOperateTip') : t('channel.list.batchOperateTipDisabled')"
              placement="top"
            >
              <span>
                <el-button type="primary" :disabled="!canBatchOperate">
                  {{ t('common.batchOps') }}
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
              </span>
            </el-tooltip>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="region" :disabled="!canBatchOperate">{{ t('channel.list.civilCode') }}</el-dropdown-item>
                <el-dropdown-item command="group" :disabled="!canBatchOperate">{{ t('channel.list.businessGroup') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-form-item>
        <el-form-item>
          <el-button :icon="RefreshRight" circle @click="loadList" :title="t('channel.list.refreshListTip')" />
        </el-form-item>
      </el-form>

      <div class="channel-summary mb-2">
        <span>{{ t('channel.list.totalCount', { n: total }) }}</span>
        <span class="divider">|</span>
        <span>{{ t('channel.list.selectedCount', { n: multipleSelection.length }) }}</span>
      </div>

      <div class="flex-1 min-h-0 border rounded-lg overflow-hidden bg-white">
        <el-table
          ref="tableRef"
          v-loading="loading"
          :data="channelList"
          size="small"
          :aria-label="t('channel.list.title')"
          height="100%"
          style="width: 100%"
          class="channel-table"
          header-row-class-name="channel-table-header-row"
          row-key="gbId"
          @selection-change="(rows: Record<string, unknown>[]) => (multipleSelection = rows)"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="gbName" :label="t('common.name')" min-width="160" show-overflow-tooltip />
          <el-table-column prop="gbDeviceId" :label="t('common.code')" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.gbDeviceId }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="gbManufacturer" :label="t('channel.list.manufacturerCol')" width="100" show-overflow-tooltip />
          <el-table-column :label="t('common.type')" width="110">
            <template #default="{ row }">
              <el-tooltip :content="t('channel.list.channelTypeTip', { type: row.dataType })" placement="top">
                <el-tag size="small" effect="plain" :style="(channelTypeTag(row.dataType) as any).style">
                  {{ (channelTypeTag(row.dataType) as any).name }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column :label="t('channel.list.locationInfo')" min-width="120">
            <template #default="{ row }">
              <span v-if="row.gbLongitude != null && row.gbLatitude != null" class="text-xs text-slate-600">
                {{ row.gbLongitude }} / {{ row.gbLatitude }}
              </span>
              <span v-else class="text-slate-400 text-xs">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('channel.list.cameraType')" width="100" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tag
                size="small"
                effect="plain"
                :type="ptzTypeTagType(row.ptzTypeText)"
                :style="ptzTypeTagStyle(row.ptzTypeText)"
              >
                {{ row.ptzTypeText }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.status')" width="90">
            <template #default="{ row }">
              <el-tooltip :content="row.gbStatus === 'ON' ? t('common.online') : t('common.offline')" placement="top">
                <span class="status-wrap">
                  <span class="status-dot" :class="row.gbStatus === 'ON' ? 'online' : 'offline'"></span>
                  <span>{{ row.gbStatus === 'ON' ? t('common.online') : t('common.offline') }}</span>
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.action')" width="260" fixed="right">
            <template #default="{ row }">
              <div class="table-actions">
                <el-tooltip :content="row.gbStatus === 'ON' ? t('channel.manager.play') : t('channel.list.offlineCannotPlay')" placement="top">
                  <span>
                    <el-button
                      type="primary"
                      link
                      size="small"
                      :disabled="row.gbStatus !== 'ON'"
                      :loading="!!playLoading[row.gbId]"
                      @click="play(row)"
                    >
                      <el-icon class="mr-1"><VideoPlay /></el-icon>{{ t('channel.manager.play') }}
                    </el-button>
                  </span>
                </el-tooltip>
                <el-tooltip :content="t('channel.list.stopPreview')" placement="top">
                  <span>
                    <el-button v-if="row.streamId" type="danger" link size="small" @click="stopRow(row)">{{ t('channel.manager.stop') }}</el-button>
                  </span>
                </el-tooltip>
                <el-divider direction="vertical" />
                <el-tooltip :content="t('channel.list.editChannelTip')" placement="top">
                  <span>
                    <el-button type="primary" link size="small" @click="openEdit(row)">
                      <el-icon class="mr-1"><Edit /></el-icon>{{ t('common.edit') }}
                    </el-button>
                  </span>
                </el-tooltip>
                <el-divider direction="vertical" />
                <el-dropdown trigger="click" @command="(c: string) => more(c, row)">
                  <el-tooltip :content="row.gbStatus === 'ON' ? t('channel.list.moreOnlineTip') : t('channel.list.moreOfflineTip')" placement="top">
                    <span>
                      <el-button type="primary" link size="small">
                        {{ t('common.more') }} <el-icon><MoreFilled /></el-icon>
                      </el-button>
                    </span>
                  </el-tooltip>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="device" :disabled="row.gbStatus !== 'ON'">{{ t('common.deviceRecord') }}</el-dropdown-item>
                      <el-dropdown-item command="cloud" :disabled="row.gbStatus !== 'ON'">{{ t('common.cloudRecord') }}</el-dropdown-item>
                      <el-dropdown-item command="timeline" :disabled="row.gbStatus !== 'ON'">
                        <el-icon class="mr-1"><Timer /></el-icon>
                        {{ t('channel.list.timeReset') }}
                      </el-dropdown-item>
                      <el-tooltip
                        :content="
                          resetLoading[String(row.gbId || '')]
                            ? t('channel.list.resetting')
                            : t('channel.list.resetFieldsTip')
                        "
                        placement="left"
                      >
                        <span class="inline-block">
                          <el-dropdown-item command="reset" :disabled="!!resetLoading[String(row.gbId || '')]">
                            {{ t('channel.list.resetChannelFields') }}
                          </el-dropdown-item>
                        </span>
                      </el-tooltip>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-pagination
        class="mt-3 justify-end"
        v-model:current-page="currentPage"
        v-model:page-size="count"
        :total="total"
        :page-sizes="[15, 25, 35, 50, 100, 500, 1000]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadList"
        @current-change="loadList"
      />
      </TableCard>

      <PickCivilDialog v-model="showCivil" @picked="onCivilDialogPicked" />
      <PickGroupDialog v-model="showGroup" @picked="onGroupDialogPicked" />

            <ChannelPlayerDialog
        v-model:visible="playerVisible"
        :device-id="playDeviceGb"
        :channel-id="playChannelGb"
      />

    <ChannelEditDialog
      v-model:visible="editVisible"
      :channel-data="editForm"
      @success="loadList"
    />

    <AddChannelDialog
      v-model:visible="addVisible"
      @success="loadList"
    />
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { logger } from '@/utils/logger'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { ArrowDown, RefreshRight, Search, VideoPlay, Edit, MoreFilled, Timer } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import ChannelPlayerDialog from '../components/channel/ChannelPlayerDialog.vue'
import ChannelEditDialog from '../components/channel/ChannelEditDialog.vue'
import AddChannelDialog from '../components/channel/AddChannelDialog.vue'
import PickCivilDialog from '../components/channel/PickCivilDialog.vue'
import PickGroupDialog from '../components/channel/PickGroupDialog.vue'
import { channelTypeTag } from '../constants/channelType'
import { getFriendlyError } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const router = useRouter()
const { t } = useI18n()
const typeOptions = computed(() => [
  { id: 1, name: t('channel.list.typeGbDevice') },
  { id: 2, name: t('channel.list.typePushDevice') },
  { id: 3, name: t('channel.list.typeStreamProxy') }
])

const ptzTypeTagType = (ptzTypeText: unknown): 'success' | 'info' | 'warning' | 'danger' => {
  const s = String(ptzTypeText || '').trim()
  if (!s) return 'info'
  if (s.includes('球机')) return 'success'
  if (s.includes('半球')) return 'info'
  if (s.includes('固定') || s.includes('枪机')) return 'warning'
  if (s.includes('遥控')) return 'danger'
  if (s.includes('全景') || s.includes('拼接')) return 'info'
  if (s.includes('分割')) return 'warning'

  return 'info'
}

const ptzTypeTagStyle = (ptzTypeText: unknown): Record<string, string> => {
  const type = ptzTypeTagType(ptzTypeText)
  if (type === 'success') return { color: '#10b981', borderColor: '#a7f3d0' }
  if (type === 'danger') return { color: '#ef4444', borderColor: '#fecaca' }
  if (type === 'warning') return { color: '#f59e0b', borderColor: '#fde68a' }
  return { color: '#3b82f6', borderColor: '#bfdbfe' }
}

const searchStr = ref('')
const online = ref('')
const channelType = ref('')
const civilCodeName = ref('')
const civilCodeDeviceId = ref('')
const groupName = ref('')
const groupDeviceId = ref('')
const groupBusiness = ref('')

const showCivil = ref(false)
const showGroup = ref(false)
const civilDialogMode = ref<'filter' | 'batchRegion'>('filter')
const groupDialogMode = ref<'filter' | 'batchGroup'>('filter')

const channelList = ref<Channel[]>([])
const loading = ref(false)
const currentPage = ref(1)
const count = ref(15)
const total = ref(0)
const multipleSelection = ref<Channel[]>([])
const tableRef = ref()
const playLoading = ref<Record<number, boolean>>({})
const resetLoading = ref<Record<string, boolean>>({})

const canBatchOperate = computed(() => (multipleSelection.value?.length || 0) > 0)

const playerVisible = ref(false)

const playDeviceGb = ref('')
const playChannelGb = ref('')
const currentRow = ref<Channel | null>(null)
const editVisible = ref(false)
const editForm = ref<Channel>({})

const addVisible = ref(false)

const openAdd = () => {
  addVisible.value = true
}

const subTitle = computed(() => {
  const r = currentRow.value
  if (!r) return ''
  return `${r.deviceId || ''} / ${r.gbDeviceId || ''}`
})

const loadList = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/common/channel/list', {
      params: {
        page: currentPage.value,
        count: count.value,
        query: searchStr.value || undefined,
        online: online.value === '' ? undefined : online.value,
        channelType: channelType.value === '' ? undefined : Number(channelType.value),
        civilCode: civilCodeDeviceId.value || undefined,
        parentDeviceId: groupDeviceId.value || undefined
      }
    })
    total.value = Number(res.data?.total || 0)
    channelList.value = Array.isArray(res.data?.list) ? res.data.list : []
    await nextTick()
    tableRef.value?.doLayout?.()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    loading.value = false
  }
}

const search = () => {
  currentPage.value = 1
  loadList()
}

const openCivilForFilter = () => {
  civilDialogMode.value = 'filter'
  showCivil.value = true
}

const openGroupForFilter = () => {
  groupDialogMode.value = 'filter'
  showGroup.value = true
}

const clearCivil = () => {
  civilCodeName.value = ''
  civilCodeDeviceId.value = ''
  loadList()
}

const clearGroup = () => {
  groupName.value = ''
  groupDeviceId.value = ''
  groupBusiness.value = ''
  loadList()
}

const onCivilDialogPicked = async (code: string, name: string) => {
  if (civilDialogMode.value === 'filter') {
    civilCodeDeviceId.value = code
    civilCodeName.value = `${name} (${code})`
    loadList()
    return
  }
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(t('channel.list.batchAddRegionConfirm', { n: ids.length, code }), t('common.batchOps'), { type: 'warning' })
    await api.post('/api/common/channel/region/add', { civilCode: code, channelIds: ids })
    ElMessage.success(t('common.saveSuccess'))
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const onGroupDialogPicked = async (parentId: string, businessGroup: string, name: string) => {
  if (groupDialogMode.value === 'filter') {
    groupDeviceId.value = parentId
    groupBusiness.value = businessGroup
    groupName.value = name
    loadList()
    return
  }
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(t('channel.list.batchAddGroupConfirm', { n: ids.length, name }), t('common.batchOps'), { type: 'warning' })
    await api.post('/api/common/channel/group/add', {
      parentId,
      businessGroup,
      channelIds: ids
    })
    ElMessage.success(t('common.saveSuccess'))
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const onBatchCommand = (cmd: string) => {
  if (cmd === 'region') startBatchRegion()
  else if (cmd === 'group') startBatchGroup()
}

const startBatchRegion = () => {
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!ids.length) {
    ElMessage.warning(t('common.pleaseSelectChannel'))
    return
  }
  civilDialogMode.value = 'batchRegion'
  showCivil.value = true
}

const startBatchGroup = () => {
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!ids.length) {
    ElMessage.warning(t('common.pleaseSelectChannel'))
    return
  }
  groupDialogMode.value = 'batchGroup'
  showGroup.value = true
}

const play = async (row: Record<string, unknown>) => {
  const deviceId = String(row?.deviceId || '').trim()
  const channelId = String(row?.gbDeviceId || '').trim()
  if (!deviceId || !channelId) return
  currentRow.value = row
  playDeviceGb.value = deviceId
  playChannelGb.value = channelId
  playerVisible.value = true
}

const stopRow = async (row: Record<string, unknown>) => {
  if (!row.streamId) return
  try {
    await api.post('/api/v1/stream/stop', { app: 'live', stream: row.streamId })
  } catch (e) {
    logger.warn('停止播放失败:', e)
  }
  row.streamId = ''
  loadList()
}

const openEdit = async (row: Record<string, unknown>) => {
  const deviceId = String(row.deviceId || '').trim()
  const channelId = String(row.gbDeviceId || '').trim()
  if (!deviceId || !channelId) return
  try {
    const res = await api.get('/api/v1/devices/channels/flat', { params: { device_id: deviceId, keyword: channelId, limit: 1 } })
    const items = res.data?.items || []
    const d = items.find((x: Record<string, unknown>) => x.gb_id === channelId)
    if (!d) {
       ElMessage.error(t('channel.list.channelDetailNotFound'))
       return
    }
    editForm.value = d
    editVisible.value = true
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const more = (cmd: string, row: Record<string, unknown>) => {
  const deviceId = String(row.deviceId || '').trim()
  const ch = String(row.gbDeviceId || '').trim()
  if (!deviceId || !ch) return
  const nowIso = new Date().toISOString()
  if (cmd === 'device') {
    router.push({ path: '/devices', query: { device_id: deviceId, channel_id: ch, tab: 'device', time: nowIso, window_minutes: 30 } })
  } else if (cmd === 'cloud') {
    router.push({ path: '/devices', query: { device_id: deviceId, channel_id: ch, tab: 'cloud', time: nowIso, window_minutes: 30 } })
  } else if (cmd === 'timeline') {
    router.push({ path: '/devices', query: { device_id: deviceId, channel_id: ch, tab: 'timeline', time: nowIso, window_minutes: 30 } })
  } else if (cmd === 'reset') {
    void resetChannel(row)
  }
}

const resetChannel = async (row: Record<string, unknown>) => {
  try {
    const key = String(row.gbId || '')
    if (resetLoading.value[key]) return
    resetLoading.value[key] = true
    await ElMessageBox.confirm(t('channel.list.resetChannelConfirm', { id: row.gbDeviceId }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/reset', {
      id: row.gbId,
      channelFields: ['gbCivilCode', 'gbParentId', 'gbBusinessGroupId', 'gbLongitude', 'gbLatitude', 'ptzType']
    })
    ElMessage.success(t('channel.list.resetSuccess'))
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  } finally {
    const key = String(row.gbId || '')
    resetLoading.value[key] = false
  }
}

onMounted(loadList)
</script>

<style scoped>
.channel-summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.channel-summary .divider {
  color: var(--el-border-color);
}
.status-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.online {
  background: var(--el-color-success);
  box-shadow: none;
}
.status-dot.offline {
  background: var(--el-border-color);
}
.channel-table :deep(.el-table__body tr) {
  transition: background-color 0.2s ease;
}
.channel-table :deep(.el-table__body tr:hover > td.el-table__cell) {
  background-color: var(--el-fill-color-extra-light);
}
.channel-table :deep(.el-table__fixed-right),
.channel-table :deep(.el-table__fixed) {
  background-color: var(--el-bg-color) !important;
}
.channel-table :deep(.el-table__fixed-right .el-table__cell),
.channel-table :deep(.el-table__fixed .el-table__cell) {
  background-color: var(--el-bg-color) !important;
}
.channel-table :deep(.el-table__cell) {
  padding: 8px 0;
  font-size: 12px;
  line-height: 1.2;
}
.table-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.channel-table-header-row :deep(.el-table__cell) {
  background-color: var(--el-fill-color-light) !important;
  color: var(--el-text-color-primary) !important;
  font-weight: 600;
  font-size: 12px;
}
.channel-table :deep(.el-table__body tr.is-selected > td.el-table__cell) {
  background-color: var(--el-color-primary-light-9) !important;
}
.channel-table :deep(.el-table__body tr.is-selected:hover > td.el-table__cell) {
  background-color: var(--el-color-primary-light-8) !important;
}
</style>
