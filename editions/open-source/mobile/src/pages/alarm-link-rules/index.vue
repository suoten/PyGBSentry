<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, reactive, ref } from "vue";
import {
  createAlarmLinkRule,
  deleteAlarmLinkRule,
  fetchAlarmLinkRules,
  type AlarmLinkRuleItem,
  type AlarmLinkRulePayload,
  updateAlarmLinkRule
} from "@/api/alarm";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const saving = ref(false);
const rules = ref<AlarmLinkRuleItem[]>([]);
const editingId = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const form = reactive<AlarmLinkRulePayload>({
  name: "",
  enabled: true,
  min_priority: null,
  max_priority: null,
  start_time: "",
  end_time: "",
  days: "",
  organization_id: "",
  link_record: true,
  link_wall: false,
  link_notify: false
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function resetForm() {
  editingId.value = "";
  form.name = "";
  form.enabled = true;
  form.min_priority = null;
  form.max_priority = null;
  form.start_time = "";
  form.end_time = "";
  form.days = "";
  form.organization_id = "";
  form.link_record = true;
  form.link_wall = false;
  form.link_notify = false;
}

function normalizePayload(): AlarmLinkRulePayload {
  const minP = form.min_priority == null ? null : Math.max(1, Math.min(4, Number(form.min_priority)));
  const maxP = form.max_priority == null ? null : Math.max(1, Math.min(4, Number(form.max_priority)));
  return {
    name: String(form.name || "").trim(),
    enabled: !!form.enabled,
    min_priority: minP,
    max_priority: maxP,
    start_time: String(form.start_time || "").trim() || null,
    end_time: String(form.end_time || "").trim() || null,
    days: String(form.days || "").trim() || null,
    organization_id: String(form.organization_id || "").trim() || null,
    link_record: !!form.link_record,
    link_wall: !!form.link_wall,
    link_notify: !!form.link_notify
  };
}

function renderDays(days?: string | null) {
  const raw = String(days || "").trim();
  if (!raw) return "每天";
  const map: Record<string, string> = {
    "0": "周一",
    "1": "周二",
    "2": "周三",
    "3": "周四",
    "4": "周五",
    "5": "周六",
    "6": "周日"
  };
  const labels = raw
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => map[x] || x);
  return labels.join("、") || "每天";
}

const summaryText = computed(() => {
  const enabled = rules.value.filter((x) => !!x.enabled).length;
  const disabled = rules.value.length - enabled;
  return `联动规则：总数=${rules.value.length}；启用=${enabled}；停用=${disabled}`;
});

const adviceText = computed(() => {
  const enabled = rules.value.filter((x) => !!x.enabled).length;
  if (enabled <= 0) return "下一步建议：至少启用一条规则，避免告警联动断链。";
  return "下一步建议：优先检查高优先级规则的时间段与组织限制是否匹配值班策略。";
});

async function loadRules() {
  loading.value = true;
  try {
    const rows = (await fetchAlarmLinkRules()) || [];
    rules.value = [...rows];
    setLoadStatus(`刷新成功：${rules.value.length} 条`);
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    setLoadStatus(`刷新失败：${reason}`);
    uni.showToast({ title: "规则加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function editRule(row: AlarmLinkRuleItem) {
  editingId.value = String(row.id || "");
  form.name = String(row.name || "");
  form.enabled = !!row.enabled;
  form.min_priority = row.min_priority == null ? null : Number(row.min_priority);
  form.max_priority = row.max_priority == null ? null : Number(row.max_priority);
  form.start_time = String(row.start_time || "");
  form.end_time = String(row.end_time || "");
  form.days = String(row.days || "");
  form.organization_id = String(row.organization_id || "");
  form.link_record = !!row.link_record;
  form.link_wall = !!row.link_wall;
  form.link_notify = !!row.link_notify;
}

async function saveRule() {
  const payload = normalizePayload();
  if (!payload.name) {
    uni.showToast({ title: "请先填写规则名称", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      await updateAlarmLinkRule(editingId.value, payload);
      uni.showToast({ title: "规则已更新", icon: "none" });
    } else {
      await createAlarmLinkRule(payload);
      uni.showToast({ title: "规则已创建", icon: "none" });
    }
    resetForm();
    await loadRules();
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    uni.showToast({ title: `保存失败：${reason}`, icon: "none" });
  } finally {
    saving.value = false;
  }
}

function removeRule(row: AlarmLinkRuleItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认删除",
    content: `确认删除规则「${row.name || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await deleteAlarmLinkRule(id);
        uni.showToast({ title: "规则已删除", icon: "none" });
        if (editingId.value === id) resetForm();
        await loadRules();
      } catch (err: any) {
        const reason = err?.message ? String(err.message) : "请稍后重试";
        uni.showToast({ title: `删除失败：${reason}`, icon: "none" });
      }
    }
  });
}

function copySummary() {
  const text = [summaryText.value, adviceText.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "规则摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadRules);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">告警联动规则</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadRules">刷新</button>
      </view>
      <text class="app-subtext">{{ adviceText }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text v-if="loadAt" class="app-subtext">状态时间：{{ loadAt }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制规则摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">{{ editingId ? "编辑规则" : "新增规则" }}</text>
      <input v-model="form.name" placeholder="规则名称" />
      <view class="app-row">
        <text class="app-subtext">启用</text>
        <switch :checked="form.enabled" @change="(e:any)=>form.enabled=!!e?.detail?.value" />
      </view>
      <view class="app-row">
        <input v-model="form.min_priority" type="number" placeholder="最小优先级(1-4)" style="flex:1" />
        <input v-model="form.max_priority" type="number" placeholder="最大优先级(1-4)" style="flex:1" />
      </view>
      <view class="app-row">
        <input v-model="form.start_time" placeholder="开始时间 HH:mm (可空)" style="flex:1" />
        <input v-model="form.end_time" placeholder="结束时间 HH:mm (可空)" style="flex:1" />
      </view>
      <input v-model="form.days" placeholder="星期限制，如 0,1,2（可空表示每天）" />
      <input v-model="form.organization_id" placeholder="组织ID（可空）" />
      <view class="app-row">
        <label class="app-subtext"><checkbox :checked="form.link_record" @click="form.link_record=!form.link_record" /> 录像联动</label>
        <label class="app-subtext"><checkbox :checked="form.link_wall" @click="form.link_wall=!form.link_wall" /> 上墙联动</label>
        <label class="app-subtext"><checkbox :checked="form.link_notify" @click="form.link_notify=!form.link_notify" /> 通知联动</label>
      </view>
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveRule">{{ editingId ? "更新规则" : "创建规则" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="rules.length" class="app-gap-12">
        <view v-for="row in rules" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || row.id }}</text>
            <text class="app-subtext">启用：{{ row.enabled ? "是" : "否" }} / 优先级：{{ row.min_priority || 1 }}-{{ row.max_priority || 4 }}</text>
            <text class="app-subtext">时段：{{ (row.start_time && row.end_time) ? `${row.start_time}-${row.end_time}` : "全天" }} / 星期：{{ renderDays(row.days) }}</text>
            <text class="app-subtext">组织限制：{{ row.organization_id || "不限" }}</text>
            <text class="app-subtext">动作：{{ row.link_record ? "录像 " : "" }}{{ row.link_wall ? "上墙 " : "" }}{{ row.link_notify ? "通知 " : "" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.enabled ? '启用' : '停用'" :type="row.enabled ? 'success' : 'info'" />
            <button size="mini" @click="editRule(row)">编辑</button>
            <button size="mini" @click="removeRule(row)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '规则加载中...' : '暂无联动规则'" />
    </view>
  </view>
</template>
