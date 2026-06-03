<template>
  <AppDialog
    v-model="visible"
    title="选择行政区划"
    size="small"
    width="520px"
    @closed="onClosed"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item label="省份">
        <el-select v-model="form.province" filterable placeholder="省份代码" class="w-full">
          <el-option v-for="p in provinces" :key="p.code" :label="`${p.name} - ${p.code}`" :value="p.code" />
        </el-select>
      </el-form-item>
      <el-form-item label="城市">
        <el-select v-model="form.city" filterable allow-create default-first-option placeholder="两位市级代码" class="w-full">
          <el-option v-for="c in cityOpts" :key="c.code" :label="`${c.name} - ${c.code}`" :value="c.code" />
        </el-select>
      </el-form-item>
      <el-form-item label="区县">
        <el-select v-model="form.district" filterable allow-create default-first-option placeholder="两位区县代码" class="w-full">
          <el-option v-for="d in districtOpts" :key="d.code" :label="`${d.name} - ${d.code}`" :value="d.code" />
        </el-select>
      </el-form-item>
    </el-form>
    <div class="text-sm mt-2" style="color: var(--el-text-color-secondary)">预览：{{ preview6 }}（{{ previewName }}）</div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="confirm">确定</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'picked', code: string, name: string): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const provinces = [
  { name: '北京', code: '11' },
  { name: '天津', code: '12' },
  { name: '河北', code: '13' },
  { name: '山西', code: '14' },
  { name: '内蒙古', code: '15' },
  { name: '辽宁', code: '21' },
  { name: '吉林', code: '22' },
  { name: '黑龙江', code: '23' },
  { name: '上海', code: '31' },
  { name: '江苏', code: '32' },
  { name: '浙江', code: '33' },
  { name: '安徽', code: '34' },
  { name: '福建', code: '35' },
  { name: '江西', code: '36' },
  { name: '山东', code: '37' },
  { name: '河南', code: '41' },
  { name: '湖北', code: '42' },
  { name: '湖南', code: '43' },
  { name: '广东', code: '44' },
  { name: '广西', code: '45' },
  { name: '海南', code: '46' },
  { name: '重庆', code: '50' },
  { name: '四川', code: '51' },
  { name: '贵州', code: '52' },
  { name: '云南', code: '53' },
  { name: '西藏', code: '54' },
  { name: '陕西', code: '61' },
  { name: '甘肃', code: '62' },
  { name: '青海', code: '63' },
  { name: '宁夏', code: '64' },
  { name: '新疆', code: '65' }
]

const cityMap: Record<string, { name: string; code: string }[]> = {
  '11': [{ name: '市辖区', code: '1101' }],
  '31': [{ name: '市辖区', code: '3101' }],
  '50': [{ name: '市辖区', code: '5001' }]
}

const form = ref({ province: '', city: '', district: '' })

const cityOpts = computed(() => {
  return cityMap[form.value.province] || [{ name: '自定义', code: form.value.city || '01' }]
})

const districtOpts = computed(() => [{ name: '自定义', code: form.value.district || '01' }])

const preview6 = computed(() => {
  const p = String(form.value.province || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const c = String(form.value.city || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const d = String(form.value.district || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  return `${p}${c}${d}`
})

const previewName = computed(() => {
  const pn = provinces.find(x => x.code === form.value.province)?.name || ''
  return pn || '未选择'
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
    ElMessage.warning('请完整选择省/市/县（或输入两位代码）')
    return
  }
  const code = preview6.value
  if (code.length !== 6) {
    ElMessage.warning('区划码应为6位数字')
    return
  }
  emit('picked', code, previewName.value)
  visible.value = false
}
</script>
