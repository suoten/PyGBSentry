<template>
  <div class="app-page">
    <PageContainer flex>
      <template #header>
        <PageHeader title="行政区划（通道）" description="按行政区划管理通道挂载，支持异常数据清理与批量处理" />
      </template>

      <div class="flex-1 min-h-0 flex gap-4 mt-4">
        <div class="w-96 flex flex-col border rounded-lg bg-white overflow-hidden">
        <div class="p-2 border-b text-sm font-medium flex items-center justify-between">
          <span>行政区划</span>
          <div class="flex gap-1">
            <el-button size="small" type="primary" link @click="showAddRegionDialog">新增</el-button>
            <el-button size="small" type="danger" link @click="deleteCurrentRegion" :disabled="!currentRegionId">删除</el-button>
          </div>
        </div>
        <div v-if="treeLoading" class="flex-1 flex items-center justify-center text-slate-400">加载中…</div>
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

      <el-dialog v-model="regionDialogVisible" :title="regionDialogMode === 'add' ? '新增区域' : '编辑区域'" width="440px">
        <el-form :model="regionForm" label-width="80px" size="default">
          <el-form-item label="区划代码" v-if="regionDialogMode === 'add'">
            <el-input v-model="regionForm.code" placeholder="行政区划代码" />
          </el-form-item>
          <el-form-item label="区域名称">
            <el-input v-model="regionForm.name" placeholder="区域名称" />
          </el-form-item>
          <el-form-item label="排序">
            <el-input-number v-model="regionForm.sort_order" :min="0" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="regionDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitRegionForm" :loading="regionSubmitting">确定</el-button>
        </template>
      </el-dialog>

      <div class="flex-1 flex flex-col min-w-0 border rounded-lg bg-white p-3">
        <el-form :inline="true" size="small" class="mb-2">
          <el-radio-group v-model="viewMode" size="small" class="mr-2" @change="onModeChange">
            <el-radio-button value="normal">已挂载</el-radio-button>
            <el-radio-button value="unusual">异常数据</el-radio-button>
          </el-radio-group>
          <el-breadcrumb v-if="regionParents.length" separator="/">
            <el-breadcrumb-item v-for="p in regionParents" :key="p">{{ p }}</el-breadcrumb-item>
          </el-breadcrumb>
          <span v-else class="text-sky-600 text-sm">{{ viewMode === 'normal' ? '未选择行政区划' : '异常区划通道' }}</span>
          <div class="float-right flex flex-wrap gap-2 items-center">
            <el-input v-model="searchStr" placeholder="关键字" clearable style="width: 140px" @keyup.enter="search" />
            <el-select v-model="online" style="width: 110px" @change="search">
              <el-option label="全部" value="" />
              <el-option label="在线" value="true" />
              <el-option label="离线" value="false" />
            </el-select>
            <el-select v-model="channelType" style="width: 120px" @change="loadList">
              <el-option label="全部" value="" />
              <el-option v-for="t in typeOpts" :key="t.id" :label="t.name" :value="String(t.id)" />
            </el-select>
            <el-button v-if="viewMode === 'normal'" type="primary" :disabled="!regionDeviceId" @click="openPickCh">添加通道</el-button>
            <el-dropdown v-if="viewMode === 'normal'" trigger="click" @command="handleNormalMoreCommand">
              <el-button plain class="table-action-more">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="removeSel" :disabled="!multipleSelection.length">移除通道</el-dropdown-item>
                  <el-dropdown-item command="removeByDevice" :disabled="!regionDeviceId">按设备移除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button v-if="viewMode === 'unusual'" type="warning" @click="clearUnusual(true)">一键清理</el-button>
            <el-dropdown v-if="viewMode === 'unusual'" trigger="click" @command="handleUnusualMoreCommand">
              <el-button plain class="table-action-more">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="clearSelected" :disabled="!multipleSelection.length">清理选中</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button :icon="RefreshRight" circle @click="loadList" title="刷新列表" />
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
          <el-table-column prop="gbName" label="名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="gbDeviceId" label="编号" min-width="130" />
          <el-table-column prop="gbManufacturer" label="厂家" width="90" />
          <el-table-column v-if="viewMode === 'unusual'" prop="gbCivilCode" label="区划码" width="120" />
          <el-table-column v-if="viewMode === 'unusual'" prop="gbParentId" label="父节点" min-width="140" show-overflow-tooltip />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :style="channelTypeTag(row.dataType).style">
                {{ channelTypeTag(row.dataType).name }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.gbStatus === 'ON'" size="small" type="success">在线</el-tag>
              <el-tag v-else size="small" type="info">离线</el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="viewMode === 'unusual'" label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="clearOne(row)">清理</el-button>
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

    <AppDialog v-model="pickChVisible" title="添加到行政区划" size="large">
      <div class="text-xs text-slate-500 mb-2">请选择添加模式：按通道选择 或 按设备批量。</div>
      <el-radio-group v-model="pickMode" size="small" class="mb-3">
        <el-radio-button value="channel">按通道</el-radio-button>
        <el-radio-button value="device">按设备</el-radio-button>
      </el-radio-group>

      <div v-if="pickMode === 'channel'">
        <el-input v-model="pickKw" placeholder="搜索国标/名称" clearable class="mb-2" @keyup.enter="searchPick" />
        <el-button size="small" type="primary" class="mb-2" @click="searchPick">查询</el-button>
        <el-table :data="pickRows" size="small" max-height="360" @selection-change="(r: Record<string, unknown>[]) => (pickSel = r)">
          <el-table-column type="selection" width="45" />
          <el-table-column prop="gbDeviceId" label="通道编号" width="160" />
          <el-table-column prop="gbName" label="名称" />
          <el-table-column prop="deviceId" label="设备" width="140" />
        </el-table>
      </div>

      <div v-else>
        <el-form :inline="true" size="small">
          <el-form-item label="设备ID列表" class="w-full">
            <el-input
              v-model="pickDeviceIdsText"
              type="textarea"
              :rows="4"
              placeholder="逗号分隔：如 设备A, 设备B"
            />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="pickChVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmPick">确定</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="removeByDeviceVisible" title="按设备移除（行政区划）" size="medium">
      <div class="text-xs text-slate-500 mb-2">输入设备编号列表（逗号或换行分隔），会移除这些设备下所有通道的区划挂载。</div>
      <el-input
        v-model="removeByDeviceIdsText"
        type="textarea"
        :rows="5"
        placeholder="设备A, 设备B"
      />
      <template #footer>
        <el-button @click="removeByDeviceVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmRemoveByDevice">确定移除</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { channelTypeTag } from '../constants/channelType'
import { getFriendlyError } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const typeOpts = [
  { id: 1, name: '国标设备' },
  { id: 2, name: '推流设备' },
  { id: 3, name: '拉流代理' }
]

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
    await ElMessageBox.confirm(`从当前行政区划移除 ${ids.length} 条？`, '提示', { type: 'warning' })
    await api.post('/api/common/channel/region/delete', { channelIds: ids })
    ElMessage.success('已移除')
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
    await ElMessageBox.confirm(all ? '确定清理全部异常区划通道？' : `确定清理 ${ids.length} 条异常区划通道？`, '提示', { type: 'warning' })
    await api.post('/api/common/channel/civilCode/unusual/clear', {
      all,
      channelIds: all ? [] : ids
    })
    ElMessage.success('清理完成')
    multipleSelection.value = []
    loadList()
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message)
  }
}

const clearOne = async (row: Record<string, unknown>) => {
  try {
    await ElMessageBox.confirm(`确定清理通道 ${row.gbDeviceId} 的异常区划信息？`, '提示', { type: 'warning' })
    await api.post('/api/common/channel/civilCode/unusual/clear', {
      all: false,
      channelIds: [row.gbId]
    })
    ElMessage.success('清理完成')
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
    ElMessage.warning('请先在左侧选择有效行政区划节点（需能解析出6位区划码）')
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
        ElMessage.warning('请填写设备ID列表')
        return
      }
      await api.post('/api/common/channel/region/device/add', {
        civilCode: code,
        deviceIds
      })
    }

    ElMessage.success('已添加')
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
    ElMessage.warning('请填写设备ID列表')
    return
  }
  try {
    await ElMessageBox.confirm(`确定移除 ${deviceIds.length} 个设备下所有通道的区域挂载？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await api.post('/api/common/channel/region/device/delete', {
      deviceIds
    })
    ElMessage.success('已移除')
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
    ElMessage.warning('请输入区域名称')
    return
  }
  regionSubmitting.value = true
  try {
    if (regionDialogMode.value === 'add') {
      if (!regionForm.value.code.trim()) {
        ElMessage.warning('请输入区划代码')
        regionSubmitting.value = false
        return
      }
      await api.post('/api/v1/regions', regionForm.value)  // FIXED: 移除末尾多余斜杠
      ElMessage.success('区域已创建')
    } else {
      await api.put(`/api/v1/regions/${currentRegionId.value}`, { name: regionForm.value.name, sort_order: regionForm.value.sort_order })
      ElMessage.success('区域已更新')
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
    await ElMessageBox.confirm('确定删除该区域？若存在子区域则无法删除。', '删除区域', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/v1/regions/${currentRegionId.value}`)
    ElMessage.success('区域已删除')
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
