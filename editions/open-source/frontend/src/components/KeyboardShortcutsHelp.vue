<template>
  <AppDialog
    v-model="visible"
    title="键盘快捷键"
    size="medium"
    @update:model-value="handleClose"
  >
    <div class="shortcut-list">
      <div v-for="group in groupedShortcuts" :key="group.name" class="shortcut-group">
        <div class="shortcut-group-title">{{ group.name }}</div>
        <div class="shortcut-items">
          <div
            v-for="item in group.items"
            :key="item.key"
            class="shortcut-item"
          >
            <div class="shortcut-keys">
              <template v-if="item.key.includes('g ')">
                <kbd class="kbd kbd--primary">g</kbd>
                <span class="key-separator">+</span>
                <kbd class="kbd">{{ item.key.split(' ')[1] }}</kbd>
              </template>
              <template v-else-if="item.key.startsWith('Ctrl') || item.key.startsWith('Meta')">
                <kbd class="kbd kbd--small">{{ item.key.includes('Ctrl') ? 'Ctrl' : '⌘' }}</kbd>
                <span class="key-separator">+</span>
                <kbd class="kbd kbd--small">{{ item.key.split('+')[1]?.trim() }}</kbd>
              </template>
              <template v-else>
                <kbd class="kbd">{{ item.key }}</kbd>
              </template>
            </div>
            <span class="shortcut-desc">{{ item.description }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="shortcut-tip">
      <el-icon><InfoFilled /></el-icon>
      <span>按 <kbd class="kbd kbd--inline">?</kbd> 或 <kbd class="kbd kbd--inline">?</kbd> 键可随时打开此帮助</span>
    </div>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import AppDialog from './common/AppDialog.vue'

interface ShortcutItem {
  key: string
  description: string
  group: string
}

interface Props {
  modelValue: boolean
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

/** 快捷键分组数据 */
const shortcutGroups: ShortcutItem[] = [
  // 导航
  { key: 'g d', description: '跳转到仪表盘', group: '导航' },
  { key: 'g m', description: '跳转到监控中心', group: '导航' },
  { key: 'g c', description: '跳转到设备列表', group: '导航' },
  { key: 'g a', description: '跳转到告警中心', group: '导航' },
  { key: 'g r', description: '跳转到录像回放', group: '导航' },
  { key: 'g p', description: '跳转到运维中心', group: '导航' },
  { key: 'g u', description: '跳转到用户管理', group: '导航' },
  { key: 'g s', description: '跳转到系统设置', group: '导航' },
  // 操作
  { key: 'Escape', description: '关闭弹窗 / 取消操作', group: '操作' },
  { key: 'Ctrl+K', description: '打开帮助页面', group: '操作' },
  { key: 'r', description: '刷新当前页面', group: '操作' },
]

/** 按分组聚合快捷键 */
const groupedShortcuts = computed(() => {
  const groups: Record<string, ShortcutItem[]> = {}
  for (const item of shortcutGroups) {
    if (!groups[item.group]) {
      groups[item.group] = []
    }
    groups[item.group].push(item)
  }
  return Object.entries(groups).map(([name, items]) => ({ name, items }))
})

const handleClose = () => {
  visible.value = false
}
</script>

<style scoped>
.shortcut-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.shortcut-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.shortcut-group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.shortcut-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.shortcut-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
}

.shortcut-keys {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.key-separator {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 26px;
  padding: 0 8px;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.kbd--primary {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
}

.kbd--small {
  min-width: 24px;
  height: 24px;
  padding: 0 6px;
  font-size: 12px;
}

.kbd--inline {
  min-width: auto;
  height: auto;
  padding: 2px 6px;
  font-size: 12px;
}

.shortcut-desc {
  font-size: 13px;
  color: var(--el-text-color-regular);
  text-align: right;
}

.shortcut-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.shortcut-tip .el-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}
</style>
