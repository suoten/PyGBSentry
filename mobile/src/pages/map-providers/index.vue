<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  activateMapProvider,
  createMapProvider,
  deleteMapProvider,
  fetchMapProviders,
  updateMapProvider,
  type MapProviderItem
} from "@/api/map";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const items = ref<MapProviderItem[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const editingId = ref("");

const form = ref({
  name: "",
  provider: "tianditu",
  api_key: "",
  vector_tile_url: "",
  center_lng: 116.404,
  center_lat: 39.915,
  zoom_level: 12,
  min_zoom: 1,
  max_zoom: 20
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `地图配置：方案总数=${items.value.length}；默认方案=${items.value.find((x) => x.is_default)?.name || "-"}；编辑模式=${editingId.value ? "编辑" : "新增"}`;
});

const nextStepAdvice = computed(() => {
  return "下一步建议：优先确认默认地图方案可用，再维护不同业务场景的备选方案。";
});

function providerLabel(provider: string) {
  const p = String(provider || "").toLowerCase();
  if (p === "tianditu") return "天地图";
  if (p === "gaode") return "高德";
  if (p === "osm") return "OSM";
  if (p === "vector") return "矢量瓦片";
  return p || "-";
}

function resetForm() {
  editingId.value = "";
  form.value = {
    name: "",
    provider: "tianditu",
    api_key: "",
    vector_tile_url: "",
    center_lng: 116.404,
    center_lat: 39.915,
    zoom_level: 12,
    min_zoom: 1,
    max_zoom: 20
  };
}

function beginEdit(row: MapProviderItem) {
  editingId.value = String(row.id || "");
  form.value = {
    name: String(row.name || ""),
    provider: String(row.provider || "tianditu"),
    api_key: String(row.api_key || ""),
    vector_tile_url: String(row.vector_tile_url || ""),
    center_lng: Number(row.center_lng || 116.404),
    center_lat: Number(row.center_lat || 39.915),
    zoom_level: Number(row.zoom_level || 12),
    min_zoom: Number(row.min_zoom || 1),
    max_zoom: Number(row.max_zoom || 20)
  };
}

async function loadItems() {
  loading.value = true;
  try {
    const res = await fetchMapProviders();
    items.value = Array.isArray(res?.items) ? res.items : [];
    setLoadStatus(`刷新成功：${items.value.length} 个地图方案`);
  } catch (err: any) {
    items.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "地图方案加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveForm() {
  const name = String(form.value.name || "").trim();
  if (!name) {
    uni.showToast({ title: "请输入方案名称", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name,
      provider: String(form.value.provider || "tianditu").trim() || "tianditu",
      api_key: String(form.value.api_key || "").trim(),
      vector_tile_url: String(form.value.vector_tile_url || "").trim(),
      center_lng: Number(form.value.center_lng || 116.404),
      center_lat: Number(form.value.center_lat || 39.915),
      zoom_level: Number(form.value.zoom_level || 12),
      min_zoom: Number(form.value.min_zoom || 1),
      max_zoom: Number(form.value.max_zoom || 20)
    };
    if (editingId.value) {
      await updateMapProvider(editingId.value, payload);
      uni.showToast({ title: "地图方案已更新", icon: "none" });
    } else {
      await createMapProvider(payload);
      uni.showToast({ title: "地图方案已创建", icon: "none" });
    }
    resetForm();
    await loadItems();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function setDefaultRow(row: MapProviderItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await activateMapProvider(id);
    uni.showToast({ title: "默认方案已更新", icon: "none" });
    await loadItems();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `设置失败：${err.message}` : "设置失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function removeRow(row: MapProviderItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  if (row.is_default) {
    uni.showToast({ title: "默认方案不可删除", icon: "none" });
    return;
  }
  uni.showModal({
    title: "确认删除",
    content: `确认删除地图方案「${row.name || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteMapProvider(id);
        uni.showToast({ title: "地图方案已删除", icon: "none" });
        await loadItems();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "地图摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadItems);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">地图配置</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadItems">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ editingId ? "编辑地图方案" : "新增地图方案" }}</text>
      <input v-model="form.name" placeholder="方案名称" />
      <picker mode="selector" :range="['天地图(tianditu)','OSM(osm)','高德(gaode)','矢量瓦片(vector)']" :value="['tianditu','osm','gaode','vector'].indexOf(form.provider)" @change="(e:any)=>{ const i=Number(e?.detail?.value||0); form.provider = ['tianditu','osm','gaode','vector'][i] || 'tianditu'; }">
        <view class="app-subtext">服务商：{{ providerLabel(form.provider) }}（{{ form.provider }}）</view>
      </picker>
      <input v-model="form.api_key" placeholder="API Key（可空）" />
      <input v-if="form.provider === 'vector'" v-model="form.vector_tile_url" placeholder="MVT URL（vector 必填）" />
      <view class="app-row">
        <input v-model="form.center_lng" type="digit" placeholder="中心经度" />
        <input v-model="form.center_lat" type="digit" placeholder="中心纬度" />
      </view>
      <view class="app-row">
        <input v-model="form.zoom_level" type="number" placeholder="缩放级别" />
        <input v-model="form.min_zoom" type="number" placeholder="最小缩放" />
        <input v-model="form.max_zoom" type="number" placeholder="最大缩放" />
      </view>
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveForm">{{ editingId ? "更新方案" : "创建方案" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">方案列表：{{ items.length }} 条</text>
      <view v-if="items.length" class="app-gap-12">
        <view v-for="row in items" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || "-" }}（{{ providerLabel(row.provider) }}）</text>
            <text class="app-subtext">中心：{{ Number(row.center_lng || 0).toFixed(6) }}, {{ Number(row.center_lat || 0).toFixed(6) }}；缩放：{{ row.zoom_level }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.is_default ? '默认方案' : '普通方案'" :type="row.is_default ? 'success' : 'default'" />
            <button size="mini" @click="beginEdit(row)">编辑</button>
            <button size="mini" :loading="actionLoading" :disabled="row.is_default" @click="setDefaultRow(row)">设为默认</button>
            <button size="mini" :loading="actionLoading" :disabled="row.is_default" @click="removeRow(row)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '地图方案加载中...' : '暂无地图方案'" />
    </view>
  </view>
</template>
