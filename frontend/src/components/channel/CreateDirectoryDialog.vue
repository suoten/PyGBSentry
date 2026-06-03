<template>
  <AppDialog
    v-model="visible"
    title="新建节点"
    size="small"
    width="500px"
  >
    <el-steps :active="createDialogStep - 1" simple class="mb-3">
      <el-step title="选择上级节点" />
      <el-step title="填写节点信息" />
    </el-steps>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <template v-if="createDialogStep === 1">
        <el-form-item label="上级节点">
          <el-popover
            v-model:visible="parentPickerVisible"
            trigger="click"
            placement="bottom-start"
            :width="520"
            popper-class="create-directory-parent-popper"
            @show="onParentPopoverShow"
          >
            <template #reference>
              <el-input
                :model-value="selectedParentLabel"
                readonly
                clearable
                placeholder="请选择上级节点"
                @clear="clearSelectedParent"
              />
            </template>
            <div class="parent-picker-panel">
              <el-input
                v-model="parentKeyword"
                size="small"
                clearable
                placeholder="搜索节点名称或编号"
                class="parent-picker-search"
              />
              <el-tree
                ref="parentTreeRef"
                :data="createParentTreeOptions"
                :props="defaultProps"
                node-key="id"
                highlight-current
                default-expand-all
                :expand-on-click-node="false"
                :filter-node-method="filterParentNode"
                class="parent-picker-tree"
                @node-click="handleParentNodeClick"
              />
            </div>
          </el-popover>
        </el-form-item>
        <el-form-item>
          <div class="text-xs" style="color: var(--el-text-color-secondary)">
            仅支持创建子节点，不支持创建根资源组同级节点。
          </div>
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item label="上级节点">
          <el-input :model-value="createParentLabel" disabled />
        </el-form-item>
        <el-form-item label="节点编号" prop="gb_id">
          <el-input v-model="form.gb_id" placeholder="可自动生成，也可手动修改">
            <template #append>
              <el-button :loading="generating" @click="generateGbId">生成</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="节点名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入节点名称" />
        </el-form-item>
        <el-form-item v-if="createDialogMode === 'region'" label="行政区划码" prop="civil_code">
          <el-input
            v-model="form.civil_code"
            placeholder="自动带出，可按需调整"
            maxlength="6"
          />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button v-if="createDialogStep === 2" @click="createDialogStep = 1">上一步</el-button>
      <el-button v-if="createDialogStep === 1" type="primary" @click="goStep2">下一步</el-button>
      <el-button v-else type="primary" :loading="creating" @click="submit">确认</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import api from '@/utils/http'
import { getFriendlyError } from '../../utils/errorMessage'
import AppDialog from '../common/AppDialog.vue'

const props = defineProps<{
  visible: boolean
  treeData: Record<string, unknown>[]
  nodeLabelMap: Map<string, string>
  treeMode: 'business' | 'region'
  businessRootId: string
  initParentId: string
  initRegionCode: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.visible,
  set: v => emit('update:visible', v)
})

const defaultProps = {
  children: 'children',
  label: 'label',
  disabled: 'disabled'
}

const createDialogStep = ref<1 | 2>(1)
const createParentPickId = ref('')
const parentPickerVisible = ref(false)
const parentKeyword = ref('')
type ParentTreeRef = {
  filter?: (keyword: string) => void
  setCurrentKey?: (key: string | null) => void
}

const parentTreeRef = ref<ParentTreeRef | null>(null)
const creating = ref(false)
const generating = ref(false)
const formRef = ref<FormInstance>()
const createDialogMode = ref<'business' | 'region'>('business')

const form = ref({
  gb_id: '',
  name: '',
  parent_gb_id: '',
  civil_code: ''
})

const rules: FormRules = {
  gb_id: [
    {
      validator: (_rule, value: string, callback) => {
        const v = String(value || '').trim()
        if (!v) return callback()
        if (v.length > 20) return callback(new Error('节点编号长度不能超过20位'))
        callback()
      },
      trigger: 'blur'
    }
  ],
  name: [
    { required: true, message: '请输入节点名称', trigger: 'blur' }
  ],
  civil_code: [
    {
      validator: (_rule, value: string, callback) => {
        const v = String(value || '').trim()
        if (!v) return callback()
        if (!/^\d{6}$/.test(v)) return callback(new Error('行政区划码必须是6位数字'))
        callback()
      },
      trigger: 'blur'
    }
  ]
}

watch(() => props.visible, (val) => {
  if (val) {
    createDialogMode.value = props.treeMode
    createParentPickId.value = props.initParentId
    form.value = {
      gb_id: '',
      name: '',
      parent_gb_id: props.initParentId,
      civil_code: props.treeMode === 'region' ? props.initRegionCode : ''
    }
    createDialogStep.value = 1
  }
})

watch(parentKeyword, (keyword) => {
  parentTreeRef.value?.filter?.(keyword)
})

const createParentTreeOptions = computed(() => {
  const walk = (nodes: Record<string, unknown>[]): Record<string, unknown>[] => {
    return (nodes || []).map((node: TreeNode) => {
      const nodeType = String(node?.nodeType || '').toLowerCase()
      const allow = ['root', 'region', 'directory'].includes(nodeType)
      return {
        ...node,
        disabled: !allow,
        children: walk(Array.isArray(node?.children) ? node.children : [])
      }
    })
  }
  return walk(props.treeData)
})

const createParentLabel = computed(() => {
  const id = String(form.value.parent_gb_id || '').trim()
  if (!id) return '根资源组'
  return props.nodeLabelMap.get(id) || id
})

const selectedParentLabel = computed(() => {
  const id = String(createParentPickId.value || '').trim()
  if (!id) return ''
  return props.nodeLabelMap.get(id) || id
})

const clearSelectedParent = () => {
  createParentPickId.value = ''
}

const filterParentNode = (keyword: string, data: Record<string, unknown>) => {
  const q = String(keyword || '').trim().toLowerCase()
  if (!q) return true
  const text = [
    String(data?.label || ''),
    String(data?.name || ''),
    String(data?.id || ''),
    String(data?.gb_id || ''),
  ].join(' ').toLowerCase()
  return text.includes(q)
}

const onParentPopoverShow = () => {
  nextTick(() => {
    parentTreeRef.value?.setCurrentKey?.(createParentPickId.value || null)
    parentTreeRef.value?.filter?.(parentKeyword.value)
  })
}

const handleParentNodeClick = (data: Record<string, unknown>) => {
  if (!data || data.disabled) return
  const id = String(data?.id || '').trim()
  if (!id) return
  createParentPickId.value = id
  parentPickerVisible.value = false
}

const applyParent = () => {
  const parentId = String(createParentPickId.value || '').trim()
  if (!parentId) return false
  const mode = props.treeMode === 'region' || parentId.startsWith('region:') ? 'region' : 'business'
  createDialogMode.value = mode
  form.value.parent_gb_id = parentId
  if (mode === 'region') {
    const regionCode = parentId.startsWith('region:') ? parentId.split(':', 2)[1] : ''
    if (regionCode && regionCode !== 'root') {
      form.value.civil_code = String(regionCode).replace(/\D/g, '').slice(0, 6)
    }
  } else {
    form.value.civil_code = ''
  }
  return true
}

const goStep2 = async () => {
  if (!applyParent()) {
    ElMessage.warning('请先选择上级节点')
    return
  }
  createDialogStep.value = 2
  if (!String(form.value.gb_id || '').trim()) {
    await generateGbId()
  }
}

const generateGbId = async () => {
  generating.value = true
  try {
    const parentRegionCode = String(form.value.parent_gb_id || '').replace(/^region:/, '').replace(/\D/g, '').slice(0, 6)
    const targetCivilCode = String(form.value.civil_code || '').trim() || parentRegionCode
    const res = await api.get('/api/v1/devices/directories/next-gb-id', {
      params: { civil_code: targetCivilCode || undefined }
    })
    const gbId = String(res.data?.gb_id || '').trim()
    if (!gbId) throw new Error('未获取到可用编号')
    form.value.gb_id = gbId
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    generating.value = false
  }
}

const submit = async () => {
  if (!String(form.value.gb_id || '').trim()) {
    await generateGbId()
  }
  if (!String(form.value.gb_id || '').trim()) {
    ElMessage.warning('无法自动生成节点编号，请手动填写')
    return
  }
  if (createDialogMode.value === 'business') {
    const pid = String(form.value.parent_gb_id || '').trim()
    if (!pid) {
      const rootId = props.businessRootId
      if (rootId) form.value.parent_gb_id = rootId
    }
  }
  if (createDialogMode.value === 'region') {
    const parentId = String(form.value.parent_gb_id || '').trim()
    const civilCode = String(form.value.civil_code || '').trim()
    const finalParentId = parentId || 'region:root'
    form.value.parent_gb_id = finalParentId
    if (civilCode && !/^\d{6}$/.test(civilCode)) {
      ElMessage.warning('行政区划码必须是6位数字')
      return
    }
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    await api.post('/api/v1/devices/directories', {
      name: form.value.name,
      gb_id: form.value.gb_id,
      parent_gb_id: form.value.parent_gb_id || null,
      civil_code: form.value.civil_code || null
    })
    ElMessage.success('创建成功')
    emit('success')
    emit('update:visible', false)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.create-directory-parent-popper {
  max-width: min(92vw, 760px) !important;
}

.parent-picker-panel {
  width: min(84vw, 760px);
  max-width: 100%;
}

.parent-picker-search {
  margin-bottom: 8px;
}

.parent-picker-tree {
  max-height: 52vh;
  overflow: auto;
}

.parent-picker-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 32px;
  align-items: flex-start;
  padding-top: 6px;
  padding-bottom: 6px;
}

.parent-picker-tree :deep(.el-tree-node__label) {
  white-space: normal;
  line-height: 1.35;
  word-break: break-all;
}
</style>
