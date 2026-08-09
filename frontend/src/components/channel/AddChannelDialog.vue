<template>
  <AppDialog
    v-model="visible"
    :title="t('channel.add.title')"
    size="medium"
    width="720px"
  >
    <el-form :model="addForm" label-width="120px" :rules="addRules" ref="addFormRef">
      <el-form-item :label="t('channel.add.deviceGbId')" prop="deviceId">
        <el-input v-model="addForm.deviceId" :placeholder="t('channel.add.deviceGbIdPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.channelGbId')" prop="gbDeviceId">
        <el-input v-model="addForm.gbDeviceId" :placeholder="t('channel.add.channelGbIdPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.channelName')" prop="gbName">
        <el-input v-model="addForm.gbName" :placeholder="t('channel.add.channelNamePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.manufacturer')">
        <el-input v-model="addForm.gbManufacturer" :placeholder="t('channel.add.manufacturerPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.model')">
        <el-input v-model="addForm.gbModel" :placeholder="t('channel.add.modelPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.civilCode')">
        <el-input v-model="addForm.gbCivilCode" :placeholder="t('channel.add.civilCodePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.parentId')">
        <el-input v-model="addForm.gbParentId" :placeholder="t('channel.add.parentIdPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.businessGroupId')">
        <el-input v-model="addForm.gbBusinessGroupId" :placeholder="t('channel.add.businessGroupIdPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.longitude')">
        <el-input v-model="addForm.gbLongitude" :placeholder="t('channel.add.longitudePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.latitude')">
        <el-input v-model="addForm.gbLatitude" :placeholder="t('channel.add.latitudePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channel.add.ptzType')">
        <el-select v-model="addForm.ptzType" style="width: 100%">
          <el-option :label="t('channel.add.ptzUnknown')" :value="0" />
          <el-option :label="t('channel.add.ptzDome')" :value="1" />
          <el-option :label="t('channel.add.ptzHemisphere')" :value="2" />
          <el-option :label="t('channel.add.ptzFixed')" :value="3" />
          <el-option :label="t('channel.add.ptzRemote')" :value="4" />
          <el-option :label="t('channel.add.ptzRemoteHemi')" :value="5" />
          <el-option :label="t('channel.add.ptzPanoramic')" :value="6" />
          <el-option :label="t('channel.add.ptzSplit')" :value="7" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">{{ t('channel.add.btnCancel') }}</el-button>
      <el-button type="primary" :loading="addSaving" @click="saveAdd">{{ t('channel.add.btnSave') }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/http'
import { getFriendlyError } from '../../utils/errorMessage'
import AppDialog from '../common/AppDialog.vue'
import { useI18n } from 'vue-i18n'  // FIXED: [2026-07-13] P1 i18n — 添加国际化支持

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.visible,
  set: v => emit('update:visible', v)
})

const addSaving = ref(false)
const addFormRef = ref()
const addForm = reactive<any>({
  deviceId: '',
  gbDeviceId: '',
  gbName: '',
  gbManufacturer: '',
  gbModel: '',
  gbCivilCode: '',
  gbParentId: '',
  gbBusinessGroupId: '',
  gbLongitude: '',
  gbLatitude: '',
  ptzType: 0
})

const addRules = computed(() => ({
  deviceId: [{ required: true, message: t('channel.add.msgDeviceGbIdRequired'), trigger: 'blur' }],
  gbDeviceId: [{ required: true, message: t('channel.add.msgChannelGbIdRequired'), trigger: 'blur' }],
  gbName: [{ required: true, message: t('channel.add.msgChannelNameRequired'), trigger: 'blur' }]
}))

watch(() => props.visible, (val) => {
  if (val) {
    addSaving.value = false
    addForm.deviceId = ''
    addForm.gbDeviceId = ''
    addForm.gbName = ''
    addForm.gbManufacturer = ''
    addForm.gbModel = ''
    addForm.gbCivilCode = ''
    addForm.gbParentId = ''
    addForm.gbBusinessGroupId = ''
    addForm.gbLongitude = ''
    addForm.gbLatitude = ''
    addForm.ptzType = 0
  }
})

const saveAdd = async () => {
  try {
    await addFormRef.value?.validate?.()
  } catch {
    return
  }
  addSaving.value = true
  try {
    await api.post('/api/common/channel/add', {
      deviceId: addForm.deviceId,
      gbDeviceId: addForm.gbDeviceId,
      gbName: addForm.gbName,
      gbManufacturer: addForm.gbManufacturer || null,
      gbModel: addForm.gbModel || null,
      gbCivilCode: addForm.gbCivilCode || null,
      gbParentId: addForm.gbParentId || null,
      gbBusinessGroupId: addForm.gbBusinessGroupId || null,
      gbLongitude: addForm.gbLongitude === '' ? null : Number(addForm.gbLongitude),
      gbLatitude: addForm.gbLatitude === '' ? null : Number(addForm.gbLatitude),
      ptzType: Number(addForm.ptzType || 0)
    })
    ElMessage.success(t('channel.add.msgAdded'))
    emit('success')
    emit('update:visible', false)
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    addSaving.value = false
  }
}
</script>
