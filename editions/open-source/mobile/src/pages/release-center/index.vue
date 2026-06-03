<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchCurrentDraft } from "@/api/config";
import { fetchDraftDiff, publishDraft, rollbackRevision, type DiffItem } from "@/api/release";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const saving = ref(false);
const diffRows = ref<DiffItem[]>([]);
const fromRevision = ref(0);
const loadMessage = ref("未刷新");
const loadAt = ref("");

const publishForm = ref({
  draftId: "",
  publishNote: ""
});
const rollbackForm = ref({
  targetRevision: 1,
  reason: ""
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `发布中心：草稿=${publishForm.value.draftId || "-"}；差异=${diffRows.value.length}；fromRevision=${fromRevision.value}`;
});

const nextStepAdvice = computed(() => {
  if (!publishForm.value.draftId) return "下一步建议：先读取草稿并执行差异预览。";
  if (!diffRows.value.length) return "下一步建议：先执行差异预览，再决定发布或回滚。";
  return "下一步建议：确认高风险差异后再执行发布，必要时预先设定回滚版本。";
});

async function loadCurrentDraft() {
  loading.value = true;
  try {
    const draft = await fetchCurrentDraft();
    publishForm.value.draftId = String(draft.draft_id || "");
    setLoadStatus("草稿读取成功");
  } catch (err: any) {
    setLoadStatus(err?.message ? `草稿读取失败：${err.message}` : "草稿读取失败");
    uni.showToast({ title: "草稿读取失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function loadDiff() {
  const draftId = String(publishForm.value.draftId || "").trim();
  if (!draftId) {
    uni.showToast({ title: "请先填写草稿ID", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const diff = await fetchDraftDiff(draftId);
    diffRows.value = Array.isArray(diff.changes) ? diff.changes : [];
    fromRevision.value = Number(diff.from_revision || 0);
    setLoadStatus(`差异读取成功：${diffRows.value.length} 条`);
  } catch (err: any) {
    diffRows.value = [];
    setLoadStatus(err?.message ? `差异读取失败：${err.message}` : "差异读取失败");
    uni.showToast({ title: "差异读取失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function publishNow() {
  const draftId = String(publishForm.value.draftId || "").trim();
  if (!draftId) {
    uni.showToast({ title: "请先填写草稿ID", icon: "none" });
    return;
  }
  uni.showModal({
    title: "确认发布",
    content: `确认发布草稿 ${draftId} 吗？`,
    success: async (res) => {
      if (!res.confirm) return;
      saving.value = true;
      try {
        const result = await publishDraft(draftId, String(publishForm.value.publishNote || "").trim() || undefined);
        rollbackForm.value.targetRevision = Number(result.revision || rollbackForm.value.targetRevision);
        uni.showToast({ title: `发布成功 revision=${result.revision}`, icon: "none" });
        await loadDiff();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `发布失败：${err.message}` : "发布失败", icon: "none" });
      } finally {
        saving.value = false;
      }
    }
  });
}

async function rollbackNow() {
  const targetRevision = Number(rollbackForm.value.targetRevision || 0);
  if (!targetRevision || targetRevision < 1) {
    uni.showToast({ title: "请输入有效回滚版本", icon: "none" });
    return;
  }
  uni.showModal({
    title: "确认回滚",
    content: `确认回滚到 revision=${targetRevision} 吗？`,
    success: async (res) => {
      if (!res.confirm) return;
      saving.value = true;
      try {
        await rollbackRevision(targetRevision, String(rollbackForm.value.reason || "").trim() || undefined);
        uni.showToast({ title: `回滚成功 revision=${targetRevision}`, icon: "none" });
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `回滚失败：${err.message}` : "回滚失败", icon: "none" });
      } finally {
        saving.value = false;
      }
    }
  });
}

function copySummary() {
  const highRisk = diffRows.value.filter((x) => String(x.risk_level || "").toLowerCase() === "high").length;
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `高风险差异=${highRisk}`,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "发布摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadCurrentDraft);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">发布中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadCurrentDraft">读取草稿</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">发布操作</text>
      <input v-model="publishForm.draftId" placeholder="草稿ID" />
      <input v-model="publishForm.publishNote" placeholder="发布说明（可空）" />
      <view class="app-row">
        <button size="mini" :loading="saving" @click="loadDiff">执行差异预览</button>
        <button size="mini" type="primary" :loading="saving" @click="publishNow">执行确认发布</button>
      </view>
      <text class="app-subtext">提示：发布前请先查看高风险差异，并确认插件配置变更是否需要重启。</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">差异预览：{{ diffRows.length }} 条（from revision {{ fromRevision }}）</text>
      <view v-if="diffRows.length" class="app-gap-12">
        <view v-for="(row, idx) in diffRows.slice(0, 50)" :key="`${row.module}-${row.path}-${idx}`" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.module }} / {{ row.path }}</text>
            <text class="app-subtext">前：{{ String(row.before ?? "-") }}</text>
            <text class="app-subtext">后：{{ String(row.after ?? "-") }}</text>
          </view>
          <text class="app-subtext">风险：{{ row.risk_level || "-" }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="saving ? '差异加载中...' : '暂无差异'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">回滚中心</text>
      <input v-model="rollbackForm.targetRevision" type="number" placeholder="目标版本 revision" />
      <input v-model="rollbackForm.reason" placeholder="回滚原因（可空）" />
      <button size="mini" :loading="saving" @click="rollbackNow">执行版本回滚</button>
    </view>
  </view>
</template>
