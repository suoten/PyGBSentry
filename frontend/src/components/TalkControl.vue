<template>
  <div class="talk-wrap">
    <div class="talk-top">
      <span class="label">{{ t('talkCtrl.talk') }}</span>
      <el-switch v-model="broadcastMode" />
      <span class="label active">{{ t('talkCtrl.broadcast') }}</span>
    </div>

    <div class="status-bar">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ statusText }}</span>
    </div>

    <div
      class="mic-area"
      :class="{ active: isTalking }"
      @mousedown="startTalk"
      @mouseup="stopTalk"
      @mouseleave="stopTalk"
      @touchstart.prevent="startTalk"
      @touchend.prevent="stopTalk"
    >
      <div class="mic-circle">
        <el-icon><Microphone /></el-icon>
      </div>
      <div class="mic-text">{{ isTalking ? t('talkCtrl.releaseToStop') : t('talkCtrl.holdToTalk') }}</div>
      <div class="mic-sub">{{ t('talkCtrl.holdToTalkTip') }}</div>
    </div>

    <div class="settings-title">{{ t('talkCtrl.settings') }}</div>
    <div class="setting-row">
      <span class="setting-label">{{ t('talkCtrl.micVolume') }}</span>
      <el-slider v-model="micVolume" :min="0" :max="100" />
      <span class="setting-value">{{ micVolume }}%</span>
    </div>
    <div class="setting-row">
      <span class="setting-label">{{ t('talkCtrl.speakerVolume') }}</span>
      <el-slider v-model="speakerVolume" :min="0" :max="100" />
      <span class="setting-value">{{ speakerVolume }}%</span>
    </div>
    <div class="setting-row mini">
      <span class="setting-label">{{ t('talkCtrl.echoCancellation') }}</span>
      <el-switch v-model="echoCancellation" />
    </div>
    <div class="setting-row mini">
      <span class="setting-label">{{ t('talkCtrl.autoGain') }}</span>
      <el-switch v-model="autoGain" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Microphone,
  InfoFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/http'
import { getFriendlyError } from '../utils/errorMessage'

const { t } = useI18n()

const props = defineProps<{
  deviceId: string
  channelId: string
}>()

const broadcastMode = ref(true)
const isTalking = ref(false)
const isConnecting = ref(false)
const callId = ref('')
const micVolume = ref(80)
const speakerVolume = ref(80)
const echoCancellation = ref(true)
const autoGain = ref(true)

const statusText = computed(() => {
  if (isTalking.value) return t('talkCtrl.pleaseTalk')
  if (isConnecting.value) return t('talkCtrl.connecting')
  return t('talkCtrl.waitingForConnection')
})

const startTalk = async () => {
  if (isTalking.value || isConnecting.value) return

  isConnecting.value = true
  try {
    const url = broadcastMode.value ? '/api/v1/stream/broadcast/start' : '/api/v1/stream/talk/start'

    // 如果是对讲模式，理想情况下这里要向后端传入 WebRTC 麦克风的 SDP，或者由后端返回流地址供前端推流
    const payload: Record<string, unknown> = {
      device_id: props.deviceId,
      channel_id: props.channelId
    }

    // 假设是 Talk 模式，为了演示双向对讲的 API 调用，直接发请求
    // 实际商业项目中，这里需要结合浏览器 navigator.mediaDevices.getUserMedia() 获取麦克风
    const resp = await api.post(url, payload)
    callId.value = String(resp?.data?.call_id || '')

    isTalking.value = true
    isConnecting.value = false

    ElMessage.success(broadcastMode.value ? t('talkCtrl.broadcastStarted') : t('talkCtrl.talkConnected'))
  } catch (error) {
    isConnecting.value = false
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const stopTalk = async () => {
  if (!isTalking.value) return

  try {
    const url = broadcastMode.value ? '/api/v1/stream/broadcast/stop' : '/api/v1/stream/talk/stop'
    await api.post(url, {
      device_id: props.deviceId,
      channel_id: props.channelId,
      call_id: callId.value
    })
    ElMessage.success(broadcastMode.value ? t('talkCtrl.broadcastEnded') : t('talkCtrl.talkEnded'))
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.warning(friendly.message)
  } finally {
    callId.value = ''
    isTalking.value = false
  }
}

</script>

<style scoped>
.talk-wrap { padding: 6px 8px; }
.talk-top { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 10px; }
.label { color: #606266; font-size: 14px; }
.label.active { color: #409eff; }
.status-bar { height: 34px; border-radius: 18px; background: #f2f4f7; display: flex; align-items: center; justify-content: center; gap: 6px; color: #606266; margin-bottom: 12px; }
.mic-area { border: 2px solid #d9e8ff; border-radius: 14px; background: #eef5ff; min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; }
.mic-area.active { border-color: #409eff; background: #e5f0ff; }
.mic-circle { width: 64px; height: 64px; border-radius: 50%; background: #409eff; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 28px; }
.mic-text { margin-top: 10px; color: #303133; font-size: 18px; }
.mic-sub { margin-top: 6px; color: #909399; font-size: 12px; }
.settings-title { text-align: center; margin: 14px 0 8px; color: #606266; font-size: 13px; }
.setting-row { display: grid; grid-template-columns: 90px 1fr 42px; align-items: center; gap: 8px; margin-bottom: 10px; }
.setting-row.mini { grid-template-columns: 90px 1fr; }
.setting-label { color: #606266; font-size: 13px; }
.setting-value { color: #409eff; font-size: 13px; text-align: right; }
</style>
