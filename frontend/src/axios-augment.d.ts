import 'axios'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 为 true 时跳过 main.ts 全局 axios 错误 Toast（由调用方自行展示） */
    skipFriendlyMessage?: boolean
  }
}
