<template>
  <div class="app-page space-y-4 ">
    <PageContainer>
      <template #header>
        <PageHeader title="报表中心" description="内置统计报表 + 私有化模板扩展" />
      </template>
      <TableCard>
    <el-tabs v-model="activeTab" type="border-card" class="border-0">
      <el-tab-pane label="平台摘要" name="summary">
        <div class="space-y-4">
          <div class="flex flex-wrap justify-between items-center gap-2">
            <span class="text-lg font-semibold" style="color: var(--el-text-color-regular)">运行概览</span>
            <div class="flex flex-wrap gap-2">
              <el-button type="primary" size="small" @click="exportCsv('summary')">导出表格</el-button>
              <el-button type="primary" size="small" @click="exportPdf('summary')">导出文档</el-button>
            </div>
          </div>
          
          <div v-if="loading" class="py-8 flex justify-center">
            <el-icon class="is-loading text-2xl" style="color: var(--el-text-color-secondary)" :size="28"><Loading /></el-icon>
          </div>
          <div v-else-if="summaryError" class="py-10 text-center space-y-2" style="color: var(--el-text-color-secondary)">
            <div>{{ summaryError }}</div>
            <el-button size="small" type="primary" @click="reloadSummary">重试</el-button>
          </div>
          <div v-else-if="!items.length" class="py-10 text-center" style="color: var(--el-text-color-secondary)">
            暂无运行概览数据，请检查后端报表接口是否正常
          </div>
          <div v-else-if="isMobileRoute" class="grid grid-cols-1 gap-2">
            <div
              v-for="row in items"
              :key="row.name"
              class="rounded-xl p-3 flex items-center justify-between gap-3"
              style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)"
            >
              <div class="min-w-0">
                <div class="text-sm truncate" style="color: var(--el-text-color-regular)" :title="row.name">{{ row.name }}</div>
                <div class="text-[11px] mt-1 truncate" style="color: var(--el-text-color-secondary)" :title="row.updated_at || ''">
                  更新时间：{{ row.updated_at || '-' }}
                </div>
              </div>
              <div class="shrink-0 text-right">
                <div class="font-mono font-bold text-lg" style="color: var(--el-text-color-regular)">{{ row.value ?? '-' }}</div>
              </div>
            </div>
          </div>
          <div v-else class="overflow-x-auto">
            <el-table :data="items" stripe style="width: 100%">
              <el-table-column prop="name" label="指标" />
              <el-table-column prop="value" label="数值" width="120">
                <template #default="{ row }">
                  <span class="font-mono font-bold text-lg">{{ row.value }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="updated_at" label="更新时间" width="220" />
            </el-table>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="报表明细" name="details">
        <div class="space-y-4">
          <div class="flex flex-wrap justify-between items-center gap-2">
            <div class="flex items-center gap-2">
              <span class="text-lg font-semibold" style="color: var(--el-text-color-regular)">可用报表清单</span>
              <el-tag size="small" type="info">总计 {{ filteredReports.length }} / {{ reports.length }} 个</el-tag>
            </div>
            <div class="flex flex-wrap gap-2">
              <el-button size="small" @click="selectedReportIds = []">清空选择</el-button>
              <el-button size="small" type="primary" :disabled="selectedReportIds.length === 0 || !!exportLoading" @click="batchExportSelected">
                一键导出已选（{{ selectedReportIds.length }}）
              </el-button>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <el-input v-model="reportKeyword" placeholder="按报表ID/名称筛选" clearable style="max-width: 320px" />
            <el-select v-model="detailSourceFilter" clearable placeholder="来源筛选" style="width: 140px">
              <el-option label="内置" value="builtin" />
              <el-option label="扩展" value="external" />
            </el-select>
          </div>
          <div v-if="isMobileRoute" class="space-y-2">
            <div
              v-for="row in filteredReports"
              :key="row.id"
              class="rounded-xl p-3"
              style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="text-sm truncate" style="color: var(--el-text-color-regular)" :title="row.name">{{ row.name }}</div>
                  <div class="text-[11px] mt-1 truncate" style="color: var(--el-text-color-secondary)">ID：{{ row.id }}</div>
                </div>
                <el-tag size="small" :type="row.source === 'builtin' ? 'success' : 'warning'">
                  {{ row.source === 'builtin' ? '内置' : '扩展' }}
                </el-tag>
              </div>
              <div class="mt-2 text-xs" style="color: var(--el-text-color-secondary)">
                格式：{{ (row.export_formats || []).join(', ') || '-' }}
              </div>
              <div class="mt-2">
                <el-button size="small" type="primary" :loading="exportLoading === row.id" @click="exportReport(row.id)">导出</el-button>
              </div>
            </div>
          </div>
          <el-table v-else :data="filteredReports" stripe v-loading="loading" @selection-change="onSelectionChange">
            <el-table-column type="selection" width="48" />
            <el-table-column prop="id" label="报表ID" min-width="220" />
            <el-table-column prop="name" label="报表名称" min-width="220" />
            <el-table-column prop="source" label="来源" width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="row.source === 'builtin' ? 'success' : 'warning'">
                  {{ row.source === 'builtin' ? '内置' : '扩展' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="export_formats" label="可导出格式" min-width="160">
              <template #default="{ row }">{{ (row.export_formats || []).join(', ') || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button size="small" type="primary" :loading="exportLoading === row.id" @click="exportReport(row.id)">导出</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!loading && !filteredReports.length" class="py-8 text-center text-sm" style="color: var(--el-text-color-secondary)">
            未找到匹配报表
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="报警统计" name="alarms">
        <div class="space-y-4">
          <div class="flex flex-wrap justify-between items-center gap-2">
            <span class="text-lg font-semibold" style="color: var(--el-text-color-regular)">报警类型分布</span>
            <el-button type="primary" size="small" @click="exportCsv('alarms')">导出报警记录</el-button>
          </div>

          <div v-if="loadingAlarms" class="py-10 text-center" style="color: var(--el-text-color-secondary)">加载中…</div>
          <div v-else-if="alarmError" class="py-10 text-center space-y-2" style="color: var(--el-text-color-secondary)">
            <div>{{ alarmError }}</div>
            <el-button size="small" type="primary" @click="loadAlarmStats">重试</el-button>
          </div>
          <div v-else-if="!alarmStats.length" class="py-10 text-center" style="color: var(--el-text-color-secondary)">暂无报警数据</div>
          <div v-else class="space-y-4">
            <div v-for="item in alarmStats" :key="item.name" class="flex items-center gap-4">
              <div class="w-32 text-right truncate" style="color: var(--el-text-color-regular)" :title="item.name">{{ item.name }}</div>
              <div class="flex-1">
                <el-progress 
                  :percentage="getPercentage(item.value)" 
                  :format="() => item.value" 
                  :stroke-width="18"
                  text-inside
                />
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="流量趋势" name="traffic">
        <div class="space-y-4">
          <div class="flex flex-wrap justify-between items-center gap-2">
            <span class="text-lg font-semibold" style="color: var(--el-text-color-regular)">近24小时流量趋势</span>
            <el-button type="primary" size="small" @click="exportCsv('traffic')" :loading="exportLoading">导出流量数据</el-button>
          </div>
          <div v-if="trafficLoading" class="flex justify-center py-8">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          </div>
          <template v-else-if="trafficSummary">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">平均并发流</div>
                <div class="text-xl font-bold mt-1">{{ trafficSummary.avg_streams }}</div>
              </div>
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">峰值并发流</div>
                <div class="text-xl font-bold mt-1">{{ trafficSummary.max_streams }}</div>
              </div>
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">平均带宽</div>
                <div class="text-xl font-bold mt-1">{{ formatKbps(trafficSummary.avg_bandwidth_kbps) }}</div>
              </div>
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">峰值带宽</div>
                <div class="text-xl font-bold mt-1">{{ formatKbps(trafficSummary.max_bandwidth_kbps) }}</div>
              </div>
            </div>
            <div class="grid md:grid-cols-2 gap-3">
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">并发流数</div>
                <VChart :option="trafficStreamsOption" autoresize style="height: 260px" />
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">带宽占用</div>
                <VChart :option="trafficBandwidthOption" autoresize style="height: 260px" />
              </div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4" v-if="trafficQualitySummary">
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">活跃会话</div>
                <div class="text-xl font-bold mt-1">{{ trafficQualitySummary.active_sessions }}</div>
              </div>
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">平均健康分</div>
                <div class="text-xl font-bold mt-1">{{ trafficQualitySummary.avg_health_score }}</div>
              </div>
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">异常会话</div>
                <div class="text-xl font-bold mt-1">{{ trafficQualitySummary.unhealthy_sessions }}</div>
              </div>
              <div class="rounded-lg p-3 text-center" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">质量样本点</div>
                <div class="text-xl font-bold mt-1">{{ trafficQualityTrend.length }}</div>
              </div>
            </div>
            <div class="grid md:grid-cols-2 gap-3 mt-4" v-if="trafficQualitySummary">
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">健康分趋势</div>
                <VChart :option="trafficQualityTrendOption" autoresize style="height: 260px" />
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">健康等级分布</div>
                <VChart :option="trafficQualityLevelOption" autoresize style="height: 260px" />
              </div>
            </div>
            <div class="rounded-xl p-3 mt-4" style="border: 1px solid var(--el-border-color-lighter)" v-if="trafficRiskSessions.length">
              <div class="font-medium mb-2">风险会话 Top10（低健康分优先）</div>
              <el-table :data="trafficRiskSessions" size="small" stripe>
                <el-table-column prop="session_id" label="Session ID" min-width="200" />
                <el-table-column prop="device_id" label="设备ID" min-width="140" />
                <el-table-column prop="channel_id" label="通道ID" min-width="140" />
                <el-table-column prop="health_score" label="健康分" width="100" />
                <el-table-column prop="health_level" label="等级" width="120" />
              </el-table>
            </div>
          </template>
          <el-empty v-else description="暂无流量数据" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="Closeout看板" name="closeout_dashboard">
        <div class="space-y-4">
          <div class="flex flex-wrap justify-between items-center gap-2">
            <span class="text-lg font-semibold" style="color: var(--el-text-color-regular)">Closeout 统一看板</span>
            <div class="flex flex-wrap gap-2">
              <el-select v-model="closeoutExportTemplate" size="small" style="width: 140px">
                <el-option label="默认字段" value="default" />
                <el-option label="最小字段" value="minimal" />
                <el-option label="全量字段" value="full" />
                <el-option label="自定义字段" value="custom" />
              </el-select>
              <el-select
                v-if="closeoutExportTemplate === 'custom'"
                v-model="closeoutExportCustomFields"
                multiple
                collapse-tags
                collapse-tags-tooltip
                size="small"
                placeholder="选择导出字段"
                style="width: 320px"
              >
                <el-option
                  v-for="field in closeoutExportFieldOptions"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value"
                />
              </el-select>
              <el-button size="small" type="primary" @click="exportCloseoutCsv">导出CSV</el-button>
              <el-button size="small" @click="reloadCloseoutDashboard">刷新</el-button>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <el-select v-model="closeoutEnvFilter" clearable placeholder="环境筛选" style="width: 140px">
              <el-option label="prod" value="prod" />
              <el-option label="canary" value="canary" />
              <el-option label="dev" value="dev" />
            </el-select>
            <el-input v-model="closeoutReasonFilter" clearable placeholder="报警原因码（reason_code）" style="max-width: 260px" />
            <el-input v-model="closeoutCloseoutReasonFilter" clearable placeholder="收口原因码（closeout_reason_code）" style="max-width: 320px" />
            <el-input-number v-model="closeoutDays" :min="1" :max="180" :step="1" size="small" controls-position="right" />
            <el-button size="small" type="primary" @click="reloadCloseoutDashboard">应用筛选</el-button>
          </div>
          <div v-if="closeoutSelectedDay" class="flex items-center gap-2">
            <el-tag type="success" size="small">按天筛选：{{ closeoutSelectedDay }}</el-tag>
            <el-button size="small" text @click="clearCloseoutSelectedDay">清除日期筛选</el-button>
          </div>
          <div v-if="closeoutQuickDayOptions.length" class="flex flex-wrap items-center gap-2">
            <span class="text-xs" style="color: var(--el-text-color-secondary)">快捷日期</span>
            <el-select v-model="closeoutQuickDayPreset" size="small" style="width: 160px">
              <el-option label="值班快速（5天倒序）" value="oncall" />
              <el-option label="交接核对（7天正序）" value="handover" />
              <el-option label="复盘分析（14天倒序）" value="review" />
              <el-option label="自定义" value="custom" />
            </el-select>
            <el-input-number
              v-if="closeoutQuickDayPreset === 'custom'"
              v-model="closeoutQuickDayCount"
              :min="1"
              :max="30"
              :step="1"
              size="small"
              controls-position="right"
            />
            <el-select v-if="closeoutQuickDayPreset === 'custom'" v-model="closeoutQuickDayOrder" size="small" style="width: 120px">
              <el-option label="倒序" value="desc" />
              <el-option label="正序" value="asc" />
            </el-select>
            <el-button
              v-for="day in closeoutQuickDayOptions"
              :key="`quick-day-${day}`"
              size="small"
              :type="closeoutSelectedDay === day ? 'primary' : 'default'"
              @click="applyCloseoutQuickDay(day)"
            >
              {{ day }}
            </el-button>
          </div>

          <div v-if="loadingCloseoutDashboard" class="py-10 text-center" style="color: var(--el-text-color-secondary)">加载中…</div>
          <div v-else-if="closeoutError" class="py-10 text-center space-y-2" style="color: var(--el-text-color-secondary)">
            <div>{{ closeoutError }}</div>
            <el-button size="small" type="primary" @click="reloadCloseoutDashboard">重试</el-button>
          </div>
          <div v-else class="space-y-4">
            <div class="grid md:grid-cols-4 gap-3">
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">窗口天数</div>
                <div class="mt-1 text-lg font-semibold">{{ closeoutSummary.window_days ?? '-' }}</div>
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">窗口总记录</div>
                <div class="mt-1 text-lg font-semibold">{{ closeoutSummary.total ?? 0 }}</div>
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">最新环境</div>
                <div class="mt-1 text-lg font-semibold">{{ closeoutSummary.latest?.policy_env || '-' }}</div>
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
                <div class="text-xs" style="color: var(--el-text-color-secondary)">最新收口原因</div>
                <div class="mt-1 text-lg font-semibold">{{ closeoutSummary.latest?.dashboard?.latest?.alert?.closeout_reason_code || '-' }}</div>
              </div>
            </div>

            <div class="grid md:grid-cols-2 gap-3">
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">报警原因趋势</div>
                <div v-if="closeoutReasonRows.length === 0" class="text-sm" style="color: var(--el-text-color-secondary)">暂无数据</div>
                <div v-else class="space-y-1 text-sm">
                  <div v-for="row in closeoutReasonRows" :key="`reason-${row.key}`" class="flex justify-between gap-3">
                    <span class="truncate" :title="row.key">{{ row.key }}</span>
                    <span class="font-mono">{{ row.count }}</span>
                  </div>
                </div>
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">收口原因趋势</div>
                <div v-if="closeoutCloseoutReasonRows.length === 0" class="text-sm" style="color: var(--el-text-color-secondary)">暂无数据</div>
                <div v-else class="space-y-1 text-sm">
                  <div v-for="row in closeoutCloseoutReasonRows" :key="`closeout-${row.key}`" class="flex justify-between gap-3">
                    <span class="truncate" :title="row.key">{{ row.key }}</span>
                    <span class="font-mono">{{ row.count }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="grid md:grid-cols-2 gap-3">
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">报警原因分布（柱状）</div>
                <VChart :option="closeoutReasonBarOption" autoresize style="height: 260px" @click="onCloseoutReasonBarClick" />
              </div>
              <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
                <div class="font-medium mb-2">按天趋势（折线）</div>
                <VChart :option="closeoutTrendLineOption" autoresize style="height: 260px" @click="onCloseoutTrendLineClick" />
              </div>
            </div>

            <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
              <div class="font-medium mb-2">按天趋势</div>
              <el-table :data="closeoutTrendRows" size="small" stripe>
                <el-table-column prop="day" label="日期" width="180" />
                <el-table-column prop="count" label="条数" width="120" />
              </el-table>
            </div>

            <div class="rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter)">
              <div class="flex flex-wrap justify-between items-center gap-2 mb-2">
                <div class="font-medium">明细钻取</div>
                <el-switch v-model="closeoutIncludeDashboard" active-text="返回完整dashboard" @change="reloadCloseoutDashboard" />
              </div>
              <el-table :data="closeoutDisplayItems" size="small" stripe>
                <el-table-column prop="received_at" label="接收时间" min-width="180" />
                <el-table-column prop="policy_env" label="环境" width="100" />
                <el-table-column prop="reason_code" label="报警原因码" min-width="180" />
                <el-table-column prop="closeout_reason_code" label="收口原因码" min-width="220" />
                <el-table-column prop="run_id" label="Run ID" min-width="120" />
              </el-table>
              <div class="flex justify-end mt-3">
                <el-pagination
                  v-model:current-page="closeoutPage"
                  v-model:page-size="closeoutPageSize"
                  :total="closeoutTotal"
                  layout="total, prev, pager, next"
                  :page-sizes="[10, 20, 50]"
                  size="small"
                  @current-change="loadCloseoutDashboardDrilldown"
                  @size-change="onCloseoutPageSizeChange"
                />
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane v-if="canUseReportSuite" label="更多报表" name="extensions">
        <div class="space-y-4">
          <div class="grid md:grid-cols-3 gap-3">
            <el-tooltip content="对接外部报表服务的 API 地址，导出时会 POST 请求该地址获取报表数据" placement="top">
              <el-input v-model="reportSuiteConfig.connector_url" placeholder="报表连接器地址（如 https://report-api/export）" class="md:col-span-2" clearable />
            </el-tooltip>
            <div class="flex flex-wrap gap-2">
              <el-button @click="testReportConnector">测试连接器</el-button>
              <el-button type="primary" @click="saveReportSuiteConfig(false)">保存模板</el-button>
              <el-button type="success" @click="saveReportSuiteConfig(true)">保存并发布</el-button>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <el-switch v-model="reportSuiteConfig.enabled" active-text="启用报表插件模板" />
            <span class="text-sm" style="color: var(--el-text-color-secondary)">草稿ID：{{ reportSuiteDraftId || '-' }}</span>
          </div>
          <div class="flex gap-2">
            <el-button size="small" type="primary" @click="openTemplateDialog()">新增模板</el-button>
            <el-button size="small" :loading="loadingConfig" @click="loadReportSuiteConfig">重载配置</el-button>
          </div>
          <el-input v-model="templateKeyword" placeholder="按模板ID/名称筛选" clearable style="max-width: 320px" />
          <div v-if="isMobileRoute" class="space-y-2">
            <div
              v-for="row in paginatedExtensionReports"
              :key="row.id"
              class="rounded-xl p-3"
              style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-sm truncate" style="color: var(--el-text-color-regular)" :title="row.name">{{ row.name }}</div>
                  <div class="text-[11px] mt-1 truncate" style="color: var(--el-text-color-secondary)" :title="row.id">ID：{{ row.id }}</div>
                  <div class="mt-1">
                    <el-tag size="small" type="success">插件：report_suite</el-tag>
                    <span class="ml-2 text-[11px]" style="color: var(--el-text-color-secondary)">
                      格式：{{ (row.export_formats || []).join(', ') || '-' }}
                    </span>
                  </div>
                </div>
                <div class="shrink-0 flex flex-col gap-2">
                  <el-button size="small" @click="openTemplateDialog(row)">编辑</el-button>
                  <el-button
                    size="small"
                    type="primary"
                    :loading="exportLoading === row.id"
                    @click="exportReport(row.id)"
                  >
                    导出
                  </el-button>
                  <el-button size="small" text @click="toggleMobileRow(row.id)">
                    {{ mobileExpanded[row.id] ? '收起' : '展开' }}
                  </el-button>
                </div>
              </div>
              <div v-if="mobileExpanded[row.id]" class="mt-2 text-xs space-y-1" style="color: var(--el-text-color-secondary)">
                <div>来源：report_suite</div>
                <div>导出接口：`/api/v1/reports/export?type={{ row.id }}`</div>
              </div>
            </div>
            <div v-if="filteredExtensionReports.length === 0" class="text-xs py-6 text-center" style="color: var(--el-text-color-secondary)">
              暂无模板
            </div>
          </div>
          <div v-else class="overflow-x-auto">
            <el-table :data="paginatedExtensionReports" stripe>
              <el-table-column prop="id" label="报表ID" width="220" />
              <el-table-column prop="name" label="报表名称" />
              <el-table-column prop="source" label="来源" width="140">
                <template #default="{ row }">
                  <el-tag size="small" type="success">插件：report_suite</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="export_formats" label="导出格式">
                <template #default="{ row }">
                  <span>{{ (row.export_formats || []).join(', ') }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="160">
                <template #default="{ row }">
                  <div class="flex flex-wrap gap-1">
                    <el-button size="small" @click="openTemplateDialog(row)">编辑</el-button>
                    <el-button size="small" type="primary" :loading="exportLoading === row.id" @click="exportReport(row.id)">导出</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="flex justify-end mt-4 pagination-wrapper" v-if="filteredExtensionReports.length > 0">
            <el-pagination
              v-model:current-page="extensionReportsPage"
              v-model:page-size="extensionReportsPageSize"
              :total="filteredExtensionReports.length"
              layout="total, sizes, prev, pager, next, jumper"
              :page-sizes="[10, 20, 50, 100]"
              prev-text="上一页"
              next-text="下一页"
              size="small"
            />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
    <div v-if="exportTasks.length > 0" class="mt-4 rounded-xl p-3" style="border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light)">
      <div class="flex items-center justify-between">
        <div class="font-medium">导出任务队列</div>
        <el-button size="small" text @click="clearDoneTasks">清理已完成</el-button>
      </div>
      <div class="mt-2 space-y-2 text-sm">
        <div v-for="task in exportTasks.slice(0, 5)" :key="task.id" class="flex items-center justify-between gap-3">
          <div class="truncate">{{ task.name }}</div>
          <div class="shrink-0">
            <el-tag size="small" :type="task.status === 'success' ? 'success' : (task.status === 'failed' ? 'danger' : 'info')">
              {{ task.statusText }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>
      </TableCard>
    </PageContainer>
    <AppDialog v-model="templateDialogVisible" title="报表模板" size="medium">
      <el-form :model="templateForm" label-width="90px">
        <el-form-item label="模板ID">
          <el-input v-model="templateForm.id" placeholder="如 patrol_summary" />
        </el-form-item>
        <el-form-item label="模板名称">
          <el-input v-model="templateForm.name" placeholder="如 巡检统计报表" />
        </el-form-item>
        <el-form-item label="导出格式">
          <el-select v-model="templateForm.export_formats" multiple style="width: 100%">
            <el-option label="CSV" value="csv" />
            <el-option label="XLSX" value="xlsx" />
            <el-option label="PDF" value="pdf" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="templateEditIndex >= 0" type="danger" @click="removeTemplate">删除</el-button>
        <el-button @click="templateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmTemplate">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { getFriendlyError } from '../utils/errorMessage'
import AppDialog from '../components/common/AppDialog.vue'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'
import { logger } from '@/utils/logger'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent])

const route = useRoute()
const router = useRouter()
const isMobileRoute = computed(() => String(route.path || '').startsWith('/m/'))

const activeTab = ref('summary')
const loading = ref(true)
const loadingAlarms = ref(false)
const summaryError = ref('')
const alarmError = ref('')
const items = ref<{ name: string; value?: number; updated_at?: string }[]>([])
const reports = ref<{ id: string; name: string; source: string; export_formats?: string[] }[]>([])
const alarmStats = ref<{ name: string; value: number }[]>([])
const reportKeyword = ref('')
const detailSourceFilter = ref('')
const selectedReportIds = ref<string[]>([])
const templateKeyword = ref('')
const exportTasks = ref<Array<{ id: string; name: string; status: 'running' | 'success' | 'failed'; statusText: string }>>([])
const loadingCloseoutDashboard = ref(false)
const closeoutError = ref('')
const closeoutDays = ref(14)
const closeoutEnvFilter = ref('')
const closeoutReasonFilter = ref('')
const closeoutCloseoutReasonFilter = ref('')
const closeoutIncludeDashboard = ref(false)
const closeoutPage = ref(1)
const closeoutPageSize = ref(10)
const closeoutTotal = ref(0)
const closeoutItems = ref<Alarm[]>([])
const closeoutSelectedDay = ref('')
const closeoutExportTemplate = ref<'default' | 'minimal' | 'full' | 'custom'>('default')
const closeoutExportCustomFields = ref<string[]>([])
const closeoutExportFieldOptions = [
  { label: '接收时间', value: 'received_at' },
  { label: '环境', value: 'policy_env' },
  { label: '报警原因码', value: 'reason_code' },
  { label: '收口原因码', value: 'closeout_reason_code' },
  { label: 'Run ID', value: 'run_id' },
  { label: '幂等键', value: 'idempotency_key' },
  { label: '签名 Key ID', value: 'key_id' },
  { label: '生成时间', value: 'generated_at' }
]
const closeoutExportTemplateStorageKey = 'closeout_dashboard_export_template_v1'
const closeoutExportCustomFieldsStorageKey = 'closeout_dashboard_export_custom_fields_v1'
const closeoutSelectedDayStorageKey = 'closeout_dashboard_selected_day_v1'
const closeoutQuickDayPresetStorageKey = 'closeout_dashboard_quick_day_preset_v1'
const closeoutQuickDayCountStorageKey = 'closeout_dashboard_quick_day_count_v1'
const closeoutQuickDayOrderStorageKey = 'closeout_dashboard_quick_day_order_v1'
const closeoutQuickDayPreset = ref<'oncall' | 'handover' | 'review' | 'custom'>('oncall')
const closeoutQuickDayCount = ref(5)
const closeoutQuickDayOrder = ref<'asc' | 'desc'>('desc')
const closeoutSummary = ref<Alarm>({
  window_days: 14,
  total: 0,
  by_reason_code: {},
  by_closeout_reason_code: {},
  trend_by_day: {},
  latest: null
})

// ── 流量趋势数据 ──
const trafficLoading = ref(false)
const trafficSummary = ref<{ avg_streams: number; max_streams: number; avg_bandwidth_kbps: number; max_bandwidth_kbps: number; sample_count: number } | null>(null)
const trafficStreamsData = ref<{ t: string; value: number }[]>([])
const trafficBandwidthData = ref<{ t: string; value_kbps: number }[]>([])
const trafficQualitySummary = ref<{
  active_sessions: number
  avg_health_score: number
  unhealthy_sessions: number
  level_distribution: Record<string, number>
} | null>(null)
const trafficQualityTrend = ref<{ t: string; avg_health_score: number }[]>([])
const trafficRiskSessions = ref<Array<{ session_id: string; device_id: string; channel_id: string; health_score: number; health_level: string }>>([])

const formatKbps = (kbps: number): string => {
  if (kbps >= 1_000_000) return (kbps / 1_000_000).toFixed(1) + ' Gbps'
  if (kbps >= 1_000) return (kbps / 1_000).toFixed(1) + ' Mbps'
  return kbps + ' Kbps'
}

const trafficStreamsOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  xAxis: { type: 'category' as const, data: trafficStreamsData.value.map(p => p.t.slice(11, 16)), axisLabel: { rotate: 30 } },
  yAxis: { type: 'value' as const, name: '流数' },
  series: [{ type: 'line', data: trafficStreamsData.value.map(p => p.value), smooth: true, areaStyle: { opacity: 0.15 } }],
  grid: { left: 50, right: 20, top: 20, bottom: 40 },
}))

const trafficBandwidthOption = computed(() => ({
  tooltip: { trigger: 'axis' as const, formatter: (params: Record<string, unknown>) => `${params[0].axisValue}<br/>${formatKbps(params[0].value)}` },
  xAxis: { type: 'category' as const, data: trafficBandwidthData.value.map(p => p.t.slice(11, 16)), axisLabel: { rotate: 30 } },
  yAxis: { type: 'value' as const, name: 'Kbps' },
  series: [{ type: 'line', data: trafficBandwidthData.value.map(p => p.value_kbps), smooth: true, areaStyle: { opacity: 0.15 }, itemStyle: { color: '#67C23A' } }],
  grid: { left: 60, right: 20, top: 20, bottom: 40 },
}))

const trafficQualityTrendOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  xAxis: { type: 'category' as const, data: trafficQualityTrend.value.map((p) => p.t) },
  yAxis: { type: 'value' as const, name: '健康分', min: 0, max: 100 },
  series: [{ type: 'line', data: trafficQualityTrend.value.map((p) => p.avg_health_score), smooth: true, areaStyle: { opacity: 0.15 }, itemStyle: { color: '#409EFF' } }],
  grid: { left: 60, right: 20, top: 20, bottom: 40 },
}))

const trafficQualityLevelOption = computed(() => {
  const dist = trafficQualitySummary.value?.level_distribution || {}
  const keys = Object.keys(dist)
  return {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: keys },
    yAxis: { type: 'value' as const, name: '会话数' },
    series: [{ type: 'bar', data: keys.map((k) => Number(dist[k] || 0)), itemStyle: { color: '#67C23A' } }],
    grid: { left: 40, right: 20, top: 20, bottom: 40 },
  }
})

async function loadTrafficData() {
  trafficLoading.value = true
  try {
    const res = await api.get('/api/v1/reports/data/traffic')
    const data = res.data?.data ?? res.data
    trafficSummary.value = data.summary || null
    trafficStreamsData.value = data.streams || []
    trafficBandwidthData.value = data.bandwidth || []
    try {
      const qualityRes = await api.get('/api/v1/reports/data/stream-quality')
      const qualityData = qualityRes.data?.data ?? qualityRes.data
      trafficQualitySummary.value = qualityData.summary || null
      trafficQualityTrend.value = qualityData.trend || []
      trafficRiskSessions.value = qualityData.risk_sessions || []
    } catch {
      trafficQualitySummary.value = null
      trafficQualityTrend.value = []
      trafficRiskSessions.value = []
    }
  } catch (e: unknown) {
    logger.error('加载流量数据失败', e)
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    trafficSummary.value = null
    trafficQualitySummary.value = null
    trafficQualityTrend.value = []
    trafficRiskSessions.value = []
  } finally {
    trafficLoading.value = false
  }
}

const canUseReportSuite = ref(false)

const reportSuiteDraftId = ref('')
const reportSuiteConfig = ref({
  enabled: true,
  connector_url: '',
  export_formats: ['csv', 'xlsx'],
  templates: [] as { id: string; name: string; export_formats: string[] }[]
})
const templateDialogVisible = ref(false)
const templateEditIndex = ref(-1)
const templateForm = ref({ id: '', name: '', export_formats: ['csv'] as string[] })

const extensionReports = computed(() => reports.value.filter(r => r.source !== 'builtin'))
const filteredExtensionReports = computed(() => {
  const keyword = templateKeyword.value.trim().toLowerCase()
  if (!keyword) return extensionReports.value
  return extensionReports.value.filter((r) => {
    const id = String(r.id || '').toLowerCase()
    const name = String(r.name || '').toLowerCase()
    return id.includes(keyword) || name.includes(keyword)
  })
})
const extensionReportsPage = ref(1)
const extensionReportsPageSize = ref(10)
const paginatedExtensionReports = computed(() => {
  const start = (extensionReportsPage.value - 1) * extensionReportsPageSize.value
  const end = start + extensionReportsPageSize.value
  return filteredExtensionReports.value.slice(start, end)
})
watch(filteredExtensionReports, () => { extensionReportsPage.value = 1 })

const exportLoading = ref<string | null>(null)
const mobileExpanded = ref<Record<string, boolean>>({})
const filteredReports = computed(() => {
  const keyword = reportKeyword.value.trim().toLowerCase()
  return reports.value.filter((r) => {
    if (detailSourceFilter.value === 'builtin' && r.source !== 'builtin') return false
    if (detailSourceFilter.value === 'external' && r.source === 'builtin') return false
    const id = String(r.id || '').toLowerCase()
    const name = String(r.name || '').toLowerCase()
    if (!keyword) return true
    return id.includes(keyword) || name.includes(keyword)
  })
})

const closeoutReasonRows = computed(() =>
  Object.entries(closeoutSummary.value?.by_reason_code || {})
    .map(([key, count]) => ({ key, count: Number(count || 0) }))
    .sort((a, b) => b.count - a.count)
)
const closeoutCloseoutReasonRows = computed(() =>
  Object.entries(closeoutSummary.value?.by_closeout_reason_code || {})
    .map(([key, count]) => ({ key, count: Number(count || 0) }))
    .sort((a, b) => b.count - a.count)
)
const closeoutTrendRows = computed(() =>
  Object.entries(closeoutSummary.value?.trend_by_day || {})
    .map(([day, count]) => ({ day, count: Number(count || 0) }))
    .sort((a, b) => String(a.day).localeCompare(String(b.day)))
)
const closeoutQuickDayOptions = computed(() => {
  const normalizedCount = Math.max(1, Math.min(30, Number(closeoutQuickDayCount.value || 5)))
  const latestDays = [...closeoutTrendRows.value]
    .sort((a, b) => (
      closeoutQuickDayOrder.value === 'asc'
        ? String(a.day).localeCompare(String(b.day))
        : String(b.day).localeCompare(String(a.day))
    ))
    .slice(0, normalizedCount)
    .map((x) => String(x.day))
  if (closeoutSelectedDay.value && !latestDays.includes(closeoutSelectedDay.value)) {
    return [closeoutSelectedDay.value, ...latestDays].slice(0, normalizedCount)
  }
  return latestDays
})
const closeoutDisplayItems = computed(() => {
  if (!closeoutSelectedDay.value) return closeoutItems.value
  return closeoutItems.value.filter((item) => normalizeToDay(item?.received_at) === closeoutSelectedDay.value)
})
const closeoutReasonBarOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 46 },
  xAxis: {
    type: 'category',
    axisLabel: { rotate: 25, color: '#64748b', fontSize: 11, interval: 0 },
    data: closeoutReasonRows.value.map((x) => x.key)
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#94a3b8', fontSize: 11 },
    splitLine: { lineStyle: { color: '#f1f5f9' } }
  },
  series: [
    {
      type: 'bar',
      data: closeoutReasonRows.value.map((x) => x.count),
      itemStyle: { color: '#3b82f6' },
      barMaxWidth: 36
    }
  ]
}))
const closeoutTrendLineOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 36 },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    axisLabel: { color: '#64748b', fontSize: 11 },
    data: closeoutTrendRows.value.map((x) => x.day)
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#94a3b8', fontSize: 11 },
    splitLine: { lineStyle: { color: '#f1f5f9' } }
  },
  series: [
    {
      type: 'line',
      smooth: true,
      data: closeoutTrendRows.value.map((x) => x.count),
      lineStyle: { width: 2, color: '#22c55e' },
      areaStyle: { color: 'rgba(34,197,94,0.12)' },
      symbolSize: 6
    }
  ]
}))

function onSelectionChange(rows: Array<{ id: string }>) {
  selectedReportIds.value = rows.map((r) => String(r.id || '')).filter(Boolean)
}

async function batchExportSelected() {
  const ids = [...selectedReportIds.value]
  if (!ids.length) return
  const batchId = `${Date.now()}`
  const taskLabel = `批量导出（${ids.length} 项）`
  exportTasks.value.unshift({ id: batchId, name: taskLabel, status: 'running', statusText: '执行中' })
  for (const id of ids) {
    await exportReport(id)
  }
  const target = exportTasks.value.find((x) => x.id === batchId)
  if (target) {
    target.status = 'success'
    target.statusText = '已完成'
  }
  ElMessage.success(`已触发 ${ids.length} 个报表导出`)
}

const clearDoneTasks = () => {
  exportTasks.value = exportTasks.value.filter((x) => x.status === 'running')
}

function toggleMobileRow(id: string) {
  const key = String(id || '')
  if (!key) return
  mobileExpanded.value = { ...mobileExpanded.value, [key]: !mobileExpanded.value[key] }
}

async function exportReport(type: string) {
  if (exportLoading.value) return
  exportLoading.value = type
  const taskId = `${Date.now()}_${type}`
  exportTasks.value.unshift({ id: taskId, name: `导出报表 ${type}`, status: 'running', statusText: '执行中' })
  try {
    const res = await api.get('/api/v1/reports/export', { params: { type }, responseType: 'blob' })
    const disposition = res.headers['content-disposition']
    const filename = disposition?.split('filename=')?.[1]?.replace(/"/g, '')?.trim() || `report_${type}.bin`
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    const task = exportTasks.value.find((x) => x.id === taskId)
    if (task) {
      task.status = 'success'
      task.statusText = '已完成'
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '导出失败')
    const task = exportTasks.value.find((x) => x.id === taskId)
    if (task) {
      task.status = 'failed'
      task.statusText = '失败'
    }
  } finally {
    exportLoading.value = null
  }
}

const openTemplateDialog = (row?: { id: string; name: string; export_formats?: string[] }) => {
  if (!row) {
    templateEditIndex.value = -1
    templateForm.value = { id: '', name: '', export_formats: ['csv'] }
  } else {
    const idx = reportSuiteConfig.value.templates.findIndex(t => t.id === row.id)
    templateEditIndex.value = idx
    templateForm.value = {
      id: row.id,
      name: row.name,
      export_formats: Array.isArray(row.export_formats) && row.export_formats.length ? row.export_formats : ['csv']
    }
  }
  templateDialogVisible.value = true
}

const confirmTemplate = () => {
  const id = templateForm.value.id.trim()
  const name = templateForm.value.name.trim()
  const exportFormats = (templateForm.value.export_formats || []).filter(Boolean)
  if (!id) {
    ElMessage.warning('请填写模板ID')
    return
  }
  const next = { id, name: name || id, export_formats: exportFormats.length ? exportFormats : ['csv'] }
  if (templateEditIndex.value >= 0) {
    reportSuiteConfig.value.templates[templateEditIndex.value] = next
  } else {
    const dup = reportSuiteConfig.value.templates.find(t => t.id === id)
    if (dup) {
      ElMessage.warning('模板ID已存在')
      return
    }
    reportSuiteConfig.value.templates.push(next)
  }
  templateDialogVisible.value = false
}

const removeTemplate = () => {
  if (templateEditIndex.value < 0) return
  reportSuiteConfig.value.templates.splice(templateEditIndex.value, 1)
  templateDialogVisible.value = false
}

const maxAlarmValue = computed(() => {
  if (!alarmStats.value.length) return 1
  return Math.max(...alarmStats.value.map(i => i.value))
})

function getPercentage(val: number) {
  return Math.round((val / maxAlarmValue.value) * 100)
}

async function exportCsv(type: string) {
  try {
    const res = await api.get('/api/v1/reports/export', { params: { type }, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = res.headers['content-disposition']?.split('filename=')?.[1]?.replace(/"/g, '') || `report_${type}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '导出 CSV 失败')
  }
}

async function exportPdf(type: string) {
  try {
    const res = await api.get('/api/v1/reports/export.pdf', { params: { type }, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    const a = document.createElement('a')
    a.href = url
    a.download = res.headers['content-disposition']?.split('filename=')?.[1]?.replace(/"/g, '') || `report_${type}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '导出 PDF 失败')
  }
}

async function loadAlarmStats() {
  loadingAlarms.value = true
  alarmError.value = ''
  try {
    const res = await api.get('/api/v1/reports/data/alarms')
    alarmStats.value = res.data
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    alarmError.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '报警统计加载失败'
    alarmStats.value = []
  } finally {
    loadingAlarms.value = false
  }
}

async function loadCloseoutDashboardSummary() {
  const params: Record<string, unknown> = { days: closeoutDays.value }
  if (closeoutEnvFilter.value) params.policy_env = closeoutEnvFilter.value
  const res = await api.get('/api/v1/reports/mobile-regression/closeout-governance-dashboard/summary', { params })
  closeoutSummary.value = res.data || {
    window_days: closeoutDays.value,
    total: 0,
    by_reason_code: {},
    by_closeout_reason_code: {},
    trend_by_day: {},
    latest: null
  }
}

async function loadCloseoutDashboardDrilldown() {
  const params: Record<string, unknown> = {
    limit: closeoutPageSize.value,
    offset: (closeoutPage.value - 1) * closeoutPageSize.value
  }
  if (closeoutEnvFilter.value) params.policy_env = closeoutEnvFilter.value
  if (closeoutReasonFilter.value.trim()) params.reason_code = closeoutReasonFilter.value.trim()
  if (closeoutCloseoutReasonFilter.value.trim()) params.closeout_reason_code = closeoutCloseoutReasonFilter.value.trim()
  if (closeoutSelectedDay.value) params.received_day = closeoutSelectedDay.value
  if (closeoutIncludeDashboard.value) params.include_dashboard = true
  const res = await api.get('/api/v1/reports/mobile-regression/closeout-governance-dashboard/drilldown', { params })
  closeoutItems.value = Array.isArray(res.data?.items) ? res.data.items : []
  closeoutTotal.value = Number(res.data?.total || 0)
}

async function reloadCloseoutDashboard() {
  loadingCloseoutDashboard.value = true
  closeoutError.value = ''
  try {
    await Promise.all([loadCloseoutDashboardSummary(), loadCloseoutDashboardDrilldown()])
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    closeoutError.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || 'closeout 看板加载失败'
    closeoutItems.value = []
    closeoutTotal.value = 0
  } finally {
    loadingCloseoutDashboard.value = false
  }
}

function onCloseoutPageSizeChange() {
  closeoutPage.value = 1
  loadCloseoutDashboardDrilldown()
}

function escapeCsvCell(value: unknown): string {
  const text = String(value ?? '')
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function normalizeToDay(value: unknown): string {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text.length >= 10) return text.slice(0, 10)
  return text
}

function resolveCloseoutExportFields(): string[] {
  if (closeoutExportTemplate.value === 'minimal') {
    return ['received_at', 'policy_env', 'reason_code']
  }
  if (closeoutExportTemplate.value === 'full') {
    return closeoutExportFieldOptions.map((x) => x.value)
  }
  if (closeoutExportTemplate.value === 'custom') {
    const selected = closeoutExportCustomFields.value.filter(Boolean)
    return selected.length ? selected : ['received_at', 'policy_env', 'reason_code', 'closeout_reason_code', 'run_id']
  }
  return ['received_at', 'policy_env', 'reason_code', 'closeout_reason_code', 'run_id']
}

function onCloseoutReasonBarClick(params: Record<string, unknown>) {
  const reasonCode = String(params?.name || '').trim()
  closeoutReasonFilter.value = reasonCode
  closeoutPage.value = 1
  loadCloseoutDashboardDrilldown()
}

function onCloseoutTrendLineClick(params: Record<string, unknown>) {
  const day = String(params?.name || '').trim()
  closeoutSelectedDay.value = day
  closeoutPage.value = 1
  loadCloseoutDashboardDrilldown()
}

function applyCloseoutQuickDay(day: string) {
  const nextDay = String(day || '').trim()
  if (!nextDay) return
  closeoutSelectedDay.value = nextDay
  closeoutPage.value = 1
  loadCloseoutDashboardDrilldown()
}

function clearCloseoutSelectedDay() {
  closeoutSelectedDay.value = ''
  closeoutPage.value = 1
  loadCloseoutDashboardDrilldown()
}

function exportCloseoutCsv() {
  const header = resolveCloseoutExportFields()
  const rows = closeoutDisplayItems.value.map((item) => header.map((field) => item?.[field] || ''))
  const csv = [header, ...rows]
    .map((line) => line.map((x) => escapeCsvCell(x)).join(','))
    .join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const envPart = closeoutEnvFilter.value || 'all'
  const dayPart = closeoutSelectedDay.value || 'all-days'
  const templatePart = closeoutExportTemplate.value
  a.download = `closeout_dashboard_${envPart}_${dayPart}_${templatePart}_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

const loadingConfig = ref(false)
async function loadReportSuiteConfig() {
  loadingConfig.value = true
  try {
    const res = await api.get('/api/v1/reports/report-suite/config')
    reportSuiteDraftId.value = res.data?.draft_id || ''
    const cfg = res.data?.config || {}
    reportSuiteConfig.value = {
      enabled: cfg.enabled !== false,
      connector_url: cfg.connector_url || '',
      export_formats: Array.isArray(cfg.export_formats) && cfg.export_formats.length ? cfg.export_formats : ['csv', 'xlsx'],
      templates: Array.isArray(cfg.templates) ? cfg.templates : []
    }
  } catch {
    reportSuiteConfig.value = {
      enabled: true,
      connector_url: '',
      export_formats: ['csv', 'xlsx'],
      templates: []
    }
    ElMessage.warning('加载 report_suite 配置失败，使用默认配置')
  } finally {
    loadingConfig.value = false
  }
}

async function saveReportSuiteConfig(publish: boolean) {
  try {
    await api.put('/api/v1/reports/report-suite/config', {
      ...reportSuiteConfig.value,
      publish
    })
    ElMessage.success(publish ? '已保存并发布' : '已保存到草稿')
    await loadReports()
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '保存失败，请稍后重试')
  }
}

async function testReportConnector() {
  const url = reportSuiteConfig.value.connector_url?.trim()
  if (!url) {
    ElMessage.warning('请先填写报表连接器 URL')
    return
  }
  try {
    const res = await api.post('/api/v1/reports/report-suite/connector-test', null, {
      params: { connector_url: url }
    })
    if (res.data?.ok) {
      ElMessage.success(`连接器可用（HTTP ${res.data?.status_code ?? 'ok'}）`)
    } else {
      ElMessage.warning(`连接器返回异常（HTTP ${res.data?.status_code || '-'})`)
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '连接器测试失败，请检查 URL 可访问性')
  }
}

async function loadReports() {
  try {
    const listRes = await api.get('/api/v1/reports/list')
    if (Array.isArray(listRes.data?.reports)) {
      reports.value = listRes.data.reports
    } else {
      reports.value = []
    }
  } catch {
    reports.value = []
  }
}

async function reloadSummary() {
  loading.value = true
  summaryError.value = ''
  try {
    const summaryRes = await api.get('/api/v1/reports/summary')
    if (Array.isArray(summaryRes.data?.items)) {
      items.value = summaryRes.data.items
    } else {
      items.value = []
    }
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    summaryError.value = friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message || '运行概览加载失败'
    items.value = []
  } finally {
    loading.value = false
  }
}

watch(activeTab, (val) => {
  router.replace({
    path: route.path,
    query: {
      ...route.query,
      tab: val
    }
  })
})

watch(activeTab, (val) => {
  if (val === 'alarms' && !alarmStats.value.length) {
    loadAlarmStats()
  }
  if (val === 'closeout_dashboard' && !loadingCloseoutDashboard.value && closeoutTotal.value === 0 && !closeoutError.value) {
    reloadCloseoutDashboard()
  }
})

watch(closeoutExportTemplate, (val) => {
  localStorage.setItem(closeoutExportTemplateStorageKey, val)
})

watch(closeoutExportCustomFields, (val) => {
  localStorage.setItem(closeoutExportCustomFieldsStorageKey, JSON.stringify(val || []))
}, { deep: true })

watch(closeoutSelectedDay, (val) => {
  const day = String(val || '').trim()
  if (day) {
    localStorage.setItem(closeoutSelectedDayStorageKey, day)
  } else {
    localStorage.removeItem(closeoutSelectedDayStorageKey)
  }
})

watch(closeoutQuickDayPreset, (preset) => {
  localStorage.setItem(closeoutQuickDayPresetStorageKey, preset)
  if (preset === 'oncall') {
    closeoutQuickDayCount.value = 5
    closeoutQuickDayOrder.value = 'desc'
  } else if (preset === 'handover') {
    closeoutQuickDayCount.value = 7
    closeoutQuickDayOrder.value = 'asc'
  } else if (preset === 'review') {
    closeoutQuickDayCount.value = 14
    closeoutQuickDayOrder.value = 'desc'
  }
})

watch(closeoutQuickDayCount, (count) => {
  const normalized = Math.max(1, Math.min(30, Number(count || 5)))
  if (normalized !== closeoutQuickDayCount.value) {
    closeoutQuickDayCount.value = normalized
    return
  }
  localStorage.setItem(closeoutQuickDayCountStorageKey, String(normalized))
})

watch(closeoutQuickDayOrder, (order) => {
  localStorage.setItem(closeoutQuickDayOrderStorageKey, order)
})

onMounted(async () => {
  const savedTemplate = localStorage.getItem(closeoutExportTemplateStorageKey)
  if (savedTemplate && ['default', 'minimal', 'full', 'custom'].includes(savedTemplate)) {
    closeoutExportTemplate.value = savedTemplate as 'default' | 'minimal' | 'full' | 'custom'
  }
  const savedCustomFields = localStorage.getItem(closeoutExportCustomFieldsStorageKey)
  if (savedCustomFields) {
    try {
      const parsed = JSON.parse(savedCustomFields)
      if (Array.isArray(parsed)) {
        const available = new Set(closeoutExportFieldOptions.map((x) => x.value))
        closeoutExportCustomFields.value = parsed.map((x) => String(x || '')).filter((x) => available.has(x))
      }
    } catch {
      closeoutExportCustomFields.value = []
    }
  }
  const savedSelectedDay = localStorage.getItem(closeoutSelectedDayStorageKey)
  if (savedSelectedDay && /^\d{4}-\d{2}-\d{2}$/.test(savedSelectedDay)) {
    closeoutSelectedDay.value = savedSelectedDay
  }
  const savedPreset = localStorage.getItem(closeoutQuickDayPresetStorageKey)
  if (savedPreset && ['oncall', 'handover', 'review', 'custom'].includes(savedPreset)) {
    closeoutQuickDayPreset.value = savedPreset as 'oncall' | 'handover' | 'review' | 'custom'
  }
  const savedQuickDayCount = Number(localStorage.getItem(closeoutQuickDayCountStorageKey) || '')
  if (Number.isFinite(savedQuickDayCount) && savedQuickDayCount >= 1 && savedQuickDayCount <= 30) {
    closeoutQuickDayCount.value = Math.floor(savedQuickDayCount)
  }
  const savedQuickDayOrder = localStorage.getItem(closeoutQuickDayOrderStorageKey)
  if (savedQuickDayOrder === 'asc' || savedQuickDayOrder === 'desc') {
    closeoutQuickDayOrder.value = savedQuickDayOrder
  }
  const queryTab = String((route.query as Record<string, unknown>).tab || '')
  if (queryTab) {
    const allowed = ['summary', 'details', 'alarms', 'traffic', 'closeout_dashboard', 'extensions']
    if (allowed.includes(queryTab)) activeTab.value = queryTab
  }
  try {
    await reloadSummary()
    loadTrafficData()  // 非阻塞加载流量趋势

    // report_suite：仅在“已购买 + 已安装”后才展示扩展报表能力
    try {
      const [purchasedRes, menusRes] = await Promise.all([
        api.get('/api/v1/plugins/purchased'),
        api.get('/api/v1/plugins/menus')
      ])
      const purchasedIds = Array.isArray(purchasedRes?.data?.plugin_ids)
        ? purchasedRes.data.plugin_ids.map((x: Record<string, unknown>) => String(x))
        : []
      const installedIds = new Set(
        (Array.isArray(menusRes?.data) ? menusRes.data : [])
          .map((m: Record<string, unknown>) => String(m?.plugin_id || ''))
          .filter(Boolean)
      )
      canUseReportSuite.value = purchasedIds.includes('report_suite') && installedIds.has('report_suite')
    } catch {
      canUseReportSuite.value = false
    } finally {
      // report suite gate check done
    }

    await loadReports()
    if (canUseReportSuite.value) {
      await loadReportSuiteConfig()
    }
  } catch {
    summaryError.value = '初始化失败，请重试'
  } finally {
    loading.value = false
  }
})
</script>
