import api from '../utils/http'
export interface OrgTreeNode { id: string; name: string; children?: OrgTreeNode[]; [k: string]: unknown }
export async function getOrganizationTree() { const res = await api.get('/api/v1/organizations/tree'); return res.data ?? [] }
export function flattenOrgTree(tree: OrgTreeNode[]): OrgTreeNode[] {
  const result: OrgTreeNode[] = []
  function walk(nodes: OrgTreeNode[]) { for (const n of nodes) { result.push(n); if (n.children?.length) walk(n.children) } }
  walk(tree); return result
}
