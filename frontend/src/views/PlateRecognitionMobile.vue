<template>
  <div class="page-stub">
    <el-empty :description="t('common.pageUnderConstruction')" />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<style scoped>
.page-stub { display: flex; align-items: center; justify-content: center; min-height: 60vh; }
</style>
