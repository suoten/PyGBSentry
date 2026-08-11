<template>
  <div class="setup-page">
    <div class="setup-wrapper">
      <!-- 步骤指示器 -->
      <el-steps :active="activeStep" finish-status="success" align-center class="setup-steps">
        <el-step :title="t('setupPage.stepSystem')" />
        <el-step :title="t('setupPage.stepSip')" />
        <el-step :title="t('setupPage.stepMedia')" />
        <el-step :title="t('setupPage.stepComplete')" />
      </el-steps>

      <!-- Step 0: 系统检查 -->
      <div v-if="activeStep === 0" class="setup-step-content">
        <h2 class="setup-step-title">{{ t('setupPage.connectivityCheck') }}</h2>
        <p class="setup-step-desc">{{ t('setupPage.systemCheckDesc') }}</p>

        <div class="check-list">
          <div class="check-item">
            <div class="check-item__left">
              <el-icon class="check-item__icon" :class="status.db_ok ? 'check-item__icon--ok' : 'check-item__icon--err'">
                <CircleCheck v-if="status.db_ok" />
                <CircleClose v-else />
              </el-icon>
              <span class="check-item__label">{{ t('setupPage.database') }}</span>
            </div>
            <el-tag size="small" :type="status.db_ok ? 'success' : 'danger'">
              {{ status.db_ok ? t('setupPage.normal') : t('setupPage.abnormal') }}
            </el-tag>
          </div>
          <p v-if="!status.db_ok && status.db_detail" class="check-item__detail">{{ status.db_detail }}</p>

          <div class="check-item">
            <div class="check-item__left">
              <el-icon class="check-item__icon" :class="status.zlm_ok ? 'check-item__icon--ok' : 'check-item__icon--err'">
                <CircleCheck v-if="status.zlm_ok" />
                <CircleClose v-else />
              </el-icon>
              <span class="check-item__label">{{ t('setupPage.zlmService') }}</span>
            </div>
            <el-tag size="small" :type="status.zlm_ok ? 'success' : 'danger'">
              {{ status.zlm_ok ? t('setupPage.normal') : t('setupPage.abnormal') }}
            </el-tag>
          </div>
          <p v-if="!status.zlm_ok && status.zlm_detail" class="check-item__detail">{{ status.zlm_detail }}</p>
          <p v-if="!status.zlm_ok" class="check-item__hint">
            {{ t('setupPage.zlmHint', { host: status.zlm_host, port: status.zlm_http_port }) }}
          </p>
        </div>

        <el-button class="mt-4" size="small" :loading="loading" @click="loadStatus">
          {{ t('setupPage.recheck') }}
        </el-button>

        <div class="setup-actions">
          <el-button type="primary" :disabled="!status.db_ok" @click="activeStep = 1">
            {{ t('setupPage.nextStep') }}
          </el-button>
          <el-button @click="$router.push('/dashboard')">{{ t('setupPage.later') }}</el-button>
        </div>
      </div>

      <!-- Step 1: SIP 配置 -->
      <div v-if="activeStep === 1" class="setup-step-content">
        <h2 class="setup-step-title">{{ t('setupPage.sipConfig') }}</h2>
        <p class="setup-step-desc">{{ t('setupPage.sipConfigDesc') }}</p>

        <el-alert type="info" :closable="false" class="mb-4">
          <template #title>
            {{ t('setupPage.sipConfigTip') }}
          </template>
        </el-alert>

        <el-form label-position="top" class="setup-form">
          <el-form-item :label="t('setupPage.sipId')">
            <el-input :model-value="sipConfig.sip_id" readonly>
              <template #append>
                <el-button @click="copyToClipboard(sipConfig.sip_id)">{{ t('setupPage.copy') }}</el-button>
              </template>
            </el-input>
            <p class="form-item-hint">{{ t('setupPage.sipIdHint') }}</p>
          </el-form-item>
          <el-form-item :label="t('setupPage.sipDomain')">
            <el-input :model-value="sipConfig.sip_domain" readonly>
              <template #append>
                <el-button @click="copyToClipboard(sipConfig.sip_domain)">{{ t('setupPage.copy') }}</el-button>
              </template>
            </el-input>
            <p class="form-item-hint">{{ t('setupPage.sipDomainHint') }}</p>
          </el-form-item>
          <el-form-item :label="t('setupPage.sipPort')">
            <el-input :model-value="sipConfig.sip_port" readonly />
            <p class="form-item-hint">{{ t('setupPage.sipPortHint') }}</p>
          </el-form-item>
          <el-form-item :label="t('setupPage.devicePassword')">
            <el-input :model-value="sipConfig.sip_password" readonly>
              <template #append>
                <el-button @click="copyToClipboard(sipConfig.sip_password)">{{ t('setupPage.copy') }}</el-button>
              </template>
            </el-input>
            <p class="form-item-hint">{{ t('setupPage.devicePasswordHint') }}</p>
          </el-form-item>
        </el-form>

        <div class="setup-actions">
          <el-button @click="activeStep = 0">{{ t('setupPage.prevStep') }}</el-button>
          <el-button type="primary" @click="activeStep = 2">{{ t('setupPage.nextStep') }}</el-button>
        </div>
      </div>

      <!-- Step 2: 媒体节点 -->
      <div v-if="activeStep === 2" class="setup-step-content">
        <h2 class="setup-step-title">{{ t('setupPage.mediaConfig') }}</h2>
        <p class="setup-step-desc">{{ t('setupPage.mediaConfigDesc') }}</p>

        <div class="check-list">
          <div class="check-item">
            <div class="check-item__left">
              <el-icon class="check-item__icon" :class="status.zlm_ok ? 'check-item__icon--ok' : 'check-item__icon--err'">
                <CircleCheck v-if="status.zlm_ok" />
                <CircleClose v-else />
              </el-icon>
              <span class="check-item__label">ZLMediaKit</span>
            </div>
            <el-tag size="small" :type="status.zlm_ok ? 'success' : 'danger'">
              {{ status.zlm_ok ? t('setupPage.normal') : t('setupPage.abnormal') }}
            </el-tag>
          </div>
          <p v-if="status.zlm_ok" class="check-item__hint">
            {{ t('setupPage.zlmReadyHint', { host: status.zlm_host, port: status.zlm_http_port }) }}
          </p>
          <p v-else class="check-item__hint">
            {{ t('setupPage.zlmNotReadyHint') }}
          </p>
        </div>

        <el-alert v-if="!status.zlm_ok" type="warning" :closable="false" class="mt-3">
          <template #title>
            {{ t('setupPage.zlmWaitHint') }}
          </template>
        </el-alert>

        <div class="setup-actions">
          <el-button @click="activeStep = 1">{{ t('setupPage.prevStep') }}</el-button>
          <el-button type="primary" @click="activeStep = 3">{{ t('setupPage.nextStep') }}</el-button>
        </div>
      </div>

      <!-- Step 3: 完成 -->
      <div v-if="activeStep === 3" class="setup-step-content">
        <div class="setup-complete">
          <el-icon class="setup-complete__icon"><CircleCheckFilled /></el-icon>
          <h2 class="setup-step-title">{{ t('setupPage.readyToGo') }}</h2>
          <p class="setup-step-desc">{{ t('setupPage.readyDesc') }}</p>

          <div class="setup-checklist">
            <div class="setup-checklist__item">
              <el-icon><Check /></el-icon>
              <span>{{ t('setupPage.checklistDb') }}</span>
            </div>
            <div class="setup-checklist__item">
              <el-icon><Check /></el-icon>
              <span>{{ t('setupPage.checklistSip') }}</span>
            </div>
            <div class="setup-checklist__item">
              <el-icon :class="status.zlm_ok ? '' : 'setup-checklist__item--pending'">
                <Check v-if="status.zlm_ok" />
                <Loading v-else class="is-loading" />
              </el-icon>
              <span>{{ t('setupPage.checklistZlm') }}</span>
            </div>
          </div>

          <div class="setup-actions">
            <el-button @click="activeStep = 2">{{ t('setupPage.prevStep') }}</el-button>
            <el-button type="primary" :loading="completing" @click="complete">
              {{ t('setupPage.completeAndEnter') }}
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { CircleCheck, CircleClose, CircleCheckFilled, Check, Loading } from '@element-plus/icons-vue'
import { getFriendlyError } from '../utils/errorMessage'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const completing = ref(false)
const activeStep = ref(0)
const status = ref({
  wizard_completed: false,
  db_ok: false,
  db_detail: '',
  zlm_ok: false,
  zlm_detail: '',
  zlm_host: '',
  zlm_http_port: 0
})
const sipConfig = ref({
  sip_id: '34020000002000000001',
  sip_domain: '3402000000',
  sip_port: 5060,
  sip_password: ''
})

const loadStatus = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/setup/status')
    status.value = {
      wizard_completed: res.data?.wizard_completed ?? false,
      db_ok: res.data?.db_ok ?? false,
      db_detail: res.data?.db_detail ?? '',
      zlm_ok: res.data?.zlm_ok ?? false,
      zlm_detail: res.data?.zlm_detail ?? '',
      zlm_host: res.data?.zlm_host ?? '',
      zlm_http_port: res.data?.zlm_http_port ?? 0
    }
    if (res.data?.sip_config) {
      sipConfig.value = { ...sipConfig.value, ...res.data.sip_config }
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : (friendly.message || t('setupPage.loadStatusFailed')))
  } finally {
    loading.value = false
  }
}

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('setupPage.copied'))
  } catch {
    ElMessage.warning(t('setupPage.copyFailed'))
  }
}

const complete = async () => {
  completing.value = true
  try {
    await api.post('/api/v1/setup/complete')
    ElMessage.success(t('setupPage.wizardCompleted'))
    router.replace('/dashboard')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    completing.value = false
  }
}

onMounted(() => {
  loadStatus()
})
</script>

<style scoped>
.setup-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--el-bg-color-page);
}

.setup-wrapper {
  max-width: 640px;
  width: 100%;
  padding: 40px;
  border-radius: 16px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.setup-steps {
  margin-bottom: 32px;
}

.setup-step-content {
  min-height: 280px;
}

.setup-step-title {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.setup-step-desc {
  margin: 0 0 24px 0;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.check-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.check-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.check-item__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.check-item__icon {
  font-size: 20px;
}

.check-item__icon--ok {
  color: var(--el-color-success);
}

.check-item__icon--err {
  color: var(--el-color-danger);
}

.check-item__label {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.check-item__detail {
  margin: 4px 16px 0 48px;
  font-size: 13px;
  color: var(--el-color-danger);
}

.check-item__hint {
  margin: 4px 16px 0 48px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.setup-form {
  max-width: 100%;
}

.form-item-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.setup-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 32px;
}

.setup-complete {
  text-align: center;
  padding: 20px 0;
}

.setup-complete__icon {
  font-size: 56px;
  color: var(--el-color-success);
  margin-bottom: 16px;
}

.setup-checklist {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 24px auto;
  max-width: 280px;
  text-align: left;
}

.setup-checklist__item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.setup-checklist__item .el-icon {
  color: var(--el-color-success);
  font-size: 18px;
}

.setup-checklist__item--pending {
  color: var(--el-color-warning);
}
</style>
