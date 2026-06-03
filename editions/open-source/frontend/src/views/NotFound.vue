<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-[var(--app-content-bg-color)]">
    <el-result icon="warning" title="404" sub-title="抱歉，页面不存在或您没有访问权限。">
      <template #extra>
        <div class="mt-4 flex justify-center gap-4">
          <router-link to="/dashboard">
            <el-button type="primary" size="large">返回工作台</el-button>
          </router-link>
          <router-link to="/login">
            <el-button size="large">重新登录</el-button>
          </router-link>
        </div>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
</script>
