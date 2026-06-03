import { createSSRApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { installMockNativePlayerBridge } from "@/utils/nativePlayerMockBridge";
import i18n from "@/locales"; // FIXED-P3: N-14 工单页面国际化

export function createApp() {
  if (import.meta.env.DEV) {
    installMockNativePlayerBridge();
  }
  const app = createSSRApp(App);
  const pinia = createPinia();
  app.use(pinia);
  app.use(i18n); // FIXED-P3: N-14 工单页面国际化
  return {
    app
  };
}
