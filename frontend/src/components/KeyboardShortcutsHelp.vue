<template>
  <AppDialog
    v-model="visible"
    :title="t('shortcutHelp.title')"
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
      <span>{{ t('shortcutHelp.tipPrefix') }} <kbd class="kbd kbd--inline">?</kbd> {{ t('shortcutHelp.tipMiddle') }} <kbd class="kbd kbd--inline">?</kbd> {{ t('shortcutHelp.tipSuffix') }}</span>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.close') }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { InfoFilled } from '@element-plus/icons-vue'
import AppDialog from './common/AppDialog.vue'

const { t } = useI18n()

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
const shortcutGroups = computed<ShortcutItem[]>(() => [
  // 导航
  { key: 'g d', description: t('shortcutHelp.gotoDashboard'), group: t('shortcutHelp.groupNav') },
  { key: 'g m', description: t('shortcutHelp.gotoMonitor'), group: t('shortcutHelp.groupNav') },
  { key: 'g c', description: t('shortcutHelp.gotoDevices'), group: t('shortcutHelp.groupNav') },
  { key: 'g a', description: t('shortcutHelp.gotoAlerts'), group: t('shortcutHelp.groupNav') },
  { key: 'g r', description: t('shortcutHelp.gotoPlayback'), group: t('shortcutHelp.groupNav') },
  { key: 'g p', description: t('shortcutHelp.gotoOps'), group: t('shortcutHelp.groupNav') },
  { key: 'g u', description: t('shortcutHelp.gotoUsers'), group: t('shortcutHelp.groupNav') },
  { key: 'g s', description: t('shortcutHelp.gotoSettings'), group: t('shortcutHelp.groupNav') },
  // 操作
  { key: 'Escape', description: t('shortcutHelp.closeDialog'), group: t('shortcutHelp.groupAction') },
  { key: 'Ctrl+K', description: t('shortcutHelp.openHelp'), group: t('shortcutHelp.groupAction') },
  { key: 'r', description: t('shortcutHelp.refreshPage'), group: t('shortcutHelp.groupAction') },
])

/** 按分组聚合快捷键 */
const groupedShortcuts = computed(() => {
  const groups: Record<string, ShortcutItem[]> = {}
  for (const item of shortcutGroups.value) {
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
