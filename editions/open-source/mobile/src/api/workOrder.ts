import { request } from "@/utils/request";

export interface WorkOrderCreatePayload {
  alarm_id?: string;
  title: string;
  description?: string;
  category?: "tech_support" | "billing" | "other";
  priority?: "low" | "medium" | "high";
  assignee_user_id?: string;
}

export type WorkOrderStatus = "open" | "in_progress" | "resolved" | "closed";

export interface WorkOrderItem {
  id: string;
  alarm_id?: string;
  title: string;
  description?: string;
  category?: "tech_support" | "billing" | "other";
  status: WorkOrderStatus;
  priority?: "low" | "medium" | "high";
  assignee_user_id?: string;
  created_by_user_id?: string;
  created_at?: string;
}

export function createWorkOrder(payload: WorkOrderCreatePayload) {
  return request<WorkOrderItem>({
    url: "/api/v1/work-orders",
    method: "POST",
    data: payload
  });
}

export function listWorkOrders(status?: WorkOrderStatus) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<WorkOrderItem[]>({
    url: `/api/v1/work-orders${q}`
  });
}

export function updateWorkOrderStatus(workOrderId: string, status: WorkOrderStatus) {
  return request<WorkOrderItem>({
    url: `/api/v1/work-orders/${encodeURIComponent(workOrderId)}`,
    method: "PUT",
    data: { status }
  });
}

export function updateWorkOrder(workOrderId: string, payload: Partial<WorkOrderCreatePayload & { status: WorkOrderStatus }>) {
  return request<WorkOrderItem>({
    url: `/api/v1/work-orders/${encodeURIComponent(workOrderId)}`,
    method: "PUT",
    data: payload
  });
}

export function deleteWorkOrder(workOrderId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/work-orders/${encodeURIComponent(workOrderId)}`,
    method: "DELETE"
  });
}
