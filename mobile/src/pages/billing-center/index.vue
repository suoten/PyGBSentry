<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  createBillingOrder,
  fetchBillingPlans,
  fetchBillingPlugins,
  fetchMyBranding,
  fetchMyLicenses,
  fetchMyOrders,
  fetchMySubscription,
  saveMyBranding,
  simulateBillingPaymentCallback,
  type BillingLicenseItem,
  type BillingOrderItem,
  type BillingPlanItem,
  type BillingPluginItem
} from "@/api/billing";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const savingBranding = ref(false);
const creatingOrder = ref(false);
const callbackLoading = ref(false);
const plans = ref<BillingPlanItem[]>([]);
const plugins = ref<BillingPluginItem[]>([]);
const orders = ref<BillingOrderItem[]>([]);
const licenses = ref<BillingLicenseItem[]>([]);
const subscription = ref({
  tenant_id: "-",
  plan_code: "-",
  status: "-"
});
const branding = ref({
  product_name: "PyGBSentry",
  logo_url: "",
  primary_color: "#1f2937",
  welcome_text: "Welcome to PyGBSentry"
});
const monthsMap = ref<Record<string, number>>({});
const signatures = ref<Record<string, { order_no: string; signature: string; amount: number }>>({});
const activeTab = ref<"plans" | "plugins" | "orders" | "branding">("plans");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const planPage = ref(1);
const planPageSize = ref(10);
const pluginPage = ref(1);
const pluginPageSize = ref(10);
const orderPage = ref(1);
const orderPageSize = ref(10);
const licensePage = ref(1);
const licensePageSize = ref(10);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const pagedPlans = computed(() => {
  const start = (planPage.value - 1) * planPageSize.value;
  return plans.value.slice(start, start + planPageSize.value);
});
const pagedPlugins = computed(() => {
  const start = (pluginPage.value - 1) * pluginPageSize.value;
  return plugins.value.slice(start, start + pluginPageSize.value);
});
const pagedOrders = computed(() => {
  const start = (orderPage.value - 1) * orderPageSize.value;
  return orders.value.slice(start, start + orderPageSize.value);
});
const pagedLicenses = computed(() => {
  const start = (licensePage.value - 1) * licensePageSize.value;
  return licenses.value.slice(start, start + licensePageSize.value);
});

const summaryText = computed(() => {
  return `计费中心：套餐=${plans.value.length}；插件=${plugins.value.length}；订单=${orders.value.length}；授权=${licenses.value.length}；订阅=${subscription.value.status}`;
});

const nextStepAdvice = computed(() => {
  if (subscription.value.status !== "active") return "下一步建议：先确认订阅有效期与套餐状态，再执行插件下单。";
  if (orders.value.some((x) => x.status !== "paid")) return "下一步建议：优先完成未支付订单回调，确保授权已发放。";
  return "下一步建议：定期校验白标与授权到期时间，提前处理续费。";
});

async function loadData() {
  loading.value = true;
  try {
    const [plansRes, subRes, brandingRes, pluginsRes, ordersRes, licensesRes] = await Promise.allSettled([
      fetchBillingPlans(),
      fetchMySubscription(),
      fetchMyBranding(),
      fetchBillingPlugins(),
      fetchMyOrders(),
      fetchMyLicenses()
    ]);
    plans.value = plansRes.status === "fulfilled" && Array.isArray(plansRes.value) ? plansRes.value : [];
    subscription.value = subRes.status === "fulfilled" && subRes.value ? (subRes.value as any) : { tenant_id: "-", plan_code: "-", status: "-" };
    branding.value =
      brandingRes.status === "fulfilled" && brandingRes.value
        ? {
            product_name: String((brandingRes.value as any).product_name || "PyGBSentry"),
            logo_url: String((brandingRes.value as any).logo_url || ""),
            primary_color: String((brandingRes.value as any).primary_color || "#1f2937"),
            welcome_text: String((brandingRes.value as any).welcome_text || "Welcome to PyGBSentry")
          }
        : {
            product_name: "PyGBSentry",
            logo_url: "",
            primary_color: "#1f2937",
            welcome_text: "Welcome to PyGBSentry"
          };
    plugins.value = pluginsRes.status === "fulfilled" && Array.isArray(pluginsRes.value) ? pluginsRes.value : [];
    orders.value = ordersRes.status === "fulfilled" && Array.isArray(ordersRes.value) ? ordersRes.value : [];
    licenses.value = licensesRes.status === "fulfilled" && Array.isArray(licensesRes.value) ? licensesRes.value : [];
    plugins.value.forEach((x) => {
      if (!monthsMap.value[x.id]) monthsMap.value[x.id] = 1;
    });
    const failedCount = [plansRes, subRes, brandingRes, pluginsRes, ordersRes, licensesRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "计费中心加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveBrandingAction() {
  savingBranding.value = true;
  try {
    await saveMyBranding(branding.value);
    uni.showToast({ title: "白标配置已保存", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    savingBranding.value = false;
  }
}

async function createOrderAction(row: BillingPluginItem) {
  creatingOrder.value = true;
  try {
    const res = await createBillingOrder({
      plugin_id: row.id,
      months: Number(monthsMap.value[row.id] || 1),
      pay_channel: "alipay"
    });
    signatures.value[row.id] = {
      order_no: res.order_no,
      signature: res.callback_sign_example,
      amount: Number(res.amount || 0)
    };
    uni.showToast({ title: "下单成功", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `下单失败：${err.message}` : "下单失败", icon: "none" });
  } finally {
    creatingOrder.value = false;
  }
}

async function simulateCallbackAction(row: BillingPluginItem) {
  const sign = signatures.value[row.id];
  if (!sign) {
    uni.showToast({ title: "请先下单", icon: "none" });
    return;
  }
  callbackLoading.value = true;
  try {
    await simulateBillingPaymentCallback({
      order_no: sign.order_no,
      status: "paid",
      paid_amount: sign.amount,
      provider_trade_no: `sim_${sign.order_no}_${Date.now()}`,
      signature: sign.signature
    });
    uni.showToast({ title: "支付回调成功", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `回调失败：${err.message}` : "回调失败", icon: "none" });
  } finally {
    callbackLoading.value = false;
  }
}

function copySummary() {
  const text = [
    summaryText.value,
    `租户=${subscription.value.tenant_id || "-"}；套餐=${subscription.value.plan_code || "-"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "计费摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">计费中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadData">刷新</button>
      </view>
      <view class="app-row">
        <text class="app-subtext">租户：{{ subscription.tenant_id }}</text>
        <text class="app-subtext">套餐：{{ subscription.plan_code }}</text>
        <AppStatusTag :text="subscription.status || '-'" :type="subscription.status === 'active' ? 'success' : 'warning'" />
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <button size="mini" :type="activeTab === 'plans' ? 'primary' : 'default'" @click="activeTab = 'plans'">套餐与插件</button>
        <button size="mini" :type="activeTab === 'orders' ? 'primary' : 'default'" @click="activeTab = 'orders'">订单与授权</button>
        <button size="mini" :type="activeTab === 'branding' ? 'primary' : 'default'" @click="activeTab = 'branding'">白标配置</button>
      </view>
    </view>

    <view v-if="activeTab === 'plans'" class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">套餐列表（{{ plans.length }}）</text>
        <view v-if="pagedPlans.length" class="app-gap-12">
          <view v-for="row in pagedPlans" :key="row.id" class="app-row">
            <text class="app-subtext">{{ row.code }} / {{ row.name }} / ¥{{ row.price_monthly }} / 设备{{ row.max_devices }}</text>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '套餐加载中...' : '暂无套餐'" />
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">插件下单（{{ plugins.length }}）</text>
        <view v-if="pagedPlugins.length" class="app-gap-12">
          <view v-for="row in pagedPlugins" :key="row.id" class="app-card">
            <text class="app-subtext">{{ row.id }} / {{ row.name }} / ¥{{ row.price_monthly }} / 月</text>
            <input v-model.number="monthsMap[row.id]" type="number" class="app-input" placeholder="购买时长（月，1-36）" />
            <view class="app-row">
              <button size="mini" :loading="creatingOrder" @click="createOrderAction(row)">下单</button>
              <button size="mini" :loading="callbackLoading" :disabled="!signatures[row.id]" @click="simulateCallbackAction(row)">模拟支付回调</button>
            </view>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '插件加载中...' : '暂无插件'" />
      </view>
    </view>

    <view v-else-if="activeTab === 'orders'" class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">订单列表（{{ orders.length }}）</text>
        <view v-if="pagedOrders.length" class="app-gap-12">
          <view v-for="row in pagedOrders" :key="row.order_no" class="app-card">
            <text class="app-subtext">{{ row.order_no }}</text>
            <text class="app-subtext">插件：{{ row.plugin_name || row.plugin_id }}；金额：¥{{ row.amount }}</text>
            <view class="app-row">
              <text class="app-subtext">状态：{{ row.status || "-" }}</text>
              <AppStatusTag :text="row.status || '-'" :type="row.status === 'paid' ? 'success' : 'warning'" />
            </view>
            <text class="app-subtext">支付通道：{{ row.pay_channel || "-" }}；支付时间：{{ row.paid_at || "-" }}</text>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '订单加载中...' : '暂无订单'" />
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">授权记录（{{ licenses.length }}）</text>
        <view v-if="pagedLicenses.length" class="app-gap-12">
          <view v-for="row in pagedLicenses" :key="row.order_no" class="app-row">
            <text class="app-subtext">{{ row.order_no }} / {{ row.plugin_name || row.plugin_id }} / 到期：{{ row.expires_at || "-" }}</text>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '授权加载中...' : '暂无授权'" />
      </view>
    </view>

    <view v-else class="app-card app-gap-12">
      <text class="app-subtext">白标配置</text>
      <input v-model="branding.product_name" class="app-input" placeholder="产品名" />
      <input v-model="branding.logo_url" class="app-input" placeholder="Logo URL" />
      <input v-model="branding.primary_color" class="app-input" placeholder="主题色（如 #1f2937）" />
      <input v-model="branding.welcome_text" class="app-input" placeholder="欢迎语" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="savingBranding" @click="saveBrandingAction">保存白标配置</button>
      </view>
    </view>
  </view>
</template>
