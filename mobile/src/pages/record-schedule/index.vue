<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, reactive, ref } from "vue";
import { fetchChannelsFlat, type ChannelFlatItem } from "@/api/device";
import {
  createRecordSchedule,
  deleteRecordSchedule,
  forceStartRecordSchedule,
  forceStopRecordSchedule,
  listRecordScheduleRuntimes,
  listRecordSchedules,
  updateRecordSchedule,
  type RecordScheduleItem,
  type RecordScheduleRuntimeItem
} from "@/api/record";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const channels = ref<ChannelFlatItem[]>([]);
const schedules = ref<RecordScheduleItem[]>([]);
const runtimes = ref<RecordScheduleRuntimeItem[]>([]);
const planTypeFilter = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editingId = ref("");
const form = reactive({
  resource_id: "",
  plan_type: "timed",
  enabled: true,
  priority: 0,
  schedule_mode: "daily",
  custom_days: "1,2,3,4,5",
  start_time: "00:00",
  end_time: "23:59"
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const channelMap = computed(() => {
  const map: Record<string, string> = {};
  for (const row of channels.value) {
    map[String(row.id || "")] = `${row.device_name || row.device_id || "-"} / ${row.name || row.gb_id || "-"}`;
  }
  return map;
});

const runtimeMap = computed(() => {
  const map: Record<string, RecordScheduleRuntimeItem> = {};
  for (const row of runtimes.value) {
    map[String(row.schedule_id || "")] = row;
  }
  return map;
});

const summaryText = computed(() => {
  return `录像计划：总数=${schedules.value.length}；类型筛选=${planTypeFilter.value || "全部"}；运行中=${schedules.value.filter((s) => runtimeMap.value[String(s.id || "")]?.is_recording).length}`;
});

const nextStepAdvice = computed(() => {
  if (schedules.value.length <= 0) return "下一步建议：先新增定时计划，确保关键通道有录像策略。";
  const withError = schedules.value.filter((s) => String(runtimeMap.value[String(s.id || "")]?.last_error || "").trim()).length;
  if (withError > 0) return "下一步建议：优先处理运行态报错计划，必要时手动强制开始/停止。";
  return "下一步建议：定期抽样核对计划启用状态与运行态一致性。";
});

function planTypeLabel(value: string) {
  if (value === "timed") return "定时";
  if (value === "motion") return "移动侦测";
  if (value === "alarm") return "报警联动";
  if (value === "manual") return "手动";
  return value || "-";
}

function channelLabel(resourceId: string) {
  return channelMap.value[String(resourceId || "")] || resourceId || "-";
}

function runtimeOf(scheduleId: string) {
  return runtimeMap.value[String(scheduleId || "")];
}

function buildTimeRanges() {
  if (form.plan_type !== "timed") return [];
  const start = String(form.start_time || "").trim();
  const end = String(form.end_time || "").trim();
  if (!start || !end) throw new Error("请填写开始和结束时间");
  let days: number[] = [];
  if (form.schedule_mode === "daily") days = [0, 1, 2, 3, 4, 5, 6];
  else if (form.schedule_mode === "weekdays") days = [1, 2, 3, 4, 5];
  else if (form.schedule_mode === "weekend") days = [0, 6];
  else {
    days = String(form.custom_days || "")
      .split(",")
      .map((x) => Number(String(x).trim()))
      .filter((x) => !Number.isNaN(x) && x >= 0 && x <= 6);
  }
  if (!days.length) throw new Error("至少选择一个星期");
  return [{ start, end, days }];
}

function renderTimeRanges(row: RecordScheduleItem) {
  const tr = Array.isArray(row.time_ranges) ? row.time_ranges : [];
  if (!tr.length) return "无";
  return tr
    .map((x) => {
      const start = String(x.start || "00:00");
      const end = String(x.end || "23:59");
      const days = Array.isArray(x.days) ? x.days.join(",") : "0,1,2,3,4,5,6";
      return `${start}-${end}(${days})`;
    })
    .join(" | ");
}

function resetForm() {
  editingId.value = "";
  form.resource_id = "";
  form.plan_type = "timed";
  form.enabled = true;
  form.priority = 0;
  form.schedule_mode = "daily";
  form.custom_days = "1,2,3,4,5";
  form.start_time = "00:00";
  form.end_time = "23:59";
}

function editRow(row: RecordScheduleItem) {
  editingId.value = String(row.id || "");
  form.resource_id = String(row.resource_id || "");
  form.plan_type = String(row.plan_type || "timed");
  form.enabled = row.enabled !== false;
  form.priority = Number(row.priority || 0);
  const first = Array.isArray(row.time_ranges) && row.time_ranges.length ? row.time_ranges[0] : undefined;
  if (first) {
    form.start_time = String(first.start || "00:00");
    form.end_time = String(first.end || "23:59");
    const days = Array.isArray(first.days) ? first.days.map((x) => Number(x)).filter((x) => !Number.isNaN(x)) : [];
    if (days.length === 7) form.schedule_mode = "daily";
    else if ([1, 2, 3, 4, 5].every((x) => days.includes(x)) && !days.includes(0) && !days.includes(6)) form.schedule_mode = "weekdays";
    else if (days.length === 2 && days.includes(0) && days.includes(6)) form.schedule_mode = "weekend";
    else {
      form.schedule_mode = "custom";
      form.custom_days = days.join(",");
    }
  }
}

async function loadChannels() {
  try {
    const res = await fetchChannelsFlat({ skip: 0, limit: 5000, placement: "business" });
    channels.value = Array.isArray(res?.items) ? res.items : [];
  } catch {
    channels.value = [];
  }
}

async function loadSchedules() {
  loading.value = true;
  try {
    const rows = await listRecordSchedules(planTypeFilter.value || "");
    schedules.value = Array.isArray(rows) ? rows : [];
    const runtimeRows = await listRecordScheduleRuntimes("");
    runtimes.value = Array.isArray(runtimeRows) ? runtimeRows : [];
    setLoadStatus(`刷新成功：${schedules.value.length} 条`);
  } catch (err: any) {
    schedules.value = [];
    runtimes.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "录像计划加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveRow() {
  if (!editingId.value && !String(form.resource_id || "").trim()) {
    uni.showToast({ title: "请先选择通道", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const payload = {
      plan_type: String(form.plan_type || "timed"),
      enabled: !!form.enabled,
      priority: Number(form.priority || 0),
      time_ranges: buildTimeRanges()
    };
    if (editingId.value) {
      await updateRecordSchedule(editingId.value, payload);
      uni.showToast({ title: "计划已更新", icon: "none" });
    } else {
      await createRecordSchedule({
        resource_id: String(form.resource_id || "").trim(),
        ...payload
      });
      uni.showToast({ title: "计划已创建", icon: "none" });
    }
    resetForm();
    await loadSchedules();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function removeRow(row: RecordScheduleItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认删除",
    content: "确认删除该录像计划？",
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteRecordSchedule(id);
        uni.showToast({ title: "计划已删除", icon: "none" });
        await loadSchedules();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

async function forceStart(row: RecordScheduleItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await forceStartRecordSchedule(id, 60);
    uni.showToast({ title: "已触发强制开始", icon: "none" });
    await loadSchedules();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `操作失败：${err.message}` : "操作失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function forceStop(row: RecordScheduleItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await forceStopRecordSchedule(id, 10);
    uni.showToast({ title: "已触发强制停止", icon: "none" });
    await loadSchedules();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `操作失败：${err.message}` : "操作失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "录像计划摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function initPage() {
  await loadChannels();
  await loadSchedules();
}

onShow(initPage);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">录像计划</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadSchedules">刷新</button>
      </view>
      <picker mode="selector" :range="['全部类型', 'timed', 'motion', 'alarm', 'manual']" :value="['', 'timed', 'motion', 'alarm', 'manual'].indexOf(planTypeFilter)" @change="(e:any)=>{ const i=Number(e?.detail?.value||0); planTypeFilter=['','timed','motion','alarm','manual'][i] || ''; loadSchedules(); }">
        <view class="app-subtext">类型筛选：{{ planTypeFilter || "全部" }}</view>
      </picker>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ editingId ? "编辑录像计划" : "新增录像计划" }}</text>
      <picker
        mode="selector"
        :range="channels.map((x) => `${x.device_name || x.device_id || '-'} / ${x.name || x.gb_id || '-'}`)"
        :value="Math.max(0, channels.findIndex((x) => x.id === form.resource_id))"
        :disabled="!!editingId"
        @change="(e:any)=>{ const i=Number(e?.detail?.value || 0); form.resource_id = String(channels[i]?.id || ''); }"
      >
        <view class="app-subtext">通道：{{ channelLabel(form.resource_id) }}</view>
      </picker>
      <picker mode="selector" :range="['timed', 'motion', 'alarm', 'manual']" :value="['timed', 'motion', 'alarm', 'manual'].indexOf(form.plan_type)" @change="(e:any)=>{ const i=Number(e?.detail?.value || 0); form.plan_type=['timed','motion','alarm','manual'][i] || 'timed'; }">
        <view class="app-subtext">计划类型：{{ form.plan_type }}</view>
      </picker>
      <view class="app-row">
        <label class="app-subtext"><checkbox :checked="form.enabled" @click="form.enabled=!form.enabled" /> 启用</label>
        <input v-model="form.priority" type="number" placeholder="优先级" style="width:200rpx" />
      </view>
      <view v-if="form.plan_type==='timed'" class="app-gap-12">
        <picker mode="selector" :range="['daily', 'weekdays', 'weekend', 'custom']" :value="['daily','weekdays','weekend','custom'].indexOf(form.schedule_mode)" @change="(e:any)=>{ const i=Number(e?.detail?.value || 0); form.schedule_mode=['daily','weekdays','weekend','custom'][i] || 'daily'; }">
          <view class="app-subtext">执行周期：{{ form.schedule_mode }}</view>
        </picker>
        <input v-if="form.schedule_mode==='custom'" v-model="form.custom_days" placeholder="自定义星期，逗号分隔(0-6)" />
        <view class="app-row">
          <input v-model="form.start_time" placeholder="开始时间 HH:mm" style="flex:1" />
          <input v-model="form.end_time" placeholder="结束时间 HH:mm" style="flex:1" />
        </view>
      </view>
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveRow">{{ editingId ? "更新计划" : "创建计划" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="schedules.length" class="app-gap-12">
        <view v-for="row in schedules" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ channelLabel(row.resource_id) }}</text>
            <text class="app-subtext">类型：{{ planTypeLabel(row.plan_type) }}；优先级：{{ row.priority || 0 }}</text>
            <text class="app-subtext">时间窗：{{ renderTimeRanges(row) }}</text>
            <text class="app-subtext">运行态：{{ runtimeOf(row.id)?.is_recording ? "录制中" : runtimeOf(row.id)?.desired_recording ? "期望录制" : "未录制" }}</text>
            <text class="app-subtext">最近动作：{{ runtimeOf(row.id)?.last_action_at || runtimeOf(row.id)?.last_eval_at || "-" }}</text>
            <text class="app-subtext">错误：{{ runtimeOf(row.id)?.last_error || "-" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.enabled ? '启用' : '停用'" :type="row.enabled ? 'success' : 'info'" />
            <button size="mini" :loading="actionLoading" @click="editRow(row)">编辑</button>
            <button size="mini" :loading="actionLoading" @click="forceStart(row)">强制开始</button>
            <button size="mini" :loading="actionLoading" @click="forceStop(row)">强制停止</button>
            <button size="mini" :loading="actionLoading" @click="removeRow(row)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '录像计划加载中...' : '暂无录像计划'" />
    </view>
  </view>
</template>
