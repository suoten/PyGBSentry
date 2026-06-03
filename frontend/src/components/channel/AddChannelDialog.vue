<template>
  <AppDialog
    v-model="visible"
    title="新增通道"
    size="medium"
    width="720px"
  >
    <el-form :model="addForm" label-width="120px" :rules="addRules" ref="addFormRef">
      <el-form-item label="设备国标ID" prop="deviceId">
        <el-input v-model="addForm.deviceId" placeholder="如：34020000001320000001" />
      </el-form-item>
      <el-form-item label="通道国标ID" prop="gbDeviceId">
        <el-input v-model="addForm.gbDeviceId" placeholder="如：340200000013200000010001" />
      </el-form-item>
      <el-form-item label="通道名称" prop="gbName">
        <el-input v-model="addForm.gbName" placeholder="通道名称" />
      </el-form-item>
      <el-form-item label="厂家">
        <el-input v-model="addForm.gbManufacturer" placeholder="可不填" />
      </el-form-item>
      <el-form-item label="型号">
        <el-input v-model="addForm.gbModel" placeholder="可不填" />
      </el-form-item>
      <el-form-item label="行政区划码">
        <el-input v-model="addForm.gbCivilCode" placeholder="6位区划码或 region:xxxxxx（可不填）" />
      </el-form-item>
      <el-form-item label="业务父节点ID">
        <el-input v-model="addForm.gbParentId" placeholder="可不填" />
      </el-form-item>
      <el-form-item label="业务分组ID">
        <el-input v-model="addForm.gbBusinessGroupId" placeholder="可不填" />
      </el-form-item>
      <el-form-item label="经度">
        <el-input v-model="addForm.gbLongitude" placeholder="可不填" />
      </el-form-item>
      <el-form-item label="纬度">
        <el-input v-model="addForm.gbLatitude" placeholder="可不填" />
      </el-form-item>
      <el-form-item label="云台类型">
        <el-select v-model="addForm.ptzType" style="width: 100%">
          <el-option label="未知(0)" :value="0" />
          <el-option label="球机(1)" :value="1" />
          <el-option label="半球(2)" :value="2" />
          <el-option label="固定枪机(3)" :value="3" />
          <el-option label="遥控枪机(4)" :value="4" />
          <el-option label="遥控半球(5)" :value="5" />
          <el-option label="全景/拼接(6)" :value="6" />
          <el-option label="分割通道(7)" :value="7" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="addSaving" @click="saveAdd">保存</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/http'
import { getFriendlyError } from '../../utils/errorMessage'
import AppDialog from '../common/AppDialog.vue'

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

const addRules = {
  deviceId: [{ required: true, message: '设备国标ID不能为空', trigger: 'blur' }],
  gbDeviceId: [{ required: true, message: '通道国标ID不能为空', trigger: 'blur' }],
  gbName: [{ required: true, message: '通道名称不能为空', trigger: 'blur' }]
}

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
    ElMessage.success('新增成功')
    emit('success')
    emit('update:visible', false)
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    addSaving.value = false
  }
}
</script>
