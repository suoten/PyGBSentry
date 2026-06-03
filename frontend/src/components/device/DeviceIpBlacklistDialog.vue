<template>
  <AppDialog
    v-model="visible"
    title="IP 黑名单管理"
    size="large"
  >
    <div class="ip-blacklist-container">
      <el-table :data="data" v-loading="loading" style="width: 100%" :scrollbar-always-on="true">
        <el-table-column prop="ip" label="IP 地址" min-width="180" show-overflow-tooltip />
        <el-table-column prop="reason" label="拉黑原因" min-width="200" show-overflow-tooltip />
        <el-table-column prop="created_at" label="拉黑时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="scope">
            <el-button link size="small" class="remove-btn" @click="handleRemove(scope.row.ip)">
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { ElMessageBox } from 'element-plus'
import AppDialog from '../common/AppDialog.vue'
import { getFriendlyError } from '../../utils/errorMessage'
import { formatDateTime } from '../../utils/time'
import type { Device } from '@/types/models'

interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'removed'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

import { computed } from 'vue'

const loading = ref(false)
const data = ref<string[]>([])

watch(() => props.modelValue, async (val) => {
  if (val) {
    await fetchData()
  }
})

const fetchData = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/blacklist')
    data.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.message)
  } finally {
    loading.value = false
  }
}

const handleRemove = async (ip: string) => {
  try {
    await ElMessageBox.confirm(`确定要移除 IP ${ip} 的黑名单限制吗？`, '确认移除', { type: 'warning' })
    await api.delete(`/api/v1/blacklist/${ip}`)
    ElMessage.success('移除成功')
    fetchData()
    emit('removed')
  } catch (e: unknown) {
    if (e !== 'cancel') {
      const friendly = getFriendlyError(e)
      ElMessage.error(friendly.message)
    }
  }
}
</script>

<style scoped>
.ip-blacklist-container {
  max-height: 50vh;
  overflow-y: auto;
}

.ip-blacklist-container :deep(.el-table) {
  font-size: 13px;
}

.ip-blacklist-container :deep(.el-table__cell) {
  padding: 10px 8px;
}

.ip-blacklist-container :deep(.remove-btn) {
  color: #ef4444;
  font-weight: 600;
  font-size: 13px;
}

.ip-blacklist-container :deep(.remove-btn:hover) {
  color: #dc2626;
  text-decoration: underline;
}
</style>
