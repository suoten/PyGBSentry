import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/http'
import type { Device, Channel } from '@/types/models'
import { logger } from '@/utils/logger'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: 引入i18n

export const useDeviceStore = defineStore('device', () => {
  const { t } = useI18n()  // FIXED: i18n实例
  const devices = ref<Device[]>([])
  const currentDevice = ref<Device | null>(null)
  const channels = ref<Channel[]>([])
  const currentChannel = ref<Channel | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)  // FIXED: 增加 error 状态供组件感知

  async function fetchDevices(params?: Record<string, unknown>) {
    loading.value = true
    error.value = null
    try {
      const res = await api.get('/api/v1/devices', { params })
      devices.value = res.data?.items ?? res.data ?? []
    } catch (e) {
      logger.error('Failed to fetch device list', e)
      ElMessage.error(t('device.fetchFailed'))  // FIXED: 硬编码中文→i18n
      error.value = 'fetch_devices_failed'
      devices.value = []
    } finally {
      loading.value = false
    }
  }

  async function fetchChannels(deviceId: string) {
    error.value = null
    try {
      const res = await api.get(`/api/v1/devices/${deviceId}/channels`)
      channels.value = res.data?.items ?? res.data ?? []
    } catch (e) {
      logger.error('Failed to fetch channel list', e)
      ElMessage.error(t('device.fetchChannelsFailed'))  // FIXED: 硬编码中文→i18n
      error.value = 'fetch_channels_failed'
      channels.value = []
    }
  }

  function setCurrentDevice(device: Device | null) {
    currentDevice.value = device
  }

  function setCurrentChannel(channel: Channel | null) {
    currentChannel.value = channel
  }

  return { devices, currentDevice, channels, currentChannel, loading, error, fetchDevices, fetchChannels, setCurrentDevice, setCurrentChannel }
})
