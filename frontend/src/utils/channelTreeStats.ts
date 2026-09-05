import { ref, type Ref } from 'vue'

export type TreeNodeStats = { online: number; total: number }

type NodeMatcher = string[] | ((node: Record<string, unknown>) => boolean)

export interface UseChannelTreeStatsOptions {
  countableNodeTypes: NodeMatcher
  statsVisibleNodeTypes: NodeMatcher
  isPlayableChannel: (node: Record<string, unknown>) => boolean
}

const resolveMatcher = (matcher: NodeMatcher) => {
  if (typeof matcher === 'function') return matcher
  const typeSet = new Set((matcher || []).map((item) => String(item || '').toLowerCase()))
  return (node: Record<string, unknown>) => {
    const nodeType = String(node?.nodeType || '').toLowerCase()
    return typeSet.has(nodeType)
  }
}

export const useChannelTreeStats = (
  treeData: Ref<any[]>,
  options: UseChannelTreeStatsOptions
) => {
  const isCountableNode = resolveMatcher(options.countableNodeTypes)
  const isStatsVisibleNode = resolveMatcher(options.statsVisibleNodeTypes)
  const treeNodeStats = ref<Record<string, TreeNodeStats>>({})

  const collectNodeChannelStats = (node: Record<string, unknown>): TreeNodeStats => {
    let total = 0
    let online = 0
    if (isCountableNode(node)) {
      total += 1
      if (options.isPlayableChannel(node)) {
        online += 1
      }
    }
    const children = Array.isArray(node?.children) ? node.children : []
    for (const child of children) {
      const childStats = collectNodeChannelStats(child)
      total += childStats.total
      online += childStats.online
    }
    return { total, online }
  }

  const rebuildTreeNodeStats = () => {
    const statsMap: Record<string, TreeNodeStats> = {}
    const walk = (nodes: Record<string, unknown>[]) => {
      for (const node of nodes || []) {
        const nodeKey = String(node?.id || '').trim()
        if (nodeKey) {
          statsMap[nodeKey] = collectNodeChannelStats(node)
        }
        if (Array.isArray(node?.children) && node.children.length > 0) {
          walk(node.children)
        }
      }
    }
    walk(treeData.value)
    treeNodeStats.value = statsMap
  }

  const shouldShowNodeStats = (node: Record<string, unknown>) => isStatsVisibleNode(node)

  const getNodeStats = (node: Record<string, unknown>): TreeNodeStats => {
    const key = String(node?.id || '').trim()
    if (!key) return { online: 0, total: 0 }
    return treeNodeStats.value[key] || { online: 0, total: 0 }
  }

  const getNodeStatsTone = (node: Record<string, unknown>) => {
    const stats = getNodeStats(node)
    if (stats.total <= 0) return 'muted'
    const ratio = stats.online / stats.total
    if (ratio >= 0.75) return 'good'
    if (ratio >= 0.3) return 'warn'
    return 'bad'
  }

  return {
    treeNodeStats,
    rebuildTreeNodeStats,
    shouldShowNodeStats,
    getNodeStats,
    getNodeStatsTone
  }
}
