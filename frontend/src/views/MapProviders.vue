<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="地图配置" description="统一维护地图 API Key 与多地图方案，电子地图页可随时切换。" />
      </template>
      <TableCard v-loading="loading">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">地图方案列表</div>
            <el-button type="primary" size="small" @click="openCreate">新建地图方案</el-button>
          </div>
        </template>
        <el-table :data="paginatedItems" style="width: 100%">
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="provider" label="底图服务商" width="140">
            <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
          </el-table-column>
          <el-table-column label="API Key" width="120" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.api_key ? 'success' : 'info'">{{ row.api_key ? '已配置' : '未配置' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="默认" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" size="small" type="primary">默认</el-tag>
              <el-button v-else link type="primary" size="small" @click="setDefault(row)">设为默认</el-button>
            </template>
          </el-table-column>
          <el-table-column label="中心点/缩放" min-width="210">
            <template #default="{ row }">
              <span class="text-xs text-slate-500">{{ Number(row.center_lng).toFixed(6) }}, {{ Number(row.center_lat).toFixed(6) }} / {{ row.zoom_level }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" align="center">
            <template #default="{ row }">
              <div class="flex items-center justify-center gap-2">
                <el-button size="small" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" plain :disabled="!canDeleteProfile(row)" @click="removeProfile(row)">删除</el-button>
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
            prev-text="上一页"
            next-text="下一页"
            size="small"
          />
        </div>
      </TableCard>
    </PageContainer>

    <AppDialog v-model="dialogVisible" :title="editingId ? '编辑地图方案' : '新建地图方案'" size="medium">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="120px">
        <el-form-item label="方案名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：园区地图 / 城市大盘" />
        </el-form-item>
        <el-form-item label="底图服务商" prop="provider">
          <el-select v-model="form.provider" class="w-full">
            <el-option label="天地图 (TianDiTu)" value="tianditu" />
            <el-option label="OpenStreetMap" value="osm" />
            <el-option label="高德地图 (Gaode)" value="gaode" />
            <el-option label="自定义矢量瓦片 (MVT)" value="vector" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password :placeholder="t('settings.fillByProvider')" />  <!-- FIXED: P3 i18n -->
        </el-form-item>
        <el-form-item v-if="form.provider === 'vector'" label="MVT 地址" prop="vector_tile_url">
          <el-input v-model="form.vector_tile_url" placeholder="http://server/{z}/{x}/{y}.pbf" />
        </el-form-item>
        <el-form-item label="中心经度">
          <el-input-number v-model="form.center_lng" :min="-180" :max="180" :precision="6" class="w-full" />
        </el-form-item>
        <el-form-item label="中心纬度">
          <el-input-number v-model="form.center_lat" :min="-90" :max="90" :precision="6" class="w-full" />
        </el-form-item>
        <el-form-item label="缩放级别" prop="zoom_level">
          <el-input-number v-model="form.zoom_level" :min="1" :max="20" class="w-full" />
        </el-form-item>
        <el-form-item label="最小/最大缩放" prop="max_zoom">
          <div class="flex items-center gap-2 w-full">
            <el-input-number v-model="form.min_zoom" :min="0" :max="20" class="w-full" />
            <el-input-number v-model="form.max_zoom" :min="0" :max="22" class="w-full" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
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
const formRules: FormRules = {
  name: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '').trim()
        if (!text) return callback(new Error('请填写方案名称'))
        if (text.length > 64) return callback(new Error('方案名称不能超过64个字符'))
        callback()
      },
      trigger: 'blur'
    }
  ],
  provider: [
    {
      validator: (_rule, value, callback) => {
        const p = String(value || '').trim()
        if (!p) return callback(new Error('请选择底图服务商'))
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
        if (!text) return callback(new Error('请填写 MVT 地址'))
        callback()
      },
      trigger: 'blur'
    }
  ],
  zoom_level: [
    {
      validator: (_rule, value, callback) => {
        const n = Number(value)
        if (!Number.isFinite(n)) return callback(new Error('请填写缩放级别'))
        if (n < 1 || n > 20) return callback(new Error('缩放级别范围为1-20'))
        callback()
      },
      trigger: 'change'
    }
  ],
  max_zoom: [
    {
      validator: (_rule, _value, callback) => {
        if (Number(form.min_zoom) > Number(form.max_zoom)) return callback(new Error('最小缩放不能大于最大缩放'))
        callback()
      },
      trigger: 'change'
    }
  ]
}

const providerLabel = (provider: string) => {
  const p = String(provider || '').toLowerCase()
  if (p === 'tianditu') return '天地图'
  if (p === 'gaode') return '高德'
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
    const msg = getApiErrorMessage(e, '地图服务商加载失败')
    ElMessage.error(typeof msg === 'string' ? msg : '地图服务商加载失败')
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
    ElMessage.success('保存成功')
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, '保存失败')
    ElMessage.error(typeof msg === 'string' ? msg : '保存失败')
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
    ElMessage.success('默认地图已更新')
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, '设置失败')
    ElMessage.error(typeof msg === 'string' ? msg : '设置失败')
  }
}

const removeProfile = async (row: MapProfile) => {
  if (!canDeleteProfile(row)) {
    ElMessage.warning('默认地图方案不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除地图方案「${row.name}」？`, '提示', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    await api.delete(`/api/v1/map/providers/${row.id}`)
    await loadItems()
    ElMessage.success('删除成功')
  } catch (e: unknown) {
    if (e === 'cancel' || e === 'close') return
    const msg = getApiErrorMessage(e, '删除失败')
    ElMessage.error(typeof msg === 'string' ? msg : '删除失败')
  }
}

onMounted(async () => {
  await loadItems()
})
</script>
