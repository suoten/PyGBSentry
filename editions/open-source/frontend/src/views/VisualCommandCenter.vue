<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="可视化指挥" description="报警联动、轨迹追踪与快速处置入口" />
      </template>
      <TableCard>
        <template #header>
          <div class="w-full flex items-center justify-between gap-2">
            <div class="font-medium">联动总览</div>
            <div class="flex gap-2">
              <el-button size="small" @click="exportAlarmsCsv" :disabled="!alarms.length">导出当前报警</el-button>
              <el-button size="small" @click="reload" :loading="loading">刷新</el-button>
            </div>
          </div>
        </template>
        <div class="space-y-3">
          <el-alert v-if="errorText" type="error" :closable="false" show-icon :title="errorText">
            <template #default>
              <el-button size="small" text type="primary" @click="reload">重试</el-button>
            </template>
          </el-alert>
          <el-alert
            v-if="configMessage"
            type="info"
            :closable="false"
            show-icon
            :title="configMessage"
          />
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">轨迹点上限</div>
              <div class="text-lg font-semibold">{{ commandConfig.trajectory_max_points }}</div>
            </div>
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">闪烁秒数</div>
              <div class="text-lg font-semibold">{{ commandConfig.alarm_blink_seconds }}</div>
            </div>
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">待处理报警</div>
              <div class="text-lg font-semibold">{{ alarmsTotal }}</div>
            </div>
            <div class="rounded-lg p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
              <div class="text-xs" style="color: var(--el-text-color-secondary)">状态</div>
              <div class="text-lg font-semibold">{{ commandConfig.enabled ? '已启用' : '未启用' }}</div>
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <el-button type="primary" @click="router.push('/map')">打开电子地图</el-button>
            <el-button @click="router.push('/mobile-command')">移动指挥</el-button>
            <el-button @click="router.push('/alarms')">告警中心</el-button>
          </div>
        </div>
      </TableCard>
      <TableCard>
        <template #header><div class="font-medium">最近报警快速处置</div></template>
        <el-table :data="alarms" v-loading="loading" stripe>
          <el-table-column prop="time" :label="t('common.time')" width="180" />
          <el-table-column prop="device_id" label="设备" width="180" />
          <el-table-column prop="channel_id" label="通道" width="180" />
          <el-table-column prop="description" :label="t('common.description')" min-width="220" show-overflow-tooltip />
          <el-table-column :label="t('common.action')" width="260" fixed="right">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-1">
                <el-button size="small" type="primary" @click="focusOnMap(row)">地图定位</el-button>
                <el-button size="small" @click="openVisualCommand(row)">指挥追踪</el-button>
                <el-button size="small" type="success" @click="ackAlarm(row)" :loading="ackingId===row.id">确认</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && !errorText && alarms.length === 0" class="py-8 text-center text-sm" style="color: var(--el-text-color-secondary)">
          当前无待处理报警，可稍后刷新查看。
        </div>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getFriendlyError } from '../utils/errorMessage'
import { useI18n } from 'vue-i18n' // FIXED: 国际化

const { t } = useI18n() // FIXED: 国际化

const router = useRouter()
const loading = ref(false)
const errorText = ref('')
const configMessage = ref('')
const alarmsTotal = ref(0)
const alarms = ref<Array<{ id: string; device_id: string; channel_id: string; description: string; time: string }>>([])
const ackingId = ref('')
const commandConfig = ref({
  enabled: true,
  alarm_blink_seconds: 5,
  trajectory_max_points: 50
})

const reload = async () => {
  loading.value = true
  errorText.value = ''
  try {
    const [cfg, alarmRes] = await Promise.all([
      api.get('/api/v1/map/command-config'),
      api.get('/api/v1/alarms', { params: { limit: 20, skip: 0, escalation_state: 'open' } })
    ])
    commandConfig.value = {
      enabled: Boolean(cfg.data?.enabled ?? true),
      alarm_blink_seconds: Number(cfg.data?.alarm_blink_seconds ?? 5),
      trajectory_max_points: Number(cfg.data?.trajectory_max_points ?? 50)
    }
    configMessage.value = String(cfg.data?.message || '')
    alarms.value = Array.isArray(alarmRes.data?.items) ? alarmRes.data.items : []
    alarmsTotal.value = Number(alarmRes.data?.total || alarms.value.length || 0)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    errorText.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message
    ElMessage.error(errorText.value)
  } finally {
    loading.value = false
  }
}

const exportAlarmsCsv = () => {
  const header = ['id', 'time', 'device_id', 'channel_id', 'description']
  const rows = alarms.value.map((row) => [row.id, row.time, row.device_id, row.channel_id, row.description])
  const escapeCsv = (val: string) => {
    const text = String(val ?? '')
    if (text.includes('"') || text.includes(',') || text.includes('\n')) return `"${text.replace(/"/g, '""')}"`
    return text
  }
  const csv = [header.join(','), ...rows.map((r) => r.map((x) => escapeCsv(String(x))).join(','))].join('\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `visual-command-alarms-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

const focusOnMap = (row: { device_id: string; channel_id: string }) => {
  router.push({
    path: '/map',
    query: { device_id: row.device_id || '', channel_id: row.channel_id || '' }
  })
}

const openVisualCommand = (row: { device_id: string; channel_id: string }) => {
  router.push({
    path: '/visual-command',
    query: { device_id: row.device_id || '', channel_id: row.channel_id || '' }
  })
}

const ackAlarm = async (row: { id: string }) => {
  ackingId.value = row.id
  try {
    await api.post(`/api/v1/alarms/${row.id}/ack`)
    ElMessage.success('已确认')
    await reload()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    ackingId.value = ''
  }
}

onMounted(reload)
</script>
