<template>
  <PageContainer>
    <PageHeader :title="t('vodPage.title')" :description="t('vodPage.desc')" />
    <el-card>
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-semibold">{{ t('vodPage.listTitle') }}</span>
          <el-upload
            :show-file-list="false"
            accept=".mp4"
            :auto-upload="false"
            :on-change="handleFileChange"
          >
            <el-button type="primary" :loading="uploading" :title="t('vodPage.uploadTitle')">{{ t('vodPage.upload') }}</el-button>
          </el-upload>
        </div>
      </template>
      <el-alert type="info" :closable="false" class="mb-4" show-icon :title="t('vodPage.hint')" />
      <el-table v-loading="loading" :data="rows" stripe :empty-text="t('vodPage.empty')">
        <el-table-column prop="name" :label="t('vodPage.nameLabel')" min-width="180" show-overflow-tooltip />
        <el-table-column prop="file_size_text" :label="t('vodPage.sizeLabel')" width="110" />
        <el-table-column prop="created_by" :label="t('vodPage.createdByLabel')" width="130" show-overflow-tooltip />
        <el-table-column :label="t('common.action')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="playRow(row)">{{ t('vodPage.play') }}</el-button>
            <el-popconfirm :title="t('vodPage.deleteConfirm', { name: row.name })" @confirm="deleteRow(row)">
              <template #reference>
                <el-button type="danger" size="small" link>{{ t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <AdvancedVideoPlayerDialog
      v-model="playerVisible"
      :title="playingName"
      :urls="playingUrls"
      :request="playingRequest"
    />
  </PageContainer>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/http'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import AdvancedVideoPlayerDialog from '../components/AdvancedVideoPlayerDialog.vue'
import { getFriendlyError } from '../utils/errorMessage'

const { t } = useI18n()
const rows = ref<Array<{ id: string; name: string; original_name?: string; file_size_text: string; created_by?: string }>>([])
const loading = ref(false)
const uploading = ref(false)
const playerVisible = ref(false)
const playingName = ref('')
const playingUrls = ref<Record<string, string>>({})
const playingRequest = ref<{ status: 'ready'; message?: string }>({ status: 'ready' })

const loadList = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/vod/mp4-channels')
    rows.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    loading.value = false
  }
}

const handleFileChange = async (file: { raw?: File }) => {
  const raw = file?.raw
  if (!raw) return
  if (!raw.name.toLowerCase().endsWith('.mp4')) {
    ElMessage.error(t('vodPage.mp4Only'))
    return
  }
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', raw)
    await api.post('/api/v1/vod/mp4-channels', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
    ElMessage.success(t('vodPage.uploaded'))
    await loadList()
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || t('vodPage.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

const playRow = async (row: { id: string; name: string }) => {
  try {
    const res = await api.post(`/api/v1/vod/mp4-channels/${row.id}/play`)
    const urls = (res.data?.urls || {}) as Record<string, string>
    if (!Object.values(urls).some(Boolean)) {
      ElMessage.error(t('vodPage.noUrls'))
      return
    }
    playingName.value = row.name
    playingUrls.value = urls
    playingRequest.value = { status: 'ready' }
    playerVisible.value = true
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || t('vodPage.playFailed'))
  }
}

const deleteRow = async (row: { id: string; name: string }) => {
  try {
    await api.delete(`/api/v1/vod/mp4-channels/${row.id}`)
    ElMessage.success(t('vodPage.deleted'))
    await loadList()
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(detail || t('vodPage.deleteFailed'))
  }
}

onMounted(loadList)
</script>
