<template>
  <el-dialog
    v-model="authDialogVisible"
    :title="t('plugin.officialAccountTitle')"
    width="420px"
    :close-on-click-modal="false"
    destroy-on-close
    class="official-account-dialog"
  >
    <el-alert
      v-if="authIntentVisible"
      :title="t('plugin.officialAccountRequired')"
      :description="t('plugin.officialAccountRequiredDesc')"
      type="info"
      show-icon
      :closable="false"
      class="mb-3"
    />
    <el-tabs v-model="authTab">
      <el-tab-pane :label="t('plugin.officialLoginTab')" name="login">
        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          label-position="top"
          @submit.prevent="submitLogin"
        >
          <el-form-item :label="t('common.username')" prop="username">
            <el-input
              v-model="loginForm.username"
              name="official-username"
              :placeholder="t('common.pleaseInput')"
              autocomplete="off"
            />
          </el-form-item>
          <el-form-item :label="t('common.password')" prop="password">
            <el-input
              v-model="loginForm.password"
              type="password"
              show-password
              name="official-password"
              :placeholder="t('common.pleaseInput')"
              autocomplete="new-password"
              @keyup.enter="submitLogin"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane :label="t('plugin.officialRegisterTab')" name="register">
        <el-form
          ref="registerFormRef"
          :model="registerForm"
          :rules="registerRules"
          label-position="top"
          @submit.prevent="submitRegister"
        >
          <el-form-item :label="t('common.username')" prop="username">
            <el-input
              v-model="registerForm.username"
              name="official-register-username"
              :placeholder="t('common.pleaseInput')"
              autocomplete="off"
            />
          </el-form-item>
          <el-form-item :label="t('common.password')" prop="password">
            <el-input
              v-model="registerForm.password"
              type="password"
              show-password
              name="official-register-password"
              :placeholder="t('common.pleaseInput')"
              autocomplete="new-password"
              @keyup.enter="submitRegister"
            />
          </el-form-item>
          <el-form-item :label="t('plugin.officialEmailLabel')" prop="email">
            <el-input
              v-model="registerForm.email"
              name="official-register-email"
              :placeholder="t('common.pleaseInput')"
              autocomplete="off"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
    <el-alert
      v-if="authError"
      :title="authError"
      type="error"
      show-icon
      :closable="false"
      class="mt-1"
    />
    <template #footer>
      <el-button @click="authDialogVisible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="authLoading" @click="authTab === 'login' ? submitLogin() : submitRegister()">
        {{ authTab === 'login' ? t('plugin.officialLoginSubmit') : t('plugin.officialRegisterSubmit') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { FormInstance, FormItemRule } from 'element-plus'
import i18n from '@/locales'
import { useOfficialAccount } from '../../composables/useOfficialAccount'

const t = i18n.global.t

const {
  authDialogVisible,
  authTab,
  authIntentVisible,
  authLoading,
  authError,
  submitOfficialAuth,
} = useOfficialAccount()

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', email: '' })

// 前端必填/长度校验：用户名 ≥3、密码 ≥6；邮箱选填但格式需合法
const accountRules: Record<string, FormItemRule[]> = {
  username: [
    { required: true, message: t('common.required'), trigger: 'blur' },
    { min: 3, message: t('plugin.officialUsernameMin'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('common.required'), trigger: 'blur' },
    { min: 6, message: t('plugin.officialPasswordMin'), trigger: 'blur' },
  ],
}
const loginRules = { ...accountRules }
const registerRules: Record<string, FormItemRule[]> = {
  ...accountRules,
  email: [{ type: 'email', message: t('plugin.officialEmailInvalid'), trigger: 'blur' }],
}

// 弹窗每次打开时重置表单与校验状态；切换页签时清空错误提示
watch(authDialogVisible, (visible) => {
  if (!visible) return
  loginForm.username = ''
  loginForm.password = ''
  registerForm.username = ''
  registerForm.password = ''
  registerForm.email = ''
})
watch(authTab, () => {
  authError.value = ''
})

const validateForm = async (formRef: FormInstance | undefined): Promise<boolean> => {
  if (!formRef) return true
  try {
    await formRef.validate()
    return true
  } catch {
    return false
  }
}

const submitLogin = async () => {
  if (!(await validateForm(loginFormRef.value))) return
  await submitOfficialAuth({ ...loginForm, email: '' })
}

const submitRegister = async () => {
  if (!(await validateForm(registerFormRef.value))) return
  await submitOfficialAuth({ ...registerForm })
}
</script>
