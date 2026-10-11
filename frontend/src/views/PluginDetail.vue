<template>
  <div class="app-page space-y-4">
    <PageContainer class="max-w-3xl mx-auto">
      <template #header>
        <PageHeader :title="t('plugin.pluginDetail')" :description="t('plugin.viewPluginInfo')">  <!-- FIXED: 硬编码中文→t() -->
          <template #actions>
            <el-button @click="$router.push('/plugins')">{{ t('plugin.backToCenter') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
          </template>
        </PageHeader>
      </template>

    <TableCard v-if="plugin">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-xl font-semibold">{{ plugin.name }}</span>
            <el-tag v-if="plugin.is_official" type="primary" size="small">{{ t('plugin.official') }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
            <el-tag size="small" :type="plugin.type === 'paid' ? 'warning' : 'success'">
              {{ plugin.type === 'paid' ? t('plugin.paid') : t('plugin.free') }}  <!-- FIXED: 硬编码中文→t() -->
            </el-tag>
            <el-tag v-if="plugin.status === 'deprecated'" type="danger" size="small">{{ t('plugin.deprecated') }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
            <el-tag v-if="isInstalled(pluginId) && !isPurchased(pluginId) && plugin.type === 'paid'" type="warning" size="small" class="ml-1">
              {{ t('plugin.trialExpired') }}  <!-- FIXED: 硬编码中文→t() -->
            </el-tag>
          </div>
        </div>
      </template>
      <div class="space-y-3" style="color: var(--el-text-color-regular)">
        <p class="text-sm" style="color: var(--el-text-color-secondary)">
          {{ t('common.version') }} {{ plugin.version }}
          <template v-if="plugin.type === 'paid' && detailPriceTiers.length > 0">
            ·
            <el-tooltip
              v-if="detailPriceTiers.length > 1"
              placement="top"
              :content="detailPriceTiers.map((tier) => tier.label).join(' / ')"
            >
              <span class="text-orange-500 font-medium" style="cursor: help">{{ lowestDetailPriceLabel }}</span>
            </el-tooltip>
            <span v-else class="text-orange-500 font-medium">{{ lowestDetailPriceLabel }}</span>
          </template>
          <span v-else-if="plugin.type !== 'paid'"> · {{ t('pluginDetail.freeToUse') }}</span>
          <el-tag v-if="hasPluginTrial(plugin)" size="small" type="success" class="ml-2">
            {{ t('plugin.trialDays', { days: plugin.trial_days }) }}
          </el-tag>
        </p>
        <p v-if="installedVersion" class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
          {{ t('pluginDetail.installedVersion', { version: installedVersion }) }}
        </p>
        <el-alert
          v-if="plugin.status === 'deprecated'"
          type="warning"
          show-icon
          :closable="false"
          :title="plugin.deprecated_message || t('pluginDetail.deprecatedFallback')"
        />
        <p>{{ plugin.description }}</p>
        <p v-if="plugin.detail" class="whitespace-pre-wrap text-sm pt-3 mt-3" style="border-top: 1px solid var(--el-border-color-lighter)">
          {{ plugin.detail }}
        </p>
        <a v-if="plugin.doc_url" :href="plugin.doc_url" target="_blank" rel="noopener" class="el-link el-link--primary">{{ t('pluginDetail.viewDocs') }}</a>
      </div>
      <div class="mt-6 flex gap-3">
        <el-button
          v-if="plugin.type === 'paid' && !isPurchased(pluginId)"
          type="warning"
          :disabled="installingId !== ''"
          @click="onClickBuy"
        >
          {{ t('plugin.buy') }}  <!-- FIXED: 硬编码中文→t() -->
        </el-button>
        <el-button
          v-else
          type="primary"
          :loading="installingId === pluginId"
          :disabled="installingId !== ''"
          @click="onClickInstall"
        >
          {{ isInstalled(pluginId) ? t('plugin.reinstall') : t('plugin.install') }}  <!-- FIXED: 硬编码中文→t() -->
        </el-button>
        <el-button v-if="isInstalled(pluginId)" type="danger" plain :disabled="installingId !== ''" @click="uninstallPlugin(pluginId)">
          {{ t('common.cancel') }}  <!-- FIXED: 硬编码中文→t() -->
        </el-button>
      </div>
      <!-- 健康状态 -->
      <div v-if="isServerEdition && pluginHealth" class="mt-3 flex items-center gap-2 text-sm">
        <span style="color: var(--el-text-color-secondary)">{{ t('plugin.healthStatus') }}：</span>  <!-- FIXED: 硬编码中文→t() -->
        <el-tag v-if="pluginHealth.healthy" size="small" type="success">{{ t('common.normal') }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
        <el-tag v-else size="small" type="danger">{{ t('plugin.abnormalErrors', { count: pluginHealth.error_count }) }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
      </div>
    </TableCard>

    <!-- 安全扫描报告 -->
    <TableCard v-if="isServerEdition && securityReport">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="font-medium">{{ t('pluginDetail.securityScanReport') }}</span>
          <el-tag :type="securityReport.risk_level === 'high' ? 'danger' : securityReport.risk_level === 'medium' ? 'warning' : 'success'" size="small">
            {{ securityReport.risk_level === 'high' ? t('plugin.riskHigh') : securityReport.risk_level === 'medium' ? t('plugin.riskMedium') : t('plugin.riskLow') }}
          </el-tag>
        </div>
      </template>
      <div class="space-y-2 text-sm" style="color: var(--el-text-color-regular)">
        <p v-if="securityReport.scanned_at" style="color: var(--el-text-color-secondary)">{{ t('pluginDetail.scanTime', { time: securityReport.scanned_at }) }}</p>
        <div v-if="securityReport.findings && securityReport.findings.length > 0">
          <p class="font-medium mb-2">{{ t('pluginDetail.findingsCount', { count: securityReport.findings.length }) }}</p>
          <div v-for="(finding, idx) in securityReport.findings" :key="idx" class="border rounded p-2 mb-2" style="border-color: var(--el-border-color-lighter)">
            <div class="flex items-center gap-2">
              <el-tag size="small" :type="finding.severity === 'high' ? 'danger' : finding.severity === 'medium' ? 'warning' : 'info'">{{ finding.severity }}</el-tag>
              <span class="font-medium">{{ finding.rule_id || finding.title || '-' }}</span>
            </div>
            <p v-if="finding.description" class="mt-1" style="color: var(--el-text-color-secondary)">{{ finding.description }}</p>
          </div>
        </div>
        <p v-else style="color: var(--el-color-success)">{{ t('pluginDetail.noSecurityIssues') }}</p>
      </div>
    </TableCard>

    <TableCard v-if="plugin && showSuperuserZipUpload">
      <template #header>
        <div class="font-medium">{{ t('plugin.localUploadTitle') }}</div>
      </template>
      <p class="text-xs mb-3" style="color: var(--el-text-color-secondary)" v-html="sanitizeHtml(t('pluginDetail.localUploadDesc'))"></p>
      <el-upload
        ref="detailZipUploadRef"
        :limit="1"
        accept=".zip"
        :http-request="handleDetailZipUpload"
      >
        <el-button type="primary" :loading="detailZipUploading" :disabled="detailZipUploading">{{ t('plugin.selectZipAndInstall') }}</el-button>
      </el-upload>
    </TableCard>

    <el-empty v-if="!plugin" :description="t('pluginDetail.notFound')" />
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadInstance, UploadRequestOptions } from 'element-plus'
import api from '@/utils/http'
import { logger } from '@/utils/logger'
import { hasPluginTrial, formatPluginPriceCents, lowestPluginSubscriptionTier, pluginPerpetualTier, resolvePluginPriceTiers } from '../utils/pluginMarketplaceStatus'
import { useOfficialAccount } from '../composables/useOfficialAccount'

import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getVerifiedRoleInfo } from '../utils/auth' // FIX C-3: 改用后端验证角色
import { sanitizeHtml } from '@/utils/sanitize'

const route = useRoute()
const { t } = useI18n()  // FIXED: 国际化
const router = useRouter()
const pluginId = computed(() => (route.params.pluginId as string) || '')

// 官网账户（双版账户打通）：与插件中心共享登录态；商城插件的购买/安装需先登录
const { isMarketplacePlugin, refreshOfficialAccount, ensureOfficialAccount, guideOfficialAccountOnError } =
  useOfficialAccount()

type PluginItem = {
  id: string
  name: string
  version: string
  type: string
  description?: string
  price_monthly?: number
  price_quarterly?: number
  price_yearly?: number
  price_perpetual?: number
  trial_days?: number
  package_url?: string
  detail?: string
  doc_url?: string
  status?: string
  deprecated_message?: string
  is_official?: boolean
}

const marketplaceList = ref<PluginItem[]>([])
const installedList = ref<PluginItem[]>([])
const purchasedIds = ref<string[]>([])
const shopUrl = ref('')
const installingId = ref('')
const showSuperuserZipUpload = ref(false)

// 插件健康状态
const pluginHealth = ref<{ healthy: boolean; error_count: number; last_error: string } | null>(null)
const securityReport = ref<any>(null)

const isServerEdition = (import.meta.env.VITE_APP_EDITION || 'oss') === 'server'

const loadPluginHealth = async () => {
  if (!isServerEdition) return
  try {
    const res = await api.get('/api/v1/plugins/runtime/health-status', { params: { plugin_id: pluginId.value } })
    if (Array.isArray(res.data?.items) && res.data.items.length > 0) {
        const item = res.data.items[0]
      if (!item) { pluginHealth.value = null; return }
      pluginHealth.value = { healthy: item.healthy, error_count: item.error_count || 0, last_error: item.last_error || '' }
    }
  } catch { pluginHealth.value = null; logger.warn('加载插件健康数据失败') }
}

const loadSecurityReport = async () => {
  if (!isServerEdition) return
  try {
    const res = await api.get('/api/v1/plugins/runtime/security-report', { params: { plugin_id: pluginId.value } })
    securityReport.value = res.data
  } catch { securityReport.value = null; logger.warn('加载安全报告失败') }
}
const detailZipUploadRef = ref<UploadInstance>()
const detailZipUploading = ref(false)

const plugin = computed(() => marketplaceList.value.find(p => p.id === pluginId.value))
const installedVersion = computed(() => {
  const row = installedList.value.find((p) => p.id === pluginId.value)
  return row?.version?.trim() || ''
})
const isInstalled = (id: string) => installedList.value.some(p => p.id === id)
const isPurchased = (id: string) => purchasedIds.value.includes(id)

// 价格/试用展示（分 → ¥ 文案；四档 月/季/年/终身，最低订阅档 + 终身价，悬浮全部档位）
const detailPriceTiers = computed(() => (plugin.value ? resolvePluginPriceTiers(plugin.value) : []))
const lowestDetailPriceLabel = computed(() => {
  if (!plugin.value) return ''
  const sub = lowestPluginSubscriptionTier(plugin.value)
  if (!sub) return ''
  const base = t('plugin.priceFromPrefix') + sub.label + t('plugin.priceFromSuffix')
  const perpetual = pluginPerpetualTier(plugin.value)
  return perpetual ? `${base} · ${t('plugin.lifetimeLabel')} ${formatPluginPriceCents(perpetual.cents)}` : base
})

// 官网账户门控：商城插件（有 package_url 或 type=paid）购买/安装前需登录官网账户
const onClickBuy = () => {
  const row = plugin.value
  if (!row) return
  void ensureOfficialAccount(isMarketplacePlugin(row) ? row : null, async () => openShop())
}

const onClickInstall = () => {
  const row = plugin.value
  if (!row) return
  void ensureOfficialAccount(isMarketplacePlugin(row) ? row : null, async () => installPlugin(row))
}

const openShop = () => {
  const baseUrl = shopUrl.value || '/'
  const returnUrl = encodeURIComponent(window.location.href)
  window.open(`${baseUrl}${baseUrl.endsWith('/') ? '' : '/'}market/plugin/${pluginId.value}?return=${returnUrl}`, '_blank', 'noopener,noreferrer')
}

type UploadErrorCallbackArg = Parameters<NonNullable<UploadRequestOptions['onError']>>[0]

const handleDetailZipUpload = async (options: UploadRequestOptions) => {
  detailZipUploading.value = true
  const form = new FormData()
  form.append('file', options.file)
  try {
    const res = await api.post('/api/v1/plugins/upload', form, { skipFriendlyMessage: true })
    const data = res.data as { plugin_id?: string; operation?: string; version?: string }
    const pid = String(data.plugin_id || '').trim()
    const op = String(data.operation || 'install')
    if (op === 'upgrade') {
      ElMessage.success(t('plugin.upgradeSuccess', { pid, version: data.version || '' }))  // FIXED: 硬编码中文→t()
    } else {
      ElMessage.success(pid ? t('plugin.installSuccess', { pid }) : t('plugin.installSuccess', { pid: '' }))  // FIXED: 硬编码中文→t()
    }
    window.dispatchEvent(new Event('plugins-updated'))
    await loadData()
    options.onSuccess(data as Record<string, unknown>)
    detailZipUploadRef.value?.clearFiles()
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    options.onError?.(new Error(friendly.message) as UploadErrorCallbackArg)
  } finally {
    detailZipUploading.value = false
  }
}

const loadData = async () => {
  const [marketRes, installedRes, shopRes, purchasedRes] = await Promise.all([
    api.get('/api/v1/plugins/marketplace').catch(() => ({ data: [] })),
    api.get('/api/v1/plugins/installed').catch(() => ({ data: [] })),
    api.get('/api/v1/plugins/marketplace-shop-url').catch(() => ({ data: { url: '' } })),
    api.get('/api/v1/plugins/purchased').catch(() => ({ data: { plugin_ids: [] } }))
  ])
  marketplaceList.value = Array.isArray(marketRes.data) ? marketRes.data : []
  installedList.value = Array.isArray(installedRes.data) ? installedRes.data : []
  shopUrl.value = (shopRes?.data?.url || '').trim() || ''
  purchasedIds.value = Array.isArray(purchasedRes?.data?.plugin_ids) ? purchasedRes.data.plugin_ids : []
}

const installPlugin = async (row: PluginItem) => {
  installingId.value = row.id
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
    await loadData()
    window.dispatchEvent(new Event('plugins-updated'))
    ElMessage.success(t('plugin.installAndOpen'))  // FIXED: 硬编码中文→t()
    await router.push(`/plugins/runtime/${row.id}`)
  } catch (error: unknown) {
    // 官网账户 token 缺失/失效：弹官网登录弹窗，登录成功后自动继续安装
    if (guideOfficialAccountOnError(error, () => installPlugin(row))) return
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    installingId.value = ''
  }
}

const uninstallPlugin = async (id: string) => {
  // FIXED: [2026-10-11] 后端卸载要求 confirm=true + confirm_phrase（ack_phrase）——预览取回并携带，
  // 预览失败时从 400 错误文案兜底提取短语重试一次。
  let ackPhrase = ''
  try {
    const prev = await api.get(`/api/v1/plugins/${id}/uninstall-preview`)
    ackPhrase = String(prev.data?.ack_phrase || '').trim()
  } catch {
    // 预览失败继续，走兜底提取
  }
  try {
    await ElMessageBox.confirm(
      t('plugin.uninstallConfirmMsg'),  // FIXED: 硬编码中文→t()
      t('plugin.uninstallConfirmTitle'),  // FIXED: 硬编码中文→t()
      { type: 'warning', confirmButtonText: t('common.confirmUninstall'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }
  installingId.value = id
  const doDelete = (phrase?: string) =>
    api.delete(`/api/v1/plugins/${id}`, { params: phrase ? { confirm: true, confirm_phrase: phrase } : { confirm: true } })
  const finishSuccess = async () => {
    await loadData()
    window.dispatchEvent(new Event('plugins-updated'))
    ElMessage.success(t('plugin.uninstallSuccess'))
    await router.push('/plugins')
  }
  try {
    await doDelete(ackPhrase || undefined)
    await finishSuccess()
  } catch (error: unknown) {
    const detail = String((error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '')
    const m = /confirmation phrase:\s*([^)]+)/.exec(detail)
    if (!ackPhrase && m && m[1]) {
      try {
        await doDelete(m[1].trim())
        await finishSuccess()
      } catch (retryError: unknown) {
        const friendly = getFriendlyError(retryError)
        ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
      }
    } else {
      const friendly = getFriendlyError(error)
      ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    }
  } finally {
    installingId.value = ''
  }
}

// FIX C-3: 改用后端验证的权威角色信息
const refreshSuperuserZipVisibility = async () => {
  const info = await getVerifiedRoleInfo()
  showSuperuserZipUpload.value = !!info?.isSuperuser
}

onMounted(async () => {
  refreshSuperuserZipVisibility()
  void refreshOfficialAccount()
  await loadData()
  loadPluginHealth()
  loadSecurityReport()
  window.addEventListener('plugin-purchases-updated', loadData)
})

onActivated(() => {
  refreshSuperuserZipVisibility()
})

onUnmounted(() => {
  window.removeEventListener('plugin-purchases-updated', loadData)
})
</script>

<style scoped>
</style>