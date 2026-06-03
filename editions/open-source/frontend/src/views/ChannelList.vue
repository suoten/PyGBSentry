<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader title="通道列表" description="集中管理系统内的所有通道数据，支持状态检索与快捷操作">
          <template #actions>
            <el-tooltip content="刷新通道列表" placement="bottom">
              <el-button @click="loadList">
                <el-icon class="mr-1"><RefreshRight /></el-icon>
                刷新
              </el-button>
            </el-tooltip>
            <el-tooltip content="新增通道（填写设备通道国标ID等）" placement="bottom">
              <el-button type="primary" @click="openAdd">新增通道</el-button>
            </el-tooltip>
            <el-button @click="$router.push('/channels/legacy')">旧版资源</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard class="flex-1 flex flex-col min-h-0" body-class="flex-1 flex flex-col min-h-0 p-4">
        <el-form :inline="true" size="small" class="mb-2 flex flex-wrap gap-1 items-center">
        <el-form-item label="搜索">
          <el-input v-model="searchStr" placeholder="名称/编号关键字" clearable style="width: 220px" @keyup.enter="search">
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="在线状态">
          <el-select v-model="online" style="width: 120px" @change="search">
            <el-option label="全部" value="" />
            <el-option label="在线" value="true" />
            <el-option label="离线" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="channelType" style="width: 130px" @change="loadList">
            <el-option label="全部" value="" />
            <el-option v-for="t in typeOptions" :key="t.id" :label="t.name" :value="String(t.id)" />
          </el-select>
        </el-form-item>
        <el-form-item label="行政区划">
          <el-input v-model="civilCodeName" placeholder="请选择" readonly style="width: 200px">
            <template #append>
              <el-button @click="openCivilForFilter">选择</el-button>
            </template>
          </el-input>
          <el-button v-if="civilCodeDeviceId" link type="danger" class="ml-1" @click="clearCivil">清除</el-button>
        </el-form-item>
        <el-form-item label="业务分组">
          <el-input v-model="groupName" placeholder="请选择" readonly style="width: 200px">
            <template #append>
              <el-button @click="openGroupForFilter">选择</el-button>
            </template>
          </el-input>
          <el-button v-if="groupDeviceId" link type="danger" class="ml-1" @click="clearGroup">清除</el-button>
        </el-form-item>
        <el-form-item>
          <el-dropdown trigger="click" @command="onBatchCommand">
            <el-tooltip
              :content="canBatchOperate ? '对选中的通道执行批量操作' : '请先勾选要批量操作的通道'"
              placement="top"
            >
              <span>
                <el-button type="primary" :disabled="!canBatchOperate">
                  批量操作
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
              </span>
            </el-tooltip>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="region" :disabled="!canBatchOperate">行政区划</el-dropdown-item>
                <el-dropdown-item command="group" :disabled="!canBatchOperate">业务分组</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-form-item>
        <el-form-item>
          <el-button :icon="RefreshRight" circle @click="loadList" title="刷新列表" />
        </el-form-item>
      </el-form>

      <div class="channel-summary mb-2">
        <span>总数 {{ total }}</span>
        <span class="divider">|</span>
        <span>已选 {{ multipleSelection.length }}</span>
      </div>

      <div class="flex-1 min-h-0 border rounded-lg overflow-hidden bg-white">
        <el-table
          ref="tableRef"
          v-loading="loading"
          :data="channelList"
          size="small"
          aria-label="通道列表"
          height="100%"
          style="width: 100%"
          class="channel-table"
          header-row-class-name="channel-table-header-row"
          row-key="gbId"
          @selection-change="(rows: Record<string, unknown>[]) => (multipleSelection = rows)"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="gbName" label="名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="gbDeviceId" label="编号" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.gbDeviceId }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="gbManufacturer" label="厂家" width="100" show-overflow-tooltip />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              <el-tooltip :content="`通道类型：{row.dataType}`" placement="top">
                <el-tag size="small" effect="plain" :style="channelTypeTag(row.dataType).style">
                  {{ channelTypeTag(row.dataType).name }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="位置信息" min-width="120">
            <template #default="{ row }">
              <span v-if="row.gbLongitude != null && row.gbLatitude != null" class="text-xs text-slate-600">
                {{ row.gbLongitude }} / {{ row.gbLatitude }}
              </span>
              <span v-else class="text-slate-400 text-xs">—</span>
            </template>
          </el-table-column>
          <el-table-column label="摄像头类型" width="100" show-overflow-tooltip>
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
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tooltip :content="row.gbStatus === 'ON' ? '在线' : '离线'" placement="top">
                <span class="status-wrap">
                  <span class="status-dot" :class="row.gbStatus === 'ON' ? 'online' : 'offline'"></span>
                  <span>{{ row.gbStatus === 'ON' ? '在线' : '离线' }}</span>
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <div class="table-actions">
                <el-tooltip :content="row.gbStatus === 'ON' ? '播放' : '离线设备无法播放'" placement="top">
                  <span>
                    <el-button
                      type="primary"
                      link
                      size="small"
                      :disabled="row.gbStatus !== 'ON'"
                      :loading="!!playLoading[row.gbId]"
                      @click="play(row)"
                    >
                      <el-icon class="mr-1"><VideoPlay /></el-icon>播放
                    </el-button>
                  </span>
                </el-tooltip>
                <el-tooltip content="停止预览" placement="top">
                  <span>
                    <el-button v-if="row.streamId" type="danger" link size="small" @click="stopRow(row)">停止</el-button>
                  </span>
                </el-tooltip>
                <el-divider direction="vertical" />
                <el-tooltip content="编辑通道字段" placement="top">
                  <span>
                    <el-button type="primary" link size="small" @click="openEdit(row)">
                      <el-icon class="mr-1"><Edit /></el-icon>编辑
                    </el-button>
                  </span>
                </el-tooltip>
                <el-divider direction="vertical" />
                <el-dropdown trigger="click" @command="(c: string) => more(c, row)">
                  <el-tooltip :content="row.gbStatus === 'ON' ? '更多：设备录像/云端录像/时间重置' : '离线：仅重置通道字段可用'" placement="top">
                    <span>
                      <el-button type="primary" link size="small">
                        更多 <el-icon><MoreFilled /></el-icon>
                      </el-button>
                    </span>
                  </el-tooltip>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="device" :disabled="row.gbStatus !== 'ON'">设备录像</el-dropdown-item>
                      <el-dropdown-item command="cloud" :disabled="row.gbStatus !== 'ON'">云端录像</el-dropdown-item>
                      <el-dropdown-item command="timeline" :disabled="row.gbStatus !== 'ON'">
                        <el-icon class="mr-1"><Timer /></el-icon>
                        时间重置
                      </el-dropdown-item>
                      <el-tooltip
                        :content="
                          resetLoading[String(row.gbId || '')]
                            ? '重置中，请稍候…'
                            : '重置区划/分组/坐标/云台字段（会覆盖当前值）'
                        "
                        placement="left"
                      >
                        <span class="inline-block">
                          <el-dropdown-item command="reset" :disabled="!!resetLoading[String(row.gbId || '')]">
                            重置通道字段
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
import { ElMessage, ElMessageBox } from 'element-plus'
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
const typeOptions = [
  { id: 1, name: '国标设备' },
  { id: 2, name: '推流设备' },
  { id: 3, name: '拉流代理' }
]

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
    await ElMessageBox.confirm(`确定添加 ${ids.length} 个通道到行政区：${code}？`, '批量操作', { type: 'warning' })
    await api.post('/api/common/channel/region/add', { civilCode: code, channelIds: ids })
    ElMessage.success('保存成功')
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
    await ElMessageBox.confirm(`确定添加 ${ids.length} 个通道到分组：${name}？`, '批量操作', { type: 'warning' })
    await api.post('/api/common/channel/group/add', {
      parentId,
      businessGroup,
      channelIds: ids
    })
    ElMessage.success('保存成功')
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
    ElMessage.warning('请选择通道')
    return
  }
  civilDialogMode.value = 'batchRegion'
  showCivil.value = true
}

const startBatchGroup = () => {
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!ids.length) {
    ElMessage.warning('请选择通道')
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
    console.warn('停止播放失败:', e)
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
       ElMessage.error('找不到该通道详细信息')
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
    await ElMessageBox.confirm(`确定重置通道 ${row.gbDeviceId} 的区域/分组/坐标/云台字段？`, '提示', { type: 'warning' })
    await api.post('/api/common/channel/reset', {
      id: row.gbId,
      channelFields: ['gbCivilCode', 'gbParentId', 'gbBusinessGroupId', 'gbLongitude', 'gbLatitude', 'ptzType']
    })
    ElMessage.success('重置成功')
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
