<template>
  <el-tag
    :type="tagType"
    :effect="effect"
    :size="size"
    :round="round"
    class="status-badge"
    :class="[`status-badge--${status}`, `status-badge--${size}`]"
  >
    <el-icon v-if="showIcon" class="status-badge__icon">
      <component :is="iconComponent" />
    </el-icon>
    <slot>{{ displayText }}</slot>
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
  Loading,
  InfoFilled,
  QuestionFilled,
} from '@element-plus/icons-vue'

/** Element Plus el-tag type 联合类型 */
type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

interface Props {
  /** 状态值 */
  status: string
  /** 是否显示状态图标 */
  showIcon?: boolean
  /** 标签效果：light / dark / plain / dark */
  effect?: 'light' | 'dark' | 'plain'
  /** 标签尺寸 */
  size?: 'small' | 'default' | 'large'
  /** 是否圆角 */
  round?: boolean
  /** 自定义文本（可选，默认根据 status 自动推断） */
  text?: string
}

const props = withDefaults(defineProps<Props>(), {
  showIcon: false,
  effect: 'light',
  size: 'default',
  round: true,
})

/** 状态到 Element Plus tag type 的映射 */
const STATUS_TAG_MAP: Record<string, TagType> = {
  // 通用状态
  success: 'success',
  online: 'success',
  active: 'success',
  enabled: 'success',
  running: 'success',
  ok: 'success',
  normal: 'success',

  error: 'danger',
  danger: 'danger',
  offline: 'danger',
  disabled: 'danger',
  failed: 'danger',
  stopped: 'danger',
  stopped_running: 'danger',
  critical: 'danger',

  warning: 'warning',
  warn: 'warning',
  paused: 'warning',
  processing: 'warning',
  pending: 'warning',
  pending_sync: 'warning',

  info: 'info',
  unknown: 'info',
  default: 'info',
  inactive: 'info',
}

/** 状态文本映射（可覆盖） */
const STATUS_TEXT_MAP: Record<string, string> = {
  online: '在线',
  offline: '离线',
  success: '成功',
  error: '失败',
  active: '已启用',
  inactive: '已停用',
  enabled: '启用',
  disabled: '停用',
  running: '运行中',
  stopped: '已停止',
  failed: '失败',
  warning: '警告',
  warn: '警告',
  pending: '待处理',
  pending_sync: '同步中',
  paused: '已暂停',
  processing: '处理中',
  ok: '正常',
  normal: '正常',
  critical: '严重',
  unknown: '未知',
}

/** 状态到图标的映射 */
const STATUS_ICON_MAP: Record<string, Component> = {
  success: CircleCheckFilled,
  online: CircleCheckFilled,
  active: CircleCheckFilled,
  enabled: CircleCheckFilled,
  running: CircleCheckFilled,
  ok: CircleCheckFilled,
  normal: CircleCheckFilled,

  error: CircleCloseFilled,
  danger: CircleCloseFilled,
  offline: CircleCloseFilled,
  disabled: CircleCloseFilled,
  failed: CircleCloseFilled,
  stopped: CircleCloseFilled,
  critical: CircleCloseFilled,

  warning: WarningFilled,
  warn: WarningFilled,
  paused: WarningFilled,
  processing: Loading,
  pending: Loading,
  pending_sync: Loading,

  info: InfoFilled,
  unknown: QuestionFilled,
  inactive: InfoFilled,
}

const tagType = computed<TagType>(() => {
  const normalized = String(props.status || 'default').toLowerCase()
  return STATUS_TAG_MAP[normalized] || 'info'
})

const displayText = computed(() => {
  if (props.text) return props.text
  const normalized = String(props.status || 'unknown').toLowerCase()
  return STATUS_TEXT_MAP[normalized] || props.status
})

const iconComponent = computed(() => {
  const normalized = String(props.status || 'unknown').toLowerCase()
  return STATUS_ICON_MAP[normalized] || InfoFilled
})
</script>

<style scoped>
.status-badge {
  font-weight: 600;
  letter-spacing: 0.2px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.status-badge__icon {
  font-size: 12px;
}

.status-badge--small .status-badge__icon {
  font-size: 11px;
}

.status-badge--large .status-badge__icon {
  font-size: 14px;
}

/* 悬停时不加深颜色（已有语义色） */
.status-badge:hover {
  filter: brightness(0.95);
}
</style>
