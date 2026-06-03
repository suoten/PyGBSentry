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
                  来源：{{ status.zlm_select_reason_label || status.zlm_select_reason || '使用全局配置' }}
                  <span v-if="status.zlm_node_id">（{{ status.zlm_node_id }}）</span>
                </div>
                <div class="text-xs ops-muted">
                  目标：{{ status.zlm_target || '-' }}
                </div>
                <div v-if="status.zlm_status !== 'Online' && status.zlm_error" class="text-xs mt-1 ops-danger-break">
                  错误：{{ status.zlm_error }}
                </div>
              </div>
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">当前流数</div>
                <div class="text-2xl font-bold" style="color: var(--el-color-warning)">{{ status.zlm_streams }}</div>
              </div>
            </div>
          </el-card>
          <el-card class="col-span-2 md:col-span-1 flex flex-col h-[500px]">
            <template #header>
              <div class="flex justify-between items-center">
                <div class="font-semibold flex items-center gap-2">
                  <span>实时日志</span>
                  <el-input v-model="logContains" size="small" placeholder="包含关键词（逗号分隔，需全部命中）" clearable class="ops-input-240" />
                  <el-input v-model="logContainsAny" size="small" placeholder="任一关键词命中（逗号分隔）" clearable class="ops-input-220" />
                  <el-button size="small" @click="applyLogFilter">应用</el-button>
                  <el-button size="small" type="primary" plain @click="openHistoricalLogs">历史日志</el-button>
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
                总体状态：{{ diagnoseSummaryLabel }}
              </el-tag>
              <span class="ops-muted">生成时间：{{ diagnoseGeneratedAt || '-' }}</span>
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
            <el-button @click="exportDiagnoseReport">导出报告</el-button>
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
            <el-table-column :label="t('common.actions')" width="200" fixed="right">  <!-- FIXED: 硬编码中文→t() -->
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
            <el-input v-model="traceForm.platform_id" placeholder="平台 ID（级联平台）" class="ops-input-220" clearable />
            <el-input v-model="traceForm.trace_id" placeholder="追踪 ID / 呼叫标识" class="ops-input-260" clearable />
            <el-input v-model="traceForm.event" placeholder="事件类型（可选）" class="ops-input-220" clearable />
            <el-input-number v-model="traceForm.limit" :min="1" :max="500" />
            <el-button type="primary" @click="loadTraceEvents" :loading="traceLoading">查询</el-button>
            <el-button @click="clearTrace">清空筛选</el-button>
            <el-popover placement="bottom-end" :width="220" trigger="click">
              <template #reference>
                <el-button plain>字段显示</el-button>
              </template>
              <el-checkbox-group v-model="visibleTraceColumns" class="grid grid-cols-2 gap-x-3 gap-y-2">
                <el-checkbox v-for="col in traceColumnOptions" :key="col.key" :label="col.key">
                  {{ col.label }}
                </el-checkbox>
              </el-checkbox-group>
              <div class="mt-3 flex justify-end">
                <el-button size="small" text @click="resetTraceColumns">恢复默认</el-button>
              </div>
            </el-popover>
          </div>
          <el-table :data="paginatedTraceRows" border size="small" v-loading="traceLoading" :empty-text="'暂无事件'">
            <el-table-column prop="created_at" label="时间" width="190" />
            <el-table-column prop="event" label="事件" width="200" />
            <el-table-column prop="trace_id" label="追踪 ID" min-width="240" show-overflow-tooltip />
            <el-table-column v-if="isTraceColumnVisible('platform_id')" prop="platform_id" label="平台" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="isTraceColumnVisible('device_id')" prop="device_id" label="设备" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="isTraceColumnVisible('channel_id')" prop="channel_id" label="通道" min-width="180" show-overflow-tooltip />
            <el-table-column label="负载" min-width="360" show-overflow-tooltip>
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
              prev-text="上一页"
              next-text="下一页"
              size="small"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="媒体节点" name="media">
        <el-card shadow="never">
          <div class="mb-3">
            <el-button type="primary" @click="openMediaDialog()">新增媒体节点</el-button>
            <el-button class="ml-2" @click="copyMediaNodesJson">复制 MEDIA_NODES 配置</el-button>
            <el-button class="ml-2" @click="copyMediaNodesEnv">复制 ENV 配置</el-button>
            <el-button class="ml-2" @click="openLeaseDialog()">查看租约</el-button>
            <el-button class="ml-2" type="warning" plain @click="openLeaseCleanupDialog()">清理孤儿租约</el-button>
            <el-button class="ml-2" :loading="testingAllMediaNodes" @click="testAllMediaNodes">批量测试</el-button>
            <el-button class="ml-2" @click="showPortPoolStatus">端口池状态</el-button>
            <el-button class="ml-2" @click="showFfmpegCmds">FFmpeg 命令</el-button>
            <el-switch class="ml-4" v-model="mediaAutoRefresh" active-text="自动刷新" />
            <el-tag v-if="mediaAutoRefreshError" class="ml-2" type="warning" effect="plain">
              刷新失败
            </el-tag>
            <span class="ml-2 text-xs" style="color: var(--el-text-color-secondary)">间隔</span>
            <el-input-number class="ml-2" v-model="mediaRefreshIntervalSec" :min="3" :max="300" size="small" />
            <span class="ml-1 text-xs" style="color: var(--el-text-color-secondary)">秒</span>
            <span class="ml-4 text-xs" style="color: var(--el-text-color-secondary)">离线阈值（秒）</span>
            <el-input-number class="ml-2" v-model="mediaOfflineSeconds" :min="10" :max="86400" size="small" />
            <el-button class="ml-2" size="small" :loading="savingMediaOfflineSeconds" @click="saveMediaOfflineSeconds">保存</el-button>
          </div>
          <el-table :data="paginatedMediaNodes" border :empty-text="'暂无媒体节点'" fit>
            <el-table-column prop="ip" label="IP">
              <template #default="{ row }">
                <div class="flex items-center gap-2">
                  <span class="font-mono">{{ row.ip || '-' }}</span>
                  <el-tag v-if="row.is_active" type="success" effect="plain" size="small">活动</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="public_ip" label="公网IP" />
            <el-table-column label="对外访问" min-width="220">
              <template #default="{ row }">
                <span class="font-mono text-xs" :title="`${row.computed_public_host || ''}:${row.computed_public_http_port || ''}`">
                  {{ (row.computed_public_host || '-') + ':' + (row.computed_public_http_port || '-') }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="computed_hook_base_url" label="Hook回调" min-width="260">
              <template #default="{ row }">
                <span
                  class="truncate block ops-hook-url"
                  :title="row.computed_hook_base_url || ''"
                >
                  {{ row.computed_hook_base_url || '-' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="收流端口" min-width="180">
              <template #default="{ row }">
                <span v-if="row.rtp_port_mode === 'range'">
                  {{ row.rtp_port_range_start }} - {{ row.rtp_port_range_end }}
                </span>
                <span v-else>
                  {{ row.rtp_proxy_port }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="http_port" label="HTTP端口" width="100" />
            <el-table-column label="ZLM SSL" width="88">
              <template #default="{ row }">
                <el-tag v-if="row.is_embedded && row.zlm_ssl_configured" type="success" size="small">已配</el-tag>
                <span v-else-if="row.is_embedded" class="text-xs ops-muted">—</span>
                <span v-else class="text-xs ops-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="rtsp_port" label="RTSP端口" width="100" />
            <el-table-column prop="rtmp_port" label="RTMP端口" width="100" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <div class="flex flex-col items-start gap-1">
                  <el-tag size="small" :type="row.is_online ? 'success' : 'danger'">{{ row.is_online ? '在线' : '离线' }}</el-tag>
                  <el-tooltip
                    v-if="!row.is_online && row.last_probe_error"
                    :content="row.last_probe_error"
                    placement="top"
                  >
                    <span class="text-xs ops-danger-help">离线原因</span>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="最后心跳" min-width="160">
              <template #default="{ row }">
                <span class="text-xs ops-muted" :title="row.last_seen_at || ''">
                  {{ formatLastSeen(row.last_seen_at) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="最近探测错误" min-width="220">
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
            <el-table-column label="操作" width="260">
              <template #default="{ row }">
                <div class="table-action-inline">
                  <el-button size="small" @click="openMediaDialog(row)">编辑</el-button>
                  <el-button size="small" @click="testMediaNode(row.id)">测试</el-button>
                  <el-dropdown trigger="click" @command="(cmd: string) => handleMediaMoreCommand(row, cmd)">
                    <el-button size="small" plain class="table-action-more">
                      更多
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="lease">租约</el-dropdown-item>
                        <el-dropdown-item command="copyHook">复制 Hook</el-dropdown-item>
                        <el-dropdown-item command="copyZlm">复制 ZLM 片段</el-dropdown-item>
                        <el-dropdown-item command="activate" :disabled="row.is_active">设为活动</el-dropdown-item>
                        <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
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
              prev-text="上一页"
              next-text="下一页"
              size="small"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="国标级联诊断" name="cascade_diagnosis">
        <el-card shadow="never">
          <div class="flex flex-wrap items-center gap-2 mb-4">
            <el-button type="primary" @click="loadCascadeDiagnosis" :loading="cascadeLoading">
              {{ cascadeLoading ? '正在诊断...' : '一键诊断' }}
            </el-button>
            <span class="text-xs" style="color:var(--el-text-color-secondary)">检测其他平台与本平台的国标级联连接状态</span>
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
              <el-collapse-item title="本端 SIP 配置（供下级平台连接时填写）" name="sip_config">
                <div class="grid grid-cols-2 gap-3 text-sm">
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">国标 ID（SIP ID）</div>
                    <code class="text-sm font-semibold">{{ cascadeSipConfig.sip_id || '—' }}</code>
                  </div>
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">域（Realm）</div>
                    <code class="text-sm font-semibold">{{ cascadeSipConfig.sip_domain || '—' }}</code>
                  </div>
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">SIP 服务器地址</div>
                    <code class="text-sm font-semibold">{{ cascadeSipConfig.sip_ip || '—' }}:{{ cascadeSipConfig.sip_port || '—' }}</code>
                  </div>
                  <div class="p-3 rounded" style="background:var(--el-fill-color-light)">
                    <div class="text-xs mb-1" style="color:var(--el-text-color-secondary)">传输方式</div>
                    <code class="text-sm font-semibold">UDP</code>
                  </div>
                </div>
                <div class="mt-2 text-xs" style="color:var(--el-color-primary)">
                  💡 把以上信息填到下级平台的"上级平台"配置中即可
                </div>
              </el-collapse-item>
            </el-collapse>

            <!-- 注册流程步骤条 -->
            <div class="mb-4">
              <div class="text-sm font-semibold mb-3">注册流程检查</div>
              <el-steps :active="cascadeStepActive" finish-status="success" :process-status="cascadeStepProcessStatus" align-center>
                <el-step title="收到注册请求" :description="cascadeStep1Desc" />
                <el-step title="身份验证" :description="cascadeStep2Desc" />
                <el-step title="注册成功" :description="cascadeStep3Desc" />
                <el-step title="心跳保活" :description="cascadeStep4Desc" />
              </el-steps>
            </div>

            <!-- 入站平台列表（人话版） -->
            <div v-if="(cascadeDiagnosis.inbound_platforms || []).length > 0" class="mb-4">
              <div class="text-sm font-semibold mb-2">已连接的下级平台</div>
              <div class="space-y-2">
                <div v-for="p in cascadeDiagnosis.inbound_platforms" :key="p.platform_id" class="p-3 rounded border" style="border-color:var(--el-border-color-lighter)">
                  <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2">
                      <el-tag :type="p.register?.last_ok_at ? 'success' : 'danger'" size="small" effect="dark">
                        {{ p.register?.last_ok_at ? '已注册' : '未注册' }}
                      </el-tag>
                      <span class="font-medium text-sm">{{ p.register?.last_gb_id || p.platform_id || '未知' }}</span>
                    </div>
                    <el-tag v-if="p.keepalive?.last_at" type="success" size="small">心跳正常</el-tag>
                    <el-tag v-else type="info" size="small">无心跳</el-tag>
                  </div>
                  <div class="grid grid-cols-3 gap-2 text-xs" style="color:var(--el-text-color-secondary)">
                    <div>来源地址：{{ p.register?.last_addr || '—' }}</div>
                    <div>传输方式：{{ p.register?.last_transport || '—' }}</div>
                    <div>认证方式：{{ cascadeAuthLabel(p.register?.auth) }}</div>
                    <div>注册时间：{{ p.register?.last_ok_at || '—' }}</div>
                    <div>最近心跳：{{ p.keepalive?.last_at || '—' }}</div>
                    <div>心跳来源：{{ p.keepalive?.last_addr || '—' }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 诊断结论（卡片式，人话版） -->
            <div v-if="cascadeDiagnosis.diagnostics?.length > 0" class="mb-4">
              <div class="text-sm font-semibold mb-2">诊断结果</div>
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
                    <strong>怎么办：</strong>{{ d.suggestion }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 高级详情（默认折叠） -->
            <el-collapse>
              <el-collapse-item title="高级详情（技术数据）" name="advanced">
                <!-- SIP 事件统计 -->
                <div class="mb-3">
                  <div class="text-xs font-semibold mb-2" style="color:var(--el-text-color-secondary)">SIP 事件统计</div>
                  <div class="flex gap-2 flex-wrap">
                    <el-tag type="info" size="small">收到注册: {{ cascadeDiagnosis.recent_trace_events_count?.register_received || 0 }}</el-tag>
                    <el-tag type="warning" size="small">发出401质询: {{ cascadeDiagnosis.recent_trace_events_count?.register_401_challenge || 0 }}</el-tag>
                    <el-tag type="success" size="small">平台注册成功: {{ cascadeDiagnosis.recent_trace_events_count?.register_ok_platform || 0 }}</el-tag>
                    <el-tag type="success" size="small">设备注册成功: {{ cascadeDiagnosis.recent_trace_events_count?.register_ok_device || 0 }}</el-tag>
                    <el-tag type="danger" size="small">鉴权失败: {{ cascadeDiagnosis.recent_trace_events_count?.register_auth_failed || 0 }}</el-tag>
                  </div>
                </div>
                <!-- 事件详情 -->
                <div v-if="cascadeDiagnosis.recent_trace_by_trace_id && Object.keys(cascadeDiagnosis.recent_trace_by_trace_id).length > 0">
                  <div class="text-xs font-semibold mb-2" style="color:var(--el-text-color-secondary)">最近注册事件（按会话分组）</div>
                  <div v-for="(events, tid) in cascadeDiagnosis.recent_trace_by_trace_id" :key="tid" class="mb-2 p-2 rounded" style="background: var(--el-fill-color-lighter); border: 1px solid var(--el-border-color-lighter);">
                    <div class="text-xs font-mono mb-1" style="color: var(--el-text-color-secondary)">会话: {{ tid }}</div>
                    <div v-for="evt in events" :key="evt.created_at" class="flex items-center gap-2 text-xs mb-0.5">
                      <el-tag :type="cascadeEventTagType(evt.event)" size="small">{{ cascadeEventLabel(evt.event) }}</el-tag>
                      <span style="color: var(--el-text-color-secondary)">{{ evt.created_at }}</span>
                      <span v-if="evt.payload?.reason" style="color: var(--el-color-danger)">原因: {{ evt.payload.reason }}</span>
                    </div>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </template>

          <div v-else-if="!cascadeLoading" class="text-center py-8" style="color:var(--el-text-color-secondary)">
            <div class="text-4xl mb-3">🔍</div>
            <div class="text-sm mb-3">点击"一键诊断"检测国标级联连接状态</div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="流媒体诊断" name="stream_diagnosis">
        <el-card shadow="never">
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <el-select v-model="diagNodeId" placeholder="选择媒体节点（留空使用活动节点）" clearable class="ops-diag-node-select" @change="diagResults = []">
              <el-option v-for="n in mediaNodes" :key="n.id" :label="`${n.ip || n.id}${n.is_embedded ? '【内置】' : ''}`" :value="n.id" />
            </el-select>
            <el-select
              v-model="diagChannelId"
              placeholder="选择通道（留空诊断全部）"
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
                    {{ s.stream }} &nbsp; {{ s.readerCount > 0 ? `🔴 ${s.readerCount}人观看` : `⚪ ${s.aliveSecond}s` }}
                  </span>
                </div>
              </el-option>
            </el-select>
            <el-button type="primary" plain bg @click="runStreamDiagnose" :loading="diagLoading" size="default">开始诊断</el-button>
            <el-button @click="diagResults = []" size="default">清空</el-button>
          </div>

          <div v-if="diagResults.length > 0" class="space-y-3">
            <div class="flex justify-between items-center mb-3">
              <div class="flex items-center gap-3">
                <el-tag :type="diagOverallOk ? 'success' : 'danger'" size="large" effect="plain">
                  {{ diagOverallOk ? '诊断通过' : '发现问题' }}
                </el-tag>
                <span v-if="diagChannelName && diagChannelName !== diagChannelId" class="text-sm" style="color: var(--el-text-color-secondary)">
                  通道：{{ diagChannelName }}
                </span>
              </div>
              <el-button size="small" @click="exportDiagReport">导出报告</el-button>
            </div>
            <div v-for="group in diagGroupedResults" :key="group.step" class="border rounded p-4">
              <div class="flex items-center gap-2 mb-3">
                <el-tag :type="group.ok ? 'success' : 'danger'" size="small">{{ group.ok ? '通过' : '失败' }}</el-tag>
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

          <el-empty v-else-if="!diagLoading" description="选择节点后点击「开始诊断」，系统将自动检查播放链路各环节" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="备份恢复" name="backup">
        <el-card>
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-semibold">数据库备份与恢复</span>
              <div class="flex gap-2">
                <el-button type="primary" :loading="backupLoading" @click="createBackup">创建备份</el-button>
                <el-button @click="loadBackupList" :loading="backupListLoading">刷新列表</el-button>
              </div>
            </div>
          </template>
          <el-alert type="warning" :closable="false" class="mb-4" show-icon>
            <template #title>
              恢复操作将覆盖当前数据库数据，仅超级管理员可执行。恢复前建议先创建备份。
            </template>
          </el-alert>
          <el-table :data="backupList" v-loading="backupListLoading" stripe empty-text="暂无备份">
            <el-table-column prop="filename" label="文件名" min-width="280" />
            <el-table-column label="大小" width="120">
              <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="200" />
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-popconfirm
                  :title="`确定从备份「${row.filename}」恢复？此操作将覆盖当前数据！`"
                  confirm-button-text="确定恢复"
                  cancel-button-text="取消"
                  confirm-button-type="danger"
                  @confirm="restoreBackup(row.filename)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" link>恢复</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="RTP接收" name="rtp">
        <el-card>
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-semibold">RTP 收流管理</span>
              <el-button @click="loadRtpTasks" :loading="rtpLoading">刷新列表</el-button>
            </div>
          </template>
          <el-alert type="info" :closable="false" class="mb-4" show-icon>
            <template #title>开启 RTP 接收后，外部编码器可向指定端口推送 RTP 流，系统自动转码分发。</template>
          </el-alert>
          <div class="mb-4">
            <el-button type="primary" @click="rtpOpenDialogVisible = true">开启 RTP 接收</el-button>
          </div>
          <el-table :data="rtpTasks" v-loading="rtpLoading" stripe empty-text="暂无 RTP 接收任务">
            <el-table-column prop="task_id" label="任务ID" min-width="200" show-overflow-tooltip />
            <el-table-column prop="stream_id" label="流ID" min-width="180" show-overflow-tooltip />
            <el-table-column prop="app" label="应用" width="100" />
            <el-table-column prop="port" label="端口" width="100" />
            <el-table-column prop="tcp_mode" label="TCP模式" width="100">
              <template #default="{ row }">{{ ({ 0: 'UDP', 1: 'TCP被动', 2: 'TCP主动' } as Record<number, string>)[row.tcp_mode as number] || row.tcp_mode }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : row.status === 'closed' ? 'info' : 'danger'" size="small">{{ ({ running: '运行中', closed: '已关闭', failed: '失败' } as Record<string, string>)[row.status as string] || row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_error" label="错误信息" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.last_error || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-popconfirm v-if="row.status === 'running'" :title="`确定关闭 RTP 接收任务 ${row.stream_id}？`" @confirm="closeRtpTask(row.task_id)">
                  <template #reference>
                    <el-button type="danger" size="small" link>关闭</el-button>
                  </template>
                </el-popconfirm>
                <span v-else class="text-xs ops-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="SSL证书" name="ssl">
        <el-card>
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-semibold">SSL 证书管理（Let's Encrypt / Certbot）</span>
              <div class="flex gap-2">
                <el-button @click="loadSslStatus" :loading="sslLoading">刷新状态</el-button>
                <el-button type="primary" :loading="sslRenewing" @click="renewSslCert">续签证书</el-button>
              </div>
            </div>
          </template>
          <div v-if="sslStatus" v-loading="sslLoading">
            <div class="grid grid-cols-2 gap-4 mb-4">
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">启用状态</div>
                <div class="text-xl font-bold" :style="{ color: sslStatus.enabled ? 'var(--el-color-success)' : 'var(--el-text-color-secondary)' }">
                  {{ sslStatus.enabled ? '已启用' : '未启用' }}
                </div>
              </div>
              <div class="ops-status-card text-center p-4">
                <div class="ops-muted">证书状态</div>
                <div class="text-xl font-bold" :style="{ color: sslStatus.status === 'valid' ? 'var(--el-color-success)' : sslStatus.status === 'expired' ? 'var(--el-color-danger)' : 'var(--el-color-warning)' }">
                  {{ { valid: '有效', expired: '已过期', disabled: '未启用', renewing: '续签中' }[sslStatus.status] || sslStatus.status || '—' }}
                </div>
              </div>
            </div>
            <el-descriptions :column="2" border size="small" v-if="sslStatus.enabled">
              <el-descriptions-item label="域名">{{ sslStatus.domain || '—' }}</el-descriptions-item>
              <el-descriptions-item label="剩余天数">
                <span :style="{ color: (sslStatus.remaining_days ?? 0) < 30 ? 'var(--el-color-danger)' : 'var(--el-color-success)' }">
                  {{ sslStatus.remaining_days != null ? `${sslStatus.remaining_days} 天` : '—' }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="生效时间">{{ sslStatus.not_before || '—' }}</el-descriptions-item>
              <el-descriptions-item label="过期时间">{{ sslStatus.not_after || '—' }}</el-descriptions-item>
              <el-descriptions-item label="证书路径">{{ sslStatus.cert_path || '—' }}</el-descriptions-item>
              <el-descriptions-item label="上次续签">{{ sslStatus.last_renew_at || '—' }}</el-descriptions-item>
              <el-descriptions-item label="上次检查">{{ sslStatus.last_check_at || '—' }}</el-descriptions-item>
              <el-descriptions-item label="错误信息">
                <span v-if="sslStatus.error" style="color: var(--el-color-danger)">{{ sslStatus.error }}</span>
                <span v-else>—</span>
              </el-descriptions-item>
            </el-descriptions>
            <el-empty v-else description="Certbot 自动证书未启用。请在配置文件中设置 CERTBOT_DOMAIN 和 CERTBOT_EMAIL 后重启服务。" />
          </div>
          <el-empty v-else-if="!sslLoading" description="点击「刷新状态」查看 SSL 证书信息" />
        </el-card>
      </el-tab-pane>

      </el-tabs>
    </PageContainer>

    <AppDialog v-model="mediaDialogVisible" :title="editingMediaId ? '编辑媒体节点' : '新增媒体节点'" size="large">
      <el-form :model="mediaForm" ref="mediaFormRef" :rules="mediaRules" label-width="120px">
        <el-form-item label="IP" prop="ip"><el-input v-model="mediaForm.ip" placeholder="请输入节点内网 IP，例如 10.0.0.88" /></el-form-item>
        <el-form-item label="公网IP" prop="public_ip"><el-input v-model="mediaForm.public_ip" placeholder="请输入节点公网 IP（无公网可填内网 IP）" /></el-form-item>
        <el-form-item label="流IP/域名" prop="stream_ip"><el-input v-model="mediaForm.stream_ip" placeholder="流地址对外访问域名或 IP，优先级高于公网 IP" /></el-form-item>

        <el-form-item label="HTTP端口" prop="http_port"><el-input-number v-model="mediaForm.http_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="HTTPS端口" prop="https_port"><el-input-number v-model="mediaForm.https_port" :min="0" :max="65535" /></el-form-item>
        <template v-if="mediaForm.is_embedded && editingMediaId">
          <el-divider content-position="left">内置 ZLM HTTPS 证书</el-divider>
          <p class="text-xs mb-2 ops-muted ops-leading">
            与
            <a href="https://docs.zlmediakit.com/guide/media_server/how_to_enable_https_related_functions.html" target="_blank" rel="noopener noreferrer">ZLMediaKit 文档</a>
            一致：可粘贴<strong>合并 PEM</strong>（私钥 + 证书链），或分别填写私钥与证书链后保存。保存后需<strong>重启后端</strong>使内置 MediaServer 带上 <code>-s</code> 加载证书；并请将 HTTPS 端口设为非 0（如 8443）。
          </p>
          <div class="flex items-center gap-2 mb-2">
            <el-tag v-if="mediaSslConfigured" type="success" size="small">数据库中已有证书</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">尚未保存证书</el-tag>
          </div>
          <el-form-item label="合并 PEM">
            <el-input v-model="mediaSslMerged" type="textarea" :rows="5" placeholder="-----BEGIN PRIVATE KEY----- ... -----END CERTIFICATE-----" class="font-mono text-xs" />
          </el-form-item>
          <el-form-item label="或：私钥 PEM">
            <el-input v-model="mediaSslKey" type="textarea" :rows="4" placeholder="-----BEGIN PRIVATE KEY----- ..." class="font-mono text-xs" />
          </el-form-item>
          <el-form-item label="或：证书链 PEM">
            <el-input v-model="mediaSslCert" type="textarea" :rows="4" placeholder="-----BEGIN CERTIFICATE----- ...（可含多段）" class="font-mono text-xs" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="mediaSslSaving" :disabled="!editingMediaId" @click="saveMediaZlmSsl">保存证书</el-button>
            <el-button type="danger" plain :loading="mediaSslSaving" :disabled="!editingMediaId || !mediaSslConfigured" @click="clearMediaZlmSsl">清除证书</el-button>
          </el-form-item>
        </template>
        <el-form-item label="RTSP端口" prop="rtsp_port"><el-input-number v-model="mediaForm.rtsp_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="RTSPS端口" prop="rtsps_port"><el-input-number v-model="mediaForm.rtsps_port" :min="0" :max="65535" /></el-form-item>
        <el-form-item label="RTMP端口" prop="rtmp_port"><el-input-number v-model="mediaForm.rtmp_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="RTMPS端口" prop="rtmps_port"><el-input-number v-model="mediaForm.rtmps_port" :min="0" :max="65535" /></el-form-item>

        <el-form-item label="HOOK 基础地址">
          <el-input v-model="mediaForm.hook_base_url" placeholder="可选：覆盖 Hook 回调地址，如 http://public-host:8000/api/v1/hook" />
        </el-form-item>
        <el-form-item label="HOOK IP"><el-input v-model="mediaForm.hook_ip" placeholder="可选：节点侧连通后端用的 IP" /></el-form-item>
        <el-form-item label="SDP IP"><el-input v-model="mediaForm.sdp_ip" placeholder="可选：写入 SDP 的对外 IP（NAT）" /></el-form-item>

        <el-form-item label="收流端口模式">
          <el-radio-group v-model="mediaForm.rtp_port_mode">
            <el-radio-button value="single">单端口</el-radio-button>
            <el-radio-button value="range">多端口</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="收流端口">
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

        <el-form-item label="录像管理端口">
          <el-input-number v-model="mediaForm.record_mgr_port" :min="0" :max="65535" />
        </el-form-item>
        
        <el-form-item label="分片大小估算">
          <div class="flex items-center gap-2">
            <el-input-number v-model="targetFileSizeMB" :min="1" :max="500" :step="10" size="small" class="ops-input-120" />
            <span class="text-xs text-slate-500">MB (按2Mbps码率估算)</span>
            <el-button size="small" type="primary" link @click="applyEstimatedSeconds">应用估算值: {{ Math.round(targetFileSizeMB * 8 / 2) }}秒</el-button>
          </div>
        </el-form-item>

        <el-form-item label="MP4分片秒数">
          <el-input-number v-model="mediaForm.protocol_mp4_max_second" :min="30" :max="86400" />
        </el-form-item>
        <el-form-item label="record.fileSecond">
          <el-input-number v-model="mediaForm.record_file_second" :min="30" :max="86400" />
        </el-form-item>
        <el-form-item label="record.sampleMS">
          <el-input-number v-model="mediaForm.record_sample_ms" :min="100" :max="10000" />
        </el-form-item>

        <el-form-item label="密钥"><el-input v-model="mediaForm.secret" placeholder="与 ZLM 配置一致" /></el-form-item>
        <el-form-item label="自动配置媒体服务">
          <el-switch v-model="mediaForm.auto_config_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mediaDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveMediaNode">保存</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="leaseDialogVisible" title="RTP 端口租约" size="large">
      <div class="flex gap-2 items-center mb-3">
        <el-select v-model="leaseFilterNodeId" placeholder="全部节点" clearable class="ops-lease-select">
          <el-option v-for="n in mediaNodes" :key="n.id" :label="`${n.ip || n.id}${n.is_active ? '（活动）' : ''}`" :value="n.id" />
        </el-select>
        <el-switch v-model="leaseOnlyUnbound" active-text="仅孤儿租约" />
        <span class="text-xs ops-muted">最多</span>
        <el-input-number v-model="leaseLimit" :min="1" :max="1000" size="small" />
        <el-button :loading="leasesLoading" @click="loadLeases">刷新</el-button>
      </div>
      <el-table :data="leaseItems" border size="small" :empty-text="'暂无租约'" fit>
        <el-table-column prop="media_server_id" label="节点ID" width="160" />
        <el-table-column prop="port" label="端口" width="100" />
        <el-table-column label="绑定状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.stream_session_id ? 'success' : 'warning'" effect="plain">
              {{ row.stream_session_id ? '已绑定' : '未绑定' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="stream_session_id" label="会话 ID" min-width="160" />
        <el-table-column prop="leased_at" label="租约时间" min-width="180" />
      </el-table>
      <template #footer>
        <el-button @click="leaseDialogVisible = false">关闭</el-button>
        <el-button type="warning" plain @click="openLeaseCleanupDialog()">清理孤儿租约</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="leaseCleanupVisible" title="清理孤儿租约" size="small">
      <div class="text-sm mb-3 ops-muted">
        仅清理“未绑定会话且超过时间阈值”的租约，用于兜底回收端口池。
      </div>
      <el-form label-width="140px">
        <el-form-item label="超过秒数">
          <el-input-number v-model="leaseCleanupMaxAgeSeconds" :min="60" :max="86400" />
        </el-form-item>
        <el-form-item label="最多清理条数">
          <el-input-number v-model="leaseCleanupLimit" :min="1" :max="5000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="leaseCleanupVisible = false">取消</el-button>
        <el-button type="warning" :loading="cleaningLeases" @click="cleanupLeases">开始清理</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="rtpOpenDialogVisible" title="开启 RTP 接收" size="small">
      <el-form :model="rtpOpenForm" label-width="100px">
        <el-form-item label="流ID" required>
          <el-input v-model="rtpOpenForm.stream_id" placeholder="例如：rtp_stream_001" />
        </el-form-item>
        <el-form-item label="应用名">
          <el-input v-model="rtpOpenForm.app" placeholder="默认 live" />
        </el-form-item>
        <el-form-item label="SSRC">
          <el-input v-model="rtpOpenForm.ssrc" placeholder="可选；留空由系统自动分配" />
        </el-form-item>
        <el-form-item label="TCP模式">
          <el-select v-model="rtpOpenForm.tcp_mode">
            <el-option :value="0" label="UDP（默认）" />
            <el-option :value="1" label="TCP 被动" />
            <el-option :value="2" label="TCP 主动" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rtpOpenDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="rtpOpening" @click="openRtpReceive">开启</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="portPoolDialogVisible" title="端口池状态" size="medium">
      <el-table :data="portPoolStatus" v-loading="portPoolLoading" border size="small" empty-text="暂无数据">
        <el-table-column prop="node_ip" label="节点IP" width="140" />
        <el-table-column prop="protocol" label="协议" width="100" />
        <el-table-column prop="total" label="总端口数" width="100" />
        <el-table-column prop="used" label="已用" width="80" />
        <el-table-column prop="free" label="空闲" width="80" />
        <el-table-column label="使用率" width="120">
          <template #default="{ row }">
            <el-progress :percentage="Number(row.total) > 0 ? Math.round(Number(row.used) / Number(row.total) * 100) : 0" :stroke-width="14" :text-inside="true" size="small" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="portPoolDialogVisible = false">关闭</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="ffmpegDialogVisible" title="FFmpeg 命令管理" size="large">
      <div class="mb-3">
        <el-button type="primary" size="small" @click="openFfmpegCmdDialog()">新增命令</el-button>
      </div>
      <el-table :data="ffmpegCmds" v-loading="ffmpegLoading" border size="small" empty-text="暂无 FFmpeg 命令">
        <el-table-column prop="name" label="名称" width="160" />
        <el-table-column prop="protocol" label="协议" width="100" />
        <el-table-column prop="cmd" label="命令模板" min-width="300" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openFfmpegCmdDialog(row)">编辑</el-button>
            <el-popconfirm :title="`确定删除命令「${row.name}」？`" @confirm="deleteFfmpegCmd(row.id)">
              <template #reference>
                <el-button size="small" link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="ffmpegDialogVisible = false">关闭</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="ffmpegCmdDialogVisible" :title="editingFfmpegCmdId ? '编辑 FFmpeg 命令' : '新增 FFmpeg 命令'" size="small">
      <el-form :model="ffmpegCmdForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="ffmpegCmdForm.name" placeholder="命令名称" />
        </el-form-item>
        <el-form-item label="协议">
          <el-input v-model="ffmpegCmdForm.protocol" placeholder="如 rtsp, rtmp, hls" />
        </el-form-item>
        <el-form-item label="命令模板" required>
          <el-input v-model="ffmpegCmdForm.cmd" type="textarea" :rows="4" placeholder="FFmpeg 命令模板，可用 {src} {dst} 等占位符" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ffmpegCmdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingFfmpegCmd" @click="saveFfmpegCmd">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import api from '@/utils/http'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { getFriendlyError, getApiErrorMessage } from '../utils/errorMessage'
import { useRoute } from 'vue-router'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'

const route = useRoute()
const activeTab = ref(String(route.query.tab || 'status'))
const status = ref({
  cpu: 0,
  memory_percent: 0,
  zlm_status: '检查中',
  zlm_streams: 0,
  zlm_node_id: '',
  zlm_select_reason: 'global',
  zlm_select_reason_label: '使用全局配置',
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
    ElMessage.error(getApiErrorMessage(e, '获取历史日志列表失败'))
  } finally {
    historyLogsLoading.value = false
  }
}

const viewLogLines = (row: Record<string, unknown>) => {
  currentLogFile.value = row.name
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
    currentLogLines.value = [`加载失败: ${getApiErrorMessage(e, '')}`]
    logTotal.value = 0
  } finally {
    logLinesLoading.value = false
  }
}

const downloadLog = async (row: Record<string, unknown>) => {
  try {
    const res = await api.get(`/api/v1/logs/files/${encodeURIComponent(row.name).replace(/%2F/g, '/')}/download`, {
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', row.name.split('/').pop() || row.name)
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
const TRACE_COLUMN_STORAGE_KEY = 'ops_trace_visible_columns_v1'
const traceColumnOptions = [
  { key: 'platform_id', label: '平台' },
  { key: 'device_id', label: '设备' },
  { key: 'channel_id', label: '通道' }
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
  ip: [{ required: true, message: '请输入节点 IP', trigger: 'blur' }],
  public_ip: [{ required: true, message: '请输入公网 IP（无公网可填内网 IP）', trigger: 'blur' }],
  stream_ip: [{ required: true, message: '请输入流访问 IP 或域名', trigger: 'blur' }],
  http_port: [{ required: true, message: '请输入 HTTP 端口', trigger: 'blur' }],
  rtsp_port: [{ required: true, message: '请输入 RTSP 端口', trigger: 'blur' }],
  rtmp_port: [{ required: true, message: '请输入 RTMP 端口', trigger: 'blur' }]
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
  ElMessage.success(`已将分片秒数设为 ${seconds} 秒`)
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
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
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
    status.value.zlm_status = '离线'
  }
}

const initWebSocket = () => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.host
  if (wsReconnectTimer != null) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  const sp = new URLSearchParams()
  if (String(logContains.value || '').trim()) sp.set('contains', String(logContains.value || '').trim())
  if (String(logContainsAny.value || '').trim()) sp.set('contains_any', String(logContainsAny.value || '').trim())
  const qs = sp.toString()
  // FIXED-P1: R3-01 日志WebSocket连接添加token认证参数
  const tokenParam = `token=${encodeURIComponent(localStorage.getItem('token') || '')}`
  ws = new WebSocket(`${protocol}://${host}/api/v1/logs/ws/logs${qs ? `?${qs}&${tokenParam}` : `?${tokenParam}`}`)
  ws.onopen = () => {
    wsConnected.value = true
    wsReconnecting.value = false
    wsReconnectAttempts = 0
    logs.value.push('--- 已连接日志流 ---')
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
    logs.value.push('--- 已断开 ---')
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
  logs.value.push('--- 已应用过滤，重连日志流 ---')
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
  editingMediaId.value = row?.id || ''
  mediaSslMerged.value = ''
  mediaSslCert.value = ''
  mediaSslKey.value = ''
  mediaSslConfigured.value = !!row?.zlm_ssl_configured
  mediaForm.value = row ? {
    ip: row.ip || '',
    public_ip: row.public_ip || '',
    stream_ip: row.stream_ip || '',
    hook_base_url: row.hook_base_url || '',
    hook_ip: row.hook_ip || '',
    sdp_ip: row.sdp_ip || '',
    http_port: row.http_port || 8880,
    https_port: row.https_port || 0,
    rtsp_port: row.rtsp_port || 554,
    rtsps_port: row.rtsps_port || 0,
    rtmp_port: row.rtmp_port || 1935,
    rtmps_port: row.rtmps_port || 0,
    rtp_proxy_port: row.rtp_proxy_port || 30000,
    rtp_port_mode: row.rtp_port_mode || 'single',
    rtp_port_range_start: row.rtp_port_range_start || 30000,
    rtp_port_range_end: row.rtp_port_range_end || 39000,
    record_mgr_port: row.record_mgr_port || 0,
    protocol_mp4_max_second: row.protocol_mp4_max_second || 300,
    record_file_second: row.record_file_second || 300,
    record_sample_ms: row.record_sample_ms || 500,
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
    ElMessage.success('证书已保存，请重启后端使内置 ZLM 加载证书')
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
    await ElMessageBox.confirm('确定清除该内置节点已保存的 ZLM 证书？重启后端后生效。', '确认', { type: 'warning' })
  } catch {
    return
  }
  mediaSslSaving.value = true
  try {
    await api.delete(`/api/v1/integrations/media-nodes/${editingMediaId.value}/zlm-ssl`)
    ElMessage.success('已清除证书')
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
    ElMessage.success(editingMediaId.value ? '媒体节点已更新' : '媒体节点已创建')
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
      ElMessage.warning('未生成配置片段')
      return
    }
    await copyText(snippet)
    ElMessage.success('ZLM 配置片段已复制')
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
      ElMessage.warning('未生成 ENV 片段')
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
    ElMessage.success(`已清理 ${Number(res.data?.cleaned ?? 0)} 条孤儿租约`)
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
    ElMessage.success(`批量测试完成：在线 ${onlineCount}/${items.length}`)
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
    const t = new Date(iso).getTime()
    if (!Number.isFinite(t)) return iso
    const diff = Date.now() - t
    if (diff < 0) return iso
    const sec = Math.floor(diff / 1000)
    if (sec < 10) return '刚刚'
    if (sec < 60) return `${sec}s 前`
    const min = Math.floor(sec / 60)
    if (min < 60) return `${min}min 前`
    const hr = Math.floor(min / 60)
    if (hr < 48) return `${hr}h 前`
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
    ElMessage.success(online ? '节点在线' : '节点离线')
    if (hookBase) {
      ElMessage.info(`Hook回调地址：${hookBase}`)
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
    await ElMessageBox.confirm('删除后不可恢复，是否继续？', '删除媒体节点', { type: 'warning' })
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
    await openLeaseDialog(row.id)
    return
  }
  if (cmd === 'copyHook') {
    await copyMediaNodeHookUrls(row.id)
    return
  }
  if (cmd === 'copyZlm') {
    await copyMediaNodeZlmSnippet(row.id)
    return
  }
  if (cmd === 'activate') {
    await activateMediaNode(row.id)
    return
  }
  if (cmd === 'delete') {
    await deleteMediaNode(row.id)
  }
}

const shutdownService = async () => {
  try {
    await ElMessageBox.confirm('确认关闭服务进程？该操作会导致当前站点立即不可用。', '提示', { type: 'warning' })
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
        lines.push({ text: `数据库：${ok ? '连接正常' : '连接异常'}`, ok })
      } catch {
        lines.push({ text: '数据库：检查失败或未配置', ok: false })
      }
      try {
        const netRes = await api.get('/api/v1/network/summary')
        const d = netRes.data || {}
        lines.push({
          text: `网络概况：设备 ${d.device_total ?? 0} 台，在线 ${d.device_online ?? 0}，当前流 ${d.stream_count ?? 0}`,
          ok: true
        })
      } catch {
        lines.push({ text: '网络概况：获取失败', ok: false })
      }
      lines.push({
        text: `流媒体(ZLM)：${status.value.zlm_status === 'Online' ? '在线' : '离线'}，当前流数 ${status.value.zlm_streams ?? 0}；目标 ${status.value.zlm_target || '-'}；来源 ${status.value.zlm_select_reason_label || status.value.zlm_select_reason || '使用全局配置'}${status.value.zlm_node_id ? `；node_id=${status.value.zlm_node_id}` : ''}`,
        ok: status.value.zlm_status === 'Online'
      })
    }
    diagnoseLines.value = lines
  } finally {
    diagnoseLoading.value = false
  }
}

const exportDiagnoseReport = () => {
  const title = 'PyGBSentry 一键诊断报告'
  const time = diagnoseGeneratedAt.value || new Date().toLocaleString('zh-CN')
  const body = [
    `summary: ${diagnoseSummary.value}`,
    `generated_at: ${time}`,
    '',
    ...diagnoseLines.value.map((l) => (l.ok ? '[OK]' : l.level === 'error' ? '[ERROR]' : '[WARN]') + ' ' + l.text)
  ].join('\n')
  const blob = new Blob([`${title}\n生成时间: ${time}\n\n${body}\n`], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `diagnose-${new Date().toISOString().slice(0, 10)}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

const diagnoseSummaryLabel = computed(() => {
  if (diagnoseSummary.value === 'error') return '异常'
  if (diagnoseSummary.value === 'warn') return '存在告警'
  return '正常'
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
    await ElMessageBox.confirm('确定创建数据库备份？备份过程中系统正常运行。', '创建备份', { type: 'info', confirmButtonText: '确定', cancelButtonText: '取消' })
  } catch { return }
  backupLoading.value = true
  try {
    const res = await api.post('/api/v1/ops/backup')
    ElMessage.success(`备份成功：${res.data?.filename || ''}（${res.data?.tables || 0} 张表）`)
    await loadBackupList()
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    backupLoading.value = false
  }
}

const restoreBackup = async (filename: string) => {
  try {
    await ElMessageBox.confirm(`此操作将使用备份「${filename}」覆盖当前数据库，恢复后需重启服务。确定继续？`, '危险操作', { type: 'error', confirmButtonText: '确定恢复', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    const res = await api.post('/api/v1/ops/restore', null, { params: { filename } })
    ElMessage.success(`恢复成功：${res.data?.tables_restored || 0} 张表已恢复`)
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
    ElMessage.warning('请输入流ID')
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
    ElMessage.success(`RTP 接收已开启，端口：${port}${publicHost ? `，对外地址：${publicHost}:${port}` : ''}`)
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
    await ElMessageBox.confirm('确定续签 SSL 证书？续签过程可能需要几分钟。', '续签证书', { type: 'info' })
  } catch { return }
  sslRenewing.value = true
  try {
    const res = await api.post('/api/v1/ssl-cert/renew')
    if (res.data?.success) {
      ElMessage.success(res.data?.message || '证书续签成功')
    } else {
      ElMessage.error(res.data?.message || '证书续签失败')
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
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
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
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  } finally {
    ffmpegLoading.value = false
  }
}

const openFfmpegCmdDialog = (row?: Record<string, unknown>) => {
  if (row) {
    editingFfmpegCmdId.value = String(row.id || '')
    ffmpegCmdForm.value = { name: row.name || '', protocol: row.protocol || '', cmd: row.cmd || '' }
  } else {
    editingFfmpegCmdId.value = ''
    ffmpegCmdForm.value = { name: '', protocol: '', cmd: '' }
  }
  ffmpegCmdDialogVisible.value = true
}

const saveFfmpegCmd = async () => {
  if (!ffmpegCmdForm.value.name.trim()) { ElMessage.warning('请输入命令名称'); return }
  savingFfmpegCmd.value = true
  try {
    if (editingFfmpegCmdId.value) {
      await api.put(`/api/v1/integrations/ffmpeg_cmd/${editingFfmpegCmdId.value}`, ffmpegCmdForm.value)
    } else {
      await api.post('/api/v1/integrations/ffmpeg_cmd', ffmpegCmdForm.value)
    }
    ElMessage.success('保存成功')
    ffmpegCmdDialogVisible.value = false
    await showFfmpegCmds()
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
  } finally {
    savingFfmpegCmd.value = false
  }
}

const deleteFfmpegCmd = async (id: string) => {
  try {
    await ElMessageBox.confirm('确定删除该 FFmpeg 命令模板？', '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/api/v1/integrations/ffmpeg_cmd/${id}`)
    ElMessage.success(t('ops.commandDeleted'))  // FIXED: 硬编码中文→i18n
    await showFfmpegCmds()
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? `${f.message}（${f.suggestion}）` : f.message)
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
  if (cascadeOverallLevel.value === 'error') return '级联存在异常'
  if (cascadeOverallLevel.value === 'warn') return '级联需要注意'
  return '级联状态正常'
})

const cascadeOverallDesc = computed(() => {
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  const diags = cascadeDiagnosis.value?.diagnostics || []
  const errorCount = diags.filter((d: Record<string, unknown>) => d.level === 'error').length
  const warnCount = diags.filter((d: Record<string, unknown>) => d.level === 'warn').length
  if (platforms.length === 0) return '暂无下级平台连接到本平台'
  const parts = [`${platforms.length} 个下级平台已连接`]
  if (errorCount > 0) parts.push(`${errorCount} 个异常`)
  if (warnCount > 0) parts.push(`${warnCount} 个警告`)
  return parts.join('，')
})

const cascadeStepActive = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  if (counts.register_received > 0) {
    if (counts.register_401_challenge > 0) {
      if (counts.register_ok_platform > 0 || counts.register_ok_device > 0 || platforms.some((p: Record<string, unknown>) => p.register?.last_ok_at)) {
        if (platforms.some((p: Record<string, unknown>) => p.keepalive?.last_at)) {
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
  if (counts.register_received > 0) return `已收到 ${counts.register_received} 次`
  return '未收到请求'
})

const cascadeStep2Desc = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  if (counts.register_401_challenge > 0) return `已发出 ${counts.register_401_challenge} 次质询`
  return '—'
})

const cascadeStep3Desc = computed(() => {
  const counts = cascadeDiagnosis.value?.recent_trace_events_count || {}
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  const okCount = (counts.register_ok_platform || 0) + (counts.register_ok_device || 0)
  const registeredPlatforms = platforms.filter((p: Record<string, unknown>) => p.register?.last_ok_at).length
  if (okCount > 0 || registeredPlatforms > 0) return `${registeredPlatforms} 个平台已注册`
  if (counts.register_auth_failed > 0) return `${counts.register_auth_failed} 次验证失败`
  return '—'
})

const cascadeStep4Desc = computed(() => {
  const platforms = cascadeDiagnosis.value?.inbound_platforms || []
  const withKeepalive = platforms.filter((p: Record<string, unknown>) => p.keepalive?.last_at).length
  if (withKeepalive > 0) return `${withKeepalive} 个心跳正常`
  return '—'
})

const cascadeAuthLabel = (auth: string | undefined) => {
  if (!auth) return '未认证'
  const a = String(auth).toLowerCase()
  if (a.includes('digest')) return '摘要认证'
  if (a.includes('basic')) return '基础认证'
  if (a === 'none' || a === '') return '无需认证'
  return auth
}

const cascadeEventLabel = (event: string) => {
  const map: Record<string, string> = {
    'register_received': '收到注册',
    'register_401_challenge': '要求验证身份',
    'register_ok_platform': '平台注册成功',
    'register_ok_device': '设备注册成功',
    'register_auth_failed': '验证失败',
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
  { key: 'zlm_api', label: 'ZLM API 连通性' },
  { key: 'stream_list', label: '流列表检查' },
  { key: 'hook_callback', label: 'Hook 回调检查' },
  { key: 'play_address', label: '播放地址构造' },
  { key: 'nginx_proxy', label: 'Nginx 反向代理' },
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
    `PyGBSentry 流媒体诊断报告 - ${new Date().toLocaleString('zh-CN')}`,
    `节点: ${diagNodeId.value || '默认活动节点'}`,
    `通道: ${diagChannelId.value || '全部'}`,
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
