<template>
  <AppDialog
    v-model="visible"
    :title="t('device.accessInfo.title')"
    size="large"
  >
    <div v-if="loading" class="py-8 flex justify-center">
      <el-icon class="is-loading text-2xl"><Loading /></el-icon>
    </div>
    <div v-else class="dialog-content access-info-content">
      <div class="info-section">
        <div class="info-item">
          <div class="info-label">{{ t('device.accessInfo.code') }}</div>
          <div class="info-value-wrapper">
            <span class="info-value">{{ accessInfo.sipId || '-' }}</span>
            <el-button v-if="accessInfo.sipId" size="small" type="primary" link @click="copy(accessInfo.sipId)">
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="info-item">
          <div class="info-label">{{ t('device.accessInfo.domain') }}</div>
          <div class="info-value-wrapper">
            <span class="info-value">{{ accessInfo.domain || '-' }}</span>
            <el-button v-if="accessInfo.domain" size="small" type="primary" link @click="copy(accessInfo.domain)">
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="info-item">
          <div class="info-label">IP</div>
          <div class="info-value-wrapper">
            <span class="info-value">{{ maskSipIp(accessInfo.sipIp) || '-' }}</span>
            <el-button v-if="accessInfo.sipIp" size="small" type="primary" link @click="copy(maskSipIp(accessInfo.sipIp))">
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="info-item">
          <div class="info-label">{{ t('device.accessInfo.port') }}</div>
          <div class="info-value-wrapper">
            <span class="info-value">{{ accessInfo.port || '-' }}</span>
            <el-button v-if="accessInfo.port" size="small" type="primary" link @click="copy(String(accessInfo.port))">
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="info-item">
          <div class="info-label">{{ t('device.accessInfo.password') }}</div>
          <div class="info-value-wrapper">
            <el-input
              v-if="accessInfo.password"
              :model-value="accessInfo.password"
              type="password"
              show-password
              size="small"
              readonly
              style="width: 180px"
            />
            <span v-else class="info-value-empty">{{ t('device.accessInfo.notSet') }}</span>
            <el-button v-if="accessInfo.password" size="small" type="primary" link @click="copy(accessInfo.password)">
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </div>
    <div class="mt-3 text-xs text-center leading-5" style="color: var(--el-text-color-secondary)">
      {{ t('device.accessInfo.hint') }}
    </div>
    <template #footer>
      <el-button @click="visible = false">{{ t('device.accessInfo.close') }}</el-button>
      <el-button type="primary" @click="copyAll">
        <el-icon class="mr-1"><DocumentCopy /></el-icon>
        {{ t('device.accessInfo.copyAll') }}
      </el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { Loading, DocumentCopy } from '@element-plus/icons-vue'
import AppDialog from '../common/AppDialog.vue'
import { showError } from '@/utils/feedback'
import { maskSipIp } from '@/utils/sipMask' // FIX H-10: SIP IP 脱敏

const { t } = useI18n()

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const accessInfo = ref({
  sipId: '',
  domain: '',
  port: '',
  sipIp: '',
  password: ''
})

watch(() => props.modelValue, async (val) => {
  if (val) {
    await loadAccessInfo()
  }
})

const loadAccessInfo = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/system-config/system-info')
    const info = res.data || {}
    accessInfo.value = {
      sipId: String(info.sip_id || info.sipId || ''),
      domain: String(info.sip_domain || info.sipDomain || info.domain || ''),
      port: String(info.sip_port || info.sipPort || info.port || ''),
      sipIp: String(info.sip_ip || info.sipIp || info.ip || ''),
      password: String(info.sip_password || info.sipPassword || '')
    }
  } catch (e: unknown) {
    showError(t('device.accessInfo.fetchFailed'), e)
    accessInfo.value = { sipId: '', domain: '', port: '', sipIp: '', password: '' }
  } finally {
    loading.value = false
  }
}

const copy = async (text: string) => {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(t('device.accessInfo.copiedToClipboard'))
      return
    } catch {
      // fallback
    }
  }
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.cssText = 'position:fixed;left:-999999px;top:-999999px'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    const success = document.execCommand('copy')
    textArea.remove()
    if (success) {
      ElMessage.success(t('device.accessInfo.copiedToClipboard'))
    } else {
      ElMessage.warning(t('device.accessInfo.copyFailedManual'))
    }
  } catch {
    ElMessage.warning(t('device.accessInfo.copyFailedManual'))
  }
}

const copyAll = () => {
  const lines = [
    `${t('device.accessInfo.copyLineCode')}: ${accessInfo.value.sipId || '-'}`,
    `${t('device.accessInfo.copyLineDomain')}: ${accessInfo.value.domain || '-'}`,
    `IP: ${maskSipIp(accessInfo.value.sipIp) || '-'}`,
    `${t('device.accessInfo.copyLinePort')}: ${accessInfo.value.port || '-'}`,
    `${t('device.accessInfo.copyLinePassword')}: ${accessInfo.value.password || t('device.accessInfo.notSet')}`
  ]
  copy(lines.join('\n'))
}
</script>

<style scoped>
.access-info-content {
  max-height: 60vh;
  overflow-y: auto;
}

.info-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: var(--el-fill-color-lightest);
  border-radius: 6px;
}

.info-label {
  min-width: 56px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.info-value-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.info-value {
  font-size: 13px;
  color: var(--el-text-color-primary);
  font-family: 'Courier New', monospace;
  word-break: break-all;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-value-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}
</style>
