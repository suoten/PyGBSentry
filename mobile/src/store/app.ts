import { defineStore } from "pinia";
import type { MobilePluginEntry } from "@/types/api";

interface AppState {
  loading: boolean;
  mobilePlugins: MobilePluginEntry[];
}

export const useAppStore = defineStore("app", {
  state: (): AppState => ({
    loading: false,
    mobilePlugins: []
  }),
  actions: {
    setLoading(value: boolean) {
      this.loading = value;
    },
    setMobilePlugins(plugins: MobilePluginEntry[]) {
      this.mobilePlugins = plugins;
    }
  }
});
