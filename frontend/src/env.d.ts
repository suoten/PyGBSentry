/// <reference types="vite/client" />

import 'axios'
import 'vue-router'

// P1-24: ImportMetaEnv 接口 — 提供前端环境变量的类型安全
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_API_TIMEOUT: string
  readonly VITE_TOKEN_CACHE_TTL: string
  readonly VITE_APP_EDITION: string
  readonly VITE_ALLOW_PUBLIC_REGISTRATION: string
  readonly VITE_DEV_API_TARGET: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    titleKey?: string
    hiddenInMenu?: boolean
    affix?: boolean
    keepAlive?: boolean
    paidFeature?: boolean
    requiredRoles?: string[]
  }
}

// Axios 自定义配置项类型扩展（skipFriendlyMessage 用于跳过友好错误提示）
declare module 'axios' {
  interface AxiosRequestConfig {
    skipFriendlyMessage?: boolean
    _retry?: boolean
  }
}

declare module '*.vue' {
  // P2-10: 收紧类型 — 使用 DefineComponent 默认泛型而非显式 any
  import type { DefineComponent } from 'vue'
  const component: DefineComponent
  export default component
}

declare module '@element-plus/icons-vue' {
  import type { Component } from 'vue'
  const icons: Record<string, Component>
  export default icons
  export const Plus: Component
  export const Edit: Component
  export const EditPen: Component
  export const Delete: Component
  export const DeleteFilled: Component
  export const View: Component
  export const InfoFilled: Component
  export const Search: Component
  export const Refresh: Component
  export const RefreshRight: Component
  export const Setting: Component
  export const Download: Component
  export const Upload: Component
  export const Close: Component
  export const CircleCheckFilled: Component
  export const CircleCloseFilled: Component
  export const WarningFilled: Component
  export const Loading: Component
  export const InfoFilled2: Component
  export const QuestionFilled: Component
}

