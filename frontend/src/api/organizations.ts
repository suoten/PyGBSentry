import api from '@/utils/http'

export type OrgNode = {
  id: string
  name: string
  parent_id: string | null
  tenant_id?: string
  sort_order?: number
  children: OrgNode[]
}

export type OrgItem = {
  id: string
  name: string
  parent_id: string | null
  tenant_id?: string
  sort_order?: number
}

export const getOrganizationTree = async (): Promise<OrgNode[]> => {
  const res = await api.get<OrgNode[]>('/api/v1/organizations/tree')
  return Array.isArray(res.data) ? res.data : []
}

export const listOrganizations = async (parentId?: string): Promise<OrgItem[]> => {
  const params = parentId != null ? { parent_id: parentId } : {}
  const res = await api.get<OrgItem[]>('/api/v1/organizations', { params })
  return Array.isArray(res.data) ? res.data : []
}

export const createOrganization = async (payload: { name: string; parent_id?: string; sort_order?: number }) => {
  const res = await api.post('/api/v1/organizations', payload)
  return res.data
}

export const updateOrganization = async (id: string, payload: { name?: string; parent_id?: string; sort_order?: number }) => {
  await api.put(`/api/v1/organizations/${id}`, payload)
}

export const deleteOrganization = async (id: string) => {
  await api.delete(`/api/v1/organizations/${id}`)
}

/** 将组织树压平为 { id, label } 列表，用于下拉选项（label 带缩进） */
export function flattenOrgTree(nodes: OrgNode[], level = 0): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = []
  const indent = '  '.repeat(level)  // FIXED-P3: W-28 full-width space→regular spaces
  for (const n of nodes) {
    out.push({ id: n.id, label: indent + n.name })
    if (n.children?.length) out.push(...flattenOrgTree(n.children, level + 1))
  }
  return out
}
