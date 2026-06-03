<template>
  <AppDialog
    v-model="visible"
    title="拉黑设备/IP"
    size="medium"
  >
    <div v-if="deviceData" class="mb-4">
      <p class="mb-2" style="color: var(--el-text-color-regular)">正在操作设备: <strong>{{ deviceData.name || deviceData.gb_id }}</strong></p>
      <p class="mb-4" style="color: var(--el-text-color-regular)">设备 IP: <strong>{{ deviceData.ip_addr || deviceData.ip || '未知' }}</strong></p>

      <el-form :model="form" label-width="0">
        <el-form-item>
          <el-checkbox v-model="form.blacklist_ip">
            拉黑该 IP (拒绝该 IP 的所有注册请求)
          </el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.delete_current">
            删除当前设备
          </el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.delete_all_from_ip">
            删除该 IP 下的所有已注册设备
          </el-checkbox>
        </el-form-item>
      </el-form>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="danger" :loading="saving" @click="handleSubmit">确认拉黑</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'

interface Props {
  modelValue: boolean
  deviceData: Record<string, unknown> | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const saving = ref(false)
const form = ref({
  blacklist_ip: true,
  delete_current: true,
  delete_all_from_ip: false
})

watch(() => props.modelValue, (val) => {
  if (val) {
    form.value = { blacklist_ip: true, delete_current: true, delete_all_from_ip: false }
  }
})

const handleSubmit = async () => {
  if (!props.deviceData) return
  try {
    await ElMessageBox.confirm('确认拉黑该IP？此操作不可撤销。', '确认拉黑', { type: 'warning' })
  } catch { return }
  saving.value = true
  try {
    await api.post(`/api/v1/devices/${props.deviceData.gb_id}/blacklist`, {
      ip: props.deviceData.ip_addr || props.deviceData.ip,
      blacklist_ip: form.value.blacklist_ip,
      delete_current: form.value.delete_current,
      delete_all_from_ip: form.value.delete_all_from_ip
    })
    ElMessage.success('已加入 IP 黑名单')
    visible.value = false
    emit('success')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    saving.value = false
  }
}
</script>
