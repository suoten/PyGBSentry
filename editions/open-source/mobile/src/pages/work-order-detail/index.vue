<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { type WorkOrderStatus, updateWorkOrderStatus } from "@/api/workOrder";
import AppStatusTag from "@/components/AppStatusTag.vue";

let openerEventChannel: { emit: (event: string, data?: unknown) => void } | null = null;
const loading = ref(false);
const moveStatusMessage = ref("");
const moveStatusAt = ref("");
const detailLoadStatusMessage = ref("未加载详情");
const detailLoadStatusAt = ref("");
const item = ref({
  id: "",
  title: "",
  status: "open" as WorkOrderStatus,
  priority: "medium",
  assignee: "未指派",
  alarmId: "",
  createdAt: "",
  description: ""
});

function setMoveStatus(message: string) {
  moveStatusMessage.value = message;
  moveStatusAt.value = new Date().toISOString();
}

function setDetailLoadStatus(message: string) {
  detailLoadStatusMessage.value = message;
  detailLoadStatusAt.value = new Date().toISOString();
}

function statusTag(status: WorkOrderStatus) {
  if (status === "closed") return { text: "已关闭", type: "info" as const };
  if (status === "resolved") return { text: "已解决", type: "success" as const };
  if (status === "in_progress") return { text: "处理中", type: "warning" as const };
  return { text: "待处理", type: "danger" as const };
}

const nextActions = computed(() => {
  const s = item.value.status;
  if (s === "open") return ["in_progress", "resolved", "closed"] as WorkOrderStatus[];
  if (s === "in_progress") return ["resolved", "closed"] as WorkOrderStatus[];
  if (s === "resolved") return ["in_progress", "closed"] as WorkOrderStatus[];
  return [] as WorkOrderStatus[];
});

const workOrderHandoverSummary = computed(() => {
  return [
    "工单交接摘要",
    `工单ID：${item.value.id || "-"}`,
    `状态：${statusTag(item.value.status).text}`,
    `优先级：${item.value.priority || "-"}`,
    `处置人：${item.value.assignee || "-"}`,
    `关联告警：${item.value.alarmId || "-"}`
  ].join("；");
});

const workOrderNextStepAdvice = computed(() => {
  if (item.value.status === "open") return "下一步建议：先受理并转为处理中，补充处置记录。";
  if (item.value.status === "in_progress") return "下一步建议：确认修复结果，满足条件后转为已解决。";
  if (item.value.status === "resolved") return "下一步建议：观察回归情况，无复发后可关闭工单。";
  return "下一步建议：工单已关闭，建议归档处置复盘结论。";
});

const workOrderFlowRiskLevel = computed(() => {
  if (item.value.status === "open" && String(item.value.priority || "").toLowerCase() === "high") return "风险等级：高";
  if (item.value.status === "open") return "风险等级：中";
  if (item.value.status === "in_progress") return "风险等级：中";
  if (item.value.status === "resolved") return "风险等级：低";
  return "风险等级：低";
});

const workOrderFlowRiskSummary = computed(() => {
  return [
    "工单流转风险摘要",
    `当前状态：${statusTag(item.value.status).text}`,
    `优先级：${item.value.priority || "-"}`,
    `可流转动作：${nextActions.value.join("/") || "无"}`,
    workOrderFlowRiskLevel.value
  ].join("；");
});

const workOrderFlowRiskAdvice = computed(() => {
  if (item.value.status === "open" && String(item.value.priority || "").toLowerCase() === "high") {
    return "下一步建议：高优工单应立即受理并升级跟进频率。";
  }
  if (item.value.status === "open") return "下一步建议：尽快转入处理中，避免工单长时间滞留。";
  if (item.value.status === "in_progress") return "下一步建议：补齐处理证据后转为已解决。";
  if (item.value.status === "resolved") return "下一步建议：完成回归观察后及时关闭。";
  return "下一步建议：保持关闭状态并归档复盘信息。";
});

const workOrderElapsedHours = computed(() => {
  const raw = String(item.value.createdAt || "").trim();
  if (!raw) return 0;
  const ms = new Date(raw).getTime();
  if (Number.isNaN(ms)) return 0;
  const diff = Date.now() - ms;
  if (diff <= 0) return 0;
  return Number((diff / (1000 * 60 * 60)).toFixed(2));
});

const workOrderTimelinessSummary = computed(() => {
  const overdueTag = workOrderElapsedHours.value >= 24 && item.value.status !== "closed" ? "是" : "否";
  return [
    "工单流转时效摘要",
    `当前状态：${statusTag(item.value.status).text}`,
    `创建后时长=${workOrderElapsedHours.value}h`,
    `可流转动作=${nextActions.value.join("/") || "无"}`,
    `超24h未闭环=${overdueTag}`
  ].join("；");
});

const workOrderTimelinessAdvice = computed(() => {
  if (item.value.status === "closed") return "下一步建议：已闭环，建议归档并同步复盘结论。";
  if (workOrderElapsedHours.value >= 24) return "下一步建议：优先推进当前工单流转，避免跨班继续滞留。";
  if (item.value.status === "open") return "下一步建议：尽快接单转处理中，建立处置轨迹。";
  if (item.value.status === "in_progress") return "下一步建议：补齐证据并尽快转已解决。";
  return "下一步建议：完成回归观察后关闭工单，形成闭环。";
});

const workOrderAssigneePushSummary = computed(() => {
  const assignee = String(item.value.assignee || "").trim() || "未指派";
  const isUnassigned = assignee === "未指派";
  const highPriority = String(item.value.priority || "").toLowerCase() === "high";
  const pushLevel = isUnassigned && highPriority ? "高" : isUnassigned ? "中" : highPriority ? "中" : "低";
  return [
    "责任人推进摘要",
    `责任人=${assignee}`,
    `当前状态=${statusTag(item.value.status).text}`,
    `优先级=${item.value.priority || "-"}`,
    `推进优先级=${pushLevel}`
  ].join("；");
});

const workOrderAssigneePushAdvice = computed(() => {
  const assignee = String(item.value.assignee || "").trim();
  const highPriority = String(item.value.priority || "").toLowerCase() === "high";
  if (!assignee || assignee === "未指派") return "下一步建议：先明确责任人并同步接单时限。";
  if (item.value.status === "closed") return "下一步建议：工单已闭环，责任人同步复盘结论即可。";
  if (highPriority) return "下一步建议：责任人需提高跟进频率，优先推进高优工单闭环。";
  return "下一步建议：责任人按当前节奏推进处理，并及时更新状态。";
});

const workOrderInfoCompletenessSummary = computed(() => {
  const titleReady = !!String(item.value.title || "").trim();
  const descReady = !!String(item.value.description || "").trim();
  const alarmReady = !!String(item.value.alarmId || "").trim();
  const assigneeReady = !!String(item.value.assignee || "").trim() && String(item.value.assignee || "").trim() !== "未指派";
  const readyCount = [titleReady, descReady, alarmReady, assigneeReady].filter(Boolean).length;
  const missing: string[] = [];
  if (!titleReady) missing.push("标题");
  if (!descReady) missing.push("描述");
  if (!alarmReady) missing.push("关联告警");
  if (!assigneeReady) missing.push("责任人");
  return `工单信息完整性：完整项=${readyCount}/4；缺失项=${missing.join("/") || "无"}；状态=${statusTag(item.value.status).text}`;
});

const workOrderInfoCompletenessAdvice = computed(() => {
  if (workOrderInfoCompletenessSummary.value.includes("缺失项=无")) {
    return "下一步建议：信息完整，可继续推进状态流转与闭环验证。";
  }
  if (workOrderInfoCompletenessSummary.value.includes("责任人")) return "下一步建议：优先补齐责任人，明确跟进归属。";
  if (workOrderInfoCompletenessSummary.value.includes("描述")) return "下一步建议：补充处置描述，便于交接与复盘。";
  return "下一步建议：补齐缺失字段后再推进后续流转动作。";
});

const workOrderActionCoverageSummary = computed(() => {
  const status = statusTag(item.value.status).text;
  const actions = nextActions.value;
  const actionCount = actions.length;
  const hasClose = actions.includes("closed");
  return `流转动作覆盖：当前状态=${status}；可流转动作数=${actionCount}；动作列表=${actions.join("/") || "无"}；可直接闭环=${hasClose ? "是" : "否"}`;
});

const workOrderActionCoverageAdvice = computed(() => {
  const actions = nextActions.value;
  if (actions.length <= 0) return "下一步建议：当前无可流转动作，保持闭环状态并归档。";
  if (actions.includes("closed")) return "下一步建议：满足条件时可直接闭环，同时补齐处置与回归记录。";
  if (actions.includes("resolved")) return "下一步建议：优先推进至已解决，再进入闭环。";
  return "下一步建议：先转入处理中并持续更新处置轨迹。";
});

function copyWorkOrderHandoverSummary() {
  const text = [workOrderHandoverSummary.value, `可流转动作：${nextActions.value.join("/") || "无"}`, workOrderNextStepAdvice.value].join(
    "；"
  );
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "交接摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyWorkOrderFlowRiskSummary() {
  const text = [workOrderFlowRiskSummary.value, workOrderFlowRiskAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "流转风险摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyWorkOrderTimelinessSummary() {
  const text = [workOrderTimelinessSummary.value, workOrderTimelinessAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "流转时效摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyWorkOrderAssigneePushSummary() {
  const text = [workOrderAssigneePushSummary.value, workOrderAssigneePushAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "责任人推进摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyWorkOrderInfoCompletenessSummary() {
  const text = [workOrderInfoCompletenessSummary.value, workOrderInfoCompletenessAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "信息完整性摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyWorkOrderActionCoverageSummary() {
  const text = [workOrderActionCoverageSummary.value, workOrderActionCoverageAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "动作覆盖摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function move(next: WorkOrderStatus) {
  if (!item.value.id) return;
  loading.value = true;
  setMoveStatus("正在提交流转...");
  try {
    const updated = await updateWorkOrderStatus(item.value.id, next);
    item.value.status = updated.status;
    openerEventChannel?.emit("workOrderUpdated", {
      id: item.value.id,
      status: updated.status
    });
    setMoveStatus(`流转成功：${next}`);
    uni.showToast({ title: `已更新为 ${statusTag(updated.status).text}`, icon: "none" });
  } catch (err: any) {
    setMoveStatus(err?.message ? `流转失败：${err.message}` : "流转失败，请重试");
    uni.showToast({ title: "状态流转失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

onLoad((query) => {
  try {
    openerEventChannel = uni.getOpenerEventChannel();
  } catch {
    openerEventChannel = null;
  }
  item.value.id = String(query?.id || "");
  item.value.title = decodeURIComponent(String(query?.title || ""));
  const status = String(query?.status || "open") as WorkOrderStatus;
  item.value.status = ["open", "in_progress", "resolved", "closed"].includes(status) ? status : "open";
  item.value.priority = decodeURIComponent(String(query?.priority || "medium"));
  item.value.assignee = decodeURIComponent(String(query?.assignee || "未指派"));
  item.value.alarmId = decodeURIComponent(String(query?.alarmId || ""));
  item.value.createdAt = decodeURIComponent(String(query?.createdAt || ""));
  item.value.description = decodeURIComponent(String(query?.description || ""));
  if (!item.value.id) {
    setDetailLoadStatus("详情加载失败：缺少工单ID，请从工单列表重新进入");
    uni.showToast({ title: "工单参数异常", icon: "none" });
    return;
  }
  setDetailLoadStatus(`详情加载成功：工单ID=${item.value.id}`);
});
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:32rpx">{{ item.title || "工单详情" }}</text>
        <AppStatusTag :text="statusTag(item.status).text" :type="statusTag(item.status).type" />
      </view>
      <text class="app-subtext">工单ID：{{ item.id || "-" }}</text>
      <text class="app-subtext">关联告警：{{ item.alarmId || "-" }}</text>
      <text class="app-subtext">优先级：{{ item.priority || "-" }}</text>
      <text class="app-subtext">处置人：{{ item.assignee || "-" }}</text>
      <text class="app-subtext">创建时间：{{ item.createdAt || "-" }}</text>
      <text class="app-subtext">描述：{{ item.description || "-" }}</text>
      <text class="app-subtext">详情状态：{{ detailLoadStatusMessage || "-" }}</text>
      <text v-if="detailLoadStatusAt" class="app-subtext">详情时间：{{ detailLoadStatusAt }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">状态流转</text>
      <text class="app-subtext">{{ workOrderHandoverSummary }}</text>
      <text class="app-subtext">{{ workOrderNextStepAdvice }}</text>
      <text class="app-subtext">{{ workOrderFlowRiskSummary }}</text>
      <text class="app-subtext">{{ workOrderFlowRiskAdvice }}</text>
      <text class="app-subtext">{{ workOrderTimelinessSummary }}</text>
      <text class="app-subtext">{{ workOrderTimelinessAdvice }}</text>
      <text class="app-subtext">{{ workOrderAssigneePushSummary }}</text>
      <text class="app-subtext">{{ workOrderAssigneePushAdvice }}</text>
      <text class="app-subtext">{{ workOrderInfoCompletenessSummary }}</text>
      <text class="app-subtext">{{ workOrderInfoCompletenessAdvice }}</text>
      <text class="app-subtext">{{ workOrderActionCoverageSummary }}</text>
      <text class="app-subtext">{{ workOrderActionCoverageAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyWorkOrderHandoverSummary">复制交接摘要</button>
        <button size="mini" @click="copyWorkOrderFlowRiskSummary">复制流转风险摘要</button>
        <button size="mini" @click="copyWorkOrderTimelinessSummary">复制流转时效摘要</button>
        <button size="mini" @click="copyWorkOrderAssigneePushSummary">复制责任人推进摘要</button>
        <button size="mini" @click="copyWorkOrderInfoCompletenessSummary">复制信息完整性摘要</button>
        <button size="mini" @click="copyWorkOrderActionCoverageSummary">复制动作覆盖摘要</button>
      </view>
      <view class="app-row">
        <button
          v-for="act in nextActions"
          :key="act"
          size="mini"
          :loading="loading"
          @click="move(act)"
        >
          {{ statusTag(act).text }}
        </button>
      </view>
      <text class="app-subtext">流转状态：{{ moveStatusMessage || "-" }}</text>
      <text v-if="moveStatusAt" class="app-subtext">流转时间：{{ moveStatusAt }}</text>
      <text v-if="nextActions.length === 0" class="app-subtext">当前状态无可用流转动作</text>
    </view>
  </view>
</template>
