<template>
  <AppDialog
    v-model="visible"
    :title="dialogTitle"
    size="medium"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item :label="t('businessFilter.province')">
        <el-select v-model="form.province" filterable :placeholder="t('businessFilter.provincePlaceholder')" style="width: 100%">
          <el-option v-for="item in provinces" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('businessFilter.cityCode')">
        <el-select v-model="form.city" filterable allow-create default-first-option :placeholder="t('businessFilter.cityPlaceholder')" style="width: 100%">
          <el-option v-for="item in cityOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('businessFilter.districtCode')">
        <el-select v-model="form.district" filterable allow-create default-first-option :placeholder="t('businessFilter.districtPlaceholder')" style="width: 100%">
          <el-option v-for="item in districtOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('businessFilter.suffixLabel')">
        <el-input v-model="form.suffix" maxlength="2" :placeholder="t('businessFilter.suffixPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('businessFilter.previewLabel')">
        <div class="civil-code-preview">
          <div class="preview-code">{{ previewDisplay }}</div>
          <div class="preview-name">{{ namePreview }}</div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="handleSubmit">{{ confirmLabel }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  title?: string
  targetGbIds: string[]
  targetNames: string[]
  mode: 'single' | 'batch_region'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const dialogTitle = computed(() => props.title || t('businessFilter.defaultTitle'))
const confirmLabel = computed(() => props.mode === 'batch_region' ? t('businessFilter.batchSet') : t('common.ok'))

const saving = ref(false)
const form = ref({ province: '', city: '', district: '', suffix: '' })

const provinces = [
  { name: '北京', code: '11' }, { name: '天津', code: '12' }, { name: '河北', code: '13' },
  { name: '山西', code: '14' }, { name: '内蒙古', code: '15' }, { name: '辽宁', code: '21' },
  { name: '吉林', code: '22' }, { name: '黑龙江', code: '23' }, { name: '上海', code: '31' },
  { name: '江苏', code: '32' }, { name: '浙江', code: '33' }, { name: '安徽', code: '34' },
  { name: '福建', code: '35' }, { name: '江西', code: '36' }, { name: '山东', code: '37' },
  { name: '河南', code: '41' }, { name: '湖北', code: '42' }, { name: '湖南', code: '43' },
  { name: '广东', code: '44' }, { name: '广西', code: '45' }, { name: '海南', code: '46' },
  { name: '重庆', code: '50' }, { name: '四川', code: '51' }, { name: '贵州', code: '52' },
  { name: '云南', code: '53' }, { name: '西藏', code: '54' }, { name: '陕西', code: '61' },
  { name: '甘肃', code: '62' }, { name: '青海', code: '63' }, { name: '宁夏', code: '64' },
  { name: '新疆', code: '65' }
]

const cityMap: Record<string, { name: string; code: string }[]> = {
  '11': [{ name: '市辖区', code: '1101' }],
  '31': [{ name: '市辖区', code: '3101' }],
  '50': [{ name: '市辖区', code: '5001' }]
}

const cityOptions = computed(() => cityMap[form.value.province] || [{ name: '自定义', code: form.value.city || '01' }])
const districtOptions = computed(() => [{ name: '自定义', code: form.value.district || '01' }])

watch(() => form.value.province, () => {
  form.value.city = ''
  form.value.district = ''
  form.value.suffix = ''
})

watch(() => props.modelValue, (val) => {
  if (val) {
    form.value = { province: '', city: '', district: '', suffix: '' }
  }
})

const previewDisplay = computed(() => {
  const p = String(form.value.province || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const c = String(form.value.city || '').replace(/\D/g, '').slice(-2).padStart(2, '0')
  const d = String(form.value.district || '').replace(/\D/g, '').slice(-2).padStart(2, '0')
  const s = String(form.value.suffix || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  return `${p}${c}${d}${s}`
})

const namePreview = computed(() => {
  const pn = provinces.find(x => x.code === form.value.province)?.name || t('businessFilter.notSelected')
  return pn
})

const handleSubmit = async () => {
  if (!form.value.province) {
    ElMessage.warning(t('businessFilter.selectProvince'))
    return
  }
  const civilCode = previewDisplay.value
  if (civilCode.length !== 8) {
    ElMessage.warning(t('businessFilter.codeLengthError'))
    return
  }
  saving.value = true
  try {
    if (props.mode === 'batch_region') {
      await api.post('/api/v1/devices/channels/batch-update-civil-code', {
        gb_ids: props.targetGbIds,
        civil_code: civilCode
      })
      ElMessage.success(t('businessFilter.batchSetSuccess', { count: props.targetGbIds.length }))
    } else {
      // single mode handled by parent
    }
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

<style scoped>
.civil-code-preview {
  display: flex;
  align-items: center;
  gap: 12px;
}

.preview-code {
  font-family: 'Courier New', monospace;
  font-size: 16px;
  font-weight: 700;
  color: var(--el-color-primary);
  background: var(--el-fill-color-lightest);
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
}

.preview-name {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
