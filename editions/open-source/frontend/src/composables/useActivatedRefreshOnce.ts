import { onActivated, ref } from 'vue'
import type { Ref } from 'vue'

type RefreshFn = () => void | Promise<void>

type Options = {
  /**
   * 默认跳过首次激活（通常首屏由 onMounted 拉取，避免重复请求）。
   * 设为 false 则首次激活也会执行 refresh。
   */
  skipFirst?: boolean
}

export function useActivatedRefreshOnce(refresh: RefreshFn, options: Options = {}) {
  const { skipFirst = true } = options
  const activatedOnce: Ref<boolean> = ref(false)

  onActivated(() => {
    if (skipFirst && !activatedOnce.value) {
      activatedOnce.value = true
      return
    }
    activatedOnce.value = true
    void refresh()
  })

  return { activatedOnce }
}

