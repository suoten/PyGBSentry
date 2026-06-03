<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchActiveStreams,
  fetchDbCheck,
  fetchDbCompatReport,
  fetchDiagnoseReport,
  fetchOpsStatus,
  runStreamDiagnose,
  shutdownService,
  type StreamDiagItem
} from "@/api/ops";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const actionLoading = ref(false);
const status = ref<any>(null);
const dbCheck = ref<any>(null);
const dbCompat = ref<any>(null);
const diagnose = ref<any>(null);
const streams = ref<any[]>([]);
const streamDiagItems = ref<StreamDiagItem[]>([]);
const selectedStream = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `运维中心：CPU=${status.value?.cpu ?? 0}%；内存=${status.value?.memory_percent ?? 0}%；ZLM=${status.value?.zlm_status || "-"}；流数=${status.value?.zlm_streams ?? 0}`;
});

const nextStepAdvice = computed(() => {
  if (String(status.value?.zlm_status || "").toLowerCase() !== "online") return "下一步建议：先恢复 ZLM 在线状态，再执行流媒体诊断。";
  if (dbCheck.value?.connected === false) return "下一步建议：先修复数据库连接，再继续配置与发布流程。";
  return "下一步建议：定期执行一键诊断并抽样检查活跃流链路。";
});

async function loadData() {
  loading.value = true;
  try {
    const [statusRes, dbRes, compatRes, diagRes, streamsRes] = await Promise.allSettled([
      fetchOpsStatus(),
      fetchDbCheck(),
      fetchDbCompatReport(),
      fetchDiagnoseReport(),
      fetchActiveStreams()
    ]);
    status.value = statusRes.status === "fulfilled" ? statusRes.value : null;
    dbCheck.value = dbRes.status === "fulfilled" ? dbRes.value : null;
    dbCompat.value = compatRes.status === "fulfilled" ? compatRes.value : null;
    diagnose.value = diagRes.status === "fulfilled" ? diagRes.value : null;
    streams.value = streamsRes.status === "fulfilled" && Array.isArray(streamsRes.value.streams) ? streamsRes.value.streams : [];
    const failedCount = [statusRes, dbRes, compatRes, diagRes, streamsRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "运维数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function doStreamDiagnose() {
  actionLoading.value = true;
  try {
    const res = await runStreamDiagnose({
      channel_id: selectedStream.value || undefined
    });
    streamDiagItems.value = Array.isArray(res.items) ? res.items : [];
    uni.showToast({ title: `诊断完成(${streamDiagItems.value.length}项)`, icon: "none" });
  } catch (err: any) {
    streamDiagItems.value = [];
    uni.showToast({ title: err?.message ? `诊断失败：${err.message}` : "诊断失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function doShutdown() {
  uni.showModal({
    title: "确认关闭服务",
    content: "确认关闭服务进程吗？该操作会导致当前站点不可用。",
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await shutdownService();
        uni.showToast({ title: "关闭请求已提交", icon: "none" });
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `提交失败：${err.message}` : "提交失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `DB=${dbCheck.value?.connected ? "ok" : "error"}`,
    `诊断总结=${diagnose.value?.summary || "-"}`,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "运维摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">运维中心</view>

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
        <button size="mini" :loading="actionLoading" @click="doShutdown">关闭服务</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">系统状态</text>
      <text class="app-subtext">CPU：{{ status?.cpu ?? 0 }}%；内存：{{ status?.memory_percent ?? 0 }}%</text>
      <text class="app-subtext">ZLM：{{ status?.zlm_status || "-" }}；目标：{{ status?.zlm_target || "-" }}；来源：{{ status?.zlm_select_reason_label || status?.zlm_select_reason || "-" }}</text>
      <text class="app-subtext">错误：{{ status?.zlm_error || "-" }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">数据库检查</text>
      <text class="app-subtext">连接：{{ dbCheck?.connected ? "正常" : "异常" }}；数据库：{{ dbCheck?.database || "-" }}</text>
      <text class="app-subtext">兼容性：{{ dbCompat?.summary || "-" }}；提示：{{ dbCompat?.vendor_hint || "-" }}</text>
      <text class="app-subtext">检查项：{{ (dbCompat?.checks || []).length }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">一键诊断</text>
      <text class="app-subtext">总结：{{ diagnose?.summary || "-" }}；时间：{{ diagnose?.generated_at || "-" }}</text>
      <view v-if="(diagnose?.items || []).length" class="app-gap-12">
        <view v-for="(row, idx) in diagnose.items.slice(0, 20)" :key="`diag-${idx}`" class="app-row">
          <text class="app-subtext">{{ row.ok ? "✓" : "✗" }} {{ row.name }}：{{ row.text }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '诊断加载中...' : '暂无诊断项'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">流媒体诊断</text>
      <picker
        mode="selector"
        :range="['全部活跃流', ...streams.map((x)=>`${x.name || x.stream}`)]"
        :value="Math.max(0, streams.findIndex((x)=>x.stream===selectedStream)+1)"
        @change="(e:any)=>{ const i=Number(e?.detail?.value||0); selectedStream = i<=0 ? '' : (streams[i-1]?.stream || ''); }"
      >
        <view class="app-subtext">目标流：{{ selectedStream || "全部活跃流" }}</view>
      </picker>
      <button size="mini" :loading="actionLoading" @click="doStreamDiagnose">执行流媒体诊断</button>
      <view v-if="streamDiagItems.length" class="app-gap-12">
        <view v-for="(row, idx) in streamDiagItems" :key="`sdiag-${idx}`" class="app-row">
          <text class="app-subtext">{{ row.ok ? "✓" : "✗" }} {{ row.step }} / {{ row.title }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="actionLoading ? '诊断执行中...' : '暂无诊断结果'" />
    </view>
  </view>
</template>
