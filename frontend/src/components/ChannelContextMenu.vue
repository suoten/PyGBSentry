<template>
  <div
    v-if="visible"
    class="tree-context-menu"
    :style="{ left: `${x}px`, top: `${y}px` }"
    role="menu"
    :aria-label="t('channelContextMenu.menuLabel')"
    @mousedown.stop
    @click.stop
  >
    <template v-if="targetType === 'channel'">
      <div class="menu-item" v-if="canPlay" role="menuitem" tabindex="0" @click="$emit('play')">
        <el-icon class="menu-item-icon"><VideoPlay /></el-icon>
        {{ t('channelContextMenu.play') }}
      </div>
      <div
        class="menu-item danger"
        v-if="isPlaying"
        role="menuitem"
        tabindex="0"
        @click="$emit('stop')"
      >
        <el-icon class="menu-item-icon"><CloseBold /></el-icon>
        {{ t('channelContextMenu.stop') }}
      </div>
      <div class="menu-item" role="menuitem" tabindex="0" @click="$emit('cloud-record')">
        <el-icon class="menu-item-icon"><VideoCamera /></el-icon>{{ t('channelContextMenu.cloudRecord') }}
      </div>
      <div class="menu-item" role="menuitem" tabindex="0" @click="$emit('device-record')">
        <el-icon class="menu-item-icon"><Files /></el-icon>{{ t('channelContextMenu.deviceRecord') }}
      </div>
      <div class="menu-item" role="menuitem" tabindex="0" @click="$emit('timeline')">
        <el-icon class="menu-item-icon"><Timer /></el-icon>{{ t('channelContextMenu.timeline') }}
      </div>
    </template>
    <template v-else>
      <div v-if="isDevice" class="menu-item" role="menuitem" tabindex="0" @click="$emit('sync-catalog')">
        <el-icon class="menu-item-icon"><Setting /></el-icon>{{ t('channelContextMenu.syncCatalog') }}
      </div>
      <div class="menu-item" role="menuitem" tabindex="0" @click="$emit('create-child')">
        <el-icon class="menu-item-icon"><Plus /></el-icon>{{ t('channelContextMenu.createChild') }}
      </div>
      <div class="menu-item" role="menuitem" tabindex="0" @click="$emit('rename')">
        <el-icon class="menu-item-icon"><Edit /></el-icon>{{ t('channelContextMenu.rename') }}
      </div>
      <div class="menu-item danger" role="menuitem" tabindex="0" @click="$emit('delete-node')">
        <el-icon class="menu-item-icon"><Delete /></el-icon>{{ t('channelContextMenu.deleteNode') }}
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { VideoPlay, CloseBold, VideoCamera, Files, Timer, Setting, Plus, Edit, Delete } from '@element-plus/icons-vue'

const { t } = useI18n()

defineProps<{
  visible: boolean
  x: number
  y: number
  targetType: 'channel' | 'folder'
  canPlay: boolean
  isPlaying: boolean
  isDevice: boolean
}>()

defineEmits<{
  play: []
  stop: []
  'cloud-record': []
  'device-record': []
  timeline: []
  'sync-catalog': []
  'create-child': []
  rename: []
  'delete-node': []
}>()
</script>

<style scoped>
.tree-context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,.12);
  padding: 4px 0;
  min-width: 150px;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.menu-item:hover {
  background: var(--el-fill-color-light);
}
.menu-item.danger {
  color: var(--el-color-danger);
}
.menu-item-icon {
  font-size: 14px;
}
</style>
