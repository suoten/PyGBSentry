export interface SourceTreeNode { id: string; label: string; children?: SourceTreeNode[]; [k: string]: unknown }

export interface SourceTreeOptions {
  resolveStatus?: (item: Record<string, unknown>) => number
}

export function buildSourceTree(devices: unknown[], options?: SourceTreeOptions): SourceTreeNode[] {
  if (!Array.isArray(devices)) return []
  return devices.map((d, i) => {
    const dev = d as Record<string, unknown>
    return { id: String(dev.id ?? dev.device_id ?? i), label: String(dev.name ?? dev.device_id ?? `Device ${i}`), children: [] }
  })
}
