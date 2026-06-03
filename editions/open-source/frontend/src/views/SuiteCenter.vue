<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="title" description="能力运营中心（移动端入口、安装状态、兼容性与依赖检查）" />
      </template>
      <TableCard>
        <template #header>
          <div class="w-full flex items-center justify-between gap-2">
            <div class="font-medium">能力矩阵</div>
            <el-button size="small" @click="reload" :loading="loading">刷新</el-button>
          </div>
        </template>
        <div class="space-y-3">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">总能力数</div>
              <div class="text-xl font-semibold">{{ matrixRows.length }}</div>
            </div>
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">可直接使用</div>
              <div class="text-xl font-semibold">{{ usableCount }}</div>
            </div>
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">仅购买未安装</div>
              <div class="text-xl font-semibold">{{ purchasedOnlyCount }}</div>
            </div>
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">兼容性提醒</div>
              <div class="text-xl font-semibold">{{ compatibilityWarnings.length }}</div>
            </div>
          </div>
          <el-alert
            v-if="errorText"
            type="error"
            :closable="false"
            show-icon
            :title="errorText"
          >
            <template #default>
              <el-button size="small" type="primary" text @click="reload">重试</el-button>
            </template>
          </el-alert>
          <el-alert
            v-else
            type="info"
            :closable="false"
            show-icon
            :title="`可用移动入口 ${items.length} 个，能力项 ${matrixRows.length} 个`"
            description="自动汇聚插件声明的 mobile/miniprogram 入口，并展示购买、安装、依赖与兼容性状态。"
          />
          <div class="flex flex-wrap items-center gap-2">
            <el-select v-model="platformFilter" clearable placeholder="平台筛选" style="width: 150px">
              <el-option label="移动端" value="mobile" />
              <el-option label="小程序" value="miniprogram" />
            </el-select>
            <el-select v-model="statusFilter" clearable placeholder="状态筛选" style="width: 170px">
              <el-option label="可用" value="usable" />
              <el-option label="待安装" value="need_install" />
              <el-option label="待购买" value="need_purchase" />
            </el-select>
            <el-input v-model="keyword" clearable placeholder="按能力名/插件ID搜索" style="width: 280px" />
          </div>
          <el-table :data="pagedRows" v-loading="loading" stripe>
            <el-table-column prop="name" label="能力名称" min-width="180" />
            <el-table-column prop="plugin_id" label="插件ID" min-width="180" />
            <el-table-column prop="platforms" label="平台" width="140">
              <template #default="{ row }">
                <el-space wrap>
                  <el-tag v-for="p in row.platforms" :key="p" size="small" :type="p === 'mobile' ? 'success' : 'warning'">
                    {{ p === 'mobile' ? '移动端' : '小程序' }}
                  </el-tag>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.status')">
              <template #default="{ row }">
                <el-tag size="small" :type="row.statusTag">{{ row.statusText }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="dependencyText" label="依赖检查" min-width="220" show-overflow-tooltip />
            <el-table-column prop="compatibilityText" label="兼容性" min-width="220" show-overflow-tooltip />
            <el-table-column :label="t('common.action')">
              <template #default="{ row }">
                <div class="flex flex-wrap gap-1">
                  <el-button size="small" type="primary" :disabled="!row.canOpen" @click="openBestEntry(row)">打开入口</el-button>
                  <el-button size="small" :disabled="!row.installed" @click="openRuntime(row)">运行页</el-button>
                  <el-button size="small" @click="goPluginDetail(row.plugin_id)">插件详情</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="filteredRows.length"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            class="mt-3"
          />
          <div v-if="!loading && !errorText && filteredRows.length === 0" class="py-8 text-center text-sm" style="color: var(--el-text-color-secondary)">
            当前条件下没有匹配能力项，可调整筛选后重试。
          </div>
        </div>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getFriendlyError } from '../utils/errorMessage'
import { useI18n } from 'vue-i18n' // FIXED: 国际化

const { t } = useI18n() // FIXED: 国际化

const route = useRoute()
const router = useRouter()
const title = computed(() => {
  const t = (route.meta as Record<string, unknown> | undefined)?.title
  if (typeof t === 'string' && t) return t
  return '移动能力中心'
})

const loading = ref(false)
const errorText = ref('')
const platformFilter = ref<'' | 'mobile' | 'miniprogram'>('')
const statusFilter = ref<'' | 'usable' | 'need_install' | 'need_purchase'>('')
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const items = ref<Array<{
  plugin_id: string
  name: string
  platform: 'mobile' | 'miniprogram'
  entry_type: string
  entry_url?: string
  entry_url_template?: string
}>>([])
const purchasedIds = ref<string[]>([])
const installedIds = ref<string[]>([])
const pluginMeta = ref<Record<string, { min_oss_version?: string; version?: string }>>({})
const ossVersion = ref('1.0.0')

const parseVer = (v: string) => String(v || '')
  .trim()
  .replace(/^[^0-9]*/, '')
  .split('.')
  .map((x) => {
    const n = Number.parseInt(String(x).replace(/[^0-9].*$/, ''), 10)
    return Number.isFinite(n) ? n : 0
  })
const gteVer = (a: string, b: string) => {
  const av = parseVer(a)
  const bv = parseVer(b)
  const len = Math.max(av.length, bv.length)
  for (let i = 0; i < len; i += 1) {
    const ai = av[i] || 0
    const bi = bv[i] || 0
    if (ai > bi) return true
    if (ai < bi) return false
  }
  return true
}

const matrixRows = computed(() => {
  const grouped = new Map<string, {
    plugin_id: string
    name: string
    platforms: Array<'mobile' | 'miniprogram'>
    entries: typeof items.value
  }>()
  for (const item of items.value) {
    const key = String(item.plugin_id || '')
    if (!key) continue
    const current = grouped.get(key)
    if (!current) {
      grouped.set(key, {
        plugin_id: key,
        name: item.name || key,
        platforms: [item.platform],
        entries: [item]
      })
    } else {
      current.entries.push(item)
      if (!current.platforms.includes(item.platform)) current.platforms.push(item.platform)
    }
  }
  return Array.from(grouped.values()).sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN')).map((row) => {
    const purchased = purchasedIds.value.includes(row.plugin_id)
    const installed = installedIds.value.includes(row.plugin_id)
    const canOpen = row.entries.some((entry) => !!resolveEntryUrl(entry))
    const required = pluginMeta.value[row.plugin_id]?.min_oss_version || ''
    const compatible = required ? gteVer(ossVersion.value, required) : true
    let statusText = '待购买'
    let statusTag: 'success' | 'warning' | 'danger' = 'danger'
    if (purchased && installed) {
      statusText = canOpen ? '可用' : '已安装未配置入口'
      statusTag = canOpen ? 'success' : 'warning'
    } else if (purchased && !installed) {
      statusText = '已购买待安装'
      statusTag = 'warning'
    }
    const dependencyText = purchased
      ? installed ? '购买与安装均满足' : '已购买，待安装插件'
      : '未购买，需先在插件中心购买'
    const compatibilityText = compatible
      ? (required ? `兼容（要求 ≥ ${required}）` : '无版本门槛')
      : `当前版本 ${ossVersion.value}，要求 ≥ ${required}`
    return {
      ...row,
      purchased,
      installed,
      canOpen,
      compatible,
      statusText,
      statusTag,
      dependencyText,
      compatibilityText
    }
  })
})

const filteredRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return matrixRows.value.filter((row) => {
    if (platformFilter.value && !row.platforms.includes(platformFilter.value)) return false
    if (statusFilter.value === 'usable' && !(row.purchased && row.installed && row.canOpen)) return false
    if (statusFilter.value === 'need_install' && !(row.purchased && !row.installed)) return false
    if (statusFilter.value === 'need_purchase' && row.purchased) return false
    if (kw) {
      const a = String(row.name || '').toLowerCase()
      const b = String(row.plugin_id || '').toLowerCase()
      if (!a.includes(kw) && !b.includes(kw)) return false
    }
    return true
  })
})

const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

const usableCount = computed(() => matrixRows.value.filter((x) => x.purchased && x.installed && x.canOpen).length)
const purchasedOnlyCount = computed(() => matrixRows.value.filter((x) => x.purchased && !x.installed).length)
const compatibilityWarnings = computed(() => matrixRows.value.filter((x) => !x.compatible))

const reload = async () => {
  loading.value = true
  errorText.value = ''
  try {
    const [entriesRes, purchasedRes, menusRes, marketRes, versionRes] = await Promise.all([
      api.get('/api/v1/plugins/mobile-entries'),
      api.get('/api/v1/plugins/purchased'),
      api.get('/api/v1/plugins/menus'),
      api.get('/api/v1/plugins/marketplace'),
      api.get('/api/v1/system-config/info')
    ])
    items.value = Array.isArray(entriesRes.data?.items) ? entriesRes.data.items : []
    purchasedIds.value = Array.isArray(purchasedRes.data?.plugin_ids) ? purchasedRes.data.plugin_ids.map((x: unknown) => String(x)) : []
    installedIds.value = Array.isArray(menusRes.data) ? menusRes.data.map((x: { plugin_id?: string }) => String(x?.plugin_id || '')).filter(Boolean) : []
    const rows = Array.isArray(marketRes.data) ? marketRes.data : []
    const map: Record<string, { min_oss_version?: string; version?: string }> = {}
    for (const row of rows) {
      const id = String(row?.id || '')
      if (!id) continue
      map[id] = {
        min_oss_version: String(row?.min_oss_version || ''),
        version: String(row?.version || '')
      }
    }
    pluginMeta.value = map
    ossVersion.value = String(versionRes.data?.version || '1.0.0')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    errorText.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message
    ElMessage.error(errorText.value)
  } finally {
    loading.value = false
  }
}

const resolveEntryUrl = (row: {
  entry_url?: string
  entry_url_template?: string
  plugin_id: string
  platform: string
}) => {
  if (row.entry_url) return row.entry_url
  if (row.entry_url_template) {
    return row.entry_url_template
      .replace('{plugin_id}', encodeURIComponent(row.plugin_id))
      .replace('{platform}', encodeURIComponent(row.platform))
  }
  return ''
}

const openEntry = (row: {
  entry_url?: string
  entry_url_template?: string
  plugin_id: string
  platform: string
}) => {
  const url = resolveEntryUrl(row)
  if (!url) {
    ElMessage.warning('该能力未声明可打开入口')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

const openRuntime = (row: { plugin_id: string }) => {
  router.push(`/plugins/runtime/${encodeURIComponent(row.plugin_id)}`)
}

const openBestEntry = (row: {
  entries: Array<{
    entry_url?: string
    entry_url_template?: string
    plugin_id: string
    platform: string
  }>
}) => {
  const target = row.entries.find((entry) => !!resolveEntryUrl(entry))
  if (!target) {
    ElMessage.warning('该能力未配置可打开入口')
    return
  }
  openEntry(target)
}

const goPluginDetail = (pluginId: string) => {
  if (!pluginId) return
  router.push(`/plugins/detail/${encodeURIComponent(pluginId)}`)
}

onMounted(reload)
</script>
