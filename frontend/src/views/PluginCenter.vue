<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('plugin.title')" :description="t('plugin.description')" />  <!-- FIXED: 硬编码中文→t() -->
      </template>

    <el-row :gutter="16" class="mb-4">
      <el-col :span="8">
        <el-card shadow="never">
          <el-statistic :title="t('plugin.marketPlugins')" :value="marketplaceList.length" />  <!-- FIXED: 硬编码中文→t() -->
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <el-statistic :title="t('plugin.installedPlugins')" :value="installedList.length" />  <!-- FIXED: 硬编码中文→t() -->
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <el-statistic :title="t('plugin.purchasedPaid')" :value="purchasedPaidCount" />  <!-- FIXED: 硬编码中文→t() -->
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="showSuperuserZipUpload" :gutter="16" class="mb-4">
      <el-col :span="24">
        <TableCard>
          <template #header>
            <div class="font-medium">{{ t('plugin.localUploadTitle') }}</div>
          </template>
          <p class="text-xs mb-3" style="color: var(--el-text-color-secondary)" v-html="sanitizeHtml(t('plugin.localUploadDesc'))"></p>
          <el-upload
            ref="ossZipUploadRef"
            :limit="1"
            accept=".zip"
            :http-request="handleOssPluginZipUpload"
          >
            <el-button type="primary" :loading="ossZipUploading" :disabled="ossZipUploading">{{ t('plugin.selectZipAndInstall') }}</el-button>
            <template #tip>
              <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">{{ t('plugin.installSuccessListRefresh') }}</div>
            </template>
          </el-upload>
        </TableCard>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <TableCard>
          <template #header>
            <div class="flex items-center justify-between">
              <div class="font-medium">{{ t('plugin.marketTitle') }}</div>
              <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.marketDesc') }}</div>
            </div>
          </template>
          <TableSkeleton v-if="marketLoading && marketplaceList.length === 0" :rows="5" />
          <el-table
            v-else
            class="plugin-marketplace-table"
            :data="paginatedMarketplaceList"
            stripe
            v-loading="marketLoading"
            :empty-text="marketplaceEmptyText"
          >
            <el-table-column :label="t('plugin.colName')" min-width="160">
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="$router.push('/plugins/detail/' + row.id)">{{ row.name }}</el-link>
                <el-tag v-if="row.is_official" size="small" type="primary" class="ml-1">{{ t('plugin.official') }}</el-tag>
                <el-tag v-if="row.status === 'deprecated'" size="small" type="danger" class="ml-1">{{ t('plugin.deprecated') }}</el-tag>
                <el-tag v-else-if="row.min_oss_version" size="small" type="info" class="ml-1">≥ {{ row.min_oss_version }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="version" :label="t('common.version')" width="100" />
            <el-table-column :label="t('common.type')" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'free' ? 'success' : 'warning'">
                  {{ row.type === 'free' ? t('plugin.free') : t('plugin.paid') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('plugin.price')" width="120">
              <template #default="{ row }">
                <span v-if="row.type === 'free'">-</span>
                <span v-else class="text-orange-500 font-medium">¥{{ row.price_monthly || 0 }}{{ t('plugin.perMonth') }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action')" width="140">
              <template #default="{ row }">
                <el-button
                  v-if="row.type === 'paid' && !isPurchased(row.id)"
                  type="warning"
                  size="small"
                  @click="openEmbeddedPurchase(row)"
                >
                  {{ t('plugin.buyNow') }}
                </el-button>
                <el-button
                  v-else-if="row.type === 'paid' && isPurchased(row.id)"
                  type="primary"
                  size="small"
                  :disabled="installing"
                  @click="installPlugin(row)"
                >
                  {{ t('plugin.install') }}
                </el-button>
                <el-button
                  v-else
                  type="primary"
                  size="small"
                  :disabled="installing"
                  @click="installPlugin(row)"
                >
                  {{ t('plugin.install') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="flex justify-end mt-4 pagination-wrapper" v-if="marketplaceList.length > 0">
            <el-pagination
              v-model:current-page="marketPage"
              v-model:page-size="marketPageSize"
              :total="marketplaceList.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
              :prev-text="t('pagination.prev')"
              :next-text="t('pagination.next')"
              size="small"
            />
          </div>
        </TableCard>
      </el-col>
      <el-col :span="12">
        <TableCard>
          <template #header>
            <div class="flex items-center justify-between">
              <div class="font-medium">{{ t('plugin.installedPlugins') }}</div>
              <div class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.installedDesc') }}</div>
            </div>
          </template>
          <TableSkeleton v-if="installedLoading && installedList.length === 0" :rows="4" />
          <el-table v-else :data="paginatedInstalledList" stripe v-loading="installedLoading" :empty-text="t('plugin.noInstalled')">
            <el-table-column :label="t('plugin.colName')" min-width="140">
              <template #default="{ row }">
                <span>{{ row.name }}</span>
                <el-tag v-if="row.type === 'paid' && !isPurchased(row.id)" size="small" type="danger" class="ml-1">{{ t('plugin.expired') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="version" :label="t('common.version')" width="120" />
            <el-table-column :label="t('common.type')" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'free' ? 'success' : 'warning'">
                  {{ row.type === 'free' ? t('plugin.free') : t('plugin.paid') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isServerEdition" :label="t('plugin.healthStatus')" width="100">
              <template #default="{ row }">
                <template v-if="pluginHealthMap[row.id]">
                  <el-tag v-if="pluginHealthMap[row.id].healthy" size="small" type="success">{{ t('common.normal') }}</el-tag>
                  <el-tooltip v-else :content="pluginHealthMap[row.id].last_error ? t('plugin.errorCountWithDetail', { count: pluginHealthMap[row.id].error_count, detail: pluginHealthMap[row.id].last_error }) : t('plugin.errorCount', { count: pluginHealthMap[row.id].error_count })">
                    <el-tag size="small" type="danger">{{ t('plugin.abnormal') }}</el-tag>
                  </el-tooltip>
                </template>
                <span v-else class="text-gray-400 text-xs">-</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isServerEdition" :label="t('plugin.securityScan')" width="100">
              <template #default="{ row }">
                <template v-if="pluginSecurityReports[row.id]">
                  <el-tag size="small" :type="pluginSecurityReports[row.id].risk_level === 'high' ? 'danger' : pluginSecurityReports[row.id].risk_level === 'medium' ? 'warning' : 'success'">
                    {{ pluginSecurityReports[row.id].risk_level === 'high' ? t('plugin.riskHigh') : pluginSecurityReports[row.id].risk_level === 'medium' ? t('plugin.riskMedium') : t('plugin.riskLow') }}
                  </el-tag>
                </template>
                <span v-else class="text-gray-400 text-xs">-</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action')" width="120">
              <template #default="{ row }">
                <el-button type="danger" size="small" :disabled="installing" @click="uninstallPlugin(row.id)">
                  {{ t('plugin.uninstall') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="flex justify-end mt-4 pagination-wrapper" v-if="installedList.length > 0">
            <el-pagination
              v-model:current-page="installedPage"
              v-model:page-size="installedPageSize"
              :total="installedList.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
              :prev-text="t('pagination.prev')"
              :next-text="t('pagination.next')"
              size="small"
            />
          </div>
        </TableCard>
      </el-col>
    </el-row>

    <el-dialog
      v-model="purchaseDialogVisible"
      :title="t('plugin.purchaseDialogTitle', { name: purchaseTarget?.name || '' })"
      width="480px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-if="purchaseTarget" class="purchase-dialog-content">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item :label="t('plugin.fieldName')">{{ purchaseTarget.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.type')">
            <el-tag size="small" type="warning">{{ t('plugin.paid') }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('plugin.price')">
            <span v-if="purchaseTarget.price_monthly" class="text-orange-500 font-medium">
              ¥{{ purchaseTarget.price_monthly }}{{ t('plugin.perMonth') }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <el-form label-width="80px" class="mt-4">
          <el-form-item v-if="isServerEdition" :label="t('plugin.billingPeriod')">
            <el-radio-group v-model="purchaseBillingPeriod">
              <el-radio value="monthly">{{ t('plugin.monthly') }}</el-radio>
              <el-radio value="yearly">{{ t('plugin.yearly') }}</el-radio>
              <el-radio value="perpetual">{{ t('plugin.perpetual') }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <el-alert
          v-if="purchaseError"
          :title="purchaseError"
          type="error"
          show-icon
          :closable="false"
          class="mt-3"
        />
      </div>
      <template #footer>
        <el-button @click="purchaseDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="purchaseLoading" @click="doEmbeddedPurchase">
          {{ t('plugin.confirmPurchase') }}
        </el-button>
      </template>
    </el-dialog>

    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadInstance, UploadRequestOptions } from 'element-plus'
import api from '@/utils/http'
import { logger } from '@/utils/logger'

import TableSkeleton from '../components/TableSkeleton.vue'
import { getFriendlyError, promptUpgradeHookReportIfPresent } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getVerifiedRoleInfo } from '../utils/auth' // FIX C-3: 改用后端验证角色
import { sanitizeHtml } from '@/utils/sanitize'

// FIX: [2026-07-04] useI18n 已导入但未解构 t，模板/脚本中 t 为 undefined 导致 ReferenceError [全栈工程师]
const { t } = useI18n()
const router = useRouter()

type PluginRow = {
  id: string
  name: string
  version: string
  type: string
  package_url?: string
  status?: string
  deprecated_message?: string
  min_oss_version?: string
  is_official?: boolean
  price_monthly?: number
}

// 插件市场
const marketplaceList = ref<PluginRow[]>([])
const marketPage = ref(1)
const marketPageSize = ref(10)
const paginatedMarketplaceList = computed(() => {
  const start = (marketPage.value - 1) * marketPageSize.value
  const end = start + marketPageSize.value
  return marketplaceList.value.slice(start, end)
})
watch(marketplaceList, () => { marketPage.value = 1 })

// 已安装插件
const installedList = ref<PluginRow[]>([])
const installedPage = ref(1)
const installedPageSize = ref(10)
const paginatedInstalledList = computed(() => {
  const start = (installedPage.value - 1) * installedPageSize.value
  const end = start + installedPageSize.value
  return installedList.value.slice(start, end)
})
watch(installedList, () => { installedPage.value = 1 })

const purchasedIds = ref<string[]>([])
const marketLoading = ref(false)
const installedLoading = ref(false)
const marketplaceEmptyText = ref(t('plugin.marketEmpty'))
const installing = ref(false)
const showSuperuserZipUpload = ref(false)

// 插件健康监控
const pluginHealthMap = ref<Record<string, { healthy: boolean; error_count: number; last_error: string }>>({})

// 插件安全扫描报告
const pluginSecurityReports = ref<Record<string, Record<string, unknown>>>({})

const isServerEdition = (import.meta.env.VITE_APP_EDITION || 'oss') === 'server'

const loadPluginHealth = async () => {
  if (!isServerEdition) return
  try {
    const res = await api.get('/api/v1/plugins/runtime/health-status')
    if (res.data?.items && Array.isArray(res.data.items)) {
      for (const item of res.data.items) {
        pluginHealthMap.value[item.plugin_id] = {
          healthy: item.healthy,
          error_count: item.error_count || 0,
          last_error: item.last_error || '',
        }
      }
    }
  } catch { pluginHealthMap.value = {}; logger.warn('加载插件健康数据失败') }
}

const loadSecurityReports = async () => {
  if (!isServerEdition) return
  try {
    const res = await api.get('/api/v1/plugins/runtime/security-report')
    if (res.data?.items && Array.isArray(res.data.items)) {
      for (const item of res.data.items) {
        pluginSecurityReports.value[item.plugin_id] = item
      }
    }
  } catch { pluginSecurityReports.value = {}; logger.warn('加载插件安全报告失败') }
}
const ossZipUploadRef = ref<UploadInstance>()
const ossZipUploading = ref(false)
const shopUrl = ref('')

const isPurchased = (pluginId: string) => purchasedIds.value.includes(pluginId)
const purchasedPaidCount = computed(() => purchasedIds.value.length)

const purchaseDialogVisible = ref(false)
const purchaseTarget = ref<PluginRow | null>(null)
const purchaseBillingPeriod = ref<'monthly' | 'yearly' | 'perpetual'>('monthly')
const purchaseLoading = ref(false)
let paymentPollingTimer: ReturnType<typeof setInterval> | null = null
const purchaseError = ref('')

const openEmbeddedPurchase = (row: PluginRow) => {
  purchaseTarget.value = row
  purchaseBillingPeriod.value = 'monthly'
  purchaseError.value = ''
  purchaseDialogVisible.value = true
}

const doEmbeddedPurchase = async () => {
  if (!purchaseTarget.value) return
  purchaseLoading.value = true
  purchaseError.value = ''
  try {
    const res = await api.post('/api/v1/plugins/marketplace/purchase', {
      plugin_id: purchaseTarget.value.id,
      billing_period: purchaseBillingPeriod.value,
    }, { skipFriendlyMessage: true })
    const orderData = res.data
    if (orderData.status === 'paid' || orderData.status === 'active') {
      purchaseDialogVisible.value = false
      ElMessage.success(t('plugin.buySuccessInstalling'))
      await installPlugin(purchaseTarget.value)
    } else if (orderData.payment_url) {
      purchaseDialogVisible.value = false
      ElMessage.info(t('plugin.payPageHint'))
      const payWindow = window.open(orderData.payment_url, '_blank', 'width=600,height=700')
      if (paymentPollingTimer) clearInterval(paymentPollingTimer)
      let paymentPollRetries = 0
      paymentPollingTimer = setInterval(async () => {
        if (payWindow?.closed) {
          clearInterval(paymentPollingTimer!)
          paymentPollingTimer = null
          return
        }
        try {
          const checkRes = await api.post('/api/v1/plugins/marketplace/purchase/confirm', {
            order_id: orderData.order_id,
          }, { skipFriendlyMessage: true })
          if (checkRes.data.status === 'paid' || checkRes.data.status === 'active') {
            clearInterval(paymentPollingTimer!)
            paymentPollingTimer = null
            payWindow?.close()
            ElMessage.success(t('plugin.paySuccessInstalling'))
            if (purchaseTarget.value) {
              await installPlugin(purchaseTarget.value)
            }
          }
        } catch {
          paymentPollRetries++
          if (paymentPollRetries >= 20) {
            clearInterval(paymentPollingTimer!)
            paymentPollingTimer = null
            ElMessage.warning(t('plugin.payTimeout'))
          }
        }
      }, 3000)
    } else {
      purchaseDialogVisible.value = false
      ElMessage.success(t('plugin.orderCreated'))
      await loadData()
    }
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    purchaseError.value = friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message
  } finally {
    purchaseLoading.value = false
  }
}

const emitPluginUpdated = () => {
  window.dispatchEvent(new Event('plugins-updated'))
}

// FIX C-3: 改用后端验证的权威角色信息
const refreshSuperuserZipVisibility = async () => {
  const info = await getVerifiedRoleInfo()
  showSuperuserZipUpload.value = !!info?.isSuperuser
}

type UploadErrorCallbackArg = Parameters<NonNullable<UploadRequestOptions['onError']>>[0]

const handleOssPluginZipUpload = async (options: UploadRequestOptions) => {
  ossZipUploading.value = true
  const form = new FormData()
  form.append('file', options.file)
  try {
    const res = await api.post('/api/v1/plugins/upload', form, { skipFriendlyMessage: true })
    const data = res.data as { plugin_id?: string; operation?: string; version?: string }
    const pid = String(data.plugin_id || '').trim()
    const op = String(data.operation || 'install')
    if (op === 'upgrade') {
      ElMessage.success(t('plugin.upgradeSuccess', { pid, version: data.version || '' }))
    } else {
      ElMessage.success(pid ? t('plugin.installSuccessWithName', { pid }) : t('plugin.installSuccess'))
    }
    emitPluginUpdated()
    await loadData()
    options.onSuccess(data as Record<string, unknown>)
    ossZipUploadRef.value?.clearFiles()
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    const line = friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message
    ElMessage.error(line)
    await promptUpgradeHookReportIfPresent(friendly)
    options.onError?.(new Error(line) as UploadErrorCallbackArg)
  } finally {
    ossZipUploading.value = false
  }
}

const loadData = async () => {
  marketLoading.value = true
  installedLoading.value = true
  marketplaceEmptyText.value = t('common.loading')
  try {
    let marketData: PluginRow[] = []
    try {
      const res = await api.get('/api/v1/plugins/marketplace')
      marketData = Array.isArray(res.data) ? res.data : []
    } catch {
      marketplaceEmptyText.value = t('plugin.marketLoadFailed')
    }
    marketplaceList.value = marketData
    if (marketData.length === 0 && marketplaceEmptyText.value === t('common.loading')) {
      marketplaceEmptyText.value = t('plugin.noAvailablePlugins')
    }

    const [installedRes, shopRes, purchasedRes] = await Promise.all([
      api.get('/api/v1/plugins/installed'),
      api.get('/api/v1/plugins/marketplace-shop-url').catch(() => ({ data: { url: '' } })),
      api.get('/api/v1/plugins/purchased').catch(() => ({ data: { plugin_ids: [] } }))
    ])
    installedList.value = Array.isArray(installedRes.data) ? installedRes.data : []
    shopUrl.value = (shopRes?.data?.url || '').trim() || ''
    purchasedIds.value = Array.isArray(purchasedRes?.data?.plugin_ids) ? purchasedRes.data.plugin_ids : []
  } finally {
    marketLoading.value = false
    installedLoading.value = false
  }
}

const onPurchaseSync = () => {
  void loadData()
}

const installPlugin = async (row: PluginRow) => {
  installing.value = true
  try {
    const res = await api.post(
      '/api/v1/plugins/marketplace/install',
      {
        plugin_id: row.id,
        package_url: row.package_url || null
      },
      { skipFriendlyMessage: true }
    )
    const data = res.data as { operation?: string; version?: string }
    const op = String(data?.operation || '')
    await loadData()
    emitPluginUpdated()
    if (op === 'upgrade') {
      ElMessage.success(data?.version ? t('plugin.updatedToVersion', { version: data.version }) : t('plugin.updatedLatest'))
    } else {
      ElMessage.success(t('plugin.installAndOpen'))
      await router.push(`/plugins/runtime/${row.id}`)
    }
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
    await promptUpgradeHookReportIfPresent(friendly)
  } finally {
    installing.value = false
  }
}

const uninstallPlugin = async (pluginId: string) => {
  let tableHint = ''
  try {
    const prev = await api.get(`/api/v1/plugins/${pluginId}/uninstall-preview`)
    const tables: string[] = Array.isArray(prev.data?.tables) ? prev.data.tables : []
    if (tables.length > 0) {
      tableHint = '\n\n' + t('plugin.uninstallTableHint', { tables: tables.join('、') })
    }
  } catch {
    logger.warn('卸载预览失败，继续卸载流程')
  }
  try {
    await ElMessageBox.confirm(
      t('plugin.uninstallConfirmMessage', { tableHint }),
      t('plugin.uninstallConfirmTitle'),
      { type: 'warning', confirmButtonText: t('plugin.uninstall'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }
  installing.value = true
  try {
    await api.delete(`/api/v1/plugins/${pluginId}`)
    await loadData()
    emitPluginUpdated()
    ElMessage.success(t('plugin.uninstallSuccess'))
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    installing.value = false
  }
}

onMounted(async () => {
  try {
    refreshSuperuserZipVisibility()
    await loadData()
    loadPluginHealth()
    loadSecurityReports()
    window.addEventListener('plugin-purchases-updated', onPurchaseSync)
  } catch {
    ElMessage.error(t('plugin.loadDataFailed'))
  }
})

onActivated(() => {
  refreshSuperuserZipVisibility()
})

onUnmounted(() => {
  window.removeEventListener('plugin-purchases-updated', onPurchaseSync)
  if (paymentPollingTimer) {
    clearInterval(paymentPollingTimer)
    paymentPollingTimer = null
  }
})
</script>

<style scoped>
</style>