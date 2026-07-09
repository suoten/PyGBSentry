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

  return { visitedViews, cachedViews, addView, removeView }
})
