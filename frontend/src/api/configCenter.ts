import api from '@/utils/http'

export type DraftResponse = {
  draft_id: string
  base_revision: number
  status: string
  modules: Record<string, unknown>
  updated_at: string
}

export type ValidateResponse = {
  valid: boolean
  errors: Array<{ field: string; message: string }>
  warnings: Array<{ field: string; message: string }>
  hints: string[]
}

export const getCurrentDraft = async (): Promise<DraftResponse> => {
  const res = await api.get('/api/v1/config-center/drafts/current')
  return res.data
}

export const updateDraftModule = async (
  draftId: string,
  moduleName: string,
  moduleData: Record<string, unknown>
): Promise<DraftResponse> => {
  // FIXED: A-13 原来用 { payload } shorthand 导致请求体为 { payload: moduleData }
  // 后端 UpdateDraftModuleRequest schema 期望 { payload: dict, operator?: string }
  // 显式构造请求体，与后端 schema 字段名对齐，避免参数名混淆
  const res = await api.put(`/api/v1/config-center/drafts/${draftId}/modules/${moduleName}`, {
    payload: moduleData
  })
  return res.data
}

export const validateDraft = async (draftId: string): Promise<ValidateResponse> => {
  const res = await api.post(`/api/v1/config-center/drafts/${draftId}/validate`)
  return res.data
}
