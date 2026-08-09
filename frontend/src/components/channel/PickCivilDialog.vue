<template>
  <AppDialog
    v-model="visible"
    :title="t('pickCivilDlg.title')"
    size="small"
    width="520px"
    @closed="onClosed"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item :label="t('pickCivilDlg.province')">
        <el-select v-model="form.province" filterable :placeholder="t('pickCivilDlg.provinceCodePlaceholder')" class="w-full">
          <el-option v-for="p in provinces" :key="p.code" :label="`${p.name} - ${p.code}`" :value="p.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('pickCivilDlg.city')">
        <el-select v-model="form.city" filterable allow-create default-first-option :placeholder="t('pickCivilDlg.cityCodePlaceholder')" class="w-full">
          <el-option v-for="c in cityOpts" :key="c.code" :label="`${c.name} - ${c.code}`" :value="c.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('pickCivilDlg.district')">
        <el-select v-model="form.district" filterable allow-create default-first-option :placeholder="t('pickCivilDlg.districtCodePlaceholder')" class="w-full">
          <el-option v-for="d in districtOpts" :key="d.code" :label="`${d.name} - ${d.code}`" :value="d.code" />
        </el-select>
      </el-form-item>
    </el-form>
    <div class="text-sm mt-2" style="color: var(--el-text-color-secondary)">{{ t('pickCivilDlg.preview') }}{{ preview6 }}（{{ previewName }}）</div>
    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="confirm">{{ t('common.ok') }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'

const { t } = useI18n()

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'picked', code: string, name: string): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const provinceCodes = [
  '11', '12', '13', '14', '15',
  '21', '22', '23',
  '31', '32', '33', '34', '35', '36', '37',
  '41', '42', '43', '44', '45', '46',
  '50', '51', '52', '53', '54',
  '61', '62', '63', '64', '65'
]

const provinces = computed(() => provinceCodes.map(code => ({
  code,
  name: t(`pickCivilDlg.province_${code}`)
})))

const cityMap: Record<string, { code: string }[]> = {
  '11': [{ code: '1101' }],
  '31': [{ code: '3101' }],
  '50': [{ code: '5001' }]
}

const form = ref({ province: '', city: '', district: '' })

const cityOpts = computed(() => {
  const list = cityMap[form.value.province]
  if (list) {
    return list.map(c => ({
      code: c.code,
      name: t('pickCivilDlg.municipalArea')
    }))
  }
  return [{ name: t('pickCivilDlg.custom'), code: form.value.city || '01' }]
})

const districtOpts = computed(() => [{ name: t('pickCivilDlg.custom'), code: form.value.district || '01' }])

const preview6 = computed(() => {
  const p = String(form.value.province || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const c = String(form.value.city || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const d = String(form.value.district || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  return `${p}${c}${d}`
})

const previewName = computed(() => {
  const pn = provinces.value.find(x => x.code === form.value.province)?.name || ''
  return pn || t('pickCivilDlg.notSelected')
})

watch(
  () => form.value.province,
  () => {
    form.value.city = ''
    form.value.district = ''
  }
)

const onClosed = () => {
  form.value = { province: '', city: '', district: '' }
}

const confirm = () => {
  if (!form.value.province || !form.value.city || !form.value.district) {
    ElMessage.warning(t('pickCivilDlg.pleaseCompleteSelection'))
    return
  }
  const code = preview6.value
  if (code.length !== 6) {
    ElMessage.warning(t('pickCivilDlg.codeMustBe6Digits'))
    return
  }
  emit('picked', code, previewName.value)
  visible.value = false
}
</script>
