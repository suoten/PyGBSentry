import { ref, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'

export function useDebounceFn<T extends (...args: unknown[]) => any>(fn: T, delay: number = 300) {
  let timer: number | null = null
  const pending = ref(false)

  const debounced = ((...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    pending.value = true
    return new Promise<Awaited<ReturnType<T>>>((resolve) => {
      timer = window.setTimeout(async () => {
        timer = null
        pending.value = false
        const result = await fn(...args)
        resolve(result)
      }, delay)
    })
  }) as T & { pending: Ref<boolean>; cancel: () => void }

  debounced.pending = pending
  debounced.cancel = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
      pending.value = false
    }
  }

  return debounced
}

export function useThrottleFn<T extends (...args: unknown[]) => any>(fn: T, interval: number = 300) {
  let lastCall = 0
  let timer: number | null = null

  return ((...args: Parameters<T>) => {
    const now = Date.now()
    const remaining = interval - (now - lastCall)
    if (remaining <= 0) {
      if (timer) { clearTimeout(timer); timer = null }
      lastCall = now
      return fn(...args)
    } else if (!timer) {
      timer = window.setTimeout(() => {
        lastCall = Date.now()
        timer = null
        fn(...args)
      }, remaining)
    }
  }) as T
}

export function useIntervalFn(fn: () => void, interval: number, immediate = false) {
  let timer: number | null = null
  const isActive = ref(false)

  const start = () => {
    if (isActive.value) return
    isActive.value = true
    timer = window.setInterval(fn, interval)
  }

  const stop = () => {
    if (!isActive.value) return
    isActive.value = false
    if (timer) { clearInterval(timer); timer = null }
  }

  if (immediate) fn()

  onMounted(start)
  onBeforeUnmount(stop)

  return { isActive, start, stop }
}

export function useStorage<T>(key: string, defaultValue: T): Ref<T> {
  const stored = localStorage.getItem(key)
  let parsed: T = defaultValue // FIXED: JSON.parse包裹try-catch
  if (stored) {
    try {
      parsed = JSON.parse(stored)
    } catch {
      parsed = defaultValue
    }
  }
  const data = ref<T>(parsed) as Ref<T>

  watch(data, (val) => {
    localStorage.setItem(key, JSON.stringify(val))
  }, { deep: true })

  return data
}

export function useWindowSize() {
  const width = ref(window.innerWidth)
  const height = ref(window.innerHeight)

  const update = () => {
    width.value = window.innerWidth
    height.value = window.innerHeight
  }

  onMounted(() => window.addEventListener('resize', update))
  onBeforeUnmount(() => window.removeEventListener('resize', update))

  return { width, height }
}
