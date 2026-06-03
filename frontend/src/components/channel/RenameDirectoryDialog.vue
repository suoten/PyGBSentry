<template>
  <AppDialog
    v-model="visible"
    title="重命名节点"
    size="small"
  >
    <el-form :model="form" label-width="90px">
      <el-form-item label="节点名称">
        <el-input v-model="form.name" placeholder="请输入节点名称" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSubmit">确认</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'

const props = defineProps<{
  modelValue: boolean
  nodeId: string
  nodeName: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const saving = ref(false)
const form = ref({ name: '' })

watch(() => props.modelValue, (val) => {
  if (val) {
    form.value.name = props.nodeName || ''
  }
})

const handleSubmit = async () => {
  const name = String(form.value.name || '').trim()
  if (!name) {
    ElMessage.warning('请输入节点名称')
    return
  }
  saving.value = true
  try {
    await api.put('/api/v1/devices/directories', { gb_id: props.nodeId, name })
    ElMessage.success('节点已重命名')
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
