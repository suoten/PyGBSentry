<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('assetPage.title')" :description="t('assetPage.description')">
          <template #actions>
            <el-button @click="loadLedger" :loading="loadingLedger">{{ t('assetPage.refreshLedger') }}</el-button>
            <el-button @click="loadMaintenances" :loading="loadingM">{{ t('assetPage.refreshMaintenance') }}</el-button>
          </template>
        </PageHeader>
      </template>

      <el-tabs v-model="activeTab" class="mb-4">
        <el-tab-pane :label="t('assetPage.tabLedger')" name="ledger">
          <QueryFormSection :title="t('assetPage.filterTitle')" :default-collapsed="true">
            <el-form-item :label="t('assetPage.searchLabel')">
              <el-input v-model="keyword" :placeholder="t('assetPage.searchDevicePlaceholder')" style="width: 280px" clearable @clear="loadLedger" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadLedger">{{ t('common.query') }}</el-button>
            </el-form-item>
          </QueryFormSection>

          <TableCard>
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('assetPage.listLabel') }}</div>
                <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('assetPage.totalCount', { count: ledger.length }) }}</div>
              </div>
            </template>
            <el-table :data="paginatedLedger" v-loading="loadingLedger">
              <el-table-column prop="gb_id" :label="t('assetPage.colGbId')" width="160" />
              <el-table-column prop="name" :label="t('common.name')" min-width="120" />
              <el-table-column prop="manufacturer" :label="t('assetPage.colManufacturer')" width="100" />
              <el-table-column prop="model" :label="t('assetPage.colModel')" width="100" />
              <el-table-column prop="status" :label="t('common.status')" width="80">
                <template #default="{ row }">
                  <el-tag :type="Number(row.status) === 1 ? 'success' : 'info'">{{ Number(row.status) === 1 ? t('common.online') : t('common.offline') }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="maintenance_count" :label="t('assetPage.colMaintenanceCount')" width="100" />
              <el-table-column :label="t('common.action')" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openAddMaintenance(row.id)">{{ t('assetPage.addMaintenance') }}</el-button>
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
                :prev-text="t('common.prevPage')"
                :next-text="t('common.nextPage')"
                size="small"
              />
            </div>
          </TableCard>
        </el-tab-pane>
        <el-tab-pane :label="t('assetPage.tabMaintenance')" name="maintenance">
          <QueryFormSection :title="t('assetPage.filterConditions')" :default-collapsed="true">
            <el-form-item :label="t('assetPage.filterByDevice')">
              <el-select v-model="filterAssetId" :placeholder="t('assetPage.filterByDevice')" clearable style="width: 280px" @change="loadMaintenances">
                <el-option v-for="a in ledger" :key="a.id" :label="a.name || a.gb_id" :value="a.id" />
              </el-select>
            </el-form-item>
          </QueryFormSection>

          <TableCard>
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('assetPage.listLabel') }}</div>
                <div class="flex items-center gap-3">
                  <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('assetPage.totalCount', { count: maintenances.length }) }}</div>
                  <el-button type="primary" size="small" @click="openAddMaintenance(filterAssetId)">{{ t('assetPage.newMaintenance') }}</el-button>
                </div>
              </div>
            </template>
            <el-table :data="paginatedMaintenances" v-loading="loadingM">
              <el-table-column prop="maintenance_date" :label="t('assetPage.colDate')" width="180">
                <template #default="{ row }">{{ row.maintenance_date ? new Date(row.maintenance_date).toLocaleString() : '-' }}</template>
              </el-table-column>
              <el-table-column prop="maintenance_type" :label="t('common.type')" width="100">
                <template #default="{ row }">
                  {{ getMaintenanceTypeLabel(row.maintenance_type) }}
                </template>
              </el-table-column>
              <el-table-column prop="note" :label="t('common.remark')" min-width="200" />
              <el-table-column prop="operator" :label="t('assetPage.colOperator')" width="100" />
              <el-table-column :label="t('common.action')" width="140">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openEditMaintenance(row)">{{ t('common.edit') }}</el-button>
                  <el-button link type="danger" size="small" @click="deleteMaintenance(row.id)">{{ t('common.delete') }}</el-button>
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
                :prev-text="t('common.prevPage')"
                :next-text="t('common.nextPage')"
                size="small"
              />
            </div>
          </TableCard>

        </el-tab-pane>
      </el-tabs>

      <AppDialog v-model="showAddMaintenance" :title="editingMaintenanceId ? t('assetPage.editMaintenanceTitle') : t('assetPage.addMaintenanceTitle')" size="small">
        <el-form :model="maintenanceForm" label-width="80px">
          <el-form-item :label="t('common.device')">
            <el-select v-model="maintenanceForm.asset_id" :placeholder="t('common.selectDevice')" class="w-full">
              <el-option v-for="a in ledger" :key="a.id" :label="a.name || a.gb_id" :value="a.id" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('common.type')">
            <el-select v-model="maintenanceForm.maintenance_type" class="w-full">
              <el-option :label="t('assetPage.typeRoutine')" value="routine" />
              <el-option :label="t('assetPage.typeRepair')" value="repair" />
              <el-option :label="t('assetPage.typeUpgrade')" value="upgrade" />
              <el-option :label="t('assetPage.typeReplace')" value="replace" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('assetPage.colDate')">
            <el-date-picker v-model="maintenanceForm.maintenance_date" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" class="w-full" />
          </el-form-item>
          <el-form-item :label="t('common.remark')">
            <el-input v-model="maintenanceForm.note" type="textarea" rows="2" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddMaintenance = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="submitMaintenance">{{ t('common.ok') }}</el-button>
        </template>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import QueryFormSection from '../components/QueryFormSection.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const { t } = useI18n()

const maintenanceTypeLabels = computed<Record<string, string>>(() => ({
  routine: t('assetPage.typeRoutine'),
  repair: t('assetPage.typeRepair'),
  upgrade: t('assetPage.typeUpgrade'),
  replace: t('assetPage.typeReplace')
}))

const getMaintenanceTypeLabel = (value: unknown) => {
  const key = String(value || '').trim()
  return maintenanceTypeLabels.value[key] || String(value || '')
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
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
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
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
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
    ElMessage.warning(t('assetPage.pleaseSelectDevice'))
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
      ElMessage.success(t('common.updated'))
    } else {
      await api.post('/api/v1/asset-management/maintenances', {
        asset_id: maintenanceForm.value.asset_id,
        maintenance_type: maintenanceForm.value.maintenance_type,
        maintenance_date: maintenanceForm.value.maintenance_date,
        note: maintenanceForm.value.note || undefined
      })
      ElMessage.success(t('assetPage.addedSuccess'))
    }
    showAddMaintenance.value = false
    activeTab.value = 'maintenance'
    filterAssetId.value = addedAssetId
    await loadMaintenances()
    await loadLedger()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  }
}

const deleteMaintenance = async (id: string) => {
  try {
    await ElMessageBox.confirm(t('assetPage.deleteConfirmMsg'), t('assetPage.deleteConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/asset-management/maintenances/${id}`)
    ElMessage.success(t('common.deleted'))
    loadMaintenances()
    loadLedger()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  }
}

onMounted(() => {
  loadLedger()
  loadMaintenances()
})
</script>
