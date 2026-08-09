import { ref } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from '../../utils/errorMessage'
import type { Channel } from '@/types/models'
import i18n from '@/locales'

const t = i18n.global.t

export function useBatchOps(deps: {
  selectedChannels: { value: Channel[] }
  selectedNode: { value: Channel | null }
  canAddToSelectedNode: { value: boolean }
  placementPayloadKey: { value: string }
  catalogParentId: (row: Record<string, unknown>) => string
  clearTableSelection: () => void
  loadTree: () => Promise<void>
  loadChannels: () => Promise<void>
  loadUnaddedCount: () => Promise<void>
}) {
  const batchPlacementLoading = ref(false)
  const batchBusinessDialogVisible = ref(false)
  const batchBusinessPickId = ref('')
  const listBusinessFilterDialogVisible = ref(false)
  const listBusinessFilterPickId = ref('')
  const listBusinessFilterPickLabel = ref('')

  const onBatchPlacementCommand = (cmd: string, civilPickerTarget: { value: string }, civilCodeForm: { value: Record<string, unknown> }, civilCodeDialogVisible: { value: boolean }, systemSipId: { value: string }) => {
    if (cmd === 'batch_region') { civilPickerTarget.value = 'batch_region'; const sip = String(systemSipId.value || '').replace(/\D/g, '').slice(0, 6); civilCodeForm.value = { province: sip.slice(0, 2), city: sip.slice(2, 4), district: sip.slice(4, 6), suffix: '01' }; civilCodeDialogVisible.value = true; return }
    if (cmd === 'batch_business') { batchBusinessDialogVisible.value = true; return }
    if (cmd === 'clear_region' || cmd === 'clear_business') batchClearPlacement(cmd)
  }

  const batchClearPlacement = async (cmd: string) => {
    const placement = cmd === 'clear_region' ? 'region' : 'business'; if (!deps.selectedChannels.value.length) return
    try { await ElMessageBox.confirm(t('channelBatchOps.confirmClearPlacement', { count: deps.selectedChannels.value.length, type: placement === 'region' ? t('channelBatchOps.placementTypeRegion') : t('channelBatchOps.placementTypeBusiness') }), t('channelBatchOps.confirmTitle'), { type: 'warning' }); await api.post('/api/v1/devices/channels/batch-placement', { resource_ids: deps.selectedChannels.value.map((c: Record<string, unknown>) => c.id), placement, target_id: '' }); ElMessage.success(t('channelBatchOps.cleared')); deps.selectedChannels.value = []; deps.clearTableSelection(); await Promise.all([deps.loadTree(), deps.loadChannels(), deps.loadUnaddedCount()]) } catch (e: unknown) { if (e !== 'cancel') ElMessage.error(getFriendlyError(e).message) }
  }

  const batchAddToSelectedNode = async () => {
    if (!deps.selectedNode.value || !deps.canAddToSelectedNode.value || deps.selectedChannels.value.length === 0) return
    const key = deps.placementPayloadKey.value; const nid = String(deps.selectedNode.value.id || '').trim(); const toAdd = deps.selectedChannels.value
    const alreadyMounted = toAdd.filter(ch => { const pid = key === 'region_parent_gb_id' ? ch.region_parent_gb_id : ch.parent_gb_id; return pid && pid !== nid })
    if (alreadyMounted.length > 0) { try { await ElMessageBox.confirm(t('channelBatchOps.confirmForceMove', { total: toAdd.length, count: alreadyMounted.length }), t('channelBatchOps.confirmTitle'), { type: 'warning', confirmButtonText: t('channelBatchOps.continueMove'), cancelButtonText: t('channelBatchOps.cancel') }) } catch { return } }
    try { await api.post('/api/v1/devices/channels/batch-placement', { resource_ids: toAdd.map(ch => ch.id), placement: key === 'region_parent_gb_id' ? 'region' : 'business', target_id: nid }); ElMessage.success(t('channelBatchOps.batchAdded', { count: toAdd.length })); toAdd.forEach(ch => { if (key === 'region_parent_gb_id') ch.region_parent_gb_id = nid; else ch.parent_gb_id = nid }); deps.selectedChannels.value = []; await Promise.all([deps.loadTree(), deps.loadChannels(), deps.loadUnaddedCount()]) } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) }
  }

  const batchRemoveFromNode = async () => {
    if (!deps.selectedNode.value || !deps.canAddToSelectedNode.value || deps.selectedChannels.value.length === 0) return
    const key = deps.placementPayloadKey.value; const nid = String(deps.selectedNode.value.id || '').trim(); const toRm = deps.selectedChannels.value.filter(ch => deps.catalogParentId(ch) === nid)
    if (!toRm.length) { ElMessage.warning(t('channelBatchOps.notBelongToNode')); return }
    try { await api.post('/api/v1/devices/channels/batch-placement', { resource_ids: toRm.map(ch => ch.id), placement: key === 'region_parent_gb_id' ? 'region' : 'business', target_id: '' }); ElMessage.success(t('channelBatchOps.batchRemoved', { count: toRm.length })); toRm.forEach(ch => { if (key === 'region_parent_gb_id') ch.region_parent_gb_id = null; else ch.parent_gb_id = null }); deps.selectedChannels.value = []; await Promise.all([deps.loadTree(), deps.loadChannels(), deps.loadUnaddedCount()]) } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) }
  }

  const removeFromNode = async (channel: Record<string, unknown>) => {
    try { const key = deps.placementPayloadKey.value; await api.put(`/api/v1/devices/channels/${channel.id}`, { [key]: null }); ElMessage.success(t('channelBatchOps.removeSuccess')); if (key === 'region_parent_gb_id') channel.region_parent_gb_id = null; else channel.parent_gb_id = null; await Promise.all([deps.loadTree(), deps.loadChannels()]) } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) }
  }

  const onBatchBusinessTreeClick = (data: { id: string; label: string }) => { batchBusinessPickId.value = data.id }
  const onBatchBusinessConfirm = async (nodeId: string) => {
    if (!nodeId) return; const ids = deps.selectedChannels.value.map((c: Record<string, unknown>) => String(c?.id || '').trim()).filter(Boolean); if (!ids.length) return; batchPlacementLoading.value = true
    try { await api.post('/api/v1/devices/channels/batch-placement', { resource_ids: ids, placement: 'business', target_id: nodeId }); ElMessage.success(t('channelBatchOps.businessSet')); batchBusinessDialogVisible.value = false; deps.selectedChannels.value = []; deps.clearTableSelection(); await Promise.all([deps.loadTree(), deps.loadChannels(), deps.loadUnaddedCount()]) } catch (e: unknown) { ElMessage.error(getFriendlyError(e).message) } finally { batchPlacementLoading.value = false }
  }

  const onBusinessFilterTreeClick = (data: { id: string; label: string }) => { listBusinessFilterPickId.value = data.id; listBusinessFilterPickLabel.value = data.label }
  const onBusinessFilterConfirm = (nodeId: string, filters: Record<string, unknown>, page: Record<string, unknown>, loadChannels: () => Promise<void>) => { if (!nodeId) return; filters.value.listBusinessParentGbId = nodeId; filters.value.listBusinessParentLabel = String(listBusinessFilterPickLabel.value || nodeId).trim(); listBusinessFilterDialogVisible.value = false; page.value = 1; loadChannels() }

  return { batchPlacementLoading, batchBusinessDialogVisible, batchBusinessPickId, listBusinessFilterDialogVisible, listBusinessFilterPickId, listBusinessFilterPickLabel, onBatchPlacementCommand, batchClearPlacement, batchAddToSelectedNode, batchRemoveFromNode, removeFromNode, onBatchBusinessTreeClick, onBatchBusinessConfirm, onBusinessFilterTreeClick, onBusinessFilterConfirm }
}
