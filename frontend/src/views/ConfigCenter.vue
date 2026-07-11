<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('configCenter.title')" :description="t('configCenter.description')">
          <template #actions>
            <el-tooltip :content="t('configCenter.refreshConfig')" placement="top">
              <el-button @click="loadAllData" circle>
                <el-icon><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
          </template>
        </PageHeader>
      </template>

      <el-tabs v-model="activeTab" type="border-card" class="config-tabs">
        <!-- 基础配置 -->
        <el-tab-pane :label="t('configCenter.tabBasic')" name="basic">
          <TableCard v-loading="saving">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('configCenter.deviceAndAlarmConfig') }}</div>
              </div>
            </template>
            <el-form label-width="180px" class="max-w-2xl">
              <el-form-item :label="t('configCenter.streamPullTimeout')">
                <el-input-number v-model="basicForm.streamPullTimeout" :min="1" :max="120" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.streamPullTimeoutHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.alarmDefaultLevel')">
                <el-select v-model="basicForm.alarmDefaultLevel" style="width: 200px">
                  <el-option :label="t('configCenter.alarmLevelLow')" value="low" />
                  <el-option :label="t('configCenter.alarmLevelMedium')" value="medium" />
                  <el-option :label="t('configCenter.alarmLevelHigh')" value="high" />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('configCenter.deviceHeartbeatInterval')">
                <el-input-number v-model="basicForm.deviceHeartbeatInterval" :min="10" :max="300" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.deviceHeartbeatHint') }}</span>
              </el-form-item>
              <el-divider />
              <el-form-item :label="t('configCenter.recordAutoCleanDays')">
                <el-input-number v-model="basicForm.recordAutoCleanDays" :min="0" :max="365" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.recordAutoCleanHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.logRetentionDays')">
                <el-input-number v-model="basicForm.logRetentionDays" :min="1" :max="90" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.logRetentionHint') }}</span>
              </el-form-item>
              <el-divider />
              <div class="font-medium mb-2" style="color: var(--el-text-color-primary)">{{ t('configCenter.pluginSandboxTitle') }}</div>
              <el-form-item :label="t('configCenter.pluginSandboxCpuLimit')">
                <el-input-number v-model="basicForm.pluginSandboxCpuLimitPercent" :min="0" :max="100" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.pluginSandboxCpuHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.pluginSandboxMemoryLimit')">
                <el-input-number v-model="basicForm.pluginSandboxMemoryLimitMb" :min="0" :max="32768" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.pluginSandboxMemoryHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.pluginSandboxDiskLimit')">
                <el-input-number v-model="basicForm.pluginSandboxDiskLimitMb" :min="0" :max="1048576" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.pluginSandboxDiskHint') }}</span>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="savingBasic" @click="saveBasicConfig">{{ t('configCenter.saveConfig') }}</el-button>
              </el-form-item>
            </el-form>
          </TableCard>
        </el-tab-pane>

        <!-- 数据库配置 -->
        <el-tab-pane :label="t('configCenter.tabDatabase')" name="database">
          <TableCard v-loading="loadingDb">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('configCenter.dbConnectionConfig') }}</div>
                <div class="flex gap-2">
                  <el-button size="small" @click="testDbConfig">{{ t('configCenter.testConnection') }}</el-button>
                  <el-button size="small" type="primary" :loading="savingDb" @click="saveDbConfig">{{ t('configCenter.saveConfig') }}</el-button>
                </div>
              </div>
            </template>
            <el-form label-width="140px" class="max-w-3xl">
              <el-form-item :label="t('configCenter.dbType')">
                <el-select v-model="dbForm.database_type" class="w-52">
                  <el-option label="PostgreSQL" value="postgresql" />
                  <el-option label="MySQL" value="mysql" />
                  <el-option label="SQLite" value="sqlite" />
                  <el-option :label="t('configCenter.dbTypeKingbase')" value="kingbase" />
                  <el-option :label="t('configCenter.dbTypeDameng')" value="dameng" />
                </el-select>
              </el-form-item>
              <template v-if="dbForm.database_type !== 'sqlite'">
                <el-form-item :label="t('configCenter.dbHost')">
                  <el-input v-model="dbForm.host" class="w-80" />
                </el-form-item>
                <el-form-item :label="t('configCenter.dbPort')">
                  <el-input-number v-model="dbForm.port" :min="1" :max="65535" />
                </el-form-item>
                <el-form-item :label="t('configCenter.dbName')">
                  <el-input v-model="dbForm.name" class="w-80" />
                </el-form-item>
                <el-form-item :label="t('common.username')">
                  <el-input v-model="dbForm.username" class="w-80" />
                </el-form-item>
                <el-form-item :label="t('common.password')">  <!-- FIXED: P3 i18n -->
                  <el-input v-model="dbForm.password" type="password" show-password class="w-80" />
                </el-form-item>
              </template>
              <template v-else>
                <el-form-item :label="t('configCenter.dbSqlitePath')">
                  <el-input v-model="dbForm.sqlite_path" class="w-80" />
                </el-form-item>
              </template>
              <el-form-item :label="t('configCenter.dbUri')">
                <el-input v-model="dbForm.sqlalchemy_database_uri" class="w-full" :placeholder="t('configCenter.dbUriPlaceholder')" />
              </el-form-item>
            </el-form>

            <!-- 兼容性报告 -->
            <AppDialog v-model="dbCompatVisible" :title="t('configCenter.dbCompatReport')" size="medium">
              <div class="space-y-3 text-sm">
                <div class="flex items-center gap-2">
                  <el-tag :type="dbCompatSummary === 'ok' ? 'success' : (dbCompatSummary === 'warn' ? 'warning' : 'danger')" effect="plain">
                    {{ t('common.status') }}{{ t('configCenter.colon') }}{{ dbCompatSummary === 'ok' ? t('configCenter.dbCompatStatusOk') : (dbCompatSummary === 'warn' ? t('configCenter.dbCompatStatusWarn') : t('configCenter.dbCompatStatusError')) }}
                  </el-tag>
                  <span style="color: var(--el-text-color-secondary)">{{ t('configCenter.dbCompatDatabase') }}{{ t('configCenter.colon') }}{{ dbCompatDatabase || '-' }}</span>
                </div>
                <p v-if="dbCompatVendorHint" style="color: var(--el-color-warning)">{{ dbCompatVendorHint }}</p>
                <el-divider />
                <p v-for="(line, i) in dbCompatChecks" :key="i"
                  :style="{ color: line.ok ? 'var(--el-text-color-regular)' : 'var(--el-color-danger)' }">
                  {{ line.ok ? '✓' : '✗' }} {{ line.name }}{{ t('configCenter.colon') }}{{ line.detail }}
                </p>
              </div>
              <template #footer>
                <el-button @click="dbCompatVisible = false">{{ t('common.close') }}</el-button>
              </template>
            </AppDialog>
          </TableCard>
        </el-tab-pane>

        <!-- 多协议接入 -->
        <el-tab-pane :label="t('configCenter.tabSource')" name="source">
          <TableCard>
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('configCenter.sourceManagement') }}</div>
                <div class="flex gap-2">
                  <el-button size="small" @click="loadDbCompatReport">{{ t('configCenter.compatReport') }}</el-button>
                  <el-button size="small" type="primary" @click="openSourceDialog()">{{ t('configCenter.addSource') }}</el-button>
                </div>
              </div>
            </template>
            <el-table :data="accessSources" border :empty-text="t('configCenter.noSources')" fit>
              <el-table-column prop="name" :label="t('common.name')" />
              <el-table-column prop="protocol" :label="t('configCenter.sourceProtocol')" width="120" />
              <el-table-column prop="host" :label="t('common.address')" />
              <el-table-column prop="port" :label="t('configCenter.dbPort')" width="100" />
              <el-table-column prop="path" :label="t('common.path')" />
              <el-table-column :label="t('common.enable')" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? t('common.yes') : t('common.no') }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('common.action')" width="220">
                <template #default="{ row }">
                  <div class="table-action-inline">
                    <el-button link size="small" type="primary" @click="openSourceDialog(row)">{{ t('common.edit') }}</el-button>
                    <el-button link size="small" type="primary" @click="testSource(row.id)">{{ t('configCenter.test') }}</el-button>
                    <el-dropdown trigger="click" @command="(cmd: string) => handleSourceMoreCommand(row, cmd)">
                      <el-button link size="small" type="primary" class="table-action-more">{{ t('common.more') }}</el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="preview">{{ t('configCenter.sourcePreview') }}</el-dropdown-item>
                          <el-dropdown-item command="delete" divided>{{ t('common.delete') }}</el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <div class="flex justify-end mt-4 pagination-wrapper" v-if="accessSources.length > 0">
              <el-pagination
                v-model:current-page="sourcePage"
                v-model:page-size="sourcePageSize"
                :total="accessSources.length"
                layout="total, sizes, prev, pager, next, jumper"
                :page-sizes="[10, 20, 50, 100]"
                :prev-text="t('configCenter.prevPage')"
                :next-text="t('configCenter.nextPage')"
                size="small"
              />
            </div>
          </TableCard>
        </el-tab-pane>

        <!-- 录像存储配置 -->
        <el-tab-pane :label="t('configCenter.tabStorage')" name="storage">
          <TableCard v-loading="loadingStorage">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('configCenter.storageConfigTitle') }}</div>
                <el-button size="small" type="primary" :loading="savingStorage" @click="saveStorageConfig">{{ t('common.save') }}</el-button>
              </div>
            </template>
            <div class="mb-4">
              <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.storageRootHint') }}</div>
              <div class="flex gap-2 items-center">
                <el-input v-model="storageRoot" :placeholder="t('configCenter.storageRootPlaceholder')" class="w-96" />
              </div>
            </div>
            <div>
              <div class="text-sm mb-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.storageNodeHint') }}</div>
              <div class="mb-3">
                <el-button size="small" type="primary" @click="openStorageNodeDialog()">{{ t('configCenter.addNode') }}</el-button>
              </div>
              <el-table :data="storageNodes" border :empty-text="t('configCenter.noStorageNodes')" size="small" fit>
                <el-table-column prop="id" :label="t('common.id')" width="120" />
                <el-table-column prop="name" :label="t('common.name')" width="140" />
                <el-table-column prop="path" :label="t('common.path')" />
                <el-table-column :label="t('common.action')" width="120">
                  <template #default="{ row, $index }">
                    <el-button link type="primary" size="small" @click="openStorageNodeDialog(row, (storagePage - 1) * storagePageSize + $index)">{{ t('common.edit') }}</el-button>
                    <el-button link type="danger" size="small" @click="removeStorageNode((storagePage - 1) * storagePageSize + $index)">{{ t('common.delete') }}</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div class="flex justify-end mt-4" v-if="storageNodes.length > 0">
                <el-button type="primary" :loading="savingStorageNodes" @click="saveStorageNodes">{{ t('configCenter.saveNodeList') }}</el-button>
              </div>
            </div>
            <div class="mt-4 pt-4 border-t text-sm" style="color: var(--el-text-color-secondary)">
              {{ t('configCenter.recordScheduleHint') }}
              <router-link to="/record-schedule" style="color: var(--el-color-primary); text-decoration: underline;">{{ t('configCenter.recordScheduleLink') }}</router-link>
            </div>
          </TableCard>
        </el-tab-pane>

        <!-- 国标播放配置 -->
        <el-tab-pane :label="t('configCenter.tabGbPlay')" name="gbplay">
          <TableCard v-loading="loadingGbPlay">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-medium">{{ t('configCenter.gbPlayConfigTitle') }}</div>
                <div class="flex gap-2">
                  <el-button size="small" @click="loadGbPlayConfig">{{ t('common.refresh') }}</el-button>
                  <el-button size="small" type="primary" :loading="savingGbPlay" @click="saveGbPlayConfig">{{ t('configCenter.saveConfig') }}</el-button>
                </div>
              </div>
            </template>
            <el-form label-width="180px" class="max-w-2xl">
              <el-form-item :label="t('configCenter.defaultStreamType')">
                <el-select v-model="gbPlayForm.default_stream_type" style="width: 200px">
                  <el-option :label="t('configCenter.streamTypeMain')" value="main" />
                  <el-option :label="t('configCenter.streamTypeSub')" value="sub" />
                  <el-option :label="t('configCenter.streamTypeAuto')" value="auto" />
                </el-select>
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.defaultStreamTypeHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.transportProtocol')">
                <el-select v-model="gbPlayForm.transport" style="width: 200px">
                  <el-option label="UDP" value="udp" />
                  <el-option :label="t('configCenter.transportTcpPassive')" value="tcp_passive" />
                  <el-option :label="t('configCenter.transportTcpActive')" value="tcp_active" />
                </el-select>
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.transportHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.inviteTimeout')">
                <el-input-number v-model="gbPlayForm.invite_timeout" :min="1" :max="60" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.inviteTimeoutHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.enableAdaptiveLearning')">
                <el-switch v-model="gbPlayForm.learning_enabled" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.adaptiveLearningHint') }}</span>
              </el-form-item>
              <el-form-item :label="t('configCenter.minLearningSamples')">
                <el-input-number v-model="gbPlayForm.learning_min_samples" :min="1" :max="100" />
                <span class="text-xs ml-2" style="color: var(--el-text-color-secondary)">{{ t('configCenter.minLearningSamplesHint') }}</span>
              </el-form-item>
            </el-form>
            <el-divider />
            <div class="flex items-center justify-between">
              <div>
                <span class="text-sm font-medium">{{ t('configCenter.learningStatus') }}</span>
                <span v-if="gbLearningState" class="ml-3 text-sm" style="color: var(--el-text-color-secondary)">
                  {{ t('configCenter.learningStatusInfo', { samples: gbLearningState.total_samples || 0, devices: gbLearningState.devices_learned || 0 }) }}
                </span>
                <span v-else class="ml-3 text-sm" style="color: var(--el-text-color-secondary)">{{ t('configCenter.noLearningData') }}</span>
              </div>
              <el-popconfirm :title="t('configCenter.resetLearningConfirm')" @confirm="resetGbLearningState">
                <template #reference>
                  <el-button size="small" type="danger" plain>{{ t('configCenter.resetLearningData') }}</el-button>
                </template>
              </el-popconfirm>
            </div>
          </TableCard>
        </el-tab-pane>

        <!-- 审计日志 -->
        <el-tab-pane :label="t('configCenter.tabAudit')" name="audit">
          <TableCard v-loading="loadingAudit">
            <template #header>
              <div class="flex items-center justify-between mb-3">
                <div class="font-medium">{{ t('configCenter.auditLog') }}</div>
                <el-button size="small" @click="loadAuditLogs">{{ t('common.refresh') }}</el-button>
              </div>
              <div class="flex flex-wrap gap-2 items-center mb-3">
                <el-input v-model="auditForm.keyword" :placeholder="t('configCenter.searchAuditPlaceholder')" clearable class="w-48" @keyup.enter="loadAuditLogs" />
                <el-date-picker
                  v-model="auditForm.dateRange"
                  type="daterange"
                  :range-separator="t('configCenter.dateRangeSeparator')"
                  :start-placeholder="t('common.startDate')"
                  :end-placeholder="t('common.endDate')"
                  value-format="YYYY-MM-DD"
                  class="w-64"
                />
                <el-select v-model="auditForm.result" :placeholder="t('common.result')" clearable style="width: 120px">
                  <el-option :label="t('configCenter.auditSuccess')" value="success" />
                  <el-option :label="t('configCenter.auditFailed')" value="failed" />
                </el-select>
                <el-button type="primary" @click="loadAuditLogs">{{ t('common.query') }}</el-button>
                <el-button @click="resetAuditFilters">{{ t('common.reset') }}</el-button>
              </div>
            </template>
            <el-table :data="paginatedAuditLogs" border size="small" :empty-text="t('configCenter.noAuditLogs')">
              <el-table-column prop="created_at" :label="t('common.time')" width="180" />
              <el-table-column prop="operator" :label="t('audit.operator')" width="120" />
              <el-table-column prop="module" :label="t('audit.module')" width="150" />
              <el-table-column prop="action" :label="t('common.action')" min-width="150" show-overflow-tooltip />
              <el-table-column :label="t('common.result')" width="80">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.result === 'success' ? 'success' : 'danger'" effect="plain">
                    {{ row.result === 'success' ? t('configCenter.auditSuccess') : t('configCenter.auditFailed') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('common.detail')" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ row.detail || '-' }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="flex justify-end mt-4">
              <el-pagination
                v-model:current-page="auditPage"
                v-model:page-size="auditPageSize"
                :total="auditTotal"
                layout="total, sizes, prev, pager, next, jumper"
                :page-sizes="[20, 50, 100]"
                :prev-text="t('configCenter.prevPage')"
                :next-text="t('configCenter.nextPage')"
                size="small"
                @current-change="loadAuditLogs"
                @size-change="loadAuditLogs"
              />
            </div>
          </TableCard>
        </el-tab-pane>
      </el-tabs>
    </PageContainer>

    <!-- 接入源弹窗 -->
    <AppDialog v-model="sourceDialogVisible" :title="editingSourceId ? t('configCenter.editSource') : t('configCenter.addSource')" size="large">
      <el-form :model="sourceForm" ref="sourceFormRef" :rules="sourceRules" label-width="120px">
        <el-form-item :label="t('common.name')" prop="name"><el-input v-model="sourceForm.name" :placeholder="t('configCenter.sourceNamePlaceholder')" /></el-form-item>
        <el-form-item :label="t('configCenter.sourceProtocol')" prop="protocol">
          <el-select v-model="sourceForm.protocol" style="width: 220px">
            <el-option label="GB28181" value="GB28181" />
            <el-option label="ONVIF" value="ONVIF" />
            <el-option label="RTSP" value="RTSP" />
            <el-option :label="t('configCenter.sdkPrivateProtocol')" value="SDK" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('common.address')" prop="host"><el-input v-model="sourceForm.host" :placeholder="t('configCenter.sourceHostPlaceholder')" /></el-form-item>
        <el-form-item :label="t('configCenter.dbPort')" prop="port"><el-input-number v-model="sourceForm.port" :min="0" :max="65535" /></el-form-item>
        <el-form-item :label="t('common.username')"><el-input v-model="sourceForm.username" :placeholder="t('configCenter.optional')" /></el-form-item>
        <el-form-item :label="t('common.password')"><el-input v-model="sourceForm.password" type="password" show-password :placeholder="t('configCenter.sourcePasswordPlaceholder')" /></el-form-item>
        <el-form-item :label="t('common.path')"><el-input v-model="sourceForm.path" :placeholder="t('configCenter.sourcePathPlaceholder')" /></el-form-item>
        <el-form-item :label="t('configCenter.sourceStreamName')"><el-input v-model="sourceForm.stream_name" :placeholder="t('configCenter.optional')" /></el-form-item>
        <el-form-item :label="t('common.enable')"><el-switch v-model="sourceForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sourceDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveSource">{{ t('common.save') }}</el-button>
      </template>
    </AppDialog>

    <!-- 存储节点弹窗 -->
    <AppDialog v-model="storageNodeDialogVisible" :title="t('configCenter.storageNodeTitle')" size="small">
      <el-form :model="storageNodeForm" label-width="80px">
        <el-form-item :label="t('common.id')"><el-input v-model="storageNodeForm.id" :placeholder="t('configCenter.storageNodeIdPlaceholder')" /></el-form-item>
        <el-form-item :label="t('common.name')"><el-input v-model="storageNodeForm.name" :placeholder="t('configCenter.storageNodeNamePlaceholder')" /></el-form-item>
        <el-form-item :label="t('common.path')"><el-input v-model="storageNodeForm.path" :placeholder="t('configCenter.storageNodePathPlaceholder')" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="storageNodeDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="confirmStorageNode">{{ t('common.ok') }}</el-button>
      </template>
    </AppDialog>

    <!-- 预览弹窗 -->
    <AppDialog v-model="previewVisible" :title="t('configCenter.sourcePreviewTitle')" size="large">
      <div class="h-[520px] bg-black">
        <JessibucaPlayer v-if="previewStream.url" :video-url="previewStream.url" :hls-url="previewStream.hls" :codec="previewStream.codec" />
      </div>
      <template #footer>
        <el-button @click="closePreview">{{ t('common.close') }}</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import AppDialog from '../components/common/AppDialog.vue'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import { getFriendlyError } from '../utils/errorMessage'
import api from '@/utils/http'
import { logger } from '@/utils/logger'
import type { AuditLog } from '@/types/models'
import { useI18n } from 'vue-i18n'  // FIXED: P3 i18n

const { t } = useI18n()  // FIXED: P3 i18n

const activeTab = ref('basic')

// 基础配置
const basicForm = ref({
  streamPullTimeout: 10,
  alarmDefaultLevel: 'medium',
  deviceHeartbeatInterval: 60,
  recordAutoCleanDays: 0,
  logRetentionDays: 7,
  pluginSandboxCpuLimitPercent: 0,
  pluginSandboxMemoryLimitMb: 0,
  pluginSandboxDiskLimitMb: 0
})
const savingBasic = ref(false)
const saving = computed(() => savingBasic.value || savingDb.value || savingStorage.value || savingStorageNodes.value || savingGbPlay.value)

// 国标播放配置
const gbPlayForm = ref({
  default_stream_type: 'auto',
  transport: 'udp',
  invite_timeout: 10,
  learning_enabled: true,
  learning_min_samples: 5
})
const loadingGbPlay = ref(false)
const savingGbPlay = ref(false)
const gbLearningState = ref<{ total_samples: number; devices_learned: number } | null>(null)

const loadGbPlayConfig = async () => {
  loadingGbPlay.value = true
  try {
    const [configRes, stateRes] = await Promise.allSettled([
      api.get('/api/v1/system-config/gb28181/play-config'),
      api.get('/api/v1/system-config/gb28181/learning-state')
    ])
    if (configRes.status === 'fulfilled' && configRes.value.data) {
      const d = configRes.value.data
      gbPlayForm.value = {
        default_stream_type: d.default_stream_type || 'auto',
        transport: d.transport || 'udp',
        invite_timeout: d.invite_timeout ?? 10,
        learning_enabled: d.learning_enabled !== false,
        learning_min_samples: d.learning_min_samples ?? 5
      }
    }
    if (stateRes.status === 'fulfilled' && stateRes.value.data) {
      gbLearningState.value = stateRes.value.data
    }
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  } finally {
    loadingGbPlay.value = false
  }
}

const saveGbPlayConfig = async () => {
  savingGbPlay.value = true
  const prev = { ...gbPlayForm.value }
  try {
    await api.put('/api/v1/system-config/gb28181/play-config', gbPlayForm.value)
    ElMessage.success(t('configCenter.gbPlaybackConfigSaved')) // FIXED: 硬编码中文→英文
  } catch (e: unknown) {
    gbPlayForm.value = prev
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  } finally {
    savingGbPlay.value = false
  }
}

const resetGbLearningState = async () => {
  try {
    await api.delete('/api/v1/system-config/gb28181/learning-state')
    ElMessage.success(t('configCenter.learningDataReset')) // FIXED: 硬编码中文→英文
    gbLearningState.value = null
    await loadGbPlayConfig()
  } catch (e: unknown) {
    const f = getFriendlyError(e); ElMessage.error(f.suggestion ? t('common.errorWithSuggestion', { message: f.message, suggestion: f.suggestion }) : f.message)
  }
}

// 数据库配置
const dbForm = ref({
  database_type: 'postgresql',
  host: '',
  port: 5432,
  name: '',
  username: '',
  password: '',
  sqlite_path: './pygbsentry.db',
  sqlalchemy_database_uri: ''
})
const loadingDb = ref(false)
const savingDb = ref(false)
const dbCompatVisible = ref(false)
const dbCompatSummary = ref<'ok' | 'warn' | 'error'>('ok')
const dbCompatDatabase = ref('')
const dbCompatVendorHint = ref('')
const dbCompatChecks = ref<{ name: string; ok: boolean; detail: string }[]>([])

// 多协议接入
const accessSources = ref<AuditLog[]>([])
const sourcePage = ref(1)
const sourcePageSize = ref(10)
const sourceDialogVisible = ref(false)
const editingSourceId = ref('')
const sourceFormRef = ref()
const sourceRules = {
  name: [{ required: true, message: t('configCenter.sourceNameRequired'), trigger: 'blur' }],
  protocol: [{ required: true, message: t('configCenter.sourceProtocolRequired'), trigger: 'change' }],
  host: [{ required: true, message: t('configCenter.sourceHostRequired'), trigger: 'blur' }],
  port: [{ required: true, message: t('configCenter.sourcePortRequired'), trigger: 'blur' }]
}
const sourceForm = ref({
  name: '',
  protocol: 'RTSP',
  host: '',
  port: 554,
  username: '',
  password: '',
  path: '',
  stream_name: '',
  enabled: true,
  extra: {}
})
const previewVisible = ref(false)
const previewStream = ref({ app: 'live', stream: '', url: '', hls: '', codec: 'h264' })

// 录像存储
const storageRoot = ref('')
const storageNodes = ref<{ id: string; name: string; path: string }[]>([])
const storagePage = ref(1)
const storagePageSize = ref(10)
const loadingStorage = ref(false)
const savingStorage = ref(false)
const savingStorageNodes = ref(false)
const storageNodeDialogVisible = ref(false)
const storageNodeForm = ref({ id: '', name: '', path: '' })
const storageNodeEditIndex = ref(-1)

// 审计日志
const auditLogs = ref<AuditLog[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditPageSize = ref(20)
const loadingAudit = ref(false)
const auditForm = ref({
  keyword: '',
  dateRange: [] as string[],
  result: ''
})

const paginatedAuditLogs = computed(() => {
  const start = (auditPage.value - 1) * auditPageSize.value
  return auditLogs.value.slice(start, start + auditPageSize.value)
})

// 加载基础配置
const loadBasicConfig = async () => {
  try {
    const { data } = await api.get('/api/v1/config-center/basic')
    if (data && typeof data === 'object') {
      const safeData: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(data)) {
        if (v !== null && v !== undefined) safeData[k] = v
      }
      basicForm.value = { ...basicForm.value, ...safeData }
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

const saveBasicConfig = async () => {
  savingBasic.value = true
  const prev = { ...basicForm.value }
  try {
    await api.put('/api/v1/config-center/basic', basicForm.value)
    ElMessage.success(t('configCenter.basicConfigSaved')) // FIXED: 硬编码中文→英文
  } catch (e: unknown) {
    basicForm.value = prev
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    savingBasic.value = false
  }
}

// 加载数据库配置
const loadDbConfig = async () => {
  loadingDb.value = true
  try {
    const { data } = await api.get('/api/v1/system-config/database')
    dbForm.value = { ...dbForm.value, ...data }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    loadingDb.value = false
  }
}

// 测试数据库连接
const testDbConfig = async () => {
  try {
    const { data } = await api.post('/api/v1/system-config/database/test', dbForm.value)
    if (data.compatibility) {
      dbCompatSummary.value = data.compatibility.summary || 'ok'
      dbCompatDatabase.value = data.compatibility.database || ''
      dbCompatVendorHint.value = data.compatibility.vendor_hint || ''
      dbCompatChecks.value = data.compatibility.checks || []
      dbCompatVisible.value = true
      if (data.compatibility.summary === 'ok') {
        ElMessage.success(t('configCenter.dbTestSuccess')) // FIXED: 硬编码中文→英文
      } else {
        ElMessage.warning(t('configCenter.dbTestRisk')) // FIXED: 硬编码中文→英文
      }
    } else {
      ElMessage.success(t('configCenter.dbTestSuccess')) // FIXED: 硬编码中文→英文
    }
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

// 保存数据库配置
const saveDbConfig = async () => {
  savingDb.value = true
  const prev = { ...dbForm.value }
  try {
    await api.put('/api/v1/system-config/database', dbForm.value)
    ElMessage.success(t('configCenter.dbConfigSaved')) // FIXED: 硬编码中文→英文
  } catch (e: unknown) {
    dbForm.value = prev
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    savingDb.value = false
  }
}

// 加载数据库兼容性报告
const loadDbCompatReport = async () => {
  try {
    const { data } = await api.get('/api/v1/ops/db-compat-report')
    dbCompatSummary.value = data.summary || 'error'
    dbCompatDatabase.value = data.database || ''
    dbCompatVendorHint.value = data.vendor_hint || ''
    dbCompatChecks.value = data.checks || []
    dbCompatVisible.value = true
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

// 加载接入源
const loadSources = async () => {
  try {
    const { data } = await api.get('/api/v1/integrations/sources')
    accessSources.value = data
  } catch (e) {
    logger.warn('加载接入源失败:', e)
    accessSources.value = []
  }
}

// 打开接入源弹窗
const openSourceDialog = (row?: Record<string, unknown>) => {
  editingSourceId.value = String(row?.id || '')
  sourceForm.value = row ? {
    name: String(row.name || ''),
    protocol: String(row.protocol || 'RTSP'),
    host: String(row.host || ''),
    port: Number(row.port || 554),
    username: String(row.username || ''),
    password: '',
    path: String(row.path || ''),
    stream_name: String(row.stream_name || ''),
    enabled: row.enabled !== false,
    extra: (row.extra || {}) as any
  } : {
    name: '',
    protocol: 'RTSP',
    host: '',
    port: 554,
    username: '',
    password: '',
    path: '',
    stream_name: '',
    enabled: true,
    extra: {}
  }
  sourceDialogVisible.value = true
}

// 保存接入源
const saveSource = async () => {
  if (sourceFormRef.value) {
    try {
      await sourceFormRef.value.validate()
    } catch {
      return
    }
  }
  try {
    const payload: Record<string, unknown> = { ...sourceForm.value }
    if (!payload.password) delete payload.password
    const url = editingSourceId.value
      ? `/api/v1/integrations/sources/${editingSourceId.value}`
      : '/api/v1/integrations/sources'
    const method = editingSourceId.value ? 'PUT' : 'POST'
    if (method === 'PUT') {
      await api.put(url, payload)
    } else {
      await api.post(url, payload)
    }
    sourceDialogVisible.value = false
    await loadSources()
    ElMessage.success(editingSourceId.value ? t('configCenter.sourceUpdated') : t('configCenter.sourceCreated')) // FIXED: 硬编码中文→英文
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

// 测试接入源
const testSource = async (id: string) => {
  try {
    const { data } = await api.post(`/api/v1/integrations/sources/${id}/test`)
    ElMessage.success(data.message || t('configCenter.sourceTestCompleted')) // FIXED: 硬编码中文→英文
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

// 删除接入源
const deleteSource = async (id: string) => {
  try {
    await ElMessageBox.confirm(t('configCenter.deleteSourceConfirm'), t('configCenter.deleteSourceTitle'), { type: 'warning' }) // FIXED: 硬编码中文→英文
  } catch {
    return
  }
  try {
    await api.delete(`/api/v1/integrations/sources/${id}`)
    await loadSources()
    ElMessage.success(t('configCenter.sourceDeleted')) // FIXED: 硬编码中文→英文
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

// 预览接入源
const previewSource = async (id: string) => {
  try {
    const { data } = await api.post(`/api/v1/integrations/sources/${id}/play`)
    previewStream.value = {
      app: data.app || 'live',
      stream: data.stream || '',
      url: data.flv || '',
      hls: data.hls || '',
      codec: data.codec || 'h264'
    }
    previewVisible.value = true
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  }
}

// 关闭预览
const closePreview = async () => {
  const current = previewStream.value
  previewVisible.value = false
  if (current.stream) {
    try {
      await api.post('/api/v1/stream/stop', { app: current.app, stream: current.stream })
    } catch (e) {
      logger.warn('停止预览流失败:', e)
    }
  }
  previewStream.value = { app: 'live', stream: '', url: '', hls: '', codec: 'h264' }
}

// 接入源更多操作
const handleSourceMoreCommand = async (row: Record<string, unknown>, cmd: string) => {
  if (cmd === 'preview') {
    await previewSource(row.id as string)
  } else if (cmd === 'delete') {
    await deleteSource(row.id as string)
  }
}

// 加载录像存储配置
const loadStorageConfig = async () => {
  loadingStorage.value = true
  try {
    const [rootRes, nodesRes] = await Promise.all([
      api.get('/api/v1/record-schedule/storage-config'),
      api.get('/api/v1/record-schedule/storage-nodes')
    ])
    const rootData = rootRes.data
    storageRoot.value = rootData.storage_root || ''
    const nodesData = nodesRes.data
    storageNodes.value = nodesData.nodes || []
  } catch (e) {
    storageRoot.value = ''
    storageNodes.value = []
  } finally {
    loadingStorage.value = false
  }
}

// 保存录像存储配置
const saveStorageConfig = async () => {
  savingStorage.value = true
  try {
    await api.put('/api/v1/record-schedule/storage-config', { storage_root: storageRoot.value })
    ElMessage.success(t('configCenter.storageRootSaved'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    savingStorage.value = false
  }
}

// 存储节点弹窗
const openStorageNodeDialog = (row?: { id: string; name: string; path: string }, index = -1) => {
  storageNodeEditIndex.value = index
  if (row) {
    storageNodeForm.value = { id: row.id, name: row.name, path: row.path }
  } else {
    storageNodeForm.value = { id: '', name: '', path: '' }
  }
  storageNodeDialogVisible.value = true
}

// 确认存储节点
const confirmStorageNode = () => {
  const id = storageNodeForm.value.id.trim()
  const name = storageNodeForm.value.name.trim()
  const path = storageNodeForm.value.path.trim()
  if (!id || !name || !path) {
    ElMessage.warning(t('configCenter.fillNodeInfo'))  // FIXED: 硬编码中文→i18n
    return
  }
  if (storageNodeEditIndex.value >= 0) {
    storageNodes.value[storageNodeEditIndex.value] = { id, name, path }
  } else {
    storageNodes.value.push({ id, name, path })
  }
  storageNodeDialogVisible.value = false
}

// 删除存储节点
const removeStorageNode = (index: number) => {
  storageNodes.value.splice(index, 1)
}

// 保存存储节点列表
const saveStorageNodes = async () => {
  savingStorageNodes.value = true
  try {
    await api.put('/api/v1/record-schedule/storage-nodes', { nodes: storageNodes.value })
    ElMessage.success(t('configCenter.nodeListSaved'))  // FIXED: 硬编码中文→i18n
  } catch (e: unknown) {
    ElMessage.error(getFriendlyError(e).message)
  } finally {
    savingStorageNodes.value = false
  }
}

// 加载审计日志
const loadAuditLogs = async () => {
  loadingAudit.value = true
  try {
    const params: Record<string, unknown> = {
      page: auditPage.value,
      page_size: auditPageSize.value
    }
    if (auditForm.value.keyword) params.keyword = auditForm.value.keyword
    if (auditForm.value.result) params.result = auditForm.value.result
    if (auditForm.value.dateRange?.length === 2) {
      params.start_date = auditForm.value.dateRange[0]
      params.end_date = auditForm.value.dateRange[1]
    }
    const { data } = await api.get('/api/v1/audit-center/logs', { params })
    auditLogs.value = data.items || []
    auditTotal.value = data.total || 0
  } catch (e) {
    auditLogs.value = []
    auditTotal.value = 0
  } finally {
    loadingAudit.value = false
  }
}

// 重置审计筛选
const resetAuditFilters = () => {
  auditForm.value = { keyword: '', dateRange: [], result: '' }
  auditPage.value = 1
  loadAuditLogs()
}

// 加载所有数据
const loadAllData = async () => {
  await Promise.all([
    loadBasicConfig(),
    loadDbConfig(),
    loadSources(),
    loadStorageConfig(),
    loadGbPlayConfig()
  ])
  ElMessage.success(t('configCenter.configRefreshed'))  // FIXED: 硬编码中文→i18n
}

onMounted(() => {
  loadAllData()
})
</script>

<style scoped>
.config-tabs {
  margin-top: 16px;
}
.config-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px 0;
}
.config-tabs :deep(.el-tabs__content) {
  padding-top: 0;
}
.w-52 {
  width: 208px;
}
.table-action-inline {
  display: flex;
  align-items: center;
  gap: 6px;
}
.table-action-more {
  padding: 4px 8px;
}
</style>
