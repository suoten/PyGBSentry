<template>
  <AppDialog
    v-model="visible"
    :title="t('channel.edit.title')"
    size="medium"
    width="680px"
  >
    <div class="px-2">
      <el-form :model="form" label-width="120px" size="small">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.gbId')">
              <el-input v-model="form.gb_id" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.name')">
              <el-input v-model="form.name" :placeholder="t('channel.edit.namePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.civilCode')">
              <el-input v-model="form.civil_code" :placeholder="t('channel.edit.civilCodePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.status')">
              <el-select v-model="form.status" style="width: 100%">
                <el-option :value="1" :label="t('channel.edit.online')" />
                <el-option :value="0" :label="t('channel.edit.offline')" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.longitude')">
              <el-input-number v-model="form.longitude" :precision="6" style="width: 100%" :step="0.000001" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.latitude')">
              <el-input-number v-model="form.latitude" :precision="6" style="width: 100%" :step="0.000001" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.audio')">
              <el-switch v-model="form.has_audio" inline-prompt :active-text="t('channel.edit.switchOn')" :inactive-text="t('channel.edit.switchOff')" class="pretty-switch" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.defaultStream')">
              <el-select v-model="form.default_stream_type" style="width: 100%">
                <el-option :label="t('channel.edit.mainStream')" value="main" />
                <el-option :label="t('channel.edit.subStream')" value="sub" />
                <el-option :label="t('channel.edit.mainStreamGeneric')" value="stream:0" />
                <el-option :label="t('channel.edit.subStreamGeneric')" value="stream:1" />
                <el-option :label="t('channel.edit.mainStreamGB2022')" value="streamnumber:0" />
                <el-option :label="t('channel.edit.subStreamGB2022')" value="streamnumber:1" />
                <el-option :label="t('channel.edit.mainStreamDahua')" value="streamprofile:0" />
                <el-option :label="t('channel.edit.subStreamDahua')" value="streamprofile:1" />
                <el-option :label="t('channel.edit.mainStreamMercury')" value="streamMode:MAIN" />
                <el-option :label="t('channel.edit.subStreamMercury')" value="streamMode:SUB" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">{{ t('channel.edit.extInfo') }}</el-divider>

        <el-form-item :label="t('channel.edit.address')">
          <el-input v-model="form.address" :placeholder="t('channel.edit.addressPlaceholder')" />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.ptzType')">
              <el-select v-model="form.ptz_type" style="width: 100%">
                <el-option :value="0" :label="t('channel.edit.ptzUnknown')" />
                <el-option :value="1" :label="t('channel.edit.ptzDome')" />
                <el-option :value="2" :label="t('channel.edit.ptzHemisphere')" />
                <el-option :value="3" :label="t('channel.edit.ptzFixed')" />
                <el-option :value="4" :label="t('channel.edit.ptzRemote')" />
                <el-option :value="5" :label="t('channel.edit.ptzRemoteHemi')" />
                <el-option :value="6" :label="t('channel.edit.ptzPanoramic')" />
                <el-option :value="7" :label="t('channel.edit.ptzSplit')" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.resolution')">
              <el-input v-model="form.resolution" :placeholder="t('channel.edit.resolutionPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.parental')">
              <el-select v-model="form.parental" style="width: 100%">
                <el-option :value="0" :label="t('channel.edit.parentalNone')" />
                <el-option :value="1" :label="t('channel.edit.parentalHas')" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.registerWay')">
              <el-select v-model="form.register_way" style="width: 100%">
                <el-option :value="1" :label="t('channel.edit.registerStandard')" />
                <el-option :value="2" :label="t('channel.edit.registerNonStandard')" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.secrecy')">
              <el-select v-model="form.secrecy" style="width: 100%">
                <el-option :value="0" :label="t('channel.edit.secrecyNo')" />
                <el-option :value="1" :label="t('channel.edit.secrecyYes')" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.businessGroupId')">
              <el-input v-model="form.business_group_id" :placeholder="t('channel.edit.businessGroupIdPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.positionType')">
              <el-select v-model="form.position_type" style="width: 100%">
                <el-option :value="0" :label="t('channel.edit.positionUnknown')" />
                <el-option :value="1" :label="t('channel.edit.positionIndoor')" />
                <el-option :value="2" :label="t('channel.edit.positionOutdoor')" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.useType')">
              <el-select v-model="form.use_type" style="width: 100%">
                <el-option :value="0" :label="t('channel.edit.useOther')" />
                <el-option :value="1" :label="t('channel.edit.useSecurity')" />
                <el-option :value="2" :label="t('channel.edit.useTraffic')" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.supplyLightType')">
              <el-select v-model="form.supply_light_type" style="width: 100%">
                <el-option :value="0" :label="t('channel.edit.supplyLightUnknown')" />
                <el-option :value="1" :label="t('channel.edit.supplyLightNone')" />
                <el-option :value="2" :label="t('channel.edit.supplyLightInfrared')" />
                <el-option :value="3" :label="t('channel.edit.supplyLightWhite')" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('channel.edit.directionType')">
              <el-input-number v-model="form.direction_type" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>
    <template #footer>
      <el-button @click="visible = false">{{ t('channel.edit.btnCancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('channel.edit.btnConfirm') }}</el-button>
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
import { useI18n } from 'vue-i18n'  // FIXED: [2026-07-13] P1 i18n — 添加国际化支持

const { t } = useI18n()

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
    ElMessage.success(t('channel.edit.msgSaved'))
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
