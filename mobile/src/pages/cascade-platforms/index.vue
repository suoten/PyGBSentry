<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  createPlatform,
  deletePlatform,
  fetchPlatformCatalogResources,
  fetchPlatformChannelsFlat,
  fetchPlatformDiagnosis,
  fetchPlatforms,
  triggerPlatformPushCatalog,
  triggerPlatformRegister,
  updatePlatform,
  updatePlatformCatalogResources,
  type PlatformItem,
  type PlatformPayload
} from "@/api/platform";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const actionLoading = ref(false);
const list = ref<PlatformItem[]>([]);
const selectedPlatformId = ref("");
const diagnosisData = ref<any>(null);
const catalogOptions = ref<Array<{ id: string; name: string }>>([]);
const catalogSelected = ref<string[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const mode = ref<"create" | "edit">("create");

const form = ref<PlatformPayload>({
  name: "",
  server_gb_id: "",
  server_ip: "",
  server_port: 5060,
  transport: "UDP",
  client_gb_id: "",
  password: "",
  register_interval: 3600,
  keepalive_interval: 60,
  catalog_batch_size: 0,
  catalog_push_delay_seconds: 0,
  enable: true
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const selectedPlatform = computed(() => {
  return list.value.find((x) => x.id === selectedPlatformId.value) || null;
});

const onlineCount = computed(() => list.value.filter((x) => x.is_online).length);

const summaryText = computed(() => {
  return `国标级联：总数=${list.value.length}；在线=${onlineCount.value}；启用=${list.value.filter((x) => x.enable).length}；当前选中=${selectedPlatform.value?.name || "-"}`;
});

const nextStepAdvice = computed(() => {
  if (list.value.length === 0) return "下一步建议：先新增上级平台并完成注册，再执行目录推送与诊断。";
  if (onlineCount.value === 0) return "下一步建议：当前无在线级联，建议优先执行“立即注册”并检查链路。";
  return "下一步建议：优先处理诊断中的 error/warn 项并复测注册保活。";
});

function fillForm(row?: PlatformItem | null) {
  if (!row) {
    mode.value = "create";
    form.value = {
      name: "",
      server_gb_id: "",
      server_ip: "",
      server_port: 5060,
      transport: "UDP",
      client_gb_id: "",
      password: "",
      register_interval: 3600,
      keepalive_interval: 60,
      catalog_batch_size: 0,
      catalog_push_delay_seconds: 0,
      enable: true
    };
    return;
  }
  mode.value = "edit";
  form.value = {
    name: row.name || "",
    server_gb_id: row.server_gb_id || "",
    server_ip: row.server_ip || "",
    server_port: Number(row.server_port || 5060),
    transport: String(row.transport || "UDP").toUpperCase(),
    client_gb_id: row.client_gb_id || "",
    password: "",
    register_interval: Number(row.register_interval || 3600),
    keepalive_interval: Number(row.keepalive_interval || 60),
    catalog_batch_size: Number(row.catalog_batch_size || 0),
    catalog_push_delay_seconds: Number(row.catalog_push_delay_seconds || 0),
    enable: Boolean(row.enable)
  };
}

async function loadData() {
  loading.value = true;
  try {
    const rows = await fetchPlatforms();
    list.value = Array.isArray(rows) ? rows : [];
    if (!selectedPlatformId.value && list.value.length) {
      selectedPlatformId.value = list.value[0].id;
    }
    if (selectedPlatformId.value && !list.value.find((x) => x.id === selectedPlatformId.value)) {
      selectedPlatformId.value = list.value[0]?.id || "";
    }
    setLoadStatus("刷新成功");
  } catch (err: any) {
    list.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "级联平台加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function submitForm() {
  if (!form.value.name || !form.value.server_gb_id || !form.value.server_ip || !form.value.client_gb_id) {
    uni.showToast({ title: "请补全必填字段", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    if (mode.value === "create") {
      const res = await createPlatform(form.value);
      selectedPlatformId.value = res.id;
      uni.showToast({ title: "新增成功", icon: "none" });
    } else if (selectedPlatform.value) {
      await updatePlatform(selectedPlatform.value.id, form.value);
      uni.showToast({ title: "更新成功", icon: "none" });
    }
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function doDelete(platformId: string) {
  uni.showModal({
    title: "确认删除",
    content: "删除后将清理该级联的目录映射，是否继续？",
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deletePlatform(platformId);
        uni.showToast({ title: "删除成功", icon: "none" });
        if (selectedPlatformId.value === platformId) selectedPlatformId.value = "";
        await loadData();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

async function doRegister(platformId: string) {
  actionLoading.value = true;
  try {
    await triggerPlatformRegister(platformId);
    uni.showToast({ title: "已触发注册", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `触发失败：${err.message}` : "触发失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function doPushCatalog(platformId: string) {
  actionLoading.value = true;
  try {
    await triggerPlatformPushCatalog(platformId);
    uni.showToast({ title: "已触发目录推送", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `触发失败：${err.message}` : "触发失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function loadDiagnosis() {
  if (!selectedPlatform.value) return;
  actionLoading.value = true;
  try {
    diagnosisData.value = await fetchPlatformDiagnosis(selectedPlatform.value.id);
    uni.showToast({ title: "诊断已刷新", icon: "none" });
  } catch (err: any) {
    diagnosisData.value = null;
    uni.showToast({ title: err?.message ? `诊断失败：${err.message}` : "诊断失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function toggleCatalog(id: string) {
  if (catalogSelected.value.includes(id)) {
    catalogSelected.value = catalogSelected.value.filter((x) => x !== id);
  } else {
    catalogSelected.value = [...catalogSelected.value, id];
  }
}

async function loadCatalog() {
  if (!selectedPlatform.value) return;
  actionLoading.value = true;
  try {
    const [c0, c1, c2, current] = await Promise.all([
      fetchPlatformChannelsFlat(0, 500),
      fetchPlatformChannelsFlat(1, 500),
      fetchPlatformChannelsFlat(2, 500),
      fetchPlatformCatalogResources(selectedPlatform.value.id)
    ]);
    const all = [...(c0.items || []), ...(c1.items || []), ...(c2.items || [])];
    catalogOptions.value = all.map((x) => ({
      id: x.id,
      name: x.name || x.gb_id || x.id
    }));
    catalogSelected.value = Array.isArray(current.resource_ids) ? current.resource_ids : [];
    uni.showToast({ title: "目录范围已加载", icon: "none" });
  } catch (err: any) {
    catalogOptions.value = [];
    catalogSelected.value = [];
    uni.showToast({ title: err?.message ? `加载失败：${err.message}` : "加载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function saveCatalog() {
  if (!selectedPlatform.value) return;
  actionLoading.value = true;
  try {
    await updatePlatformCatalogResources(selectedPlatform.value.id, catalogSelected.value);
    uni.showToast({ title: "目录范围已保存", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const diagLevel = diagnosisData.value?.level || "-";
  const diagCount = Array.isArray(diagnosisData.value?.diagnostics) ? diagnosisData.value.diagnostics.length : 0;
  const text = [
    summaryText.value,
    `诊断级别=${diagLevel}；诊断项=${diagCount}`,
    `目录映射=${catalogSelected.value.length || 0} 项`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "级联摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">国标级联</view>

    <view class="app-card app-gap-12">
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

    <view class="app-card app-gap-12">
      <text class="app-subtext">平台列表（{{ list.length }}）</text>
      <view v-if="list.length" class="app-gap-12">
        <view v-for="row in list" :key="row.id" class="app-card">
          <text class="app-subtext">{{ row.name }}（{{ row.server_gb_id }}）</text>
          <text class="app-subtext">上级：{{ row.server_ip }}:{{ row.server_port }} / {{ row.transport || "UDP" }}</text>
          <text class="app-subtext">本级：{{ row.client_gb_id }}；在线={{ row.is_online ? "是" : "否" }}；启用={{ row.enable ? "是" : "否" }}</text>
          <view class="app-row">
            <button
              size="mini"
              @click="
                selectedPlatformId = row.id;
                fillForm(row);
              "
            >
              编辑
            </button>
            <button size="mini" :loading="actionLoading" @click="doRegister(row.id)">立即注册</button>
            <button size="mini" :loading="actionLoading" @click="doPushCatalog(row.id)">推送目录</button>
            <button size="mini" :loading="actionLoading" @click="doDelete(row.id)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '级联列表加载中...' : '暂无级联平台'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ mode === "create" ? "新增级联平台" : "编辑级联平台" }}</text>
      <input v-model="form.name" class="app-input" placeholder="名称" />
      <input v-model="form.server_gb_id" class="app-input" placeholder="上级平台国标ID（20位）" />
      <input v-model="form.server_ip" class="app-input" placeholder="上级IP" />
      <input v-model.number="form.server_port" type="number" class="app-input" placeholder="上级端口（默认 5060）" />
      <input v-model="form.transport" class="app-input" placeholder="传输方式（UDP/TCP）" />
      <input v-model="form.client_gb_id" class="app-input" placeholder="本平台国标ID（20位）" />
      <input v-model="form.password" class="app-input" password placeholder="密码（编辑时可留空不修改）" />
      <input v-model.number="form.register_interval" type="number" class="app-input" placeholder="注册间隔（秒）" />
      <input v-model.number="form.keepalive_interval" type="number" class="app-input" placeholder="保活间隔（秒）" />
      <view class="app-row">
        <button
          size="mini"
          @click="
            form.enable = !form.enable;
          "
        >
          {{ form.enable ? "已启用" : "已禁用" }}
        </button>
        <button size="mini" :loading="actionLoading" @click="submitForm">{{ mode === "create" ? "新增" : "保存" }}</button>
        <button
          size="mini"
          @click="
            fillForm(null);
            selectedPlatformId = '';
          "
        >
          重置
        </button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">诊断与目录范围（当前：{{ selectedPlatform?.name || "-" }}）</text>
        <button size="mini" :loading="actionLoading" :disabled="!selectedPlatform" @click="loadDiagnosis">刷新诊断</button>
      </view>
      <view class="app-row">
        <button size="mini" :loading="actionLoading" :disabled="!selectedPlatform" @click="loadCatalog">加载目录范围</button>
        <button size="mini" :loading="actionLoading" :disabled="!selectedPlatform" @click="saveCatalog">保存目录范围</button>
      </view>
      <view v-if="diagnosisData" class="app-gap-12">
        <text class="app-subtext">诊断级别：{{ diagnosisData.level || "-" }}</text>
        <view v-for="(d, idx) in diagnosisData.diagnostics || []" :key="`diag-${idx}`" class="app-row">
          <text class="app-subtext">{{ d.level }} / {{ d.title }} / {{ d.detail }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="actionLoading ? '诊断加载中...' : '暂无诊断数据'" />
      <view v-if="catalogOptions.length" class="app-gap-12">
        <text class="app-subtext">目录范围（已选 {{ catalogSelected.length }}）</text>
        <view v-for="row in catalogOptions.slice(0, 120)" :key="`catalog-${row.id}`" class="app-row">
          <checkbox :checked="catalogSelected.includes(row.id)" @click="toggleCatalog(row.id)" />
          <text class="app-subtext">{{ row.name }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="actionLoading ? '目录加载中...' : '未加载目录候选项'" />
    </view>
  </view>
</template>
