<template>
  <!-- 通道编辑对话框 -->
  <ChannelEditDialog
    :visible="props.channelEditDialogVisible"
    @update:visible="(v: boolean) => emit('update:channelEditDialogVisible', v)"
    :channel-data="channelEditData"
    @success="emit('loadChannels')"
  />

  <!-- 创建目录对话框 -->
  <CreateDirectoryDialog
    :visible="props.createDirectoryDialogVisible"
    @update:visible="(v: boolean) => emit('update:createDirectoryDialogVisible', v)"
    :tree-data="treeData"
    :node-label-map="nodeLabelMap"
    :tree-mode="treeMode"
    :business-root-id="businessRootId"
    :init-parent-id="createDirectoryInitParentId"
    :init-region-code="createDirectoryInitRegionCode"
    @success="emit('loadTree')"
  />

  <RenameDirectoryDialog
    :model-value="props.renameDirectoryDialogVisible"
    @update:model-value="(v: boolean) => emit('update:renameDirectoryDialogVisible', v)"
    :node-id="renameDirectoryDialogId"
    :node-name="renameDirectoryDialogName"
    @success="emit('loadTree')"
  />

  <AddChannelDialog
    :visible="props.addChannelDialogVisible"
    @update:visible="(v: boolean) => emit('update:addChannelDialogVisible', v)"
    @success="emit('loadChannels')"
  />

  <BusinessPickerDialog
    :model-value="props.listBusinessFilterDialogVisible"
    @update:model-value="(v: boolean) => emit('update:listBusinessFilterDialogVisible', v)"
    :title="t('channelBatch.filterBusinessTitle')"
    mode="filter"
    @tree-click="emit('businessFilterTreeClick', $event)"
    @confirm="emit('businessFilterConfirm', $event)"
  />

  <BusinessPickerDialog
    :model-value="props.batchBusinessDialogVisible"
    @update:model-value="(v: boolean) => emit('update:batchBusinessDialogVisible', v)"
    :title="t('channelBatch.batchSetBusinessTitle')"
    mode="batch"
    @tree-click="emit('batchBusinessTreeClick', $event)"
    @confirm="emit('batchBusinessConfirm', $event)"
  />

  <AppDialog :model-value="props.civilCodeDialogVisible" @update:model-value="(v: boolean) => emit('update:civilCodeDialogVisible', v)" :title="civilCodeDialogTitle" size="medium">
    <el-form :model="civilCodeForm" label-width="100px">
      <el-form-item :label="t('channelBatch.province')">
        <el-select v-model="civilCodeForm.province" filterable :placeholder="t('channelBatch.selectProvinceCode')" style="width: 100%">
          <el-option v-for="item in provinceOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('channelBatch.cityCode')">
        <el-select v-model="civilCodeForm.city" filterable allow-create default-first-option :placeholder="t('channelBatch.selectCityCode')" style="width: 100%">
          <el-option v-for="item in cityOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('channelBatch.districtCode')">
        <el-select v-model="civilCodeForm.district" filterable allow-create default-first-option :placeholder="t('channelBatch.selectDistrictCode')" style="width: 100%">
          <el-option v-for="item in districtOptions" :key="item.code" :label="`${item.name} - ${item.code}`" :value="item.code" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('channelBatch.lastTwoDigits')">
        <el-input v-model="civilCodeForm.suffix" maxlength="2" :placeholder="t('channelBatch.twoDigitsPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('channelBatch.codePreview')">
        <div class="civil-code-preview">
          <div class="preview-code">{{ civilCodePreviewDisplay }}</div>
          <div class="preview-name">{{ civilCodeNamePreview }}</div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:civilCodeDialogVisible', false)">{{ t('channelBatch.cancel') }}</el-button>
      <el-button type="primary" @click="emit('applyCivilCode')">{{ civilCodeDialogConfirmLabel }}</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppDialog from '../../components/common/AppDialog.vue'
import ChannelEditDialog from '../../components/channel/ChannelEditDialog.vue'
import AddChannelDialog from '../../components/channel/AddChannelDialog.vue'
import CreateDirectoryDialog from '../../components/channel/CreateDirectoryDialog.vue'
import RenameDirectoryDialog from '../../components/channel/RenameDirectoryDialog.vue'
import BusinessPickerDialog from '../../components/channel/BusinessPickerDialog.vue'
import type { Channel } from '@/types/models'

const { t } = useI18n()

const props = defineProps<{
  treeData: Channel[]
  treeMode: 'business' | 'region'
  nodeLabelMap: Map<string, string>
  businessRootId: string
  regionTreeOptions: Channel[]

  channelEditDialogVisible: boolean
  channelEditData: Channel | null
  createDirectoryDialogVisible: boolean
  createDirectoryInitParentId: string
  createDirectoryInitRegionCode: string
  renameDirectoryDialogVisible: boolean
  renameDirectoryDialogId: string
  renameDirectoryDialogName: string
  addChannelDialogVisible: boolean
  listBusinessFilterDialogVisible: boolean
  batchBusinessDialogVisible: boolean
  civilCodeDialogVisible: boolean
  civilPickerTarget: 'create' | 'list_filter' | 'batch_region'
  civilCodeForm: {
    province: string
    city: string
    district: string
    suffix: string
  }
}>()

const emit = defineEmits<{
  (e: 'loadTree'): void
  (e: 'loadChannels'): void
  (e: 'update:channelEditDialogVisible', value: boolean): void
  (e: 'update:createDirectoryDialogVisible', value: boolean): void
  (e: 'update:renameDirectoryDialogVisible', value: boolean): void
  (e: 'update:addChannelDialogVisible', value: boolean): void
  (e: 'update:listBusinessFilterDialogVisible', value: boolean): void
  (e: 'update:batchBusinessDialogVisible', value: boolean): void
  (e: 'update:civilCodeDialogVisible', value: boolean): void
  (e: 'applyCivilCode'): void
  (e: 'businessFilterTreeClick', data: { id: string; label: string }): void
  (e: 'businessFilterConfirm', nodeId: string): void
  (e: 'batchBusinessTreeClick', data: { id: string; label: string }): void
  (e: 'batchBusinessConfirm', nodeId: string): void
}>()

const civilCodeDialogTitle = computed(() => {
  switch (props.civilPickerTarget) {
    case 'list_filter': return t('channelBatch.civilCodeFilter')
    case 'batch_region': return t('channelBatch.batchSetRegionCode')
    default: return t('channelBatch.generateCivilCode')
  }
})

const civilCodeDialogConfirmLabel = computed(() => {
  switch (props.civilPickerTarget) {
    case 'list_filter': return t('channelBatch.confirm')
    case 'batch_region': return t('channelBatch.confirmApply')
    default: return t('channelBatch.generateAndUse')
  }
})

// Province/city/district options (static data)
const provinceOptions = [
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
  { name: '新疆', code: '65' }, { name: '台湾', code: '71' }, { name: '香港', code: '81' },
  { name: '澳门', code: '82' }
]

const cityOptionsMap: Record<string, Array<{ name: string; code: string }>> = {
  '11': [{ name: '北京市', code: '01' }],
  '12': [{ name: '天津市', code: '01' }],
  '31': [{ name: '上海市', code: '01' }],
  '50': [{ name: '重庆市', code: '01' }],
  '44': [{ name: '广州市', code: '01' }, { name: '深圳市', code: '03' }, { name: '珠海市', code: '04' }, { name: '佛山市', code: '06' }],
  '32': [{ name: '南京市', code: '01' }, { name: '无锡市', code: '02' }, { name: '徐州市', code: '03' }, { name: '苏州市', code: '05' }],
  '33': [{ name: '杭州市', code: '01' }, { name: '宁波市', code: '02' }, { name: '温州市', code: '03' }]
}

const districtOptionsMap: Record<string, Array<{ name: string; code: string }>> = {
  '11-01': [{ name: '东城区', code: '01' }, { name: '西城区', code: '02' }, { name: '朝阳区', code: '05' }, { name: '海淀区', code: '08' }],
  '31-01': [{ name: '黄浦区', code: '01' }, { name: '徐汇区', code: '04' }, { name: '浦东新区', code: '15' }],
  '44-01': [{ name: '越秀区', code: '04' }, { name: '天河区', code: '06' }, { name: '白云区', code: '11' }],
  '44-03': [{ name: '罗湖区', code: '03' }, { name: '福田区', code: '04' }, { name: '南山区', code: '05' }]
}

const fallbackCityOptions = computed(() => cityOptionsMap[props.civilCodeForm.province] || [])
const fallbackDistrictOptions = computed(() => {
  const key = `${props.civilCodeForm.province}-${props.civilCodeForm.city}`
  return districtOptionsMap[key] || []
})

const dynamicProvinceOptions = computed(() => {
  return (props.regionTreeOptions || [])
    .map((item: Record<string, unknown>) => ({
      name: String(item?.name || ''),
      code: String(item?.code || '').slice(0, 2),
      children: Array.isArray(item?.children) ? item.children : []
    }))
    .filter((item: Record<string, unknown>) => /^\d{2}$/.test(item.code))
})

const cityOptions = computed(() => {
  const province = dynamicProvinceOptions.value.find((item: Record<string, unknown>) => item.code === props.civilCodeForm.province)
  if (!province) return fallbackCityOptions.value
  return (province.children || [])
    .map((item: Record<string, unknown>) => ({
      name: String(item?.name || ''),
      code: String(item?.code || '').slice(2, 4),
      children: Array.isArray(item?.children) ? item.children : []
    }))
    .filter((item: Record<string, unknown>) => /^\d{2}$/.test(item.code))
})

const districtOptions = computed(() => {
  const province = dynamicProvinceOptions.value.find((item: Record<string, unknown>) => item.code === props.civilCodeForm.province)
  if (!province) return fallbackDistrictOptions.value
  const city = (province.children || []).find((item: Record<string, unknown>) => String(item?.code || '').slice(2, 4) === props.civilCodeForm.city)
  if (!city) return fallbackDistrictOptions.value
  return (city.children || [])
    .map((item: Record<string, unknown>) => ({
      name: String(item?.name || ''),
      code: String(item?.code || '').slice(4, 6)
    }))
    .filter((item: Record<string, unknown>) => /^\d{2}$/.test(item.code))
})

const selectedProvinceName = computed(() => {
  const found = provinceOptions.find((item: Record<string, unknown>) => item.code === props.civilCodeForm.province)
  return found?.name || t('channelBatch.unselectedProvince')
})

const selectedCityName = computed(() => {
  const found = cityOptions.value.find((item: Record<string, unknown>) => item.code === props.civilCodeForm.city)
  return found?.name || (props.civilCodeForm.city ? t('channelBatch.cityCodeLabel', { code: props.civilCodeForm.city }) : t('channelBatch.unselectedCity'))
})

const selectedDistrictName = computed(() => {
  const found = districtOptions.value.find((item: Record<string, unknown>) => item.code === props.civilCodeForm.district)
  return found?.name || (props.civilCodeForm.district ? t('channelBatch.districtCodeLabel', { code: props.civilCodeForm.district }) : t('channelBatch.unselectedDistrict'))
})

const civilCodePreview = computed(() => {
  const p = String(props.civilCodeForm.province || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const c = String(props.civilCodeForm.city || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  const d = String(props.civilCodeForm.district || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
  return `${p}${c}${d}`
})

const civilCodeSuffix = computed(() => String(props.civilCodeForm.suffix || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0'))

const civilCodePreviewDisplay = computed(() => {
  const code = civilCodePreview.value
  return `${code.slice(0, 2)} ${code.slice(2, 4)} ${code.slice(4, 6)} ${civilCodeSuffix.value}  =>  ${code}${civilCodeSuffix.value}`
})

const civilCodeNamePreview = computed(() => `${selectedProvinceName.value} / ${selectedCityName.value} / ${selectedDistrictName.value}`)
</script>

<style scoped>
.civil-code-preview {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
}
.preview-code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.preview-name {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.cm-rename-dialog :deep(.el-dialog),
.cm-civil-code-dialog :deep(.el-dialog),
.cm-business-filter-dialog :deep(.el-dialog),
.cm-batch-business-dialog :deep(.el-dialog) {
  border-radius: 10px;
}
.cm-rename-dialog :deep(.el-dialog__header),
.cm-civil-code-dialog :deep(.el-dialog__header),
.cm-business-filter-dialog :deep(.el-dialog__header),
.cm-batch-business-dialog :deep(.el-dialog__header) {
  padding: 14px 18px 12px;
  background: #f8fafc;
}
.cm-rename-dialog :deep(.el-dialog__body),
.cm-civil-code-dialog :deep(.el-dialog__body),
.cm-business-filter-dialog :deep(.el-dialog__body),
.cm-batch-business-dialog :deep(.el-dialog__body) {
  padding: 14px 18px;
}
.cm-rename-dialog :deep(.el-dialog__footer),
.cm-civil-code-dialog :deep(.el-dialog__footer),
.cm-business-filter-dialog :deep(.el-dialog__footer),
.cm-batch-business-dialog :deep(.el-dialog__footer) {
  padding: var(--el-dialog-footer-padding);
}
</style>
