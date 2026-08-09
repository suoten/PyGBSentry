<template>
  <div class="app-page">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('ops.title')" :description="t('ops.description')">  <!-- FIXED: 硬编码中文→t() -->
          <template #actions>
            <el-button size="small" type="success" plain @click="exportDiagnostics" :loading="exporting">{{ t('ops.exportDiagnostics') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
            <el-button size="small" type="primary" plain @click="runDiagnose" :loading="diagnoseLoading">{{ t('ops.onlineDiagnose') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
            <el-button size="small" type="danger" plain @click="shutdownService">{{ t('ops.shutdownService') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
          </template>
        </PageHeader>
      </template>
      <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('ops.systemStatus')" name="status">  <!-- FIXED: 硬编码中文→t() -->
        <div class="grid grid-cols-2 gap-4">
          <el-card class="col-span-2 md:col-span-1">
            <template #header>
              <div class="flex justify-between items-center">
                <span class="font-semibold">{{ t('ops.systemStatus') }}</span>  <!-- FIXED: 硬编码中文→t() -->
              </div>
            </template>
            <div class="grid grid-cols-2 gap-4" v-loading="loading">
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">{{ t('ops.cpuUsage') }}</div>  <!-- FIXED: 硬编码中文→t() -->
                <div class="text-2xl font-bold ops-kpi-value">{{ status.cpu }}%</div>
                <el-progress :percentage="status.cpu" :status="status.cpu > 80 ? 'exception' : ''" />
              </div>
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">{{ t('ops.memoryUsage') }}</div>  <!-- FIXED: 硬编码中文→t() -->
                <div class="text-2xl font-bold ops-kpi-value">{{ status.memory_percent }}%</div>
                <el-progress :percentage="status.memory_percent" :status="status.memory_percent > 80 ? 'exception' : ''" />
              </div>
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">{{ t('ops.mediaService') }}</div>  <!-- FIXED: 硬编码中文→t() -->
                <div class="text-2xl font-bold" :style="{ color: status.zlm_status === 'Online' ? 'var(--el-color-success)' : 'var(--el-color-danger)' }">
                  {{ status.zlm_status === 'Online' ? t('ops.online') : t('ops.offline') }}  <!-- FIXED: 硬编码中文→t() -->
                </div>
                <div class="text-xs mt-1 ops-muted">
                  {{ t('ops.source') }}：{{ status.zlm_select_reason_label || status.zlm_select_reason || t('ops.useGlobalConfig') }}
                  <span v-if="status.zlm_node_id">（{{ status.zlm_node_id }}）</span>
                </div>
                <div class="text-xs ops-muted">
                  {{ t('ops.target') }}：{{ status.zlm_target || '-' }}
                </div>
                <div v-if="status.zlm_status !== 'Online' && status.zlm_error" class="text-xs mt-1 ops-danger-break">
                  {{ t('common.error') }}：{{ status.zlm_error }}
                </div>
              </div>
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">{{ t('ops.currentStreams') }}</div>
                <div class="text-2xl font-bold" style="color: var(--el-color-warning)">{{ status.zlm_streams }}</div>
              </div>
            </div>
          </el-card>
          <el-card class="col-span-2 md:col-span-1 flex flex-col h-[500px]">
            <template #header>
              <div class="flex justify-between items-center">
                <div class="font-semibold flex items-center gap-2">
                  <span>{{ t('ops.realtimeLogs') }}</span>
                  <el-input v-model="logContains" size="small" :placeholder="t('ops.containsKeywords')" clearable class="ops-input-240" />
                  <el-input v-model="logContainsAny" size="small" :placeholder="t('ops.anyKeyword')" clearable class="ops-input-220" />
                  <el-button size="small" @click="applyLogFilter">{{ t('ops.applyFilter') }}</el-button>
                  <el-button size="small" type="primary" plain @click="openHistoricalLogs">{{ t('ops.historicalLogs') }}</el-button>
                </div>
                <div class="flex items-center gap-2">
                  <el-tag type="success" v-if="wsConnected">{{ t('ops.connected') }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
                  <el-tag type="warning" v-else-if="wsReconnecting">{{ t('ops.reconnecting') }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
                  <el-tag type="danger" v-else>{{ t('ops.disconnected') }}</el-tag>  <!-- FIXED: 硬编码中文→t() -->
                </div>
              </div>
            </template>
            <div
              ref="logContainer"
              class="ops-log-box flex-grow font-mono text-xs p-3 overflow-y-auto h-full"
            >
              <div v-for="(log, index) in logs" :key="index" class="mb-1 break-words">
                {{ log }}
              </div>
            </div>
          </el-card>
        </div>
        <AppDialog v-model="diagnoseVisible" :title="t('ops.diagnoseReport')" size="medium">  <!-- FIXED: 硬编码中文→t() -->
          <div class="space-y-3 text-sm">
            <div class="flex items-center gap-2">
              <el-tag :type="diagnoseSummaryTag" effect="plain">
                {{ t('ops.overallStatus') }}：{{ diagnoseSummaryLabel }}
              </el-tag>
              <span class="ops-muted">{{ t('ops.generateTime') }}：{{ diagnoseGeneratedAt || '-' }}</span>
            </div>
            <el-divider />
            <div class="space-y-2">
              <p
                v-for="(line, i) in diagnoseLines"
                :key="i"
                :style="{ color: line.ok ? 'var(--el-text-color-regular)' : (line.level === 'error' ? 'var(--el-color-danger)' : 'var(--el-color-warning)') }"
              >
                {{ line.ok ? '✓' : (line.level === 'error' ? '✗' : '○') }} {{ line.text }}
              </p>
            </div>
          </div>
          <template #footer>
            <el-button @click="exportDiagnoseReport">{{ t('ops.exportReport') }}</el-button>
            <el-button @click="diagnoseVisible = false">{{ t('common.close') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
          </template>
        </AppDialog>

        <AppDialog v-model="historyLogsVisible" :title="t('ops.historicalLogs')" size="large">  <!-- FIXED: 硬编码中文→t() -->
          <el-table :data="historyLogFiles" v-loading="historyLogsLoading" border size="small">
            <el-table-column prop="name" :label="t('ops.fileName')" min-width="200" />  <!-- FIXED: 硬编码中文→t() -->
            <el-table-column :label="t('ops.size')" width="120">  <!-- FIXED: 硬编码中文→t() -->
              <template #default="{ row }">
                {{ (row.size / 1024 / 1024).toFixed(2) }} MB
              </template>
            </el-table-column>
            <el-table-column :label="t('ops.modifiedTime')" width="180">  <!-- FIXED: 硬编码中文→t() -->
              <template #default="{ row }">
                {{ (() => { const ts = Number(row.mtime); if (!Number.isFinite(ts)) return '-'; const d = new Date(ts * 1000); return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString() })() }}
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action')" width="200" fixed="right">  <!-- FIXED: 硬编码中文→t() -->
              <template #default="{ row }">
                <el-button link type="primary" @click="viewLogLines(row)">{{ t('ops.onlinePreview') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
                <el-button link type="primary" @click="downloadLog(row)">{{ t('ops.downloadFile') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
              </template>
            </el-table-column>
          </el-table>
          <template #footer>
            <el-button @click="historyLogsVisible = false">{{ t('common.close') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
          </template>
        </AppDialog>

        <AppDialog v-model="logViewerVisible" :title="`${t('ops.viewLog')}: ${currentLogFile}`" size="large">  <!-- FIXED: 硬编码中文→t() -->
          <div class="flex gap-2 mb-3">
            <el-input v-model="logSearchKeyword" :placeholder="t('ops.keywordFilter')" clearable @keyup.enter="fetchLogLines" class="ops-input-300" />  <!-- FIXED: 硬编码中文→t() -->
            <el-button type="primary" @click="fetchLogLines">{{ t('common.search') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
            <el-button @click="downloadLog({name: currentLogFile})">{{ t('ops.downloadOriginal') }}</el-button>  <!-- FIXED: 硬编码中文→t() -->
          </div>
          <div
            class="ops-log-box ops-log-box--dialog font-mono text-xs p-3 overflow-y-auto"
            v-loading="logLinesLoading"
            element-loading-background="rgba(0, 0, 0, 0.6)"
          >
            <div v-if="currentLogLines.length === 0 && !logLinesLoading" class="text-slate-500 text-center mt-4">{{ t('ops.noMatchingLogs') }}</div>  <!-- FIXED: 硬编码中文→t() -->
            <div v-for="(line, index) in currentLogLines" :key="index" class="mb-1 break-words whitespace-pre-wrap">
              {{ line }}
            </div>
          </div>
          <div class="flex justify-end mt-3">
            <el-pagination
              v-model:current-page="logCurrentPage"
              v-model:page-size="logPageSize"
              :total="logTotal"
              :page-sizes="[100, 500, 1000, 2000]"
              layout="total, sizes, prev, pager, next"
              @size-change="fetchLogLines"
              @current-change="fetchLogLines"
            />
          </div>
        </AppDialog>

      </el-tab-pane>

      <el-tab-pane :label="t('ops.sipTrace')" name="trace">  <!-- FIXED: 硬编码中文→t() -->
        <el-card shadow="never">
          <div class="flex flex-wrap items-center gap-2 mb-3">
            <el-input v-model="traceForm.platform_id" :placeholder="t('ops.platformId')" class="ops-input-220" clearable />
            <el-input v-model="traceForm.trace_id" :placeholder="t('ops.traceId')" class="ops-input-260" clearable />
            <el-input v-model="traceForm.event" :placeholder="t('ops.eventType')" class="ops-input-220" clearable />
            <el-input-number v-model="traceForm.limit" :min="1" :max="500" />
            <el-button type="primary" @click="loadTraceEvents" :loading="traceLoading">{{ t('common.query') }}</el-button>
            <el-button @click="clearTrace">{{ t('ops.clearFilter') }}</el-button>
            <el-popover placement="bottom-end" :width="220" trigger="click">
              <template #reference>
                <el-button plain>{{ t('ops.fieldDisplay') }}</el-button>
              </template>
              <el-checkbox-group v-model="visibleTraceColumns" class="grid grid-cols-2 gap-x-3 gap-y-2">
                <el-checkbox v-for="col in traceColumnOptions" :key="col.key" :label="col.key">
                  {{ col.label }}
                </el-checkbox>
              </el-checkbox-group>
              <div class="mt-3 flex justify-end">
                <el-button size="small" text @click="resetTraceColumns">{{ t('ops.restoreDefault') }}</el-button>
              </div>
            </el-popover>
          </div>
          <el-table :data="paginatedTraceRows" border size="small" v-loading="traceLoading" :empty-text="t('ops.noEvents')">
            <el-table-column prop="created_at" :label="t('common.time')" width="190" />
            <el-table-column prop="event" :label="t('common.event')" width="200" />
            <el-table-column prop="trace_id" :label="t('ops.traceIdLabel')" min-width="240" show-overflow-tooltip />
            <el-table-column v-if="isTraceColumnVisible('platform_id')" prop="platform_id" :label="t('common.platform')" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="isTraceColumnVisible('device_id')" prop="device_id" :label="t('common.device')" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="isTraceColumnVisible('channel_id')" prop="channel_id" :label="t('common.channel')" min-width="180" show-overflow-tooltip />
            <el-table-column :label="t('ops.payload')" min-width="360" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="font-mono text-xs">{{ row.payload }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="flex justify-end mt-4 pagination-wrapper" v-if="traceRows.length > 0">
            <el-pagination
              v-model:current-page="tracePage"
              v-model:page-size="tracePageSize"
              :total="traceRows.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
              :prev-text="t('pagination.prev')"
              :next-text="t('pagination.next')"
              size="small"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.mediaNodes')" name="media">
        <el-card shadow="never">
          <div class="mb-3">
            <el-button type="primary" @click="openMediaDialog()">{{ t('ops.addMediaNode') }}</el-button>
            <el-button class="ml-2" @click="copyMediaNodesJson">{{ t('ops.copyMediaNodesConfig') }}</el-button>
            <el-button class="ml-2" @click="copyMediaNodesEnv">{{ t('ops.copyEnvConfig') }}</el-button>
            <el-button class="ml-2" @click="openLeaseDialog()">{{ t('ops.viewLeases') }}</el-button>
            <el-button class="ml-2" type="warning" plain @click="openLeaseCleanupDialog()">{{ t('ops.cleanupOrphanLeases') }}</el-button>
            <el-button class="ml-2" :loading="testingAllMediaNodes" @click="testAllMediaNodes">{{ t('ops.batchTest') }}</el-button>
            <el-button class="ml-2" @click="showPortPoolStatus">{{ t('ops.portPoolStatus') }}</el-button>
            <el-button class="ml-2" @click="showFfmpegCmds">{{ t('ops.ffmpegCommands') }}</el-button>
            <el-switch class="ml-4" v-model="mediaAutoRefresh" :active-text="t('ops.autoRefresh')" />
            <el-tag v-if="mediaAutoRefreshError" class="ml-2" type="warning" effect="plain">
              {{ t('ops.refreshFailed') }}
            </el-tag>
            <span class="ml-2 text-xs" style="color: var(--el-text-color-secondary)">{{ t('ops.interval') }}</span>
            <el-input-number class="ml-2" v-model="mediaRefreshIntervalSec" :min="3" :max="300" size="small" />
            <span class="ml-1 text-xs" style="color: var(--el-text-color-secondary)">{{ t('ops.secondsUnit') }}</span>
            <span class="ml-4 text-xs" style="color: var(--el-text-color-secondary)">{{ t('ops.offlineThresholdSeconds') }}</span>
            <el-input-number class="ml-2" v-model="mediaOfflineSeconds" :min="10" :max="86400" size="small" />
            <el-button class="ml-2" size="small" :loading="savingMediaOfflineSeconds" @click="saveMediaOfflineSeconds">{{ t('common.save') }}</el-button>
          </div>
          <el-table :data="paginatedMediaNodes" border :empty-text="t('ops.noMediaNodes')" fit>
            <el-table-column prop="ip" label="IP">
              <template #default="{ row }">
                <div class="flex items-center gap-2">
                  <span class="font-mono">{{ row.ip || '-' }}</span>
                  <el-tag v-if="row.is_active" type="success" effect="plain" size="small">{{ t('ops.active') }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="public_ip" :label="t('ops.publicIp')" />
            <el-table-column :label="t('ops.externalAccess')" min-width="220">
              <template #default="{ row }">
                <span class="font-mono text-xs" :title="`${row.computed_public_host || ''}:${row.computed_public_http_port || ''}`">
                  {{ (row.computed_public_host || '-') + ':' + (row.computed_public_http_port || '-') }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="computed_hook_base_url" :label="t('ops.hookCallback')" min-width="260">
              <template #default="{ row }">
                <span
                  class="truncate block ops-hook-url"
                  :title="row.computed_hook_base_url || ''"
                >
                  {{ row.computed_hook_base_url || '-' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column :label="t('ops.rtpPort')" min-width="180">
              <template #default="{ row }">
                <span v-if="row.rtp_port_mode === 'range'">
                  {{ row.rtp_port_range_start }} - {{ row.rtp_port_range_end }}
                </span>
                <span v-else>
                  {{ row.rtp_proxy_port }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="http_port" :label="t('ops.httpPortLabel')" width="100" />
            <el-table-column label="ZLM SSL" width="88">
              <template #default="{ row }">
                <el-tag v-if="row.is_embedded && row.zlm_ssl_configured" type="success" size="small">{{ t('ops.configured') }}</el-tag>
                <span v-else-if="row.is_embedded" class="text-xs ops-muted">—</span>
                <span v-else class="text-xs ops-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="rtsp_port" :label="t('ops.rtspPort')" width="100" />
            <el-table-column prop="rtmp_port" :label="t('ops.rtmpPort')" width="100" />
            <el-table-column :label="t('common.status')" width="100">
              <template #default="{ row }">
                <div class="flex flex-col items-start gap-1">
                  <el-tag size="small" :type="row.is_online ? 'success' : 'danger'">{{ row.is_online ? t('ops.online') : t('ops.offline') }}</el-tag>
                  <el-tooltip
                    v-if="!row.is_online && row.last_probe_error"
                    :content="row.last_probe_error"
                    placement="top"
                  >
                    <span class="text-xs ops-danger-help">{{ t('ops.offlineReason') }}</span>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('ops.lastHeartbeat')" min-width="160">
              <template #default="{ row }">
                <span class="text-xs ops-muted" :title="row.last_seen_at || ''">
                  {{ formatLastSeen(row.last_seen_at) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column :label="t('ops.lastProbeError')" min-width="220">
              <template #default="{ row }">
                <span
                  class="text-xs"
                  :style="{ color: row.last_probe_error ? 'var(--el-color-danger)' : 'var(--el-text-color-secondary)' }"
                  :title="row.last_probe_error || ''"
                >
                  {{ row.last_probe_error || '-' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action')" width="260">
              <template #default="{ row }">
                <div class="table-action-inline">
                  <el-button size="small" @click="openMediaDialog(row)">{{ t('common.edit') }}</el-button>
                  <el-button size="small" @click="testMediaNode(row.id)">{{ t('ops.test') }}</el-button>
                  <el-dropdown trigger="click" @command="(cmd: string) => handleMediaMoreCommand(row, cmd)">
                    <el-button size="small" plain class="table-action-more">
                      {{ t('common.more') }}
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="lease">{{ t('ops.lease') }}</el-dropdown-item>
                        <el-dropdown-item command="copyHook">{{ t('ops.copyHook') }}</el-dropdown-item>
                        <el-dropdown-item command="copyZlm">{{ t('ops.copyZlmSnippet') }}</el-dropdown-item>
                        <el-dropdown-item command="activate" :disabled="row.is_active">{{ t('ops.setActive') }}</el-dropdown-item>
                        <el-dropdown-item command="delete" divided>{{ t('common.delete') }}</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div class="flex justify-end mt-4 pagination-wrapper" v-if="mediaNodes.length > 0">
            <el-pagination
              v-model:current-page="mediaPage"
              v-model:page-size="mediaPageSize"
              :total="mediaNodes.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
              :prev-text="t('pagination.prev')"
              :next-text="t('pagination.next')"
              size="small"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.cascadeDiag')" name="cascade_diagnosis">
        <el-card shadow="never">
          <div class="flex flex-wrap items-center gap-2 mb-4">
            <el-button type="primary" @click="loadCascadeDiagnosis" :loading="cascadeLoading">
              {{ cascadeLoading ? t('ops.diagnosing') : t('ops.oneClickDiagnose') }}
            </el-button>
            <span class="text-xs" style="color:var(--el-text-color-secondary)">{{ t('ops.cascadeDiagnosisDesc') }}</span>
          </div>

          <template v-if="cascadeDiagnosis.diagnostics || cascadeDiagnosis.inbound_platforms">
            <!-- 总体健康状态 -->
            <div class="cascade-health-banner mb-4" :class="cascadeOverallClass">
              <div class="cascade-health-icon">{{ cascadeOverallIcon }}</div>
              <div>
                <div class="cascade-health-title">{{ cascadeOverallTitle }}</div>
                <div class="cascade-health-desc">{{ cascadeOverallDesc }}</div>
              </div>
            </div>

            <!-- 本端 SIP 配置（给下级平台填的） -->
            <el-collapse class="mb-4">
              <el-collapse-item :title="t('ops.localSipConfig')" name="sip_config">
                <div class="grid grid-cols-2 gap-3 text-sm">
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">{{ t('ops.gbIdSipId') }}</div>
                    <code class="text-sm font-semibold">{{ cascadeSipConfig.sip_id || '—' }}</code>
                  </div>
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">{{ t('ops.realm') }}</div>
                    <code class="text-sm font-semibold">{{ cascadeSipConfig.sip_domain || '—' }}</code>
                  </div>
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">{{ t('ops.sipServerAddress') }}</div>
                    <code class="text-sm font-semibold">{{ cascadeSipConfig.sip_ip || '—' }}:{{ cascadeSipConfig.sip_port || '—' }}</code>
                  </div>
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">{{ t('ops.transportMode') }}</div>
                    <code class="text-sm font-semibold">UDP</code>
                  </div>
                </div>
                <div class="mt-2 text-xs" style="color:var(--el-color-primary)">
                  {{ t('ops.sipConfigHint') }}
                </div>
              </el-collapse-item>
            </el-collapse>

            <!-- 注册流程步骤条 -->
            <div class="mb-4">
              <div class="text-sm font-semibold mb-3">{{ t('ops.registerFlowCheck') }}</div>
              <el-steps :active="cascadeStepActive" finish-status="success" :process-status="cascadeStepProcessStatus" align-center>
                <el-step :title="t('ops.stepReceiveRegister')" :description="cascadeStep1Desc" />
                <el-step :title="t('ops.stepAuthVerify')" :description="cascadeStep2Desc" />
                <el-step :title="t('ops.stepRegisterSuccess')" :description="cascadeStep3Desc" />
                <el-step :title="t('ops.stepKeepalive')" :description="cascadeStep4Desc" />
              </el-steps>
            </div>

            <!-- 入站平台列表（人话版） -->
            <div v-if="(cascadeDiagnosis.inbound_platforms || []).length > 0" class="mb-4">
              <div class="text-sm font-semibold mb-2">{{ t('ops.connectedDownstreamPlatforms') }}</div>
              <div class="space-y-2">
                <div v-for="p in cascadeDiagnosis.inbound_platforms" :key="p.platform_id" class="p-3 rounded border" style="border-color:var(--el-border-color-lighter)">
                  <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2">
                      <el-tag :type="p.register?.last_ok_at ? 'success' : 'danger'" size="small" effect="dark">
                        {{ p.register?.last_ok_at ? t('ops.registered') : t('ops.unregistered') }}
                      </el-tag>
                      <span class="font-medium text-sm">{{ p.register?.last_gb_id || p.platform_id || t('common.unknown') }}</span>
                    </div>
                    <el-tag v-if="p.keepalive?.last_at" type="success" size="small">{{ t('ops.heartbeatNormal') }}</el-tag>
                    <el-tag v-else type="info" size="small">{{ t('ops.noHeartbeat') }}</el-tag>
                  </div>
                  <div class="grid grid-cols-3 gap-2 text-xs" style="color:var(--el-text-color-secondary)">
                    <div>{{ t('ops.sourceAddress') }}：{{ p.register?.last_addr || '—' }}</div>
                    <div>{{ t('ops.transportMode') }}：{{ p.register?.last_transport || '—' }}</div>
                    <div>{{ t('ops.authMethod') }}：{{ cascadeAuthLabel(p.register?.auth) }}</div>
                    <div>{{ t('ops.registerTime') }}：{{ p.register?.last_ok_at || '—' }}</div>
                    <div>{{ t('ops.recentHeartbeat') }}：{{ p.keepalive?.last_at || '—' }}</div>
                    <div>{{ t('ops.heartbeatSource') }}：{{ p.keepalive?.last_addr || '—' }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 诊断结论（卡片式，人话版） -->
            <div v-if="cascadeDiagnosis.diagnostics?.length > 0" class="mb-4">
              <div class="text-sm font-semibold mb-2">{{ t('ops.diagResult') }}</div>
              <div class="space-y-2">
                <div v-for="d in cascadeDiagnosis.diagnostics" :key="d.key" class="p-3 rounded" :style="{
                    background: d.level === 'error' ? 'var(--el-color-danger-light-9)' : d.level === 'warn' ? 'var(--el-color-warning-light-9)' : 'var(--el-color-success-light-9)',
                    border: '1px solid ' + (d.level === 'error' ? 'var(--el-color-danger-light-5)' : d.level === 'warn' ? 'var(--el-color-warning-light-5)' : 'var(--el-color-success-light-5)')
                  }">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="text-lg">{{ d.level === 'error' ? '🔴' : d.level === 'warn' ? '🟡' : '🟢' }}</span>
                    <span class="text-sm font-medium">{{ d.title }}</span>
                  </div>
                  <div class="text-xs mb-2" style="color: var(--el-text-color-regular)">{{ d.detail }}</div>
                  <div class="text-xs p-2 rounded" style="background:var(--el-fill-color); color: var(--el-color-primary)">
                    <strong>{{ t('ops.howToFix') }}</strong>{{ d.suggestion }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 高级详情（默认折叠） -->
            <el-collapse>
              <el-collapse-item :title="t('ops.advancedDetails')" name="advanced">
                <!-- SIP 事件统计 -->
                <div class="mb-3">
                  <div class="text-xs font-semibold mb-2" style="color:var(--el-text-color-secondary)">{{ t('ops.sipEventStats') }}</div>
                  <div class="flex gap-2 flex-wrap">
                    <el-tag type="info" size="small">{{ t('ops.receivedRegister') }}: {{ cascadeDiagnosis.recent_trace_events_count?.register_received || 0 }}</el-tag>
                    <el-tag type="warning" size="small">{{ t('ops.sent401Challenge') }}: {{ cascadeDiagnosis.recent_trace_events_count?.register_401_challenge || 0 }}</el-tag>
                    <el-tag type="success" size="small">{{ t('ops.platformRegisterOk') }}: {{ cascadeDiagnosis.recent_trace_events_count?.register_ok_platform || 0 }}</el-tag>
                    <el-tag type="success" size="small">{{ t('ops.deviceRegisterOk') }}: {{ cascadeDiagnosis.recent_trace_events_count?.register_ok_device || 0 }}</el-tag>
                    <el-tag type="danger" size="small">{{ t('ops.authFailed') }}: {{ cascadeDiagnosis.recent_trace_events_count?.register_auth_failed || 0 }}</el-tag>
                  </div>
                </div>
                <!-- 事件详情 -->
                <div v-if="cascadeDiagnosis.recent_trace_by_trace_id && Object.keys(cascadeDiagnosis.recent_trace_by_trace_id).length > 0">
                  <div class="text-xs font-semibold mb-2" style="color:var(--el-text-color-secondary)">{{ t('ops.recentRegisterEvents') }}</div>
                  <div v-for="(events, tid) in cascadeDiagnosis.recent_trace_by_trace_id" :key="tid" class="mb-2 p-2 rounded" style="background: var(--el-fill-color-lighter); border: 1px solid var(--el-border-color-lighter);">
                    <div class="text-xs font-mono mb-1" style="color: var(--el-text-color-secondary)">{{ t('ops.session') }}: {{ tid }}</div>
                    <div v-for="evt in events" :key="evt.created_at" class="flex items-center gap-2 text-xs mb-0.5">
                      <el-tag :type="cascadeEventTagType(evt.event)" size="small">{{ cascadeEventLabel(evt.event) }}</el-tag>
                      <span style="color: var(--el-text-color-secondary)">{{ evt.created_at }}</span>
                      <span v-if="evt.payload?.reason" style="color: var(--el-color-danger)">{{ t('ops.reason') }}: {{ evt.payload.reason }}</span>
                    </div>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </template>

          <div v-else-if="!cascadeLoading" class="text-center py-8" style="color:var(--el-text-color-secondary)">
            <div class="text-4xl mb-3">🔍</div>
            <div class="text-sm mb-3">{{ t('ops.clickToDiagnose') }}</div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.streamDiag')" name="stream_diagnosis">
        <el-card shadow="never">
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <el-select v-model="diagNodeId" :placeholder="t('ops.selectMediaNode')" clearable class="ops-diag-node-select" @change="diagResults = []">
              <el-option v-for="n in mediaNodes" :key="n.id" :label="`${n.ip || n.id}${n.is_embedded ? t('ops.embeddedBracket') : ''}`" :value="n.id || ''" />
            </el-select>
            <el-select
              v-model="diagChannelId"
              :placeholder="t('ops.selectChannelDiag')"
              clearable filterable default-first-option
              class="ops-diag-channel-input"
              :loading="diagChannelLoading"
              :disabled="diagChannelLoading"
            >
              <el-option
                v-for="s in diagActiveStreams"
                :key="s.stream"
                :label="s.name || s.stream"
                :value="s.stream"
              >
                <div class="flex items-center justify-between w-full">
                  <span class="font-medium truncate" style="max-width: 200px;">{{ s.name || s.stream }}</span>
                  <span class="text-xs ml-2 shrink-0" style="color: var(--el-text-color-secondary);">
                    {{ s.stream }} &nbsp; {{ s.readerCount > 0 ? `🔴 ${t('ops.viewersWatching', { count: s.readerCount })}` : `⚪ ${s.aliveSecond}s` }}
                  </span>
                </div>
              </el-option>
            </el-select>
            <el-button type="primary" plain bg @click="runStreamDiagnose" :loading="diagLoading" size="default">{{ t('ops.startDiagnose') }}</el-button>
            <el-button @click="diagResults = []" size="default">{{ t('common.clear') }}</el-button>
          </div>

          <div v-if="diagResults.length > 0" class="space-y-3">
            <div class="flex justify-between items-center mb-3">
              <div class="flex items-center gap-3">
                <el-tag :type="diagOverallOk ? 'success' : 'danger'" size="large" effect="plain">
                  {{ diagOverallOk ? t('ops.diagPassed') : t('ops.foundIssues') }}
                </el-tag>
                <span v-if="diagChannelName && diagChannelName !== diagChannelId" class="text-sm" style="color: var(--el-text-color-secondary)">
                  {{ t('common.channel') }}：{{ diagChannelName }}
                </span>
              </div>
              <el-button size="small" @click="exportDiagReport">{{ t('ops.exportReport') }}</el-button>
            </div>
            <div v-for="group in diagGroupedResults" :key="group.step" class="border rounded p-4">
              <div class="flex items-center gap-2 mb-3">
                <el-tag :type="group.ok ? 'success' : 'danger'" size="small">{{ group.ok ? t('ops.passed') : t('ops.failed') }}</el-tag>
                <span class="font-semibold text-sm">{{ group.label }}</span>
              </div>
              <div v-for="item in group.items" :key="item.key" class="flex items-start gap-3 mb-2 text-sm">
                  <el-icon class="mt-0.5 flex-shrink-0" :color="item.ok ? 'var(--el-color-success)' : 'var(--el-color-danger)'">
                    <CircleCheckFilled v-if="item.ok" />
                    <CircleCloseFilled v-else />
                </el-icon>
                <div class="flex-1">
                  <div :style="{ color: item.ok ? 'var(--el-text-color-regular)' : 'var(--el-color-danger)' }">{{ item.title }}</div>
                  <div v-if="item.detail" class="text-xs mt-0.5 font-mono" style="color: var(--el-text-color-secondary)">{{ item.detail }}</div>
                  <div v-if="item.suggestion" class="text-xs mt-1" style="color: var(--el-color-primary)">{{ item.suggestion }}</div>
                </div>
              </div>
            </div>
          </div>

          <el-empty v-else-if="!diagLoading" :description="t('ops.streamDiagEmpty')" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.backupRestore')" name="backup">
        <el-card>
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-semibold">{{ t('ops.dbBackupRestore') }}</span>
              <div class="flex gap-2">
                <el-button type="primary" :loading="backupLoading" @click="createBackup">{{ t('ops.createBackup') }}</el-button>
                <el-button @click="loadBackupList" :loading="backupListLoading">{{ t('ops.refreshList') }}</el-button>
              </div>
            </div>
          </template>
          <el-alert type="warning" :closable="false" class="mb-4" show-icon>
            <template #title>
              {{ t('ops.restoreWarn') }}
            </template>
          </el-alert>
          <el-table :data="backupList" v-loading="backupListLoading" stripe :empty-text="t('ops.noBackups')">
            <el-table-column prop="filename" :label="t('ops.fileName')" min-width="280" />
            <el-table-column :label="t('common.size')" width="120">
              <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
            </el-table-column>
            <el-table-column prop="created_at" :label="t('common.createTime')" width="200" />
            <el-table-column :label="t('common.action')" width="160" fixed="right">
              <template #default="{ row }">
                <el-popconfirm
                  :title="t('ops.restoreConfirmTitle', { filename: row.filename })"
                  :confirm-button-text="t('ops.restore')"
                  :cancel-button-text="t('common.cancel')"
                  confirm-button-type="danger"
                  @confirm="restoreBackup(row.filename)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" link>{{ t('ops.restore') }}</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.rtpReceive')" name="rtp">
        <el-card>
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-semibold">{{ t('ops.rtpManage') }}</span>
              <el-button @click="loadRtpTasks" :loading="rtpLoading">{{ t('ops.refreshList') }}</el-button>
            </div>
          </template>
          <el-alert type="info" :closable="false" class="mb-4" show-icon>
            <template #title>{{ t('ops.rtpOpenHint') }}</template>
          </el-alert>
          <div class="mb-4">
            <el-button type="primary" @click="rtpOpenDialogVisible = true">{{ t('ops.openRtpReceive') }}</el-button>
          </div>
          <el-table :data="rtpTasks" v-loading="rtpLoading" stripe :empty-text="t('ops.noRtpTasks')">
            <el-table-column prop="task_id" :label="t('ops.taskId')" min-width="200" show-overflow-tooltip />
            <el-table-column prop="stream_id" :label="t('ops.streamIdLabel')" min-width="180" show-overflow-tooltip />
            <el-table-column prop="app" :label="t('ops.appId')" width="100" />
            <el-table-column prop="port" :label="t('ops.portLabel')" width="100" />
            <el-table-column prop="tcp_mode" :label="t('ops.tcpMode')" width="100">
              <template #default="{ row }">{{ ({ 0: 'UDP', 1: t('ops.tcpPassive'), 2: t('ops.tcpActive') } as Record<number, string>)[row.tcp_mode as number] || row.tcp_mode }}</template>
            </el-table-column>
            <el-table-column prop="status" :label="t('common.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : row.status === 'closed' ? 'info' : 'danger'" size="small">{{ ({ running: t('common.running'), closed: t('ops.closed'), failed: t('ops.failed') } as Record<string, string>)[row.status as string] || row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_error" :label="t('ops.errorInfo')" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.last_error || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('common.action')" width="120" fixed="right">
              <template #default="{ row }">
                <el-popconfirm v-if="row.status === 'running'" :title="t('ops.closeRtpConfirm', { streamId: row.stream_id })" @confirm="closeRtpTask(row.task_id)">
                  <template #reference>
                    <el-button type="danger" size="small" link>{{ t('common.close') }}</el-button>
                  </template>
                </el-popconfirm>
                <span v-else class="text-xs ops-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.sslCert')" name="ssl">
        <el-card>
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-semibold">{{ t('ops.sslCertManage') }}</span>
              <div class="flex gap-2">
                <el-button @click="loadSslStatus" :loading="sslLoading">{{ t('ops.refreshStatus') }}</el-button>
                <el-button type="primary" :loading="sslRenewing" @click="renewSslCert">{{ t('ops.renewCert') }}</el-button>
              </div>
            </div>
          </template>
          <div v-if="sslStatus" v-loading="sslLoading">
            <div class="grid grid-cols-2 gap-4 mb-4">
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">{{ t('ops.enableStatus') }}</div>
                <div class="text-xl font-bold" :style="{ color: sslStatus.enabled ? 'var(--el-color-success)' : 'var(--el-text-color-secondary)' }">
                  {{ sslStatus.enabled ? t('ops.enabled') : t('ops.notEnabled') }}
                </div>
              </div>
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">{{ t('ops.certStatus') }}</div>
                <div class="text-xl font-bold" :style="{ color: sslStatus.status === 'valid' ? 'var(--el-color-success)' : sslStatus.status === 'expired' ? 'var(--el-color-danger)' : 'var(--el-color-warning)' }">
                  {{ { valid: t('ops.valid'), expired: t('ops.expired'), disabled: t('ops.notEnabled'), renewing: t('ops.renewing') }[sslStatus.status] || sslStatus.status || '—' }}
                </div>
              </div>
            </div>
            <el-descriptions :column="2" border size="small" v-if="sslStatus.enabled">
              <el-descriptions-item :label="t('ops.domain')">{{ sslStatus.domain || '—' }}</el-descriptions-item>
              <el-descriptions-item :label="t('ops.remainingDays')">
                <span :style="{ color: (sslStatus.remaining_days ?? 0) < 30 ? 'var(--el-color-danger)' : 'var(--el-color-success)' }">
                  {{ sslStatus.remaining_days != null ? t('ops.days', { count: sslStatus.remaining_days }) : '—' }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item :label="t('ops.effectiveTime')">{{ sslStatus.not_before || '—' }}</el-descriptions-item>
              <el-descriptions-item :label="t('ops.expireTime')">{{ sslStatus.not_after || '—' }}</el-descriptions-item>
              <el-descriptions-item :label="t('ops.certPath')">{{ sslStatus.cert_path || '—' }}</el-descriptions-item>
              <el-descriptions-item :label="t('ops.lastRenew')">{{ sslStatus.last_renew_at || '—' }}</el-descriptions-item>
              <el-descriptions-item :label="t('ops.lastCheck')">{{ sslStatus.last_check_at || '—' }}</el-descriptions-item>
              <el-descriptions-item :label="t('ops.errorInfo')">
                <span v-if="sslStatus.error" style="color: var(--el-color-danger)">{{ sslStatus.error }}</span>
                <span v-else>—</span>
              </el-descriptions-item>
            </el-descriptions>
            <el-empty v-else :description="t('ops.sslNotEnabledHint')" />
          </div>
          <el-empty v-else-if="!sslLoading" :description="t('ops.sslEmptyHint')" />
        </el-card>
      </el-tab-pane>

      </el-tabs>
    </PageContainer>

    <AppDialog v-model="mediaDialogVisible" :title="editingMediaId ? t('ops.editMediaNode') : t('ops.newMediaNode')" size="large">
      <el-form :model="mediaForm" ref="mediaFormRef" :rules="mediaRules" label-width="120px">
        <el-form-item :label="t('common.ip')" prop="ip"><el-input v-model="mediaForm.ip" :placeholder="t('ops.nodeInternalIp')" /></el-form-item>
        <el-form-item :label="t('ops.publicIp')" prop="public_ip"><el-input v-model="mediaForm.public_ip" :placeholder="t('ops.nodePublicIp')" /></el-form-item>
        <el-form-item :label="t('ops.streamIpDomain')" prop="stream_ip"><el-input v-model="mediaForm.stream_ip" :placeholder="t('ops.streamDomain')" /></el-form-item>

        <el-form-item :label="t('ops.httpPortLabel')" prop="http_port"><el-input-number v-model="mediaForm.http_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item :label="t('ops.httpsPort')" prop="https_port"><el-input-number v-model="mediaForm.https_port" :min="0" :max="65535" /></el-form-item>
        <template v-if="mediaForm.is_embedded && editingMediaId">
          <el-divider content-position="left">{{ t('ops.builtInZlmHttpsCert') }}</el-divider>
          <p class="text-xs mb-2 ops-muted ops-leading">
            {{ t('ops.zlmCertHelpText') }}
          </p>
          <div class="flex items-center gap-2 mb-2">
            <el-tag v-if="mediaSslConfigured" type="success" size="small">{{ t('ops.certInDb') }}</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">{{ t('ops.noCertSaved') }}</el-tag>
          </div>
          <el-form-item :label="t('ops.mergedPem')">
            <el-input v-model="mediaSslMerged" type="textarea" :rows="5" placeholder="-----BEGIN PRIVATE KEY----- ... -----END CERTIFICATE-----" class="font-mono text-xs" />
          </el-form-item>
          <el-form-item :label="t('ops.orPrivateKeyPem')">
            <el-input v-model="mediaSslKey" type="textarea" :rows="4" placeholder="-----BEGIN PRIVATE KEY----- ..." class="font-mono text-xs" />
          </el-form-item>
          <el-form-item :label="t('ops.orCertChainPem')">
            <el-input v-model="mediaSslCert" type="textarea" :rows="4" :placeholder="t('ops.certChainPlaceholder')" class="font-mono text-xs" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="mediaSslSaving" :disabled="!editingMediaId" @click="saveMediaZlmSsl">{{ t('ops.saveCert') }}</el-button>
            <el-button type="danger" plain :loading="mediaSslSaving" :disabled="!editingMediaId || !mediaSslConfigured" @click="clearMediaZlmSsl">{{ t('ops.clearCert') }}</el-button>
          </el-form-item>
        </template>
        <el-form-item :label="t('ops.rtspPort')" prop="rtsp_port"><el-input-number v-model="mediaForm.rtsp_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item :label="t('ops.rtspsPort')" prop="rtsps_port"><el-input-number v-model="mediaForm.rtsps_port" :min="0" :max="65535" /></el-form-item>
        <el-form-item :label="t('ops.rtmpPort')" prop="rtmp_port"><el-input-number v-model="mediaForm.rtmp_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item :label="t('ops.rtmpsPort')" prop="rtmps_port"><el-input-number v-model="mediaForm.rtmps_port" :min="0" :max="65535" /></el-form-item>

        <el-form-item :label="t('ops.hookBaseUrl')">
          <el-input v-model="mediaForm.hook_base_url" :placeholder="t('ops.hookPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ops.hookIp')"><el-input v-model="mediaForm.hook_ip" :placeholder="t('ops.hookIpPlaceholder')" /></el-form-item>
        <el-form-item :label="t('ops.sdpIp')"><el-input v-model="mediaForm.sdp_ip" :placeholder="t('ops.sdpIpPlaceholder')" /></el-form-item>

        <el-form-item :label="t('ops.rtpPortMode')">
          <el-radio-group v-model="mediaForm.rtp_port_mode">
            <el-radio-button value="single">{{ t('ops.singlePort') }}</el-radio-button>
            <el-radio-button value="range">{{ t('ops.multiPort') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('ops.rtpPort')">
          <template v-if="mediaForm.rtp_port_mode === 'single'">
            <el-input-number v-model="mediaForm.rtp_proxy_port" :min="1" :max="65535" />
          </template>
          <template v-else>
            <div class="flex gap-2 items-center">
              <el-input-number v-model="mediaForm.rtp_port_range_start" :min="1" :max="65535" />
              <span class="ops-muted">-</span>
              <el-input-number v-model="mediaForm.rtp_port_range_end" :min="1" :max="65535" />
            </div>
          </template>
        </el-form-item>

        <el-form-item :label="t('ops.recordMgrPort')">
          <el-input-number v-model="mediaForm.record_mgr_port" :min="0" :max="65535" />
        </el-form-item>
        
        <el-form-item :label="t('ops.shardSizeEstimate')">
          <div class="flex items-center gap-2">
            <el-input-number v-model="targetFileSizeMB" :min="1" :max="500" :step="10" size="small" class="ops-input-120" />
            <span class="text-xs text-slate-500">{{ t('ops.mbBitrateHint') }}</span>
            <el-button size="small" type="primary" link @click="applyEstimatedSeconds">{{ t('ops.applyEstimate', { seconds: Math.round(targetFileSizeMB * 8 / 2) }) }}</el-button>
          </div>
        </el-form-item>

        <el-form-item :label="t('ops.mp4ShardSeconds')">
          <el-input-number v-model="mediaForm.protocol_mp4_max_second" :min="30" :max="86400" />
        </el-form-item>
        <el-form-item label="record.fileSecond">
          <el-input-number v-model="mediaForm.record_file_second" :min="30" :max="86400" />
        </el-form-item>
        <el-form-item label="record.sampleMS">
          <el-input-number v-model="mediaForm.record_sample_ms" :min="100" :max="10000" />
        </el-form-item>

        <el-form-item :label="t('ops.secret')"><el-input v-model="mediaForm.secret" /></el-form-item>
        <el-form-item :label="t('ops.autoConfigMedia')">
          <el-switch v-model="mediaForm.auto_config_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mediaDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveMediaNode">{{ t('common.save') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="leaseDialogVisible" :title="t('ops.rtpPortLease')" size="large">
      <div class="flex gap-2 items-center mb-3">
        <el-select v-model="leaseFilterNodeId" :placeholder="t('ops.allNodes')" clearable class="ops-lease-select">
          <el-option v-for="n in mediaNodes" :key="n.id" :label="`${n.ip || n.id}${n.is_active ? t('ops.activeNodeSuffix') : ''}`" :value="n.id || ''" />
        </el-select>
        <el-switch v-model="leaseOnlyUnbound" :active-text="t('ops.onlyOrphanLeases')" />
        <span class="text-xs ops-muted">{{ t('ops.maxLabel') }}</span>
        <el-input-number v-model="leaseLimit" :min="1" :max="1000" size="small" />
        <el-button :loading="leasesLoading" @click="loadLeases">{{ t('common.refresh') }}</el-button>
      </div>
      <el-table :data="leaseItems" border size="small" :empty-text="t('ops.noLeases')" fit>
        <el-table-column prop="media_server_id" :label="t('ops.nodeId')" width="160" />
        <el-table-column prop="port" :label="t('ops.portLabel')" width="100" />
        <el-table-column :label="t('ops.bindStatus')" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.stream_session_id ? 'success' : 'warning'" effect="plain">
              {{ row.stream_session_id ? t('ops.bound') : t('ops.unbound') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="stream_session_id" :label="t('ops.sessionId')" min-width="160" />
        <el-table-column prop="leased_at" :label="t('ops.leaseTime')" min-width="180" />
      </el-table>
      <template #footer>
        <el-button @click="leaseDialogVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="warning" plain @click="openLeaseCleanupDialog()">{{ t('ops.cleanupOrphanLeases') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="leaseCleanupVisible" :title="t('ops.cleanupOrphanLeases')" size="small">
      <div class="text-sm mb-3 ops-muted">
        {{ t('ops.cleanupOrphanHint') }}
      </div>
      <el-form label-width="140px">
        <el-form-item :label="t('ops.exceedSeconds')">
          <el-input-number v-model="leaseCleanupMaxAgeSeconds" :min="60" :max="86400" />
        </el-form-item>
        <el-form-item :label="t('ops.maxCleanupCount')">
          <el-input-number v-model="leaseCleanupLimit" :min="1" :max="5000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="leaseCleanupVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="warning" :loading="cleaningLeases" @click="cleanupLeases">{{ t('ops.startCleanup') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="rtpOpenDialogVisible" :title="t('ops.openRtpReceive')" size="small">
      <el-form :model="rtpOpenForm" label-width="100px">
        <el-form-item :label="t('ops.streamIdLabel')" required>
          <el-input v-model="rtpOpenForm.stream_id" :placeholder="t('ops.streamIdPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ops.appName')">
          <el-input v-model="rtpOpenForm.app" :placeholder="t('ops.appPlaceholder')" />
        </el-form-item>
        <el-form-item label="SSRC">
          <el-input v-model="rtpOpenForm.ssrc" :placeholder="t('ops.ssrcPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ops.tcpMode')">
          <el-select v-model="rtpOpenForm.tcp_mode">
            <el-option :value="0" :label="t('ops.udpDefault')" />
            <el-option :value="1" :label="t('ops.tcpPassiveOption')" />
            <el-option :value="2" :label="t('ops.tcpActiveOption')" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rtpOpenDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="rtpOpening" @click="openRtpReceive">{{ t('ops.open') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="portPoolDialogVisible" :title="t('ops.portPoolStatus')" size="medium">
      <el-table :data="portPoolStatus" v-loading="portPoolLoading" border size="small" :empty-text="t('common.noData')">
        <el-table-column prop="node_ip" :label="t('ops.nodeId')" width="140" />
        <el-table-column prop="protocol" :label="t('ops.protocol')" width="100" />
        <el-table-column prop="total" :label="t('ops.totalPorts')" width="100" />
        <el-table-column prop="used" :label="t('ops.used')" width="80" />
        <el-table-column prop="free" :label="t('ops.free')" width="80" />
        <el-table-column :label="t('ops.usageRate')" width="120">
          <template #default="{ row }">
            <el-progress :percentage="Number(row.total) > 0 ? Math.round(Number(row.used) / Number(row.total) * 100) : 0" :stroke-width="14" :text-inside="true" size="small" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="portPoolDialogVisible = false">{{ t('common.close') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="ffmpegDialogVisible" :title="t('ops.ffmpegCmdManage')" size="large">
      <div class="mb-3">
        <el-button type="primary" size="small" @click="openFfmpegCmdDialog()">{{ t('ops.addCommand') }}</el-button>
      </div>
      <el-table :data="ffmpegCmds" v-loading="ffmpegLoading" border size="small" :empty-text="t('ops.noFfmpegCommands')">
        <el-table-column prop="name" :label="t('common.name')" width="160" />
        <el-table-column prop="protocol" :label="t('ops.protocol')" width="100" />
        <el-table-column prop="cmd" :label="t('ops.commandTemplate')" min-width="300" show-overflow-tooltip />
        <el-table-column :label="t('common.action')" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openFfmpegCmdDialog(row)">{{ t('common.edit') }}</el-button>
            <el-popconfirm :title="t('ops.deleteCmdConfirm', { name: row.name })" @confirm="deleteFfmpegCmd(row.id)">
              <template #reference>
                <el-button size="small" link type="danger">{{ t('common.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="ffmpegDialogVisible = false">{{ t('common.close') }}</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="ffmpegCmdDialogVisible" :title="editingFfmpegCmdId ? t('ops.editFfmpegCmd') : t('ops.newFfmpegCmd')" size="small">
      <el-form :model="ffmpegCmdForm" label-width="100px">
        <el-form-item :label="t('common.name')" required>
          <el-input v-model="ffmpegCmdForm.name" :placeholder="t('ops.commandNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ops.protocol')">
          <el-input v-model="ffmpegCmdForm.protocol" :placeholder="t('ops.protocolPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ops.commandTemplate')" required>
          <el-input v-model="ffmpegCmdForm.cmd" type="textarea" :rows="4" :placeholder="t('ops.cmdTemplatePlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ffmpegCmdDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="savingFfmpegCmd" @click="saveFfmpegCmd">{{ t('common.save') }}</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import api from '@/utils/http'
import { logger } from '@/utils/logger'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { getFriendlyError, getApiErrorMessage } from '../utils/errorMessage'
import { buildWsUrlWithTicket } from '@/utils/wsTicket'  // P0-6: ws-ticket 认证
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const { t } = useI18n()
const route = useRoute()
const activeTab = ref(String(route.query.tab || 'status'))
const status = ref({
  cpu: 0,
  memory_percent: 0,
  zlm_status: t('ops.checking'),
  zlm_streams: 0,
  zlm_node_id: '',
  zlm_select_reason: 'global',
  zlm_select_reason_label: t('ops.useGlobalConfig'),
  zlm_target: '',
  zlm_error: ''
})
const loading = ref(false)
const logs = ref<string[]>([])
const wsConnected = ref(false)
const wsReconnecting = ref(false)
const logContainer = ref<HTMLElement | null>(null)
const logContains = ref(String(route.query.log_contains || ''))
const logContainsAny = ref(String(route.query.log_contains_any || ''))

const historyLogsVisible = ref(false)
const historyLogsLoading = ref(false)
const historyLogFiles = ref<AuditLog[]>([])

const logViewerVisible = ref(false)
const currentLogFile = ref('')
const currentLogLines = ref<string[]>([])
const logSearchKeyword = ref('')
const logCurrentPage = ref(1)
const logPageSize = ref(1000)
const logTotal = ref(0)
const logLinesLoading = ref(false)

const openHistoricalLogs = async () => {
  historyLogsVisible.value = true
  historyLogsLoading.value = true
  try {
    const res = await api.get('/api/v1/logs/files')
    historyLogFiles.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('ops.fetchHistoryLogsFailed')))
  } finally {
    historyLogsLoading.value = false
  }
}

const viewLogLines = (row: Record<string, unknown>) => {
  currentLogFile.value = String(row.name || '')
  logSearchKeyword.value = ''
  logCurrentPage.value = 1
  logPageSize.value = 1000
  logViewerVisible.value = true
  fetchLogLines()
}

const fetchLogLines = async () => {
  logLinesLoading.value = true
  try {
    const res = await api.get(`/api/v1/logs/files/${encodeURIComponent(currentLogFile.value).replace(/%2F/g, '/')}/lines`, {
      params: {
        keyword: logSearchKeyword.value,
        page: logCurrentPage.value,
        page_size: logPageSize.value
      }
    })
    currentLogLines.value = res.data?.lines || []
    logTotal.value = res.data?.total || 0
  } catch (e: unknown) {
    currentLogLines.value = [`${t('ops.loadFailedPrefix')}: ${getApiErrorMessage(e, '')}`]
    logTotal.value = 0
  } finally {
    logLinesLoading.value = false
  }
}

const downloadLog = async (row: Record<string, unknown>) => {
  try {
    const res = await api.get(`/api/v1/logs/files/${encodeURIComponent(String(row.name || '')).replace(/%2F/g, '/')}/download`, {
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', String(row.name || '').split('/').pop() || String(row.name || ''))
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (e: unknown) {
    ElMessage.error(t('ops.downloadFailed'))  // FIXED: 硬编码中文→i18n
  }
}

const traceLoading = ref(false)
const traceRows = ref<AuditLog[]>([])
const tracePage = ref(1)
const tracePageSize = ref(10)
const paginatedTraceRows = computed(() => {
  const start = (tracePage.value - 1) * tracePageSize.value
  const end = start + tracePageSize.value
  return traceRows.value.slice(start, end)
})
watch(traceRows, () => { tracePage.value = 1 })
// SECURITY: 非敏感 UI 偏好（运维追踪可见列配置）— 仅存列 key 数组，不含用户身份或鉴权信息，
// 可安全存入 localStorage 跨会话保留。读取见 initTraceColumns，写入见 watch(visibleTraceColumns)。
const TRACE_COLUMN_STORAGE_KEY = 'ops_trace_visible_columns_v1'
const traceColumnOptions = [
  { key: 'platform_id', label: t('common.platform') },
  { key: 'device_id', label: t('common.device') },
  { key: 'channel_id', label: t('common.channel') }
] as const
const defaultTraceColumns = ['platform_id'] as const
const visibleTraceColumns = ref<string[]>([])
const traceForm = ref({
  platform_id: String(route.query.platform_id || ''),
  trace_id: String(route.query.trace_id || ''),
  event: String(route.query.event || ''),
  limit: Number(route.query.limit || 200)
})

const initTraceColumns = () => {
  const fallback = [...defaultTraceColumns]
  try {
    const raw = localStorage.getItem(TRACE_COLUMN_STORAGE_KEY)
    if (!raw) {
      visibleTraceColumns.value = fallback
      return
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      visibleTraceColumns.value = fallback
      return
    }
    const allow = new Set<string>(traceColumnOptions.map((item) => item.key))
    const filtered = parsed
      .map((x: Record<string, unknown>) => String(x || ''))
      .filter((x: string) => allow.has(x))
    visibleTraceColumns.value = filtered
  } catch {
    visibleTraceColumns.value = fallback
  }
}

const isTraceColumnVisible = (key: string) => visibleTraceColumns.value.includes(key)

const resetTraceColumns = () => {
  visibleTraceColumns.value = [...defaultTraceColumns]
}
const mediaNodes = ref<AuditLog[]>([])
const mediaPage = ref(1)
const mediaPageSize = ref(10)
const paginatedMediaNodes = computed(() => {
  const start = (mediaPage.value - 1) * mediaPageSize.value
  const end = start + mediaPageSize.value
  return mediaNodes.value.slice(start, end)
})
watch(mediaNodes, () => { mediaPage.value = 1 })

const mediaDialogVisible = ref(false)
const editingMediaId = ref('')
const mediaFormRef = ref()
const mediaRules = {
  ip: [{ required: true, message: t('ops.enterNodeIp'), trigger: 'blur' }],
  public_ip: [{ required: true, message: t('ops.enterPublicIp'), trigger: 'blur' }],
  stream_ip: [{ required: true, message: t('ops.enterStreamIp'), trigger: 'blur' }],
  http_port: [{ required: true, message: t('ops.enterHttpPort'), trigger: 'blur' }],
  rtsp_port: [{ required: true, message: t('ops.enterRtspPort'), trigger: 'blur' }],
  rtmp_port: [{ required: true, message: t('ops.enterRtmpPort'), trigger: 'blur' }]
}

let timer: ReturnType<typeof setInterval> | null = null
let ws: WebSocket | null = null
let wsClosedByUser = false
let wsReconnectTimer: number | null = null
let wsReconnectAttempts = 0

const targetFileSizeMB = ref(20)

const applyEstimatedSeconds = () => {
  const seconds = Math.round(targetFileSizeMB.value * 8 / 2)
  mediaForm.value.protocol_mp4_max_second = seconds
  mediaForm.value.record_file_second = seconds
  ElMessage.success(t('ops.shardSecondsSet', { seconds }))
}

const clearTrace = () => {
  traceForm.value = { platform_id: '', trace_id: '', event: '', limit: 200 }
  traceRows.value = []
}

const loadTraceEvents = async () => {
  traceLoading.value = true
  try {
    const params: Record<string, string | number> = { limit: Number(traceForm.value.limit || 200) }
    const platformId = String(traceForm.value.platform_id || '').trim()
    const traceId = String(traceForm.value.trace_id || '').trim()
    const event = String(traceForm.value.event || '').trim()
    if (platformId) params.platform_id = platformId
    if (traceId) params.trace_id = traceId
    if (event) params.event = event
    const res = await api.get('/api/v1/trace-events', { params })
    traceRows.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    traceRows.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? t('common.errorWithSuggestion', { message: friendly.message, suggestion: friendly.suggestion }) : friendly.message)
  } finally {
    traceLoading.value = false
  }
}

const mediaForm = ref({
  ip: '',
  public_ip: '',
  stream_ip: '',
  hook_base_url: '',
  hook_ip: '',
  sdp_ip: '',
  http_port: 8880,
  https_port: 0,
  rtsp_port: 554,
  rtsps_port: 0,
  rtmp_port: 1935,
  rtmps_port: 0,
  rtp_proxy_port: 30000,
  rtp_port_mode: 'single',
  rtp_port_range_start: 30000,
  rtp_port_range_end: 39000,
  record_mgr_port: 0,
  protocol_mp4_max_second: 300,
  record_file_second: 300,
  record_sample_ms: 500,
  secret: '',
  is_embedded: false
  ,
  auto_config_enabled: false
})

const fetchStatus = async () => {
  try {
    const res = await api.get('/api/v1/ops/status')
    status.value = { ...status.value, ...res.data }
  } catch {
    status.value.zlm_status = t('ops.offline')
  }
}

const initWebSocket = async () => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.host
  if (wsReconnectTimer != null) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  const extraParams: Record<string, string> = {}
  if (String(logContains.value || '').trim()) extraParams['contains'] = String(logContains.value || '').trim()
  if (String(logContainsAny.value || '').trim()) extraParams['contains_any'] = String(logContainsAny.value || '').trim()
  // P0-6: 通过 ws-ticket 认证，消除 URL 暴露 JWT token
  let wsUrl: string
  try {
    wsUrl = await buildWsUrlWithTicket('/api/v1/logs/ws/logs')
    const qs = Object.entries(extraParams).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')
    if (qs) wsUrl += `&${qs}`
  } catch (e) {
    logger.warn('initWebSocket: failed to fetch ws-ticket', e)
    return
  }
  ws = new WebSocket(wsUrl)
  ws.onopen = () => {
    wsConnected.value = true
    wsReconnecting.value = false
    wsReconnectAttempts = 0
    logs.value.push(t('ops.logConnected'))
  }
  ws.onmessage = (event) => {
    logs.value.push(event.data)
    if (logs.value.length > 500) logs.value.shift()
    nextTick(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    })
  }
  ws.onclose = () => {
    wsConnected.value = false
    logs.value.push(t('ops.logDisconnected'))
    if (wsClosedByUser) return
    if (wsReconnectTimer != null) return
    wsReconnecting.value = true
    wsReconnectAttempts += 1
    const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(wsReconnectAttempts, 5)))
    wsReconnectTimer = window.setTimeout(() => {
      wsReconnectTimer = null
      initWebSocket()
    }, delay)
  }
}

const applyLogFilter = () => {
  try {
    wsClosedByUser = true
    ws?.close()
  } catch { /* ignore */ }
  wsClosedByUser = false
  logs.value.push(t('ops.logFilterApplied'))
  initWebSocket()
}

const mediaAutoRefreshError = ref(false)
const mediaAutoRefreshErrorAt = ref<string | null>(null)

const mediaSslMerged = ref('')
const mediaSslCert = ref('')
const mediaSslKey = ref('')
const mediaSslSaving = ref(false)
const mediaSslConfigured = ref(false)

const loadMediaNodes = async (opts?: { keepOnError?: boolean; silent?: boolean }) => {
  try {
    const res = await api.get('/api/v1/integrations/media-nodes')
    mediaNodes.value = res.data || []
    mediaAutoRefreshError.value = false
    mediaAutoRefreshErrorAt.value = null
  } catch {
    mediaAutoRefreshError.value = true
    mediaAutoRefreshErrorAt.value = new Date().toISOString()
    if (!opts?.keepOnError) {
      mediaNodes.value = []
    }
  }
}

const mediaOfflineSeconds = ref(120)
const savingMediaOfflineSeconds = ref(false)

const loadMediaOfflineSeconds = async () => {
  try {
    const res = await api.get('/api/v1/integrations/media-nodes/offline-threshold')
    mediaOfflineSeconds.value = Number(res.data?.offline_seconds ?? 120) || 120
  } catch {
    mediaOfflineSeconds.value = 120
  }
}

const saveMediaOfflineSeconds = async () => {
  savingMediaOfflineSeconds.value = true
  try {
    const res = await api.put('/api/v1/integrations/media-nodes/offline-threshold', { offline_seconds: mediaOfflineSeconds.value })
    mediaOfflineSeconds.value = Number(res.data?.offline_seconds ?? mediaOfflineSeconds.value) || mediaOfflineSeconds.value
    ElMessage.success(t('ops.offlineThresholdSaved'))  // FIXED: 硬编码中文→i18n
    await loadMediaNodes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    savingMediaOfflineSeconds.value = false
  }
}

const mediaAutoRefresh = ref(true)
const mediaRefreshIntervalSec = ref(10)
let mediaRefreshTimer: number | null = null

const stopMediaAutoRefresh = () => {
  if (mediaRefreshTimer != null) {
    clearInterval(mediaRefreshTimer)
    mediaRefreshTimer = null
  }
}

const startMediaAutoRefresh = () => {
  stopMediaAutoRefresh()
  if (!mediaAutoRefresh.value) return
  const sec = Math.max(3, Math.min(300, Number(mediaRefreshIntervalSec.value) || 10))
  mediaRefreshTimer = window.setInterval(() => {
    if (activeTab.value === 'media') {
      loadMediaNodes({ keepOnError: true, silent: true })
    }
  }, sec * 1000)
}

const openMediaDialog = (row?: Record<string, unknown>) => {
  editingMediaId.value = String(row?.id || '')
  mediaSslMerged.value = ''
  mediaSslCert.value = ''
  mediaSslKey.value = ''
  mediaSslConfigured.value = !!row?.zlm_ssl_configured
  mediaForm.value = row ? {
    ip: String(row.ip || ''),
    public_ip: String(row.public_ip || ''),
    stream_ip: String(row.stream_ip || ''),
    // FIX: [2026-07-16] 优先使用 DB 原始值，而非计算后的 hook_base_url。
    // 计算后的值可能因 loopback 回退逻辑显示为公网域名，导致用户误以为保存失败。
    hook_base_url: String(row.hook_base_url_raw || row.hook_base_url || ''),
    hook_ip: String(row.hook_ip || ''),
    sdp_ip: String(row.sdp_ip || ''),
    http_port: Number(row.http_port || 8880),
    https_port: Number(row.https_port || 0),
    rtsp_port: Number(row.rtsp_port || 554),
    rtsps_port: Number(row.rtsps_port || 0),
    rtmp_port: Number(row.rtmp_port || 1935),
    rtmps_port: Number(row.rtmps_port || 0),
    rtp_proxy_port: Number(row.rtp_proxy_port || 30000),
    rtp_port_mode: String(row.rtp_port_mode || 'single'),
    rtp_port_range_start: Number(row.rtp_port_range_start || 30000),
    rtp_port_range_end: Number(row.rtp_port_range_end || 39000),
    record_mgr_port: Number(row.record_mgr_port || 0),
    protocol_mp4_max_second: Number(row.protocol_mp4_max_second || 300),
    record_file_second: Number(row.record_file_second || 300),
    record_sample_ms: Number(row.record_sample_ms || 500),
    secret: '',
    is_embedded: !!row.is_embedded
    ,
    auto_config_enabled: !!row.auto_config_enabled
  } : {
    ip: '',
    public_ip: '',
    stream_ip: '',
    hook_base_url: '',
    hook_ip: '',
    sdp_ip: '',
    http_port: 8880,
    https_port: 0,
    rtsp_port: 554,
    rtsps_port: 0,
    rtmp_port: 1935,
    rtmps_port: 0,
    rtp_proxy_port: 30000,
    rtp_port_mode: 'single',
    rtp_port_range_start: 30000,
    rtp_port_range_end: 39000,
    record_mgr_port: 0,
    protocol_mp4_max_second: 300,
    record_file_second: 300,
    record_sample_ms: 500,
    secret: '',
    is_embedded: false
    ,
    auto_config_enabled: false
  }
  mediaDialogVisible.value = true
}

const saveMediaZlmSsl = async () => {
  if (!editingMediaId.value) return
  mediaSslSaving.value = true
  try {
    await api.put(`/api/v1/integrations/media-nodes/${editingMediaId.value}/zlm-ssl`, {
      merged_pem: String(mediaSslMerged.value || '').trim() || null,
      cert_pem: String(mediaSslCert.value || '').trim() || null,
      key_pem: String(mediaSslKey.value || '').trim() || null
    })
    ElMessage.success(t('ops.certSaved'))
    mediaSslMerged.value = ''
    mediaSslCert.value = ''
    mediaSslKey.value = ''
    mediaSslConfigured.value = true
    await loadMediaNodes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    mediaSslSaving.value = false
  }
}

const clearMediaZlmSsl = async () => {
  if (!editingMediaId.value) return
  try {
    await ElMessageBox.confirm(t('ops.confirmClearCert'), t('common.confirm'), { type: 'warning' })
  } catch {
    return
  }
  mediaSslSaving.value = true
  try {
    await api.delete(`/api/v1/integrations/media-nodes/${editingMediaId.value}/zlm-ssl`)
    ElMessage.success(t('ops.certCleared'))
    mediaSslConfigured.value = false
    await loadMediaNodes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    mediaSslSaving.value = false
  }
}

const saveMediaNode = async () => {
  if (mediaFormRef.value) {
    try {
      await mediaFormRef.value.validate()
    } catch {
      return
    }
  }
  try {
    if (editingMediaId.value) {
      await api.put(`/api/v1/integrations/media-nodes/${editingMediaId.value}`, mediaForm.value)
    } else {
      await api.post('/api/v1/integrations/media-nodes', mediaForm.value)
    }
    mediaDialogVisible.value = false
    await loadMediaNodes()
    ElMessage.success(editingMediaId.value ? t('ops.mediaNodeUpdated') : t('ops.mediaNodeCreated'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('ops.copiedToClipboard'))  // FIXED: 硬编码中文→i18n
  } catch {
    ElMessage.warning(t('ops.copyFailed'))  // FIXED: 硬编码中文→i18n
  }
}

const copyMediaNodeHookUrls = async (id: string) => {
  try {
    const res = await api.get(`/api/v1/integrations/media-nodes/${id}/zlm-hook-urls`)
    const base = res.data?.hook_base_url || ''
    const urls = res.data?.hook_urls || {}
    const text = [
      `hook_base_url: ${base}`,
      `on_server_started: ${urls.on_server_started || ''}`,
      `on_server_keepalive: ${urls.on_server_keepalive || ''}`,
      `on_play: ${urls.on_play || ''}`,
      `on_publish: ${urls.on_publish || ''}`,
      `on_stream_changed: ${urls.on_stream_changed || ''}`,
      `on_stream_none_reader: ${urls.on_stream_none_reader || ''}`,
      `on_record_mp4: ${urls.on_record_mp4 || ''}`
    ].join('\\n')
    await copyText(text)
    ElMessage.success(t('ops.hookConfigCopied'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const copyMediaNodeZlmSnippet = async (id: string) => {
  try {
    const res = await api.get(`/api/v1/integrations/media-nodes/${id}/zlm-config-snippet`)
    const snippet = res.data?.snippet || ''
    if (!snippet) {
      ElMessage.warning(t('ops.noConfigSnippet'))
      return
    }
    await copyText(snippet)
    ElMessage.success(t('ops.zlmConfigCopied'))
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const copyMediaNodesJson = async () => {
  try {
    const res = await api.get('/api/v1/integrations/media-nodes/export/media-nodes-json')
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    await copyText(JSON.stringify(items, null, 2))
    ElMessage.success(t('ops.mediaNodesJsonCopied'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const copyMediaNodesEnv = async () => {
  try {
    const res = await api.get('/api/v1/integrations/media-nodes/export/env')
    const text = res.data?.env_text || ''
    if (!text) {
      ElMessage.warning(t('ops.noEnvSnippet'))
      return
    }
    await copyText(text)
    ElMessage.success(t('ops.envCopied'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const leaseDialogVisible = ref(false)
const leaseItems = ref<AuditLog[]>([])
const leasesLoading = ref(false)
const leaseFilterNodeId = ref<string>('')
const leaseOnlyUnbound = ref(true)
const leaseLimit = ref(200)

const loadLeases = async () => {
  leasesLoading.value = true
  try {
    const params: Record<string, string | number | boolean> = { limit: Number(leaseLimit.value) }
    if (leaseFilterNodeId.value) params.node_id = leaseFilterNodeId.value
    if (leaseOnlyUnbound.value) params.only_unbound = true
    const res = await api.get('/api/v1/integrations/media-nodes/leases', { params })
    leaseItems.value = Array.isArray(res.data?.items) ? res.data.items : []
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    leasesLoading.value = false
  }
}

const openLeaseDialog = async (nodeId?: string) => {
  leaseFilterNodeId.value = nodeId || ''
  leaseOnlyUnbound.value = false
  leaseDialogVisible.value = true
  await loadLeases()
}

const leaseCleanupVisible = ref(false)
const leaseCleanupMaxAgeSeconds = ref(600)
const leaseCleanupLimit = ref(500)
const cleaningLeases = ref(false)

const openLeaseCleanupDialog = () => {
  leaseCleanupVisible.value = true
}

const cleanupLeases = async () => {
  cleaningLeases.value = true
  try {
    const res = await api.post('/api/v1/integrations/media-nodes/leases/cleanup', {
      max_age_seconds: leaseCleanupMaxAgeSeconds.value,
      limit: leaseCleanupLimit.value
    })
    ElMessage.success(t('ops.cleanedLeases', { count: Number(res.data?.cleaned ?? 0) }))
    leaseCleanupVisible.value = false
    if (leaseDialogVisible.value) {
      await loadLeases()
    }
    await loadMediaNodes({ keepOnError: true, silent: true })
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    cleaningLeases.value = false
  }
}

const testingAllMediaNodes = ref(false)
const testAllMediaNodes = async () => {
  testingAllMediaNodes.value = true
  try {
    const res = await api.post('/api/v1/integrations/media-nodes/test-all')
    const items = Array.isArray(res.data?.items) ? res.data.items : []
    const onlineCount = items.filter((x: Record<string, unknown>) => x?.online === true).length
    ElMessage.success(t('ops.batchTestDone', { online: onlineCount, total: items.length }))
    await loadMediaNodes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    testingAllMediaNodes.value = false
  }
}

const formatLastSeen = (iso?: string) => {
  if (!iso) return '-'
  try {
    // FIX: [2026-07-04] 局部变量 t 遮蔽了 useI18n 的 t 函数，运行时 TypeError: t is not a function [全栈工程师]
    const ts = new Date(iso).getTime()
    if (!Number.isFinite(ts)) return iso
    const diff = Date.now() - ts
    if (diff < 0) return iso
    const sec = Math.floor(diff / 1000)
    if (sec < 10) return t('ops.justNow')
    if (sec < 60) return t('ops.secondsAgo', { sec })
    const min = Math.floor(sec / 60)
    if (min < 60) return t('ops.minutesAgo', { min })
    const hr = Math.floor(min / 60)
    if (hr < 48) return t('ops.hoursAgo', { hr })
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

const testMediaNode = async (id: string) => {
  try {
    const res = await api.post(`/api/v1/integrations/media-nodes/${id}/test`)
    const online = res.data?.online === true
    const hookBase = res.data?.hook_base_url
    ElMessage.success(online ? t('ops.nodeOnline') : t('ops.nodeOffline'))
    if (hookBase) {
      ElMessage.info(t('ops.hookCallbackUrl', { url: hookBase }))
    }
    await loadMediaNodes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const activateMediaNode = async (id: string) => {
  try {
    await api.post(`/api/v1/integrations/media-nodes/${id}/activate`)
    ElMessage.success(t('ops.nodeActivated'))  // FIXED: 硬编码中文→i18n
    await loadMediaNodes()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const deleteMediaNode = async (id: string) => {
  try {
    await ElMessageBox.confirm(t('common.confirmIrreversible'), t('ops.deleteMediaNodeTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/integrations/media-nodes/${id}`)
    await loadMediaNodes()
    ElMessage.success(t('ops.nodeDeleted'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const handleMediaMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'lease') {
    await openLeaseDialog(String(row.id || ''))
    return
  }
  if (cmd === 'copyHook') {
    await copyMediaNodeHookUrls(String(row.id || ''))
    return
  }
  if (cmd === 'copyZlm') {
    await copyMediaNodeZlmSnippet(String(row.id || ''))
    return
  }
  if (cmd === 'activate') {
    await activateMediaNode(String(row.id || ''))
    return
  }
  if (cmd === 'delete') {
    await deleteMediaNode(String(row.id || ''))
  }
}

const shutdownService = async () => {
  try {
    await ElMessageBox.confirm(t('ops.confirmShutdown'), t('common.tips'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.post('/api/v1/ops/shutdown')
    ElMessage.success(t('ops.shutdownSubmitted'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const diagnoseVisible = ref(false)
const diagnoseLoading = ref(false)
const diagnoseLines = ref<{ text: string; ok: boolean; level?: 'error' | 'warn' }[]>([])
const diagnoseSummary = ref<'ok' | 'warn' | 'error'>('ok')
const diagnoseGeneratedAt = ref<string | null>(null)
const exporting = ref(false)

const exportDiagnostics = async () => {
  exporting.value = true
  try {
    const res = await api.get('/api/v1/ops/diagnostics/export', { responseType: 'blob' })
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    // Try to get filename from content-disposition header if possible, else default
    const contentDisposition = res.headers['content-disposition']
    let filename = `pygbsentry_diag_${new Date().toISOString().replace(/[:.]/g, '')}.zip`
    if (contentDisposition) {
      const match = contentDisposition.match(/filename=(.+)/)
      if (match && match[1]) filename = match[1].replace(/["']/g, '')
    }
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    exporting.value = false
  }
}

const runDiagnose = async () => {
  diagnoseLoading.value = true
  diagnoseVisible.value = true
  diagnoseLines.value = []
  try {
    let lines: { text: string; ok: boolean; level?: 'error' | 'warn' }[] = []
    try {
      const res = await api.get('/api/v1/ops/diagnose-report')
      const data =
        res.data && typeof res.data === 'object' ? (res.data as Record<string, unknown>) : ({} as Record<string, unknown>)

      const rawSummary = data.summary
      diagnoseSummary.value = rawSummary === 'ok' || rawSummary === 'warn' || rawSummary === 'error' ? rawSummary : 'ok'

      diagnoseGeneratedAt.value = typeof data.generated_at === 'string' ? data.generated_at : null

      const items = Array.isArray(data.items) ? data.items : []
      lines = items.map((x: unknown) => {
        const row = x && typeof x === 'object' ? (x as Record<string, unknown>) : ({} as Record<string, unknown>)
        const ok = row.ok !== false
        const name = typeof row.name === 'string' ? row.name : ''
        return {
          text: typeof row.text === 'string' ? row.text : String(row.text ?? ''),
          ok,
          level: ok ? undefined : name === 'database' || name === 'zlm' ? 'error' : 'warn'
        }
      })
    } catch {
      // 兼容旧版：无 /diagnose 时回退到分散请求
      try {
        const dbRes = await api.get('/api/v1/ops/db-check')
        const ok = dbRes.data?.connected === true
        lines.push({ text: ok ? t('ops.dbConnectionOk') : t('ops.dbConnectionError'), ok })
      } catch {
        lines.push({ text: t('ops.dbCheckFailed'), ok: false })
      }
      try {
        const netRes = await api.get('/api/v1/network/summary')
        const d = netRes.data || {}
        lines.push({
          text: t('ops.networkSummary', { deviceTotal: d.device_total ?? 0, deviceOnline: d.device_online ?? 0, streamCount: d.stream_count ?? 0 }),
          ok: true
        })
      } catch {
        lines.push({ text: t('ops.networkSummaryFailed'), ok: false })
      }
      lines.push({
        text: t('ops.zlmStatusLine', { status: status.value.zlm_status === 'Online' ? t('ops.online') : t('ops.offline'), streams: status.value.zlm_streams ?? 0, target: status.value.zlm_target || '-', source: status.value.zlm_select_reason_label || status.value.zlm_select_reason || t('ops.useGlobalConfig'), nodeId: status.value.zlm_node_id ? t('ops.nodeIdSuffix', { nodeId: status.value.zlm_node_id }) : '' }),
        ok: status.value.zlm_status === 'Online'
      })
    }
    diagnoseLines.value = lines
  } finally {
    diagnoseLoading.value = false
  }
}

const exportDiagnoseReport = () => {
  const title = t('ops.diagReportTitle')
  const time = diagnoseGeneratedAt.value || new Date().toLocaleString('zh-CN')
  const body = [
    `summary: ${diagnoseSummary.value}`,
    `generated_at: ${time}`,
    '',
    ...diagnoseLines.value.map((l) => (l.ok ? '[OK]' : l.level === 'error' ? '[ERROR]' : '[WARN]') + ' ' + l.text)
  ].join('\n')
  const blob = new Blob([`${title}\n${t('ops.generateTime')}: ${time}\n\n${body}\n`], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `diagnose-${new Date().toISOString().slice(0, 10)}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

const diagnoseSummaryLabel = computed(() => {
  if (diagnoseSummary.value === 'error') return t('ops.abnormal')
  if (diagnoseSummary.value === 'warn') return t('ops.hasWarnings')
  return t('ops.normalStatus')
})

const diagnoseSummaryTag = computed(() => {
  if (diagnoseSummary.value === 'error') return 'danger'
  if (diagnoseSummary.value === 'warn') return 'warning'
  return 'success'
})

const backupList = ref<{ filename: string; size_bytes: number; created_at: string }[]>([])
const backupLoading = ref(false)
const backupListLoading = ref(false)

const formatBytes = (bytes: number) => {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++ }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

const loadBackupList = async () => {
  backupListLoading.value = true
  try {
    const res = await api.get('/api/v1/ops/backup/list')
    backupList.value = Array.isArray(res.data?.backups) ? res.data.backups : []
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    backupListLoading.value = false
  }
}

const createBackup = async () => {
  try {
    await ElMessageBox.confirm(t('ops.confirmBackup'), t('ops.createBackup'), { type: 'info', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') })
  } catch { return }
  backupLoading.value = true
  try {
    const res = await api.post('/api/v1/ops/backup')
    ElMessage.success(t('ops.backupSuccess', { filename: res.data?.filename || '', tables: res.data?.tables || 0 }))
    await loadBackupList()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    backupLoading.value = false
  }
}

const restoreBackup = async (filename: string) => {
  try {
    await ElMessageBox.confirm(t('ops.restoreConfirmMsg', { filename }), t('common.dangerousAction'), { type: 'error', confirmButtonText: t('ops.restore'), cancelButtonText: t('common.cancel'), confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    const res = await api.post('/api/v1/ops/restore', null, { params: { filename } })
    ElMessage.success(t('ops.restoreSuccess', { tables: res.data?.tables_restored || 0 }))
    await loadBackupList()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const rtpTasks = ref<{ task_id: string; stream_id: string; app: string; port: number; tcp_mode: number; status: string; last_error: string }[]>([])
const rtpLoading = ref(false)
const rtpOpenDialogVisible = ref(false)
const rtpOpening = ref(false)
const rtpOpenForm = ref({ stream_id: '', app: 'live', ssrc: '', tcp_mode: 0 })

const loadRtpTasks = async () => {
  rtpLoading.value = true
  try {
    const res = await api.get('/api/v1/ops/active-streams')
    const streams = Array.isArray(res.data?.streams) ? res.data.streams : []
    const rtpStreamIds = streams.filter((s: Record<string, unknown>) => s.app === 'rtp').map((s: Record<string, unknown>) => s.stream)
    const tasks: typeof rtpTasks.value = []
    for (const s of streams.filter((s: Record<string, unknown>) => s.app === 'rtp')) {
      tasks.push({
        task_id: s.stream || '',
        stream_id: s.stream || '',
        app: 'rtp',
        port: 0,
        tcp_mode: 0,
        status: 'running',
        last_error: ''
      })
    }
    rtpTasks.value = tasks
  } catch (e: unknown) {
    rtpTasks.value = []
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    rtpLoading.value = false
  }
}

const openRtpReceive = async () => {
  const streamId = String(rtpOpenForm.value.stream_id || '').trim()
  if (!streamId) {
    ElMessage.warning(t('ops.streamIdRequired'))
    return
  }
  rtpOpening.value = true
  try {
    const res = await api.post('/api/v1/rtp/receive/open', {
      stream_id: streamId,
      app: String(rtpOpenForm.value.app || 'live').trim() || 'live',
      ssrc: String(rtpOpenForm.value.ssrc || '').trim() || null,
      tcp_mode: Number(rtpOpenForm.value.tcp_mode || 0)
    })
    const port = res.data?.port
    const publicHost = res.data?.public_host || ''
    ElMessage.success(t('ops.rtpOpenSuccess', { port, publicHost: publicHost ? t('ops.rtpOpenPublicHost', { host: publicHost, port }) : '' }))
    rtpOpenDialogVisible.value = false
    rtpOpenForm.value = { stream_id: '', app: 'live', ssrc: '', tcp_mode: 0 }
    await loadRtpTasks()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    rtpOpening.value = false
  }
}

const closeRtpTask = async (taskId: string) => {
  try {
    await api.post(`/api/v1/rtp/receive/close/${taskId}`)
    ElMessage.success(t('ops.rtpClosed'))  // FIXED: 硬编码中文→i18n
    await loadRtpTasks()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  }
}

const sslStatus = ref<{
  enabled: boolean; domain: string; status: string; not_before: string; not_after: string;
  remaining_days: number | null; cert_path: string; last_renew_at: string; last_check_at: string; error: string
} | null>(null)
const sslLoading = ref(false)
const sslRenewing = ref(false)

const loadSslStatus = async () => {
  sslLoading.value = true
  try {
    const res = await api.get('/api/v1/ssl-cert/status')
    sslStatus.value = res.data || null
  } catch (e: unknown) {
    sslStatus.value = null
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    sslLoading.value = false
  }
}

const renewSslCert = async () => {
  try {
    await ElMessageBox.confirm(t('ops.confirmRenewSSL'), t('ops.renewCert'), { type: 'info' })
  } catch { return }
  sslRenewing.value = true
  try {
    const res = await api.post('/api/v1/ssl-cert/renew')
    if (res.data?.success) {
      ElMessage.success(res.data?.message || t('ops.certRenewSuccess'))
    } else {
      ElMessage.error(res.data?.message || t('ops.certRenewFailed'))
    }
    await loadSslStatus()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    sslRenewing.value = false
  }
}

const portPoolDialogVisible = ref(false)
const portPoolStatus = ref<{ node_ip: string; protocol: string; total: number; used: number; free: number }[]>([])
const portPoolLoading = ref(false)

const showPortPoolStatus = async () => {
  portPoolDialogVisible.value = true
  portPoolLoading.value = true
  try {
    const res = await api.get('/api/v1/integrations/media-nodes/port-pool-status')
    portPoolStatus.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    portPoolStatus.value = []
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  } finally {
    portPoolLoading.value = false
  }
}

const ffmpegDialogVisible = ref(false)
const ffmpegCmds = ref<{ id: string; name: string; protocol: string; cmd: string }[]>([])
const ffmpegLoading = ref(false)
const ffmpegCmdDialogVisible = ref(false)
const editingFfmpegCmdId = ref('')
const savingFfmpegCmd = ref(false)
const ffmpegCmdForm = ref({ name: '', protocol: '', cmd: '' })

const showFfmpegCmds = async () => {
  ffmpegDialogVisible.value = true
  ffmpegLoading.value = true
  try {
    const res = await api.get('/api/v1/integrations/ffmpeg_cmd/list')
    ffmpegCmds.value = Array.isArray(res.data) ? res.data : []
  } catch (e: unknown) {
    ffmpegCmds.value = []
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  } finally {
    ffmpegLoading.value = false
  }
}

const openFfmpegCmdDialog = (row?: Record<string, unknown>) => {
  if (row) {
    editingFfmpegCmdId.value = String(row.id || '')
    ffmpegCmdForm.value = { name: String(row.name || ''), protocol: String(row.protocol || ''), cmd: String(row.cmd || '') }
  } else {
    editingFfmpegCmdId.value = ''
    ffmpegCmdForm.value = { name: '', protocol: '', cmd: '' }
  }
  ffmpegCmdDialogVisible.value = true
}

const saveFfmpegCmd = async () => {
  if (!ffmpegCmdForm.value.name.trim()) { ElMessage.warning(t('ops.commandNameRequired')); return }
  savingFfmpegCmd.value = true
  try {
    if (editingFfmpegCmdId.value) {
      await api.put(`/api/v1/integrations/ffmpeg_cmd/${editingFfmpegCmdId.value}`, ffmpegCmdForm.value)
    } else {
      await api.post('/api/v1/integrations/ffmpeg_cmd', ffmpegCmdForm.value)
    }
    ElMessage.success(t('ops.commandSaved'))
    ffmpegCmdDialogVisible.value = false
    await showFfmpegCmds()
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  } finally {
    savingFfmpegCmd.value = false
  }
}

const deleteFfmpegCmd = async (id: string) => {
  try {
    await ElMessageBox.confirm(t('ops.confirmDeleteTemplate'), t('common.confirm'), { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/v1/integrations/ffmpeg_cmd/${id}`)
    ElMessage.success(t('ops.commandDeleted'))  // FIXED: 硬编码中文→i18n
    await showFfmpegCmds()
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  }
}

watch(activeTab, (tab) => {
  if (tab === 'backup') loadBackupList()
  if (tab === 'rtp') loadRtpTasks()
  if (tab === 'ssl') loadSslStatus()
})

onMounted(async () => {
  initTraceColumns()
  await Promise.all([fetchStatus(), loadMediaNodes(), loadMediaOfflineSeconds()])
  timer = setInterval(fetchStatus, 3000)
  initWebSocket()
  startMediaAutoRefresh()
  if (activeTab.value === 'trace') {
    await loadTraceEvents()
  }
})

onBeforeUnmount(async () => {
  if (timer) clearInterval(timer)
  stopMediaAutoRefresh()
  wsClosedByUser = true
  wsReconnecting.value = false
  if (ws) ws.close()
  if (wsReconnectTimer != null) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
})

watch([activeTab, mediaAutoRefresh, mediaRefreshIntervalSec], () => {
  startMediaAutoRefresh()
})

watch(activeTab, async () => {
  if (activeTab.value === 'trace') {
    await loadTraceEvents()
  }
  if (activeTab.value === 'cascade_diagnosis') {
    await loadCascadeDiagnosis()
  }
})

watch(visibleTraceColumns, (value) => {
  localStorage.setItem(TRACE_COLUMN_STORAGE_KEY, JSON.stringify(value))
}, { deep: true })

// 国标级联诊断
const cascadeLoading = ref(false)
const cascadeDiagnosis = ref<AuditLog>({})
const cascadeSipConfig = ref<AuditLog>({})

const loadCascadeDiagnosis = async () => {
  cascadeLoading.value = true
  try {
    const res = await api.get('/api/v1/platforms/inbound/diagnosis')
    cascadeDiagnosis.value = res.data || {}
    cascadeSipConfig.value = res.data?.sip_config || {}
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    cascadeDiagnosis.value = {}
    cascadeSipConfig.value = {}
  } finally {
    cascadeLoading.value = false
  }
}

const cascadeOverallLevel = computed(() => {
  const diags = cascadeDiagnosis.value?.diagnostics || []
  if (diags.some((d: Record<string, unknown>) => d.level === 'error')) return 'error'
  if (diags.some((d: Record<string, unknown>) => d.level === 'warn')) return 'warn'
  return 'ok'
})

const cascadeOverallClass = computed(() => ({
  'cascade-health-ok': cascadeOverallLevel.value === 'ok',
  'cascade-health-warn': cascadeOverallLevel.value === 'warn',
  'cascade-health-error': cascadeOverallLevel.value === 'error',
}))

const cascadeOverallIcon = computed(() => {
  if (cascadeOverallLevel.value === 'error') return '🔴'
  if (cascadeOverallLevel.value === 'warn') return '🟡'
  return '🟢'
})

const cascadeOverallTitle = computed(() => {
  if (cascadeOverallLevel.value === 'error') return t('ops.cascadeAbnormal')
  if (cascadeOverallLevel.value === 'warn') return t('ops.cascadeAttention')
  return t('ops.cascadeNormal')
})

const cascadeOverallDesc = computed(() => {
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  const diags = cascadeDiagnosis.value?.diagnostics || []
  const errorCount = diags.filter((d: Record<string, unknown>) => d.level === 'error').length
  const warnCount = diags.filter((d: Record<string, unknown>) => d.level === 'warn').length
  if (platforms.length === 0) return t('ops.noDownstreamPlatforms')
  const parts = [t('ops.downstreamConnected', { count: platforms.length })]
  if (errorCount > 0) parts.push(t('ops.errorCount', { count: errorCount }))
  if (warnCount > 0) parts.push(t('ops.warnCount', { count: warnCount }))
  return parts.join('，')
})

const cascadeStepActive = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  if (counts.register_received > 0) {
    if (counts.register_401_challenge > 0) {
      if (counts.register_ok_platform > 0 || counts.register_ok_device > 0 || platforms.some((p: Record<string, unknown>) => Boolean((p.register as Record<string, unknown> | undefined)?.last_ok_at))) {
        if (platforms.some((p: Record<string, unknown>) => Boolean((p.keepalive as Record<string, unknown> | undefined)?.last_at))) {
          return 4
        }
        return 3
      }
      return 2
    }
    return 1
  }
  return 0
})

const cascadeStepProcessStatus = computed(() => {
  const diags = cascadeDiagnosis.value?.diagnostics || []
  if (diags.some((d: Record<string, unknown>) => d.level === 'error')) return 'error'
  return 'process'
})

const cascadeStep1Desc = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  if (counts.register_received > 0) return t('ops.receivedTimes', { count: counts.register_received })
  return t('ops.noRequestReceived')
})

const cascadeStep2Desc = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  if (counts.register_401_challenge > 0) return t('ops.sentChallengeTimes', { count: counts.register_401_challenge })
  return '—'
})

const cascadeStep3Desc = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  const okCount = (counts.register_ok_platform || 0) + (counts.register_ok_device || 0)
  const registeredPlatforms = platforms.filter((p: Record<string, unknown>) => Boolean((p.register as Record<string, unknown> | undefined)?.last_ok_at)).length
  if (okCount > 0 || registeredPlatforms > 0) return t('ops.platformsRegistered', { count: registeredPlatforms })
  if (counts.register_auth_failed > 0) return t('ops.authFailedTimes', { count: counts.register_auth_failed })
  return '—'
})

const cascadeStep4Desc = computed(() => {
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  const withKeepalive = platforms.filter((p: Record<string, unknown>) => Boolean((p.keepalive as Record<string, unknown> | undefined)?.last_at)).length
  if (withKeepalive > 0) return t('ops.heartbeatsNormal', { count: withKeepalive })
  return '—'
})

const cascadeAuthLabel = (auth: string | undefined) => {
  if (!auth) return t('ops.unauthenticated')
  const a = String(auth).toLowerCase()
  if (a.includes('digest')) return t('ops.digestAuth')
  if (a.includes('basic')) return t('ops.basicAuth')
  if (a === 'none' || a === '') return t('ops.noAuthRequired')
  return auth
}

const cascadeEventLabel = (event: string) => {
  const map: Record<string, string> = {
    'register_received': t('ops.receivedRegister'),
    'register_401_challenge': t('ops.requireAuth'),
    'register_ok_platform': t('ops.platformRegisterOk'),
    'register_ok_device': t('ops.deviceRegisterOk'),
    'register_auth_failed': t('ops.authFailed'),
  }
  return map[event] || event
}

const cascadeEventTagType = (event: string) => {
  if (event.includes('ok')) return 'success'
  if (event.includes('failed')) return 'danger'
  if (event.includes('401')) return 'warning'
  return 'info'
}

// 流媒体诊断
const diagNodeId = ref<string>('')
const diagChannelId = ref<string>('')
const diagChannelName = ref<string>('')
const diagActiveStreams = ref<AuditLog[]>([])
const diagChannelLoading = ref(false)
const diagLoading = ref(false)
const diagResults = ref<AuditLog[]>([])
const diagAllSteps = [
  { key: 'zlm_api', label: t('ops.zlmApiConnectivity') },
  { key: 'stream_list', label: t('ops.streamListCheck') },
  { key: 'hook_callback', label: t('ops.hookCallbackCheck') },
  { key: 'play_address', label: t('ops.playAddressBuild') },
  { key: 'nginx_proxy', label: t('ops.nginxReverseProxy') },
]
const diagRunningSteps = ref<string[]>([])

const getStepStatus = (key: string) => {
  const done = diagResults.value.some(r => r.step === key)
  const ok = diagResults.value.find(r => r.step === key && r.ok)
  if (done && ok) return 'success'
  if (done && !ok) return 'error'
  if (diagRunningSteps.value.includes(key)) return 'process'
  return 'wait'
}

const diagOverallOk = computed(() => diagResults.value.length > 0 && diagResults.value.every(r => r.ok))

const diagGroupedResults = computed(() => {
  return diagAllSteps.map(step => {
    const items = diagResults.value.filter(r => r.step === step.key)
    return {
      step: step.key,
      label: step.label,
      ok: items.length > 0 && items.every(i => i.ok),
      items,
    }
  }).filter(g => g.items.length > 0)
})

const loadDiagStreams = async () => {
  diagActiveStreams.value = []
  diagChannelId.value = ''
  diagChannelName.value = ''
  diagChannelLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (diagNodeId.value) params.node_id = diagNodeId.value
    const res = await api.get('/api/v1/ops/active-streams', { params })
    diagActiveStreams.value = Array.isArray(res.data?.streams) ? res.data.streams : []
  } catch {
    diagActiveStreams.value = []
  } finally {
    diagChannelLoading.value = false
  }
}

watch(diagNodeId, () => {
  loadDiagStreams()
})

watch(diagChannelId, (val) => {
  if (!val) {
    diagChannelName.value = ''
    return
  }
  const found = diagActiveStreams.value.find(s => s.stream === val)
  diagChannelName.value = found?.name || val
})

const runStreamDiagnose = async () => {
  diagLoading.value = true
  diagResults.value = []
  diagRunningSteps.value = [...diagAllSteps.map(s => s.key)]
  try {
    const nodeId = diagNodeId.value || undefined
    const params: Record<string, string> = {}
    if (nodeId) params.node_id = nodeId
    if (diagChannelId.value) params.channel_id = diagChannelId.value

    const res = await api.get('/api/v1/ops/stream-diagnose', { params })
    diagResults.value = Array.isArray(res.data?.items) ? res.data.items : []
    // 优先用 API 返回的通道名称（精确），其次用前端已知名称
    if (res.data?.channel_name) {
      diagChannelName.value = res.data.channel_name
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    diagLoading.value = false
    diagRunningSteps.value = []
  }
}

const exportDiagReport = () => {
  const lines = [
    `${t('ops.diagReportExport')} - ${new Date().toLocaleString('zh-CN')}`,
    `${t('ops.nodeColon')}${diagNodeId.value || t('ops.defaultActiveNode')}`,
    `${t('ops.channelColonLabel')}${diagChannelId.value || t('common.all')}`,
    '',
    ...diagGroupedResults.value.flatMap(group => [
      `${group.ok ? '[PASS]' : '[FAIL]'} ${group.label}`,
      ...group.items.map(i => `  ${i.ok ? '✓' : '✗'} ${i.title}${i.detail ? '\n    ' + i.detail : ''}${i.suggestion ? '\n    💡 ' + i.suggestion : ''}`),
      '',
    ])
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `stream_diag_${new Date().toISOString().slice(0, 10)}.txt`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<style scoped>
.ops-status-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-bg-color);
}

.ops-muted {
  color: var(--el-text-color-secondary);
}

.ops-kpi-value {
  color: var(--el-color-primary);
}

.ops-danger-break {
  color: var(--el-color-danger);
  word-break: break-all;
}

.ops-log-box {
  background: var(--el-color-black);
  color: var(--el-color-success-light-5);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.ops-log-box--dialog {
  height: 500px;
}

.ops-input-120 {
  width: 120px;
}

.ops-input-220 {
  width: 220px;
}

.ops-input-240 {
  width: 240px;
}

.ops-input-260 {
  width: 260px;
}

.ops-input-300 {
  width: 300px;
}

.ops-input-400 {
  max-width: 400px;
}

.ops-lease-select {
  min-width: 260px;
}

.ops-hook-url {
  max-width: 240px;
  color: var(--el-text-color-secondary);
}

.ops-danger-help {
  color: var(--el-color-danger);
  cursor: help;
}

.ops-warning {
  color: var(--el-color-warning);
}

.ops-storage-tip {
  border-color: var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
}

.ops-leading {
  line-height: 1.5;
}

.ops-diag-node-select {
  min-width: 280px;
}

.ops-diag-channel-input {
  width: 380px;
}

.cascade-health-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid;
}
.cascade-health-banner.cascade-health-ok {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
}
.cascade-health-banner.cascade-health-warn {
  background: var(--el-color-warning-light-9);
  border-color: var(--el-color-warning-light-5);
}
.cascade-health-banner.cascade-health-error {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-5);
}
.cascade-health-icon {
  font-size: 32px;
  line-height: 1;
}
.cascade-health-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 2px;
}
.cascade-health-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
