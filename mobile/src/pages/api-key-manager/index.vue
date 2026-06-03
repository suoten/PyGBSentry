<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { createUserApiKey, listMyApiKeys, revokeUserApiKey, type UserApiKeyItem } from "@/api/security";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const creating = ref(false);
const actionLoading = ref(false);
const keys = ref<UserApiKeyItem[]>([]);
const page = ref(1);
const pageSize = ref(10);
const createName = ref("");
const createScopesText = ref("");
const createdSecret = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return keys.value.slice(start, start + pageSize.value);
});

const summaryText = computed(() => {
  return `接口密钥：总数=${keys.value.length}；可用=${keys.value.filter((x) => x.is_active).length}；已撤销=${keys.value.filter((x) => !x.is_active).length}`;
});

const nextStepAdvice = computed(() => {
  if (keys.value.length <= 0) return "下一步建议：先按系统集成场景创建独立密钥，便于后续审计与回收。";
  return "下一步建议：定期回收长期未使用密钥，保持最小权限范围。";
});

function normalizeScopes(text: string) {
  return String(text || "")
    .split(",")
    .map((x) => String(x || "").trim())
    .filter(Boolean);
}

async function loadKeys() {
  loading.value = true;
  try {
    const rows = await listMyApiKeys();
    keys.value = Array.isArray(rows) ? rows : [];
    setLoadStatus(`刷新成功：${keys.value.length} 条`);
  } catch (err: any) {
    keys.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "密钥加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function createKey() {
  const name = String(createName.value || "").trim();
  if (!name) {
    uni.showToast({ title: "请输入密钥名称", icon: "none" });
    return;
  }
  creating.value = true;
  try {
    const res = await createUserApiKey({
      name,
      scopes: normalizeScopes(createScopesText.value)
    });
    createdSecret.value = String(res?.api_key || "");
    createName.value = "";
    createScopesText.value = "";
    if (createdSecret.value) {
      uni.setClipboardData({
        data: createdSecret.value,
        success: () => uni.showToast({ title: "创建成功，密钥已复制", icon: "none" }),
        fail: () => uni.showToast({ title: "创建成功，请手动保存密钥", icon: "none" })
      });
    } else {
      uni.showToast({ title: "密钥已创建", icon: "none" });
    }
    await loadKeys();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `创建失败：${err.message}` : "创建失败", icon: "none" });
  } finally {
    creating.value = false;
  }
}

async function revokeKey(row: UserApiKeyItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认撤销",
    content: `确认撤销密钥「${row.name || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await revokeUserApiKey(id);
        uni.showToast({ title: "密钥已撤销", icon: "none" });
        await loadKeys();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `撤销失败：${err.message}` : "撤销失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function copyCreatedSecret() {
  const secret = String(createdSecret.value || "").trim();
  if (!secret) {
    uni.showToast({ title: "暂无新创建密钥", icon: "none" });
    return;
  }
  uni.setClipboardData({
    data: secret,
    success: () => uni.showToast({ title: "密钥已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "密钥摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(keys.value.length / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
}

onShow(loadKeys);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">接口密钥</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadKeys">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">创建密钥（仅展示一次）</text>
      <input v-model="createName" placeholder="密钥名称（如：工单系统）" />
      <input v-model="createScopesText" placeholder="权限范围，逗号分隔（可空）" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="creating" @click="createKey">创建密钥</button>
        <button size="mini" @click="copyCreatedSecret">复制最新密钥</button>
      </view>
      <text class="app-subtext">最近创建密钥：{{ createdSecret ? "已生成（建议立即保存）" : "暂无" }}</text>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">密钥列表：{{ keys.length }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page>=Math.max(1, Math.ceil(keys.length / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(keys.length / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="pagedRows.length" class="app-gap-12">
        <view v-for="row in pagedRows" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || row.id }}</text>
            <text class="app-subtext">前缀：{{ row.key_prefix || "-" }}</text>
            <text class="app-subtext">权限：{{ Array.isArray(row.scopes) && row.scopes.length ? row.scopes.join(", ") : "全量" }}</text>
            <text class="app-subtext">最近使用：{{ row.last_used_at || "-" }}</text>
            <text class="app-subtext">创建时间：{{ row.created_at || "-" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.is_active ? '可用' : '已撤销'" :type="row.is_active ? 'success' : 'info'" />
            <button size="mini" :disabled="!row.is_active" :loading="actionLoading" @click="revokeKey(row)">
              {{ row.is_active ? "撤销" : "已撤销" }}
            </button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '密钥加载中...' : '暂无接口密钥'" />
    </view>
  </view>
</template>
