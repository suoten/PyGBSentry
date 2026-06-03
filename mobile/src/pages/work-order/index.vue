// FIXED-P3: N-14 工单页面国际化
<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  createWorkOrder,
  deleteWorkOrder,
  listWorkOrders,
  type WorkOrderItem,
  type WorkOrderStatus,
  updateWorkOrder,
  updateWorkOrderStatus
} from "@/api/workOrder";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";

const { t } = useI18n();

const loading = ref(false);
const statusLoadingId = ref("");
const deleteLoadingId = ref("");
const statusFilter = ref<"" | WorkOrderStatus>("");
const workOrders = ref<WorkOrderItem[]>([]);
const loadMessage = ref(t('workOrder.notRefreshed'));
const loadAt = ref("");
const createSubmitting = ref(false);
const createPanelVisible = ref(false);
const editSubmitting = ref(false);
const editingId = ref("");
const categoryPickerIndex = ref(2);
const priorityPickerIndex = ref(1);
const editCategoryPickerIndex = ref(2);
const editPriorityPickerIndex = ref(1);

const categoryOptions = ["tech_support", "billing", "other"] as const;
const categoryLabels = computed(() => [t('workOrder.categoryTechSupport'), t('workOrder.categoryBilling'), t('workOrder.categoryOther')]);
const priorityOptions = ["low", "medium", "high"] as const;
const priorityLabels = computed(() => [t('workOrder.priorityLow'), t('workOrder.priorityMedium'), t('workOrder.priorityHigh')]);

const createForm = ref({
  title: "",
  alarm_id: "",
  description: "",
  category: "other" as "tech_support" | "billing" | "other",
  priority: "medium" as "low" | "medium" | "high",
  assignee_user_id: ""
});

const editForm = ref({
  id: "",
  title: "",
  alarm_id: "",
  description: "",
  category: "other" as "tech_support" | "billing" | "other",
  priority: "medium" as "low" | "medium" | "high",
  assignee_user_id: ""
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function statusLabel(status: WorkOrderStatus) {
  if (status === "in_progress") return t('workOrder.statusInProgress');
  if (status === "resolved") return t('workOrder.statusResolved');
  if (status === "closed") return t('workOrder.statusClosed');
  return t('workOrder.statusOpen');
}

function statusTagType(status: WorkOrderStatus): "danger" | "warning" | "success" | "info" {
  if (status === "in_progress") return "warning";
  if (status === "resolved") return "success";
  if (status === "closed") return "info";
  return "danger";
}

function categoryLabel(category: WorkOrderItem["category"] | string | undefined) {
  if (category === "tech_support") return t('workOrder.categoryTechSupport');
  if (category === "billing") return t('workOrder.categoryBilling');
  return t('workOrder.categoryOther');
}

function priorityLabel(priority: WorkOrderItem["priority"] | string | undefined) {
  if (priority === "high") return t('workOrder.priorityHigh');
  if (priority === "low") return t('workOrder.priorityLow');
  return t('workOrder.priorityMedium');
}

function formatDate(value?: string) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("zh-CN", { hour12: false });
}

const filteredCountText = computed(() => {
  return t('workOrder.filteredCount', { count: workOrders.value.length, filter: statusFilter.value ? statusLabel(statusFilter.value) : t('workOrder.all') });
});

const statusDistributionText = computed(() => {
  let open = 0;
  let inProgress = 0;
  let resolved = 0;
  let closed = 0;
  for (const row of workOrders.value) {
    if (row.status === "in_progress") inProgress += 1;
    else if (row.status === "resolved") resolved += 1;
    else if (row.status === "closed") closed += 1;
    else open += 1;
  }
  return t('workOrder.statusDistribution', { open, inProgress, resolved, closed });
});

const nextStepAdviceText = computed(() => {
  const pending = workOrders.value.filter((x) => x.status === "open").length;
  const processing = workOrders.value.filter((x) => x.status === "in_progress").length;
  if (pending > 0) return t('workOrder.advicePending');
  if (processing > 0) return t('workOrder.adviceProcessing');
  return t('workOrder.adviceLowPressure');
});

async function loadWorkOrders() {
  loading.value = true;
  try {
    const rows = (await listWorkOrders(statusFilter.value || undefined)) || [];
    workOrders.value = [...rows].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
    setLoadStatus(t('workOrder.refreshSuccess', { count: workOrders.value.length }));
  } catch (err: any) {
    setLoadStatus(err?.message ? t('workOrder.refreshFailedWithMsg', { msg: err.message }) : t('workOrder.refreshFailed'));
    uni.showToast({ title: t('workOrder.loadFailed'), icon: "none" });
  } finally {
    loading.value = false;
  }
}

function copyWorkOrderListSummary() {
  const text = [filteredCountText.value, statusDistributionText.value, nextStepAdviceText.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: t('workOrder.summaryCopied'), icon: "none" }),
    fail: () => uni.showToast({ title: t('workOrder.copyFailed'), icon: "none" })
  });
}

function resetCreateForm() {
  createForm.value = {
    title: "",
    alarm_id: "",
    description: "",
    category: "other",
    priority: "medium",
    assignee_user_id: ""
  };
  categoryPickerIndex.value = 2;
  priorityPickerIndex.value = 1;
}

function openCreatePanel() {
  createPanelVisible.value = true;
  resetCreateForm();
}

function closeCreatePanel() {
  createPanelVisible.value = false;
}

async function submitCreate() {
  const title = String(createForm.value.title || "").trim();
  const desc = String(createForm.value.description || "").trim();
  if (title.length < 2) {
    uni.showToast({ title: t('workOrder.titleMinLength'), icon: "none" });
    return;
  }
  if (desc.length < 4) {
    uni.showToast({ title: t('workOrder.descMinLength'), icon: "none" });
    return;
  }
  createSubmitting.value = true;
  try {
    await createWorkOrder({
      title,
      description: desc,
      alarm_id: String(createForm.value.alarm_id || "").trim() || undefined,
      category: createForm.value.category,
      priority: createForm.value.priority,
      assignee_user_id: String(createForm.value.assignee_user_id || "").trim() || undefined
    });
    uni.showToast({ title: t('workOrder.createSuccess'), icon: "none" });
    closeCreatePanel();
    await loadWorkOrders();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? t('workOrder.createFailedWithMsg', { msg: err.message }) : t('workOrder.createFailed'), icon: "none" });
  } finally {
    createSubmitting.value = false;
  }
}

function openEdit(item: WorkOrderItem) {
  if (!canEdit(item)) {
    uni.showToast({ title: t('workOrder.cannotEdit'), icon: "none" });
    return;
  }
  editingId.value = item.id;
  editForm.value = {
    id: item.id,
    title: String(item.title || ""),
    alarm_id: String(item.alarm_id || ""),
    description: String(item.description || ""),
    category: (item.category || "other") as "tech_support" | "billing" | "other",
    priority: (item.priority || "medium") as "low" | "medium" | "high",
    assignee_user_id: String(item.assignee_user_id || "")
  };
  editCategoryPickerIndex.value = Math.max(0, categoryOptions.indexOf(editForm.value.category));
  editPriorityPickerIndex.value = Math.max(0, priorityOptions.indexOf(editForm.value.priority));
}

function closeEdit() {
  editingId.value = "";
}

async function submitEdit() {
  const id = String(editForm.value.id || "").trim();
  if (!id) return;
  const title = String(editForm.value.title || "").trim();
  const desc = String(editForm.value.description || "").trim();
  if (title.length < 2) {
    uni.showToast({ title: t('workOrder.titleMinLength'), icon: "none" });
    return;
  }
  if (desc.length < 4) {
    uni.showToast({ title: t('workOrder.descMinLength'), icon: "none" });
    return;
  }
  editSubmitting.value = true;
  try {
    await updateWorkOrder(id, {
      title,
      description: desc,
      alarm_id: String(editForm.value.alarm_id || "").trim() || undefined,
      category: editForm.value.category,
      priority: editForm.value.priority,
      assignee_user_id: String(editForm.value.assignee_user_id || "").trim() || undefined
    });
    uni.showToast({ title: t('workOrder.saveSuccess'), icon: "none" });
    closeEdit();
    await loadWorkOrders();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? t('workOrder.saveFailedWithMsg', { msg: err.message }) : t('workOrder.saveFailed'), icon: "none" });
  } finally {
    editSubmitting.value = false;
  }
}

async function onStatusFilterChange(index: number) {
  statusFilter.value = index === 1 ? "open" : index === 2 ? "in_progress" : index === 3 ? "resolved" : index === 4 ? "closed" : "";
  await loadWorkOrders();
}

function encode(v: unknown) {
  return encodeURIComponent(String(v || ""));
}

function openDetail(item: WorkOrderItem) {
  const url = [
    "/pages/work-order-detail/index",
    `?id=${encode(item.id)}`,
    `&title=${encode(item.title)}`,
    `&status=${encode(item.status)}`,
    `&priority=${encode(item.priority || "medium")}`,
    `&assignee=${encode(item.assignee_user_id || t('workOrder.notAssigned'))}`,
    `&alarmId=${encode(item.alarm_id || "")}`,
    `&createdAt=${encode(item.created_at || "")}`,
    `&description=${encode(item.description || "")}`
  ].join("");
  uni.navigateTo({ url });
}

async function quickMove(item: WorkOrderItem, next: WorkOrderStatus) {
  if (!item.id || item.status === next) return;
  if (!canSwitchStatus(item, next)) return;
  statusLoadingId.value = `${item.id}:${next}`;
  try {
    const updated = await updateWorkOrderStatus(item.id, next);
    item.status = updated.status;
    uni.showToast({ title: t('workOrder.updatedTo', { status: statusLabel(updated.status) }), icon: "none" });
    setLoadStatus(t('workOrder.statusUpdated', { id: item.id, status: statusLabel(updated.status) }));
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : t('workOrder.retryLater');
    setLoadStatus(t('workOrder.statusUpdateFailedWithMsg', { reason }));
    uni.showToast({ title: t('workOrder.statusUpdateFailed'), icon: "none" });
  } finally {
    statusLoadingId.value = "";
  }
}

function canEdit(item: WorkOrderItem) {
  return ["open", "in_progress", "resolved"].includes(String(item.status || ""));
}

function canDelete(item: WorkOrderItem) {
  return String(item.status || "") === "closed";
}

function canSwitchStatus(item: WorkOrderItem, next: WorkOrderStatus) {
  const current = String(item.status || "open") as WorkOrderStatus;
  if (current === next) return false;
  const allowed: Record<WorkOrderStatus, WorkOrderStatus[]> = {
    open: ["in_progress", "resolved", "closed"],
    in_progress: ["open", "resolved", "closed"],
    resolved: ["in_progress", "closed"],
    closed: []
  };
  return allowed[current].includes(next);
}

function quickActions(item: WorkOrderItem): WorkOrderStatus[] {
  const current = item.status;
  if (current === "open") return ["in_progress", "resolved", "closed"];
  if (current === "in_progress") return ["resolved", "closed"];
  if (current === "resolved") return ["in_progress", "closed"];
  return [];
}

async function removeOrder(item: WorkOrderItem) {
  if (!canDelete(item)) {
    uni.showToast({ title: t('workOrder.onlyClosedCanDelete'), icon: "none" });
    return;
  }
  const confirmRes = await uni.showModal({
    title: t('workOrder.deleteConfirmTitle'),
    content: t('workOrder.deleteConfirmContent', { id: item.id }),
    confirmText: t('workOrder.confirmDelete'),
    cancelText: t('workOrder.confirmCancel')
  });
  if (!confirmRes.confirm) return;
  deleteLoadingId.value = item.id;
  try {
    await deleteWorkOrder(item.id);
    uni.showToast({ title: t('workOrder.deleteSuccess'), icon: "none" });
    await loadWorkOrders();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? t('workOrder.deleteFailedWithMsg', { msg: err.message }) : t('workOrder.deleteFailed'), icon: "none" });
  } finally {
    deleteLoadingId.value = "";
  }
}

onShow(loadWorkOrders);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">{{ t('workOrder.title') }}</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ filteredCountText }}</text>
        <view class="app-row">
          <button size="mini" :loading="loading" @click="loadWorkOrders">{{ t('workOrder.refresh') }}</button>
          <button size="mini" type="primary" @click="openCreatePanel">{{ t('workOrder.createWorkOrder') }}</button>
        </view>
      </view>
      <picker
        mode="selector"
        :range="[t('workOrder.allStatus'), t('workOrder.statusOpen'), t('workOrder.statusInProgress'), t('workOrder.statusResolved'), t('workOrder.statusClosed')]"
        :value="statusFilter === '' ? 0 : statusFilter === 'open' ? 1 : statusFilter === 'in_progress' ? 2 : statusFilter === 'resolved' ? 3 : 4"
        @change="(e:any) => onStatusFilterChange(Number(e?.detail?.value || 0))"
      >
        <view class="app-subtext">{{ t('workOrder.statusFilter') }}：{{ statusFilter ? statusLabel(statusFilter) : t('workOrder.all') }}</view>
      </picker>
      <text class="app-subtext">{{ statusDistributionText }}</text>
      <text class="app-subtext">{{ nextStepAdviceText }}</text>
      <text class="app-subtext">{{ t('workOrder.refreshStatus') }}：{{ loadMessage || "-" }}</text>
      <text v-if="loadAt" class="app-subtext">{{ t('workOrder.statusTime') }}：{{ loadAt }}</text>
      <view class="app-row">
        <button size="mini" @click="copyWorkOrderListSummary">{{ t('workOrder.copySummary') }}</button>
      </view>
    </view>

    <view v-if="createPanelVisible" class="app-card app-gap-12">
      <text class="app-subtext">{{ t('workOrder.createTitle') }}</text>
      <input v-model="createForm.title" class="app-input" :placeholder="t('workOrder.titlePlaceholder')" />
      <input v-model="createForm.alarm_id" class="app-input" :placeholder="t('workOrder.alarmIdPlaceholder')" />
      <textarea v-model="createForm.description" class="app-input" auto-height :maxlength="-1" :placeholder="t('workOrder.descriptionPlaceholder')" />
      <picker mode="selector" :range="categoryLabels" :value="categoryPickerIndex" @change="(e:any) => { categoryPickerIndex = Number(e?.detail?.value || 0); createForm.category = categoryOptions[categoryPickerIndex] }">
        <view class="app-subtext">{{ t('workOrder.categoryLabel') }}：{{ categoryLabel(createForm.category) }}</view>
      </picker>
      <picker mode="selector" :range="priorityLabels" :value="priorityPickerIndex" @change="(e:any) => { priorityPickerIndex = Number(e?.detail?.value || 0); createForm.priority = priorityOptions[priorityPickerIndex] }">
        <view class="app-subtext">{{ t('workOrder.priorityLabel') }}：{{ priorityLabel(createForm.priority) }}</view>
      </picker>
      <input v-model="createForm.assignee_user_id" class="app-input" :placeholder="t('workOrder.assigneePlaceholder')" />
      <view class="app-row">
        <button size="mini" @click="closeCreatePanel">{{ t('workOrder.cancel') }}</button>
        <button size="mini" type="primary" :loading="createSubmitting" @click="submitCreate">{{ t('workOrder.submitCreate') }}</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="workOrders.length" class="app-gap-12">
        <view v-for="row in workOrders" :key="row.id" class="app-card app-gap-12">
          <view>
            <text class="app-subtext">{{ row.title || row.id }}</text>
            <text class="app-subtext">{{ t('workOrder.idLabel') }}：{{ row.id }}</text>
            <text class="app-subtext">{{ t('workOrder.statusLabel') }}：{{ statusLabel(row.status) }} / {{ t('workOrder.priorityLabel') }}：{{ priorityLabel(row.priority) }}</text>
            <text class="app-subtext">{{ t('workOrder.categoryLabel') }}：{{ categoryLabel(row.category) }} / {{ t('workOrder.assigneeLabel') }}：{{ row.assignee_user_id || t('workOrder.notAssigned') }}</text>
            <text class="app-subtext">{{ t('workOrder.alarmLabel') }}：{{ row.alarm_id || "-" }}</text>
            <text class="app-subtext">{{ t('workOrder.createTime') }}：{{ formatDate(row.created_at) }}</text>
          </view>
          <view class="app-row">
            <AppStatusTag :text="statusLabel(row.status)" :type="statusTagType(row.status)" />
            <button size="mini" @click="openDetail(row)">{{ t('workOrder.detail') }}</button>
            <button size="mini" :disabled="!canEdit(row)" @click="openEdit(row)">{{ t('workOrder.edit') }}</button>
            <button
              v-for="act in quickActions(row)"
              :key="`${row.id}-${act}`"
              size="mini"
              :loading="statusLoadingId === `${row.id}:${act}`"
              @click="quickMove(row, act)"
            >
              {{ statusLabel(act) }}
            </button>
            <button size="mini" type="warn" :disabled="!canDelete(row)" :loading="deleteLoadingId === row.id" @click="removeOrder(row)">{{ t('workOrder.delete') }}</button>
          </view>
          <view v-if="editingId === row.id" class="app-card app-gap-12">
            <text class="app-subtext">{{ t('workOrder.editTitle') }}</text>
            <input v-model="editForm.title" class="app-input" :placeholder="t('workOrder.editTitlePlaceholder')" />
            <input v-model="editForm.alarm_id" class="app-input" :placeholder="t('workOrder.editAlarmIdPlaceholder')" />
            <textarea v-model="editForm.description" class="app-input" auto-height :maxlength="-1" :placeholder="t('workOrder.editDescriptionPlaceholder')" />
            <picker mode="selector" :range="categoryLabels" :value="editCategoryPickerIndex" @change="(e:any) => { editCategoryPickerIndex = Number(e?.detail?.value || 0); editForm.category = categoryOptions[editCategoryPickerIndex] }">
              <view class="app-subtext">{{ t('workOrder.categoryLabel') }}：{{ categoryLabel(editForm.category) }}</view>
            </picker>
            <picker mode="selector" :range="priorityLabels" :value="editPriorityPickerIndex" @change="(e:any) => { editPriorityPickerIndex = Number(e?.detail?.value || 0); editForm.priority = priorityOptions[editPriorityPickerIndex] }">
              <view class="app-subtext">{{ t('workOrder.priorityLabel') }}：{{ priorityLabel(editForm.priority) }}</view>
            </picker>
            <input v-model="editForm.assignee_user_id" class="app-input" :placeholder="t('workOrder.assigneePlaceholder')" />
            <view class="app-row">
              <button size="mini" @click="closeEdit">{{ t('workOrder.cancel') }}</button>
              <button size="mini" type="primary" :loading="editSubmitting" @click="submitEdit">{{ t('workOrder.saveChanges') }}</button>
            </view>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? t('workOrder.loading') : t('workOrder.noRecords')" />
    </view>
  </view>
</template>
