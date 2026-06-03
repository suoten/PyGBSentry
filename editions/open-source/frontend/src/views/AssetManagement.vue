﻿<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="资产管理" description="设备台账与维保记录">
          <template #actions>
            <el-button @click="loadLedger" :loading="loadingLedger">刷新台账</el-button>
            <el-button @click="loadMaintenances" :loading="loadingM">刷新维保</el-button>
          </template>
        </PageHeader>
      </template>

      <el-tabs v-model="activeTab" class="mb-4">
        <el-tab-pane label="设备台账" name="ledger">
          <QueryFormSection title="筛选" :default-collapsed="true">
            <el-form-item label="搜索">
              <el-input v-model="keyword" placeholder="搜索设备" style="width: 280px" clearable @clear="loadLedger" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadLedger">查询</el-button>
            </el-form-item>
          </QueryFormSection>

          <TableCard>
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">列表</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ ledger.length }} 条</div>
              </div>
            </template>
            <el-table :data="paginatedLedger" v-loading="loadingLedger">
              <el-table-column prop="gb_id" label="国标ID" width="160" />
              <el-table-column prop="name" label="名称" min-width="120" />
              <el-table-column prop="manufacturer" label="厂商" width="100" />
              <el-table-column prop="model" label="型号" width="100" />
              <el-table-column prop="status" label="状态" width="80">
                <template #default="{ row }">
                  <el-tag :type="Number(row.status) === 1 ? 'success' : 'info'">{{ Number(row.status) === 1 ? '在线' : '离线' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="maintenance_count" label="维保次数" width="100" />
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openAddMaintenance(row.id)">添加维保</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="flex justify-end mt-4 pagination-wrapper" v-if="ledger.length > 0">
              <el-pagination
                v-model:current-page="ledgerPage"
                v-model:page-size="ledgerPageSize"
                :total="ledger.length"
                layout="total, sizes, prev, pager, next, jumper"
                :page-sizes="[10, 20, 50, 100]"
                prev-text="上一页"
                next-text="下一页"
                size="small"
              />
            </div>
          </TableCard>
        </el-tab-pane>
        <el-tab-pane label="维保记录" name="maintenance">
          <QueryFormSection title="筛选条件" :default-collapsed="true">
            <el-form-item label="按设备筛选">
              <el-select v-model="filterAssetId" placeholder="按设备筛选" clearable style="width: 280px" @change="loadMaintenances">
                <el-option v-for="a in ledger" :key="a.id" :label="a.name || a.gb_id" :value="a.id" />
              </el-select>
            </el-form-item>
          </QueryFormSection>

          <TableCard>
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">列表</div>
                <div class="flex items-center gap-3">
                  <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ maintenances.length }} 条</div>
                  <el-button type="primary" size="small" @click="openAddMaintenance(filterAssetId)">新增维保</el-button>
                </div>
              </div>
            </template>
            <el-table :data="paginatedMaintenances" v-loading="loadingM">
              <el-table-column prop="maintenance_date" label="日期" width="180">
                <template #default="{ row }">{{ row.maintenance_date ? new Date(row.maintenance_date).toLocaleString() : '-' }}</template>
              </el-table-column>
              <el-table-column prop="maintenance_type" label="类型" width="100">
                <template #default="{ row }">
                  {{ getMaintenanceTypeLabel(row.maintenance_type) }}
                </template>
              </el-table-column>
              <el-table-column prop="note" label="备注" min-width="200" />
              <el-table-column prop="operator" label="操作人" width="100" />
              <el-table-column label="操作" width="140">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openEditMaintenance(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="deleteMaintenance(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="flex justify-end mt-4 pagination-wrapper" v-if="maintenances.length > 0">
              <el-pagination
                v-model:current-page="maintenancePage"
                v-model:page-size="maintenancePageSize"
                :total="maintenances.length"
                layout="total, sizes, prev, pager, next, jumper"
                :page-sizes="[10, 20, 50, 100]"
                prev-text="上一页"
                next-text="下一页"
                size="small"
              />
            </div>
          </TableCard>

        </el-tab-pane>
      </el-tabs>

      <AppDialog v-model="showAddMaintenance" :title="editingMaintenanceId ? '编辑维保记录' : '新增维保记录'" size="small">
        <el-form :model="maintenanceForm" label-width="80px">
          <el-form-item label="设备">
            <el-select v-model="maintenanceForm.asset_id" placeholder="选择设备" class="w-full">
              <el-option v-for="a in ledger" :key="a.id" :label="a.name || a.gb_id" :value="a.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="maintenanceForm.maintenance_type" class="w-full">
              <el-option label="例行" value="routine" />
              <el-option label="维修" value="repair" />
              <el-option label="升级" value="upgrade" />
              <el-option label="更换" value="replace" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker v-model="maintenanceForm.maintenance_date" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" class="w-full" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="maintenanceForm.note" type="textarea" rows="2" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddMaintenance = false">取消</el-button>
          <el-button type="primary" @click="submitMaintenance">确定</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import QueryFormSection from '../components/QueryFormSection.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const maintenanceTypeLabels = {
  routine: '例行',
  repair: '维修',
  upgrade: '升级',
  replace: '更换'
} as const

const getMaintenanceTypeLabel = (value: unknown) => {
  const key = String(value || '').trim() as keyof typeof maintenanceTypeLabels
  return maintenanceTypeLabels[key] || String(value || '')
}

const activeTab = ref('ledger')
const keyword = ref('')
const ledger = ref<AssetLedger[]>([])
const loadingLedger = ref(false)
const ledgerPage = ref(1)
const ledgerPageSize = ref(10)
const paginatedLedger = computed(() => {
  const start = (ledgerPage.value - 1) * ledgerPageSize.value
  const end = start + ledgerPageSize.value
  return ledger.value.slice(start, end)
})
watch(ledger, () => { ledgerPage.value = 1 })

const loadLedger = async () => {
  loadingLedger.value = true
  try {
    const res = await api.get('/api/v1/asset-management/ledger', { params: { keyword: keyword.value } })
    ledger.value = res.data
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loadingLedger.value = false
  }
}

const filterAssetId = ref('')
const maintenances = ref<AssetLedger[]>([])
const loadingM = ref(false)
const maintenancePage = ref(1)
const maintenancePageSize = ref(10)
const paginatedMaintenances = computed(() => {
  const start = (maintenancePage.value - 1) * maintenancePageSize.value
  const end = start + maintenancePageSize.value
  return maintenances.value.slice(start, end)
})
watch(maintenances, () => { maintenancePage.value = 1 })

const loadMaintenances = async () => {
  loadingM.value = true
  try {
    const params: Record<string, string> = {}
    if (filterAssetId.value) params.asset_id = filterAssetId.value
    const res = await api.get('/api/v1/asset-management/maintenances', { params })
    maintenances.value = res.data
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loadingM.value = false
  }
}

const showAddMaintenance = ref(false)
const editingMaintenanceId = ref<string | null>(null)
const maintenanceForm = ref({
  asset_id: '',
  maintenance_type: 'routine',
  maintenance_date: new Date().toISOString().slice(0, 19),
  note: ''
})

const openAddMaintenance = (assetId?: string) => {
  editingMaintenanceId.value = null
  maintenanceForm.value = {
    asset_id: String(assetId || ''),
    maintenance_type: 'routine',
    maintenance_date: new Date().toISOString().slice(0, 19),
    note: ''
  }
  showAddMaintenance.value = true
}

const openEditMaintenance = (row: any) => {
  editingMaintenanceId.value = row.id
  maintenanceForm.value = {
    asset_id: String(row.asset_id || ''),
    maintenance_type: row.maintenance_type || 'routine',
    maintenance_date: row.maintenance_date || new Date().toISOString().slice(0, 19),
    note: row.note || ''
  }
  showAddMaintenance.value = true
}

const submitMaintenance = async () => {
  if (!maintenanceForm.value.asset_id) {
    ElMessage.warning('请选择设备')
    return
  }
  const addedAssetId = String(maintenanceForm.value.asset_id || '')
  try {
    if (editingMaintenanceId.value) {
      await api.put(`/api/v1/asset-management/maintenances/${editingMaintenanceId.value}`, {
        maintenance_type: maintenanceForm.value.maintenance_type,
        maintenance_date: maintenanceForm.value.maintenance_date,
        note: maintenanceForm.value.note || undefined
      })
      ElMessage.success('已更新')
    } else {
      await api.post('/api/v1/asset-management/maintenances', {
        asset_id: maintenanceForm.value.asset_id,
        maintenance_type: maintenanceForm.value.maintenance_type,
        maintenance_date: maintenanceForm.value.maintenance_date,
        note: maintenanceForm.value.note || undefined
      })
      ElMessage.success('已添加')
    }
    showAddMaintenance.value = false
    activeTab.value = 'maintenance'
    filterAssetId.value = addedAssetId
    await loadMaintenances()
    await loadLedger()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const deleteMaintenance = async (id: string) => {
  try {
    await ElMessageBox.confirm('确认删除该维保记录？删除后不可恢复。', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/asset-management/maintenances/${id}`)
    ElMessage.success('已删除')
    loadMaintenances()
    loadLedger()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

onMounted(() => {
  loadLedger()
  loadMaintenances()
})
</script>
