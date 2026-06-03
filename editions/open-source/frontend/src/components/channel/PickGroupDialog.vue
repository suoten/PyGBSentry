<template>
  <AppDialog
    v-model="visible"
    title="选择虚拟组织（业务分组）"
    size="small"
    width="480px"
  >
    <div v-if="loading" class="py-8 flex justify-center"><el-icon class="is-loading text-2xl"><Loading /></el-icon></div>
    <el-tree
      v-else
      :data="treeData"
      :props="{ label: 'label', children: 'children' }"
      node-key="id"
      highlight-current
      default-expand-all
      class="max-h-96 overflow-auto"
      @node-click="onClick"
    />
    <div class="text-xs mt-2" style="color: var(--el-text-color-secondary)">请选择业务分组树上的目录节点（需区分 parentId / businessGroup 时，此处暂以节点国标 id 同时填入二者）。</div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="submit">确定</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import api from '@/utils/http'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'
import { showError } from '@/utils/feedback'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'picked', parentId: string, businessGroup: string, name: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const loading = ref(false)
const treeData = ref<Record<string, unknown>[]>([])
const pick = ref<{ id: string; label: string } | null>(null)

const loadTree = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/devices/tree/business')
    treeData.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    showError('加载分组树', e)
    treeData.value = []
  } finally {
    loading.value = false
  }
}

watch(visible, v => {
  if (v) {
    pick.value = null
    void loadTree()
  }
})

const onClick = (data: Record<string, unknown>) => {
  const id = String(data?.id || '').trim()
  const label = String(data?.label || id).trim()
  const nt = String(data?.nodeType || '').toLowerCase()
  if (!id || nt === 'device') return
  pick.value = { id, label }
}

const submit = () => {
  if (!pick.value) {
    ElMessage.warning('请选择分组节点')
    return
  }
  const id = pick.value.id
  emit('picked', id, id, pick.value.label)
  visible.value = false
}
</script>
