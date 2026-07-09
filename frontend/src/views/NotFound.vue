<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-[var(--app-content-bg-color)]">
    <el-result icon="warning" title="404" :sub-title="t('notFound.subTitle')">
      <template #extra>
        <div class="mt-4 flex justify-center gap-4">
          <router-link to="/dashboard">
            <el-button type="primary" size="large">{{ t('notFound.backToDashboard') }}</el-button>
          </router-link>
          <router-link to="/login">
            <el-button size="large">{{ t('notFound.reLogin') }}</el-button>
          </router-link>
        </div>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>
