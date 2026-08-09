<template>
  <div class="h-screen flex items-center justify-center">
    <el-card class="w-96">
      <template #header>
        <div class="text-center">
          <div class="font-bold text-xl" style="color: var(--el-text-color-primary)">{{ t('registerPage.title') }}</div>
        </div>
      </template>
      <el-form ref="formRef" :model="form" :rules="registerRules" label-position="top">
        <el-form-item :label="t('registerPage.username')" prop="username">
          <el-input v-model="form.username" :placeholder="t('register.enterUsername')" clearable />  <!-- FIXED: A-05 硬编码中文→t() -->
        </el-form-item>
        <el-form-item :label="t('registerPage.email')" prop="email">
          <el-input v-model="form.email" :placeholder="t('register.emailOptional')" clearable />  <!-- FIXED: A-05 硬编码中文→t() -->
        </el-form-item>
        <el-form-item :label="t('registerPage.password')" prop="password">
          <el-input v-model="form.password" type="password" :placeholder="t('auth.enterPassword')" show-password clearable />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item :label="t('registerPage.confirmPassword')" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" :placeholder="t('auth.reenterPassword')" show-password clearable />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="w-full" :loading="loading" @click="handleRegister">{{ t('registerPage.submit') }}</el-button>
        </el-form-item>
        <el-form-item>
          <el-button text class="w-full" @click="router.push('/login')">{{ t('registerPage.hasAccount') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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

const registerRules = computed<FormRules>(() => ({
  username: [
    { required: true, message: t('registerPage.ruleUsernameRequired'), trigger: 'blur' },
    { min: 2, max: 64, message: t('registerPage.ruleUsernameLength'), trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: t('registerPage.ruleEmailInvalid'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('registerPage.rulePasswordRequired'), trigger: 'blur' },
    { min: 8, max: 128, message: t('registerPage.rulePasswordLength'), trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: t('registerPage.ruleConfirmRequired'), trigger: 'blur' },
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
}))

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
    ElMessage.success(t('registerPage.registerSuccess'))
    router.push('/login')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || t('registerPage.registerFailed'))
  } finally {
    loading.value = false
  }
}
</script>
