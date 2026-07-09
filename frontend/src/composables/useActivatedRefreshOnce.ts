import { onActivated, onMounted } from 'vue'
export function useActivatedRefreshOnce(callback: () => void | Promise<void>): void {
  let mounted = false
  onMounted(() => { mounted = true; callback() })
  onActivated(() => { if (mounted) callback() })
}
