<template>
  <AppDialog
    v-model="visible"
    :title="title"
    size="small"
  >
    <div v-if="loading" class="py-6 flex justify-center">
      <el-icon class="is-loading text-2xl" style="color: var(--el-color-primary)"><Loading /></el-icon>
    </div>
    <el-tree
      v-else
      :data="treeData"
      :props="{ label: 'label', children: 'children' }"
      node-key="id"
      highlight-current
      default-expand-all
      class="max-h-80 overflow-auto"
      @node-click="onNodeClick"
    />
    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirm" :disabled="!selectedNode">{{ t('common.ok') }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'

const { t } = useI18n()

interface Props {
  modelValue: boolean
  title?: string
  mode: 'filter' | 'batch'
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', nodeId: string, nodeName: string): void
  (e: 'tree-click', node: { id: string; label: string }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const title = computed(() => props.mode === 'filter' ? t('businessPicker.filterTitle') : t('businessPicker.batchSetTitle'))
const loading = ref(false)
const treeData = ref<Record<string, unknown>[]>([])
const selectedNode = ref<{ id: string; label: string } | null>(null)

watch(() => props.modelValue, async (val) => {
  if (val) {
    selectedNode.value = null
    await loadTree()
  }
})

const loadTree = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/devices/tree/business')
    treeData.value = Array.isArray(res.data) ? res.data : []
  } catch {
    treeData.value = []
    ElMessage.error(t('businessPicker.loadFailed'))
  } finally {
    loading.value = false
  }
}

const onNodeClick = (data: Record<string, unknown>) => {
  const id = String(data?.id || '').trim()
  const label = String(data?.label || id).trim()
  const nt = String(data?.nodeType || '').toLowerCase()
  if (!id || nt === 'device') return
  selectedNode.value = { id, label }
  emit('tree-click', { id, label })
}

const handleConfirm = () => {
  if (!selectedNode.value) {
    ElMessage.warning(t('businessPicker.selectNodeFirst'))
    return
  }
  emit('confirm', selectedNode.value.id, selectedNode.value.label)
  visible.value = false
}
</script>
