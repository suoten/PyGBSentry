<template>
  <div class="login-page">
    <div class="login-wrapper">
      <div class="login-left">
        <div class="login-brand">
          <div class="login-brand__logo">
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <!-- 深邃宇宙 -->
                <radialGradient id="deepSpace" cx="30%" cy="30%" r="70%">
                  <stop offset="0%" stop-color="#2a3f5f"/>
                  <stop offset="40%" stop-color="#1a2542"/>
                  <stop offset="100%" stop-color="#0a0f1a"/>
                </radialGradient>
                
                <!-- 霓虹渐变 -->
                <linearGradient id="neonGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#00ffff"/>
                  <stop offset="50%" stop-color="#00d4ff"/>
                  <stop offset="100%" stop-color="#0080ff"/>
                </linearGradient>
                
                <!-- 多层发光 -->
                <filter id="multiGlow" x="-100%" y="-100%" width="300%" height="300%">
                  <feGaussianBlur stdDeviation="2" result="blur1"/>
                  <feGaussianBlur stdDeviation="4" result="blur2"/>
                  <feGaussianBlur stdDeviation="8" result="blur3"/>
                  <feMerge>
                    <feMergeNode in="blur3"/>
                    <feMergeNode in="blur2"/>
                    <feMergeNode in="blur1"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
                
                <!-- 脉冲动画 -->
                <filter id="pulseGlow">
                  <feGaussianBlur stdDeviation="3" result="blur"/>
                  <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
              </defs>
              
              <!-- 背景 -->
              <rect width="32" height="32" rx="14" fill="url(#deepSpace)"/>
              
              <!-- 粒子点阵背景 -->
              <g opacity="0.3">
                <circle cx="6" cy="6" r="0.5" fill="#00ffff"/>
                <circle cx="12" cy="4" r="0.5" fill="#00ffff"/>
                <circle cx="20" cy="5" r="0.5" fill="#00ffff"/>
                <circle cx="26" cy="8" r="0.5" fill="#00ffff"/>
                <circle cx="4" cy="14" r="0.5" fill="#00ffff"/>
                <circle cx="28" cy="16" r="0.5" fill="#00ffff"/>
                <circle cx="7" cy="26" r="0.5" fill="#00ffff"/>
                <circle cx="16" cy="28" r="0.5" fill="#00ffff"/>
                <circle cx="25" cy="25" r="0.5" fill="#00ffff"/>
              </g>
              
              <!-- 外环 - 双虚线 -->
              <circle cx="16" cy="16" r="14" fill="none" stroke="rgba(0,255,255,0.08)" stroke-width="0.5" stroke-dasharray="6 3"/>
              <circle cx="16" cy="16" r="12" fill="none" stroke="rgba(0,255,255,0.15)" stroke-width="0.8" stroke-dasharray="12 6"/>
              
              <!-- 能量环 -->
              <circle cx="16" cy="16" r="9" fill="none" stroke="url(#neonGrad)" stroke-width="1.5" filter="url(#multiGlow)" opacity="0.9">
                <animate attributeName="r" values="9;9.5;9" dur="2s" repeatCount="indefinite"/>
                <animate attributeName="opacity" values="0.9;0.6;0.9" dur="2s" repeatCount="indefinite"/>
              </circle>
              
              <!-- 内环 -->
              <circle cx="16" cy="16" r="6" fill="none" stroke="rgba(0,255,255,0.4)" stroke-width="1"/>
              
              <!-- 主门 - 外框 -->
              <path d="M10 7L26 16L10 25Z" fill="none" stroke="url(#neonGrad)" stroke-width="2" filter="url(#multiGlow)"/>
              
              <!-- 主门 - 填充 -->
              <path d="M11 8L24 16L11 24Z" fill="url(#neonGrad)" filter="url(#pulseGlow)" opacity="0.9"/>
              
              <!-- 门内深渊 -->
              <path d="M13 10L21 16L13 22Z" fill="#0a0f1a"/>
              
              <!-- 门内核心光 -->
              <path d="M14 11.5L19 16L14 20.5Z" fill="#00ffff" filter="url(#multiGlow)"/>
              
              <!-- 射线 -->
              <g opacity="0.7">
                <line x1="26" y1="16" x2="31" y2="16" stroke="#00ffff" stroke-width="1.5" stroke-linecap="round"/>
                <line x1="25" y1="12" x2="30" y2="9" stroke="#00d4ff" stroke-width="1" stroke-linecap="round"/>
                <line x1="25" y1="20" x2="30" y2="23" stroke="#00d4ff" stroke-width="1" stroke-linecap="round"/>
                <line x1="24" y1="10" x2="28" y2="6" stroke="#0080ff" stroke-width="0.5" stroke-linecap="round"/>
                <line x1="24" y1="22" x2="28" y2="26" stroke="#0080ff" stroke-width="0.5" stroke-linecap="round"/>
              </g>
              
              <!-- 中心星 -->
              <circle cx="16" cy="16" r="1" fill="#ffffff" filter="url(#multiGlow)">
                <animate attributeName="r" values="1;1.3;1" dur="1.5s" repeatCount="indefinite"/>
              </circle>
            </svg>
          </div>
          <div class="login-brand__info">
            <h1 class="login-brand__name">{{ branding.product_name }}</h1>
            <p class="login-brand__welcome">{{ branding.welcome_text }}</p>
          </div>
        </div>
        <div class="login-slogan">
          <h2 class="login-slogan__title">{{ t('login.sloganTitle') }}</h2>
          <p class="login-slogan__desc">{{ t('login.sloganDesc') }}</p>
          <ul class="login-slogan__features">
            <li>{{ t('login.sloganFeature1') }}</li>
            <li>{{ t('login.sloganFeature2') }}</li>
          </ul>
        </div>
      </div>

      <div class="login-right">
        <div class="login-form-wrapper">
          <div class="login-form-header">
            <h3 class="login-form__title">{{ t('login.formTitle') }}</h3>
            <p class="login-form__hint">{{ t('login.formHint') }}</p>
          </div>

          <el-form ref="formRef" :model="form" :rules="loginRules" label-position="top" class="login-form">
            <el-form-item :label="t('login.username')" prop="username">
              <el-input
                v-model="form.username"
                :placeholder="t('login.usernameRequired')"
                clearable
                autocomplete="username"
                @keyup.enter="handleLogin"
              >
                <template #prefix>
                  <el-icon><User /></el-icon>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item :label="t('login.password')" prop="password">
              <el-input
                v-model="form.password"
                type="password"
                :placeholder="t('login.passwordRequired')"
                show-password
                clearable
                autocomplete="current-password"
                @keyup.enter="handleLogin"
              >
                <template #prefix>
                  <el-icon><Lock /></el-icon>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item :label="t('login.otpLabel')">
              <el-input
                v-model="form.otp_code"
                :placeholder="t('login.otpPlaceholder')"
                clearable
                inputmode="numeric"
                autocomplete="one-time-code"
                @keyup.enter="handleLogin"
              >
                <template #prefix>
                  <el-icon><Key /></el-icon>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item class="login-form__actions">
              <el-button type="primary" class="login-btn" @click="handleLogin" :loading="loading">
                {{ t('login.loginBtn') }}
              </el-button>
            </el-form-item>
            <el-form-item v-if="!isServerEdition && allowPublicRegistration" class="login-form__secondary">
              <el-button text class="register-link" @click="router.push('/register')">{{ t('login.noAccount') }}</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="login-footer">
          <span class="login-footer__copyright">© {{ currentYear }} {{ branding.product_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import api from '@/utils/http'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Key } from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'
import { showSuccess } from '../utils/feedback'
import { useUserStore } from '@/stores/user'
import { useI18n } from 'vue-i18n'
import { getBrandingCache } from '@/utils/brandingCache'  // FIX: [2026-07-04] 缺失品牌缓存导入 [全栈工程师]

const { t } = useI18n()

const router = useRouter()
const currentYear = new Date().getFullYear()
const isServerEdition = (import.meta.env.VITE_APP_EDITION || 'oss') === 'server'
const allowPublicRegistration = String(import.meta.env.VITE_ALLOW_PUBLIC_REGISTRATION || '') === 'true'
const formRef = ref<FormInstance>()
const form = ref({
  username: '',
  password: '',
  otp_code: ''
})
const loginRules = reactive<FormRules>({
  username: [
    { required: true, message: () => t('login.usernameRequired'), trigger: 'blur' },
    { min: 2, max: 64, message: () => t('login.usernameLength'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: () => t('login.passwordRequired'), trigger: 'blur' },
    // FIX: [2026-07-16 P1] 与注册页/后端校验对齐：min 8 而非 6
    { min: 8, max: 128, message: () => t('login.passwordLength'), trigger: 'blur' }
  ]
})
const loading = ref(false)
const branding = ref({
  product_name: 'PyGBSentry',
  welcome_text: 'Welcome to PyGBSentry'
})

const handleLogin = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const normalizedUsername = form.value.username.trim()
  form.value.username = normalizedUsername
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('username', normalizedUsername)
    formData.append('password', form.value.password)
    if (form.value.otp_code) formData.append('otp_code', form.value.otp_code)
    
    const res = await api.post('/api/v1/login/access-token', formData)
    const accessToken = res.data?.access_token
    if (!accessToken || typeof accessToken !== 'string') {
      throw new Error(t('login.tokenMissing', 'Login response error: no valid token received'))  // FIXED: 硬编码中文→i18n
    }
    try { sessionStorage.setItem('token', accessToken) } catch { /* P0-4: sessionStorage 防 XSS 持久窃取 */ }
    if (res.data?.refresh_token) { try { sessionStorage.setItem('refresh_token', res.data.refresh_token) } catch { /* P0-4: sessionStorage */ } }
    const userStore = useUserStore()
    userStore.setAuth({
      token: accessToken,
      username: normalizedUsername,
      role: res.data?.role || '',
      is_superuser: res.data?.is_superuser || false,
      tenant_id: res.data?.tenant_id || 'default'
    })
    showSuccess(t('login.loginSuccess', 'Login successful'))  // FIXED: 硬编码中文→i18n
    router.push(isServerEdition ? '/plugins' : '/dashboard')
  } catch (e: unknown) {
    const ax = (e && typeof e === 'object' && 'response' in e) ? e as { response?: { data?: Record<string, unknown> } } : null
    const raw = ax?.response?.data && typeof ax.response.data === 'object' && ax.response.data !== null && 'detail' in ax.response.data
      ? (ax.response.data as { detail?: unknown }).detail
      : undefined
    const msg = typeof raw === 'string'
      ? raw
      : String(
          ax?.response?.data && typeof ax.response.data === 'object' && ax.response.data !== null && 'message' in ax.response.data
            ? (ax.response.data as { message?: unknown }).message
            : ''
        )
    if (msg === 'OTP_REQUIRED') {
      ElMessage.warning(t('login.otpRequired', 'This account has 2FA enabled, please enter OTP code'))  // FIXED: 硬编码中文→i18n
    } else if (msg === 'OTP_INVALID') {
      ElMessage.error(t('login.otpInvalid', 'Invalid OTP code'))  // FIXED: 硬编码中文→i18n
    } else {
      const friendly = getFriendlyError(e)
      ElMessage.error(
        friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || t('login.loginFailed', 'Login failed, please check username and password')  // FIXED: 硬编码中文→i18n
      )
    }
    form.value.password = ''
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const cached = getBrandingCache()
  if (cached) {
    branding.value = {
      product_name: cached.product_name || 'PyGBSentry',
      welcome_text: cached.welcome_text || 'Welcome to PyGBSentry'
    }
  }
})
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  background: #ffffff;
}

.login-wrapper {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 100vh;
}

.login-left {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 44px 68px;
  background:
    radial-gradient(circle at top left, rgba(64, 158, 255, 0.22), transparent 26%),
    radial-gradient(circle at bottom right, rgba(22, 119, 255, 0.26), transparent 24%),
    linear-gradient(155deg, #1f2a44 0%, #1f2f50 56%, #243861 100%);
  color: #fff;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 26px;
}

.login-brand__logo {
  width: 58px;
  height: 58px;
  flex-shrink: 0;
}

.login-brand__logo svg {
  width: 100%;
  height: 100%;
}

.login-brand__name {
  margin: 0;
  font-size: 42px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--logo-title-text-color);
}

.login-brand__welcome {
  margin: 4px 0 0;
  font-size: 15px;
  color: rgba(255, 255, 255, 0.82);
}

.login-brand__info {
  display: flex;
  flex-direction: column;
}

.login-slogan {
  max-width: 560px;
}

.login-slogan__title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.4;
  letter-spacing: 0;
}

.login-slogan__desc {
  margin: 10px 0 0;
  font-size: 18px;
  color: rgba(255, 255, 255, 0.86);
  line-height: 1.5;
  max-width: 460px;
}

.login-slogan__features {
  display: none;
}

.login-right {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 40px 48px;
  background: #ffffff;
}

.login-form-wrapper {
  width: 100%;
  max-width: 420px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.login-form-header {
  margin-bottom: 28px;
  text-align: center;
}

.login-form__title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.login-form__hint {
  display: none;
}

.login-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--el-text-color-regular);
  padding-bottom: 8px;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: var(--el-border-radius-base);
  box-shadow: 0 0 0 1px var(--el-border-color) inset;
  min-height: 42px;
  background: #f8fafc;
  transition: all var(--transition-time-02);
}

.login-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--el-border-color-hover) inset;
  background: #ffffff;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
  background: #ffffff;
}

.login-form :deep(.el-input__prefix) {
  color: var(--el-text-color-placeholder);
}

.login-form__actions {
  margin-top: 28px;
  margin-bottom: 8px;
}

.login-btn {
  width: 100%;
  height: 46px;
  font-size: 15px;
  font-weight: 600;
  border-radius: var(--el-border-radius-base);
  box-shadow: none;
}

.login-form__secondary {
  margin-top: 8px;
  text-align: center;
}

.register-link {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  transition: color var(--transition-time-02);
}

.register-link:hover {
  color: var(--el-color-primary);
}

.login-footer {
  margin-top: 24px;
  text-align: center;
}

.login-footer__copyright {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

@media (max-width: 900px) {
  .login-wrapper {
    grid-template-columns: 1fr;
  }

  .login-left {
    display: none;
  }

  .login-right {
    padding: 40px 20px;
    box-shadow: none;
    background: transparent;
  }
}
</style>
