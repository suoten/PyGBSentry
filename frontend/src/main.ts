import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { applyBeijingTimezone } from './utils/timezone'
// FIX H-1: 移除失效的 v-permission 指令导入（文件已删除）
import i18n from './locales'

const app = createApp(App)

applyBeijingTimezone()

app.use(createPinia())
app.use(i18n)
app.use(router)

// Element Plus locale 联动 i18n locale
const elementLocale = i18n.global.locale.value === 'zh-CN' ? zhCn : en
app.use(ElementPlus, { locale: elementLocale })

// FIX H-1: 不再注册失效的 v-permission 指令

app.mount('#app')
