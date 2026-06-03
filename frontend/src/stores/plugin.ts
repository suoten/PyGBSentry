import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: 引入i18n

interface PluginMenuItem {
  plugin_id: string
  name: string
  path: string
  icon?: string
  [key: string]: unknown
}

export const usePluginStore = defineStore('plugin', () => {
  const { t } = useI18n()  // FIXED: i18n实例
  const purchasedIds = ref<string[]>([])
  const installedMenus = ref<PluginMenuItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)  // FIXED: 增加 error 状态

  const installedIds = computed(() => new Set(installedMenus.value.map(m => m.plugin_id)))

  function isPurchased(pluginId: string): boolean {
    return purchasedIds.value.includes(pluginId)
  }

  function isInstalled(pluginId: string): boolean {
    return installedIds.value.has(pluginId)
  }

  function canUse(pluginId: string): boolean {
    return isPurchased(pluginId) && isInstalled(pluginId)
  }

  async function fetchPluginStatus() {
    loading.value = true
    error.value = null
    try {
      const [purchasedRes, menusRes] = await Promise.allSettled([  // FIXED: Promise.all→Promise.allSettled防止单接口失败导致全部失败
        api.get('/api/v1/plugins/purchased'),
        api.get('/api/v1/plugins/menus')
      ])
      const purchasedData = purchasedRes.status === 'fulfilled' ? purchasedRes.value : null
      const menusData = menusRes.status === 'fulfilled' ? menusRes.value : null
      purchasedIds.value = Array.isArray(purchasedData?.data?.plugin_ids)
        ? purchasedData.data.plugin_ids.map((x: unknown) => String(x))
        : []
      installedMenus.value = Array.isArray(menusData?.data) ? menusData.data : []
    } catch (e) {
      // FIXED: 向用户显示错误提示而非静默失败
      ElMessage.error(t('plugin.fetchFailed'))  // FIXED: 硬编码中文→i18n
      error.value = 'fetch_plugin_status_failed'
      purchasedIds.value = []
      installedMenus.value = []
    } finally {
      loading.value = false
    }
  }

  return { purchasedIds, installedMenus, loading, error, installedIds, isPurchased, isInstalled, canUse, fetchPluginStatus }
})
