<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader :title="t('channelRegion.title')" :description="t('channelRegion.description')" />
      </template>

      <div class="flex-1 min-h-0 flex gap-4 mt-4">
        <div class="w-96 flex flex-col border rounded-lg bg-white overflow-hidden">
        <div class="p-2 border-b text-sm font-medium flex items-center justify-between">
          <span>{{ t('channelRegion.regionTitle') }}</span>
          <div class="flex gap-1">
            <el-button size="small" type="primary" link @click="showAddRegionDialog">{{ t('channelRegion.add') }}</el-button>
            <el-button size="small" type="danger" link @click="deleteCurrentRegion" :disabled="!currentRegionId">{{ t('channelRegion.delete') }}</el-button>
          </div>
        </div>
        <div v-if="treeLoading" class="flex-1 flex items-center justify-center text-slate-400">{{ t('channelRegion.loading') }}</div>
        <el-scrollbar v-else class="flex-1">
          <el-tree
            :data="treeData"
            :props="{ label: 'label', children: 'children' }"
            node-key="id"
            highlight-current
            default-expand-all
            @node-click="onTreeClick"
            @node-contextmenu="onTreeContextMenu"
          />
        </el-scrollbar>
      </div>

      <el-dialog v-model="regionDialogVisible" :title="regionDialogMode === 'add' ? t('channelRegion.addRegionTitle') : t('channelRegion.editRegionTitle')" width="440px">
        <el-form :model="regionForm" label-width="80px" size="default">
          <el-form-item :label="t('channelRegion.regionCode')" v-if="regionDialogMode === 'add'">
            <el-input v-model="regionForm.code" :placeholder="t('channelRegion.regionCodePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('channelRegion.regionName')">
            <el-input v-model="regionForm.name" :placeholder="t('channelRegion.regionNamePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('channelRegion.sort')">
            <el-input-number v-model="regionForm.sort_order" :min="0" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="regionDialogVisible = false">{{ t('channelRegion.cancel') }}</el-button>
          <el-button type="primary" @click="submitRegionForm" :loading="regionSubmitting">{{ t('channelRegion.confirm') }}</el-button>
        </template>
      </el-dialog>

      <div class="flex-1 flex flex-col min-w-0 border rounded-lg bg-white p-3">
        <el-form :inline="true" size="small" class="mb-2">
          <el-radio-group v-model="viewMode" size="small" class="mr-2" @change="onModeChange">
            <el-radio-button value="normal">{{ t('channelRegion.mounted') }}</el-radio-button>
            <el-radio-button value="unusual">{{ t('channelRegion.abnormalData') }}</el-radio-button>
          </el-radio-group>
          <el-breadcrumb v-if="regionParents.length" separator="/">
            <el-breadcrumb-item v-for="p in regionParents" :key="p">{{ p }}</el-breadcrumb-item>
          </el-breadcrumb>
          <span v-else class="text-sky-600 text-sm">{{ viewMode === 'normal' ? t('channelRegion.noRegionSelected') : t('channelRegion.abnormalRegionChannel') }}</span>
          <div class="float-right flex flex-wrap gap-2 items-center">
            <el-input v-model="searchStr" :placeholder="t('channelRegion.keyword')" clearable style="width: 140px" @keyup.enter="search" />
            <el-select v-model="online" style="width: 110px" @change="search">
              <el-option :label="t('channelRegion.all')" value="" />
              <el-option :label="t('channelRegion.online')" value="true" />
              <el-option :label="t('channelRegion.offline')" value="false" />
            </el-select>
            <el-select v-model="channelType" style="width: 120px" @change="loadList">
              <el-option :label="t('channelRegion.all')" value="" />
              <el-option v-for="t in typeOpts" :key="t.id" :label="t.name" :value="String(t.id)" />
            </el-select>
            <el-button v-if="viewMode === 'normal'" type="primary" :disabled="!regionDeviceId" @click="openPickCh">{{ t('channelRegion.addChannel') }}</el-button>
            <el-dropdown v-if="viewMode === 'normal'" trigger="click" @command="handleNormalMoreCommand">
              <el-button plain class="table-action-more">{{ t('channelRegion.more') }}</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="removeSel" :disabled="!multipleSelection.length">{{ t('channelRegion.removeChannel') }}</el-dropdown-item>
                  <el-dropdown-item command="removeByDevice" :disabled="!regionDeviceId">{{ t('channelRegion.removeByDevice') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button v-if="viewMode === 'unusual'" type="warning" @click="clearUnusual(true)">{{ t('channelRegion.oneClickClear') }}</el-button>
            <el-dropdown v-if="viewMode === 'unusual'" trigger="click" @command="handleUnusualMoreCommand">
              <el-button plain class="table-action-more">{{ t('channelRegion.more') }}</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="clearSelected" :disabled="!multipleSelection.length">{{ t('channelRegion.clearSelected') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button :icon="RefreshRight" circle @click="loadList" :title="t('channelRegion.refreshList')" />
          </div>
        </el-form>

        <el-table
          v-loading="loading"
          :data="channelList"
          size="small"
          class="flex-1"
          height="calc(100vh - 260px)"
          @selection-change="(rows: Record<string, unknown>[]) => (multipleSelection = rows)"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="gbName" :label="t('channelRegion.colName')" min-width="140" show-overflow-tooltip />
          <el-table-column prop="gbDeviceId" :label="t('channelRegion.colCode')" min-width="130" />
          <el-table-column prop="gbManufacturer" :label="t('channelRegion.colManufacturer')" width="90" />
          <el-table-column v-if="viewMode === 'unusual'" prop="gbCivilCode" :label="t('channelRegion.colCivilCode')" width="120" />
          <el-table-column v-if="viewMode === 'unusual'" prop="gbParentId" :label="t('channelRegion.colParentNode')" min-width="140" show-overflow-tooltip />
          <el-table-column :label="t('channelRegion.colType')" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :style="channelTypeTag(row.dataType).style">
                {{ channelTypeTag(row.dataType).name }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('channelRegion.colStatus')" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.gbStatus === 'ON'" size="small" type="success">{{ t('channelRegion.online') }}</el-tag>
              <el-tag v-else size="small" type="info">{{ t('channelRegion.offline') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="viewMode === 'unusual'" :label="t('channelRegion.colAction')" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="clearOne(row)">{{ t('channelRegion.clear') }}</el-button>
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

    <AppDialog v-model="pickChVisible" :title="t('channelRegion.addToRegionTitle')" size="large">
      <div class="text-xs text-slate-500 mb-2">{{ t('channelRegion.pickModeTip') }}</div>
      <el-radio-group v-model="pickMode" size="small" class="mb-3">
        <el-radio-button value="channel">{{ t('channelRegion.byChannel') }}</el-radio-button>
        <el-radio-button value="device">{{ t('channelRegion.byDevice') }}</el-radio-button>
      </el-radio-group>

      <div v-if="pickMode === 'channel'">
        <el-input v-model="pickKw" :placeholder="t('channelRegion.searchGbOrName')" clearable class="mb-2" @keyup.enter="searchPick" />
        <el-button size="small" type="primary" class="mb-2" @click="searchPick">{{ t('channelRegion.query') }}</el-button>
        <el-table :data="pickRows" size="small" max-height="360" @selection-change="(r: Record<string, unknown>[]) => (pickSel = r)">
          <el-table-column type="selection" width="45" />
          <el-table-column prop="gbDeviceId" :label="t('channelRegion.colChannelCode')" width="160" />
          <el-table-column prop="gbName" :label="t('channelRegion.colName')" />
          <el-table-column prop="deviceId" :label="t('channelRegion.colDevice')" width="140" />
        </el-table>
      </div>

      <div v-else>
        <el-form :inline="true" size="small">
          <el-form-item :label="t('channelRegion.deviceIdList')" class="w-full">
            <el-input
              v-model="pickDeviceIdsText"
              type="textarea"
              :rows="4"
              :placeholder="t('channelRegion.deviceIdListPlaceholder')"
            />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="pickChVisible = false">{{ t('channelRegion.cancel') }}</el-button>
        <el-button type="primary" @click="confirmPick">{{ t('channelRegion.confirm') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="removeByDeviceVisible" :title="t('channelRegion.removeByDeviceTitle')" size="medium">
      <div class="text-xs text-slate-500 mb-2">{{ t('channelRegion.removeByDeviceTip') }}</div>
      <el-input
        v-model="removeByDeviceIdsText"
        type="textarea"
        :rows="5"
        :placeholder="t('channelRegion.deviceIdListPlaceholder')"
      />
      <template #footer>
        <el-button @click="removeByDeviceVisible = false">{{ t('channelRegion.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRemoveByDevice">{{ t('channelRegion.confirmRemove') }}</el-button>
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
  { id: 1, name: t('channelRegion.typeGbDevice') },
  { id: 2, name: t('channelRegion.typePushDevice') },
  { id: 3, name: t('channelRegion.typeStreamProxy') }
])

const treeLoading = ref(false)
const treeData = ref<Channel[]>([])
const regionDeviceId = ref('')
const regionParents = ref<string[]>([])
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
    const res = await api.get('/api/v1/devices/tree')
    treeData.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    treeData.value = []
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    treeLoading.value = false
  }
}

const onTreeClick = (data: Record<string, unknown>) => {
  regionDeviceId.value = String(data?.id || '').trim()
  regionParents.value = data?.label ? [String(data.label)] : []
  currentPage.value = 1
  loadList()
}

const loadList = async () => {
  if (viewMode.value === 'normal' && !regionDeviceId.value) {
    channelList.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const url = viewMode.value === 'normal' ? '/api/common/channel/civilcode/list' : '/api/common/channel/civilCode/unusual/list'
    const res = await api.get(url, {
      params: {
        page: currentPage.value,
        count: count.value,
        query: searchStr.value || undefined,
        online: online.value === '' ? undefined : online.value,
        channelType: channelType.value === '' ? undefined : Number(channelType.value),
        civilCode: viewMode.value === 'normal' ? regionDeviceId.value : undefined
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
    await ElMessageBox.confirm(t('channelRegion.removeConfirm', { n: ids.length }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/region/delete', { channelIds: ids })
    ElMessage.success(t('channelRegion.removed'))
    multipleSelection.value = []
    loadList()
    loadTree()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const clearUnusual = async (all: boolean) => {
  const ids = multipleSelection.value.map((r: Record<string, unknown>) => r.gbId)
  if (!all && !ids.length) return
  try {
    await ElMessageBox.confirm(all ? t('channelRegion.clearAllConfirm') : t('channelRegion.clearSelectedConfirm', { n: ids.length }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/civilCode/unusual/clear', {
      all,
      channelIds: all ? [] : ids
    })
    ElMessage.success(t('channelRegion.clearDone'))
    multipleSelection.value = []
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const clearOne = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(t('channelRegion.clearOneConfirm', { id: row.gbDeviceId }), t('common.tips'), { type: 'warning' })
    await api.post('/api/common/channel/civilCode/unusual/clear', {
      all: false,
      channelIds: [row.gbId]
    })
    ElMessage.success(t('channelRegion.clearDone'))
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
  if (!regionDeviceId.value) return
  const code = regionDeviceId.value.replace(/^region:/, '').replace(/\D/g, '').slice(0, 6)
  if (code.length < 6) {
    ElMessage.warning(t('channelRegion.selectValidRegion'))
    return
  }

  try {
    if (pickMode.value === 'channel') {
      const ids = pickSel.value.map((r: Record<string, unknown>) => r.gbId)
      if (!ids.length) return
      await api.post('/api/common/channel/region/add', { civilCode: code, channelIds: ids })
    } else {
      const deviceIds = pickDeviceIdsText.value
        .split(/[,，\n\r\t ]+/)
        .map(x => String(x || '').trim())
        .filter(Boolean)
      if (!deviceIds.length) {
        ElMessage.warning(t('channelRegion.fillDeviceIds'))
        return
      }
      await api.post('/api/common/channel/region/device/add', {
        civilCode: code,
        deviceIds
      })
    }

    ElMessage.success(t('channelRegion.added'))
    pickChVisible.value = false
    loadList()
    loadTree()
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
    ElMessage.warning(t('channelRegion.fillDeviceIds'))
    return
  }
  try {
    await ElMessageBox.confirm(t('channelRegion.removeByDeviceConfirm', { n: deviceIds.length }), t('common.tips'), { type: 'warning' })
  } catch { return }
  try {
    await api.post('/api/common/channel/region/device/delete', {
      deviceIds
    })
    ElMessage.success(t('channelRegion.removed'))
    removeByDeviceVisible.value = false
    loadList()
    loadTree()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const currentRegionId = ref('')
const regionDialogVisible = ref(false)
const regionDialogMode = ref<'add' | 'edit'>('add')
const regionSubmitting = ref(false)
const regionForm = ref({ code: '', name: '', parent_id: '', sort_order: 0 })

const showAddRegionDialog = () => {
  regionDialogMode.value = 'add'
  regionForm.value = { code: '', name: '', parent_id: currentRegionId.value, sort_order: 0 }
  regionDialogVisible.value = true
}

const onTreeContextMenu = (data: Record<string, unknown>, _node?: TreeNode, _component?: unknown, _e?: MouseEvent) => {
  currentRegionId.value = String(data?.id || data?.code || '')
  regionDialogMode.value = 'edit'
  regionForm.value = { code: String(data?.code || ''), name: String(data?.label || data?.name || ''), parent_id: '', sort_order: Number(data?.sort_order || 0) }
  regionDialogVisible.value = true
}

const submitRegionForm = async () => {
  if (!regionForm.value.name.trim()) {
    ElMessage.warning(t('channelRegion.pleaseInputName'))
    return
  }
  regionSubmitting.value = true
  try {
    if (regionDialogMode.value === 'add') {
      if (!regionForm.value.code.trim()) {
        ElMessage.warning(t('channelRegion.pleaseInputCode'))
        regionSubmitting.value = false
        return
      }
      await api.post('/api/v1/regions', regionForm.value)  // FIXED: 移除末尾多余斜杠
      ElMessage.success(t('channelRegion.regionCreated'))
    } else {
      await api.put(`/api/v1/regions/${currentRegionId.value}`, { name: regionForm.value.name, sort_order: regionForm.value.sort_order })
      ElMessage.success(t('channelRegion.regionUpdated'))
    }
    regionDialogVisible.value = false
    await loadTree()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    regionSubmitting.value = false
  }
}

const deleteCurrentRegion = async () => {
  if (!currentRegionId.value) return
  try {
    await ElMessageBox.confirm(t('channelRegion.deleteRegionConfirm'), t('channelRegion.deleteRegionTitle'), { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/v1/regions/${currentRegionId.value}`)
    ElMessage.success(t('channelRegion.regionDeleted'))
    currentRegionId.value = ''
    await loadTree()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

onMounted(() => {
  loadTree()
})
</script>
