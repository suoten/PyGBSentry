<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { batchPlaceChannels, fetchChannelsFlat, fetchDeviceTree, type ChannelFlatItem, type DeviceTreeNode } from "@/api/device";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const actionLoading = ref(false);
const treeNodes = ref<DeviceTreeNode[]>([]);
const channels = ref<ChannelFlatItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const online = ref("");
const mode = ref<"added" | "unadded">("added");
const selectedTargetId = ref("");
const selectedIds = ref<string[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function flattenTree(nodes: DeviceTreeNode[], out: Array<{ id: string; label: string }> = [], depth = 0) {
  for (const row of nodes || []) {
    const id = String(row.id || "").trim();
    const label = `${"  ".repeat(depth)}${row.label || id}`;
    if (id) out.push({ id, label });
    if (Array.isArray(row.children) && row.children.length) flattenTree(row.children, out, depth + 1);
  }
  return out;
}

const treeOptions = computed(() => flattenTree(treeNodes.value).filter((x) => x.id && x.id !== "region:root"));
const selectedTargetLabel = computed(() => treeOptions.value.find((x) => x.id === selectedTargetId.value)?.label || selectedTargetId.value || "未选择");
const selectedIdSet = computed(() => new Set(selectedIds.value));

function parseCivilCode(id: string) {
  const raw = String(id || "").trim();
  if (!raw) return "";
  const body = raw.startsWith("region:") ? raw.slice("region:".length) : raw;
  const digits = body.replace(/\D/g, "");
  return digits.slice(0, 8);
}

const targetCivilCode = computed(() => parseCivilCode(selectedTargetId.value));

const summaryText = computed(() => {
  return `行政区划通道：模式=${mode.value === "added" ? "已挂载" : "未挂载"}；目标=${selectedTargetId.value || "无"}；区划码=${targetCivilCode.value || "-"}；总数=${total.value}；本页=${channels.value.length}；已选=${selectedIds.value.length}`;
});

const nextStepAdvice = computed(() => {
  if (mode.value === "added" && !selectedTargetId.value) return "下一步建议：先选择行政区节点，再查看已挂载通道。";
  if (selectedIds.value.length <= 0) return "下一步建议：勾选通道后可批量挂载或移除。";
  return mode.value === "added" ? "下一步建议：可批量移除选中通道，治理区划挂载偏差。" : "下一步建议：可批量挂载选中通道到当前行政区节点。";
});

function toggleSelect(id: string) {
  const value = String(id || "").trim();
  if (!value) return;
  if (selectedIdSet.value.has(value)) selectedIds.value = selectedIds.value.filter((x) => x !== value);
  else selectedIds.value = [...selectedIds.value, value];
}

async function loadTree() {
  try {
    const rows = await fetchDeviceTree("region");
    treeNodes.value = Array.isArray(rows) ? rows : [];
  } catch {
    treeNodes.value = [];
  }
}

async function loadChannels() {
  if (mode.value === "added" && !selectedTargetId.value) {
    channels.value = [];
    total.value = 0;
    return;
  }
  loading.value = true;
  try {
    const statusNum = online.value === "" ? undefined : online.value === "true" ? 1 : 0;
    const res = await fetchChannelsFlat({
      placement: "region",
      keyword: keyword.value || undefined,
      status: statusNum,
      parent_gb_id: mode.value === "added" ? selectedTargetId.value || undefined : undefined,
      added_status: mode.value === "unadded" ? "unadded" : undefined,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    });
    channels.value = Array.isArray(res?.items) ? res.items : [];
    total.value = Number(res?.total || 0);
    selectedIds.value = [];
    setLoadStatus(`刷新成功：${channels.value.length} 条`);
  } catch (err: any) {
    channels.value = [];
    total.value = 0;
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "通道加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function onTargetChange(index: number) {
  selectedTargetId.value = String(treeOptions.value[index]?.id || "");
  page.value = 1;
  await loadChannels();
}

async function onModeChange(index: number) {
  mode.value = index === 1 ? "unadded" : "added";
  page.value = 1;
  await loadChannels();
}

async function onOnlineChange(index: number) {
  online.value = ["", "true", "false"][index] || "";
  page.value = 1;
  await loadChannels();
}

async function mountSelected() {
  if (!selectedTargetId.value) {
    uni.showToast({ title: "请先选择行政区节点", icon: "none" });
    return;
  }
  if (!selectedIds.value.length) {
    uni.showToast({ title: "请先勾选通道", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await batchPlaceChannels({
      resource_ids: selectedIds.value,
      placement: "region",
      target_id: selectedTargetId.value,
      civil_code: targetCivilCode.value || undefined
    });
    uni.showToast({ title: `已挂载 ${res.updated}/${res.requested}`, icon: "none" });
    await loadChannels();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `挂载失败：${err.message}` : "挂载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function unmountSelected() {
  if (!selectedIds.value.length) {
    uni.showToast({ title: "请先勾选通道", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await batchPlaceChannels({
      resource_ids: selectedIds.value,
      placement: "region",
      target_id: "",
      civil_code: ""
    });
    uni.showToast({ title: `已移除 ${res.updated}/${res.requested}`, icon: "none" });
    await loadChannels();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `移除失败：${err.message}` : "移除失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await loadChannels();
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
  await loadChannels();
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "行政区划摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function initPage() {
  await loadTree();
  await loadChannels();
}

onShow(initPage);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">行政区划</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadChannels">刷新</button>
      </view>
      <picker mode="selector" :range="['已挂载', '未挂载']" :value="mode === 'added' ? 0 : 1" @change="(e:any)=>onModeChange(Number(e?.detail?.value || 0))">
        <view class="app-subtext">查看模式：{{ mode === "added" ? "已挂载" : "未挂载" }}</view>
      </picker>
      <picker mode="selector" :range="['全部状态', '在线', '离线']" :value="online === '' ? 0 : online === 'true' ? 1 : 2" @change="(e:any)=>onOnlineChange(Number(e?.detail?.value || 0))">
        <view class="app-subtext">在线筛选：{{ online === "" ? "全部" : online === "true" ? "在线" : "离线" }}</view>
      </picker>
      <picker mode="selector" :range="treeOptions.map((x)=>x.label)" :value="Math.max(0, treeOptions.findIndex((x)=>x.id===selectedTargetId))" @change="(e:any)=>onTargetChange(Number(e?.detail?.value || 0))">
        <view class="app-subtext">行政区节点：{{ selectedTargetLabel }}</view>
      </picker>
      <input v-model="keyword" placeholder="关键字（名称/编号）" />
      <view class="app-row">
        <button size="mini" :loading="loading" @click="loadChannels">查询</button>
        <button size="mini" :loading="actionLoading" @click="mountSelected">挂载选中</button>
        <button size="mini" :loading="actionLoading" @click="unmountSelected">移除选中</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">通道列表：{{ total }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page>=Math.max(1, Math.ceil(total / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="channels.length" class="app-gap-12">
        <view v-for="row in channels" :key="row.id" class="app-row">
          <view style="flex:1">
            <label class="app-subtext">
              <checkbox :checked="selectedIdSet.has(String(row.id || ''))" @click="toggleSelect(String(row.id || ''))" />
              选择
            </label>
            <text class="app-subtext">{{ row.name || row.gb_id || row.id }}</text>
            <text class="app-subtext">通道编号：{{ row.gb_id || "-" }}</text>
            <text class="app-subtext">设备：{{ row.device_name || row.device_id || "-" }}</text>
            <text class="app-subtext">行政父节点：{{ row.region_parent_gb_id || "-" }}</text>
            <text class="app-subtext">区划码：{{ row.civil_code || "-" }}</text>
          </view>
          <AppStatusTag :text="row.online ? '在线' : '离线'" :type="row.online ? 'success' : 'info'" />
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '通道加载中...' : '暂无通道数据'" />
    </view>
  </view>
</template>
