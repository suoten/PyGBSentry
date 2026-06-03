<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  createAssetMaintenance,
  deleteAssetMaintenance,
  fetchAssetLedger,
  fetchAssetMaintenances,
  type AssetLedgerItem,
  type AssetMaintenanceItem
} from "@/api/asset";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const activeTab = ref<"ledger" | "maintenance">("ledger");
const keyword = ref("");
const filterAssetId = ref("");
const ledger = ref<AssetLedgerItem[]>([]);
const maintenances = ref<AssetMaintenanceItem[]>([]);
const ledgerPage = ref(1);
const ledgerPageSize = ref(20);
const maintenancePage = ref(1);
const maintenancePageSize = ref(20);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const actionLoading = ref(false);

const showAddDialog = ref(false);
const formAssetId = ref("");
const formMaintenanceType = ref<"routine" | "repair" | "upgrade" | "replace">("routine");
const formMaintenanceDate = ref(new Date().toISOString().slice(0, 19));
const formNote = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const paginatedLedger = computed(() => {
  const start = (ledgerPage.value - 1) * ledgerPageSize.value;
  return ledger.value.slice(start, start + ledgerPageSize.value);
});

const paginatedMaintenances = computed(() => {
  const start = (maintenancePage.value - 1) * maintenancePageSize.value;
  return maintenances.value.slice(start, start + maintenancePageSize.value);
});

const summaryText = computed(() => {
  return `资产管理：台账=${ledger.value.length}；维保=${maintenances.value.length}；在线设备=${ledger.value.filter((x) => Number(x.status) === 1).length}`;
});

const nextStepAdvice = computed(() => {
  if (ledger.value.length <= 0) return "下一步建议：先同步设备资产台账，再补充维保记录。";
  if (maintenances.value.length <= 0) return "下一步建议：先为关键设备补充维保记录，形成可追溯台账。";
  return "下一步建议：按维保类型与设备状态做复盘，提前安排下一轮巡检。";
});

function getMaintenanceTypeLabel(value: string) {
  if (value === "routine") return "例行";
  if (value === "repair") return "维修";
  if (value === "upgrade") return "升级";
  if (value === "replace") return "更换";
  return value || "-";
}

async function loadData() {
  loading.value = true;
  try {
    const [ledgerRes, maintenanceRes] = await Promise.allSettled([
      fetchAssetLedger(keyword.value || "", 1000),
      fetchAssetMaintenances(filterAssetId.value || "", 1000)
    ]);
    ledger.value = ledgerRes.status === "fulfilled" && Array.isArray(ledgerRes.value) ? ledgerRes.value : [];
    maintenances.value = maintenanceRes.status === "fulfilled" && Array.isArray(maintenanceRes.value) ? maintenanceRes.value : [];
    ledgerPage.value = 1;
    maintenancePage.value = 1;
    const failedCount = [ledgerRes, maintenanceRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    ledger.value = [];
    maintenances.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "资产数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openAddMaintenance(assetId = "") {
  formAssetId.value = assetId || filterAssetId.value || "";
  formMaintenanceType.value = "routine";
  formMaintenanceDate.value = new Date().toISOString().slice(0, 19);
  formNote.value = "";
  showAddDialog.value = true;
}

async function submitMaintenance() {
  if (!formAssetId.value) {
    uni.showToast({ title: "请选择设备", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    await createAssetMaintenance({
      asset_id: formAssetId.value,
      maintenance_type: formMaintenanceType.value,
      maintenance_date: formMaintenanceDate.value,
      note: formNote.value || undefined
    });
    showAddDialog.value = false;
    activeTab.value = "maintenance";
    filterAssetId.value = formAssetId.value;
    uni.showToast({ title: "维保记录已新增", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `新增失败：${err.message}` : "新增失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function removeMaintenance(row: AssetMaintenanceItem) {
  uni.showModal({
    title: "确认删除",
    content: "确认删除该维保记录？",
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteAssetMaintenance(row.id);
        uni.showToast({ title: "维保记录已删除", icon: "none" });
        await loadData();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    `筛选=keyword:${keyword.value || "-"},asset_id:${filterAssetId.value || "all"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "资产摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">资产管理</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <button size="mini" :type="activeTab === 'ledger' ? 'primary' : 'default'" @click="activeTab = 'ledger'">设备台账</button>
        <button size="mini" :type="activeTab === 'maintenance' ? 'primary' : 'default'" @click="activeTab = 'maintenance'">维保记录</button>
      </view>
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadData">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view v-if="activeTab === 'ledger'" class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">台账筛选</text>
        <input v-model="keyword" class="app-input" placeholder="搜索设备（名称/国标ID）" />
        <view class="app-row">
          <button size="mini" :loading="loading" @click="loadData">查询</button>
          <button
            size="mini"
            @click="
              keyword = '';
              loadData();
            "
          >
            重置
          </button>
        </view>
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">设备台账（{{ ledger.length }}）</text>
        <view v-if="paginatedLedger.length" class="app-gap-12">
          <view v-for="row in paginatedLedger" :key="row.id" class="app-card">
            <text class="app-subtext">{{ row.name || "-" }}（{{ row.gb_id }}）</text>
            <text class="app-subtext">厂商：{{ row.manufacturer || "-" }}；型号：{{ row.model || "-" }}</text>
            <text class="app-subtext">状态：{{ Number(row.status) === 1 ? "在线" : "离线" }}；维保次数：{{ row.maintenance_count ?? 0 }}</text>
            <view class="app-row">
              <button size="mini" @click="openAddMaintenance(row.id)">添加维保</button>
            </view>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '台账加载中...' : '暂无台账记录'" />
        <view class="app-row">
          <button size="mini" :disabled="ledgerPage <= 1" @click="ledgerPage -= 1">上一页</button>
          <text class="app-subtext">第 {{ ledgerPage }} 页</text>
          <button
            size="mini"
            :disabled="ledgerPage * ledgerPageSize >= ledger.length"
            @click="ledgerPage += 1"
          >
            下一页
          </button>
        </view>
      </view>
    </view>

    <view v-else class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">维保筛选</text>
        <picker
          mode="selector"
          :range="['全部设备', ...ledger.map((x) => `${x.name || x.gb_id}`)]"
          :value="Math.max(0, ledger.findIndex((x) => x.id === filterAssetId) + 1)"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              filterAssetId = i <= 0 ? '' : String(ledger[i - 1]?.id || '');
              loadData();
            }
          "
        >
          <view class="app-subtext">设备筛选：{{ filterAssetId || "全部" }}</view>
        </picker>
        <view class="app-row">
          <button size="mini" @click="openAddMaintenance(filterAssetId)">新增维保</button>
        </view>
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">维保记录（{{ maintenances.length }}）</text>
        <view v-if="paginatedMaintenances.length" class="app-gap-12">
          <view v-for="row in paginatedMaintenances" :key="row.id" class="app-card">
            <text class="app-subtext">日期：{{ row.maintenance_date || "-" }}</text>
            <text class="app-subtext">类型：{{ getMaintenanceTypeLabel(row.maintenance_type) }}；操作人：{{ row.operator || "-" }}</text>
            <text class="app-subtext">备注：{{ row.note || "-" }}</text>
            <view class="app-row">
              <button size="mini" :loading="actionLoading" @click="removeMaintenance(row)">删除</button>
            </view>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '维保加载中...' : '暂无维保记录'" />
        <view class="app-row">
          <button size="mini" :disabled="maintenancePage <= 1" @click="maintenancePage -= 1">上一页</button>
          <text class="app-subtext">第 {{ maintenancePage }} 页</text>
          <button
            size="mini"
            :disabled="maintenancePage * maintenancePageSize >= maintenances.length"
            @click="maintenancePage += 1"
          >
            下一页
          </button>
        </view>
      </view>
    </view>

    <view v-if="showAddDialog" class="app-card app-gap-12">
      <text class="app-subtext">新增维保记录</text>
      <picker
        mode="selector"
        :range="ledger.map((x) => `${x.name || x.gb_id}`)"
        :value="Math.max(0, ledger.findIndex((x) => x.id === formAssetId))"
        @change="
          (e:any) => {
            const i = Number(e?.detail?.value || 0);
            formAssetId = String(ledger[i]?.id || '');
          }
        "
      >
        <view class="app-subtext">设备：{{ formAssetId || "请选择" }}</view>
      </picker>
      <picker
        mode="selector"
        :range="['例行', '维修', '升级', '更换']"
        :value="formMaintenanceType === 'routine' ? 0 : formMaintenanceType === 'repair' ? 1 : formMaintenanceType === 'upgrade' ? 2 : 3"
        @change="
          (e:any) => {
            const i = Number(e?.detail?.value || 0);
            formMaintenanceType = i === 1 ? 'repair' : i === 2 ? 'upgrade' : i === 3 ? 'replace' : 'routine';
          }
        "
      >
        <view class="app-subtext">类型：{{ getMaintenanceTypeLabel(formMaintenanceType) }}</view>
      </picker>
      <input v-model="formMaintenanceDate" class="app-input" placeholder="日期（ISO）" />
      <textarea v-model="formNote" class="app-input" placeholder="备注（可空）" />
      <view class="app-row">
        <button size="mini" @click="showAddDialog = false">取消</button>
        <button size="mini" type="primary" :loading="actionLoading" @click="submitMaintenance">确定</button>
      </view>
    </view>
  </view>
</template>
