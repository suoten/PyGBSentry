<template>
  <div class="relative w-full h-full bg-black overflow-hidden">
    <div v-if="props.showStop !== false && props.videoUrl" class="absolute top-2 right-2 z-30 flex items-center gap-2">
      <el-button size="small" type="danger" plain :disabled="stopped" @click="stop">停止</el-button>
      <el-button v-if="stopped" size="small" @click="resume">继续</el-button>
    </div>

    <div v-if="stopped" class="w-full h-full flex items-center justify-center text-sm" style="color: rgba(255,255,255,0.75)">
      已停止播放
    </div>

    <template v-else>
      <video
        v-if="isMp4"
        ref="mp4El"
        class="w-full h-full"
        :src="props.videoUrl"
        controls
        autoplay
        playsinline
        preload="auto"
        style="object-fit: contain; background: rgba(0, 0, 0, 0.85)"
      />
      <RtcPlayer v-else-if="isWebrtc" :webrtc-url="props.videoUrl" />
      <H265Player v-else-if="isH265" :video-url="props.videoUrl" />
      <JessibucaPlayer v-else :video-url="jessibucaUrl" :hls-url="props.hlsUrl" :codec="props.codec" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import JessibucaPlayer from './JessibucaPlayer.vue'
import RtcPlayer from './RtcPlayer.vue'
import H265Player from './H265Player.vue'

const props = defineProps<{
  videoUrl: string
  hlsUrl?: string
  codec?: string
  showStop?: boolean
}>()

const emit = defineEmits<{
  (e: 'stop'): void
}>()

const stopped = ref(false)
const mp4El = ref<HTMLVideoElement | null>(null)

const isMp4 = computed(() => {
  const url = String(props.videoUrl || '').toLowerCase()
  return url.includes('.mp4') || url.includes('/record/') || url.includes('application/mp4')
})

const isWebrtc = computed(() => {
  const url = String(props.videoUrl || '').toLowerCase()
  return url.includes('/index/api/webrtc')
})

const isH265 = computed(() => {
  return props.codec === 'h265' || props.codec === 'H265' || props.codec === 'hevc'
})

const jessibucaUrl = computed(() => {
  const url = String(props.videoUrl || '')
  if (isWebrtc.value) {
    return '' // 避免 Jessibuca 拿到 WebRTC 地址报错
  }
  return url
})

const stop = () => {
  if (stopped.value) return
  try {
    mp4El.value?.pause()
  } catch { /* ignore */ }
  stopped.value = true
  emit('stop')
}

const resume = () => {
  stopped.value = false
}

watch(
  () => props.videoUrl,
  () => {
    stopped.value = false
  }
)

defineExpose({ stop, resume })
</script>
