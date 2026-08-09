<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('mapProvider.title')" :description="t('mapProvider.description')" />
      </template>
      <TableCard v-loading="loading">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">{{ t('mapProvider.profileList') }}</div>
            <el-button type="primary" size="small" @click="openCreate">{{ t('mapProvider.createProfile') }}</el-button>
          </div>
        </template>
        <el-table :data="paginatedItems" style="width: 100%">
          <el-table-column prop="name" :label="t('mapProvider.colName')" min-width="140" />
          <el-table-column prop="provider" :label="t('mapProvider.colProvider')" width="140">
            <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
          </el-table-column>
          <el-table-column :label="t('mapProvider.colApiKey')" width="120" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.api_key ? 'success' : 'info'">{{ row.api_key ? t('mapProvider.configured') : t('mapProvider.notConfigured') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('mapProvider.colDefault')" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" size="small" type="primary">{{ t('mapProvider.defaultTag') }}</el-tag>
              <el-button v-else link type="primary" size="small" @click="setDefault(row)">{{ t('mapProvider.setDefault') }}</el-button>
            </template>
          </el-table-column>
          <el-table-column :label="t('mapProvider.colCenterZoom')" min-width="210">
            <template #default="{ row }">
              <span class="text-xs text-slate-500">{{ Number(row.center_lng).toFixed(6) }}, {{ Number(row.center_lat).toFixed(6) }} / {{ row.zoom_level }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('mapProvider.colActions')" width="220" align="center">
            <template #default="{ row }">
              <div class="flex items-center justify-center gap-2">
                <el-button size="small" @click="openEdit(row)">{{ t('mapProvider.edit') }}</el-button>
                <el-button size="small" type="danger" plain :disabled="!canDeleteProfile(row)" @click="removeProfile(row)">{{ t('mapProvider.delete') }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="items.length > 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="items.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            :prev-text="t('mapProvider.prevPage')"
            :next-text="t('mapProvider.nextPage')"
            size="small"
          />
        </div>
      </TableCard>
    </PageContainer>

    <AppDialog v-model="dialogVisible" :title="editingId ? t('mapProvider.editProfile') : t('mapProvider.createProfile')" size="medium">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="120px">
        <el-form-item :label="t('mapProvider.fieldName')" prop="name">
          <el-input v-model="form.name" :placeholder="t('mapProvider.fieldNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('mapProvider.colProvider')" prop="provider">
          <el-select v-model="form.provider" class="w-full">
            <el-option :label="t('mapProvider.providerTianditu')" value="tianditu" />
            <el-option label="OpenStreetMap" value="osm" />
            <el-option :label="t('mapProvider.providerGaode')" value="gaode" />
            <el-option :label="t('mapProvider.providerVector')" value="vector" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password :placeholder="t('settings.fillByProvider')" />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item v-if="form.provider === 'vector'" :label="t('mapProvider.fieldVectorUrl')" prop="vector_tile_url">
          <el-input v-model="form.vector_tile_url" placeholder="http://server/{z}/{x}/{y}.pbf" />
        </el-form-item>
        <el-form-item :label="t('mapProvider.fieldCenterLng')">
          <el-input-number v-model="form.center_lng" :min="-180" :max="180" :precision="6" class="w-full" />
        </el-form-item>
        <el-form-item :label="t('mapProvider.fieldCenterLat')">
          <el-input-number v-model="form.center_lat" :min="-90" :max="90" :precision="6" class="w-full" />
        </el-form-item>
        <el-form-item :label="t('mapProvider.fieldZoomLevel')" prop="zoom_level">
          <el-input-number v-model="form.zoom_level" :min="1" :max="20" class="w-full" />
        </el-form-item>
        <el-form-item :label="t('mapProvider.fieldMinMaxZoom')" prop="max_zoom">
          <div class="flex items-center gap-2 w-full">
            <el-input-number v-model="form.min_zoom" :min="0" :max="20" class="w-full" />
            <el-input-number v-model="form.max_zoom" :min="0" :max="22" class="w-full" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">{{ t('common.save') }}</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, computed } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { getApiErrorMessage } from '../utils/errorMessage'
import { useI18n } from 'vue-i18n'  // FIXED: P3 i18n

const { t } = useI18n()  // FIXED: P3 i18n

type MapProfile = {
  id: string
  name: string
  provider: string
  api_key: string
  vector_tile_url?: string
  center_lng: number
  center_lat: number
  zoom_level: number
  min_zoom: number
  max_zoom: number
  is_default: boolean
}

const loading = ref(false)
const saving = ref(false)
const items = ref<MapProfile[]>([])

const page = ref(1)
const pageSize = ref(10)
const paginatedItems = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return items.value.slice(start, end)
})

const dialogVisible = ref(false)
const editingId = ref('')
const formRef = ref<FormInstance>()
const form = reactive({
  name: '',
  provider: 'tianditu',
  api_key: '',
  vector_tile_url: '',
  center_lng: 116.404,
  center_lat: 39.915,
  zoom_level: 12,
  min_zoom: 1,
  max_zoom: 20
})
const formRules = computed<FormRules>(() => ({
  name: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('mapProvider.ruleNameRequired')))
        if (text.length > 64) return callback(new Error(t('mapProvider.ruleNameTooLong')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  provider: [
    {
      validator: (_rule, value, callback) => {
        const p = String(value || '').trim()
        if (!p) return callback(new Error(t('mapProvider.ruleProviderRequired')))
        callback()
      },
      trigger: 'change'
    }
  ],
  vector_tile_url: [
    {
      validator: (_rule, value, callback) => {
        if (form.provider !== 'vector') return callback()
        const text = String(value || '').trim()
        if (!text) return callback(new Error(t('mapProvider.ruleVectorUrlRequired')))
        callback()
      },
      trigger: 'blur'
    }
  ],
  zoom_level: [
    {
      validator: (_rule, value, callback) => {
        const n = Number(value)
        if (!Number.isFinite(n)) return callback(new Error(t('mapProvider.ruleZoomRequired')))
        if (n < 1 || n > 20) return callback(new Error(t('mapProvider.ruleZoomRange')))
        callback()
      },
      trigger: 'change'
    }
  ],
  max_zoom: [
    {
      validator: (_rule, _value, callback) => {
        if (Number(form.min_zoom) > Number(form.max_zoom)) return callback(new Error(t('mapProvider.ruleMinMaxZoom')))
        callback()
      },
      trigger: 'change'
    }
  ]
}))

const providerLabel = (provider: string) => {
  const p = String(provider || '').toLowerCase()
  if (p === 'tianditu') return t('mapProvider.providerTiandituShort')
  if (p === 'gaode') return t('mapProvider.providerGaodeShort')
  if (p === 'osm') return 'OSM'
  if (p === 'vector') return 'MVT'
  return p || '-'
}

const resetForm = () => {
  form.name = ''
  form.provider = 'tianditu'
  form.api_key = ''
  form.vector_tile_url = ''
  form.center_lng = 116.404
  form.center_lat = 39.915
  form.zoom_level = 12
  form.min_zoom = 1
  form.max_zoom = 20
}

const loadItems = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/map/providers')
    items.value = Array.isArray(res?.data?.items) ? res.data.items : []
  } catch (e: unknown) {
    items.value = []
    const msg = getApiErrorMessage(e, t('mapProvider.loadFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('mapProvider.loadFailed'))
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = ''
  resetForm()
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}

const openEdit = (row: MapProfile) => {
  editingId.value = String(row.id || '')
  form.name = row.name || ''
  form.provider = row.provider || 'tianditu'
  form.api_key = row.api_key || ''
  form.vector_tile_url = row.vector_tile_url || ''
  form.center_lng = Number(row.center_lng || 116.404)
  form.center_lat = Number(row.center_lat || 39.915)
  form.zoom_level = Number(row.zoom_level || 12)
  form.min_zoom = Number(row.min_zoom || 1)
  form.max_zoom = Number(row.max_zoom || 20)
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}

const submitForm = async () => {
  const validated = await formRef.value?.validate().catch(() => false)
  if (!validated) return
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/v1/map/providers/${editingId.value}`, { ...form })
    } else {
      await api.post('/api/v1/map/providers', { ...form })
    }
    dialogVisible.value = false
    await loadItems()
    ElMessage.success(t('common.saveSuccess'))
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('common.saveFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('common.saveFailed'))
  } finally {
    saving.value = false
  }
}

const canDeleteProfile = (row: MapProfile) => {
  if (!row) return false
  if (row.is_default) return false
  return items.value.length > 1
}

const setDefault = async (row: MapProfile) => {
  try {
    await api.post(`/api/v1/map/providers/${row.id}/activate`)
    await loadItems()
    ElMessage.success(t('mapProvider.defaultUpdated'))
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, t('mapProvider.setFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('mapProvider.setFailed'))
  }
}

const removeProfile = async (row: MapProfile) => {
  if (!canDeleteProfile(row)) {
    ElMessage.warning(t('mapProvider.cannotDeleteDefault'))
    return
  }
  try {
    await ElMessageBox.confirm(t('mapProvider.confirmDelete', { name: row.name }), t('common.tip'), {
      type: 'warning',
      confirmButtonText: t('common.delete'),
      cancelButtonText: t('common.cancel')
    })
    await api.delete(`/api/v1/map/providers/${row.id}`)
    await loadItems()
    ElMessage.success(t('common.deleteSuccess'))
  } catch (e: unknown) {
    if (e === 'cancel' || e === 'close') return
    const msg = getApiErrorMessage(e, t('common.deleteFailed'))
    ElMessage.error(typeof msg === 'string' ? msg : t('common.deleteFailed'))
  }
}

onMounted(async () => {
  await loadItems()
})
</script>
