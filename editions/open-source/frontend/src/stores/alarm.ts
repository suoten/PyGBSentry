import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/http'
import type { Alarm } from '@/types/models'
import { logger } from '@/utils/logger'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: 引入i18n

export const useAlarmStore = defineStore('alarm', () => {
  const { t } = useI18n()  // FIXED: i18n实例
  const alarms = ref<Alarm[]>([])
  const unreadCount = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)  // FIXED: 增加 error 状态

  const recentAlarms = computed(() => alarms.value.slice(0, 20))

  async function fetchAlarms(params?: Record<string, unknown>) {
    loading.value = true
    error.value = null
    try {
      const res = await api.get('/api/v1/alarms', { params })
      alarms.value = res.data?.items ?? res.data ?? []
    } catch (e) {
      logger.error('Failed to fetch alarm list', e)
      ElMessage.error(t('alarm.fetchFailed'))  // FIXED: 硬编码中文→i18n
      error.value = 'fetch_alarms_failed'
      alarms.value = []
    } finally {
      loading.value = false
    }
  }

  async function fetchUnreadCount() {
    try {
      const res = await api.get('/api/v1/alarms/unread-count')
      unreadCount.value = res.data?.unread_count ?? res.data?.count ?? 0  // FIXED: 字段名与后端对齐(unread_count)
    } catch (e) {
      // FIXED: 静默设为0改为不重置，避免用户误认为无未读告警
      logger.warning('Failed to fetch unread alarm count', e)  // FIXED: 日志中文→英文
    }
  }

  function addAlarm(alarm: Alarm) {
    const exists = alarms.value.some(a => a.id === alarm.id)
    if (!exists) {
      alarms.value.unshift(alarm)
      unreadCount.value++
    }
  }

  return { alarms, unreadCount, loading, error, recentAlarms, fetchAlarms, fetchUnreadCount, addAlarm }
})
