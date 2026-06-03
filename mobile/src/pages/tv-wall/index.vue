<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchTvWallDeviceTree, fetchTvWallSources, previewTvWallSource, stopTvWallStream, type TvWallChannelNode } from "@/api/tv-wall";
import { playStream, pickPreferredPlayUrl, type StreamPlayData } from "@/api/stream";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppStreamPlayer from "@/components/AppStreamPlayer.vue";

type ScreenState = {
  name: string;
  nodeType: "channel" | "source_stream";
  deviceId?: string;
  channelId?: string;
  sourceId?: string;
  app?: string;
  stream?: string;
  url?: string;
  mode?: string;
  loading?: boolean;
  error?: string;
};

const loading = ref(false);
const actionLoading = ref(false);
const placement = ref<"business" | "region">("business");
const layout = ref<"4" | "9" | "16">("9");
const activeScreen = ref(0);
const keyword = ref("");
const channels = ref<TvWallChannelNode[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const screens = ref<Array<ScreenState | null>>(new Array(16).fill(null));

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const layoutCount = computed(() => Number(layout.value));
const filteredChannels = computed(() => {
  return channels.value.filter((x) => {
    if (!keyword.value) return true;
    const text = `${x.label} ${x.id} ${x.deviceId || ""}`.toLowerCase();
    return text.includes(keyword.value.toLowerCase());
  });
});

const playingCount = computed(() => {
  return screens.value.slice(0, layoutCount.value).filter((x) => !!x?.url).length;
});

const summaryText = computed(() => {
  return `电视墙：布局=${layout.value}；目录通道=${filteredChannels.value.length}；已上墙=${playingCount.value}/${layoutCount.value}；当前格=${activeScreen.value + 1}`;
});

const nextStepAdvice = computed(() => {
  if (playingCount.value <= 0) return "下一步建议：先从目录双击通道上墙，再进行轮巡抽检。";
  if (playingCount.value < layoutCount.value) return "下一步建议：补齐关键窗口画面，提升值班可见性。";
  return "下一步建议：保持关键画面驻留，异常时优先切到主关注窗口。";
});

function flattenTreeChannels(nodes: any[], out: TvWallChannelNode[] = []) {
  for (const n of nodes || []) {
    const nodeType = String(n?.nodeType || "").toLowerCase();
    if (nodeType === "channel") {
      const channelId = String(n?.id || "");
      const typeCode = channelId ? channelId.substring(10, 13) : "";
      const playable = ["131", "132", "111", "112", "118"].includes(typeCode);
      if (playable && Number(n?.status || 0) === 1) {
        out.push({
          id: channelId,
          label: String(n?.label || channelId),
          nodeType: "channel",
          status: Number(n?.status || 0),
          deviceId: String(n?.deviceId || "")
        });
      }
    }
    if (Array.isArray(n?.children) && n.children.length > 0) {
      flattenTreeChannels(n.children, out);
    }
  }
  return out;
}

async function loadData() {
  loading.value = true;
  try {
    const [treeRes, sourceRes] = await Promise.allSettled([fetchTvWallDeviceTree(placement.value), fetchTvWallSources()]);
    const treeChannels = treeRes.status === "fulfilled" ? flattenTreeChannels(Array.isArray(treeRes.value) ? treeRes.value : []) : [];
    const sourceChannels =
      sourceRes.status === "fulfilled" && Array.isArray(sourceRes.value)
        ? sourceRes.value
            .filter((x) => x.enabled !== false)
            .map((x) => ({
              id: String(x.id || ""),
              label: `${x.name || x.id}（${x.protocol || "-" }）`,
              nodeType: "source_stream" as const,
              status: x.enabled === false ? 0 : 1,
              sourceId: String(x.id || ""),
              protocol: x.protocol
            }))
        : [];
    channels.value = [...sourceChannels, ...treeChannels];
    const failedCount = [treeRes, sourceRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `目录接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    channels.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "电视墙目录加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function pickTargetScreen() {
  const current = activeScreen.value;
  if (!screens.value[current]?.url && !screens.value[current]?.loading) return current;
  for (let i = 0; i < layoutCount.value; i += 1) {
    if (!screens.value[i]?.url && !screens.value[i]?.loading) return i;
  }
  return current;
}

async function stopScreen(index: number) {
  const row = screens.value[index];
  screens.value[index] = null;
  if (!row) return;
  if (row.app && row.stream) {
    try {
      await stopTvWallStream(row.app, row.stream, row.channelId || "");
    } catch {
      // noop
    }
  }
}

async function stopAll() {
  actionLoading.value = true;
  try {
    const all = screens.value.slice(0, layoutCount.value);
    screens.value = new Array(16).fill(null);
    await Promise.all(
      all.map(async (x) => {
        if (!x?.app || !x?.stream) return;
        try {
          await stopTvWallStream(x.app, x.stream, x.channelId || "");
        } catch {
          // noop
        }
      })
    );
    uni.showToast({ title: "已停止全部画面", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function playNode(node: TvWallChannelNode) {
  const target = pickTargetScreen();
  activeScreen.value = target;
  const base: ScreenState = {
    name: node.label,
    nodeType: node.nodeType,
    deviceId: node.deviceId,
    channelId: node.id,
    sourceId: node.sourceId,
    loading: true
  };
  screens.value[target] = base;
  try {
    let playData: StreamPlayData = {};
    if (node.nodeType === "source_stream" && node.sourceId) {
      const sourceRes = await previewTvWallSource(node.sourceId);
      playData = {
        app: sourceRes.app,
        stream: sourceRes.stream,
        webrtc: sourceRes.webrtc,
        flv: sourceRes.wss_flv || sourceRes.ws_flv || sourceRes.flv,
        hls: sourceRes.wss_hls || sourceRes.ws_hls || sourceRes.hls
      };
    } else {
      playData = await playStream(String(node.deviceId || ""), node.id);
    }
    const picked = pickPreferredPlayUrl(playData);
    if (!picked.url) {
      screens.value[target] = { ...base, loading: false, error: "未获取到播放地址" };
      return;
    }
    screens.value[target] = {
      ...base,
      loading: false,
      app: playData.app || "live",
      stream: playData.stream || node.id,
      url: picked.url,
      mode: picked.mode
    };
  } catch (err: any) {
    screens.value[target] = { ...base, loading: false, error: err?.message || "上墙失败" };
  }
}

function openPreview(row: ScreenState | null) {
  if (!row?.deviceId || !row.channelId || row.nodeType !== "channel") {
    uni.showToast({ title: "仅设备通道支持跳转预览页", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/preview/index?deviceId=${encodeURIComponent(row.deviceId)}&channelId=${encodeURIComponent(row.channelId)}`
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`,
    `状态时间=${loadAt.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "电视墙摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">电视墙</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <picker mode="selector" :range="['业务分组', '行政区划']" :value="placement === 'business' ? 0 : 1" @change="(e:any) => { placement = Number(e?.detail?.value || 0) === 1 ? 'region' : 'business'; loadData(); }">
          <view class="app-subtext">目录模式：{{ placement === "business" ? "业务分组" : "行政区划" }}</view>
        </picker>
        <picker mode="selector" :range="['2x2', '3x3', '4x4']" :value="layout === '4' ? 0 : layout === '9' ? 1 : 2" @change="(e:any) => { const i=Number(e?.detail?.value||1); layout = i===0 ? '4' : i===2 ? '16' : '9'; }">
          <view class="app-subtext">布局：{{ layout }}</view>
        </picker>
      </view>
      <input v-model="keyword" class="app-input" placeholder="搜索通道/接入源" />
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadData">刷新目录</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" :loading="actionLoading" @click="stopAll">全部停止</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">目录通道（{{ filteredChannels.length }}）</text>
      <view v-if="filteredChannels.length" class="app-gap-12">
        <view v-for="row in filteredChannels.slice(0, 160)" :key="`${row.nodeType}-${row.id}`" class="app-row">
          <view style="flex: 1">
            <text class="app-subtext">{{ row.label }}</text>
            <text class="app-subtext">类型：{{ row.nodeType }}；状态：{{ Number(row.status || 0) === 1 ? "在线/启用" : "离线/停用" }}</text>
          </view>
          <button size="mini" :loading="actionLoading" @click="playNode(row)">上墙</button>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '目录加载中...' : '暂无可上墙通道'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">电视墙窗口（{{ layout }}）</text>
      <view style="display:grid;grid-template-columns:1fr 1fr;gap:12rpx;" class="app-gap-12">
        <view
          v-for="i in layoutCount"
          :key="`screen-${i}`"
          :style="`border:1rpx solid ${activeScreen === i - 1 ? '#2563EB' : '#E2E8F0'};border-radius:12rpx;padding:12rpx;`"
          @click="activeScreen = i - 1"
        >
          <view class="app-row">
            <text>窗口 {{ i }}</text>
            <AppStatusTag
              :text="screens[i - 1]?.loading ? '加载中' : screens[i - 1]?.url ? (screens[i - 1]?.mode || 'raw').toUpperCase() : screens[i - 1]?.error ? '异常' : '空闲'"
              :type="screens[i - 1]?.loading ? 'warning' : screens[i - 1]?.url ? 'success' : screens[i - 1]?.error ? 'danger' : 'info'"
            />
          </view>
          <view v-if="screens[i - 1]?.url" class="app-gap-12">
            <AppStreamPlayer :url="screens[i - 1]!.url!" :mode="screens[i - 1]!.mode || 'raw'" :height-rpx="220" />
            <text class="app-subtext">{{ screens[i - 1]?.name || "-" }}</text>
          </view>
          <text v-else class="app-subtext">{{ screens[i - 1]?.loading ? "正在拉流..." : screens[i - 1]?.error || "空闲窗口" }}</text>
          <view class="app-row" style="margin-top: 8rpx">
            <button size="mini" :disabled="!screens[i - 1]" @click="stopScreen(i - 1)">停止</button>
            <button size="mini" :disabled="!screens[i - 1]" @click="openPreview(screens[i - 1])">预览联动</button>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>
