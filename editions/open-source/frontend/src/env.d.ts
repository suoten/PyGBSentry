/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
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
  export const Plus: Component
}

