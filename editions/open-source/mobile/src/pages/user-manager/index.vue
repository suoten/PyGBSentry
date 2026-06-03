<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { createUser, deleteUser, fetchMe, fetchRoles, fetchUsers, updateUser, type UserItem, type UserRoleItem } from "@/api/admin";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const users = ref<UserItem[]>([]);
const roles = ref<UserRoleItem[]>([]);
const currentUserId = ref("");
const page = ref(1);
const pageSize = ref(10);
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editingId = ref("");
const form = ref({
  username: "",
  password: "",
  full_name: "",
  is_superuser: false,
  is_active: true,
  tenant_id: "default",
  role: "viewer"
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const roleOptions = computed(() => {
  const base = [
    { code: "viewer", name: "查看者" },
    { code: "operator", name: "操作员" },
    { code: "admin", name: "管理员" },
    { code: "owner", name: "所有者" }
  ];
  const map = new Map<string, { code: string; name: string }>();
  for (const item of base) map.set(item.code, item);
  for (const item of roles.value || []) {
    const code = String(item.code || "").trim();
    if (!code) continue;
    map.set(code, { code, name: String(item.name || code) });
  }
  return Array.from(map.values());
});

const pagedUsers = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return users.value.slice(start, start + pageSize.value);
});

const summaryText = computed(() => {
  return `用户管理：总用户=${users.value.length}；活跃=${users.value.filter((x) => x.is_active).length}；超级管理员=${users.value.filter((x) => x.is_superuser).length}；编辑模式=${editingId.value ? "编辑" : "新增"}`;
});

const nextStepAdvice = computed(() => {
  if (!users.value.length) return "下一步建议：先创建首批账号并分配角色。";
  return "下一步建议：定期检查停用账号与高权限账号，保持最小权限。";
});

function resetForm() {
  editingId.value = "";
  form.value = {
    username: "",
    password: "",
    full_name: "",
    is_superuser: false,
    is_active: true,
    tenant_id: "default",
    role: "viewer"
  };
}

function beginEdit(row: UserItem) {
  editingId.value = String(row.id || "");
  form.value = {
    username: String(row.username || ""),
    password: "",
    full_name: String(row.full_name || ""),
    is_superuser: !!row.is_superuser,
    is_active: row.is_active !== false,
    tenant_id: String(row.tenant_id || "default"),
    role: String(row.role || "viewer")
  };
}

function canDelete(row: UserItem) {
  const id = String(row.id || "");
  if (id && id === currentUserId.value) return false;
  if (row.is_superuser) {
    const superCount = users.value.filter((x) => x.is_superuser).length;
    if (superCount <= 1) return false;
  }
  return true;
}

async function loadData() {
  loading.value = true;
  try {
    const [me, list, roleRows] = await Promise.all([fetchMe(), fetchUsers(0, 200), fetchRoles()]);
    currentUserId.value = String(me?.id || "");
    users.value = Array.isArray(list) ? list : [];
    roles.value = Array.isArray(roleRows) ? roleRows : [];
    setLoadStatus(`刷新成功：${users.value.length} 个用户`);
  } catch (err: any) {
    users.value = [];
    roles.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "用户列表加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveUserForm() {
  const username = String(form.value.username || "").trim();
  const role = String(form.value.role || "").trim();
  const tenant = String(form.value.tenant_id || "").trim() || "default";
  if (!username) {
    uni.showToast({ title: "请输入用户名", icon: "none" });
    return;
  }
  if (!role) {
    uni.showToast({ title: "请选择角色", icon: "none" });
    return;
  }
  if (!editingId.value) {
    const password = String(form.value.password || "");
    if (!password || password.length < 6) {
      uni.showToast({ title: "请输入至少6位密码", icon: "none" });
      return;
    }
  }
  if (editingId.value && editingId.value === currentUserId.value && !form.value.is_active) {
    uni.showToast({ title: "不能停用当前登录用户", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      await updateUser(editingId.value, {
        full_name: String(form.value.full_name || "").trim() || null,
        is_active: !!form.value.is_active,
        is_superuser: !!form.value.is_superuser,
        tenant_id: tenant,
        role
      });
      uni.showToast({ title: "用户已更新", icon: "none" });
    } else {
      await createUser({
        username,
        password: String(form.value.password || ""),
        full_name: String(form.value.full_name || "").trim() || undefined,
        is_superuser: !!form.value.is_superuser,
        tenant_id: tenant,
        role
      });
      uni.showToast({ title: "用户已创建", icon: "none" });
    }
    resetForm();
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function removeUserRow(row: UserItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  if (!canDelete(row)) {
    uni.showToast({ title: "当前用户不允许删除", icon: "none" });
    return;
  }
  uni.showModal({
    title: "确认删除",
    content: `确认删除用户「${row.username}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteUser(id);
        uni.showToast({ title: "用户已删除", icon: "none" });
        await loadData();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(users.value.length / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "用户摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">用户管理</view>

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
      <text class="app-subtext">{{ editingId ? "编辑用户" : "新增用户" }}</text>
      <input v-model="form.username" :disabled="!!editingId" placeholder="用户名" />
      <input v-if="!editingId" v-model="form.password" password placeholder="密码（至少6位）" />
      <input v-model="form.full_name" placeholder="姓名（可空）" />
      <input v-model="form.tenant_id" placeholder="租户（默认 default）" />
      <picker mode="selector" :range="roleOptions.map((x)=>`${x.name}(${x.code})`)" :value="Math.max(0, roleOptions.findIndex((x)=>x.code===form.role))" @change="(e:any)=>{ const i=Number(e?.detail?.value||0); form.role = roleOptions[i]?.code || 'viewer'; }">
        <view class="app-subtext">角色：{{ roleOptions.find((x)=>x.code===form.role)?.name || form.role }}</view>
      </picker>
      <view class="app-row">
        <label class="app-subtext"><checkbox :checked="form.is_superuser" @click="form.is_superuser=!form.is_superuser" /> 超级管理员</label>
        <label class="app-subtext"><checkbox :checked="form.is_active" @click="form.is_active=!form.is_active" /> 账号启用</label>
      </view>
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveUserForm">{{ editingId ? "更新用户" : "创建用户" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">用户列表：{{ users.length }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page>=Math.max(1, Math.ceil(users.length / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(users.length / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="pagedUsers.length" class="app-gap-12">
        <view v-for="row in pagedUsers" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.username }}（{{ row.full_name || "-" }}）</text>
            <text class="app-subtext">租户：{{ row.tenant_id || "-" }}；角色：{{ row.role || "-" }}</text>
            <text class="app-subtext">账号：{{ row.is_superuser ? "超级管理员" : "普通用户" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.is_active ? '正常' : '停用'" :type="row.is_active ? 'success' : 'warning'" />
            <button size="mini" @click="beginEdit(row)">编辑</button>
            <button size="mini" :loading="actionLoading" :disabled="!canDelete(row)" @click="removeUserRow(row)">
              删除
            </button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '用户加载中...' : '暂无用户'" />
    </view>
  </view>
</template>
