<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader title="接口密钥" description="用于第三方系统或脚本调用平台接口（密钥仅展示一次）">
          <template #actions>
            <el-button type="primary" @click="openCreateDialog">
              <el-icon class="mr-1"><Key /></el-icon>
              创建接口密钥
            </el-button>
            <el-button @click="loadKeys" :loading="loading">刷新</el-button>
          </template>
        </PageHeader>
      </template>

      <TableCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">密钥列表</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ keys.length }} 条</div>
          </div>
        </template>

        <TableSkeleton v-if="loading && keys.length === 0" :rows="6" />
        <el-table v-else :data="paginatedKeys" border size="small" v-loading="loading" :empty-text="'暂无接口密钥'">
          <template #empty>
            <EmptyStateWithAction description="暂无接口密钥。建议为每个系统集成单独创建，便于审计与回收。">
              <template #action>
                <el-button type="primary" @click="openCreateDialog">创建接口密钥</el-button>
              </template>
            </EmptyStateWithAction>
          </template>

          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="key_prefix" label="前缀" width="110">
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.key_prefix }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '可用' : '已撤销' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="权限范围" min-width="220">
            <template #default="{ row }">
              <div v-if="Array.isArray(row.scopes) && row.scopes.length" class="flex flex-wrap gap-1">
                <el-tag v-for="s in row.scopes" :key="s" size="small" effect="plain">{{ s }}</el-tag>
              </div>
              <span v-else style="color: var(--el-text-color-secondary)">全量</span>
            </template>
          </el-table-column>
          <el-table-column prop="last_used_at" label="最近使用" width="190" />
          <el-table-column prop="created_at" label="创建时间" width="190" />
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button v-if="row.is_active" size="small" type="danger" plain :loading="revoking === row.id" @click="revoke(row.id)">撤销</el-button>
              <el-button v-else size="small" disabled>已撤销</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4 pagination-wrapper" v-if="keys.length > 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="keys.length"
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[10, 20, 50, 100]"
            prev-text="上一页"
            next-text="下一页"
            size="small"
          />
        </div>
      </TableCard>

      <AppDialog v-model="createVisible" title="创建接口密钥" size="medium" :icon="Key" icon-color="primary">
        <el-form label-width="90px">
          <el-form-item label="名称" required>
            <el-input v-model="createForm.name" placeholder="例如：监控平台A / 工单系统 / 脚本巡检" />
          </el-form-item>
          <el-form-item label="权限范围">
            <el-input v-model="createScopesText" placeholder="逗号分隔，如 devices:read,stream:play" />
            <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
              留空表示全量权限（与当前账号一致）。建议按最小权限配置，后续可扩展更细粒度控制。
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" @click="createKey" :loading="creating">创建</el-button>
        </template>
      </AppDialog>

      <AppDialog v-model="secretVisible" title="接口密钥（仅展示一次）" size="medium" icon-color="warning">
        <el-alert type="warning" show-icon :closable="false" title="请立即保存该密钥，关闭后将无法再次查看明文。" />
        <div class="mt-3">
          <el-input v-model="createdSecret" readonly />
          <div class="mt-2 flex gap-2">
            <el-button type="primary" @click="copySecret">
              <el-icon class="mr-1"><DocumentCopy /></el-icon>
              复制
            </el-button>
            <el-button @click="secretVisible = false">关闭</el-button>
          </div>
          <div class="text-xs mt-3" style="color: var(--el-text-color-secondary)">
            请求头：X-API-Key: {{ createdSecret }}
          </div>
        </div>
      </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Key, DocumentCopy } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyStateWithAction from '../components/EmptyStateWithAction.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { getFriendlyError } from '../utils/errorMessage'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const loading = ref(false)
const keys = ref<ApiKey[]>([])

const page = ref(1)
const pageSize = ref(10)
const paginatedKeys = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return keys.value.slice(start, end)
})

const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ name: '' })
const createScopesText = ref('')

const secretVisible = ref(false)
const createdSecret = ref('')
const revoking = ref('')

const normalizeScopes = (text: string) => {
  const raw = String(text || '').split(',')
  const out: string[] = []
  raw.forEach((s) => {
    const v = String(s || '').trim()
    if (v) out.push(v)
  })
  return out
}

const loadKeys = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/user-api-keys/me')
    keys.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    keys.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  createForm.value = { name: '' }
  createScopesText.value = ''
  createVisible.value = true
}

const createKey = async () => {
  const name = String(createForm.value.name || '').trim()
  if (!name) {
    ElMessage.warning('请输入名称')
    return
  }
  creating.value = true
  try {
    const scopes = normalizeScopes(createScopesText.value)
    const res = await api.post('/api/v1/user-api-keys', { name, scopes })
    createdSecret.value = String(res.data?.api_key || '')
    createVisible.value = false
    secretVisible.value = true
    await loadKeys()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    creating.value = false
  }
}

const revoke = async (id: string) => {
  try {
    await ElMessageBox.confirm('确认撤销该接口密钥？撤销后将无法继续调用接口。', '提示', { type: 'warning' })
  } catch {
    return
  }
  revoking.value = id
  try {
    await api.post(`/api/v1/user-api-keys/${id}/revoke`)
    ElMessage.success('已撤销')
    await loadKeys()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    revoking.value = ''
  }
}

const copySecret = async () => {
  const v = String(createdSecret.value || '')
  if (!v) return
  try {
    await navigator.clipboard.writeText(v)
    ElMessage.success('已复制')
  } catch {
    await ElMessageBox.alert(v, '接口密钥', { confirmButtonText: '确定' })
  }
}

onMounted(() => {
  loadKeys()
})
</script>
