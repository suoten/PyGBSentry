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
            <div class="font-medium">本地上传安装（仅超级管理员）</div>
          </template>
          <p class="text-xs mb-3" style="color: var(--el-text-color-secondary)">
            非商城路径，适用于内测或自建包；对应接口
            <code>POST /api/v1/plugins/upload</code>。若开启
            <code>PLUGIN_UPGRADE_HOOK_STRICT</code>，升级迁移失败将返回 500，并可在弹窗中查看
            <code>upgrade_hook_report</code>。
          </p>
          <el-upload
            ref="ossZipUploadRef"
            :limit="1"
            accept=".zip"
            :http-request="handleOssPluginZipUpload"
          >
            <el-button type="primary" :loading="ossZipUploading" :disabled="ossZipUploading">选择 .zip 并安装</el-button>
            <template #tip>
              <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">安装成功后下方已装列表将刷新。</div>
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
              <div class="font-medium">插件市场</div>
              <div class="text-xs" style="color: var(--el-text-color-secondary)">浏览并购买插件，购买后回到此处安装</div>
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
            <el-table-column label="插件名" min-width="160">
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="$router.push('/plugins/detail/' + row.id)">{{ row.name }}</el-link>
                <el-tag v-if="row.is_official" size="small" type="primary" class="ml-1">官方</el-tag>
                <el-tag v-if="row.status === 'deprecated'" size="small" type="danger" class="ml-1">已废弃</el-tag>
                <el-tag v-else-if="row.min_oss_version" size="small" type="info" class="ml-1">≥ {{ row.min_oss_version }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="100" />
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'free' ? 'success' : 'warning'">
                  {{ row.type === 'free' ? '免费' : '付费' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="价格" width="120">
              <template #default="{ row }">
                <span v-if="row.type === 'free'">-</span>
                <span v-else class="text-orange-500 font-medium">¥{{ row.price_monthly || 0 }}/月</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140">
              <template #default="{ row }">
                <el-button
                  v-if="row.type === 'paid' && !isPurchased(row.id)"
                  type="warning"
                  size="small"
                  @click="openEmbeddedPurchase(row)"
                >
                  一键购买
                </el-button>
                <el-button
                  v-else-if="row.type === 'paid' && isPurchased(row.id)"
                  type="primary"
                  size="small"
                  :disabled="installing"
                  @click="installPlugin(row)"
                >
                  安装
                </el-button>
                <el-button
                  v-else
                  type="primary"
                  size="small"
                  :disabled="installing"
                  @click="installPlugin(row)"
                >
                  安装
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
              prev-text="上一页"
              next-text="下一页"
              size="small"
            />
          </div>
        </TableCard>
      </el-col>
      <el-col :span="12">
        <TableCard>
          <template #header>
            <div class="flex items-center justify-between">
              <div class="font-medium">已安装插件</div>
              <div class="text-xs" style="color: var(--el-text-color-secondary)">管理当前已启用的插件</div>
            </div>
          </template>
          <TableSkeleton v-if="installedLoading && installedList.length === 0" :rows="4" />
          <el-table v-else :data="paginatedInstalledList" stripe v-loading="installedLoading" :empty-text="'暂无已安装插件'">
            <el-table-column label="插件名" min-width="140">
              <template #default="{ row }">
                <span>{{ row.name }}</span>
                <el-tag v-if="row.type === 'paid' && !isPurchased(row.id)" size="small" type="danger" class="ml-1">已过期</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="120" />
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'free' ? 'success' : 'warning'">
                  {{ row.type === 'free' ? '免费' : '付费' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isServerEdition" label="健康状态" width="100">
              <template #default="{ row }">
                <template v-if="pluginHealthMap[row.id]">
                  <el-tag v-if="pluginHealthMap[row.id].healthy" size="small" type="success">正常</el-tag>
                  <el-tooltip v-else :content="`错误${pluginHealthMap[row.id].error_count}次` + (pluginHealthMap[row.id].last_error ? `：${pluginHealthMap[row.id].last_error}` : '')">
                    <el-tag size="small" type="danger">异常</el-tag>
                  </el-tooltip>
                </template>
                <span v-else class="text-gray-400 text-xs">-</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isServerEdition" label="安全扫描" width="100">
              <template #default="{ row }">
                <template v-if="pluginSecurityReports[row.id]">
                  <el-tag size="small" :type="pluginSecurityReports[row.id].risk_level === 'high' ? 'danger' : pluginSecurityReports[row.id].risk_level === 'medium' ? 'warning' : 'success'">
                    {{ pluginSecurityReports[row.id].risk_level === 'high' ? '高风险' : pluginSecurityReports[row.id].risk_level === 'medium' ? '中风险' : '低风险' }}
                  </el-tag>
                </template>
                <span v-else class="text-gray-400 text-xs">-</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button type="danger" size="small" :disabled="installing" @click="uninstallPlugin(row.id)">
                  卸载
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
              prev-text="上一页"
              next-text="下一页"
              size="small"
            />
          </div>
        </TableCard>
      </el-col>
    </el-row>

    <el-dialog
      v-model="purchaseDialogVisible"
      :title="`购买插件 - ${purchaseTarget?.name || ''}`"
      width="480px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-if="purchaseTarget" class="purchase-dialog-content">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="插件名称">{{ purchaseTarget.name }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag size="small" type="warning">付费</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="价格">
            <span v-if="purchaseTarget.price_monthly" class="text-orange-500 font-medium">
              ¥{{ purchaseTarget.price_monthly }}/月
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <el-form label-width="80px" class="mt-4">
          <el-form-item v-if="isServerEdition" label="计费周期">
            <el-radio-group v-model="purchaseBillingPeriod">
              <el-radio value="monthly">月付</el-radio>
              <el-radio value="yearly">年付</el-radio>
              <el-radio value="perpetual">永久</el-radio>
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
        <el-button @click="purchaseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="purchaseLoading" @click="doEmbeddedPurchase">
          确认购买
        </el-button>
      </template>
    </el-dialog>

    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadInstance, UploadRequestOptions } from 'element-plus'
import api from '@/utils/http'

import TableSkeleton from '../components/TableSkeleton.vue'
import { getFriendlyError, promptUpgradeHookReportIfPresent } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getRoleInfo } from '../utils/auth'

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
const marketplaceEmptyText = ref('暂无插件，或无法连接插件市场')
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
  } catch { pluginHealthMap.value = {}; console.warn('加载插件健康数据失败') }
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
  } catch { pluginSecurityReports.value = {}; console.warn('加载插件安全报告失败') }
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
      ElMessage.success('Purchase successful, auto-installing…') // FIXED: 硬编码中文→英文
      await installPlugin(purchaseTarget.value)
    } else if (orderData.payment_url) {
      purchaseDialogVisible.value = false
      ElMessage.info('Please complete payment in the popup window; plugin will auto-install after success') // FIXED: 硬编码中文→英文
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
            ElMessage.success('Payment successful, auto-installing…') // FIXED: 硬编码中文→英文
            if (purchaseTarget.value) {
              await installPlugin(purchaseTarget.value)
            }
          }
        } catch {
          paymentPollRetries++
          if (paymentPollRetries >= 20) {
            clearInterval(paymentPollingTimer!)
            paymentPollingTimer = null
            ElMessage.warning('Payment confirmation timeout, please refresh manually') // FIXED: 硬编码中文→英文
          }
        }
      }, 3000)
    } else {
      purchaseDialogVisible.value = false
      ElMessage.success('Order created, please complete payment then install the plugin') // FIXED: 硬编码中文→英文
      await loadData()
    }
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    purchaseError.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message
  } finally {
    purchaseLoading.value = false
  }
}

const emitPluginUpdated = () => {
  window.dispatchEvent(new Event('plugins-updated'))
}

const refreshSuperuserZipVisibility = () => {
  showSuperuserZipUpload.value = getRoleInfo().isSuperuser
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
      ElMessage.success(`Plugin ${pid} upgraded to v${data.version || ''}`) // FIXED: 硬编码中文→英文
    } else {
      ElMessage.success(pid ? `Plugin ${pid} installed successfully` : 'Plugin installed successfully') // FIXED: 硬编码中文→英文
    }
    emitPluginUpdated()
    await loadData()
    options.onSuccess(data as Record<string, unknown>)
    ossZipUploadRef.value?.clearFiles()
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    const line = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message
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
  marketplaceEmptyText.value = '加载中…'
  try {
    let marketData: PluginRow[] = []
    try {
      const res = await api.get('/api/v1/plugins/marketplace')
      marketData = Array.isArray(res.data) ? res.data : []
    } catch {
      marketplaceEmptyText.value = '插件市场加载失败，请检查网络或稍后重试'
    }
    marketplaceList.value = marketData
    if (marketData.length === 0 && marketplaceEmptyText.value === '加载中…') {
      marketplaceEmptyText.value = '暂无可用插件'
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
      ElMessage.success(data?.version ? `Plugin updated to v${data.version}` : 'Plugin updated to latest version') // FIXED: 硬编码中文→英文
    } else {
      ElMessage.success('Plugin installed successfully, opening plugin runtime page') // FIXED: 硬编码中文→英文
      await router.push(`/plugins/runtime/${row.id}`)
    }
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
      tableHint = `\n\nplugin.json 声明的数据库表将被删除：${tables.join('、')}。`
    }
  } catch {
    console.warn('卸载预览失败，继续卸载流程')
  }
  try {
    await ElMessageBox.confirm(
      `After uninstallation, the plugin's menus and features will be unavailable.${tableHint}\n\nYou can reinstall from the marketplace later. Confirm uninstall?`,
      'Confirm plugin uninstallation',
      { type: 'warning', confirmButtonText: 'Uninstall', cancelButtonText: 'Cancel' } // FIXED: 硬编码中文→英文
    )
  } catch {
    return
  }
  installing.value = true
  try {
    await api.delete(`/api/v1/plugins/${pluginId}`)
    await loadData()
    emitPluginUpdated()
    ElMessage.success('Plugin uninstalled successfully') // FIXED: 硬编码中文→英文
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    ElMessage.error('Failed to load plugin data') // FIXED: 硬编码中文→英文
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