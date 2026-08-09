import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
// FIX: [2026-07-18 P0] 恢复 Element Plus 全量注册。
// 之前 [2026-07-16 P1] 改用 unplugin-vue-components 按需自动导入后，
// App.vue 根节点的 <el-config-provider> 无法被自动导入（根节点组件的
// 自动导入存在 edge case），导致 Vue 将其当作未知元素渲染为注释 <!---->，
// 整个页面白屏。恢复全量注册是最简单可靠的修复。
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import { applyBeijingTimezone } from './utils/timezone'
// FIX H-1: 移除失效的 v-permission 指令导入（文件已删除）
import i18n from './locales'

const app = createApp(App)

applyBeijingTimezone()

app.use(createPinia())
app.use(i18n)
app.use(router)
app.use(ElementPlus)

// FIX H-1: 不再注册失效的 v-permission 指令

app.mount('#app')
