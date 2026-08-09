<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader :title="t('channelGroup.title')" :description="t('channelGroup.description')" />
      </template>

      <div class="flex-1 min-h-0 flex gap-4 mt-4">
      <div class="w-96 flex flex-col border rounded-lg bg-white overflow-hidden">
        <div class="p-2 border-b text-sm font-medium">{{ t('channelGroup.groupTitle') }}</div>
        <div v-if="treeLoading" class="flex-1 flex items-center justify-center text-slate-400">{{ t('channelGroup.loading') }}</div>
        <el-scrollbar v-else class="flex-1">
          <el-tree
            :data="treeData"
            :props="{ label: 'label', children: 'children' }"
            node-key="id"
            highlight-current
            default-expand-all
            @node-click="onTreeClick"
          />
        </el-scrollbar>
      </div>

      <div class="flex-1 flex flex-col min-w-0 border rounded-lg bg-white p-3">
        <el-form :inline="true" size="small" class="mb-2 flex flex-wrap gap-2 justify-end items-center">
          <el-radio-group v-model="viewMode" size="small" @change="onModeChange">
            <el-radio-button value="normal">{{ t('channelGroup.mounted') }}</el-radio-button>
            <el-radio-button value="unusual">{{ t('channelGroup.abnormalData') }}</el-radio-button>
          </el-radio-group>
          <el-input v-model="searchStr" :placeholder="t('channelGroup.keyword')" clearable style="width: 160px" @keyup.enter="search" />
          <el-select v-model="online" style="width: 110px" @change="search">
            <el-option :label="t('channelGroup.all')" value="" />
            <el-option :label="t('channelGroup.online')" value="true" />
            <el-option :label="t('channelGroup.offline')" value="false" />
          </el-select>
          <el-select v-model="channelType" style="width: 120px" @change="loadList">
            <el-option :label="t('channelGroup.all')" value="" />
            <el-option v-for="t in typeOpts" :key="t.id" :label="t.name" :value="String(t.id)" />
          </el-select>
          <el-button v-if="viewMode === 'normal'" type="primary" :disabled="!groupDeviceId" @click="openPickCh">{{ t('channelGroup.addChannel') }}</el-button>
          <el-dropdown v-if="viewMode === 'normal'" trigger="click" @command="handleNormalMoreCommand">
            <el-button plain class="table-action-more">{{ t('channelGroup.more') }}</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="removeSel" :disabled="!multipleSelection.length">{{ t('channelGroup.removeChannel') }}</el-dropdown-item>
                <el-dropdown-item command="removeByDevice" :disabled="!groupDeviceId">{{ t('channelGroup.removeByDevice') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button v-if="viewMode === 'unusual'" type="warning" @click="clearUnusual(true)">{{ t('channelGroup.oneClickClear') }}</el-button>
          <el-dropdown v-if="viewMode === 'unusual'" trigger="click" @command="handleUnusualMoreCommand">
            <el-button plain class="table-action-more">{{ t('channelGroup.more') }}</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="clearSelected" :disabled="!multipleSelection.length">{{ t('channelGroup.clearSelected') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button :icon="RefreshRight" circle @click="loadList" :title="t('channelGroup.refreshList')" />
        </el-form>

        <el-table
          v-loading="loading"
          :data="channelList"
          size="small"
          height="calc(100vh - 260px)"
          @selection-change="(rows: Record<string, unknown>[]) => (multipleSelection = rows)"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="gbName" :label="t('channelGroup.colName')" min-width="140" />
          <el-table-column prop="gbDeviceId" :label="t('channelGroup.colCode')" min-width="130" />
          <el-table-column prop="gbManufacturer" :label="t('channelGroup.colManufacturer')" width="90" />
          <el-table-column v-if="viewMode === 'unusual'" prop="gbParentId" :label="t('channelGroup.colParentNode')" min-width="140" show-overflow-tooltip />
          <el-table-column v-if="viewMode === 'unusual'" prop="gbBusinessGroupId" :label="t('channelGroup.colBusinessGroup')" min-width="140" show-overflow-tooltip />
          <el-table-column :label="t('channelGroup.colType')" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :style="channelTypeTag(row.dataType).style">
                {{ channelTypeTag(row.dataType).name }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('channelGroup.colStatus')" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.gbStatus === 'ON'" size="small" type="success">{{ t('channelGroup.online') }}</el-tag>
              <el-tag v-else size="small" type="info">{{ t('channelGroup.offline') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="viewMode === 'unusual'" :label="t('channelGroup.colAction')" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="clearOne(row)">{{ t('channelGroup.clear') }}</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="mt-4 flex justify-end" v-if="total > 0">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="count"
            :total="total"
            :page-sizes="[15, 25, 35, 50]"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="loadList"
            @current-change="loadList"
          />
        </div>
      </div>
    </div>

    <AppDialog v-model="pickChVisible" :title="t('channelGroup.addToGroupTitle')" size="large">
      <div class="text-xs text-slate-500 mb-2">{{ t('channelGroup.pickModeTip') }}</div>
      <el-radio-group v-model="pickMode" size="small" class="mb-3">
        <el-radio-button value="channel">{{ t('channelGroup.byChannel') }}</el-radio-button>
        <el-radio-button value="device">{{ t('channelGroup.byDevice') }}</el-radio-button>
      </el-radio-group>

      <div v-if="pickMode === 'channel'">
        <el-input v-model="pickKw" :placeholder="t('channelGroup.search')" clearable class="mb-2" @keyup.enter="searchPick" />
        <el-button size="small" type="primary" class="mb-2" @click="searchPick">{{ t('channelGroup.query') }}</el-button>
        <el-table :data="pickRows" size="small" max-height="360" @selection-change="(r: Record<string, unknown>[]) => (pickSel = r)">
          <el-table-column type="selection" width="45" />
          <el-table-column prop="gbDeviceId" :label="t('channelGroup.colChannelCode')" width="160" />
          <el-table-column prop="gbName" :label="t('channelGroup.colName')" />
          <el-table-column prop="deviceId" :label="t('channelGroup.colDevice')" width="140" />
        </el-table>
      </div>

      <div v-else>
        <el-form :inline="true" size="small">
          <el-form-item :label="t('channelGroup.deviceIdList')" class="w-full">
            <el-input
              v-model="pickDeviceIdsText"
              type="textarea"
              :rows="4"
              :placeholder="t('channelGroup.deviceIdListPlaceholder')"
            />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="pickChVisible = false">{{ t('channelGroup.cancel') }}</el-button>
        <el-button type="primary" @click="confirmPick">{{ t('channelGroup.confirm') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="removeByDeviceVisible" :title="t('channelGroup.removeByDeviceTitle')" size="medium">
      <div class="text-xs text-slate-500 mb-2">{{ t('channelGroup.removeByDeviceTip') }}</div>
      <el-input
        v-model="removeByDeviceIdsText"
        type="textarea"
        :rows="5"
        :placeholder="t('channelGroup.deviceIdListPlaceholder')"
      />
      <template #footer>
        <el-button @click="removeByDeviceVisible = false">{{ t('channelGroup.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRemoveByDevice">{{ t('channelGroup.confirmRemove') }}</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { channelTypeTag } from '../constants/channelType'
import { getFriendlyError } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const { t } = useI18n()

const typeOpts = computed(() => [
  { id: 1, name: t('channelGroup.typeGbDevice') },
  { id: 2, name: t('channelGroup.typePushDevice') },
  { id: 3, name: t('channelGroup.typeStreamProxy') }
])

const treeLoading = ref(false)
const treeData = ref<Channel[]>([])
const groupDeviceId = ref('')
const viewMode = ref<'normal' | 'unusual'>('normal')
const searchStr = ref('')
const online = ref('')
const channelType = ref('')
const channelList = ref<Channel[]>([])
const loading = ref(false)
const currentPage = ref(1)
const count = ref(15)
const total = ref(0)
const multipleSelection = ref<Channel[]>([])

const pickChVisible = ref(false)
const pickMode = ref<'channel' | 'device'>('channel')
const pickKw = ref('')
const pickRows = ref<Channel[]>([])
const pickSel = ref<Channel[]>([])
const pickDeviceIdsText = ref('')
const removeByDeviceVisible = ref(false)
const removeByDeviceIdsText = ref('')

const loadTree = async () => {
  treeLoading.value = true
  try {
    const res = await api.get('/api/v1/devices/tree/business')
    treeData.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    treeData.value = []
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    treeLoading.value = false
  }
}

const onTreeClick = (data: Record<string, unknown>) => {
  const nt = String(data?.nodeType || '').toLowerCase()
  if (nt === 'device') return
  groupDeviceId.value = String(data?.id || '').trim()
  currentPage.value = 1
  loadList()
}

const loadList = async () => {
  if (viewMode.value === 'normal' && !groupDeviceId.value) {
    channelList.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const url = viewMode.value === 'normal' ? '/api/common/channel/parent/list' : '/api/common/channel/parent/unusual/list'
    const res = await api.get(url, {
      params: {
        page: currentPage.value,
        count: count.value,
        query: searchStr.value || undefined,
        online: online.value === '' ? undefined : online.value,
        channelType: channelType.value === '' ? undefined : Number(channelType.value),
        groupDeviceId: viewMode.value === 'normal' ? groupDeviceId.value : undefined
      }
    })
    total.value = Number(res.data?.total || 0)
    channelList.value = Array.isArray(res.data?.list) ? res.data.list : []
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

const onModeChange = () => {
  currentPage.value = 1
  multipleSelection.value = []
  loadList()
}

const handleNormalMoreCommand = (cmd: string) => {
  if (cmd === 'removeSel') {
    removeSel()
    return
  }
  if (cmd === 'removeByDevice') {
    openRemoveByDevice()
  }
}

const handleUnusualMoreCommand = (cmd: string) => {
  if (cmd === 'clearSelected') {
    clearUnusual(false)
  }
}

const removeSel = async () => {
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(t('channelGroup.removeConfirm', { n: ids.length }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/group/delete', { channelIds: ids })
    ElMessage.success(t('channelGroup.removed'))
    multipleSelection.value = []
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const clearUnusual = async (all: boolean) => {
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!all && !ids.length) return
  try {
    await ElMessageBox.confirm(all ? t('channelGroup.clearAllConfirm') : t('channelGroup.clearSelectedConfirm', { n: ids.length }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/parent/unusual/clear', {
      all,
      channelIds: all ? [] : ids
    })
    ElMessage.success(t('channelGroup.clearDone'))
    multipleSelection.value = []
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const clearOne = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(t('channelGroup.clearOneConfirm', { id: row.gbDeviceId }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/parent/unusual/clear', {
      all: false,
      channelIds: [row.gbId]
    })
    ElMessage.success(t('channelGroup.clearDone'))
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const openPickCh = () => {
  pickKw.value = ''
  pickRows.value = []
  pickSel.value = []
  pickDeviceIdsText.value = ''
  pickMode.value = 'channel'
  pickChVisible.value = true
  searchPick()
}

const openRemoveByDevice = () => {
  removeByDeviceIdsText.value = ''
  removeByDeviceVisible.value = true
}

const searchPick = async () => {
  try {
    const res = await api.get('/api/common/channel/list', {
      params: { page: 1, count: 100, query: pickKw.value || undefined, channelType: 1 }
    })
    pickRows.value = Array.isArray(res.data?.list) ? res.data.list : []
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const confirmPick = async () => {
  if (!groupDeviceId.value) return
  try {
    if (pickMode.value === 'channel') {
      const ids = pickSel.value.map((r: Record<string, unknown>) => r.gbId)
      if (!ids.length) return
      await api.post('/api/common/channel/group/add', {
        parentId: groupDeviceId.value,
        businessGroup: groupDeviceId.value,
        channelIds: ids
      })
    } else {
      const deviceIds = pickDeviceIdsText.value
        .split(/[,，\n\r\t ]+/)
        .map(x => String(x || '').trim())
        .filter(Boolean)
      if (!deviceIds.length) {
        ElMessage.warning(t('channelGroup.fillDeviceIds'))
        return
      }
      await api.post('/api/common/channel/group/device/add', {
        parentId: groupDeviceId.value,
        businessGroup: groupDeviceId.value,
        deviceIds
      })
    }

    ElMessage.success(t('channelGroup.added'))
    pickChVisible.value = false
    loadList()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const confirmRemoveByDevice = async () => {
  const deviceIds = removeByDeviceIdsText.value
    .split(/[,，\n\r\t ]+/)
    .map(x => String(x || '').trim())
    .filter(Boolean)
  if (!deviceIds.length) {
    ElMessage.warning(t('channelGroup.fillDeviceIds'))
    return
  }
  try {
    await ElMessageBox.confirm(t('channelGroup.removeByDeviceConfirm', { n: deviceIds.length }), t('common.tips'), { type: 'warning' })
  } catch { return }
  try {
    await api.post('/api/common/channel/group/device/delete', {
      deviceIds
    })
    ElMessage.success(t('channelGroup.removed'))
    removeByDeviceVisible.value = false
    loadList()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

onMounted(loadTree)
</script>
