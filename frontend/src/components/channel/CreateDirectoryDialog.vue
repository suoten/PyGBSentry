<template>
  <AppDialog
    v-model="visible"
    :title="t('createDirDlg.title')"
    size="small"
    width="500px"
  >
    <el-steps :active="createDialogStep - 1" simple class="mb-3">
      <el-step :title="t('createDirDlg.stepSelectParent')" />
      <el-step :title="t('createDirDlg.stepFillInfo')" />
    </el-steps>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <template v-if="createDialogStep === 1">
        <el-form-item :label="t('createDirDlg.parentNode')">
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
                :placeholder="t('createDirDlg.parentPlaceholder')"
                @clear="clearSelectedParent"
              />
            </template>
            <div class="parent-picker-panel">
              <el-input
                v-model="parentKeyword"
                size="small"
                clearable
                :placeholder="t('createDirDlg.searchPlaceholder')"
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
            {{ t('createDirDlg.subNodeTip') }}
          </div>
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item :label="t('createDirDlg.parentNode')">
          <el-input :model-value="createParentLabel" disabled />
        </el-form-item>
        <el-form-item :label="t('createDirDlg.nodeId')" prop="gb_id">
          <el-input v-model="form.gb_id" :placeholder="t('createDirDlg.nodeIdPlaceholder')">
            <template #append>
              <el-button :loading="generating" @click="generateGbId">{{ t('createDirDlg.generate') }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item :label="t('createDirDlg.nodeName')" prop="name">
          <el-input v-model="form.name" :placeholder="t('createDirDlg.nodeNamePlaceholder')" />
        </el-form-item>
        <el-form-item v-if="createDialogMode === 'region'" :label="t('createDirDlg.civilCode')" prop="civil_code">
          <el-input
            v-model="form.civil_code"
            :placeholder="t('createDirDlg.civilCodePlaceholder')"
            maxlength="6"
          />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button v-if="createDialogStep === 2" @click="createDialogStep = 1">{{ t('createDirDlg.prevStep') }}</el-button>
      <el-button v-if="createDialogStep === 1" type="primary" @click="goStep2">{{ t('createDirDlg.nextStep') }}</el-button>
      <el-button v-else type="primary" :loading="creating" @click="submit">{{ t('createDirDlg.confirm') }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import api from '@/utils/http'
import { getFriendlyError } from '../../utils/errorMessage'
import AppDialog from '../common/AppDialog.vue'
import type { TreeNode } from '@/types/models'

const { t } = useI18n()

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

const rules = computed<FormRules>(() => ({
  gb_id: [
    {
      validator: (_rule, value: string, callback) => {
        const v = String(value || '').trim()
        if (!v) return callback()
        if (v.length > 20) return callback(new Error(t('createDirDlg.nodeIdTooLong')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  name: [
    { required: true, message: t('createDirDlg.nodeNameRequired'), trigger: 'blur' }
  ],
  civil_code: [
    {
      validator: (_rule, value: string, callback) => {
        const v = String(value || '').trim()
        if (!v) return callback()
        if (!/^\d{6}$/.test(v)) return callback(new Error(t('createDirDlg.civilCodeInvalid')))
        callback()
      },
      trigger: 'blur'
    }
  ]
}))

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
    return (nodes || []).map((node) => {
      const nodeType = String(node?.nodeType || '').toLowerCase()
      const allow = ['root', 'region', 'directory'].includes(nodeType)
      return {
        ...node,
        disabled: !allow,
        children: walk(Array.isArray(node?.children) ? (node.children as Record<string, unknown>[]) : [])
      }
    })
  }
  return walk(props.treeData)
})

const createParentLabel = computed(() => {
  const id = String(form.value.parent_gb_id || '').trim()
  if (!id) return t('createDirDlg.rootGroup')
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
    ElMessage.warning(t('createDirDlg.pleaseSelectParent'))
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
    if (!gbId) throw new Error(t('createDirDlg.noAvailableId'))
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
    ElMessage.warning(t('createDirDlg.cannotAutoGenId'))
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
      ElMessage.warning(t('createDirDlg.civilCodeInvalid'))
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
    ElMessage.success(t('createDirDlg.createSuccess'))
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
