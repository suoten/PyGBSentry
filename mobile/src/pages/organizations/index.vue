<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  createOrganization,
  deleteOrganization,
  fetchOrganizationTree,
  updateOrganization,
  type OrgNode
} from "@/api/admin";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const tree = ref<OrgNode[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editingId = ref("");
const parentId = ref("");
const formName = ref("");
const formSortOrder = ref(0);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function flatten(nodes: OrgNode[], depth = 0, out: Array<{ id: string; label: string; node: OrgNode }> = []) {
  for (const row of nodes || []) {
    const id = String(row.id || "").trim();
    const name = String(row.name || id);
    if (id) out.push({ id, label: `${"  ".repeat(depth)}${name}`, node: row });
    if (Array.isArray(row.children) && row.children.length) flatten(row.children, depth + 1, out);
  }
  return out;
}

const flatNodes = computed(() => flatten(tree.value));
const parentOptions = computed(() => [{ id: "", label: "无（根组织）", node: null as any }, ...flatNodes.value]);
const summaryText = computed(() => {
  const count = flatten(tree.value).length;
  return `组织管理：总组织=${count}；编辑模式=${editingId.value ? "编辑" : "新增"}；上级=${parentId.value || "根组织"}`;
});
const nextStepAdvice = computed(() => {
  if (!flatten(tree.value).length) return "下一步建议：先创建根组织，再按层级补齐子组织。";
  return "下一步建议：优先维护组织层级与排序，保证设备归属清晰。";
});

function resetForm() {
  editingId.value = "";
  parentId.value = "";
  formName.value = "";
  formSortOrder.value = 0;
}

function beginCreate(targetParentId = "") {
  resetForm();
  parentId.value = targetParentId;
}

function beginEdit(row: OrgNode) {
  editingId.value = String(row.id || "");
  parentId.value = String(row.parent_id || "");
  formName.value = String(row.name || "");
  formSortOrder.value = Number(row.sort_order || 0);
}

function setParentByIndex(index: number) {
  parentId.value = String(parentOptions.value[index]?.id || "");
}

async function loadTree() {
  loading.value = true;
  try {
    const rows = await fetchOrganizationTree();
    tree.value = Array.isArray(rows) ? rows : [];
    setLoadStatus(`刷新成功：${flatten(tree.value).length} 个组织`);
  } catch (err: any) {
    tree.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "组织树加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveForm() {
  const name = String(formName.value || "").trim();
  if (!name) {
    uni.showToast({ title: "请输入组织名称", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      await updateOrganization(editingId.value, {
        name,
        parent_id: parentId.value || undefined,
        sort_order: Number(formSortOrder.value || 0)
      });
      uni.showToast({ title: "组织已更新", icon: "none" });
    } else {
      await createOrganization({
        name,
        parent_id: parentId.value || undefined,
        sort_order: Number(formSortOrder.value || 0)
      });
      uni.showToast({ title: "组织已创建", icon: "none" });
    }
    resetForm();
    await loadTree();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function removeRow(row: OrgNode) {
  const id = String(row.id || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认删除",
    content: `确认删除组织「${row.name || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteOrganization(id);
        uni.showToast({ title: "组织已删除", icon: "none" });
        await loadTree();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "组织摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadTree);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">组织管理</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadTree">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="beginCreate('')">新增根组织</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ editingId ? "编辑组织" : "新增组织" }}</text>
      <picker mode="selector" :range="parentOptions.map((x)=>x.label)" :value="Math.max(0, parentOptions.findIndex((x)=>x.id===parentId))" @change="(e:any)=>setParentByIndex(Number(e?.detail?.value || 0))">
        <view class="app-subtext">上级组织：{{ parentOptions.find((x)=>x.id===parentId)?.label || "无（根组织）" }}</view>
      </picker>
      <input v-model="formName" placeholder="组织名称" />
      <input v-model="formSortOrder" type="number" placeholder="排序（数字）" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveForm">{{ editingId ? "更新组织" : "创建组织" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="flatNodes.length" class="app-gap-12">
        <view v-for="row in flatNodes" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.label }}</text>
            <text class="app-subtext">组织ID：{{ row.id }}</text>
          </view>
          <view class="app-row">
            <button size="mini" @click="beginCreate(row.id)">加子组织</button>
            <button size="mini" @click="beginEdit(row.node)">
              编辑
            </button>
            <button size="mini" :loading="actionLoading" @click="removeRow(row.node)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '组织树加载中...' : '暂无组织'" />
    </view>
  </view>
</template>
