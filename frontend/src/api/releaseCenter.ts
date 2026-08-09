import api from '@/utils/http'

export type DiffItem = {
  module: string
  path: string
  before: string | number | boolean | null
  after: string | number | boolean | null
  risk_level: string
}

export type DiffResponse = {
  from_revision: number
  to_draft: string
  changes: DiffItem[]
}

export type PublishResponse = {
  publish_id: string
  revision: number
  status: string
  published_at: string
}

export const getDraftDiff = async (draftId: string): Promise<DiffResponse> => {
  const res = await api.get(`/api/v1/release-center/drafts/${draftId}/diff`)
  return res.data
}

export const publishDraft = async (draftId: string, confirmToken: string, publishNote?: string): Promise<PublishResponse> => {
  const res = await api.post('/api/v1/release-center/publish', {
    draft_id: draftId,
    confirm_token: confirmToken,
    publish_note: publishNote || null
  })
  return res.data
}

// FIXED: rollback 返回类型与后端 RollbackResponse 对齐
export type RollbackResponse = {
  status: string
  target_revision: number
}

export const rollbackRevision = async (targetRevision: number, reason?: string): Promise<RollbackResponse> => {
  const res = await api.post('/api/v1/release-center/rollback', {
    target_revision: targetRevision,
    reason: reason || null
  })
  return res.data
}
