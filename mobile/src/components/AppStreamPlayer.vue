<script setup lang="ts">
import { computed, ref } from "vue";
import { buildPlaybackPlan } from "@/utils/playerAdapter";
import AppStatusTag from "@/components/AppStatusTag.vue";
import { getNativePlayerBridgeStatus, openNativePlayer } from "@/utils/nativePlayerBridge";

const props = withDefaults(
  defineProps<{
    url: string;
    mode?: string;
    autoplay?: boolean;
    muted?: boolean;
    heightRpx?: number;
  }>(),
  {
    mode: "raw",
    autoplay: true,
    muted: false,
    heightRpx: 360
  }
);

const playbackPlan = computed(() => buildPlaybackPlan(props.url, props.mode));
const canUseVideo = computed(() => playbackPlan.value.canInlineVideo);

const planType = computed(() => {
  if (playbackPlan.value.strategy === "native-video") return "success" as const;
  if (playbackPlan.value.strategy === "native-adapter") return "warning" as const;
  return "info" as const;
});

const planText = computed(() => {
  if (playbackPlan.value.strategy === "native-video") return "内嵌播放";
  if (playbackPlan.value.strategy === "native-adapter") return "原生适配";
  return "外部调试";
});

const nativeBridgeStatus = computed(() => getNativePlayerBridgeStatus());
const nativePlayerAvailable = computed(() => nativeBridgeStatus.value.available && nativeBridgeStatus.value.supported);
const openingNativePlayer = ref(false);

function copyUrl() {
  if (!props.url) return;
  uni.setClipboardData({ data: props.url });
}

async function openByNativeAdapter() {
  if (!props.url) return;
  openingNativePlayer.value = true;
  try {
    await openNativePlayer({
      url: props.url,
      protocol: playbackPlan.value.protocol,
      title: `直播-${playbackPlan.value.protocol.toUpperCase()}`,
      autoplay: props.autoplay,
      muted: props.muted
    });
    uni.showToast({ title: "已调用原生播放器", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message || "原生播放器不可用", icon: "none" });
  } finally {
    openingNativePlayer.value = false;
  }
}
</script>

<template>
  <view class="app-card app-gap-12">
    <view class="app-row">
      <text class="app-subtext">协议：{{ playbackPlan.protocol.toUpperCase() }}</text>
      <AppStatusTag :text="planText" :type="planType" />
    </view>
    <text class="app-subtext">{{ playbackPlan.reason }}</text>
    <video
      v-if="canUseVideo"
      :src="props.url"
      :autoplay="props.autoplay"
      :muted="props.muted"
      :show-center-play-btn="false"
      :enable-progress-gesture="false"
      :show-fullscreen-btn="true"
      :show-play-btn="true"
      controls
      object-fit="contain"
      :style="`width:100%;height:${props.heightRpx}rpx;background:#000;border-radius:12rpx`"
    />
    <view v-else>
      <text class="app-subtext">当前线路（{{ props.mode?.toUpperCase() }}）暂不支持内嵌播放，请按建议切换协议或接入原生适配层。</text>
      <text v-if="playbackPlan.suggestedFallback !== 'none'" class="app-subtext">建议回退：{{ playbackPlan.suggestedFallback.toUpperCase() }}</text>
      <text v-if="playbackPlan.strategy === 'native-adapter'" class="app-subtext">
        原生桥接：{{ nativeBridgeStatus.message }} / 来源={{ nativeBridgeStatus.source }} / 平台={{ nativeBridgeStatus.platform }}
      </text>
      <text selectable style="display:block;margin-top:8rpx;word-break:break-all">{{ props.url || "-" }}</text>
      <button
        v-if="playbackPlan.strategy === 'native-adapter'"
        size="mini"
        style="margin-top: 10rpx"
        :loading="openingNativePlayer"
        :disabled="!nativePlayerAvailable"
        @click="openByNativeAdapter"
      >
        原生解码播放
      </button>
      <button size="mini" style="margin-top: 10rpx" @click="copyUrl">复制地址</button>
    </view>
  </view>
</template>
