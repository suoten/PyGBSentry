import { request } from "@/utils/request";

export interface DiffItem {
  module: string;
  path: string;
  before: string | number | boolean | null;
  after: string | number | boolean | null;
  risk_level: string;
}

export interface DraftDiffResult {
  from_revision: number;
  to_draft: string;
  changes: DiffItem[];
}

export interface PublishResult {
  publish_id: string;
  revision: number;
  status: string;
  published_at: string;
}

export function fetchDraftDiff(draftId: string) {
  return request<DraftDiffResult>({
    url: `/api/v1/release-center/drafts/${encodeURIComponent(draftId)}/diff`
  });
}

export function publishDraft(draftId: string, publishNote?: string, confirmToken?: string) {
  return request<PublishResult>({
    url: "/api/v1/release-center/publish",
    method: "POST",
    data: {
      draft_id: draftId,
      confirm_token: confirmToken,  // FIXED: P1 移除硬编码confirm_token回退，必须由调用方传入
      publish_note: publishNote || undefined
    }
  });
}

// FIXED: rollback 返回类型与后端 RollbackResponse 对齐
export function rollbackRevision(targetRevision: number, reason?: string) {
  return request<{ status: string; target_revision: number }>({
    url: "/api/v1/release-center/rollback",
    method: "POST",
    data: {
      target_revision: targetRevision,
      reason: reason || undefined
    }
  });
}
