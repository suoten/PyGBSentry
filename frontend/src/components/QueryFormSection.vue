<template>
  <div class="query-form-section">
    <div 
      v-if="title" 
      class="query-form-header"
      @click="toggleCollapse"
    >
      <div class="query-form-title">
        <el-icon class="filter-icon"><Filter /></el-icon>
        <el-icon v-if="collapsible" class="collapse-icon" :class="{ 'is-collapsed': isCollapsed }">
          <ArrowRight />
        </el-icon>
        <span class="title-text">{{ title }}</span>
      </div>
      <div v-if="collapsible" class="query-form-toggle">
        <div class="toggle-btn">
          <span v-if="isCollapsed">{{ t('queryForm.expand') }}</span>
          <span v-else>{{ t('queryForm.collapse') }}</span>
        </div>
      </div>
    </div>
    <div v-show="!isCollapsed" class="query-form-content">
      <el-form :label-width="labelWidth" :class="formClass">
        <slot />
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowRight, Filter } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    labelWidth?: string
    formClass?: string
    title?: string
    collapsible?: boolean
    defaultCollapsed?: boolean
  }>(),
  {
    labelWidth: '120px',
    formClass: 'grid grid-cols-1 md:grid-cols-2 gap-x-4',
    collapsible: true,
    defaultCollapsed: true
  }
)

const isCollapsed = ref(props.defaultCollapsed)

const toggleCollapse = () => {
  if (props.collapsible) {
    isCollapsed.value = !isCollapsed.value
  }
}
</script>

<style scoped>
.query-form-section {
  width: 100%;
  margin-bottom: 14px;
}

.query-form-section:last-child {
  margin-bottom: 0;
}

.query-form-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  box-shadow: none;
  transition: all var(--transition-time-02);
}

.query-form-header:hover {
  border-color: #d5d9e0;
  background: #fafafa;
}

.query-form-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.filter-icon {
  color: var(--el-color-primary);
  font-size: 14px;
}

.collapse-icon {
  transition: transform var(--transition-time-02);
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.collapse-icon.is-collapsed {
  transform: rotate(0deg);
}

.collapse-icon:not(.is-collapsed) {
  transform: rotate(90deg);
}

.title-text {
  letter-spacing: 0.2px;
}

.query-form-toggle {
  display: flex;
  align-items: center;
}

.toggle-btn {
  font-size: 11px;
  font-weight: 500;
  color: var(--el-color-primary);
  padding: 2px 10px;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
  transition: all var(--transition-time-02);
}

.toggle-btn:hover {
  background: var(--el-color-primary-light-8);
}

.query-form-content {
  margin-top: 10px;
  padding: 14px 14px 8px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  box-shadow: none;
}
</style>
