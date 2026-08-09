<template>
  <AppDialog
    v-model="visible"
    :title="t('device.add.title')"
    size="medium"
  >
    <div class="px-2">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px" size="default">
        <div class="font-medium mb-4 flex items-center gap-2" style="color: var(--el-text-color-primary)">
          <el-icon class="text-primary"><Monitor /></el-icon>
          {{ t('device.add.basicInfo') }}
        </div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.deviceCode')" prop="gb_id">
              <el-input v-model="form.gb_id" :placeholder="t('device.add.deviceCodePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.deviceName')" prop="name">
              <el-input v-model="form.name" :placeholder="t('device.add.deviceNamePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.devicePassword')">
              <el-input v-model="form.password" :placeholder="t('device.enterPassword')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.deviceIp')">
              <el-input v-model="form.ip_addr" :placeholder="t('device.add.deviceIpPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.port')">
              <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" :placeholder="t('device.add.portPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.transport')">
              <el-select v-model="form.transport" style="width: 100%">
                <el-option label="UDP" value="UDP" />
                <el-option label="TCP" value="TCP" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.manufacturer')">
              <el-input v-model="form.manufacturer" :placeholder="t('device.add.manufacturerPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.model')">
              <el-input v-model="form.model" :placeholder="t('device.add.modelPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.firmware')">
              <el-input v-model="form.firmware" :placeholder="t('device.add.firmwarePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.sipDomain')">
              <el-input v-model="form.domain" :placeholder="t('device.add.sipDomainPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider border-style="dashed" />

        <div class="font-medium mb-4 flex items-center gap-2" style="color: var(--el-text-color-primary)">
          <el-icon class="text-primary"><Setting /></el-icon>
          {{ t('device.add.gbAndHeartbeat') }}
        </div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.charset')">
              <el-select v-model="form.charset" style="width: 100%">
                <el-option label="UTF-8" value="UTF-8" />
                <el-option label="GB2312" value="GB2312" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.coordinate')">
              <el-select v-model="form.geo_coord_sys" style="width: 100%">
                <el-option label="WGS84" value="WGS84" />
                <el-option label="GCJ02" value="GCJ02" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.ssrcCheck')">
              <el-switch v-model="form.ssrc_check" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.msgChannel')">
              <el-switch v-model="form.as_message_channel" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('device.add.heartbeatInterval')">
              <el-input-number v-model="form.heartbeat_interval" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.add.heartbeatTimeout')">
              <el-input-number v-model="form.heartbeat_count" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>
    <template #footer>
      <el-button @click="visible = false">{{ t('device.add.btnCancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="handleSubmit">{{ t('device.add.btnAdd') }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { Monitor, Setting } from '@element-plus/icons-vue'
import AppDialog from '../common/AppDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'
import type { FormRules } from 'element-plus'
import { useI18n } from 'vue-i18n'  // FIXED: P3 i18n

const { t } = useI18n()  // FIXED: P3 i18n

interface DeviceForm {
  gb_id: string
  name: string
  password: string
  ip_addr: string
  port: number | null
  transport: string
  manufacturer: string
  model: string
  firmware: string
  domain: string
  charset: string
  ssrc_check: boolean
  geo_coord_sys: string
  as_message_channel: boolean
  heartbeat_interval: number
  heartbeat_count: number
}

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const saving = ref(false)
const formRef = ref<{ validate: () => Promise<unknown> } | null>(null)
const form = ref<DeviceForm>({
  gb_id: '',
  name: '',
  password: '',
  ip_addr: '',
  port: null,
  transport: 'UDP',
  manufacturer: '',
  model: '',
  firmware: '',
  domain: '',
  charset: 'UTF-8',
  ssrc_check: false,
  geo_coord_sys: 'WGS84',
  as_message_channel: false,
  heartbeat_interval: 60,
  heartbeat_count: 3
})

const formRules = computed<FormRules>(() => ({
  gb_id: [
    { required: true, message: t('device.add.msgDeviceCodeRequired'), trigger: 'blur' },
    { pattern: /^\d{20}$/, message: t('device.add.msgDeviceCodeFormat'), trigger: 'blur' }
  ],
  name: [
    { required: true, message: t('device.add.msgDeviceNameRequired'), trigger: 'blur' }
  ]
}))

watch(() => props.modelValue, (val) => {
  if (val) {
    form.value = {
      gb_id: '',
      name: '',
      password: '',
      ip_addr: '',
      port: null,
      transport: 'UDP',
      manufacturer: '',
      model: '',
      firmware: '',
      domain: '',
      charset: 'UTF-8',
      ssrc_check: false,
      geo_coord_sys: 'WGS84',
      as_message_channel: false,
      heartbeat_interval: 60,
      heartbeat_count: 3
    }
  }
})

const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    saving.value = true
    const payload: Record<string, unknown> = { ...form.value }
    const optionalFields = ['password', 'ip_addr', 'port', 'manufacturer', 'model', 'firmware',
      'domain', 'charset', 'ssrc_check', 'geo_coord_sys', 'as_message_channel',
      'heartbeat_interval', 'heartbeat_count']
    optionalFields.forEach(k => {
      const v = payload[k]
      if (v === '' || v === null || v === undefined) delete payload[k]
    })
    await api.post('/api/v1/devices', payload)
    ElMessage.success(t('device.add.msgAddSuccess'))
    visible.value = false
    emit('success')
  } catch (e: unknown) {
    if (e !== false) {
      const friendly = getFriendlyError(e)
      ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    }
  } finally {
    saving.value = false
  }
}
</script>
