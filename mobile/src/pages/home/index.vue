<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchHomeOverview, type HomeOverview } from "@/api/home";

const overview = ref<HomeOverview>({
  online_devices: 0,
  offline_devices: 0,
  today_alarms: 0,
  pending_work_orders: 0
});
const loading = ref(false);
const homeOverviewLoadMessage = ref("未刷新");
const homeOverviewLastLoadedAt = ref("");

const homeOverviewSummaryText = computed(() => {
  return `总览摘要：在线=${overview.value.online_devices}；离线=${overview.value.offline_devices}；今日告警=${overview.value.today_alarms}；处理中工单=${overview.value.pending_work_orders}`;
});

const homeOverviewRiskLevelText = computed(() => {
  const offline = Number(overview.value.offline_devices || 0);
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  if (alarms >= 20 || pending >= 10 || offline >= 30) return "风险等级：高";
  if (alarms >= 8 || pending >= 4 || offline >= 10) return "风险等级：中";
  return "风险等级：低";
});

const homeOverviewNextStepAdvice = computed(() => {
  const offline = Number(overview.value.offline_devices || 0);
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  if (alarms > 0) return "下一步建议：优先进入告警页处理高优告警，再回看工单积压。";
  if (pending > 0) return "下一步建议：优先处理工单积压并同步处置进度。";
  if (offline > 0) return "下一步建议：进入设备页巡检离线设备并执行预览抽检。";
  return "下一步建议：保持巡检频率并继续观察总览变化。";
});

const homeQuickEntrySummaryText = computed(() => {
  const entries = ["预览", "告警", "设备", "指挥"];
  const recommended =
    Number(overview.value.today_alarms || 0) > 0
      ? "告警"
      : Number(overview.value.pending_work_orders || 0) > 0
        ? "设备"
        : Number(overview.value.offline_devices || 0) > 0
          ? "设备"
          : "预览";
  return `快捷入口巡检：入口数=${entries.length}；推荐入口=${recommended}；入口清单=${entries.join("/")}`;
});

const homeQuickEntryNextStepAdvice = computed(() => {
  if (Number(overview.value.today_alarms || 0) > 0) return "下一步建议：先从“查看告警”入口进入，处理高优告警。";
  if (Number(overview.value.pending_work_orders || 0) > 0) return "下一步建议：先从“设备巡检”入口检查关联设备状态。";
  if (Number(overview.value.offline_devices || 0) > 0) return "下一步建议：先从“设备巡检”入口定位离线设备。";
  return "下一步建议：从“一键预览”入口进行抽检，保持值班巡检节奏。";
});

const homeDutyKickoffSummaryText = computed(() => {
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  const offline = Number(overview.value.offline_devices || 0);
  const pressure = alarms >= 20 || pending >= 10 || offline >= 30 ? "高" : alarms >= 8 || pending >= 4 || offline >= 10 ? "中" : "低";
  const focus = alarms > 0 ? "告警分诊" : pending > 0 ? "工单清理" : offline > 0 ? "离线排查" : "预览抽检";
  return `值班开局摘要：压力等级=${pressure}；主攻方向=${focus}；告警=${alarms}；工单=${pending}；离线=${offline}`;
});

const homeDutyKickoffAdvice = computed(() => {
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  const offline = Number(overview.value.offline_devices || 0);
  if (alarms > 0) return "下一步建议：先完成高优告警分诊，再同步工单承接。";
  if (pending > 0) return "下一步建议：先清理处理中工单，避免跨班积压。";
  if (offline > 0) return "下一步建议：先做离线设备连通性排查并复测预览。";
  return "下一步建议：执行一次预览抽检并记录开局基线。";
});

const homeAlarmWorkOrderLinkageSummaryText = computed(() => {
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  const linkageRate = alarms <= 0 ? 0 : Number(((pending / alarms) * 100).toFixed(2));
  const pressure = pending >= 10 || alarms >= 20 ? "高" : pending >= 4 || alarms >= 8 ? "中" : "低";
  return `告警工单联动摘要：告警=${alarms}；工单=${pending}；联动率=${linkageRate}%；联动压力=${pressure}`;
});

const homeAlarmWorkOrderLinkageAdvice = computed(() => {
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  if (alarms <= 0 && pending <= 0) return "下一步建议：当前联动压力低，保持例行巡检即可。";
  if (pending <= 0 && alarms > 0) return "下一步建议：存在告警但工单承接不足，优先补建处置工单。";
  if (pending > alarms) return "下一步建议：工单积压高于告警，优先清理历史待处理工单。";
  return "下一步建议：按高优告警对应工单推进处置，并同步闭环进度。";
});

const homeDeviceStructureSummaryText = computed(() => {
  const online = Number(overview.value.online_devices || 0);
  const offline = Number(overview.value.offline_devices || 0);
  const total = online + offline;
  const onlineRate = total <= 0 ? 0 : Number(((online / total) * 100).toFixed(2));
  const offlineRate = total <= 0 ? 0 : Number(((offline / total) * 100).toFixed(2));
  const structure = offlineRate >= 40 ? "离线偏高" : offlineRate >= 20 ? "离线可控" : "结构健康";
  return `设备结构摘要：总量=${total}；在线=${online}(${onlineRate}%)；离线=${offline}(${offlineRate}%)；结构评估=${structure}`;
});

const homeDeviceStructureAdvice = computed(() => {
  const offline = Number(overview.value.offline_devices || 0);
  const online = Number(overview.value.online_devices || 0);
  const total = online + offline;
  const offlineRate = total <= 0 ? 0 : Number(((offline / total) * 100).toFixed(2));
  if (total <= 0) return "下一步建议：先完成设备同步，建立设备结构基线。";
  if (offlineRate >= 40) return "下一步建议：离线占比较高，优先排查离线分组并回归验证。";
  if (offlineRate >= 20) return "下一步建议：持续跟进离线设备恢复，防止结构进一步恶化。";
  return "下一步建议：结构稳定，保持在线抽检与离线跟踪节奏。";
});

const homeRiskBroadcastSummaryText = computed(() => {
  const alarms = Number(overview.value.today_alarms || 0);
  const pending = Number(overview.value.pending_work_orders || 0);
  const offline = Number(overview.value.offline_devices || 0);
  const triggers: string[] = [];
  if (alarms >= 20) triggers.push("告警高位");
  if (pending >= 10) triggers.push("工单积压");
  if (offline >= 30) triggers.push("离线高位");
  const level = triggers.length >= 2 ? "高" : triggers.length === 1 ? "中" : "低";
  return `风险播报：等级=${level}；触发项=${triggers.join("/") || "无"}；告警=${alarms}；工单=${pending}；离线=${offline}`;
});

const homeRiskBroadcastAdvice = computed(() => {
  if (homeRiskBroadcastSummaryText.value.includes("等级=高")) return "下一步建议：先处置触发项最多的模块，并同步跨模块联动进展。";
  if (homeRiskBroadcastSummaryText.value.includes("等级=中")) return "下一步建议：按触发项优先级逐项消减风险并观察回落趋势。";
  return "下一步建议：当前风险可控，保持巡检与抽检节奏。";
});

async function loadOverview() {
  loading.value = true;
  homeOverviewLoadMessage.value = "";
  try {
    overview.value = await fetchHomeOverview();
    homeOverviewLastLoadedAt.value = new Date().toISOString();
    homeOverviewLoadMessage.value = "总览拉取成功";
  } catch (err: any) {
    homeOverviewLoadMessage.value = err?.message ? `总览拉取失败：${err.message}` : "总览拉取失败，请重试";
    uni.showToast({ title: "总览拉取失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openPage(url: string) {
  uni.navigateTo({ url });
}

function copyHomeOverviewSummary() {
  const text = [homeOverviewSummaryText.value, homeOverviewRiskLevelText.value, homeOverviewNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "总览摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyHomeQuickEntrySummary() {
  const text = [homeQuickEntrySummaryText.value, homeQuickEntryNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "快捷入口摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyHomeDutyKickoffSummary() {
  const text = [homeDutyKickoffSummaryText.value, homeDutyKickoffAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "开局摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyHomeAlarmWorkOrderLinkageSummary() {
  const text = [homeAlarmWorkOrderLinkageSummaryText.value, homeAlarmWorkOrderLinkageAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "联动摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyHomeDeviceStructureSummary() {
  const text = [homeDeviceStructureSummaryText.value, homeDeviceStructureAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "设备结构摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyHomeRiskBroadcastSummary() {
  const text = [homeRiskBroadcastSummaryText.value, homeRiskBroadcastAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "风险播报摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadOverview);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">移动运维总览</view>
    <view class="app-subtext">重点信息优先展示，3 秒进入核心操作</view>

    <view class="app-card">
      <view class="app-row">
        <text>在线设备</text>
        <text>{{ overview.online_devices }}</text>
      </view>
      <view class="app-row" style="margin-top: 12rpx">
        <text>离线设备</text>
        <text>{{ overview.offline_devices }}</text>
      </view>
      <view class="app-row" style="margin-top: 12rpx">
        <text>今日告警</text>
        <text>{{ overview.today_alarms }}</text>
      </view>
      <view class="app-row" style="margin-top: 12rpx">
        <text>处理中工单</text>
        <text>{{ overview.pending_work_orders }}</text>
      </view>
      <button style="margin-top: 20rpx" type="primary" :loading="loading" @click="loadOverview">刷新总览</button>
      <text class="app-subtext">刷新状态：{{ homeOverviewLoadMessage || "-" }}</text>
      <text class="app-subtext">上次刷新：{{ homeOverviewLastLoadedAt || "-" }}</text>
      <text class="app-subtext" style="margin-top: 8rpx">{{ homeOverviewSummaryText }}</text>
      <text class="app-subtext">{{ homeOverviewRiskLevelText }}</text>
      <text class="app-subtext">{{ homeOverviewNextStepAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyHomeOverviewSummary">复制总览摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ homeQuickEntrySummaryText }}</text>
      <text class="app-subtext">{{ homeQuickEntryNextStepAdvice }}</text>
      <text class="app-subtext">{{ homeDutyKickoffSummaryText }}</text>
      <text class="app-subtext">{{ homeDutyKickoffAdvice }}</text>
      <text class="app-subtext">{{ homeAlarmWorkOrderLinkageSummaryText }}</text>
      <text class="app-subtext">{{ homeAlarmWorkOrderLinkageAdvice }}</text>
      <text class="app-subtext">{{ homeDeviceStructureSummaryText }}</text>
      <text class="app-subtext">{{ homeDeviceStructureAdvice }}</text>
      <text class="app-subtext">{{ homeRiskBroadcastSummaryText }}</text>
      <text class="app-subtext">{{ homeRiskBroadcastAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyHomeQuickEntrySummary">复制快捷入口摘要</button>
        <button size="mini" @click="copyHomeDutyKickoffSummary">复制开局摘要</button>
        <button size="mini" @click="copyHomeAlarmWorkOrderLinkageSummary">复制联动摘要</button>
        <button size="mini" @click="copyHomeDeviceStructureSummary">复制设备结构摘要</button>
        <button size="mini" @click="copyHomeRiskBroadcastSummary">复制风险播报摘要</button>
      </view>
      <button type="primary" @click="openPage('/pages/preview/index')">一键预览</button>
      <button @click="openPage('/pages/alarm/index')">查看告警</button>
      <button @click="openPage('/pages/alarm-notifications/index')">通知记录</button>
      <button @click="openPage('/pages/device/index')">设备巡检</button>
      <button @click="openPage('/pages/device-records/index')">设备录像</button>
      <button @click="openPage('/pages/cloud-records/index')">云端录像</button>
      <button @click="openPage('/pages/record-schedule/index')">录像计划</button>
      <button @click="openPage('/pages/api-key-manager/index')">接口密钥</button>
      <button @click="openPage('/pages/audit-center/index')">审计中心</button>
      <button @click="openPage('/pages/channel-group/index')">业务分组</button>
      <button @click="openPage('/pages/channel-region/index')">行政区划</button>
      <button @click="openPage('/pages/organizations/index')">组织管理</button>
      <button @click="openPage('/pages/user-manager/index')">用户管理</button>
      <button @click="openPage('/pages/role-manager/index')">角色管理</button>
      <button @click="openPage('/pages/account-security/index')">账号安全</button>
      <button @click="openPage('/pages/report-center/index')">报表中心</button>
      <button @click="openPage('/pages/map-providers/index')">地图配置</button>
      <button @click="openPage('/pages/config-center/index')">配置中心</button>
      <button @click="openPage('/pages/release-center/index')">发布中心</button>
      <button @click="openPage('/pages/visual-command/index')">可视化指挥</button>
      <button @click="openPage('/pages/sla-dashboard/index')">SLA看板</button>
      <button @click="openPage('/pages/health-dashboard/index')">健康看板</button>
      <button @click="openPage('/pages/operations/index')">运维中心</button>
      <button @click="openPage('/pages/network-overview/index')">网络概况</button>
      <button @click="openPage('/pages/app-logs/index')">应用日志</button>
      <button @click="openPage('/pages/legacy-gateway/index')">多协议接入</button>
      <button @click="openPage('/pages/cascade-platforms/index')">国标级联</button>
      <button @click="openPage('/pages/monitor-center/index')">监控中心</button>
      <button @click="openPage('/pages/gis-map/index')">GIS地图</button>
      <button @click="openPage('/pages/dashboard/index')">工作台</button>
      <button @click="openPage('/pages/asset-management/index')">资产管理</button>
      <button @click="openPage('/pages/tv-wall/index')">电视墙</button>
      <button @click="openPage('/pages/structured-event-center/index')">结构化事件中心</button>
      <button @click="openPage('/pages/billing-center/index')">计费中心</button>
      <button @click="openPage('/pages/plugin-runtime/index')">插件运行中心</button>
      <button @click="openPage('/pages/plugin-center/index')">插件中心</button>
      <button @click="openPage('/pages/suite-center/index')">移动能力中心</button>
      <button @click="openPage('/pages/plugin-detail/index')">插件详情</button>
      <button @click="openPage('/pages/mobile-app-center/index')">手机版中心</button>
      <button @click="openPage('/pages/mini-program-center/index')">小程序中心</button>
      <button @click="openPage('/pages/visual-command-center/index')">可视化指挥中心</button>
      <button @click="openPage('/pages/channel-list/index')">通道列表</button>
      <button @click="openPage('/pages/behavior-recognition-mobile/index')">行为识别</button>
      <button @click="openPage('/pages/face-recognition-mobile/index')">人脸识别</button>
      <button @click="openPage('/pages/plate-recognition-mobile/index')">车牌识别</button>
      <button @click="openPage('/pages/push-stream-list/index')">推流列表</button>
      <button @click="openPage('/pages/pull-proxy-list/index')">拉流代理</button>
      <button @click="openPage('/pages/channel-manager/index')">通道管理</button>
      <button @click="openPage('/pages/alarm-link-rules/index')">联动规则</button>
      <button @click="openPage('/pages/work-order/index')">工单管理</button>
      <button @click="openPage('/pages/command/index')">移动指挥</button>
    </view>
  </view>
</template>
