<template>
  <!-- FIXED: [2026-07-10] F-01 ChannelPlayerDialog 原为 11 行 stub 空壳，导致通道列表/通道管理器/设备详情抽屉
       的播放弹窗永远打不开。根因：开源版发布时组件未实现。
       修复：复用 usePlayer composable 的完整播放逻辑（API 调用/异步轮询/进度 UI/错误处理/停止），
       根据播放模式分发到 JessibucaPlayer/RtcPlayer/NativeHlsPlayer/原生 video [全栈工程师] -->
  <el-dialog
    v-model="dialogVisible"
    :width="width"
    :close-on-click-modal="false"
    :destroy-on-close="true"
    :show-close="true"
    class="channel-player-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="cpd-header">
        <div class="cpd-title">{{ title }}</div>
        <div v-if="subtitle" class="cpd-subtitle">{{ subtitle }}</div>
      </div>
    </template>

    <div class="cpd-stage">
      <!-- 播放请求进度 -->
      <div v-if="playRequest.status === 'requesting' || playRequest.status === 'waiting'" class="cpd-progress">
        <el-progress :percentage="playRequest.progress" :status="'warning'" :stroke-width="6" />
        <div class="cpd-progress-stage">{{ playRequest.stage }}</div>
        <div v-if="playRequest.message" class="cpd-progress-msg">{{ playRequest.message }}</div>
      </div>

      <!-- 播放错误 -->
      <div v-else-if="playRequest.status === 'error'" class="cpd-error">
        <el-result icon="error" :title="playRequest.stage" :sub-title="playRequest.message">
          <template v-if="playRequest.suggestion" #extra>
            <div class="cpd-suggestion">{{ playRequest.suggestion }}</div>
          </template>
          <el-button v-if="playRequest.retryable" type="primary" @click="retryPlay">
            {{ t('player.retryPlay') }}
          </el-button>
        </el-result>
      </div>

      <!-- 播放就绪 — 根据模式分发播放器 -->
      <template v-else-if="playRequest.status === 'ready' && currentPlayUrl">
        <JessibucaPlayer
          v-if="playMode === 'flv'"
          :video-url="currentPlayUrl"
          :codec="playCodec || ''"
          @error="handlePlayerError"
        />
        <RtcPlayer
          v-else-if="playMode === 'webrtc'"
          :webrtc-url="currentPlayUrl"
          @error="handlePlayerError"
        />
        <NativeHlsPlayer
          v-else-if="playMode === 'hls'"
          :hls-url="currentPlayUrl"
          @error="handlePlayerError"
        />
        <video
          v-else-if="playMode === 'raw'"
          ref="rawVideoRef"
          class="cpd-raw-video"
          autoplay
          muted
          playsinline
          controls
          :src="currentPlayUrl"
          @error="handlePlayerError"
        />
      </template>

      <!-- 空闲态 -->
      <div v-else class="cpd-empty">{{ t('player.noPlayableAddress') }}</div>
    </div>

    <!-- 底部操作栏 -->
    <template v-if="playRequest.status === 'ready' && playStreamId" #footer>
      <div class="cpd-footer">
        <span v-if="playCodec" class="cpd-codec-tag">{{ playCodec }}</span>
        <el-button size="small" @click="handleClose">{{ t('common.close') }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import JessibucaPlayer from '../JessibucaPlayer.vue'
import RtcPlayer from '../RtcPlayer.vue'
import NativeHlsPlayer from '../NativeHlsPlayer.vue'
import { usePlayer } from '@/views/channel-manager/usePlayer'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  visible?: boolean
  deviceId?: string
  channelId?: string
  width?: string
  title?: string
}>(), {
  visible: false,
  deviceId: '',
  channelId: '',
  width: '80vw',
  title: '',
})

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'close'): void
}>()

const {
  playerVisible,
  playUrl,
  playCodec,
  playApp,
  playStreamId,
  playMode,
  playRequest,
  playStream,
  closePlayer,
} = usePlayer()

const rawVideoRef = ref<HTMLVideoElement | null>(null)

const dialogVisible = computed({
  get: () => Boolean(props.visible),
  set: (value: boolean) => {
    emit('update:visible', value)
  },
})

const title = computed(() => props.title || t('player.livePreview'))
const subtitle = computed(() => {
  const dev = String(props.deviceId || '').trim()
  const ch = String(props.channelId || '').trim()
  if (dev && ch) return `${dev} / ${ch}`
  return ''
})

const currentPlayUrl = computed(() => String(playUrl.value || '').trim())

// FIXED: [2026-07-10] 弹窗打开时自动发起播放请求 [全栈工程师]
watch(
  () => [props.visible, props.deviceId, props.channelId],
  async ([visible, devId, chId]) => {
    if (!visible || !devId || !chId) return
    const row = { device_id: devId, gb_id: chId }
    await playStream(row)
  },
  { immediate: false },
)

// FIXED: [2026-07-10] 弹窗关闭时停止推流，释放设备/媒体资源 [全栈工程师]
const handleClose = async () => {
  await closePlayer()
  emit('update:visible', false)
  emit('close')
}

const retryPlay = async () => {
  const devId = String(props.deviceId || '').trim()
  const chId = String(props.channelId || '').trim()
  if (!devId || !chId) return
  await playStream({ device_id: devId, gb_id: chId })
}

const handlePlayerError = () => {
  // 播放器内部错误仅提示，不关闭弹窗（允许重试）
}

// 同步外部 visible 变化为 false 时清理资源
watch(
  () => props.visible,
  (visible) => {
    if (!visible && playStreamId.value) {
      closePlayer()
    }
    // 清理 raw video 资源
    if (!visible && rawVideoRef.value) {
      rawVideoRef.value.pause()
      rawVideoRef.value.removeAttribute('src')
      rawVideoRef.value.load()
    }
  },
)

// 防止 usePlayer 内部 playerVisible 与外部 visible 不同步
watch(playerVisible, (pv) => {
  if (!pv && props.visible) {
    emit('update:visible', false)
  }
})
</script>

<style scoped>
.cpd-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cpd-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.cpd-subtitle {
  font-size: 13px;
  color: #64748b;
  font-family: monospace;
}
.cpd-stage {
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
.cpd-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 80%;
  max-width: 480px;
  color: #e2e8f0;
}
.cpd-progress-stage {
  font-size: 15px;
  font-weight: 600;
  color: #f1f5f9;
}
.cpd-progress-msg {
  font-size: 13px;
  color: #94a3b8;
  text-align: center;
}
.cpd-error {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cpd-suggestion {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 12px;
}
.cpd-raw-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.cpd-empty {
  color: #c0c4cc;
  font-size: 14px;
}
.cpd-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.cpd-codec-tag {
  font-size: 12px;
  color: #64748b;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
}
</style>
