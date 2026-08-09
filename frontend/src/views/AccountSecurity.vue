<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('account.title')" :description="t('account.description')" />
      </template>

    <TableCard class="max-w-2xl">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="font-medium">{{ t('accountSecurity.title') }}</div>
          <el-tag :type="me?.totp_enabled ? 'success' : 'info'">
            {{ me?.totp_enabled ? t('accountSecurity.enabled') : t('accountSecurity.disabled') }}
          </el-tag>
        </div>
      </template>

      <div class="text-sm space-y-2" style="color: var(--el-text-color-regular)">
        <p>{{ t('accountSecurity.description') }}</p>
      </div>

      <div v-if="!me?.totp_enabled" class="mt-4 space-y-3">
        <el-button type="primary" @click="startSetup" :loading="loading">{{ t('accountSecurity.generateSecret') }}</el-button>

        <div v-if="setup">
          <el-alert type="warning" show-icon :closable="false" :title="t('accountSecurity.setupAlert')" />
          <div class="mt-2 text-sm">
            <div class="font-medium">{{ t('accountSecurity.secretManual') }}</div>
            <el-input v-model="setup.secret" readonly />
          </div>
          <div class="mt-2 text-sm">
            <div class="font-medium">otpauth URI：</div>
            <el-input v-model="setup.otpauth_uri" readonly type="textarea" :rows="2" />
          </div>
          <div class="mt-3 flex items-center gap-2">
            <el-input v-model="code" :placeholder="t('accountSecurity.enterCode6')" style="max-width: 220px" />
            <el-button type="success" @click="enable" :loading="loading">{{ t('accountSecurity.confirmEnable') }}</el-button>
          </div>
        </div>
      </div>

      <div v-else class="mt-4 space-y-3">
        <el-alert type="success" show-icon :closable="false" :title="t('accountSecurity.enabledAlert')" />
        <div class="flex items-center gap-2">
          <el-input v-model="code" :placeholder="t('accountSecurity.enterCode6ToDisable')" style="max-width: 260px" />
          <el-button type="danger" @click="disable" :loading="loading">{{ t('accountSecurity.disable2fa') }}</el-button>
        </div>
      </div>
    </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'

type MeProfile = {
  otp_enabled?: boolean
  [key: string]: unknown
}

const { t } = useI18n()  // FIXED: 国际化
const me = ref<MeProfile | null>(null)
const loading = ref(false)
const setup = ref<{ secret: string; otpauth_uri: string } | null>(null)
const code = ref('')

const loadMe = async () => {
  try {
    const res = await api.get('/api/v1/users/me')
    me.value = res.data
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } // FIXED: 裸await api调用包裹try-catch
}

const startSetup = async () => {
  loading.value = true
  try {
    const res = await api.post('/api/v1/users/me/2fa/setup')
    setup.value = { secret: res.data?.secret ?? '', otpauth_uri: res.data?.otpauth_uri ?? '' }
    ElMessage.success(t('account.keyGenerated'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const enable = async () => {
  if (!code.value) return ElMessage.warning(t('account.enterCode'))
  loading.value = true
  try {
    await api.post('/api/v1/users/me/2fa/enable', { code: code.value })
    code.value = ''
    setup.value = null
    await loadMe()
    ElMessage.success(t('account.twoFaEnabled'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const disable = async () => {
  if (!code.value) return ElMessage.warning(t('account.enterCode'))
  loading.value = true
  try {
    await api.post('/api/v1/users/me/2fa/disable', { code: code.value })
    code.value = ''
    await loadMe()
    ElMessage.success(t('account.twoFaDisabled'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadMe().catch(() => {
    ElMessage.error(t('account.loadFailed'))
  })
})
</script>

