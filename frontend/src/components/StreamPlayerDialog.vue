<template>
  <!-- FIX: [2026-07-04] StreamPlayerDialog 原为 stub 空壳，导致录像回放弹窗完全不能用。
       根因：开源版发布时组件未实现，仅保留 11 行 stub。
       修复：实现流播放对话框，根据 mode 分发到对应播放器组件（jessibuca/webrtc/hls/raw） [全栈工程师] -->
  <el-dialog
    v-model="dialogVisible"
    :width="width"
    :close-on-click-modal="false"
    :destroy-on-close="true"
    :show-close="true"
    class="stream-player-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="spd-header">
        <div class="spd-title">{{ title }}</div>
        <div v-if="subtitle" class="spd-subtitle">{{ subtitle }}</div>
      </div>
    </template>
    <div class="spd-stage">
      <template v-if="currentPlayUrl">
        <JessibucaPlayer
          v-if="mode === 'flv'"
          :video-url="currentPlayUrl"
          :codec="codec || ''"
          @error="handleError"
        />
        <RtcPlayer
          v-else-if="mode === 'webrtc'"
          :webrtc-url="currentPlayUrl"
          @error="handleError"
        />
        <NativeHlsPlayer
          v-else-if="mode === 'hls'"
          :hls-url="currentPlayUrl"
          @error="handleError"
        />
        <!-- FIX: [2026-07-04] raw 模式使用原生 video 播放 [全栈工程师] -->
        <video
          v-else-if="mode === 'raw'"
          ref="rawVideoRef"
          class="spd-raw-video"
          autoplay
          muted
          playsinline
          controls
          :src="currentPlayUrl"
          @error="handleError"
        />
      </template>
      <div v-else class="spd-empty">{{ emptyText }}</div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import JessibucaPlayer from './JessibucaPlayer.vue'
import RtcPlayer from './RtcPlayer.vue'
import NativeHlsPlayer from './NativeHlsPlayer.vue'

const { t } = useI18n()

type StreamMode = 'webrtc' | 'flv' | 'hls' | 'raw'
type StreamUrls = {
  webrtc?: string
  flv?: string
  hls?: string
  raw?: string
  rtcs?: string
  rtc?: string
  ws_flv?: string
  wss_flv?: string
  https_flv?: string
  https_hls?: string
  ws_hls?: string
  wss_hls?: string
  [k: string]: string | undefined
}

const props = withDefaults(defineProps<{
  modelValue?: boolean
  width?: string
  title?: string
  subtitle?: string
  urls?: StreamUrls
  playUrl?: string
  mode?: StreamMode
  codec?: string
}>(), {
  modelValue: false,
  width: '80vw',
  title: '',
  subtitle: '',
  urls: () => ({}),
  playUrl: '',
  mode: 'flv',
  codec: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
}>()

const rawVideoRef = ref<HTMLVideoElement | null>(null)

const dialogVisible = computed({
  get: () => Boolean(props.modelValue),
  set: (value: boolean) => {
    emit('update:modelValue', value)
  },
})

// FIX: [2026-07-04] 根据 mode 从 urls 中选取对应协议的播放地址，兜底使用 playUrl [全栈工程师]
const currentPlayUrl = computed(() => {
  const urls = props.urls || {}
  const mode = props.mode
  if (mode === 'webrtc') {
    return String(urls.webrtc || urls.rtcs || urls.rtc || props.playUrl || '').trim()
  }
  if (mode === 'flv') {
    return String(urls.flv || urls.ws_flv || urls.wss_flv || urls.https_flv || props.playUrl || '').trim()
  }
  if (mode === 'hls') {
    return String(urls.hls || urls.ws_hls || urls.wss_hls || urls.https_hls || props.playUrl || '').trim()
  }
  if (mode === 'raw') {
    return String(urls.raw || props.playUrl || '').trim()
  }
  return String(props.playUrl || '').trim()
})

const emptyText = computed(() => t('player.noPlayableAddress'))

const handleError = () => {
  // FIX: [2026-07-04] 播放错误时仅提示用户，不关闭弹窗（允许上层重试） [全栈工程师]
  ElMessage.warning(t('player.playFailure'))
}

const handleClose = () => {
  emit('close')
}

// FIX: [2026-07-04] 弹窗关闭时清理 raw video 资源 [全栈工程师]
watch(dialogVisible, (visible) => {
  if (!visible && rawVideoRef.value) {
    rawVideoRef.value.pause()
    rawVideoRef.value.removeAttribute('src')
    rawVideoRef.value.load()
  }
})
</script>

<style scoped>
.spd-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.spd-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.spd-subtitle {
  font-size: 13px;
  color: #64748b;
}
.spd-stage {
  width: 100%;
  height: min(60vh, 580px);
  min-height: 320px;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.spd-raw-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.spd-empty {
  color: #c0c4cc;
  font-size: 14px;
}
</style>
