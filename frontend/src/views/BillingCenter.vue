<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="插件购买与品牌配置" description="管理租户订阅、插件下单与白标定制" />
      </template>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <TableCard>
          <template #header><div class="font-medium text-sm">当前订阅</div></template>
          <div class="space-y-2 text-sm text-slate-600 mb-4">
            <div><span class="text-slate-400 w-16 inline-block">租户：</span>{{ subscription.tenant_id }}</div>
            <div><span class="text-slate-400 w-16 inline-block">套餐：</span>{{ subscription.plan_code }}</div>
            <div><span class="text-slate-400 w-16 inline-block">状态：</span>
              <el-tag :type="subscription.status === 'active' ? 'success' : 'info'" size="small">{{ subscription.status }}</el-tag>
            </div>
          </div>
          <el-button type="primary" size="small" @click="fetchData" :loading="loading">刷新状态</el-button>
        </TableCard>

        <TableCard>
          <template #header><div class="font-medium text-sm">套餐列表</div></template>
          <el-table :data="paginatedPlans" size="small" style="width: 100%" :empty-text="'暂无套餐'" v-loading="loading" stripe border>
            <el-table-column prop="code" label="编码" width="120" />
            <el-table-column prop="name" :label="t('common.name')" width="130" />
            <el-table-column prop="price_monthly" label="月费(¥)" width="100" />
            <el-table-column prop="max_devices" label="设备数" width="90" />
            <el-table-column prop="plugin_entitlements" label="插件权限" min-width="180" show-overflow-tooltip />
          </el-table>
          <div class="flex justify-end mt-4" v-if="plans.length > 0">
            <el-pagination
              v-model:current-page="planPage"
              v-model:page-size="planPageSize"
              :total="plans.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
            />
          </div>
        </TableCard>
      </div>

      <TableCard class="mb-4">
        <template #header><div class="font-medium text-sm">插件下单</div></template>
        <el-table :data="paginatedPlugins" size="small" style="width: 100%" :empty-text="'暂无插件'" v-loading="loading" stripe border>
          <el-table-column prop="id" label="插件ID" min-width="160" />
          <el-table-column prop="name" label="插件名" width="140" />
          <el-table-column prop="price_monthly" label="月费(¥)" width="100" />
          <el-table-column label="购买时长(月)" width="140">
            <template #default="{ row }">
              <el-input-number v-model="monthsMap[row.id]" :min="1" :max="36" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="渠道优惠(选填)" width="150">
            <template #default="{ row }">
              <el-input v-model="agencyIdMap[row.id]" size="small" placeholder="代理商ID" class="mb-1" />
              <el-input v-model="discountCodeMap[row.id]" size="small" placeholder="折扣码" />
            </template>
          </el-table-column>
          <el-table-column :label="t('common.action')" width="260" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="createOrder(row)">下单</el-button>
              <el-button
                v-if="isDevMode"
                size="small"
                :disabled="!orderSignatures[row.id]"
                @click="simulateCallback(row)"
              >
                模拟支付回调(开发)
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4" v-if="plugins.length > 0">
          <el-pagination
            v-model:current-page="pluginPage"
            v-model:page-size="pluginPageSize"
            :total="plugins.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
          />
        </div>
      </TableCard>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <TableCard>
          <template #header><div class="font-medium text-sm">订单状态</div></template>
          <el-table :data="paginatedOrders" size="small" style="width: 100%" :empty-text="'暂无订单'" v-loading="loading" stripe border>
            <el-table-column prop="order_no" label="订单号" min-width="220" show-overflow-tooltip />
            <el-table-column prop="plugin_name" label="插件" width="120" />
            <el-table-column prop="amount" label="金额(¥)" width="100" />
            <el-table-column prop="status" :label="t('common.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'paid' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="pay_channel" label="支付通道" width="100" />
            <el-table-column label="支付时间" min-width="180">
              <template #default="{ row }">{{ row.paid_at || '-' }}</template>
            </el-table-column>
          </el-table>
          <div class="flex justify-end mt-4" v-if="orders.length > 0">
            <el-pagination
              v-model:current-page="orderPage"
              v-model:page-size="orderPageSize"
              :total="orders.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
            />
          </div>
        </TableCard>

        <TableCard>
          <template #header><div class="font-medium text-sm">自动发放授权</div></template>
          <el-table :data="paginatedLicenses" size="small" style="width: 100%" :empty-text="'暂无授权记录'" v-loading="loading" stripe border>
            <el-table-column prop="order_no" label="订单号" min-width="220" show-overflow-tooltip />
            <el-table-column prop="plugin_name" label="插件" width="120" />
            <el-table-column label="到期时间" min-width="180">
              <template #default="{ row }">{{ row.expires_at || '-' }}</template>
            </el-table-column>
          </el-table>
          <div class="flex justify-end mt-4" v-if="licenses.length > 0">
            <el-pagination
              v-model:current-page="licensePage"
              v-model:page-size="licensePageSize"
              :total="licenses.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
            />
          </div>
        </TableCard>
      </div>

      <TableCard>
        <template #header><div class="font-medium text-sm">白标配置</div></template>
        <el-form :model="branding" label-width="140px" class="max-w-[720px]" size="small">
          <el-form-item label="产品名">
            <el-input v-model="branding.product_name" />
          </el-form-item>
          <el-form-item label="Logo URL">
            <el-input v-model="branding.logo_url" />
          </el-form-item>
          <el-form-item label="主题色">
            <el-color-picker v-model="branding.primary_color" />
            <el-input v-model="branding.primary_color" class="ml-2 w-32" />
          </el-form-item>
          <el-form-item label="欢迎语">
            <el-input v-model="branding.welcome_text" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveBranding">保存白标配置</el-button>
          </el-form-item>
        </el-form>
      </TableCard>

    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'

import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getFriendlyError } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const isDevMode = import.meta.env.DEV
const { t } = useI18n()  // FIXED: 国际化
const loading = ref(false)
const plans = ref<BillingPlan[]>([])
const planPage = ref(1)
const planPageSize = ref(10)
const paginatedPlans = computed(() => {
  const start = (planPage.value - 1) * planPageSize.value
  const end = start + planPageSize.value
  return plans.value.slice(start, end)
})
watch(plans, () => { planPage.value = 1 })

const subscription = ref<Subscription>({ id: '-', plan_id: '-', status: '-' })

const plugins = ref<BillingPlan[]>([])
const pluginPage = ref(1)
const pluginPageSize = ref(10)
const paginatedPlugins = computed(() => {
  const start = (pluginPage.value - 1) * pluginPageSize.value
  const end = start + pluginPageSize.value
  return plugins.value.slice(start, end)
})
watch(plugins, () => { pluginPage.value = 1 })

const orders = ref<Order[]>([])
const orderPage = ref(1)
const orderPageSize = ref(10)
const paginatedOrders = computed(() => {
  const start = (orderPage.value - 1) * orderPageSize.value
  const end = start + orderPageSize.value
  return orders.value.slice(start, end)
})
watch(orders, () => { orderPage.value = 1 })

const licenses = ref<License[]>([])
const licensePage = ref(1)
const licensePageSize = ref(10)
const paginatedLicenses = computed(() => {
  const start = (licensePage.value - 1) * licensePageSize.value
  const end = start + licensePageSize.value
  return licenses.value.slice(start, end)
})
watch(licenses, () => { licensePage.value = 1 })
const monthsMap = ref<Record<string, number>>({})
const agencyIdMap = ref<Record<string, string>>({})
const discountCodeMap = ref<Record<string, string>>({})
const orderSignatures = ref<Record<string, { order_no: string; signature: string; amount: number }>>({})
const branding = ref({
  product_name: 'PyGBSentry',
  logo_url: '',
  primary_color: '#1f2937',
  welcome_text: 'Welcome to PyGBSentry'
})

const fetchData = async () => {
  loading.value = true
  try {
    const results = await Promise.allSettled([
      api.get('/api/v1/billing/plans'),
      api.get('/api/v1/billing/subscription/me'),
      api.get('/api/v1/billing/branding/me'),
      api.get('/api/v1/billing/plugins'),
      api.get('/api/v1/billing/orders/me'),
      api.get('/api/v1/billing/licenses/me')
    ])
    const planRes = results[0].status === 'fulfilled' ? results[0].value : null
    const subRes = results[1].status === 'fulfilled' ? results[1].value : null
    const brandRes = results[2].status === 'fulfilled' ? results[2].value : null
    const pluginRes = results[3].status === 'fulfilled' ? results[3].value : null
    const orderRes = results[4].status === 'fulfilled' ? results[4].value : null
    const licenseRes = results[5].status === 'fulfilled' ? results[5].value : null
    plans.value = planRes && Array.isArray(planRes.data) ? planRes.data : []
    subscription.value = subRes?.data || { tenant_id: '-', plan_code: '-', status: '-' }
    plugins.value = pluginRes && Array.isArray(pluginRes.data) ? pluginRes.data : []
    orders.value = orderRes && Array.isArray(orderRes.data) ? orderRes.data : []
    licenses.value = licenseRes && Array.isArray(licenseRes.data) ? licenseRes.data : []
    plugins.value.forEach(item => {
      if (!monthsMap.value[item.id]) {
        monthsMap.value[item.id] = 1
      }
      if (agencyIdMap.value[item.id] === undefined) agencyIdMap.value[item.id] = ''
      if (discountCodeMap.value[item.id] === undefined) discountCodeMap.value[item.id] = ''
    })
    branding.value = {
      product_name: brandRes?.data?.product_name ?? '',
      logo_url: brandRes?.data?.logo_url || '',
      primary_color: brandRes?.data?.primary_color || '#1f2937',
      welcome_text: brandRes?.data?.welcome_text || 'Welcome to PyGBSentry'
    }
    const failedCount = results.filter(r => r.status === 'rejected').length
    if (failedCount > 0) {
      ElMessage.warning(`${failedCount}项计费数据加载失败，已显示可用数据`)
    }
  } catch {
    ElMessage.error('加载计费数据失败')
  } finally {
    loading.value = false
  }
}

const saveBranding = async () => {
  try {
    await api.put('/api/v1/billing/branding/me', branding.value)
    ElMessage.success('白标配置已保存')
    localStorage.setItem('tenant_branding_cache', JSON.stringify(branding.value))
  } catch {
    ElMessage.error('保存白标配置失败')
  }
}

const createOrder = async (plugin: Record<string, unknown>) => {
  if (loading.value) return
  try {
    const months = monthsMap.value[plugin.id] || 1
    await ElMessageBox.confirm(
      `确认购买插件「${plugin.name || plugin.id}」${months}个月？`,
      '下单确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  loading.value = true
  try {
    const res = await api.post('/api/v1/billing/orders', {
      plugin_id: plugin.id,
      months: monthsMap.value[plugin.id] || 1,
      pay_channel: 'alipay',
      agency_id: agencyIdMap.value[plugin.id] || undefined,
      discount_code: discountCodeMap.value[plugin.id] || undefined
    })
    orderSignatures.value[plugin.id] = {
      order_no: res.data?.order_no ?? '',
      signature: res.data?.callback_sign_example ?? '',
      amount: res.data?.amount ?? 0
    }
    ElMessage.success(`下单成功：${res.data?.order_no ?? '-'}`)
    await fetchData()
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '下单失败')
  } finally {
    loading.value = false
  }
}

const simulateCallback = async (plugin: Record<string, unknown>) => {
  const current = orderSignatures.value[plugin.id]
  if (!current) {
    ElMessage.warning('请先下单')
    return
  }
  try {
    await api.post('/api/v1/billing/payment/callback', {
      order_no: current.order_no,
      status: 'paid',
      paid_amount: current.amount,
      provider_trade_no: `sim_${current.order_no}_${Date.now()}`,
      signature: current.signature
    })
    ElMessage.success('支付回调成功，授权已发放')
    await fetchData()
  } catch (error: unknown) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '支付回调失败')
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
</style>
