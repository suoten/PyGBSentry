import { defineStore } from 'pinia'
import i18n from '@/locales'

export type TagView = {
  fullPath: string
  path: string
  name?: string
  title: string
  affix?: boolean
}

function normalizeTitle(route: Record<string, unknown>): string {
  // FIXED: 优先使用 titleKey 通过 i18n 翻译，避免标签页显示英文路由名
  const titleKey = route?.meta?.titleKey
  if (typeof titleKey === 'string' && titleKey.trim()) {
    try {
      const t = i18n.global.t(titleKey.trim())
      if (typeof t === 'string' && t.trim() && t !== titleKey) return t.trim()
    } catch { /* i18n not ready yet */ }
  }
  const t = route?.meta?.title
  if (typeof t === 'string' && t.trim()) return t.trim()
  if (typeof route?.name === 'string' && route.name.trim()) return route.name.trim()
  return route?.path || '页面'
}

const STORAGE_KEY = 'pygbsentry_tags_views'

function loadFromStorage(): TagView[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw)
  } catch {
    return []
  }
}

function saveToStorage(views: TagView[]) {
  try {
    const data = views.filter(v => !v.affix)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch { /* cleanup: ignore */ }
}

export const useTagsViewStore = defineStore('tagsView', {
  state: () => ({
    visitedViews: loadFromStorage() as TagView[],
  }),
  actions: {
    _persist() {
      saveToStorage(this.visitedViews)
    },
    addView(route: Record<string, unknown>) {
      if (!route) return
      const meta = route.meta || {}
      if (meta.noTagsView) return
      if (meta.hidden) return
      if (route.redirect) return
      const fullPath = String(route.fullPath || route.path || '')
      const path = String(route.path || '')
      if (!fullPath || !path) return
      if (path === '/' || fullPath === '/') return
      const fullPathExists = this.visitedViews.some(v => v.fullPath === fullPath)
      if (fullPathExists) return
      const samePathIndex = this.visitedViews.findIndex(v => v.path === path)
      if (samePathIndex >= 0) {
        const old = this.visitedViews[samePathIndex]
        this.visitedViews[samePathIndex] = {
          ...old,
          fullPath,
          name: typeof route.name === 'string' ? route.name : old.name,
          title: normalizeTitle(route) || old.title,
          affix: old.affix || !!meta.affix,
        }
        this._persist()
        return
      }
      this.visitedViews.push({
        fullPath,
        path,
        name: typeof route.name === 'string' ? route.name : undefined,
        title: normalizeTitle(route),
        affix: !!meta.affix,
      })
      this._persist()
    },
    delView(view: TagView) {
      this.visitedViews = this.visitedViews.filter(v => v.fullPath !== view.fullPath)
      this._persist()
    },
    delOthers(view: TagView) {
      this.visitedViews = this.visitedViews.filter(v => v.affix || v.fullPath === view.fullPath)
      this._persist()
    },
    delRight(view: TagView) {
      const idx = this.visitedViews.findIndex(v => v.fullPath === view.fullPath)
      if (idx < 0) return
      this.visitedViews = this.visitedViews.filter((v, i) => v.affix || i <= idx)
      this._persist()
    },
    delAll() {
      this.visitedViews = this.visitedViews.filter(v => v.affix)
      this._persist()
    },
    ensureAffix(affixRoutes: Array<{ path: string; meta?: Record<string, unknown>; name?: string }>) {
      for (const r of affixRoutes) {
        const path = String(r.path || '')
        if (!path) continue
        if (path === '/') continue
        const exists = this.visitedViews.some(v => v.path === path)
        if (exists) continue
        this.visitedViews.push({
          fullPath: path,
          path,
          name: typeof r.name === 'string' ? r.name : undefined,
          title: normalizeTitle(r),
          affix: true,
        })
      }
      this._persist()
    },
  },
})
