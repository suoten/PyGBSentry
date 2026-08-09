import i18n from '@/locales'

export interface BuildSourceTreeOptions {
  resolveStatus?: (item: Record<string, unknown>) => number
}

const defaultResolveStatus = (_item: Record<string, unknown>) => 1

export const buildSourceTree = (
  sourceList: Record<string, unknown>[],
  options: BuildSourceTreeOptions = {}
) => {
  const enabled = (Array.isArray(sourceList) ? sourceList : []).filter((item: Record<string, unknown>) => item.enabled !== false)
  if (!enabled.length) return null

  const resolveStatus = options.resolveStatus || defaultResolveStatus
  type ProtocolGroupNode = {
    id: string
    label: string
    nodeType: string
    children: Array<Record<string, unknown>>
  }
  const protocolGroups: Record<string, ProtocolGroupNode> = {}
  for (const item of enabled) {
    const protocol = (item.protocol || 'OTHER').toUpperCase()
    if (!protocolGroups[protocol]) {
      protocolGroups[protocol] = {
        id: `source-protocol:${protocol}`,
        label: protocol,
        nodeType: 'source_protocol',
        children: []
      }
    }
    protocolGroups[protocol].children.push({
      id: `source:${item.id}`,
      label: item.name || item.id,
      nodeType: 'source_stream',
      sourceId: item.id,
      protocol,
      status: resolveStatus(item)
    })
  }

  const protocolNodes = Object.values(protocolGroups).sort((a: Record<string, unknown>, b: Record<string, unknown>) => a.label.localeCompare(b.label))
  for (const node of protocolNodes as Record<string, unknown>[]) {
    node.children.sort((a: Record<string, unknown>, b: Record<string, unknown>) => a.label.localeCompare(b.label))
  }

  return {
    id: 'source-root',
    label: i18n.global.t('channelSource.rootLabel'),
    nodeType: 'source_root',
    children: protocolNodes
  }
}
