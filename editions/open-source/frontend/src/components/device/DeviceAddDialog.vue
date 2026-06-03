<template>
  <AppDialog
    v-model="visible"
    title="添加设备"
    size="medium"
  >
    <div class="px-2">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px" size="default">
        <div class="font-medium mb-4 flex items-center gap-2" style="color: var(--el-text-color-primary)">
          <el-icon class="text-primary"><Monitor /></el-icon>
          基本信息
        </div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="设备编号" prop="gb_id">
              <el-input v-model="form.gb_id" placeholder="设备国标ID（20位）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入设备名称" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="设备密码">
              <el-input v-model="form.password" :placeholder="t('device.enterPassword')" />  <!-- FIXED: P3 i18n -->
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备IP">
              <el-input v-model="form.ip_addr" placeholder="请输入设备IP地址" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="端口">
              <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" placeholder="端口号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="传输协议">
              <el-select v-model="form.transport" style="width: 100%">
                <el-option label="UDP" value="UDP" />
                <el-option label="TCP" value="TCP" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="制造商">
              <el-input v-model="form.manufacturer" placeholder="请输入制造商" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备型号">
              <el-input v-model="form.model" placeholder="请输入设备型号" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="固件版本">
              <el-input v-model="form.firmware" placeholder="请输入固件版本" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="SIP域">
              <el-input v-model="form.domain" placeholder="请输入SIP域" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider border-style="dashed" />

        <div class="font-medium mb-4 flex items-center gap-2" style="color: var(--el-text-color-primary)">
          <el-icon class="text-primary"><Setting /></el-icon>
          国标与心跳配置
        </div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="字符集">
              <el-select v-model="form.charset" style="width: 100%">
                <el-option label="UTF-8" value="UTF-8" />
                <el-option label="GB2312" value="GB2312" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="坐标系">
              <el-select v-model="form.geo_coord_sys" style="width: 100%">
                <el-option label="WGS84" value="WGS84" />
                <el-option label="GCJ02" value="GCJ02" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="SSRC检查">
              <el-switch v-model="form.ssrc_check" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="消息通道">
              <el-switch v-model="form.as_message_channel" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="心跳间隔">
              <el-input-number v-model="form.heartbeat_interval" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="心跳超时">
              <el-input-number v-model="form.heartbeat_count" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSubmit">添加</el-button>
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

const formRules: FormRules = {
  gb_id: [
    { required: true, message: '请输入设备编号', trigger: 'blur' },
    { pattern: /^\d{20}$/, message: '设备编号应为20位数字', trigger: 'blur' }
  ],
  name: [
    { required: true, message: '请输入设备名称', trigger: 'blur' }
  ]
}

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
    ElMessage.success('设备添加成功')
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
