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
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleConfirm" :disabled="!selectedNode">确定</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import api from '@/utils/http'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'

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

const title = computed(() => props.mode === 'filter' ? '筛选：业务分组' : '批量设置业务分组')
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
    ElMessage.error('加载业务分组失败')
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
    ElMessage.warning('请选择分组节点')
    return
  }
  emit('confirm', selectedNode.value.id, selectedNode.value.label)
  visible.value = false
}
</script>
