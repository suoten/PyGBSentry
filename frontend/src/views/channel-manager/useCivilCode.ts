import { ref } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from '../../utils/errorMessage'
import { logger } from '@/utils/logger'
import i18n from '@/locales'

export const provinceOptions = [
  { name: '北京', code: '11' }, { name: '天津', code: '12' }, { name: '河北', code: '13' }, { name: '山西', code: '14' }, { name: '内蒙古', code: '15' },
  { name: '辽宁', code: '21' }, { name: '吉林', code: '22' }, { name: '黑龙江', code: '23' }, { name: '上海', code: '31' }, { name: '江苏', code: '32' },
  { name: '浙江', code: '33' }, { name: '安徽', code: '34' }, { name: '福建', code: '35' }, { name: '江西', code: '36' }, { name: '山东', code: '37' },
  { name: '河南', code: '41' }, { name: '湖北', code: '42' }, { name: '湖南', code: '43' }, { name: '广东', code: '44' }, { name: '广西', code: '45' },
  { name: '海南', code: '46' }, { name: '重庆', code: '50' }, { name: '四川', code: '51' }, { name: '贵州', code: '52' }, { name: '云南', code: '53' },
  { name: '西藏', code: '54' }, { name: '陕西', code: '61' }, { name: '甘肃', code: '62' }, { name: '青海', code: '63' }, { name: '宁夏', code: '64' },
  { name: '新疆', code: '65' }, { name: '台湾', code: '71' }, { name: '香港', code: '81' }, { name: '澳门', code: '82' }
]

export const cityOptionsMap: Record<string, Array<{ name: string; code: string }>> = {
  '11': [{ name: '北京市', code: '01' }], '12': [{ name: '天津市', code: '01' }], '31': [{ name: '上海市', code: '01' }], '50': [{ name: '重庆市', code: '01' }],
  '44': [{ name: '广州市', code: '01' }, { name: '深圳市', code: '03' }, { name: '珠海市', code: '04' }, { name: '佛山市', code: '06' }],
  '32': [{ name: '南京市', code: '01' }, { name: '无锡市', code: '02' }, { name: '徐州市', code: '03' }, { name: '苏州市', code: '05' }],
  '33': [{ name: '杭州市', code: '01' }, { name: '宁波市', code: '02' }, { name: '温州市', code: '03' }]
}

export function useCivilCode(deps: {
  selectedChannels: { value: Record<string, unknown>[] }
  filters: { value: Record<string, unknown> }
  page: { value: number }
  civilCodeForm: { value: { province: string; city: string; district: string; suffix: string } }
  civilPickerTarget: { value: string }
  civilCodeDialogVisible: { value: boolean }
  createDirectoryForm: { value: { civil_code: string; gb_id: string } }
  systemSipId: { value: string }
  clearTableSelection: () => void
  loadTree: () => Promise<void>
  loadChannels: () => Promise<void>
  loadUnaddedCount: () => Promise<void>
}) {
  const batchPlacementLoading = ref(false)

  const openListCivilFilterPicker = () => {
    deps.civilPickerTarget.value = 'list_filter'
    const fb = String(deps.filters.value.listCivilPrefix || '').replace(/\D/g, '').slice(0, 6)
    const sip = String(deps.systemSipId.value || '').replace(/\D/g, '').slice(0, 6)
    const base = fb.length >= 6 ? fb : sip
    deps.civilCodeForm.value = { province: base.slice(0, 2), city: base.slice(2, 4), district: base.slice(4, 6), suffix: '01' }
    deps.civilCodeDialogVisible.value = true
  }

  const clearListCivilFilter = () => { deps.filters.value.listCivilPrefix = ''; deps.filters.value.listCivilLabel = ''; deps.page.value = 1; deps.loadChannels() }
  const openListBusinessFilterPicker = (dialogVisible: { value: boolean }) => { dialogVisible.value = true }
  const clearListBusinessFilter = () => { deps.filters.value.listBusinessParentGbId = ''; deps.filters.value.listBusinessParentLabel = ''; deps.page.value = 1; deps.loadChannels() }

  const applyCivilCode = async () => {
    if (!String(deps.civilCodeForm.value.province || '').trim()) { ElMessage.warning(i18n.global.t('civilCode.selectProvince')); return }
    if (!String(deps.civilCodeForm.value.city || '').trim()) { ElMessage.warning(i18n.global.t('civilCode.selectCity')); return }
    if (!String(deps.civilCodeForm.value.district || '').trim()) { ElMessage.warning(i18n.global.t('civilCode.selectDistrict')); return }
    const target = deps.civilPickerTarget.value
    const p = String(deps.civilCodeForm.value.province || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
    const c = String(deps.civilCodeForm.value.city || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
    const d = String(deps.civilCodeForm.value.district || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0')
    const six = `${p}${c}${d}`
    if (target === 'list_filter') {
      deps.filters.value.listCivilPrefix = six
      const pn = provinceOptions.find(item => item.code === deps.civilCodeForm.value.province)
      const cn = (cityOptionsMap[deps.civilCodeForm.value.province] || []).find(item => item.code === deps.civilCodeForm.value.city)
      deps.filters.value.listCivilLabel = `${pn?.name || ''} / ${cn?.name || ''}`
      deps.civilCodeDialogVisible.value = false; deps.page.value = 1; await deps.loadChannels(); return
    }
    if (target === 'batch_region') {
      if (!deps.selectedChannels.value.length) { ElMessage.warning(i18n.global.t('civilCode.selectChannelsFirst')); return }
      const ids = deps.selectedChannels.value.map((c: Record<string, unknown>) => String(c?.id || '').trim()).filter(Boolean); if (!ids.length) return
      batchPlacementLoading.value = true
      try { await api.post('/api/v1/devices/channels/batch-placement', { resource_ids: ids, placement: 'region', target_id: `region:${six}`, civil_code: six }); ElMessage.success(i18n.global.t('civilCode.batchRegionSet')); deps.civilCodeDialogVisible.value = false; deps.selectedChannels.value = []; deps.clearTableSelection(); await Promise.all([deps.loadTree(), deps.loadChannels()]) } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) } finally { batchPlacementLoading.value = false }
      return
    }
    if (!String(deps.civilCodeForm.value.suffix || '').trim()) { ElMessage.warning(i18n.global.t('civilCode.enterLastTwoDigits')); return }
    deps.createDirectoryForm.value.civil_code = six
    if (!String(deps.createDirectoryForm.value.gb_id || '').trim()) { const suffix = String(deps.civilCodeForm.value.suffix || '').replace(/\D/g, '').slice(0, 2).padStart(2, '0'); deps.createDirectoryForm.value.gb_id = `${six}${suffix}` }
    deps.civilCodeDialogVisible.value = false
  }

  const loadSystemSipId = async () => { try { const res = await api.get('/api/v1/system-config/system-info'); deps.systemSipId.value = String(res.data?.sip_id || '').trim() } catch { deps.systemSipId.value = ''; logger.warn('加载系统SIP ID失败') } }

  return { batchPlacementLoading, openListCivilFilterPicker, clearListCivilFilter, openListBusinessFilterPicker, clearListBusinessFilter, applyCivilCode, loadSystemSipId }
}
