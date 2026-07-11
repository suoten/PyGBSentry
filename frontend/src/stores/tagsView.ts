import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface TagView { path: string; title: string; name?: string; affix?: boolean }

export const useTagsViewStore = defineStore('tagsView', () => {
  const visitedViews = ref<TagView[]>([])
  const cachedViews = ref<string[]>([])

  function addView(view: TagView) {
    if (!visitedViews.value.some(v => v.path === view.path)) {
      visitedViews.value.push(view)
    }
    if (view.name && !cachedViews.value.includes(view.name)) {
      cachedViews.value.push(view.name)
    }
  }

  function removeView(path: string) {
    const idx = visitedViews.value.findIndex(v => v.path === path)
    if (idx >= 0) visitedViews.value.splice(idx, 1)
  }

  // FIX: [2026-07-10] 补充 ensureAffix — App.vue:626 调用但原 store 未导出，
  // 导致 TypeError: ensureAffix is not a function，affix 标签页不初始化 [全栈工程师]
  function ensureAffix(routes: Array<{ path: string; meta?: unknown; name?: unknown }>) {
    for (const r of routes) {
      if (r.path && !visitedViews.value.some(v => v.path === r.path)) {
        const meta = r.meta as Record<string, unknown> | undefined
        visitedViews.value.push({
          path: r.path,
          title: (meta?.title as string) || r.path,
          name: r.name as string | undefined,
          affix: true,
        })
      }
    }
  }

  return { visitedViews, cachedViews, addView, removeView, ensureAffix }
})
