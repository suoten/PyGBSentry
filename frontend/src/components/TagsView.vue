<template>
  <div class="tags-view">
    <el-scrollbar class="tags-scroll">
      <div class="tags-inner">
        <div
          v-for="tag in visitedViews"
          :key="tag.fullPath"
          class="tag-item"
          :class="{ 'is-active': tag.fullPath === activeFullPath }"
          @click="go(tag)"
        >
          <span class="tag-title">{{ tag.title }}</span>
          <el-icon
            v-if="!tag.affix"
            class="tag-close"
            @click.stop="onClose(tag)"
          >
            <Close />
          </el-icon>
        </div>
      </div>
    </el-scrollbar>
    <div class="tags-actions">
      <el-dropdown trigger="click" @command="onCommand">
        <el-button size="small" class="actions-btn">
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="close-others">
              <el-icon><Close /></el-icon>
              <span>{{ t('tagsView.closeOthers') }}</span>
            </el-dropdown-item>
            <el-dropdown-item command="close-all">
              <el-icon><Delete /></el-icon>
              <span>{{ t('tagsView.closeAll') }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { ArrowDown, Close, Delete } from '@element-plus/icons-vue'
import { useTagsViewStore, type TagView } from '../stores/tagsView'

const route = useRoute()
const router = useRouter()
const store = useTagsViewStore()
const { t } = useI18n()  // FIXED: 国际化

const visitedViews = computed(() => store.visitedViews)
const activeFullPath = computed(() => String(route.fullPath || route.path))

function go(tag: TagView) {
  if (tag.fullPath === activeFullPath.value) return
  router.push(tag.fullPath)
}

function onClose(tag: TagView) {
  const isActive = tag.fullPath === activeFullPath.value
  store.delView(tag)
  if (!isActive) return
  const last = store.visitedViews[store.visitedViews.length - 1]
  router.push(last ? last.fullPath : '/')
}

function onCommand(cmd: string) {
  const current = store.visitedViews.find(v => v.fullPath === activeFullPath.value)
  if (!current) return
  if (cmd === 'close-others') store.delOthers(current)
  if (cmd === 'close-all') store.delAll()
  const after = store.visitedViews.find(v => v.fullPath === activeFullPath.value) || store.visitedViews[store.visitedViews.length - 1]
  router.push(after ? after.fullPath : '/')
}
</script>

<style scoped>
.tags-view {
  display: flex;
  align-items: center;
  height: var(--tags-view-height);
  padding: 0 14px;
  background: var(--tags-view-bg-color);
  border-bottom: 1px solid var(--tags-view-border-color);
}

.tags-scroll {
  flex: 1;
  overflow: hidden;
}

.tags-inner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
  white-space: nowrap;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: #f8fafc;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  transition: all var(--transition-time-02);
}

.tag-item:hover {
  color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.08);
  border-color: rgba(64, 158, 255, 0.18);
}

.tag-item.is-active {
  color: #fff;
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  box-shadow: none;
}

.tag-item.is-active::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 2px;
  background: #fff;
  border-radius: 50%;
}

.tag-title {
  line-height: 1;
}

.tag-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  font-size: 12px;
  border-radius: 50%;
  transition: all var(--transition-time-02);
}

.tag-close:hover {
  background: rgba(0, 0, 0, 0.1);
}

.tag-item.is-active .tag-close:hover {
  background: rgba(255, 255, 255, 0.2);
}

.tags-actions {
  flex: none;
  margin-left: 8px;
}

.actions-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--el-border-color-lighter);
  background: #f8fafc;
  color: var(--el-text-color-secondary);
  border-radius: 4px;
  transition: all var(--transition-time-02);
}

.actions-btn:hover {
  color: var(--el-color-primary);
  border-color: rgba(64, 158, 255, 0.18);
  background: rgba(64, 158, 255, 0.08);
}

:deep(.el-dropdown-menu__item) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  transition: all var(--transition-time-02);
}

:deep(.el-dropdown-menu__item:hover) {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

:deep(.el-dropdown-menu__item .el-icon) {
  font-size: 14px;
}
</style>
