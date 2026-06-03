<template>
  <div class="h-screen flex items-center justify-center">
    <el-card class="w-96">
      <template #header>
        <div class="text-center">
          <div class="font-bold text-xl" style="color: var(--el-text-color-primary)">注册账号</div>
        </div>
      </template>
      <el-form ref="formRef" :model="form" :rules="registerRules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :placeholder="t('register.enterUsername')" clearable />  <!-- FIXED: A-05 硬编码中文→t() -->
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" :placeholder="t('register.emailOptional')" clearable />  <!-- FIXED: A-05 硬编码中文→t() -->
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" :placeholder="t('auth.enterPassword')" show-password clearable />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" :placeholder="t('auth.reenterPassword')" show-password clearable />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="w-full" :loading="loading" @click="handleRegister">注册</el-button>
        </el-form-item>
        <el-form-item>
          <el-button text class="w-full" @click="router.push('/login')">已有账号？去登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import type { FormInstance, FormRules } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'

const { t } = useI18n()  // FIXED: 国际化
const router = useRouter()
const loading = ref(false)
const formRef = ref<FormInstance>()
const form = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const registerRules = reactive<FormRules>({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 64, message: '用户名长度 2-64 个字符', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度 8-128 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule: Record<string, unknown>, value: string, callback: (err?: Error) => void) => {
        if (value && value !== form.value.password) {
          callback(new Error(t('profile.passwordMismatch')))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
})

const handleRegister = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await api.post('/api/v1/register', {
      username: form.value.username.trim(),
      email: form.value.email?.trim() || null,
      password: form.value.password
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>
