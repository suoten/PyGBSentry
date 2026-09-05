import { defineStore } from 'pinia'
import i18n from '@/locales'

export type TagView = {
  fullPath: string
  path: string
  name?: string
  title: string
  affix?: boolean
}

/**
 * 从路由 meta 提取并规范化标签标题。
 *
 * FIX: [2026-07-13] 路由配置已全部改用 `meta.titleKey`（i18n 翻译键）而非
 * 硬编码 `meta.title`。旧版 `normalizeTitle` 仅读取 `meta.title`，导致
 * `tag.title` fallback 到路由英文名（如 "Devices"），TagsView 标签栏
 * 出现大量英文硬编码。现在优先读取 `titleKey` 并通过 i18n 翻译为当前
 * 语言，其次回退到 `meta.title`（向后兼容），最后回退到路由名称/路径。
 */
function normalizeTitle(route: Record<string, unknown>): string {
  const meta = (route?.meta || {}) as Record<string, unknown>
  const titleKey = meta?.titleKey
  if (typeof titleKey === 'string' && titleKey.trim()) {
    try {
      const translated = i18n.global.t(titleKey.trim())
      if (typeof translated === 'string' && translated.trim()) return translated.trim()
    } catch { /* fall through */ }
  }
  const t = meta?.title
  if (typeof t === 'string' && t.trim()) return t.trim()
  if (typeof route?.name === 'string' && route.name.trim()) return route.name.trim()
  return (route?.path as string) || i18n.global.t('common.page')
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

/**
 * FIX: [2026-07-16] 将 affix 标签插入到列表开头，确保工作台等固定标签永远在第一位。
 * 非 affix 标签按原有顺序追加到 affix 标签之后。
 */
function insertViewAtCorrectPosition(views: TagView[], view: TagView, isAffix: boolean): TagView[] {
  if (isAffix) {
    // affix 标签插入到已有 affix 标签之后、非 affix 标签之前
    const firstNonAffixIdx = views.findIndex(v => !v.affix)
    if (firstNonAffixIdx === -1) {
      views.push(view)
    } else {
      views.splice(firstNonAffixIdx, 0, view)
    }
  } else {
    views.push(view)
  }
  return views
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
      const meta = (route.meta || {}) as Record<string, unknown>
      if (meta.noTagsView) return
      if (meta.hidden) return
      if (route.redirect) return
      const fullPath = String(route.fullPath || route.path || '')
      const path = String(route.path || '')
      if (!fullPath || !path) return
      if (path === '/' || fullPath === '/') return
      // FIX: [2026-07-13] 即使 fullPath 已存在，也需重新规范化 title。
      // 旧逻辑直接 return，导致 localStorage 中残留的英文标题（如 "Devices"）
      // 永远不会被更新为 i18n 翻译后的中文。现在会原地更新 title 并持久化。
      const fullPathIndex = this.visitedViews.findIndex(v => v.fullPath === fullPath)
      if (fullPathIndex >= 0) {
        const old = this.visitedViews[fullPathIndex]
        const newTitle = normalizeTitle(route) || old.title
        if (newTitle !== old.title) {
          this.visitedViews[fullPathIndex] = { ...old, title: newTitle }
          this._persist()
        }
        return
      }
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
      // FIX: [2026-07-16] affix 标签固定在列表开头（工作台永远第一位）
      insertViewAtCorrectPosition(this.visitedViews, {
        fullPath,
        path,
        name: typeof route.name === 'string' ? route.name : undefined,
        title: normalizeTitle(route),
        affix: !!meta.affix,
      }, !!meta.affix)
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
        // FIX: [2026-07-16] affix 标签插入到列表开头，确保工作台永远在第一位
        insertViewAtCorrectPosition(this.visitedViews, {
          fullPath: path,
          path,
          name: typeof r.name === 'string' ? r.name : undefined,
          title: normalizeTitle(r),
          affix: true,
        }, true)
      }
      this._persist()
    },
  },
})
