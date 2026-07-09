<template>
  <div class="app-page space-y-4">
    <el-alert
      v-if="!canQueryAudit"
      :title="t('audit.noPermission')"
      type="warning"
      :closable="false"
      show-icon
    />
    <PageContainer>
      <template #header>
        <PageHeader :title="t('audit.title')" :description="t('audit.currentPage', { page })" />
      </template>

    <QueryFormSection :title="t('audit.queryConditions')" :default-collapsed="true">
      <el-form-item v-for="field in filterFields" :key="field.key" :label="t(field.label)">
        <el-input
          v-if="field.component === 'input'"
          :model-value="query[field.key]"
          :placeholder="field.placeholder ? t(field.placeholder) : undefined"
          :disabled="!canQueryAudit"
          @update:model-value="(v: string) => setField(field.key, v)"
        />
        <el-select
          v-else-if="field.component === 'select'"
          :model-value="query[field.key]"
          clearable
          style="width: 100%"
          :disabled="!canQueryAudit"
          @update:model-value="(v: string) => setField(field.key, v)"
        >
          <el-option v-for="option in field.options || []" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-date-picker
          v-else
          :model-value="query[field.key]"
          type="datetimerange"
          :range-separator="t('audit.dateRangeSeparator')"
          :start-placeholder="t('audit.startTimePlaceholder')"
          :end-placeholder="t('audit.endTimePlaceholder')"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 100%"
          :disabled="!canQueryAudit"
          @update:model-value="(v: string[] | null) => setField(field.key, v)"
        />
      </el-form-item>
      <el-form-item>
        <ActionButtons
          :primary-text="t('audit.executeQuery')"
          :secondary-text="t('audit.executeReset')"
          :primary-loading="loading"
          :primary-disabled="!canQueryAudit"
          :secondary-disabled="!canQueryAudit"
          @primary="search"
          @secondary="resetForm"
        />
      </el-form-item>
    </QueryFormSection>

    <TableCard v-loading="loading">
      <template #header>
        <div class="flex justify-between items-center flex-wrap gap-2">
          <div>
            <div class="font-medium">{{ t('audit.auditLogs') }}</div>
            <div class="text-xs mt-1" style="color: var(--el-text-color-secondary)">{{ t('audit.totalCount', { total }) }}</div>
            <div class="mt-2 flex items-center gap-2 flex-wrap" v-if="quickStats.length > 0">
              <el-tag
                v-for="s in quickStats"
                :key="s.key"
                size="small"
                :type="s.type"
                :effect="isQuickStatActive(s) ? 'dark' : 'plain'"
                style="cursor: pointer"
                @click="applyQuickStatFilter(s)"
              >
                {{ s.label }}
              </el-tag>
          </div>
            <div class="mt-2 flex items-center gap-2 flex-wrap" v-if="upgradeFailureBuckets.length > 0">
              <span class="text-xs" style="color: var(--el-text-color-secondary)">
                {{ t('audit.upgradeFailureProfile', { window: upgradeProfileWindowLabel }) }}
              </span>
              <el-tooltip :content="upgradeWindowToggleHint" placement="top">
                <el-tag
                  :type="upgradeWindowTagType"
                  size="small"
                  effect="dark"
                  style="cursor: pointer"
                  @click="toggleRecommendedOnCallWindow"
                >
                  {{ t('audit.statisticsWindow', { window: upgradeProfileWindowLabel }) }}
                </el-tag>
              </el-tooltip>
              <span v-if="upgradeWindowRangeHint" class="text-xs" style="color: var(--el-text-color-secondary)">
                {{ upgradeWindowRangeHint }}
              </span>
              <el-button
                size="small"
                text
                :disabled="!canQueryAudit"
                @click="resetUpgradeProfileFilters"
              >
                {{ t('audit.resetProfileFilter') }}
              </el-button>
              <el-dropdown
                split-button
                trigger="click"
                size="small"
                :disabled="!canQueryAudit"
                @click="copySummaryWithLastFormat"
                @command="handleCopySummaryCommand"
              >
                {{ t('audit.copySummary', { format: copyFormatLabel }) }}
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item :disabled="lastCopyFormat === 'plain'" command="plain">{{ t('audit.copyTroubleshootSummary') }}</el-dropdown-item>
                    <el-dropdown-item :disabled="lastCopyFormat === 'markdown'" command="markdown">{{ t('audit.copyMarkdownSummary') }}</el-dropdown-item>
                    <el-dropdown-item :disabled="lastCopyFormat === 'codeblock'" command="codeblock">{{ t('audit.copyMarkdownCodeblock') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button
                size="small"
                :type="activeTimeWindow === '15m' ? 'primary' : 'default'"
                :plain="activeTimeWindow !== '15m'"
                text
                :disabled="!canQueryAudit"
                @click="applyTimeWindowMinutes(15)"
              >
                15m
              </el-button>
              <el-button
                size="small"
                :type="activeTimeWindow === '1h' ? 'primary' : 'default'"
                :plain="activeTimeWindow !== '1h'"
                text
                :disabled="!canQueryAudit"
                @click="applyTimeWindowMinutes(60)"
              >
                1h
              </el-button>
              <el-button
                size="small"
                :type="activeTimeWindow === '24h' ? 'primary' : 'default'"
                :plain="activeTimeWindow !== '24h'"
                text
                :disabled="!canQueryAudit"
                @click="applyTimeWindowMinutes(1440)"
              >
                24h
              </el-button>
              <el-button
                size="small"
                :type="activeTimeWindow === 'all' ? 'primary' : 'default'"
                :plain="activeTimeWindow !== 'all'"
                text
                :disabled="!canQueryAudit"
                @click="clearTimeWindow"
              >
                {{ t('audit.timeWindowAll') }}
              </el-button>
              <el-tag
                v-for="b in upgradeFailureBuckets"
                :key="b.key"
                size="small"
                :type="b.type"
                :effect="upgradeFailurePreset === b.key ? 'dark' : 'plain'"
                style="cursor: pointer"
                @click="toggleUpgradeFailurePreset(b.key as '401' | '402' | '403' | '409' | '5xx')"
              >
                {{ b.label }}
              </el-tag>
            </div>
            <div class="mt-2 flex items-center gap-2 flex-wrap" v-if="activeFilterTags.length > 0">
              <el-tag
                v-for="tag in activeFilterTags"
                :key="tag.key"
                size="small"
                closable
                @close="clearFilterTag(tag.key)"
              >
                {{ tag.label }}
              </el-tag>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <el-button
              size="small"
              :type="lifecycleMode === 'install' ? 'primary' : 'default'"
              :plain="lifecycleMode !== 'install'"
              :disabled="!canQueryAudit"
              @click="toggleLifecycleMode('install')"
            >
              {{ lifecycleMode === 'install' ? t('audit.installOnlyOn') : t('audit.installOnlyOff') }}
            </el-button>
            <el-button
              size="small"
              :type="lifecycleMode === 'upgrade' ? 'warning' : 'default'"
              :plain="lifecycleMode !== 'upgrade'"
              :disabled="!canQueryAudit"
              @click="toggleLifecycleMode('upgrade')"
            >
              {{ lifecycleMode === 'upgrade' ? t('audit.upgradeChainOn') : t('audit.upgradeChainOff') }}
            </el-button>
            <el-button
              size="small"
              :type="lifecycleMode === 'uninstall' ? 'danger' : 'default'"
              :plain="lifecycleMode !== 'uninstall'"
              :disabled="!canQueryAudit"
              @click="toggleLifecycleMode('uninstall')"
            >
              {{ lifecycleMode === 'uninstall' ? t('audit.uninstallOnlyOn') : t('audit.uninstallOnlyOff') }}
            </el-button>
            <el-button
              size="small"
              :type="lifecycleMode === 'lifecycle' ? 'success' : 'default'"
              :plain="lifecycleMode !== 'lifecycle'"
              :disabled="!canQueryAudit"
              @click="toggleLifecycleMode('lifecycle')"
            >
              {{ lifecycleMode === 'lifecycle' ? t('audit.lifecycleAllOn') : t('audit.lifecycleAllOff') }}
            </el-button>
            <el-button
              size="small"
              :type="trajectoryPrioritySort ? 'primary' : 'default'"
              :plain="!trajectoryPrioritySort"
              :disabled="!canQueryAudit"
              @click="toggleTrajectoryPrioritySort"
            >
              {{ trajectoryPrioritySort ? t('audit.trajectoryPriorityOn') : t('audit.trajectoryPriorityOff') }}
            </el-button>
            <el-button
              size="small"
              :type="groupByPlugin ? 'success' : 'default'"
              :plain="!groupByPlugin"
              :disabled="!canQueryAudit"
              @click="toggleGroupByPlugin"
            >
              {{ groupByPlugin ? t('audit.groupByPluginOn') : t('audit.groupByPluginOff') }}
            </el-button>
            <el-button
              size="small"
              :type="groupByFailurePriority ? 'danger' : 'default'"
              :plain="!groupByFailurePriority"
              :disabled="!canQueryAudit || !groupByPlugin"
              @click="toggleGroupByFailurePriority"
            >
              {{ groupByFailurePriority ? t('audit.failurePriorityOn') : t('audit.failurePriorityOff') }}
            </el-button>
            <el-button
              size="small"
              :type="onlyFailedGroups ? 'warning' : 'default'"
              :plain="!onlyFailedGroups"
              :disabled="!canQueryAudit || !groupByPlugin"
              @click="toggleOnlyFailedGroups"
            >
              {{ onlyFailedGroups ? t('audit.onlyFailedGroupsOn') : t('audit.onlyFailedGroupsOff') }}
            </el-button>
            <el-button
              size="small"
              text
              :disabled="!canQueryAudit || !groupByPlugin || failedGroupCount <= 0"
              @click="toggleTopFailedGroupsOnly"
            >
              {{ topFailedGroupsOnly ? t('audit.topFailedGroupsOn', { limit: topFailedGroupLimit }) : t('audit.topFailedGroupsOff', { limit: topFailedGroupLimit }) }}
            </el-button>
            <el-select
              v-if="groupByPlugin"
              :model-value="topFailedGroupLimit"
              size="small"
              style="width: 90px"
              :disabled="!canQueryAudit"
              @update:model-value="onTopFailedLimitChange"
            >
              <el-option :value="3" label="Top 3" />
              <el-option :value="5" label="Top 5" />
              <el-option :value="10" label="Top 10" />
            </el-select>
            <el-button
              size="small"
              text
              :disabled="!canQueryAudit || !groupByPlugin"
              @click="expandAllPluginGroups"
            >
              {{ t('audit.expandAll') }}
            </el-button>
            <el-button
              size="small"
              text
              :disabled="!canQueryAudit || !groupByPlugin"
              @click="collapseAllPluginGroups"
            >
              {{ t('audit.collapseAll') }}
            </el-button>
            <el-button
              size="small"
              :type="upgradeFailurePreset === '401' ? 'warning' : 'default'"
              :plain="upgradeFailurePreset !== '401'"
              :disabled="!canQueryAudit"
              @click="toggleUpgradeFailurePreset('401')"
            >
              {{ t('audit.upgrade401') }}
            </el-button>
            <el-button
              size="small"
              :type="upgradeFailurePreset === '402' ? 'warning' : 'default'"
              :plain="upgradeFailurePreset !== '402'"
              :disabled="!canQueryAudit"
              @click="toggleUpgradeFailurePreset('402')"
            >
              {{ t('audit.upgrade402') }}
            </el-button>
            <el-button
              size="small"
              :type="upgradeFailurePreset === '403' ? 'warning' : 'default'"
              :plain="upgradeFailurePreset !== '403'"
              :disabled="!canQueryAudit"
              @click="toggleUpgradeFailurePreset('403')"
            >
              {{ t('audit.upgrade403') }}
            </el-button>
            <el-button
              size="small"
              :type="upgradeFailurePreset === '409' ? 'warning' : 'default'"
              :plain="upgradeFailurePreset !== '409'"
              :disabled="!canQueryAudit"
              @click="toggleUpgradeFailurePreset('409')"
            >
              {{ t('audit.upgrade409') }}
            </el-button>
            <el-button
              size="small"
              :type="upgradeFailurePreset === '5xx' ? 'danger' : 'default'"
              :plain="upgradeFailurePreset !== '5xx'"
              :disabled="!canQueryAudit"
              @click="toggleUpgradeFailurePreset('5xx')"
            >
              {{ t('audit.upgrade5xx') }}
            </el-button>
          <el-button
            type="primary"
            plain
            size="small"
            :disabled="!canQueryAudit"
            :loading="exportLoading"
            @click="handleExport"
          >
            {{ t('audit.exportCsv') }}
          </el-button>
            <el-tooltip :content="autoRefreshButtonHint" placement="top">
              <el-button
                size="small"
                :type="autoRefreshEnabled ? 'success' : 'default'"
                :plain="!autoRefreshEnabled"
                :disabled="!canQueryAudit"
                @click="toggleAutoRefresh"
              >
                {{ autoRefreshButtonLabel }}
              </el-button>
            </el-tooltip>
            <el-select
              :model-value="autoRefreshSeconds"
              size="small"
              style="width: 86px"
              :disabled="!canQueryAudit"
              @update:model-value="onAutoRefreshSecondsChange"
            >
              <el-option :value="10" label="10s" />
              <el-option :value="30" label="30s" />
            </el-select>
            <el-button
              v-if="!autoRefreshEnabled && autoRefreshStoppedByError"
              size="small"
              type="warning"
              plain
              :disabled="!canQueryAudit || loading"
              @click="resumeAutoRefresh"
            >
              {{ t('audit.resumeAutoRefresh') }}
            </el-button>
            <el-button
              v-if="autoRefreshErrorStreak > 0 || autoRefreshStoppedByError"
              size="small"
              text
              :disabled="loading"
              @click="clearAutoRefreshErrorState"
            >
              {{ t('audit.clearErrorState') }}
            </el-button>
            <el-tooltip :content="t('audit.resetRefreshStatsHint')" placement="top">
              <el-button size="small" text :disabled="loading" @click="resetRefreshTelemetry">
                {{ t('audit.resetRefreshStats') }}
              </el-button>
            </el-tooltip>
            <el-button size="small" text :disabled="!canQueryAudit || loading" @click="manualRefresh">{{ t('audit.manualRefresh') }}</el-button>
          </div>
          <div class="text-xs mt-1 flex items-center gap-2" style="color: var(--el-text-color-secondary)">
            <span>{{ t('audit.lastRefresh') }}：{{ lastRefreshAt || '-' }}</span>
            <el-tag size="small" :type="lastRefreshResultTagType">{{ t('audit.resultLabel') }}：{{ lastRefreshResultLabel }}</el-tag>
            <span v-if="lastRefreshErrorAt">{{ t('audit.failureTime') }}：{{ lastRefreshErrorAt }}</span>
            <el-tag v-if="lastRefreshErrorAgoLabel" size="small" :type="lastRefreshErrorAgoTagType">
              {{ t('audit.failureAgo') }}：{{ lastRefreshErrorAgoLabel }}
            </el-tag>
            <span>{{ t('audit.winStreak') }}：{{ refreshSuccessStreak }}</span>
            <span>{{ t('audit.loseStreak') }}：{{ refreshFailureStreak }}</span>
            <el-tooltip :content="refreshHealthHint" placement="top">
              <el-tag size="small" :type="refreshHealthType">{{ refreshHealthLabel }}</el-tag>
            </el-tooltip>
            <span>{{ t('audit.refreshDuration') }}：{{ lastRefreshDurationLabel }}</span>
            <span>{{ t('audit.nextRefresh') }}：{{ nextRefreshCountdownLabel }}</span>
            <el-tooltip v-if="autoRefreshEnabled || autoRefreshStoppedByError" :content="autoRefreshStateHint" placement="top">
              <el-tag size="small" :type="autoRefreshStateType">{{ autoRefreshStateLabel }}</el-tag>
            </el-tooltip>
          </div>
          <div v-if="groupByPlugin" class="text-xs mt-1" style="color: var(--el-text-color-secondary)">
            {{ t('audit.groupStats', { total: totalGroupCount, failed: failedGroupCount, visible: visibleGroupCount }) }}
          </div>
        </div>
      </template>
      <el-table :data="displayRows" stripe style="width: 100%" :empty-text="EMPTY_TEXT" :row-class-name="getRowClassName">
        <el-table-column prop="created_at" :label="t('audit.timeCol')" width="200">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('audit.pluginId')" min-width="150">
          <template #default="{ row }">
            <span>{{ row.plugin_id || getSummaryField(row.summary, 'plugin_id') || '-' }}</span>
            <el-tag
              v-if="groupByPlugin && isPluginGroupFirstRow(row)"
              size="small"
              type="info"
              class="ml-2"
            >
              {{ t('audit.groupRowCount', { count: getPluginGroupCount(row.plugin_id || getSummaryField(row.summary, 'plugin_id')), failed: getPluginGroupFailedCount(row.plugin_id || getSummaryField(row.summary, 'plugin_id')) }) }}
            </el-tag>
            <el-button
              v-if="groupByPlugin && getPluginGroupCount(row.plugin_id || getSummaryField(row.summary, 'plugin_id')) > 1"
              size="small"
              text
              @click.stop="togglePluginGroup(row.plugin_id || getSummaryField(row.summary, 'plugin_id'))"
            >
              {{
                isPluginGroupExpanded(row.plugin_id || getSummaryField(row.summary, 'plugin_id'))
                  ? t('audit.collapse')
                  : t('audit.expandCount', { count: getPluginGroupCount(row.plugin_id || getSummaryField(row.summary, 'plugin_id')) })
              }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column :label="t('audit.source')" min-width="140">
          <template #default="{ row }">{{ row.source || getSummaryField(row.summary, 'source') || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('audit.tenant')" min-width="120">
          <template #default="{ row }">{{ row.tenant_id || getSummaryField(row.summary, 'tenant_id') || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('audit.statusCode')" width="110">
          <template #default="{ row }">
            {{
              (row.status_code ?? undefined) ??
                (getSummaryField(row.summary, 'status_code') ? Number(getSummaryField(row.summary, 'status_code')) : undefined) ??
                '-'
            }}
          </template>
        </el-table-column>
        <el-table-column prop="module" :label="t('audit.module')" min-width="180" />
        <el-table-column prop="action" :label="t('audit.actionLabel')" min-width="160" />
        <el-table-column prop="operator" :label="t('audit.operator')" width="120" />
        <el-table-column prop="result" :label="t('audit.resultLabel')" width="110" />
        <el-table-column :label="t('audit.oldVersion')" width="130">
          <template #default="{ row }">{{ getSummaryField(row.summary, 'previous_version') || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('audit.newVersion')" width="130">
          <template #default="{ row }">{{ getSummaryField(row.summary, 'version') || '-' }}</template>
        </el-table-column>
        <el-table-column prop="summary" :label="t('audit.summaryCol')" min-width="320" />
        <el-table-column :label="t('audit.detail')" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDetail(row)">{{ t('audit.view') }}</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="EMPTY_TEXT" />
        </template>
      </el-table>
      <div class="mt-4 flex justify-end">
        <el-pagination
          layout="total, sizes, prev, pager, next, jumper"
          :prev-text="t('audit.prevPage')"
          :next-text="t('audit.nextPage')"
          :page-sizes="[10, 20, 50, 100]"
          :current-page="page"
          :page-size="pageSize"
          size="small"
          :total="total"
          :disabled="!canQueryAudit"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </TableCard>
    <AppDialog v-model="detailDialogVisible" :title="t('audit.auditDetail')" size="large">
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="t('audit.timeCol')">{{ detailRow ? formatDateTime(detailRow.created_at) : '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.statusLabel')">{{ detailRow?.result || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.module')">{{ detailRow?.module || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.actionLabel')">{{ detailRow?.action || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.operator')">{{ detailRow?.operator || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.statusCode')">
          {{
            detailRow
              ? ((detailRow.status_code ?? undefined) ??
                (getSummaryField(detailRow.summary || '', 'status_code') ? Number(getSummaryField(detailRow.summary || '', 'status_code')) : undefined) ??
                '-')
              : '-'
          }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('audit.pluginId')">{{ detailRow?.plugin_id || (detailRow ? getSummaryField(detailRow.summary || '', 'plugin_id') : '') || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.tenant')">{{ detailRow?.tenant_id || (detailRow ? getSummaryField(detailRow.summary || '', 'tenant_id') : '') || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.source')">{{ detailRow?.source || (detailRow ? getSummaryField(detailRow.summary || '', 'source') : '') || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div class="audit-detail-block">
        <div class="audit-detail-title">{{ t('audit.summaryOriginal') }}</div>
        <el-input :model-value="detailRow?.summary || '-'" type="textarea" :rows="4" readonly />
      </div>
      <div class="audit-detail-block">
        <div class="audit-detail-title">{{ t('audit.summaryFields') }}</div>
        <el-table :data="detailSummaryRows" size="small" border>
          <el-table-column prop="key" :label="t('audit.field')" min-width="180" />
          <el-table-column prop="value" :label="t('audit.value')" min-width="260" />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">{{ t('audit.close') }}</el-button>
      </template>
    </AppDialog>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { downloadAuditCsv, getAuditStats, listAuditLogs, type AuditLogItem, type AuditStatsResponse } from '../api/auditCenter'
import { getVerifiedRoleInfo, getCachedRoleInfo, type RoleInfo } from '../utils/auth' // FIX H-8: 改用后端验证角色
import { EMPTY_TEXT, buildErrorMessage, buildSuccessMessage } from '../utils/ui'
import { getApiErrorMessage } from '../utils/errorMessage'
import { formatDateTime } from '../utils/time'
import QueryFormSection from '../components/QueryFormSection.vue'
import ActionButtons from '../components/ActionButtons.vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { auditFilterFields, type AuditFilterFieldKey } from '../configs/center-fields'
import { validateFields } from '../utils/field-validation'

const { t } = useI18n()

const loading = ref(false)
const total = ref(0)
const rows = ref<AuditLogItem[]>([])
const detailDialogVisible = ref(false)
const detailRow = ref<AuditLogItem | null>(null)
const stats = ref<AuditStatsResponse | null>(null)
const upgradeProfileStats = ref<AuditStatsResponse | null>(null)
const page = ref(1)
const pageSize = ref(10)
const lifecycleMode = ref<'' | 'install' | 'upgrade' | 'uninstall' | 'lifecycle'>('')
const trajectoryPrioritySort = ref(false)
const groupByPlugin = ref(false)
const groupByFailurePriority = ref(false)
const onlyFailedGroups = ref(false)
const topFailedGroupsOnly = ref(false)
const topFailedGroupLimit = ref(5)
const expandedPluginGroups = ref<Record<string, boolean>>({})
const quickActionFilter = ref('')
const quickActionPrefixFilter = ref('')
const quickStatusCodeFilter = ref('')
const upgradeFailurePreset = ref<'' | '401' | '402' | '403' | '409' | '5xx'>('')
const autoRefreshEnabled = ref(false)
const autoRefreshSeconds = ref<10 | 30>(30)
const autoRefreshTimer = ref<number | null>(null)
const lastRefreshAt = ref('')
const autoRefreshLastTotal = ref<number | null>(null)
const autoRefreshIdleRounds = ref(0)
const autoRefreshErrorStreak = ref(0)
const autoRefreshLastError = ref('')
const autoRefreshMaxErrorStreak = 5
const autoRefreshStoppedByError = ref(false)
const autoRefreshPausedByHidden = ref(false)
const autoRefreshPausedByOffline = ref(false)
const autoRefreshAdaptiveSlowMode = ref(false)
const lastRefreshDurationMs = ref(0)
const lastRefreshOk = ref<boolean | null>(null)
const lastRefreshErrorAt = ref('')
const refreshSuccessStreak = ref(0)
const refreshFailureStreak = ref(0)
const nextAutoRefreshAtMs = ref(0)
const nowMs = ref(Date.now())
const refreshTicker = ref<number | null>(null)
const lastAutoTriggerAtMs = ref(0)
const autoTriggerMinGapMs = 3000
const searchRequestSeq = ref(0)
const roleInfo = getRoleInfo()
const canQueryAudit = roleInfo.canQueryAudit
const route = useRoute()
const router = useRouter()
// SECURITY: 以下均为非敏感 UI 偏好 — 复制格式（plain/markdown/codeblock）、自动刷新开关与间隔秒数，
// 不含用户身份或鉴权信息，可安全存入 localStorage 跨会话保留。读取见 onMounted/startAutoRefresh，写入见 saveAutoRefreshPrefs/runCopyByFormat。
const COPY_FORMAT_KEY = 'audit.summary.copy.format'
const AUTO_REFRESH_ENABLED_KEY = 'audit.auto_refresh.enabled'
const AUTO_REFRESH_SECONDS_KEY = 'audit.auto_refresh.seconds'

const filterFields = auditFilterFields

const query = reactive({
  module: '',
  operator: '',
  result: '',
  plugin_id: '',
  source: '',
  tenant_id: '',
  date_range: null as string[] | null
})
const lastCopyFormat = ref<'plain' | 'markdown' | 'codeblock'>('plain')

const activeFilterTags = ref<Array<{ key: string; label: string }>>([])
const detailSummaryRows = computed(() => parseSummaryEntries(detailRow.value?.summary || ''))

const saveAutoRefreshPrefs = () => {
  localStorage.setItem(AUTO_REFRESH_ENABLED_KEY, autoRefreshEnabled.value ? '1' : '0')
  localStorage.setItem(AUTO_REFRESH_SECONDS_KEY, String(autoRefreshSeconds.value))
}

const setField = (key: AuditFilterFieldKey, value: string | string[] | null) => {
  ;(query as Record<string, unknown>)[key] = value
}

const refreshActiveFilterTags = () => {
  const tags: Array<{ key: string; label: string }> = []
  if (query.module.trim()) tags.push({ key: 'module', label: t('audit.tagModule', { value: query.module.trim() }) })
  if (query.operator.trim()) tags.push({ key: 'operator', label: t('audit.tagOperator', { value: query.operator.trim() }) })
  if (query.result) tags.push({ key: 'result', label: t('audit.tagResult', { value: query.result }) })
  if (query.plugin_id.trim()) tags.push({ key: 'plugin_id', label: t('audit.tagPlugin', { value: query.plugin_id.trim() }) })
  if (query.source.trim()) tags.push({ key: 'source', label: t('audit.tagSource', { value: query.source.trim() }) })
  if (query.tenant_id.trim()) tags.push({ key: 'tenant_id', label: t('audit.tagTenant', { value: query.tenant_id.trim() }) })
  if (query.date_range?.[0] || query.date_range?.[1]) tags.push({ key: 'date_range', label: t('audit.tagDateRangeSet') })
  if (lifecycleMode.value) {
    const labelMap: Record<string, string> = {
      install: t('audit.tagLifecycleInstall'),
      upgrade: t('audit.tagLifecycleUpgrade'),
      uninstall: t('audit.tagLifecycleUninstall'),
      lifecycle: t('audit.tagLifecycleAll')
    }
    tags.push({ key: 'lifecycle_mode', label: labelMap[lifecycleMode.value] || t('audit.tagLifecycleOther', { value: lifecycleMode.value }) })
  }
  if (trajectoryPrioritySort.value) tags.push({ key: 'trajectory_sort', label: t('audit.tagTrajectorySort') })
  if (groupByPlugin.value) tags.push({ key: 'group_by_plugin', label: t('audit.tagGroupByPlugin') })
  if (groupByFailurePriority.value) tags.push({ key: 'group_failure_priority', label: t('audit.tagGroupFailurePriority') })
  if (onlyFailedGroups.value) tags.push({ key: 'only_failed_groups', label: t('audit.tagOnlyFailed') })
  if (topFailedGroupsOnly.value) tags.push({ key: 'top_failed_groups', label: t('audit.tagTopFailedGroups', { limit: topFailedGroupLimit.value }) })
  if (quickActionFilter.value) tags.push({ key: 'quick_action', label: t('audit.tagAction', { value: quickActionFilter.value }) })
  if (quickActionPrefixFilter.value) tags.push({ key: 'quick_action_prefix', label: t('audit.tagActionPrefix', { value: quickActionPrefixFilter.value }) })
  if (quickStatusCodeFilter.value) tags.push({ key: 'quick_status', label: t('audit.tagStatusCode', { value: quickStatusCodeFilter.value }) })
  if (upgradeFailurePreset.value) tags.push({ key: 'upgrade_preset', label: t('audit.tagUpgradeProfile', { value: upgradeFailurePreset.value }) })
  if (autoRefreshEnabled.value) tags.push({ key: 'auto_refresh', label: t('audit.tagAutoRefresh', { seconds: autoRefreshSeconds.value }) })
  activeFilterTags.value = tags
}

const tableRows = computed(() => {
  const priorityMap: Record<string, number> = {
    plugin_upgrade: 0,
    plugin_install: 1,
    plugin_uninstall: 2,
  }
  if (!trajectoryPrioritySort.value && !groupByPlugin.value) return rows.value
  return [...rows.value].sort((a, b) => {
    if (groupByPlugin.value) {
      const ida = getSummaryField(String(a.summary || ''), 'plugin_id')
      const idb = getSummaryField(String(b.summary || ''), 'plugin_id')
      if (groupByFailurePriority.value) {
        const fa = Number(pluginGroupFailedCounts.value[ida || '-'] || 0)
        const fb = Number(pluginGroupFailedCounts.value[idb || '-'] || 0)
        if (fa !== fb) return fb - fa
        const ca = Number(pluginGroupCounts.value[ida || '-'] || 0)
        const cb = Number(pluginGroupCounts.value[idb || '-'] || 0)
        if (ca !== cb) return cb - ca
      }
      const cmp = ida.localeCompare(idb)
      if (cmp !== 0) return cmp
    }
    if (trajectoryPrioritySort.value) {
      const pa = priorityMap[String(a.action || '')] ?? 99
      const pb = priorityMap[String(b.action || '')] ?? 99
      if (pa !== pb) return pa - pb
    }
    const ta = Date.parse(String(a.created_at || '')) || 0
    const tb = Date.parse(String(b.created_at || '')) || 0
    return tb - ta
  })
})

const pluginGroupCounts = computed(() => {
  const out: Record<string, number> = {}
  for (const row of rows.value) {
    const pid = getSummaryField(String(row.summary || ''), 'plugin_id') || '-'
    out[pid] = (out[pid] || 0) + 1
  }
  return out
})

const pluginGroupFailedCounts = computed(() => {
  const out: Record<string, number> = {}
  for (const row of rows.value) {
    const pid = getSummaryField(String(row.summary || ''), 'plugin_id') || '-'
    if (String(row.result || '').toLowerCase() !== 'failed') continue
    out[pid] = (out[pid] || 0) + 1
  }
  return out
})

const sortedFailedGroupIds = computed(() => {
  return Object.keys(pluginGroupCounts.value)
    .filter((pid) => pid && pid !== '-')
    .sort((a, b) => {
      const fa = Number(pluginGroupFailedCounts.value[a] || 0)
      const fb = Number(pluginGroupFailedCounts.value[b] || 0)
      if (fa !== fb) return fb - fa
      const ca = Number(pluginGroupCounts.value[a] || 0)
      const cb = Number(pluginGroupCounts.value[b] || 0)
      if (ca !== cb) return cb - ca
      return a.localeCompare(b)
    })
})

const topFailedGroupSet = computed(() => {
  const s = new Set<string>()
  for (const pid of sortedFailedGroupIds.value.slice(0, topFailedGroupLimit.value)) {
    if (Number(pluginGroupFailedCounts.value[pid] || 0) > 0) s.add(pid)
  }
  return s
})

const totalGroupCount = computed(() => Object.keys(pluginGroupCounts.value).filter((k) => k && k !== '-').length)
const failedGroupCount = computed(() => Object.keys(pluginGroupFailedCounts.value).filter((k) => k && k !== '-' && Number(pluginGroupFailedCounts.value[k] || 0) > 0).length)
const visibleGroupCount = computed(() => {
  if (!groupByPlugin.value) return 0
  return new Set(displayRows.value.map((r) => getSummaryField(String(r.summary || ''), 'plugin_id') || '-')).size
})

const displayRows = computed(() => {
  if (!groupByPlugin.value) return tableRows.value
  const seen: Record<string, boolean> = {}
  const out: AuditLogItem[] = []
  for (const row of tableRows.value) {
    const pid = getSummaryField(String(row.summary || ''), 'plugin_id') || '-'
    if (onlyFailedGroups.value && Number(pluginGroupFailedCounts.value[pid] || 0) <= 0) {
      continue
    }
    if (topFailedGroupsOnly.value && !topFailedGroupSet.value.has(pid)) {
      continue
    }
    if (!seen[pid]) {
      seen[pid] = true
      out.push(row)
      continue
    }
    if (expandedPluginGroups.value[pid]) out.push(row)
  }
  return out
})

const getRowClassName = ({ rowIndex }: { rowIndex: number }) => {
  if (!groupByPlugin.value) return ''
  const current = displayRows.value[rowIndex]
  const prev = displayRows.value[rowIndex - 1]
  if (!current || rowIndex <= 0) return ''
  const curPid = getSummaryField(String(current.summary || ''), 'plugin_id') || '-'
  const prevPid = getSummaryField(String(prev?.summary || ''), 'plugin_id') || '-'
  return curPid !== prevPid ? 'audit-group-divider' : ''
}

const getPluginGroupCount = (pluginId: string) => {
  const pid = pluginId || '-'
  return Number(pluginGroupCounts.value[pid] || 0)
}

const getPluginGroupFailedCount = (pluginId: string) => {
  const pid = pluginId || '-'
  return Number(pluginGroupFailedCounts.value[pid] || 0)
}

const isPluginGroupFirstRow = (row: AuditLogItem) => {
  const pid = getSummaryField(String(row.summary || ''), 'plugin_id') || '-'
  const idx = displayRows.value.indexOf(row)
  if (idx <= 0) return true
  const prev = displayRows.value[idx - 1]
  const prevPid = getSummaryField(String(prev?.summary || ''), 'plugin_id') || '-'
  return pid !== prevPid
}

const isPluginGroupExpanded = (pluginId: string) => {
  const pid = pluginId || '-'
  return !!expandedPluginGroups.value[pid]
}

const togglePluginGroup = (pluginId: string) => {
  const pid = pluginId || '-'
  const next = {
    ...expandedPluginGroups.value,
    [pid]: !expandedPluginGroups.value[pid]
  }
  expandedPluginGroups.value = next
  const expanded = Object.keys(next).filter((k) => !!next[k] && k && k !== '-')
  const nextQuery = { ...(route.query as Record<string, unknown>) } as LocationQueryRaw
  if (expanded.length > 0) nextQuery.expanded_plugins = expanded.join(',')
  else delete nextQuery.expanded_plugins
  router.replace({ query: nextQuery }).catch(() => {})
}

const expandAllPluginGroups = () => {
  const map: Record<string, boolean> = {}
  for (const key of Object.keys(pluginGroupCounts.value)) {
    if (key && key !== '-' && Number(pluginGroupCounts.value[key] || 0) > 1) {
      map[key] = true
    }
  }
  expandedPluginGroups.value = map
  const expanded = Object.keys(map)
  const nextQuery = { ...(route.query as Record<string, unknown>) } as LocationQueryRaw
  if (expanded.length > 0) nextQuery.expanded_plugins = expanded.join(',')
  else delete nextQuery.expanded_plugins
  router.replace({ query: nextQuery }).catch(() => {})
}

const collapseAllPluginGroups = () => {
  expandedPluginGroups.value = {}
  const nextQuery = { ...(route.query as Record<string, unknown>) } as LocationQueryRaw
  delete nextQuery.expanded_plugins
  router.replace({ query: nextQuery }).catch(() => {})
}

const quickStats = computed(() => {
  const totalValue = Number(stats.value?.total ?? rows.value.length)
  const failedValue = Number(stats.value?.failed ?? rows.value.filter((x) => String(x.result || '').toLowerCase() === 'failed').length)
  const topActions = (stats.value?.top_actions || []).map((x) => [x.name, x.count] as [string, number]).slice(0, 2)
  const topStatus = (stats.value?.top_status_codes || []).map((x) => [x.code, x.count] as [string, number]).slice(0, 2)
  const items: Array<{
    key: string
    label: string
    type: 'info' | 'warning' | 'danger' | 'success'
    filterType: 'failed' | 'action' | 'status' | 'action_prefix'
    filterValue: string
  }> = []
  items.push({ key: 'failed', label: t('audit.quickStatFailed', { failed: failedValue, total: totalValue }), type: failedValue > 0 ? 'danger' : 'success', filterType: 'failed', filterValue: 'failed' })
  items.push({ key: 'family-runtime', label: t('audit.quickStatFamilyRuntime'), type: 'info', filterType: 'action_prefix', filterValue: 'plugin_runtime_' })
  items.push({ key: 'family-plugin', label: t('audit.quickStatFamilyPlugin'), type: 'success', filterType: 'action_prefix', filterValue: 'plugin_' })
  for (const [k, v] of topActions) items.push({ key: `action-${k}`, label: t('audit.quickStatAction', { key: k, count: v }), type: 'info', filterType: 'action', filterValue: k })
  for (const [k, v] of topStatus) {
    const n = Number(k)
    // FIX: [2026-07-04] 局部变量 t 遮蔽了 useI18n 的 t 函数，运行时 TypeError: t is not a function [全栈工程师]
    const tagType: 'info' | 'warning' | 'danger' = Number.isFinite(n) ? (n >= 500 ? 'danger' : (n >= 400 ? 'warning' : 'info')) : 'info'
    items.push({ key: `status-${k}`, label: t('audit.quickStatStatusCode', { key: k, count: v }), type: tagType, filterType: 'status', filterValue: k })
  }
  return items
})

const upgradeFailureBuckets = computed(() => {
  const buckets = upgradeProfileStats.value?.status_buckets || {}
  return [
    { key: '401', label: `401 (${Number(buckets['401'] || 0)})`, type: 'warning' as const },
    { key: '402', label: `402 (${Number(buckets['402'] || 0)})`, type: 'warning' as const },
    { key: '403', label: `403 (${Number(buckets['403'] || 0)})`, type: 'warning' as const },
    { key: '409', label: `409 (${Number(buckets['409'] || 0)})`, type: 'warning' as const },
    { key: '5xx', label: `5xx (${Number(buckets['5xx'] || 0)})`, type: 'danger' as const }
  ]
})

const upgradeProfileWindowLabel = computed(() => {
  const start = query.date_range?.[0]
  const end = query.date_range?.[1]
  if (!start || !end) return t('audit.timeWindowAll')
  const startTs = Date.parse(start)
  const endTs = Date.parse(end)
  if (!Number.isFinite(startTs) || !Number.isFinite(endTs) || endTs <= startTs) return t('audit.timeWindowCustom')
  const diffMin = Math.round((endTs - startTs) / 60000)
  if (diffMin >= 0 && diffMin <= 20) return t('audit.timeWindowNear15m')
  if (diffMin > 20 && diffMin <= 90) return t('audit.timeWindowNear1h')
  if (diffMin > 90 && diffMin <= 24 * 60 + 60) return t('audit.timeWindowNear24h')
  return t('audit.timeWindowCustom')
})

const activeTimeWindow = computed<'15m' | '1h' | '24h' | 'all' | 'custom'>(() => {
  const start = query.date_range?.[0]
  const end = query.date_range?.[1]
  if (!start || !end) return 'all'
  const startTs = Date.parse(start)
  const endTs = Date.parse(end)
  if (!Number.isFinite(startTs) || !Number.isFinite(endTs) || endTs <= startTs) return 'custom'
  const diffMin = Math.round((endTs - startTs) / 60000)
  if (diffMin >= 0 && diffMin <= 20) return '15m'
  if (diffMin > 20 && diffMin <= 90) return '1h'
  if (diffMin > 90 && diffMin <= 24 * 60 + 60) return '24h'
  return 'custom'
})

const upgradeWindowTagType = computed<'success' | 'warning' | 'info'>(() => {
  if (activeTimeWindow.value === '15m' || activeTimeWindow.value === '1h') return 'success'
  if (activeTimeWindow.value === '24h') return 'info'
  return 'warning'
})

const upgradeWindowRangeHint = computed(() => {
  const start = query.date_range?.[0]
  const end = query.date_range?.[1]
  if (!start || !end || activeTimeWindow.value !== 'custom') return ''
  return `${String(start).replace('T', ' ')} ~ ${String(end).replace('T', ' ')}`
})

const upgradeWindowToggleHint = computed(() => {
  if (!canQueryAudit) return t('audit.noQueryPermission')
  if (activeTimeWindow.value === '15m') return t('audit.clickRestoreAllTime')
  return t('audit.clickSwitchToOnCall')
})

const autoRefreshStateType = computed<'success' | 'warning' | 'info' | 'danger'>(() => {
  if (autoRefreshStoppedByError.value) return 'danger'
  if (!autoRefreshEnabled.value) return 'info'
  if (autoRefreshPausedByOffline.value) return 'warning'
  if (autoRefreshPausedByHidden.value) return 'warning'
  if (autoRefreshErrorStreak.value > 0) return 'danger'
  if (autoRefreshAdaptiveSlowMode.value) return 'warning'
  return autoRefreshIdleRounds.value >= 3 ? 'warning' : 'success'
})

const autoRefreshStateLabel = computed(() => {
  if (autoRefreshStoppedByError.value) return t('audit.autoRefreshStopped', { max: autoRefreshMaxErrorStreak })
  if (!autoRefreshEnabled.value) return t('audit.autoRefreshStateOff')
  if (autoRefreshPausedByOffline.value) return t('audit.autoRefreshStatePausedOffline')
  if (autoRefreshPausedByHidden.value) return t('audit.autoRefreshStatePausedHidden')
  if (autoRefreshErrorStreak.value > 0) return t('audit.autoRefreshStateError', { streak: autoRefreshErrorStreak.value, max: autoRefreshMaxErrorStreak })
  if (autoRefreshAdaptiveSlowMode.value) return t('audit.autoRefreshStateSlowMode')
  if (lastRefreshDurationMs.value > autoRefreshSeconds.value * 1000) return t('audit.autoRefreshStateLagging')
  if (autoRefreshIdleRounds.value >= 3) return t('audit.autoRefreshStateIdle', { rounds: autoRefreshIdleRounds.value })
  return t('audit.autoRefreshStateActive')
})

const autoRefreshStateHint = computed(() => {
  if (autoRefreshErrorStreak.value <= 0 || !autoRefreshLastError.value) return autoRefreshStateLabel.value
  return `${autoRefreshStateLabel.value}：${autoRefreshLastError.value}`
})

const lastRefreshDurationLabel = computed(() => {
  if (!lastRefreshDurationMs.value || lastRefreshDurationMs.value <= 0) return '-'
  if (lastRefreshDurationMs.value < 1000) return `${lastRefreshDurationMs.value}ms`
  return `${(lastRefreshDurationMs.value / 1000).toFixed(1)}s`
})

const effectiveAutoRefreshSeconds = computed(() => {
  if (autoRefreshAdaptiveSlowMode.value) return 30
  return autoRefreshSeconds.value
})

const autoRefreshButtonLabel = computed(() => {
  const base = autoRefreshEnabled.value ? t('audit.autoRefreshOn') : t('audit.autoRefreshOff')
  if (autoRefreshAdaptiveSlowMode.value) {
    return t('audit.autoRefreshLabelSlow', { seconds: effectiveAutoRefreshSeconds.value, state: base })
  }
  return t('audit.autoRefreshLabel', { seconds: effectiveAutoRefreshSeconds.value, state: base })
})

const autoRefreshButtonHint = computed(() => {
  const configured = `${autoRefreshSeconds.value}s`
  const effective = `${effectiveAutoRefreshSeconds.value}s`
  if (autoRefreshAdaptiveSlowMode.value) {
    return t('audit.autoRefreshHintSlow', { configured, effective })
  }
  return t('audit.autoRefreshHint', { configured, effective })
})

const nextRefreshCountdownLabel = computed(() => {
  if (!autoRefreshEnabled.value) return '-'
  if (autoRefreshStoppedByError.value) return '-'
  if (autoRefreshPausedByOffline.value || autoRefreshPausedByHidden.value) return t('audit.pausing')
  if (!nextAutoRefreshAtMs.value) return '-'
  const remainSec = Math.max(0, Math.ceil((nextAutoRefreshAtMs.value - nowMs.value) / 1000))
  return `${remainSec}s`
})

const lastRefreshErrorAgoLabel = computed(() => {
  if (!lastRefreshErrorAt.value) return ''
  const ts = Date.parse(lastRefreshErrorAt.value.replace(' ', 'T'))
  if (!Number.isFinite(ts)) return ''
  const diffSec = Math.max(0, Math.floor((nowMs.value - ts) / 1000))
  if (diffSec < 60) return t('audit.secondsAgo', { seconds: diffSec })
  if (diffSec < 3600) return t('audit.minutesAgo', { minutes: Math.floor(diffSec / 60) })
  if (diffSec < 86400) return t('audit.hoursAgo', { hours: Math.floor(diffSec / 3600) })
  return t('audit.daysAgo', { days: Math.floor(diffSec / 86400) })
})

const lastRefreshErrorAgoTagType = computed<'danger' | 'warning' | 'info'>(() => {
  if (!lastRefreshErrorAt.value) return 'info'
  const ts = Date.parse(lastRefreshErrorAt.value.replace(' ', 'T'))
  if (!Number.isFinite(ts)) return 'info'
  const diffSec = Math.max(0, Math.floor((nowMs.value - ts) / 1000))
  if (diffSec < 5 * 60) return 'danger'
  if (diffSec < 30 * 60) return 'warning'
  return 'info'
})

const lastRefreshResultLabel = computed(() => {
  if (lastRefreshOk.value === null) return '-'
  return lastRefreshOk.value ? t('audit.refreshSuccess') : t('audit.refreshFailed')
})

const lastRefreshResultTagType = computed<'success' | 'danger' | 'info'>(() => {
  if (lastRefreshOk.value === null) return 'info'
  return lastRefreshOk.value ? 'success' : 'danger'
})

const refreshHealthType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  if (refreshFailureStreak.value >= 3) return 'danger'
  if (refreshFailureStreak.value > 0) return 'warning'
  if (refreshSuccessStreak.value >= 5) return 'success'
  return 'info'
})

const refreshHealthLabel = computed(() => {
  if (refreshFailureStreak.value >= 3) return t('audit.healthUnstable')
  if (refreshFailureStreak.value > 0) return t('audit.healthRecovering')
  if (refreshSuccessStreak.value >= 5) return t('audit.healthStable')
  return t('audit.healthObserving')
})

const refreshHealthHint = computed(() => {
  if (refreshFailureStreak.value >= 3) {
    return t('audit.healthHintUnstable', { streak: refreshFailureStreak.value })
  }
  if (refreshFailureStreak.value > 0) {
    return t('audit.healthHintRecovering', { streak: refreshFailureStreak.value })
  }
  if (refreshSuccessStreak.value >= 5) {
    return t('audit.healthHintStable', { streak: refreshSuccessStreak.value })
  }
  return t('audit.healthHintObserving')
})

const copyFormatLabel = computed(() => {
  if (lastCopyFormat.value === 'markdown') return 'Markdown'
  if (lastCopyFormat.value === 'codeblock') return t('audit.copyFormatCodeblock')
  return t('audit.copyFormatPlain')
})

const formatLocalDateTime = (d: Date): string => {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const setTimeWindowMinutes = (minutes: number) => {
  const end = new Date()
  const start = new Date(end.getTime() - minutes * 60 * 1000)
  query.date_range = [formatLocalDateTime(start), formatLocalDateTime(end)]
}

const markRefreshedNow = () => {
  lastRefreshAt.value = formatLocalDateTime(new Date()).replace('T', ' ')
}

const startNowTicker = () => {
  if (refreshTicker.value !== null) return
  refreshTicker.value = window.setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
}

const stopNowTicker = () => {
  if (refreshTicker.value === null) return
  window.clearInterval(refreshTicker.value)
  refreshTicker.value = null
}

const applyTimeWindowMinutes = async (minutes: number) => {
  setTimeWindowMinutes(minutes)
  page.value = 1
  await search(true)
}

const clearTimeWindow = async () => {
  query.date_range = null
  page.value = 1
  await search(true)
}

const toggleRecommendedOnCallWindow = async () => {
  if (!canQueryAudit.value) return
  if (activeTimeWindow.value === '15m') {
    await clearTimeWindow()
    return
  }
  await applyTimeWindowMinutes(15)
}

const stopAutoRefresh = (resetErrorState = true) => {
  if (autoRefreshTimer.value !== null) {
    window.clearInterval(autoRefreshTimer.value)
    autoRefreshTimer.value = null
  }
  nextAutoRefreshAtMs.value = 0
  lastAutoTriggerAtMs.value = 0
  autoRefreshPausedByHidden.value = false
  autoRefreshPausedByOffline.value = false
  autoRefreshLastTotal.value = null
  autoRefreshIdleRounds.value = 0
  autoRefreshAdaptiveSlowMode.value = false
  if (resetErrorState) {
    autoRefreshErrorStreak.value = 0
    autoRefreshLastError.value = ''
    autoRefreshStoppedByError.value = false
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!autoRefreshEnabled.value) return
  const intervalMs = effectiveAutoRefreshSeconds.value * 1000
  nextAutoRefreshAtMs.value = Date.now() + intervalMs
  autoRefreshTimer.value = window.setInterval(() => {
    if (!navigator.onLine) {
      autoRefreshPausedByOffline.value = true
      return
    }
    autoRefreshPausedByOffline.value = false
    if (document.hidden) {
      autoRefreshPausedByHidden.value = true
      return
    }
    autoRefreshPausedByHidden.value = false
    triggerAutoRefreshNow()
  }, intervalMs)
}

const triggerAutoRefreshNow = () => {
  if (!autoRefreshEnabled.value || loading.value) return
  if (!navigator.onLine || document.hidden) return
  const now = Date.now()
  if (now - lastAutoTriggerAtMs.value < autoTriggerMinGapMs) return
  lastAutoTriggerAtMs.value = now
  nextAutoRefreshAtMs.value = now + effectiveAutoRefreshSeconds.value * 1000
  search(true, { suppressErrorToast: true, fromAutoRefresh: true })
}

const onVisibilityChange = () => {
  autoRefreshPausedByHidden.value = document.hidden && autoRefreshEnabled.value
  if (!document.hidden) triggerAutoRefreshNow()
}

const onNetworkOnline = () => {
  autoRefreshPausedByOffline.value = false
  triggerAutoRefreshNow()
}

const onNetworkOffline = () => {
  autoRefreshPausedByOffline.value = autoRefreshEnabled.value
}

const toggleAutoRefresh = async () => {
  autoRefreshEnabled.value = !autoRefreshEnabled.value
  if (autoRefreshEnabled.value && !query.date_range) setTimeWindowMinutes(15)
  if (autoRefreshEnabled.value) {
    autoRefreshLastTotal.value = null
    autoRefreshIdleRounds.value = 0
    autoRefreshErrorStreak.value = 0
    autoRefreshLastError.value = ''
    autoRefreshStoppedByError.value = false
    autoRefreshAdaptiveSlowMode.value = false
  }
  saveAutoRefreshPrefs()
  startAutoRefresh()
  page.value = 1
  await search(true)
}

const onAutoRefreshSecondsChange = async (value: number | string) => {
  const n = Number(value)
  if (n !== 10 && n !== 30) return
  autoRefreshSeconds.value = n as 10 | 30
  saveAutoRefreshPrefs()
  if (autoRefreshEnabled.value) {
    startAutoRefresh()
    page.value = 1
    await search(true)
  }
}

const manualRefresh = async () => {
  if (!canQueryAudit) return
  await search(true)
}

const resumeAutoRefresh = async () => {
  if (!canQueryAudit || loading.value) return
  autoRefreshEnabled.value = true
  autoRefreshStoppedByError.value = false
  autoRefreshErrorStreak.value = 0
  autoRefreshLastError.value = ''
  if (!query.date_range) setTimeWindowMinutes(15)
  saveAutoRefreshPrefs()
  startAutoRefresh()
  page.value = 1
  await search(true)
}

const clearAutoRefreshErrorState = () => {
  autoRefreshErrorStreak.value = 0
  autoRefreshLastError.value = ''
  autoRefreshStoppedByError.value = false
}

const resetRefreshTelemetry = () => {
  lastRefreshAt.value = ''
  lastRefreshOk.value = null
  lastRefreshErrorAt.value = ''
  refreshSuccessStreak.value = 0
  refreshFailureStreak.value = 0
  lastRefreshDurationMs.value = 0
  autoRefreshLastTotal.value = null
  autoRefreshIdleRounds.value = 0
}

const resetUpgradeProfileFilters = async () => {
  lifecycleMode.value = ''
  upgradeFailurePreset.value = ''
  quickActionFilter.value = ''
  quickActionPrefixFilter.value = ''
  quickStatusCodeFilter.value = ''
  query.result = ''
  page.value = 1
  await search(true)
}

const buildTroubleshootingSummaryParts = () => {
  const kv: string[] = []
  kv.push(`${t('audit.summaryWindow')}=${upgradeProfileWindowLabel.value}`)
  kv.push(`${t('audit.summaryTotal')}=${total.value}`)
  if (autoRefreshEnabled.value || autoRefreshStoppedByError.value) {
    kv.push(`${t('audit.summaryAutoRefreshStatus')}=${autoRefreshStateLabel.value}`)
    kv.push(`${t('audit.summaryAutoRefreshConfigInterval')}=${autoRefreshSeconds.value}s`)
    kv.push(`${t('audit.summaryAutoRefreshEffectiveInterval')}=${effectiveAutoRefreshSeconds.value}s`)
    kv.push(`${t('audit.summaryNextRefreshCountdown')}=${nextRefreshCountdownLabel.value}`)
  }
  if (lastRefreshAt.value) kv.push(`${t('audit.summaryLastRefresh')}=${lastRefreshAt.value}`)
  if (lastRefreshOk.value !== null) kv.push(`${t('audit.summaryLastRefreshResult')}=${lastRefreshOk.value ? t('audit.refreshSuccess') : t('audit.refreshFailed')}`)
  if (lastRefreshErrorAt.value) kv.push(`${t('audit.summaryLastFailureTime')}=${lastRefreshErrorAt.value}`)
  if (lastRefreshErrorAgoLabel.value) kv.push(`${t('audit.summaryFailureAgo')}=${lastRefreshErrorAgoLabel.value}`)
  if (refreshSuccessStreak.value > 0) kv.push(`${t('audit.summaryConsecutiveSuccess')}=${refreshSuccessStreak.value}`)
  if (refreshFailureStreak.value > 0) kv.push(`${t('audit.summaryConsecutiveFailure')}=${refreshFailureStreak.value}`)
  const healthStatusPart = refreshFailureStreak.value >= 3
    ? t('audit.healthStatusUnstable')
    : refreshFailureStreak.value > 0
      ? t('audit.healthStatusRecovering')
      : refreshSuccessStreak.value >= 5
        ? t('audit.healthStatusStable')
        : t('audit.healthStatusObserving')
  kv.push(`${t('audit.summaryHealth')}=${healthStatusPart}`)
  kv.push(`${t('audit.summaryHealthBasis')}=${refreshHealthHint.value}`)
  if (lastRefreshDurationLabel.value !== '-') kv.push(`${t('audit.summaryRefreshDuration')}=${lastRefreshDurationLabel.value}`)
  if (lifecycleMode.value) kv.push(`${t('audit.summaryLifecycle')}=${lifecycleMode.value}`)
  if (upgradeFailurePreset.value) kv.push(`${t('audit.summaryUpgradeProfile')}=${upgradeFailurePreset.value}`)
  if (quickActionFilter.value) kv.push(`${t('audit.summaryAction')}=${quickActionFilter.value}`)
  if (quickActionPrefixFilter.value) kv.push(`${t('audit.summaryActionFamily')}=${quickActionPrefixFilter.value}*`)
  if (quickStatusCodeFilter.value) kv.push(`${t('audit.summaryStatusCode')}=${quickStatusCodeFilter.value}`)
  if (query.module.trim()) kv.push(`${t('audit.module')}=${query.module.trim()}`)
  if (query.operator.trim()) kv.push(`${t('audit.operator')}=${query.operator.trim()}`)
  if (query.result) kv.push(`${t('audit.resultLabel')}=${query.result}`)
  const topAction = stats.value?.top_actions?.[0]
  const topStatus = stats.value?.top_status_codes?.[0]
  const failed = Number(stats.value?.failed ?? 0)
  const statTotal = Number(stats.value?.total ?? total.value)
  kv.push(`${t('audit.summaryFailed')}=${failed}/${statTotal}`)
  if (topAction) kv.push(`${t('audit.summaryTopAction')}=${topAction.name}(${topAction.count})`)
  if (topStatus) kv.push(`${t('audit.summaryTopStatusCode')}=${topStatus.code}(${topStatus.count})`)
  return kv
}

const copyTroubleshootingSummary = async () => {
  const kv = buildTroubleshootingSummaryParts()
  const text = `【${t('audit.summaryTitle')}】${kv.join(' | ')}\n${t('audit.summaryLink')}: ${window.location.href}`

  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    ElMessage.warning(t('audit.copyFailed'))
    return false
  }
}

const copyTroubleshootingSummaryMarkdown = async () => {
  const kv = buildTroubleshootingSummaryParts()
  const markdown = [
    `## ${t('audit.summaryTitle')}`,
    '',
    ...kv.map((x) => `- ${x}`),
    '',
    `- ${t('audit.summaryLink')}: ${window.location.href}`
  ].join('\n')
  try {
    await navigator.clipboard.writeText(markdown)
    return true
  } catch {
    ElMessage.warning(t('audit.copyFailed'))
    return false
  }
}

const copyTroubleshootingSummaryMarkdownCodeBlock = async () => {
  const kv = buildTroubleshootingSummaryParts()
  const plain = [
    t('audit.summaryTitle'),
    ...kv,
    `${t('audit.summaryLink')}: ${window.location.href}`
  ].join('\n')
  const markdown = ['```text', plain, '```'].join('\n')
  try {
    await navigator.clipboard.writeText(markdown)
    return true
  } catch {
    ElMessage.warning(t('audit.copyFailed'))
    return false
  }
}

const runCopyByFormat = async (format: 'plain' | 'markdown' | 'codeblock') => {
  lastCopyFormat.value = format
  localStorage.setItem(COPY_FORMAT_KEY, format)
  let ok = false
  if (format === 'plain') {
    ok = await copyTroubleshootingSummary()
  } else if (format === 'markdown') {
    ok = await copyTroubleshootingSummaryMarkdown()
  } else {
    ok = await copyTroubleshootingSummaryMarkdownCodeBlock()
  }
  if (ok) {
    const label = format === 'plain' ? t('audit.copyFormatPlain') : (format === 'markdown' ? 'Markdown' : t('audit.copyFormatMarkdownCodeblock'))
    ElMessage.success(t('audit.copiedSummary', { label }))
  }
}

const copySummaryWithLastFormat = async () => {
  await runCopyByFormat(lastCopyFormat.value)
}

const handleCopySummaryCommand = async (command: string) => {
  if (command === 'plain') {
    await runCopyByFormat('plain')
  } else if (command === 'markdown') {
    await runCopyByFormat('markdown')
  } else if (command === 'codeblock') {
    await runCopyByFormat('codeblock')
  }
}

const getSummaryField = (summary: string, key: string): string => {
  if (!summary) return ''
  const tokens = summary.split(';')
  for (const token of tokens) {
    const normalized = token.trim()
    if (normalized.startsWith(`${key}=`)) {
      return normalized.slice(key.length + 1).trim()
    }
  }
  return ''
}

const parseSummaryEntries = (summary: string): Array<{ key: string; value: string }> => {
  if (!summary) return []
  return summary
    .split(';')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const idx = item.indexOf('=')
      if (idx <= 0) return { key: item, value: '' }
      return {
        key: item.slice(0, idx).trim(),
        value: item.slice(idx + 1).trim()
      }
    })
}

const viewDetail = (row: AuditLogItem) => {
  detailRow.value = row
  detailDialogVisible.value = true
}

const normalizeQueryRecord = (q: Record<string, unknown>) => {
  const out: Record<string, string> = {}
  const keys = Object.keys(q).sort()
  for (const key of keys) {
    const val = q[key]
    if (val === undefined || val === null || val === '') continue
    out[key] = String(val)
  }
  return out
}

const isSameRouteQuery = (a: Record<string, unknown>, b: Record<string, unknown>) => {
  const na = normalizeQueryRecord(a)
  const nb = normalizeQueryRecord(b)
  const ka = Object.keys(na)
  const kb = Object.keys(nb)
  if (ka.length !== kb.length) return false
  for (const key of ka) {
    if (na[key] !== nb[key]) return false
  }
  return true
}

const search = async (
  silent = false,
  options: { suppressErrorToast?: boolean; fromAutoRefresh?: boolean } = {}
) => {
  if (!canQueryAudit) {
    rows.value = []
    total.value = 0
    return
  }
  const message = validateFields(filterFields, query as Record<string, unknown>)
  if (message) {
    ElMessage.warning(t('audit.validationFailed', { message }))
    return
  }
  const moduleValue = query.module.trim()
  const operatorValue = query.operator.trim()
  const startedAt = Date.now()
  const requestSeq = ++searchRequestSeq.value
  loading.value = true
  try {
    const startAt = query.date_range?.[0] || undefined
    const endAt = query.date_range?.[1] || undefined
    const actionValue =
      lifecycleMode.value === 'install'
        ? 'plugin_install'
        : lifecycleMode.value === 'upgrade'
          ? 'plugin_upgrade'
          : lifecycleMode.value === 'uninstall'
            ? 'plugin_uninstall'
            : (quickActionFilter.value || undefined)
    const actionPrefixValue = lifecycleMode.value === 'lifecycle' ? 'plugin_' : (quickActionPrefixFilter.value || undefined)
    const statusCodeValue = upgradeFailurePreset.value && upgradeFailurePreset.value !== '5xx'
      ? Number(upgradeFailurePreset.value)
      : (quickStatusCodeFilter.value ? Number(quickStatusCodeFilter.value) : undefined)
    const statusFamilyValue = upgradeFailurePreset.value === '5xx' ? 5 : undefined
    const listQuery = {
      module: moduleValue || undefined,
      action: actionValue,
      action_prefix: actionPrefixValue,
      operator: operatorValue || undefined,
      result: query.result || undefined,
      plugin_id: query.plugin_id || undefined,
      source: query.source || undefined,
      tenant_id: query.tenant_id || undefined,
      status_code: statusCodeValue,
      status_family: statusFamilyValue,
      start_at: startAt,
      end_at: endAt,
      page: page.value,
      page_size: pageSize.value
    }
    const statsQuery = {
      module: moduleValue || undefined,
      action: actionValue,
      action_prefix: actionPrefixValue,
      operator: operatorValue || undefined,
      result: query.result || undefined,
      plugin_id: query.plugin_id || undefined,
      source: query.source || undefined,
      tenant_id: query.tenant_id || undefined,
      status_code: statusCodeValue,
      status_family: statusFamilyValue,
      start_at: startAt,
      end_at: endAt
    }
    const upgradeProfileQuery = {
      module: moduleValue || undefined,
      action: 'plugin_upgrade',
      operator: operatorValue || undefined,
      result: 'failed',
      start_at: startAt,
      end_at: endAt
    }
    const [res, statsRes, upgradeStatsRes] = await Promise.all([
      listAuditLogs(listQuery),
      getAuditStats(statsQuery),
      getAuditStats(upgradeProfileQuery)
    ])
    if (requestSeq !== searchRequestSeq.value) return
    rows.value = res.items || []
    total.value = Number(res.total || 0)
    if (autoRefreshEnabled.value) {
      if (autoRefreshLastTotal.value === null) {
        autoRefreshIdleRounds.value = 0
      } else if (autoRefreshLastTotal.value === total.value) {
        autoRefreshIdleRounds.value += 1
      } else {
        autoRefreshIdleRounds.value = 0
      }
      autoRefreshLastTotal.value = total.value
    } else {
      autoRefreshLastTotal.value = null
      autoRefreshIdleRounds.value = 0
    }
    autoRefreshErrorStreak.value = 0
    autoRefreshLastError.value = ''
    autoRefreshStoppedByError.value = false
    if (options.fromAutoRefresh && autoRefreshAdaptiveSlowMode.value) {
      autoRefreshAdaptiveSlowMode.value = false
      startAutoRefresh()
    }
    stats.value = statsRes
    upgradeProfileStats.value = upgradeStatsRes
    refreshActiveFilterTags()
    const nextQuery: Record<string, string> = {}
    if (moduleValue) nextQuery.module = moduleValue
    if (operatorValue) nextQuery.operator = operatorValue
    if (query.result) nextQuery.result = query.result
    if (query.plugin_id) nextQuery.plugin_id = query.plugin_id
    if (query.source) nextQuery.source = query.source
    if (query.tenant_id) nextQuery.tenant_id = query.tenant_id
    if (startAt) nextQuery.start_at = startAt
    if (endAt) nextQuery.end_at = endAt
    if (activeTimeWindow.value !== 'custom') nextQuery.time_window = activeTimeWindow.value
    if (autoRefreshEnabled.value) nextQuery.auto_refresh = '1'
    if (autoRefreshSeconds.value !== 30) nextQuery.refresh_sec = String(autoRefreshSeconds.value)
    if (lifecycleMode.value) nextQuery.lifecycle_mode = lifecycleMode.value
    if (trajectoryPrioritySort.value) nextQuery.trajectory_sort = '1'
    if (groupByPlugin.value) nextQuery.group_by_plugin = '1'
    if (groupByFailurePriority.value) nextQuery.group_failure_priority = '1'
    if (onlyFailedGroups.value) nextQuery.only_failed_groups = '1'
    if (topFailedGroupsOnly.value) nextQuery.top_failed_groups = '1'
    if (topFailedGroupLimit.value !== 5) nextQuery.top_failed_limit = String(topFailedGroupLimit.value)
    const expanded = Object.keys(expandedPluginGroups.value).filter((k) => !!expandedPluginGroups.value[k] && k && k !== '-')
    if (expanded.length > 0) nextQuery.expanded_plugins = expanded.join(',')
    if (quickActionFilter.value) nextQuery.action = quickActionFilter.value
    if (quickActionPrefixFilter.value) nextQuery.action_prefix = quickActionPrefixFilter.value
    if (quickStatusCodeFilter.value) nextQuery.status_code = quickStatusCodeFilter.value
    if (upgradeFailurePreset.value) nextQuery.upgrade_preset = upgradeFailurePreset.value
    nextQuery.page = String(page.value)
    nextQuery.page_size = String(pageSize.value)
    if (!isSameRouteQuery(route.query as Record<string, unknown>, nextQuery)) {
      router.replace({ query: nextQuery }).catch(() => {})
    }
    if (!silent) {
      ElMessage.success(buildSuccessMessage(t('audit.searchSuccessAction'), t('audit.searchSuccessDetail', { count: rows.value.length })))
    }
    lastRefreshOk.value = true
    lastRefreshErrorAt.value = ''
    refreshSuccessStreak.value += 1
    refreshFailureStreak.value = 0
    markRefreshedNow()
  } catch (error: unknown) {
    if (requestSeq !== searchRequestSeq.value) return
    stats.value = null
    upgradeProfileStats.value = null
    if (options.fromAutoRefresh) {
      autoRefreshErrorStreak.value += 1
      autoRefreshLastError.value = getApiErrorMessage(error, t('audit.logReadError'))
      if (autoRefreshErrorStreak.value >= 2 && autoRefreshSeconds.value === 10 && !autoRefreshAdaptiveSlowMode.value) {
        autoRefreshAdaptiveSlowMode.value = true
        startAutoRefresh()
      }
      if (autoRefreshErrorStreak.value >= autoRefreshMaxErrorStreak) {
        autoRefreshEnabled.value = false
        autoRefreshStoppedByError.value = true
        stopAutoRefresh(false)
        saveAutoRefreshPrefs()
        ElMessage.warning(t('audit.autoRefreshStoppedWarning', { max: autoRefreshMaxErrorStreak }))
      }
    }
    if (!options.suppressErrorToast) {
    ElMessage.error(buildErrorMessage(t('audit.searchSuccessAction'), error, t('audit.logReadError')))
    }
    lastRefreshOk.value = false
    lastRefreshErrorAt.value = formatLocalDateTime(new Date()).replace('T', ' ')
    refreshSuccessStreak.value = 0
    refreshFailureStreak.value += 1
  } finally {
    if (requestSeq !== searchRequestSeq.value) return
    lastRefreshDurationMs.value = Math.max(0, Date.now() - startedAt)
    loading.value = false
  }
}

const resetForm = async () => {
  query.module = ''
  query.operator = ''
  query.result = ''
  query.plugin_id = ''
  query.source = ''
  query.tenant_id = ''
  query.date_range = null
  lifecycleMode.value = ''
  trajectoryPrioritySort.value = false
  groupByPlugin.value = false
  groupByFailurePriority.value = false
  onlyFailedGroups.value = false
  topFailedGroupsOnly.value = false
  expandedPluginGroups.value = {}
  quickActionFilter.value = ''
  quickActionPrefixFilter.value = ''
  quickStatusCodeFilter.value = ''
  upgradeFailurePreset.value = ''
  autoRefreshEnabled.value = false
  stopAutoRefresh()
  saveAutoRefreshPrefs()
  resetRefreshTelemetry()
  autoRefreshStoppedByError.value = false
  page.value = 1
  pageSize.value = 20
  await search()
}

const toggleLifecycleMode = async (mode: 'install' | 'upgrade' | 'uninstall' | 'lifecycle') => {
  lifecycleMode.value = lifecycleMode.value === mode ? '' : mode
  if (lifecycleMode.value) {
    quickActionFilter.value = ''
    quickActionPrefixFilter.value = ''
    upgradeFailurePreset.value = ''
  }
  page.value = 1
  await search(true)
}

const toggleTrajectoryPrioritySort = async () => {
  trajectoryPrioritySort.value = !trajectoryPrioritySort.value
  page.value = 1
  await search(true)
}

const toggleGroupByPlugin = async () => {
  groupByPlugin.value = !groupByPlugin.value
  if (!groupByPlugin.value) {
    expandedPluginGroups.value = {}
    groupByFailurePriority.value = false
    onlyFailedGroups.value = false
    topFailedGroupsOnly.value = false
  }
  page.value = 1
  await search(true)
}

const toggleGroupByFailurePriority = async () => {
  groupByFailurePriority.value = !groupByFailurePriority.value
  page.value = 1
  await search(true)
}

const toggleOnlyFailedGroups = async () => {
  onlyFailedGroups.value = !onlyFailedGroups.value
  if (!onlyFailedGroups.value) topFailedGroupsOnly.value = false
  page.value = 1
  await search(true)
}

const toggleTopFailedGroupsOnly = async () => {
  topFailedGroupsOnly.value = !topFailedGroupsOnly.value
  if (topFailedGroupsOnly.value) onlyFailedGroups.value = true
  page.value = 1
  await search(true)
}

const onTopFailedLimitChange = async (value: number | string) => {
  const n = Number(value)
  if (![3, 5, 10].includes(n)) return
  topFailedGroupLimit.value = n
  if (topFailedGroupsOnly.value) {
    page.value = 1
    await search(true)
  }
}

const toggleUpgradeFailurePreset = async (preset: '401' | '402' | '403' | '409' | '5xx') => {
  upgradeFailurePreset.value = upgradeFailurePreset.value === preset ? '' : preset
  if (upgradeFailurePreset.value) {
    lifecycleMode.value = 'upgrade'
    query.result = 'failed'
    quickActionFilter.value = ''
    quickActionPrefixFilter.value = ''
    quickStatusCodeFilter.value = ''
  }
  page.value = 1
  await search(true)
}

const applyQuickStatFilter = async (stat: { filterType: 'failed' | 'action' | 'status' | 'action_prefix'; filterValue: string }) => {
  if (stat.filterType === 'failed') {
    query.result = query.result === 'failed' ? '' : 'failed'
    if (query.result !== 'failed') upgradeFailurePreset.value = ''
  } else if (stat.filterType === 'action') {
    lifecycleMode.value = ''
    quickActionPrefixFilter.value = ''
    upgradeFailurePreset.value = ''
    quickActionFilter.value = quickActionFilter.value === stat.filterValue ? '' : stat.filterValue
  } else if (stat.filterType === 'action_prefix') {
    lifecycleMode.value = ''
    quickActionFilter.value = ''
    upgradeFailurePreset.value = ''
    quickActionPrefixFilter.value = quickActionPrefixFilter.value === stat.filterValue ? '' : stat.filterValue
  } else if (stat.filterType === 'status') {
    upgradeFailurePreset.value = ''
    quickStatusCodeFilter.value = quickStatusCodeFilter.value === stat.filterValue ? '' : stat.filterValue
  }
  page.value = 1
  await search(true)
}

const isQuickStatActive = (stat: { filterType: 'failed' | 'action' | 'status' | 'action_prefix'; filterValue: string }) => {
  if (stat.filterType === 'failed') return query.result === 'failed'
  if (stat.filterType === 'action') return quickActionFilter.value === stat.filterValue
  if (stat.filterType === 'action_prefix') return quickActionPrefixFilter.value === stat.filterValue
  if (stat.filterType === 'status') return quickStatusCodeFilter.value === stat.filterValue
  return false
}

const clearFilterTag = async (key: string) => {
  if (key === 'module') query.module = ''
  else if (key === 'operator') query.operator = ''
  else if (key === 'result') query.result = ''
  else if (key === 'plugin_id') query.plugin_id = ''
  else if (key === 'source') query.source = ''
  else if (key === 'tenant_id') query.tenant_id = ''
  else if (key === 'date_range') query.date_range = null
  else if (key === 'lifecycle_mode') lifecycleMode.value = ''
  else if (key === 'trajectory_sort') trajectoryPrioritySort.value = false
  else if (key === 'group_by_plugin') groupByPlugin.value = false
  else if (key === 'group_failure_priority') groupByFailurePriority.value = false
  else if (key === 'only_failed_groups') onlyFailedGroups.value = false
  else if (key === 'top_failed_groups') topFailedGroupsOnly.value = false
  else if (key === 'quick_action') quickActionFilter.value = ''
  else if (key === 'quick_action_prefix') quickActionPrefixFilter.value = ''
  else if (key === 'quick_status') quickStatusCodeFilter.value = ''
  else if (key === 'upgrade_preset') upgradeFailurePreset.value = ''
  else if (key === 'auto_refresh') {
    autoRefreshEnabled.value = false
    stopAutoRefresh()
    saveAutoRefreshPrefs()
  }
  page.value = 1
  if (!groupByPlugin.value) expandedPluginGroups.value = {}
  await search(true)
}

const onPageChange = async (next: number) => {
  page.value = next
  await search(true)
}

const onSizeChange = async (size: number) => {
  pageSize.value = size
  page.value = 1
  await search(true)
}

const exportLoading = ref(false)
const handleExport = async () => {
  if (!canQueryAudit) return
  exportLoading.value = true
  try {
    const startAt = query.date_range?.[0] || undefined
    const endAt = query.date_range?.[1] || undefined
    const actionValue =
      lifecycleMode.value === 'install'
        ? 'plugin_install'
        : lifecycleMode.value === 'upgrade'
          ? 'plugin_upgrade'
          : lifecycleMode.value === 'uninstall'
            ? 'plugin_uninstall'
            : (quickActionFilter.value || undefined)
    const actionPrefixValue = lifecycleMode.value === 'lifecycle' ? 'plugin_' : (quickActionPrefixFilter.value || undefined)
    const statusCodeValue = upgradeFailurePreset.value && upgradeFailurePreset.value !== '5xx'
      ? Number(upgradeFailurePreset.value)
      : (quickStatusCodeFilter.value ? Number(quickStatusCodeFilter.value) : undefined)
    const statusFamilyValue = upgradeFailurePreset.value === '5xx' ? 5 : undefined
    await downloadAuditCsv({
      module: query.module?.trim() || undefined,
      action: actionValue,
      action_prefix: actionPrefixValue,
      operator: query.operator?.trim() || undefined,
      result: query.result || undefined,
      plugin_id: query.plugin_id?.trim() || undefined,
      source: query.source?.trim() || undefined,
      tenant_id: query.tenant_id?.trim() || undefined,
      status_code: statusCodeValue,
      status_family: statusFamilyValue,
      start_at: startAt,
      end_at: endAt
    })
    ElMessage.success(t('audit.exportSuccess'))
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('audit.exportFailed')))
  } finally {
    exportLoading.value = false
  }
}

onMounted(async () => {
  // FIX H-8: 从后端刷新权威角色信息
  // FIX: [2026-07-04] getVerifiedRoleInfo 返回 RoleInfo|null，需判空后赋值 [全栈工程师]
  const verified = await getVerifiedRoleInfo()
  if (verified) roleInfo.value = verified
  startNowTicker()
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('online', onNetworkOnline)
  window.addEventListener('offline', onNetworkOffline)
  autoRefreshPausedByOffline.value = !navigator.onLine && autoRefreshEnabled.value
  const savedCopyFormat = localStorage.getItem(COPY_FORMAT_KEY)
  if (savedCopyFormat === 'plain' || savedCopyFormat === 'markdown' || savedCopyFormat === 'codeblock') {
    lastCopyFormat.value = savedCopyFormat
  }
  const q = route.query as Record<string, unknown>
  if (typeof q.module === 'string') query.module = q.module
  if (typeof q.operator === 'string') query.operator = q.operator
  if (typeof q.result === 'string') query.result = q.result
  if (typeof q.plugin_id === 'string') query.plugin_id = q.plugin_id
  if (typeof q.source === 'string') query.source = q.source
  if (typeof q.tenant_id === 'string') query.tenant_id = q.tenant_id
  if (typeof q.trajectory_sort === 'string' && q.trajectory_sort === '1') trajectoryPrioritySort.value = true
  if (typeof q.group_by_plugin === 'string' && q.group_by_plugin === '1') groupByPlugin.value = true
  if (typeof q.group_failure_priority === 'string' && q.group_failure_priority === '1') groupByFailurePriority.value = true
  if (typeof q.only_failed_groups === 'string' && q.only_failed_groups === '1') onlyFailedGroups.value = true
  if (typeof q.top_failed_groups === 'string' && q.top_failed_groups === '1') topFailedGroupsOnly.value = true
  if (typeof q.top_failed_limit === 'string') {
    const n = Number(q.top_failed_limit)
    if ([3, 5, 10].includes(n)) topFailedGroupLimit.value = n
  }
  if (typeof q.expanded_plugins === 'string' && q.expanded_plugins.trim()) {
    const map: Record<string, boolean> = {}
    for (const pid of q.expanded_plugins.split(',')) {
      const key = String(pid || '').trim()
      if (key) map[key] = true
    }
    expandedPluginGroups.value = map
  }
  if (typeof q.action === 'string' && !['plugin_install', 'plugin_upgrade', 'plugin_uninstall'].includes(q.action)) quickActionFilter.value = q.action
  if (typeof q.action_prefix === 'string' && q.lifecycle_mode !== 'lifecycle') quickActionPrefixFilter.value = q.action_prefix
  if (typeof q.status_code === 'string') quickStatusCodeFilter.value = q.status_code
  if (typeof q.upgrade_preset === 'string' && ['401', '402', '403', '409', '5xx'].includes(q.upgrade_preset)) {
    upgradeFailurePreset.value = q.upgrade_preset as '401' | '402' | '403' | '409' | '5xx'
    lifecycleMode.value = 'upgrade'
    query.result = 'failed'
  }
  const startAt = typeof q.start_at === 'string' ? q.start_at : undefined
  const endAt = typeof q.end_at === 'string' ? q.end_at : undefined
  if (startAt || endAt) query.date_range = [startAt || '', endAt || '']
  if (!startAt && !endAt && typeof q.time_window === 'string') {
    if (q.time_window === '15m') setTimeWindowMinutes(15)
    else if (q.time_window === '1h') setTimeWindowMinutes(60)
    else if (q.time_window === '24h') setTimeWindowMinutes(1440)
    else if (q.time_window === 'all') query.date_range = null
  }
  if (
    typeof q.lifecycle_mode === 'string' &&
    ['install', 'upgrade', 'uninstall', 'lifecycle'].includes(q.lifecycle_mode)
  ) {
    lifecycleMode.value = q.lifecycle_mode as 'install' | 'upgrade' | 'uninstall' | 'lifecycle'
  }
  if (typeof q.page === 'string') {
    const p = Number(q.page)
    if (Number.isFinite(p) && p >= 1) page.value = p
  }
  if (typeof q.page_size === 'string') {
    const ps = Number(q.page_size)
    if (Number.isFinite(ps) && ps >= 1 && ps <= 200) pageSize.value = ps
  }
  const hasRefreshSecInQuery = typeof q.refresh_sec === 'string'
  const hasAutoRefreshInQuery = typeof q.auto_refresh === 'string'
  if (hasRefreshSecInQuery) {
    const sec = Number(q.refresh_sec)
    if (sec === 10 || sec === 30) autoRefreshSeconds.value = sec
  }
  if (hasAutoRefreshInQuery && q.auto_refresh === '1') {
    autoRefreshEnabled.value = true
    if (!query.date_range) setTimeWindowMinutes(15)
    startAutoRefresh()
  } else if (!hasRefreshSecInQuery && !hasAutoRefreshInQuery) {
    const savedSec = Number(localStorage.getItem(AUTO_REFRESH_SECONDS_KEY) || '')
    if (savedSec === 10 || savedSec === 30) autoRefreshSeconds.value = savedSec
    const savedEnabled = localStorage.getItem(AUTO_REFRESH_ENABLED_KEY)
    if (savedEnabled === '1') {
      autoRefreshEnabled.value = true
      if (!query.date_range) setTimeWindowMinutes(15)
      startAutoRefresh()
    }
  }
  await search(true)
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('online', onNetworkOnline)
  window.removeEventListener('offline', onNetworkOffline)
  stopAutoRefresh()
  stopNowTicker()
})
</script>

<style scoped>
:deep(.audit-group-divider td) {
  border-top: 2px solid var(--el-border-color-light);
}

.audit-detail-block {
  margin-top: 12px;
}

.audit-detail-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}
</style>
