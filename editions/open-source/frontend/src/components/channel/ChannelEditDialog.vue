<template>
  <AppDialog
    v-model="visible"
    title="通道编辑"
    size="medium"
    width="680px"
  >
    <div class="px-2">
      <el-form :model="form" label-width="120px" size="small">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="通道国标ID">
              <el-input v-model="form.gb_id" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="通道名称">
              <el-input v-model="form.name" placeholder="请输入通道名称" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="行政区划码">
              <el-input v-model="form.civil_code" placeholder="例如 110120" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="在线状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option :value="1" label="在线" />
                <el-option :value="0" label="离线" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="经度">
              <el-input-number v-model="form.longitude" :precision="6" style="width: 100%" :step="0.000001" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="纬度">
              <el-input-number v-model="form.latitude" :precision="6" style="width: 100%" :step="0.000001" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="开启音频">
              <el-switch v-model="form.has_audio" inline-prompt active-text="开" inactive-text="关" class="pretty-switch" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="默认码流">
              <el-select v-model="form.default_stream_type" style="width: 100%">
                <el-option label="主码流" value="main" />
                <el-option label="子码流" value="sub" />
                <el-option label="主码流 (通用)" value="stream:0" />
                <el-option label="子码流 (通用)" value="stream:1" />
                <el-option label="主码流 (国标2022)" value="streamnumber:0" />
                <el-option label="子码流 (国标2022)" value="streamnumber:1" />
                <el-option label="主码流 (大华)" value="streamprofile:0" />
                <el-option label="子码流 (大华)" value="streamprofile:1" />
                <el-option label="主码流 (水星/TP)" value="streamMode:MAIN" />
                <el-option label="子码流 (水星/TP)" value="streamMode:SUB" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">扩展信息</el-divider>

        <el-form-item label="安装地址">
          <el-input v-model="form.address" placeholder="请输入安装地址" />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="设备类型">
              <el-select v-model="form.ptz_type" style="width: 100%">
                <el-option :value="0" label="未知" />
                <el-option :value="1" label="球机" />
                <el-option :value="2" label="半球" />
                <el-option :value="3" label="固定枪机" />
                <el-option :value="4" label="遥控枪机" />
                <el-option :value="5" label="遥控半球" />
                <el-option :value="6" label="全景/拼接通道" />
                <el-option :value="7" label="分割通道" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分辨率">
              <el-input v-model="form.resolution" placeholder="例如 1920*1080" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="子设备">
              <el-select v-model="form.parental" style="width: 100%">
                <el-option :value="0" label="无" />
                <el-option :value="1" label="有" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="注册方式">
              <el-select v-model="form.register_way" style="width: 100%">
                <el-option :value="1" label="符合国标" />
                <el-option :value="2" label="不符合国标" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="保密属性">
              <el-select v-model="form.secrecy" style="width: 100%">
                <el-option :value="0" label="不涉密" />
                <el-option :value="1" label="涉密" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务组ID">
              <el-input v-model="form.business_group_id" placeholder="请输入业务组ID" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="安装位置">
              <el-select v-model="form.position_type" style="width: 100%">
                <el-option :value="0" label="未知" />
                <el-option :value="1" label="室内" />
                <el-option :value="2" label="室外" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用途类型">
              <el-select v-model="form.use_type" style="width: 100%">
                <el-option :value="0" label="其他" />
                <el-option :value="1" label="治安" />
                <el-option :value="2" label="交通" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="补光类型">
              <el-select v-model="form.supply_light_type" style="width: 100%">
                <el-option :value="0" label="未知" />
                <el-option :value="1" label="无补光" />
                <el-option :value="2" label="红外" />
                <el-option :value="3" label="白光" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="方向类型">
              <el-input-number v-model="form.direction_type" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">确认</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoCamera, Setting } from '@element-plus/icons-vue'
import api from '@/utils/http'
import { getFriendlyError } from '../../utils/errorMessage'
import AppDialog from '../common/AppDialog.vue'

const props = defineProps<{
  visible: boolean
  channelData: Record<string, unknown>
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.visible,
  set: v => emit('update:visible', v)
})

const saving = ref(false)

const form = ref<{
  id: string
  gb_id: string
  name: string
  civil_code: string | null
  status: number
  has_audio: boolean
  default_stream_type: string
  longitude: number | null
  latitude: number | null
  // GB28181 Extended
  address: string | null
  parental: number
  safety_way: number
  register_way: number
  secrecy: number
  ip_address: string | null
  port: number | null
  password: string | null
  ptz_type: number
  position_type: number
  room_type: number
  use_type: number
  supply_light_type: number
  direction_type: number
  resolution: string | null
  business_group_id: string | null
}>({
  id: '', gb_id: '', name: '', civil_code: null, status: 0, has_audio: true, default_stream_type: 'main',
  longitude: null, latitude: null, address: null, parental: 0, safety_way: 0, register_way: 1, secrecy: 0,
  ip_address: null, port: null, password: null, ptz_type: 0, position_type: 0, room_type: 0, use_type: 0,
  supply_light_type: 0, direction_type: 0, resolution: null, business_group_id: null
})

watch(() => props.visible, (val) => {
  if (val && props.channelData) {
    const row = props.channelData
    form.value = {
      id: row.id,
      gb_id: row.gb_id,
      name: row.name || '',
      civil_code: row.civil_code != null ? String(row.civil_code) : null,
      status: Number(row.status) === 1 ? 1 : 0,
      has_audio: row.has_audio != null ? !!row.has_audio : true,
      default_stream_type: row.default_stream_type || 'main',
      longitude: row.longitude != null ? Number(row.longitude) : null,
      latitude: row.latitude != null ? Number(row.latitude) : null,
      address: row.address || null,
      parental: Number(row.parental || 0),
      safety_way: Number(row.safety_way || 0),
      register_way: Number(row.register_way || 1),
      secrecy: Number(row.secrecy || 0),
      ip_address: row.ip_address || null,
      port: row.port != null ? Number(row.port) : null,
      password: row.password || null,
      ptz_type: Number(row.ptz_type || 0),
      position_type: Number(row.position_type || 0),
      room_type: Number(row.room_type || 0),
      use_type: Number(row.use_type || 0),
      supply_light_type: Number(row.supply_light_type || 0),
      direction_type: Number(row.direction_type || 0),
      resolution: row.resolution || null,
      business_group_id: row.business_group_id || null
    }
  }
})

const save = async () => {
  if (!form.value.id) return
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: form.value.name,
      status: form.value.status,
      has_audio: form.value.has_audio,
      default_stream_type: form.value.default_stream_type,
      civil_code: (form.value.civil_code || '').trim() || null,
      longitude: form.value.longitude,
      latitude: form.value.latitude,
      address: form.value.address,
      parental: form.value.parental,
      safety_way: form.value.safety_way,
      register_way: form.value.register_way,
      secrecy: form.value.secrecy,
      ip_address: form.value.ip_address,
      port: form.value.port,
      password: form.value.password,
      ptz_type: form.value.ptz_type,
      position_type: form.value.position_type,
      room_type: form.value.room_type,
      use_type: form.value.use_type,
      supply_light_type: form.value.supply_light_type,
      direction_type: form.value.direction_type,
      resolution: form.value.resolution,
      business_group_id: form.value.business_group_id
    }
    await api.put(`/api/v1/devices/channels/${form.value.id}`, payload)
    ElMessage.success('通道已保存')
    emit('success')
    emit('update:visible', false)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    saving.value = false
  }
}
</script>

