<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="告警通知记录" description="短信 / 企微 / 飞书等第三方告警发送结果">
          <template #actions>
            <el-button type="primary" :loading="loading" @click="reload">刷新</el-button>
          </template>
        </PageHeader>
      </template>

      <QueryFormSection title="筛选" :default-collapsed="true">
        <el-form-item label="渠道">
          <el-select v-model="channel" placeholder="全部渠道" clearable style="width: 160px">
            <el-option label="全部渠道" :value="''" />
            <el-option label="短信" value="sms" />
            <el-option label="企业微信" value="wecom" />
            <el-option label="飞书" value="feishu" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="status" placeholder="全部状态" clearable style="width: 140px">
            <el-option label="全部状态" :value="''" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="fail" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="reload" :loading="loading" type="primary">应用</el-button>
        </el-form-item>
      </QueryFormSection>

      <el-alert
        v-if="latestNotificationPending"
        type="info"
        show-icon
        :closable="false"
        class="mt-4"
        title="正在等待最新测试结果"
      >
        <template #default>
          <div>已触发测试，系统正在自动刷新通知记录并尝试定位这次最新结果。</div>
        </template>
      </el-alert>

      <el-alert
        v-else-if="latestNotificationFeedback"
        :type="latestNotificationFeedback.type"
        show-icon
        class="mt-4"
        :title="latestNotificationFeedback.title"
        @close="clearLatestNotificationFeedback()"
      >
        <template #default>
          <div>{{ latestNotificationFeedback.message }}</div>
          <div
            v-if="latestNotificationFeedback.notificationId"
            class="mt-3 flex flex-wrap gap-3"
          >
            <el-button
              size="small"
              type="primary"
              @click="focusNotificationRow(latestNotificationFeedback.notificationId)"
            >
              查看最新结果
            </el-button>
            <el-button
              v-if="latestNotificationFeedback.type === 'warning'"
              size="small"
              type="warning"
              plain
              @click="focusLatestTroubleshooting()"
            >
              继续排查
            </el-button>
          </div>
        </template>
      </el-alert>

      <TableCard class="mt-4">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">列表</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">共 {{ total }} 条</div>
          </div>
        </template>
      <el-table
        class="alarm-notifications-table"
        :data="items"
        v-loading="loading"
        stripe
        :row-class-name="getNotificationRowClassName"
        @row-click="selectNotification"
      >
        <el-table-column prop="sent_at" label="发送时间" width="180" />
        <el-table-column prop="channel" label="渠道" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.channel === 'sms'" size="small">短信</el-tag>
            <el-tag v-else-if="row.channel === 'wecom'" type="success" size="small">企业微信</el-tag>
            <el-tag v-else-if="row.channel === 'feishu'" type="warning" size="small">飞书</el-tag>
            <span v-else class="text-xs" style="color: var(--el-text-color-secondary)">{{ row.channel }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="device_id" label="设备" width="160" />
        <el-table-column prop="channel_id" label="通道" width="160" />
        <el-table-column prop="description" label="描述" />
        <el-table-column prop="error_message" label="错误信息" width="220" show-overflow-tooltip />
      </el-table>
      <div class="flex justify-end mt-4">
        <el-pagination
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50, 100]"
          prev-text="上一页"
          next-text="下一页"
          size="small"
          :page-size="pageSize"
          :current-page="page"
          :total="total"
          @current-change="handlePageChange"
          @size-change="() => { page = 1; fetchNotifications() }"
        />
      </div>
      </TableCard>

      <TableCard v-if="selectedNotification" class="mt-4">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="font-medium">记录详情</div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">
              点击列表行可切换详情
            </div>
          </div>
        </template>
        <div class="grid gap-3 md:grid-cols-2">
          <div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">发送时间</div>
            <div>{{ selectedNotification.sent_at || '-' }}</div>
          </div>
          <div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">渠道</div>
            <div>{{ getChannelLabel(selectedNotification.channel) }}</div>
          </div>
          <div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">状态</div>
            <div>{{ selectedNotification.status === 'success' ? '成功' : '失败' }}</div>
          </div>
          <div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">告警 ID</div>
            <div>{{ selectedNotification.alarm_id || '-' }}</div>
          </div>
          <div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">设备 ID</div>
            <div>{{ selectedNotification.device_id || '-' }}</div>
          </div>
          <div>
            <div class="text-xs" style="color: var(--el-text-color-secondary)">通道 ID</div>
            <div>{{ selectedNotification.channel_id || '-' }}</div>
          </div>
        </div>
        <div class="mt-4">
          <div class="text-xs" style="color: var(--el-text-color-secondary)">描述</div>
          <div class="mt-1 whitespace-pre-wrap break-all">{{ selectedNotification.description || '-' }}</div>
        </div>
        <div class="mt-4">
          <div class="text-xs" style="color: var(--el-text-color-secondary)">错误信息</div>
          <div class="mt-1 whitespace-pre-wrap break-all">{{ selectedNotification.error_message || '无' }}</div>
        </div>
        <el-alert
          v-if="shouldShowLatestSuccessAlert(selectedNotification)"
          type="success"
          show-icon
          :closable="false"
          class="mt-4"
          title="本次重试已成功"
        >
          <template #default>
            <div>系统已定位到这次最新成功记录，当前渠道测试已通过，可继续核对发送时间和接收端结果。</div>
          </template>
        </el-alert>
        <el-alert
          v-if="selectedTroubleshooting"
          type="warning"
          show-icon
          data-notification-troubleshooting-panel="selected"
          :closable="false"
          :class="[
            'mt-4',
            {
              'notification-troubleshooting--spotlight': isSelectedNotificationLatestRetriedFailure,
              'notification-troubleshooting--muted': shouldMuteSelectedTroubleshooting
            }
          ]"
          :title="selectedTroubleshooting.title"
        >
          <template #default>
            <div
              v-if="shouldMuteSelectedTroubleshooting"
              class="mb-3 rounded border border-solid px-3 py-2 text-xs"
              style="border-color: var(--el-border-color-light); color: var(--el-text-color-secondary); background: var(--el-fill-color-lighter)"
            >
              当前渠道最近一次重试已成功，下方内容是历史失败记录的排查建议，仅供回溯参考。
            </div>
            <div class="whitespace-pre-wrap break-all">
              {{ selectedTroubleshooting.summary }}
            </div>
            <ul
              v-if="selectedTroubleshooting.steps.length"
              class="mt-3 list-disc pl-5 text-sm leading-6"
            >
              <li
                v-for="step in selectedTroubleshooting.steps"
                :key="step"
              >
                {{ step }}
              </li>
            </ul>
            <div
              v-if="selectedTroubleshooting.basedOn"
              class="mt-2 text-xs"
              style="color: var(--el-text-color-secondary)"
            >
              识别依据：{{ selectedTroubleshooting.basedOn }}
            </div>
            <div class="mt-3 flex flex-wrap gap-3">
              <el-button
                v-if="selectedTroubleshooting.pluginId"
                size="small"
                type="primary"
                :class="{ 'troubleshooting-action--focus': focusedTroubleshootingActionKey === 'plugin-runtime' }"
                data-troubleshooting-action-key="plugin-runtime"
                @click="openPluginRuntime(selectedTroubleshooting.pluginId)"
              >
                前往对应插件运行页
              </el-button>
              <el-button
                v-for="fieldKey in selectedTroubleshooting.fieldKeys || []"
                :key="fieldKey"
                size="small"
                :class="{ 'troubleshooting-action--focus': focusedTroubleshootingActionKey === `field:${fieldKey}` }"
                :data-troubleshooting-action-key="`field:${fieldKey}`"
                @click="openPluginRuntimeField(selectedTroubleshooting.pluginId, fieldKey)"
              >
                定位{{ getNotificationFieldLabel(selectedNotification.channel, fieldKey) }}
              </el-button>
              <el-button
                v-if="selectedTroubleshooting.pluginId"
                size="small"
                type="primary"
                plain
                :loading="retryTestLoading"
                :class="{ 'troubleshooting-action--focus': focusedTroubleshootingActionKey === 'retry-test' }"
                data-troubleshooting-action-key="retry-test"
                @click="triggerAlertChannelTest(selectedNotification)"
              >
                重新发送测试
              </el-button>
              <el-button
                v-if="selectedTroubleshooting.showConfigCenter"
                size="small"
                :class="{ 'troubleshooting-action--focus': focusedTroubleshootingActionKey === 'config-center' }"
                data-troubleshooting-action-key="config-center"
                @click="router.push('/config-center')"
              >
                打开配置中心
              </el-button>
            </div>
          </template>
        </el-alert>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { getFriendlyError } from '../utils/errorMessage'
import {
  getNotificationFieldLabel,
  getNotificationChannelLabel,
  getNotificationPluginIdByChannel,
  getNotificationTroubleshooting as resolveNotificationTroubleshooting,
  type NotificationTroubleshooting
} from '../utils/notificationTroubleshooting'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import QueryFormSection from '../components/QueryFormSection.vue'

interface NotificationItem {
  id: string
  tenant_id: string
  alarm_id?: string
  device_id?: string
  channel_id?: string
  channel: string
  status: string
  error_message?: string
  description?: string
  sent_at: string
}

interface LatestNotificationFeedback {
  type: 'success' | 'warning' | 'info'
  title: string
  message: string
  notificationId?: string
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const items = ref<NotificationItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const channel = ref<string | ''>('')
const status = ref<string | ''>('')
const timeRange = ref<[string, string] | null>(null)
const focusedNotificationId = ref('')
const selectedNotification = ref<NotificationItem | null>(null)
const retryTestLoading = ref(false)
const latestNotificationPending = ref(false)
const latestNotificationFeedback = ref<LatestNotificationFeedback | null>(null)
const focusedTroubleshootingActionKey = ref('')
let focusedNotificationTimer: ReturnType<typeof setTimeout> | null = null
let focusedTroubleshootingActionTimer: ReturnType<typeof setTimeout> | null = null
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const clearFocusedNotification = () => {
  if (focusedNotificationTimer) {
    clearTimeout(focusedNotificationTimer)
    focusedNotificationTimer = null
  }
  focusedNotificationId.value = ''
}

const clearFocusedTroubleshootingAction = () => {
  if (focusedTroubleshootingActionTimer) {
    clearTimeout(focusedTroubleshootingActionTimer)
    focusedTroubleshootingActionTimer = null
  }
  focusedTroubleshootingActionKey.value = ''
}

const getNotificationRowClassName = ({ row }: { row: NotificationItem }) => {
  return row.id === focusedNotificationId.value ? 'alarm-notifications-row--focus' : ''
}

const getChannelLabel = getNotificationChannelLabel

const getPluginIdByChannel = getNotificationPluginIdByChannel

const clearLatestNotificationFeedback = () => {
  latestNotificationFeedback.value = null
}

const selectedTroubleshooting = computed(() => {
  const row = selectedNotification.value
  if (!row || row.status === 'success') return null
  return getNotificationTroubleshooting(row)
})

const isSelectedNotificationLatestRetriedFailure = computed(() => {
  const row = selectedNotification.value
  return (
    !!row &&
    row.status !== 'success' &&
    latestNotificationFeedback.value?.type === 'warning' &&
    latestNotificationFeedback.value?.notificationId === row.id
  )
})

const shouldMuteSelectedTroubleshooting = computed(() => {
  const row = selectedNotification.value
  return (
    !!row &&
    row.status !== 'success' &&
    latestNotificationFeedback.value?.type === 'success' &&
    Boolean(latestNotificationFeedback.value?.notificationId)
  )
})

const shouldShowLatestSuccessAlert = (row?: NotificationItem | null) => {
  return (
    !!row &&
    row.status === 'success' &&
    latestNotificationFeedback.value?.type === 'success' &&
    latestNotificationFeedback.value?.notificationId === row.id
  )
}

const openPluginRuntime = (pluginId?: string) => {
  const target = String(pluginId || '').trim()
  if (!target) return
  router.push(`/plugins/runtime/${target}`)
}

const openPluginRuntimeField = (pluginId?: string, fieldKey?: string) => {
  const targetPluginId = String(pluginId || '').trim()
  const targetFieldKey = String(fieldKey || '').trim()
  if (!targetPluginId || !targetFieldKey) return
  router.push({
    path: `/plugins/runtime/${targetPluginId}`,
    query: {
      focus_field: targetFieldKey
    }
  })
}

const triggerAlertChannelTest = async (row?: NotificationItem | null) => {
  const targetPluginId = String(getPluginIdByChannel(row?.channel) || '').trim()
  const targetChannel = String(row?.channel || '').trim()
  if (!targetPluginId || !targetChannel) return
  retryTestLoading.value = true
  latestNotificationPending.value = true
  clearLatestNotificationFeedback()
  try {
    const expectedAfter = Date.now()
    const res = await api.post('/api/v1/plugins/alert-test', { channel: targetPluginId })
    ElMessage.success(res.data?.message || '测试告警已触发，可稍后查看最新通知记录。')
    await router.replace({
      path: route.path,
      query: {
        ...route.query,
        channel: targetChannel,
        focus_latest: '1',
        baseline_id: String(row?.id || ''),
        expected_after: String(expectedAfter)
      }
    })
  } catch (error: unknown) {
    latestNotificationPending.value = false
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    retryTestLoading.value = false
  }
}

const getNotificationTroubleshooting = (row: NotificationItem): NotificationTroubleshooting => {
  return resolveNotificationTroubleshooting({
    channel: row.channel,
    errorMessage: row.error_message
  })
}

const getFirstTroubleshootingActionKey = (row?: NotificationItem | null) => {
  if (!row || row.status === 'success') return ''
  const troubleshooting = getNotificationTroubleshooting(row)
  const firstFieldKey = troubleshooting.fieldKeys?.[0]
  if (firstFieldKey) return `field:${firstFieldKey}`
  if (troubleshooting.pluginId) return 'plugin-runtime'
  if (troubleshooting.showConfigCenter) return 'config-center'
  if (troubleshooting.pluginId) return 'retry-test'
  return ''
}

const scrollSelectedTroubleshootingIntoView = async () => {
  await nextTick()
  const panel = document.querySelector(
    '[data-notification-troubleshooting-panel="selected"]'
  ) as HTMLElement | null
  panel?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const focusTroubleshootingAction = async (row?: NotificationItem | null) => {
  const actionKey = getFirstTroubleshootingActionKey(row)
  if (!actionKey) return
  await scrollSelectedTroubleshootingIntoView()
  clearFocusedTroubleshootingAction()
  focusedTroubleshootingActionKey.value = actionKey
  const actionElement = document.querySelector(
    `[data-troubleshooting-action-key="${actionKey}"]`
  ) as HTMLElement | null
  actionElement?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  actionElement?.focus()
  focusedTroubleshootingActionTimer = setTimeout(() => {
    focusedTroubleshootingActionKey.value = ''
    focusedTroubleshootingActionTimer = null
  }, 4200)
}

const selectNotification = (row?: NotificationItem | null) => {
  selectedNotification.value = row || null
}

const focusNotificationRow = async (notificationId?: string) => {
  const targetId = String(notificationId || '').trim()
  if (!targetId) return
  focusedNotificationId.value = targetId
  const targetRow = items.value.find((item) => item.id === targetId)
  if (targetRow) {
    selectNotification(targetRow)
  }
  await nextTick()
  const row = document.querySelector('.alarm-notifications-table .alarm-notifications-row--focus') as HTMLElement | null
  row?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  if (focusedNotificationTimer) clearTimeout(focusedNotificationTimer)
  focusedNotificationTimer = setTimeout(() => {
    focusedNotificationId.value = ''
    focusedNotificationTimer = null
  }, 4500)
}

const focusLatestTroubleshooting = async () => {
  const notificationId = String(latestNotificationFeedback.value?.notificationId || '').trim()
  if (!notificationId) return
  await focusNotificationRow(notificationId)
  const targetRow = items.value.find((item) => item.id === notificationId) || selectedNotification.value
  await focusTroubleshootingAction(targetRow)
}

const matchesExpectedNotification = (
  row: NotificationItem | null | undefined,
  expectedAfter: number,
  baselineId: string
) => {
  if (!row) return false
  if (baselineId && row.id !== baselineId) return true
  if (expectedAfter > 0) {
    const sentAt = Date.parse(String(row.sent_at || ''))
    if (!Number.isNaN(sentAt) && sentAt >= expectedAfter - 1000) return true
  }
  return !baselineId && expectedAfter <= 0
}

const waitForLatestNotification = async (options?: {
  baselineId?: string
  expectedAfter?: number
  maxAttempts?: number
  intervalMs?: number
}) => {
  const baselineId = String(options?.baselineId || '').trim()
  const expectedAfter = Number(options?.expectedAfter || 0)
  const maxAttempts = Math.max(1, Number(options?.maxAttempts || 1))
  const intervalMs = Math.max(200, Number(options?.intervalMs || 1000))

  let latest: NotificationItem | null = null
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await fetchNotifications({ silentError: attempt < maxAttempts - 1 })
    latest = items.value[0] || null
    if (matchesExpectedNotification(latest, expectedAfter, baselineId)) {
      return { latest, matched: true, attempts: attempt + 1 }
    }
    if (attempt < maxAttempts - 1) {
      await sleep(intervalMs)
    }
  }
  return { latest, matched: false, attempts: maxAttempts }
}

const consumeRouteFocusQuery = async () => {
  const queryChannel = String(route.query.channel || '').trim()
  const focusLatest = String(route.query.focus_latest || '').trim() === '1'
  const baselineId = String(route.query.baseline_id || '').trim()
  const expectedAfter = Number(route.query.expected_after || 0)
  let shouldFetch = false
  if (queryChannel && channel.value !== queryChannel) {
    channel.value = queryChannel
    shouldFetch = true
  }
  if (!focusLatest) {
    if (shouldFetch) await fetchNotifications()
    return
  }

  page.value = 1
  latestNotificationPending.value = true
  const result = await waitForLatestNotification({
    baselineId,
    expectedAfter,
    maxAttempts: baselineId || expectedAfter > 0 ? 5 : 1,
    intervalMs: 1000
  })
  latestNotificationPending.value = false
  if (result.latest) {
    await focusNotificationRow(result.latest.id)
    const nextQuery = { ...route.query }
    delete nextQuery.focus_latest
    delete nextQuery.baseline_id
    delete nextQuery.expected_after
    router.replace({ path: route.path, query: nextQuery })
    if (result.matched && (baselineId || expectedAfter > 0)) {
      if (result.latest.status === 'success') {
        latestNotificationFeedback.value = {
          type: 'success',
          title: '本次重试已成功',
          message: '系统已自动刷新并定位到最新成功记录，可以继续核对发送时间和渠道结果。',
          notificationId: result.latest.id
        }
        clearFocusedTroubleshootingAction()
        ElMessage.success('已自动刷新并定位到最新通知结果。')
      } else {
        latestNotificationFeedback.value = {
          type: 'warning',
          title: '本次重试仍失败',
          message: '系统已定位到最新失败记录，请结合下方错误信息和排查建议继续处理。',
          notificationId: result.latest.id
        }
        await focusTroubleshootingAction(result.latest)
        ElMessage.warning('已自动刷新到最新失败记录，请按下方建议继续排查。')
      }
    } else if ((baselineId || expectedAfter > 0) && !result.matched) {
      latestNotificationFeedback.value = {
        type: 'info',
        title: '暂未等到最新测试结果',
        message: '测试已触发，但在当前等待窗口内尚未看到新的通知记录，可稍后手动刷新重试。'
      }
      ElMessage.info('测试已触发，但暂未等到新的通知记录，请稍后手动刷新。')
    } else {
      clearLatestNotificationFeedback()
    }
  } else {
    latestNotificationPending.value = false
    latestNotificationFeedback.value = {
      type: 'info',
      title: '暂未获取到通知记录',
      message: '已按当前渠道筛选告警通知记录；若暂未出现测试记录，可能仍在投递或尚未写入，请稍后刷新重试。'
    }
    ElMessage.info('已按当前渠道筛选告警通知记录；若暂未出现测试记录，可能仍在投递或尚未写入，请稍后刷新重试。')
  }
}

const fetchNotifications = async (options?: { silentError?: boolean }) => {
  loading.value = true
  try {
    const params: Record<string, string | number> = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (channel.value) params.channel = channel.value
    if (status.value) params.status = status.value
    if (timeRange.value && timeRange.value.length === 2) {
      params.start_time = timeRange.value[0]
      params.end_time = timeRange.value[1]
    }
    const res = await api.get('/api/v1/alarms/notifications', { params })
    items.value = Array.isArray(res.data?.items) ? res.data.items : []
    total.value = Number(res.data?.total || 0)
    if (!items.value.length) {
      selectedNotification.value = null
    } else if (focusedNotificationId.value) {
      selectedNotification.value = items.value.find((item) => item.id === focusedNotificationId.value) || items.value[0]
    } else if (selectedNotification.value) {
      selectedNotification.value = items.value.find((item) => item.id === selectedNotification.value?.id) || items.value[0]
    } else {
      selectedNotification.value = items.value[0]
    }
  } catch (e: unknown) {
    if (!options?.silentError) {
      const friendly = getFriendlyError(e)
      ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    }
    items.value = []
    total.value = 0
    selectedNotification.value = null
  } finally {
    loading.value = false
  }
}

const reload = () => {
  page.value = 1
  fetchNotifications()
}

const handlePageChange = (p: number) => {
  page.value = p
  fetchNotifications()
}

onMounted(() => {
  void consumeRouteFocusQuery().then(() => {
    if (String(route.query.focus_latest || '').trim() !== '1') {
      void fetchNotifications()
    }
  })
})

onUnmounted(() => {
  clearFocusedNotification()
  clearFocusedTroubleshootingAction()
})

watch(
  () => route.fullPath,
  () => {
    if (route.path === '/alarm-notifications') {
      void consumeRouteFocusQuery()
    }
  }
)
</script>

<style scoped>
:deep(.alarm-notifications-row--focus) {
  --el-table-tr-bg-color: #ecf5ff;
}

:deep(.alarm-notifications-row--focus td) {
  transition: background-color 0.3s ease;
}

:deep(.notification-troubleshooting--spotlight) {
  border-color: var(--el-color-warning);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-warning) 36%, transparent);
}

:deep(.notification-troubleshooting--muted) {
  opacity: 0.72;
}

:deep(.notification-troubleshooting--muted .el-alert__title) {
  color: var(--el-text-color-secondary);
}

:deep(.notification-troubleshooting--muted .el-button) {
  opacity: 0.88;
}

:deep(.troubleshooting-action--focus) {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--el-color-primary) 24%, transparent);
}
</style>

