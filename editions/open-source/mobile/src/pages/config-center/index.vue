<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchBasicConfig,
  fetchCurrentDraft,
  fetchDatabaseConfig,
  saveBasicConfig,
  saveDatabaseConfig,
  testDatabaseConfig,
  validateDraft
} from "@/api/config";

const loading = ref(false);
const saving = ref(false);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const draftId = ref("");

const basicForm = ref({
  streamPullTimeout: 10,
  alarmDefaultLevel: "medium",
  deviceHeartbeatInterval: 60,
  recordAutoCleanDays: 0,
  logRetentionDays: 7
});

const dbForm = ref({
  database_type: "postgresql",
  host: "",
  port: 5432,
  name: "",
  username: "",
  password: "",
  sqlite_path: "./pygbsentry.db",
  sqlalchemy_database_uri: ""
});

const validateSummary = ref("未校验");
const validateErrors = ref<string[]>([]);
const validateWarnings = ref<string[]>([]);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `配置中心：草稿=${draftId.value || "-"}；数据库=${dbForm.value.database_type || "-"}；告警默认等级=${basicForm.value.alarmDefaultLevel || "-"}`;
});

const nextStepAdvice = computed(() => {
  if (!draftId.value) return "下一步建议：先读取当前草稿并执行校验，再做发布中心操作。";
  if (validateErrors.value.length) return "下一步建议：先修复草稿错误项，再进入发布中心。";
  return "下一步建议：已可进入发布中心执行差异预览与发布。";
});

async function loadData() {
  loading.value = true;
  try {
    const [basicRes, dbRes, draftRes] = await Promise.allSettled([fetchBasicConfig(), fetchDatabaseConfig(), fetchCurrentDraft()]);
    if (basicRes.status === "fulfilled") {
      basicForm.value = {
        streamPullTimeout: Number(basicRes.value.streamPullTimeout ?? 10),
        alarmDefaultLevel: String(basicRes.value.alarmDefaultLevel ?? "medium"),
        deviceHeartbeatInterval: Number(basicRes.value.deviceHeartbeatInterval ?? 60),
        recordAutoCleanDays: Number(basicRes.value.recordAutoCleanDays ?? 0),
        logRetentionDays: Number(basicRes.value.logRetentionDays ?? 7)
      };
    }
    if (dbRes.status === "fulfilled") {
      dbForm.value = {
        database_type: String(dbRes.value.database_type || "postgresql"),
        host: String(dbRes.value.host || ""),
        port: Number(dbRes.value.port || 5432),
        name: String(dbRes.value.name || ""),
        username: String(dbRes.value.username || ""),
        password: String(dbRes.value.password || ""),
        sqlite_path: String(dbRes.value.sqlite_path || "./pygbsentry.db"),
        sqlalchemy_database_uri: String(dbRes.value.sqlalchemy_database_uri || "")
      };
    }
    if (draftRes.status === "fulfilled") {
      draftId.value = String(draftRes.value.draft_id || "");
    }
    const failedCount = [basicRes, dbRes, draftRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "配置加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveBasic() {
  saving.value = true;
  try {
    await saveBasicConfig({ ...basicForm.value });
    uni.showToast({ title: "基础配置已保存", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function testDatabase() {
  saving.value = true;
  try {
    const res = await testDatabaseConfig({ ...dbForm.value });
    const summary = String(res.compatibility?.summary || "ok");
    const vendorHint = String(res.vendor_hint || "");
    uni.showToast({ title: summary === "ok" ? "数据库连接测试成功" : "数据库连接可用但存在风险", icon: "none" });
    if (vendorHint) {
      validateSummary.value = `数据库提示：${vendorHint}`;
    }
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `测试失败：${err.message}` : "测试失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function saveDatabase() {
  saving.value = true;
  try {
    await saveDatabaseConfig({ ...dbForm.value });
    uni.showToast({ title: "数据库配置已保存", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function validateCurrentDraft() {
  if (!draftId.value) {
    uni.showToast({ title: "请先读取草稿", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const res = await validateDraft(draftId.value);
    validateErrors.value = Array.isArray(res.errors) ? res.errors.map((x) => `${x.field}: ${x.message}`) : [];
    validateWarnings.value = Array.isArray(res.warnings) ? res.warnings.map((x) => `${x.field}: ${x.message}`) : [];
    validateSummary.value = res.valid ? "草稿校验通过" : "草稿校验未通过";
    uni.showToast({ title: res.valid ? "草稿校验通过" : "草稿校验失败", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `校验失败：${err.message}` : "校验失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

function copySummary() {
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `草稿校验=${validateSummary.value}`,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "配置摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">配置中心</view>

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
      <text class="app-subtext">基础配置</text>
      <input v-model="basicForm.streamPullTimeout" type="number" placeholder="拉流超时（秒）" />
      <input v-model="basicForm.alarmDefaultLevel" placeholder="默认告警等级（low/medium/high）" />
      <input v-model="basicForm.deviceHeartbeatInterval" type="number" placeholder="设备心跳间隔（秒）" />
      <input v-model="basicForm.recordAutoCleanDays" type="number" placeholder="录像自动清理（天）" />
      <input v-model="basicForm.logRetentionDays" type="number" placeholder="日志保留（天）" />
      <button size="mini" type="primary" :loading="saving" @click="saveBasic">保存基础配置</button>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">数据库配置</text>
      <input v-model="dbForm.database_type" placeholder="数据库类型（postgresql/mysql/sqlite/kingbase/dameng）" />
      <input v-model="dbForm.host" placeholder="主机（sqlite 可空）" />
      <input v-model="dbForm.port" type="number" placeholder="端口" />
      <input v-model="dbForm.name" placeholder="数据库名" />
      <input v-model="dbForm.username" placeholder="用户名" />
      <input v-model="dbForm.password" password placeholder="密码" />
      <input v-model="dbForm.sqlite_path" placeholder="SQLite 路径" />
      <input v-model="dbForm.sqlalchemy_database_uri" placeholder="SQLAlchemy URI（可空）" />
      <view class="app-row">
        <button size="mini" :loading="saving" @click="testDatabase">测试连接</button>
        <button size="mini" type="primary" :loading="saving" @click="saveDatabase">保存数据库配置</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">草稿校验</text>
      <view class="app-row">
        <input v-model="draftId" placeholder="草稿ID（自动读取后可手动改）" />
        <button size="mini" :loading="saving" @click="validateCurrentDraft">执行草稿校验</button>
      </view>
      <text class="app-subtext">校验结果：{{ validateSummary }}</text>
      <text class="app-subtext">错误数：{{ validateErrors.length }}；告警数：{{ validateWarnings.length }}</text>
      <view v-if="validateErrors.length" class="app-gap-12">
        <text v-for="(row, idx) in validateErrors" :key="`e-${idx}`" class="app-subtext">{{ row }}</text>
      </view>
      <view v-if="validateWarnings.length" class="app-gap-12">
        <text v-for="(row, idx) in validateWarnings" :key="`w-${idx}`" class="app-subtext">{{ row }}</text>
      </view>
    </view>
  </view>
</template>
