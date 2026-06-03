<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { createRole, deleteRole, fetchRoles, updateRole, type RoleItem } from "@/api/admin";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const roles = ref<RoleItem[]>([]);
const page = ref(1);
const pageSize = ref(10);
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editingId = ref("");
const editingIsSystem = ref(false);
const form = ref({
  code: "",
  name: "",
  description: "",
  permissionText: ""
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function parsePermissionCodes(text: string) {
  const map = new Set<string>();
  const parts = String(text || "")
    .split(/[\n,;，；\s]+/g)
    .map((x) => x.trim())
    .filter(Boolean);
  for (const code of parts) map.add(code);
  return Array.from(map.values());
}

const pagedRoles = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return roles.value.slice(start, start + pageSize.value);
});

const summaryText = computed(() => {
  const total = roles.value.length;
  const systemCount = roles.value.filter((x) => x.is_system).length;
  return `角色管理：总角色=${total}；系统角色=${systemCount}；编辑模式=${editingId.value ? "编辑" : "新增"}`;
});

const nextStepAdvice = computed(() => {
  if (!roles.value.length) return "下一步建议：先创建业务角色并配置权限码。";
  return "下一步建议：优先梳理高权限角色的权限码，保持最小权限原则。";
});

function resetForm() {
  editingId.value = "";
  editingIsSystem.value = false;
  form.value = {
    code: "",
    name: "",
    description: "",
    permissionText: ""
  };
}

function beginCreate() {
  resetForm();
}

function beginEdit(row: RoleItem) {
  editingId.value = String(row.id || "");
  editingIsSystem.value = !!row.is_system;
  form.value = {
    code: String(row.code || ""),
    name: String(row.name || ""),
    description: String(row.description || ""),
    permissionText: Array.isArray(row.permission_codes) ? row.permission_codes.join("\n") : ""
  };
}

function canDelete(row: RoleItem) {
  return !row.is_system;
}

async function loadRoles() {
  loading.value = true;
  try {
    const list = await fetchRoles();
    roles.value = Array.isArray(list) ? list : [];
    setLoadStatus(`刷新成功：${roles.value.length} 个角色`);
  } catch (err: any) {
    roles.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "角色列表加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveRoleForm() {
  const code = String(form.value.code || "").trim();
  const name = String(form.value.name || "").trim();
  if (!code) {
    uni.showToast({ title: "请输入角色编码", icon: "none" });
    return;
  }
  if (!name) {
    uni.showToast({ title: "请输入角色名称", icon: "none" });
    return;
  }
  if (editingIsSystem.value && editingId.value) {
    const current = roles.value.find((x) => String(x.id) === editingId.value);
    if (current && String(current.code || "") !== code) {
      uni.showToast({ title: "系统角色不允许修改编码", icon: "none" });
      return;
    }
  }
  saving.value = true;
  try {
    const payload = {
      code,
      name,
      description: String(form.value.description || "").trim(),
      permission_codes: parsePermissionCodes(form.value.permissionText)
    };
    if (editingId.value) {
      await updateRole(editingId.value, payload);
      uni.showToast({ title: "角色已更新", icon: "none" });
    } else {
      await createRole(payload);
      uni.showToast({ title: "角色已创建", icon: "none" });
    }
    resetForm();
    await loadRoles();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function removeRole(row: RoleItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  if (!canDelete(row)) {
    uni.showToast({ title: "系统角色不允许删除", icon: "none" });
    return;
  }
  uni.showModal({
    title: "确认删除",
    content: `确认删除角色「${row.name || row.code || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteRole(id);
        uni.showToast({ title: "角色已删除", icon: "none" });
        await loadRoles();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function formatPermissionCodes(codes?: string[]) {
  if (!Array.isArray(codes) || !codes.length) return "无";
  if (codes.includes("*")) return "全部权限(*)";
  return codes.join("、");
}

function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
}

function nextPage() {
  const maxPage = Math.max(1, Math.ceil(roles.value.length / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "角色摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadRoles);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">角色管理</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadRoles">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="beginCreate">新增角色</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
      <text class="app-subtext">说明：系统角色可编辑名称与权限，不允许删除。</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ editingId ? "编辑角色" : "新增角色" }}</text>
      <input v-model="form.code" :disabled="editingIsSystem && !!editingId" placeholder="角色编码（如 custom_operator）" />
      <input v-model="form.name" placeholder="角色名称" />
      <input v-model="form.description" placeholder="描述（可空）" />
      <textarea v-model="form.permissionText" class="app-textarea" placeholder="权限码（可按换行/逗号分隔），例如：dashboard.view, alarms.handle" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveRoleForm">{{ editingId ? "更新角色" : "创建角色" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">角色列表：{{ roles.length }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page>=Math.max(1, Math.ceil(roles.length / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(roles.length / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="pagedRoles.length" class="app-gap-12">
        <view v-for="row in pagedRoles" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || "-" }}（{{ row.code || "-" }}）</text>
            <text class="app-subtext">权限：{{ formatPermissionCodes(row.permission_codes) }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.is_system ? '系统角色' : '自定义角色'" :type="row.is_system ? 'warning' : 'success'" />
            <button size="mini" @click="beginEdit(row)">编辑</button>
            <button size="mini" :loading="actionLoading" :disabled="!canDelete(row)" @click="removeRole(row)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '角色加载中...' : '暂无角色'" />
    </view>
  </view>
</template>
