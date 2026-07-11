<template>
<template v-if="isStreamHealthPlugin">
              <div class="mt-6 flex flex-wrap gap-3 items-center">
                <el-input
                  v-model="streamHealthAppFilter"
                  :placeholder="t('plugin.panels.filterByApp')"
                  size="small"
                  style="width: 220px"
                  clearable
                />
                <el-input
                  v-model="streamHealthStreamFilter"
                  :placeholder="t('plugin.panels.filterByStream')"
                  size="small"
                  style="width: 260px"
                  clearable
                />
                <el-switch
                  v-model="streamHealthOnlyLowBitrate"
                  :active-text="t('plugin.panels.onlyLowBitrate')"
                  :inactive-text="t('plugin.panels.viewAll')"
                />
                <el-button type="primary" size="small" :loading="streamHealthLoading" @click="fetchStreamHealth">
                  {{ t('plugin.panels.refreshHealthSnapshot') }}
                </el-button>
              </div>

              <div v-if="streamHealthError" class="mt-3">
                <el-alert :title="streamHealthError" type="error" show-icon />
              </div>

              <el-table
                v-loading="streamHealthLoading"
                class="mt-3"
                :data="paginatedStreamHealthRows"
                size="small"
                :empty-text="t('plugin.panels.noData')"
                style="width: 100%"
              >
                <el-table-column prop="app" :label="t('plugin.panels.app')" width="140" />
                <el-table-column prop="stream" :label="t('plugin.panels.channel')" min-width="200" />
                <el-table-column prop="total_reader_count" :label="t('plugin.panels.viewers')" width="110" />
                <el-table-column prop="bytes_speed_kbps" :label="t('plugin.panels.bitrateKBps')" width="140" />
                <el-table-column :label="t('plugin.panels.status')" width="120">
                  <template #default="scope">
                    <el-tag :type="scope.row.is_low_bitrate ? 'danger' : 'success'" effect="dark">
                      {{ scope.row.is_low_bitrate ? t('plugin.panels.lowBitrate') : t('plugin.panels.normal') }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>

              <div class="mt-4 flex justify-end">
                <el-pagination
                  v-model:current-page="streamHealthPage"
                  v-model:page-size="streamHealthPageSize"
                  :page-sizes="[10, 20, 50, 100]"
                  layout="total, sizes, prev, pager, next, jumper"
                  :total="streamHealthRows.length"
                />
              </div>
            </template>

            <template v-if="isSipLoggerPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="sipTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />

                  <el-input
                    v-model="sipLogKeyword"
                    :placeholder="t('plugin.panels.keywordOptional')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-select v-model="sipLogDirection" :placeholder="t('plugin.panels.directionOptional')" size="small" style="width: 140px" clearable>
                    <el-option :label="t('plugin.panels.all')" :value="''" />
                    <el-option label="inbound" value="inbound" />
                    <el-option label="outbound" value="outbound" />
                  </el-select>

                  <el-select v-model="sipLogProto" :placeholder="t('plugin.panels.protoOptional')" size="small" style="width: 140px" clearable>
                    <el-option :label="t('plugin.panels.all')" :value="''" />
                    <el-option label="UDP" value="UDP" />
                    <el-option label="TCP" value="TCP" />
                  </el-select>

                  <el-button type="primary" size="small" :loading="sipLogLoading" @click="fetchSipLoggerLogs">
                    {{ t('plugin.panels.query') }}
                  </el-button>
                </div>

                <div v-if="sipLogError" class="mt-3">
                  <el-alert :title="sipLogError" type="error" show-icon />
                </div>

                <el-table
                  v-loading="sipLogLoading"
                  class="mt-3"
                  :data="sipLogRows"
                  size="small"
                  :empty-text="t('plugin.panels.noData')"
                  style="width: 100%"
                >
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="direction" :label="t('plugin.panels.direction')" width="90" />
                  <el-table-column prop="proto" :label="t('plugin.panels.proto')" width="90" />
                  <el-table-column prop="addr" :label="t('plugin.panels.address')" min-width="170" show-overflow-tooltip />
                  <el-table-column prop="snippet" :label="t('plugin.panels.content')" min-width="260" show-overflow-tooltip />
                </el-table>

                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { sipLogPage = Math.max(1, sipLogPage - 1); fetchSipLoggerLogs() }" :disabled="sipLogPage <= 1">
                      {{ t('plugin.panels.prevPage') }}
                    </el-button>
                    <el-button size="small" type="primary" @click="() => { sipLogPage = sipLogPage + 1; fetchSipLoggerLogs() }" :disabled="!sipLogHasMore">
                      {{ t('plugin.panels.nextPage') }}
                    </el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select
                      v-model="sipLogPageSize"
                      size="small"
                      style="width: 120px"
                      @change="() => { sipLogPage = 1; fetchSipLoggerLogs() }"
                    >
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: sipLogPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isNetworkWatchdogPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="nwTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />

                  <el-input
                    v-model="nwKeyword"
                    :placeholder="t('plugin.panels.keywordOptional')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-input
                    v-model="nwDevice"
                    :placeholder="t('plugin.panels.deviceGbIdOptional')"
                    size="small"
                    style="width: 200px"
                    clearable
                  />

                  <el-input
                    v-model="nwIp"
                    :placeholder="t('common.ip')"
                    size="small"
                    style="width: 160px"
                    clearable
                  />

                  <el-button type="primary" size="small" :loading="nwLoading" @click="fetchNetworkWatchdogEvents">
                    {{ t('plugin.panels.query') }}
                  </el-button>
                </div>

                <div v-if="nwError" class="mt-3">
                  <el-alert :title="nwError" type="error" show-icon />
                </div>

                <el-table
                  v-loading="nwLoading"
                  class="mt-3"
                  :data="nwRows"
                  size="small"
                  :empty-text="t('plugin.panels.noData')"
                  style="width: 100%"
                >
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="device" :label="t('common.device')" width="140" />
                  <el-table-column prop="ip" :label="t('common.ip')" width="160" />
                  <el-table-column prop="message" :label="t('plugin.panels.content')" min-width="260" show-overflow-tooltip />
                </el-table>

                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { nwPage = Math.max(1, nwPage - 1); fetchNetworkWatchdogEvents() }" :disabled="nwPage <= 1">
                      {{ t('plugin.panels.prevPage') }}
                    </el-button>
                    <el-button size="small" type="primary" @click="() => { nwPage = nwPage + 1; fetchNetworkWatchdogEvents() }" :disabled="!nwHasMore">
                      {{ t('plugin.panels.nextPage') }}
                    </el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select
                      v-model="nwPageSize"
                      size="small"
                      style="width: 120px"
                      @change="() => { nwPage = 1; fetchNetworkWatchdogEvents() }"
                    >
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: nwPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isStreamIdlePlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="siTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />

                  <el-input
                    v-model="siKeyword"
                    :placeholder="t('plugin.panels.keywordOptional')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-input
                    v-model="siApp"
                    :placeholder="t('plugin.panels.filterByApp')"
                    size="small"
                    style="width: 160px"
                    clearable
                  />

                  <el-input
                    v-model="siStream"
                    :placeholder="t('plugin.panels.filterByStream')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-input
                    v-model="siNode"
                    :placeholder="t('plugin.panels.zlmNode')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-button type="primary" size="small" :loading="siLoading" @click="fetchStreamIdleEvents">
                    {{ t('plugin.panels.query') }}
                  </el-button>
                </div>

                <div v-if="siError" class="mt-3">
                  <el-alert :title="siError" type="error" show-icon />
                </div>

                <el-table
                  v-loading="siLoading"
                  class="mt-3"
                  :data="siRows"
                  size="small"
                  :empty-text="t('plugin.panels.noData')"
                  style="width: 100%"
                >
                  <el-table-column prop="ts" :label="t('plugin.panels.breakTime')" width="190" />
                  <el-table-column prop="app" :label="t('plugin.panels.app')" width="90" />
                  <el-table-column prop="stream" :label="t('plugin.panels.channel')" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="node" :label="t('plugin.panels.zlmNode')" min-width="140" show-overflow-tooltip />
                  <el-table-column prop="start" :label="t('plugin.panels.sessionStart')" min-width="190" show-overflow-tooltip />
                  <el-table-column prop="duration_s" :label="t('plugin.panels.durationS')" width="100" />
                </el-table>

                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { siPage = Math.max(1, siPage - 1); fetchStreamIdleEvents() }" :disabled="siPage <= 1">
                      {{ t('plugin.panels.prevPage') }}
                    </el-button>
                    <el-button size="small" type="primary" @click="() => { siPage = siPage + 1; fetchStreamIdleEvents() }" :disabled="!siHasMore">
                      {{ t('plugin.panels.nextPage') }}
                    </el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select
                      v-model="siPageSize"
                      size="small"
                      style="width: 120px"
                      @change="() => { siPage = 1; fetchStreamIdleEvents() }"
                    >
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: siPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isTimelapsePlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="tlTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />

                  <el-input
                    v-model="tlKeyword"
                    :placeholder="t('plugin.panels.keywordOptional')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-input
                    v-model="tlApp"
                    :placeholder="t('plugin.panels.filterByApp')"
                    size="small"
                    style="width: 160px"
                    clearable
                  />

                  <el-input
                    v-model="tlStream"
                    :placeholder="t('plugin.panels.filterByStream')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-button type="primary" size="small" :loading="tlLoading" @click="fetchTimelapseEvents">
                    {{ t('plugin.panels.query') }}
                  </el-button>
                </div>

                <div v-if="tlError" class="mt-3">
                  <el-alert :title="tlError" type="error" show-icon />
                </div>

                <el-table
                  v-loading="tlLoading"
                  class="mt-3"
                  :data="tlRows"
                  size="small"
                  :empty-text="t('plugin.panels.noData')"
                  style="width: 100%"
                >
                  <el-table-column prop="ts" :label="t('plugin.panels.screenshotTime')" width="190" />
                  <el-table-column prop="app" :label="t('plugin.panels.app')" width="90" />
                  <el-table-column prop="stream" :label="t('plugin.panels.channel')" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="asset_id" label="asset_id" min-width="140" show-overflow-tooltip />
                  <el-table-column prop="file" :label="t('plugin.panels.fileRelative')" min-width="260" show-overflow-tooltip />
                </el-table>

                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { tlPage = Math.max(1, tlPage - 1); fetchTimelapseEvents() }" :disabled="tlPage <= 1">
                      {{ t('plugin.panels.prevPage') }}
                    </el-button>
                    <el-button size="small" type="primary" @click="() => { tlPage = tlPage + 1; fetchTimelapseEvents() }" :disabled="!tlHasMore">
                      {{ t('plugin.panels.nextPage') }}
                    </el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select
                      v-model="tlPageSize"
                      size="small"
                      style="width: 120px"
                      @change="() => { tlPage = 1; fetchTimelapseEvents() }"
                    >
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: tlPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isWebhookPusherPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="wpTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />

                  <el-input
                    v-model="wpDevice"
                    :placeholder="t('plugin.panels.deviceGbIdOptional')"
                    size="small"
                    style="width: 200px"
                    clearable
                  />

                  <el-select v-model="wpStatus" :placeholder="t('plugin.panels.status')" size="small" style="width: 140px" clearable>
                    <el-option :label="t('plugin.panels.online')" value="online" />
                    <el-option :label="t('plugin.panels.offline')" value="offline" />
                  </el-select>

                  <el-select v-model="wpOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>

                  <el-input
                    v-model="wpKeyword"
                    :placeholder="t('plugin.panels.keywordOptional')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-button type="primary" size="small" :loading="wpLoading" @click="fetchWebhookPusherEvents">
                    {{ t('plugin.panels.query') }}
                  </el-button>
                </div>

                <div v-if="wpError" class="mt-3">
                  <el-alert :title="wpError" type="error" show-icon />
                </div>

                <el-table
                  v-loading="wpLoading"
                  class="mt-3"
                  :data="wpRows"
                  size="small"
                  :empty-text="t('plugin.panels.noData')"
                  style="width: 100%"
                >
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="device" :label="t('common.device')" min-width="170" show-overflow-tooltip />
                  <el-table-column prop="status" :label="t('plugin.panels.status')" width="90" />
                  <el-table-column :label="t('plugin.panels.result')" width="110">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="260" show-overflow-tooltip />
                </el-table>

                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { wpPage = Math.max(1, wpPage - 1); fetchWebhookPusherEvents() }" :disabled="wpPage <= 1">
                      {{ t('plugin.panels.prevPage') }}
                    </el-button>
                    <el-button size="small" type="primary" @click="() => { wpPage = wpPage + 1; fetchWebhookPusherEvents() }" :disabled="!wpHasMore">
                      {{ t('plugin.panels.nextPage') }}
                    </el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select
                      v-model="wpPageSize"
                      size="small"
                      style="width: 120px"
                      @change="() => { wpPage = 1; fetchWebhookPusherEvents() }"
                    >
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: wpPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isS3SyncPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="s3TimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />

                  <el-input
                    v-model="s3Bucket"
                    :placeholder="t('plugin.panels.filterByApp')"
                    size="small"
                    style="width: 200px"
                    clearable
                  />

                  <el-select v-model="s3OkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>

                  <el-input
                    v-model="s3Keyword"
                    :placeholder="t('plugin.panels.keywordOptional')"
                    size="small"
                    style="width: 220px"
                    clearable
                  />

                  <el-button type="primary" size="small" :loading="s3Loading" @click="fetchS3SyncEvents">
                    {{ t('plugin.panels.query') }}
                  </el-button>
                </div>

                <div v-if="s3Error" class="mt-3">
                  <el-alert :title="s3Error" type="error" show-icon />
                </div>

                <el-table
                  v-loading="s3Loading"
                  class="mt-3"
                  :data="s3Rows"
                  size="small"
                  :empty-text="t('plugin.panels.noData')"
                  style="width: 100%"
                >
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="bucket" :label="t('plugin.panels.filterByApp')" min-width="140" show-overflow-tooltip />
                  <el-table-column prop="rel" :label="t('plugin.panels.objectKeyRelative')" min-width="280" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.size')" width="110">
                    <template #default="scope">
                      <span v-if="scope.row.ok && scope.row.size_bytes != null">{{ scope.row.size_bytes }}</span>
                      <span v-else style="color: var(--el-text-color-placeholder)">—</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>

                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { s3Page = Math.max(1, s3Page - 1); fetchS3SyncEvents() }" :disabled="s3Page <= 1">
                      {{ t('plugin.panels.prevPage') }}
                    </el-button>
                    <el-button size="small" type="primary" @click="() => { s3Page = s3Page + 1; fetchS3SyncEvents() }" :disabled="!s3HasMore">
                      {{ t('plugin.panels.nextPage') }}
                    </el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select
                      v-model="s3PageSize"
                      size="small"
                      style="width: 120px"
                      @change="() => { s3Page = 1; fetchS3SyncEvents() }"
                    >
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: s3Page }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isPtzTourPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="ptzTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="ptzDevice" :placeholder="t('plugin.panels.deviceGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-input v-model="ptzChannel" :placeholder="t('plugin.panels.channelGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="ptzOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="ptzKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 220px" clearable />
                  <el-button type="primary" size="small" :loading="ptzLoading" @click="fetchPtzTourEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="ptzError" class="mt-3">
                  <el-alert :title="ptzError" type="error" show-icon />
                </div>
                <el-table v-loading="ptzLoading" class="mt-3" :data="ptzRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="device" :label="t('common.device')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="channel" :label="t('plugin.panels.channel')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="preset" :label="t('plugin.panels.preset')" width="90" />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { ptzPage = Math.max(1, ptzPage - 1); fetchPtzTourEvents() }" :disabled="ptzPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { ptzPage = ptzPage + 1; fetchPtzTourEvents() }" :disabled="!ptzHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="ptzPageSize" size="small" style="width: 120px" @change="() => { ptzPage = 1; fetchPtzTourEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: ptzPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isAutoRecordPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="arTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="arStream" :placeholder="t('plugin.panels.channelGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="arOp" :placeholder="t('plugin.panels.operation')" size="small" style="width: 160px" clearable>
                    <el-option label="startRecord" value="start_record" />
                    <el-option label="stopRecord" value="stop_record" />
                  </el-select>
                  <el-select v-model="arOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="arKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 220px" clearable />
                  <el-button type="primary" size="small" :loading="arLoading" @click="fetchAutoRecordEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="arError" class="mt-3">
                  <el-alert :title="arError" type="error" show-icon />
                </div>
                <el-table v-loading="arLoading" class="mt-3" :data="arRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="op" :label="t('plugin.panels.operation')" width="120" />
                  <el-table-column prop="stream" :label="t('plugin.panels.channelStream')" min-width="200" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { arPage = Math.max(1, arPage - 1); fetchAutoRecordEvents() }" :disabled="arPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { arPage = arPage + 1; fetchAutoRecordEvents() }" :disabled="!arHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="arPageSize" size="small" style="width: 120px" @change="() => { arPage = 1; fetchAutoRecordEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: arPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isRecordScheduleExecutorPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="rseTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="rseSchedule" :placeholder="t('plugin.panels.planId')" size="small" style="width: 200px" clearable />
                  <el-input v-model="rseStream" :placeholder="t('plugin.panels.channelGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="rseEvt" :placeholder="t('plugin.panels.event')" size="small" style="width: 200px" clearable>
                    <el-option label="start_ok" value="start_ok" />
                    <el-option label="start_fail" value="start_fail" />
                    <el-option label="stop_ok" value="stop_ok" />
                    <el-option label="stop_fail" value="stop_fail" />
                    <el-option label="blocked_stream" value="blocked_stream" />
                  </el-select>
                  <el-input v-model="rseKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="rseLoading" @click="fetchRecordScheduleExecutorEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="rseError" class="mt-3">
                  <el-alert :title="rseError" type="error" show-icon />
                </div>
                <el-table v-loading="rseLoading" class="mt-3" :data="rseRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="schedule" :label="t('plugin.panels.planId')" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="stream" :label="t('plugin.panels.channel')" min-width="180" show-overflow-tooltip />
                  <el-table-column prop="evt" :label="t('plugin.panels.event')" width="130" />
                  <el-table-column :label="t('plugin.panels.summary')" width="110">
                    <template #default="scope">
                      <el-tag
                        v-if="scope.row.evt === 'start_ok' || scope.row.evt === 'stop_ok'"
                        type="success"
                        effect="dark"
                        size="small"
                      >{{ t('plugin.panels.success') }}</el-tag>
                      <el-tag v-else-if="scope.row.evt === 'blocked_stream'" type="warning" effect="dark" size="small">{{ t('plugin.panels.notStreaming') }}</el-tag>
                      <el-tag v-else type="danger" effect="dark" size="small">{{ t('plugin.panels.failed') }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('plugin.panels.errorAndSuggestion')" min-width="360">
                    <template #default="scope">
                      <div class="whitespace-pre-wrap break-all">{{ scope.row.err || '-' }}</div>
                      <div
                        v-if="!scope.row.ok && getAlertEventTroubleshooting('feishu_alert', scope.row).summary"
                        class="mt-2 rounded border border-[var(--el-border-color)] bg-[var(--el-fill-color-light)] p-2"
                      >
                        <div class="text-xs font-medium">{{ getAlertEventTroubleshooting('feishu_alert', scope.row).title }}</div>
                        <div class="mt-1 text-xs leading-5">{{ getAlertEventTroubleshooting('feishu_alert', scope.row).summary }}</div>
                        <div class="mt-1 text-xs leading-5">
                          {{ t('plugin.panels.priorityCheck') }}：{{ getAlertEventTroubleshooting('feishu_alert', scope.row).steps.slice(0, 2).join('；') }}
                        </div>
                        <div
                          v-if="getAlertEventTroubleshooting('feishu_alert', scope.row).fieldKeys?.length"
                          class="mt-2 flex flex-wrap gap-2"
                        >
                          <el-button
                            v-for="fieldKey in getAlertEventTroubleshooting('feishu_alert', scope.row).fieldKeys || []"
                            :key="fieldKey"
                            size="small"
                            @click="emit('focus-config-field', fieldKey)"
                          >
                            {{ t('plugin.panels.locate') }}{{ (getNotificationFieldLabel as any)('feishu', fieldKey) }}
                          </el-button>
                        </div>
                        <div class="mt-2 flex flex-wrap gap-2">
                          <el-button size="small" type="primary" @click="emit('retry-alert-test', 'feishu_alert')">
                            {{ t('plugin.panels.resendTest') }}
                          </el-button>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { rsePage = Math.max(1, rsePage - 1); fetchRecordScheduleExecutorEvents() }" :disabled="rsePage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { rsePage = rsePage + 1; fetchRecordScheduleExecutorEvents() }" :disabled="!rseHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="rsePageSize" size="small" style="width: 120px" @change="() => { rsePage = 1; fetchRecordScheduleExecutorEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: rsePage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isRecordIndexVerifierPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="rivTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="rivRecordId" :placeholder="t('plugin.panels.recordId')" size="small" style="width: 220px" clearable />
                  <el-select v-model="rivOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 150px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.pass')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-select v-model="rivNote" :placeholder="t('plugin.panels.remark')" size="small" style="width: 180px" clearable>
                    <el-option label="ok" value="ok" />
                    <el-option label="auto_repaired" value="auto_repaired" />
                  </el-select>
                  <el-input v-model="rivKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="rivLoading" @click="fetchRecordIndexVerifierEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="rivError" class="mt-3">
                  <el-alert :title="rivError" type="error" show-icon />
                </div>
                <el-table v-loading="rivLoading" class="mt-3" :data="rivRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="record_id" :label="t('plugin.panels.recordId')" min-width="220" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.httpCode')" width="100">
                    <template #default="scope">
                      <span>{{ scope.row.code_raw ?? scope.row.code ?? '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="note" :label="t('plugin.panels.remark')" width="130" />
                  <el-table-column :label="t('plugin.panels.result')" width="90">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.pass') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { rivPage = Math.max(1, rivPage - 1); fetchRecordIndexVerifierEvents() }" :disabled="rivPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { rivPage = rivPage + 1; fetchRecordIndexVerifierEvents() }" :disabled="!rivHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="rivPageSize" size="small" style="width: 120px" @change="() => { rivPage = 1; fetchRecordIndexVerifierEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: rivPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isSnapshotRefreshPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="snapTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="snapAsset" :placeholder="t('plugin.panels.deviceGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-input v-model="snapChannel" :placeholder="t('plugin.panels.channelGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="snapOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="snapKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="snapLoading" @click="fetchSnapshotRefreshEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="snapError" class="mt-3">
                  <el-alert :title="snapError" type="error" show-icon />
                </div>
                <el-table v-loading="snapLoading" class="mt-3" :data="snapRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="asset" :label="t('common.device')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="channel" :label="t('plugin.panels.channel')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="stream_type" :label="t('plugin.panels.streamType')" width="90" />
                  <el-table-column :label="t('plugin.panels.result')" width="90">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { snapPage = Math.max(1, snapPage - 1); fetchSnapshotRefreshEvents() }" :disabled="snapPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { snapPage = snapPage + 1; fetchSnapshotRefreshEvents() }" :disabled="!snapHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="snapPageSize" size="small" style="width: 120px" @change="() => { snapPage = 1; fetchSnapshotRefreshEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: snapPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isRtmpPushChannelMonitorPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="rtmpTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="rtmpStream" :placeholder="t('plugin.panels.filterByStream')" size="small" style="width: 200px" clearable />
                  <el-input v-model="rtmpSourceId" :placeholder="t('plugin.panels.sourceId')" size="small" style="width: 200px" clearable />
                  <el-select v-model="rtmpEvt" :placeholder="t('plugin.panels.event')" size="small" style="width: 180px" clearable>
                    <el-option :label="t('plugin.panels.autoStopStream')" value="auto_stop" />
                    <el-option :label="t('plugin.panels.channelStatus')" value="resource_status" />
                  </el-select>
                  <el-input v-model="rtmpKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="rtmpLoading" @click="fetchRtmpPushMonitorEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="rtmpError" class="mt-3">
                  <el-alert :title="rtmpError" type="error" show-icon />
                </div>
                <el-table v-loading="rtmpLoading" class="mt-3" :data="rtmpRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="evt" :label="t('plugin.panels.event')" width="150" />
                  <el-table-column prop="stream" label="stream" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="source_id" :label="t('plugin.panels.sourceId')" min-width="200" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.statusResult')" width="130">
                    <template #default="scope">
                      <template v-if="scope.row.evt === 'resource_status'">
                        <el-tag type="info" size="small">{{ Number(scope.row.status) === 1 ? t('plugin.panels.online') : t('plugin.panels.offline') }}</el-tag>
                      </template>
                      <template v-else>
                        <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                          {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                        </el-tag>
                      </template>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { rtmpPage = Math.max(1, rtmpPage - 1); fetchRtmpPushMonitorEvents() }" :disabled="rtmpPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { rtmpPage = rtmpPage + 1; fetchRtmpPushMonitorEvents() }" :disabled="!rtmpHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="rtmpPageSize" size="small" style="width: 120px" @change="() => { rtmpPage = 1; fetchRtmpPushMonitorEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: rtmpPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isPullProxyMonitorPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="ppmTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="ppmStream" :placeholder="t('plugin.panels.filterByStream')" size="small" style="width: 200px" clearable />
                  <el-select v-model="ppmEvt" :placeholder="t('plugin.panels.event')" size="small" style="width: 160px" clearable>
                    <el-option :label="t('plugin.panels.autoStopStream')" value="auto_stop" />
                    <el-option :label="t('plugin.panels.autoRetryPull')" value="auto_retry" />
                  </el-select>
                  <el-select v-model="ppmOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="ppmKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="ppmLoading" @click="fetchPullProxyMonitorEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="ppmError" class="mt-3">
                  <el-alert :title="ppmError" type="error" show-icon />
                </div>
                <el-table v-loading="ppmLoading" class="mt-3" :data="ppmRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="evt" :label="t('plugin.panels.event')" width="120" />
                  <el-table-column prop="stream" label="stream" min-width="200" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('plugin.panels.errorAndSuggestion')" min-width="360">
                    <template #default="scope">
                      <div class="whitespace-pre-wrap break-all">{{ scope.row.err || '-' }}</div>
                      <div
                        v-if="!scope.row.ok && getAlertEventTroubleshooting('wecom_alert', scope.row).summary"
                        class="mt-2 rounded border border-[var(--el-border-color)] bg-[var(--el-fill-color-light)] p-2"
                      >
                        <div class="text-xs font-medium">{{ getAlertEventTroubleshooting('wecom_alert', scope.row).title }}</div>
                        <div class="mt-1 text-xs leading-5">{{ getAlertEventTroubleshooting('wecom_alert', scope.row).summary }}</div>
                        <div class="mt-1 text-xs leading-5">
                          {{ t('plugin.panels.priorityCheck') }}：{{ getAlertEventTroubleshooting('wecom_alert', scope.row).steps.slice(0, 2).join('；') }}
                        </div>
                        <div
                          v-if="getAlertEventTroubleshooting('wecom_alert', scope.row).fieldKeys?.length"
                          class="mt-2 flex flex-wrap gap-2"
                        >
                          <el-button
                            v-for="fieldKey in getAlertEventTroubleshooting('wecom_alert', scope.row).fieldKeys || []"
                            :key="fieldKey"
                            size="small"
                            @click="emit('focus-config-field', fieldKey)"
                          >
                            {{ t('plugin.panels.locate') }}{{ (getNotificationFieldLabel as any)('wecom', fieldKey) }}
                          </el-button>
                        </div>
                        <div class="mt-2 flex flex-wrap gap-2">
                          <el-button size="small" type="primary" @click="emit('retry-alert-test', 'wecom_alert')">
                            {{ t('plugin.panels.resendTest') }}
                          </el-button>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { ppmPage = Math.max(1, ppmPage - 1); fetchPullProxyMonitorEvents() }" :disabled="ppmPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { ppmPage = ppmPage + 1; fetchPullProxyMonitorEvents() }" :disabled="!ppmHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="ppmPageSize" size="small" style="width: 120px" @change="() => { ppmPage = 1; fetchPullProxyMonitorEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: ppmPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isMqttBridgePlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="mqttTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="mqttDevice" :placeholder="t('plugin.panels.deviceGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="mqttKind" :placeholder="t('plugin.panels.type')" size="small" style="width: 180px" clearable>
                    <el-option :label="t('plugin.panels.deviceStatus')" value="device_status" />
                    <el-option :label="t('plugin.panels.alarm')" value="alarm" />
                  </el-select>
                  <el-input v-model="mqttAlarmType" :placeholder="t('plugin.panels.alarmTypeOptional')" size="small" style="width: 220px" clearable />
                  <el-select v-model="mqttOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="mqttKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="mqttLoading" @click="fetchMqttBridgeEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="mqttError" class="mt-3">
                  <el-alert :title="mqttError" type="error" show-icon />
                </div>
                <el-table v-loading="mqttLoading" class="mt-3" :data="mqttRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="kind" :label="t('plugin.panels.type')" width="130" />
                  <el-table-column prop="device" :label="t('common.device')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="alarm_type" :label="t('plugin.panels.alarmType')" min-width="140" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="err" :label="t('plugin.panels.errorMsg')" min-width="220" show-overflow-tooltip />
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { mqttPage = Math.max(1, mqttPage - 1); fetchMqttBridgeEvents() }" :disabled="mqttPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { mqttPage = mqttPage + 1; fetchMqttBridgeEvents() }" :disabled="!mqttHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="mqttPageSize" size="small" style="width: 120px" @change="() => { mqttPage = 1; fetchMqttBridgeEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: mqttPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isFeishuAlertPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="feishuTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="feishuDevice" :placeholder="t('plugin.panels.deviceGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-input v-model="feishuAlarmType" :placeholder="t('plugin.panels.alarmTypeOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="feishuOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="feishuKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="feishuLoading" @click="fetchFeishuAlertEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="feishuError" class="mt-3">
                  <el-alert :title="feishuError" type="error" show-icon />
                </div>
                <el-table v-loading="feishuLoading" class="mt-3" :data="feishuRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="device" :label="t('common.device')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="alarm_type" :label="t('plugin.panels.alarmType')" min-width="160" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('plugin.panels.errorAndSuggestion')" min-width="360">
                    <template #default="scope">
                      <div class="whitespace-pre-wrap break-all">{{ scope.row.err || '-' }}</div>
                      <div
                        v-if="!scope.row.ok && getAlertEventTroubleshooting('feishu_alert', scope.row).summary"
                        class="mt-2 rounded border border-[var(--el-border-color)] bg-[var(--el-fill-color-light)] p-2"
                      >
                        <div class="text-xs font-medium">{{ getAlertEventTroubleshooting('feishu_alert', scope.row).title }}</div>
                        <div class="mt-1 text-xs leading-5">{{ getAlertEventTroubleshooting('feishu_alert', scope.row).summary }}</div>
                        <div class="mt-1 text-xs leading-5">
                          {{ t('plugin.panels.priorityCheck') }}：{{ getAlertEventTroubleshooting('feishu_alert', scope.row).steps.slice(0, 2).join('；') }}
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { feishuPage = Math.max(1, feishuPage - 1); fetchFeishuAlertEvents() }" :disabled="feishuPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { feishuPage = feishuPage + 1; fetchFeishuAlertEvents() }" :disabled="!feishuHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="feishuPageSize" size="small" style="width: 120px" @change="() => { feishuPage = 1; fetchFeishuAlertEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: feishuPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isWecomAlertPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="wecomTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="wecomDevice" :placeholder="t('plugin.panels.deviceGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-input v-model="wecomAlarmType" :placeholder="t('plugin.panels.alarmTypeOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="wecomOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="wecomKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="wecomLoading" @click="fetchWecomAlertEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="wecomError" class="mt-3">
                  <el-alert :title="wecomError" type="error" show-icon />
                </div>
                <el-table v-loading="wecomLoading" class="mt-3" :data="wecomRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="device" :label="t('common.device')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="alarm_type" :label="t('plugin.panels.alarmType')" min-width="160" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('plugin.panels.errorAndSuggestion')" min-width="360">
                    <template #default="scope">
                      <div class="whitespace-pre-wrap break-all">{{ scope.row.err || '-' }}</div>
                      <div
                        v-if="!scope.row.ok && getAlertEventTroubleshooting('wecom_alert', scope.row).summary"
                        class="mt-2 rounded border border-[var(--el-border-color)] bg-[var(--el-fill-color-light)] p-2"
                      >
                        <div class="text-xs font-medium">{{ getAlertEventTroubleshooting('wecom_alert', scope.row).title }}</div>
                        <div class="mt-1 text-xs leading-5">{{ getAlertEventTroubleshooting('wecom_alert', scope.row).summary }}</div>
                        <div class="mt-1 text-xs leading-5">
                          {{ t('plugin.panels.priorityCheck') }}：{{ getAlertEventTroubleshooting('wecom_alert', scope.row).steps.slice(0, 2).join('；') }}
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { wecomPage = Math.max(1, wecomPage - 1); fetchWecomAlertEvents() }" :disabled="wecomPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { wecomPage = wecomPage + 1; fetchWecomAlertEvents() }" :disabled="!wecomHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="wecomPageSize" size="small" style="width: 120px" @change="() => { wecomPage = 1; fetchWecomAlertEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: wecomPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="isSmsAlertPlugin">
              <div class="mt-6">
                <div class="flex flex-wrap gap-3 items-center">
                  <el-date-picker
                    v-model="smsTimeRange"
                    type="datetimerange"
                    :range-separator="t('plugin.panels.to')"
                    :start-placeholder="t('plugin.panels.startTime')"
                    :end-placeholder="t('plugin.panels.endTime')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    style="width: 360px"
                    clearable
                  />
                  <el-input v-model="smsDevice" :placeholder="t('plugin.panels.deviceGbIdOptional')" size="small" style="width: 200px" clearable />
                  <el-input v-model="smsAlarmType" :placeholder="t('plugin.panels.alarmTypeOptional')" size="small" style="width: 200px" clearable />
                  <el-select v-model="smsOkMode" :placeholder="t('plugin.panels.verifyResultOptional')" size="small" style="width: 170px">
                    <el-option :label="t('plugin.panels.all')" value="all" />
                    <el-option :label="t('plugin.panels.success')" value="true" />
                    <el-option :label="t('plugin.panels.failed')" value="false" />
                  </el-select>
                  <el-input v-model="smsKeyword" :placeholder="t('plugin.panels.keywordOptional')" size="small" style="width: 200px" clearable />
                  <el-button type="primary" size="small" :loading="smsLoading" @click="fetchSmsAlertEvents">{{ t('plugin.panels.query') }}</el-button>
                </div>
                <div v-if="smsError" class="mt-3">
                  <el-alert :title="smsError" type="error" show-icon />
                </div>
                <el-table v-loading="smsLoading" class="mt-3" :data="smsRows" size="small" :empty-text="t('plugin.panels.noData')" style="width: 100%">
                  <el-table-column prop="ts" :label="t('plugin.panels.time')" width="190" />
                  <el-table-column prop="device" :label="t('common.device')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="alarm_type" :label="t('plugin.panels.alarmType')" min-width="160" show-overflow-tooltip />
                  <el-table-column :label="t('plugin.panels.result')" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.ok ? 'success' : 'danger'" effect="dark" size="small">
                        {{ scope.row.ok ? t('plugin.panels.success') : t('plugin.panels.failed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('plugin.panels.errorAndSuggestion')" min-width="360">
                    <template #default="scope">
                      <div class="whitespace-pre-wrap break-all">{{ scope.row.err || '-' }}</div>
                      <div
                        v-if="!scope.row.ok && getAlertEventTroubleshooting('sms_alert', scope.row).summary"
                        class="mt-2 rounded border border-[var(--el-border-color)] bg-[var(--el-fill-color-light)] p-2"
                      >
                        <div class="text-xs font-medium">{{ getAlertEventTroubleshooting('sms_alert', scope.row).title }}</div>
                        <div class="mt-1 text-xs leading-5">{{ getAlertEventTroubleshooting('sms_alert', scope.row).summary }}</div>
                        <div class="mt-1 text-xs leading-5">
                          {{ t('plugin.panels.priorityCheck') }}：{{ getAlertEventTroubleshooting('sms_alert', scope.row).steps.slice(0, 2).join('；') }}
                        </div>
                        <div
                          v-if="getAlertEventTroubleshooting('sms_alert', scope.row).fieldKeys?.length"
                          class="mt-2 flex flex-wrap gap-2"
                        >
                          <el-button
                            v-for="fieldKey in getAlertEventTroubleshooting('sms_alert', scope.row).fieldKeys || []"
                            :key="fieldKey"
                            size="small"
                            @click="emit('focus-config-field', fieldKey)"
                          >
                            {{ t('plugin.panels.locate') }}{{ (getNotificationFieldLabel as any)('sms', fieldKey) }}
                          </el-button>
                        </div>
                        <div class="mt-2 flex flex-wrap gap-2">
                          <el-button size="small" type="primary" @click="emit('retry-alert-test', 'sms_alert')">
                            {{ t('plugin.panels.resendTest') }}
                          </el-button>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="flex items-center justify-between mt-3">
                  <div class="flex items-center gap-2">
                    <el-button size="small" @click="() => { smsPage = Math.max(1, smsPage - 1); fetchSmsAlertEvents() }" :disabled="smsPage <= 1">{{ t('plugin.panels.prevPage') }}</el-button>
                    <el-button size="small" type="primary" @click="() => { smsPage = smsPage + 1; fetchSmsAlertEvents() }" :disabled="!smsHasMore">{{ t('plugin.panels.nextPage') }}</el-button>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.perPage') }}</span>
                    <el-select v-model="smsPageSize" size="small" style="width: 120px" @change="() => { smsPage = 1; fetchSmsAlertEvents() }">
                      <el-option :value="20" label="20" />
                      <el-option :value="50" label="50" />
                      <el-option :value="100" label="100" />
                    </el-select>
                    <span class="text-xs" style="color: var(--el-text-color-secondary)">{{ t('plugin.panels.pageOf', { page: smsPage }) }}</span>
                  </div>
                </div>
              </div>
            </template>
            
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n' // FIXED: 国际化
import {
  getNotificationFieldLabel,
  getNotificationTroubleshootingByPluginId
} from '../../utils/notificationTroubleshooting'
import { getApiErrorMessage } from '../../utils/errorMessage'

type RuntimeRow = Record<string, unknown>

const { t } = useI18n() // FIXED: 国际化

const props = defineProps<{
  pluginId: string
}>()
const emit = defineEmits<{
  (e: 'focus-config-field', fieldKey: string): void
  (e: 'retry-alert-test', channel: 'sms_alert' | 'wecom_alert' | 'feishu_alert'): void
}>()

const pluginId = computed(() => props.pluginId)

const getAlertEventTroubleshooting = (
  currentPluginId: 'feishu_alert' | 'wecom_alert' | 'sms_alert',
  row: { err?: string }
): any => {
  return (getNotificationTroubleshootingByPluginId as any)(currentPluginId, row?.err)
}

const isStreamHealthPlugin = computed(() => pluginId.value === 'stream_health')
const isSipLoggerPlugin = computed(() => pluginId.value === 'sip_logger')
const isNetworkWatchdogPlugin = computed(() => pluginId.value === 'network_watchdog')
const isStreamIdlePlugin = computed(() => pluginId.value === 'stream_idle')
const isTimelapsePlugin = computed(() => pluginId.value === 'timelapse')
const isWebhookPusherPlugin = computed(() => pluginId.value === 'webhook_pusher')
const isS3SyncPlugin = computed(() => pluginId.value === 's3_sync')
const isPtzTourPlugin = computed(() => pluginId.value === 'ptz_tour')
const isAutoRecordPlugin = computed(() => pluginId.value === 'auto_record')
const isRecordScheduleExecutorPlugin = computed(() => pluginId.value === 'record_schedule_executor')
const isRecordIndexVerifierPlugin = computed(() => pluginId.value === 'record_index_verifier')
const isSnapshotRefreshPlugin = computed(() => pluginId.value === 'snapshot_refresh')
const isRtmpPushChannelMonitorPlugin = computed(() => pluginId.value === 'rtmp_push_channel_monitor')
const isPullProxyMonitorPlugin = computed(() => pluginId.value === 'pull_proxy_monitor')
const isMqttBridgePlugin = computed(() => pluginId.value === 'mqtt_bridge')
const isFeishuAlertPlugin = computed(() => pluginId.value === 'feishu_alert')
const isWecomAlertPlugin = computed(() => pluginId.value === 'wecom_alert')
const isSmsAlertPlugin = computed(() => pluginId.value === 'sms_alert')

// stream_health runtime special UI
const streamHealthLoading = ref(false)
const streamHealthError = ref('')
const streamHealthRows = ref<RuntimeRow[]>([])
const streamHealthPage = ref(1)
const streamHealthPageSize = ref(10)
const streamHealthAppFilter = ref('')
const streamHealthStreamFilter = ref('')
const streamHealthOnlyLowBitrate = ref(true)
let streamHealthAutoTimer: ReturnType<typeof setInterval> | null = null

const paginatedStreamHealthRows = computed(() => {
  const start = (streamHealthPage.value - 1) * streamHealthPageSize.value
  const end = start + streamHealthPageSize.value
  return streamHealthRows.value.slice(start, end)
})

watch(() => streamHealthRows.value, () => {
  streamHealthPage.value = 1
})

const fetchStreamHealth = async () => {
  streamHealthLoading.value = true
  streamHealthError.value = ''
  try {
    const params: Record<string, unknown> = {}
    if (streamHealthAppFilter.value) params.app = streamHealthAppFilter.value
    if (streamHealthStreamFilter.value) params.stream = streamHealthStreamFilter.value
    params.only_low_bitrate = !!streamHealthOnlyLowBitrate.value

    const resp = await api.get('/api/v1/plugins/runtime/stream_health/health', { params })
    const data = resp?.data || {}
    streamHealthRows.value = Array.isArray(data.rows) ? data.rows : []
  } catch (e: unknown) {
    streamHealthError.value = getApiErrorMessage(e, t('plugin.panels.fetchHealthFailed')) // FIXED: 国际化
    streamHealthRows.value = []
  } finally {
    streamHealthLoading.value = false
  }
}

// sip_logger runtime special UI
const sipLogLoading = ref(false)
const sipLogError = ref('')
const sipLogRows = ref<RuntimeRow[]>([])
const sipLogKeyword = ref('')
const sipLogDirection = ref('')
const sipLogProto = ref('')
const sipLogPage = ref(1)
const sipLogPageSize = ref(50)
const sipLogHasMore = ref(false)
const sipTimeRange = ref<[string, string] | null>(null)

const pad2 = (n: number) => String(n).padStart(2, '0')
const formatDateTimeLocal = (d: Date) => {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

const fetchSipLoggerLogs = async () => {
  sipLogLoading.value = true
  sipLogError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: sipLogPage.value,
      page_size: sipLogPageSize.value,
    }
    if (sipTimeRange.value?.[0]) params.start_at = sipTimeRange.value[0]
    if (sipTimeRange.value?.[1]) params.end_at = sipTimeRange.value[1]
    if (sipLogKeyword.value) params.keyword = sipLogKeyword.value
    if (sipLogDirection.value) params.direction = sipLogDirection.value
    if (sipLogProto.value) params.proto = sipLogProto.value

    const resp = await api.get('/api/v1/plugins/runtime/sip_logger/logs', { params })
    const data = resp?.data || {}
    sipLogRows.value = Array.isArray(data.rows) ? data.rows : []
    sipLogHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    sipLogError.value = getApiErrorMessage(e, t('plugin.panels.fetchSipLogFailed')) // FIXED: 国际化
    sipLogRows.value = []
    sipLogHasMore.value = false
  } finally {
    sipLogLoading.value = false
  }
}

// network_watchdog runtime special UI
const nwLoading = ref(false)
const nwError = ref('')
const nwRows = ref<RuntimeRow[]>([])
const nwKeyword = ref('')
const nwDevice = ref('')
const nwIp = ref('')
const nwPage = ref(1)
const nwPageSize = ref(50)
const nwHasMore = ref(false)
const nwTimeRange = ref<[string, string] | null>(null)

const fetchNetworkWatchdogEvents = async () => {
  nwLoading.value = true
  nwError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: nwPage.value,
      page_size: nwPageSize.value,
    }
    if (nwTimeRange.value?.[0]) params.start_at = nwTimeRange.value[0]
    if (nwTimeRange.value?.[1]) params.end_at = nwTimeRange.value[1]
    if (nwKeyword.value) params.keyword = nwKeyword.value
    if (nwDevice.value) params.device = nwDevice.value
    if (nwIp.value) params.ip = nwIp.value

    const resp = await api.get('/api/v1/plugins/runtime/network_watchdog/events', { params })
    const data = resp?.data || {}
    nwRows.value = Array.isArray(data.rows) ? data.rows : []
    nwHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    nwError.value = getApiErrorMessage(e, t('plugin.panels.fetchNetworkAlarmFailed')) // FIXED: 国际化
    nwRows.value = []
    nwHasMore.value = false
  } finally {
    nwLoading.value = false
  }
}

// stream_idle：断流事件查询
const siLoading = ref(false)
const siError = ref('')
const siRows = ref<RuntimeRow[]>([])
const siKeyword = ref('')
const siApp = ref('')
const siStream = ref('')
const siNode = ref('')
const siPage = ref(1)
const siPageSize = ref(50)
const siHasMore = ref(false)
const siTimeRange = ref<[string, string] | null>(null)

const fetchStreamIdleEvents = async () => {
  siLoading.value = true
  siError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: siPage.value,
      page_size: siPageSize.value,
    }
    if (siTimeRange.value?.[0]) params.start_at = siTimeRange.value[0]
    if (siTimeRange.value?.[1]) params.end_at = siTimeRange.value[1]
    if (siKeyword.value) params.keyword = siKeyword.value
    if (siApp.value) params.app = siApp.value
    if (siStream.value) params.stream = siStream.value
    if (siNode.value) params.node = siNode.value

    const resp = await api.get('/api/v1/plugins/runtime/stream_idle/events', { params })
    const data = resp?.data || {}
    siRows.value = Array.isArray(data.rows) ? data.rows : []
    siHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    siError.value = getApiErrorMessage(e, t('plugin.panels.fetchStreamBreakFailed')) // FIXED: 国际化
    siRows.value = []
    siHasMore.value = false
  } finally {
    siLoading.value = false
  }
}

// timelapse：截图事件查询
const tlLoading = ref(false)
const tlError = ref('')
const tlRows = ref<RuntimeRow[]>([])
const tlKeyword = ref('')
const tlApp = ref('')
const tlStream = ref('')
const tlPage = ref(1)
const tlPageSize = ref(50)
const tlHasMore = ref(false)
const tlTimeRange = ref<[string, string] | null>(null)

const fetchTimelapseEvents = async () => {
  tlLoading.value = true
  tlError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: tlPage.value,
      page_size: tlPageSize.value,
    }
    if (tlTimeRange.value?.[0]) params.start_at = tlTimeRange.value[0]
    if (tlTimeRange.value?.[1]) params.end_at = tlTimeRange.value[1]
    if (tlKeyword.value) params.keyword = tlKeyword.value
    if (tlApp.value) params.app = tlApp.value
    if (tlStream.value) params.stream = tlStream.value

    const resp = await api.get('/api/v1/plugins/runtime/timelapse/events', { params })
    const data = resp?.data || {}
    tlRows.value = Array.isArray(data.rows) ? data.rows : []
    tlHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    tlError.value = getApiErrorMessage(e, t('plugin.panels.fetchScreenshotFailed')) // FIXED: 国际化
    tlRows.value = []
    tlHasMore.value = false
  } finally {
    tlLoading.value = false
  }
}

// webhook_pusher：推送事件查询
const wpLoading = ref(false)
const wpError = ref('')
const wpRows = ref<RuntimeRow[]>([])
const wpKeyword = ref('')
const wpDevice = ref('')
const wpStatus = ref<string | null>(null)
const wpOkMode = ref<'all' | 'true' | 'false'>('all')
const wpPage = ref(1)
const wpPageSize = ref(50)
const wpHasMore = ref(false)
const wpTimeRange = ref<[string, string] | null>(null)

const fetchWebhookPusherEvents = async () => {
  wpLoading.value = true
  wpError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: wpPage.value,
      page_size: wpPageSize.value,
    }
    if (wpTimeRange.value?.[0]) params.start_at = wpTimeRange.value[0]
    if (wpTimeRange.value?.[1]) params.end_at = wpTimeRange.value[1]
    if (wpKeyword.value) params.keyword = wpKeyword.value
    if (wpDevice.value) params.device = wpDevice.value
    if (wpStatus.value) params.status = wpStatus.value
    if (wpOkMode.value === 'true') params.ok = true
    if (wpOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/webhook_pusher/events', { params })
    const data = resp?.data || {}
    wpRows.value = Array.isArray(data.rows) ? data.rows : []
    wpHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    wpError.value = getApiErrorMessage(e, t('plugin.panels.fetchWebhookFailed')) // FIXED: 国际化
    wpRows.value = []
    wpHasMore.value = false
  } finally {
    wpLoading.value = false
  }
}

// s3_sync：上传事件查询
const s3Loading = ref(false)
const s3Error = ref('')
const s3Rows = ref<RuntimeRow[]>([])
const s3Keyword = ref('')
const s3Bucket = ref('')
const s3OkMode = ref<'all' | 'true' | 'false'>('all')
const s3Page = ref(1)
const s3PageSize = ref(50)
const s3HasMore = ref(false)
const s3TimeRange = ref<[string, string] | null>(null)

const fetchS3SyncEvents = async () => {
  s3Loading.value = true
  s3Error.value = ''
  try {
    const params: Record<string, unknown> = {
      page: s3Page.value,
      page_size: s3PageSize.value,
    }
    if (s3TimeRange.value?.[0]) params.start_at = s3TimeRange.value[0]
    if (s3TimeRange.value?.[1]) params.end_at = s3TimeRange.value[1]
    if (s3Keyword.value) params.keyword = s3Keyword.value
    if (s3Bucket.value) params.bucket = s3Bucket.value
    if (s3OkMode.value === 'true') params.ok = true
    if (s3OkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/s3_sync/events', { params })
    const data = resp?.data || {}
    s3Rows.value = Array.isArray(data.rows) ? data.rows : []
    s3HasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    s3Error.value = getApiErrorMessage(e, t('plugin.panels.fetchS3SyncFailed')) // FIXED: 国际化
    s3Rows.value = []
    s3HasMore.value = false
  } finally {
    s3Loading.value = false
  }
}

// ptz_tour：预置位下发事件
const ptzLoading = ref(false)
const ptzError = ref('')
const ptzRows = ref<RuntimeRow[]>([])
const ptzKeyword = ref('')
const ptzDevice = ref('')
const ptzChannel = ref('')
const ptzOkMode = ref<'all' | 'true' | 'false'>('all')
const ptzPage = ref(1)
const ptzPageSize = ref(50)
const ptzHasMore = ref(false)
const ptzTimeRange = ref<[string, string] | null>(null)

const fetchPtzTourEvents = async () => {
  ptzLoading.value = true
  ptzError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: ptzPage.value,
      page_size: ptzPageSize.value,
    }
    if (ptzTimeRange.value?.[0]) params.start_at = ptzTimeRange.value[0]
    if (ptzTimeRange.value?.[1]) params.end_at = ptzTimeRange.value[1]
    if (ptzKeyword.value) params.keyword = ptzKeyword.value
    if (ptzDevice.value) params.device = ptzDevice.value
    if (ptzChannel.value) params.channel = ptzChannel.value
    if (ptzOkMode.value === 'true') params.ok = true
    if (ptzOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/ptz_tour/events', { params })
    const data = resp?.data || {}
    ptzRows.value = Array.isArray(data.rows) ? data.rows : []
    ptzHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    ptzError.value = getApiErrorMessage(e, t('plugin.panels.fetchPtzPatrolFailed')) // FIXED: 国际化
    ptzRows.value = []
    ptzHasMore.value = false
  } finally {
    ptzLoading.value = false
  }
}

// auto_record：录像启停事件
const arLoading = ref(false)
const arError = ref('')
const arRows = ref<RuntimeRow[]>([])
const arKeyword = ref('')
const arStream = ref('')
const arOp = ref<string | null>(null)
const arOkMode = ref<'all' | 'true' | 'false'>('all')
const arPage = ref(1)
const arPageSize = ref(50)
const arHasMore = ref(false)
const arTimeRange = ref<[string, string] | null>(null)

const fetchAutoRecordEvents = async () => {
  arLoading.value = true
  arError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: arPage.value,
      page_size: arPageSize.value,
    }
    if (arTimeRange.value?.[0]) params.start_at = arTimeRange.value[0]
    if (arTimeRange.value?.[1]) params.end_at = arTimeRange.value[1]
    if (arKeyword.value) params.keyword = arKeyword.value
    if (arStream.value) params.stream = arStream.value
    if (arOp.value) params.op = arOp.value
    if (arOkMode.value === 'true') params.ok = true
    if (arOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/auto_record/events', { params })
    const data = resp?.data || {}
    arRows.value = Array.isArray(data.rows) ? data.rows : []
    arHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    arError.value = getApiErrorMessage(e, t('plugin.panels.fetchAutoRecordFailed')) // FIXED: 国际化
    arRows.value = []
    arHasMore.value = false
  } finally {
    arLoading.value = false
  }
}

const rseLoading = ref(false)
const rseError = ref('')
const rseRows = ref<RuntimeRow[]>([])
const rseKeyword = ref('')
const rseSchedule = ref('')
const rseStream = ref('')
const rseEvt = ref<string | null>(null)
const rsePage = ref(1)
const rsePageSize = ref(50)
const rseHasMore = ref(false)
const rseTimeRange = ref<[string, string] | null>(null)

const fetchRecordScheduleExecutorEvents = async () => {
  rseLoading.value = true
  rseError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: rsePage.value,
      page_size: rsePageSize.value,
    }
    if (rseTimeRange.value?.[0]) params.start_at = rseTimeRange.value[0]
    if (rseTimeRange.value?.[1]) params.end_at = rseTimeRange.value[1]
    if (rseKeyword.value) params.keyword = rseKeyword.value
    if (rseSchedule.value) params.schedule = rseSchedule.value
    if (rseStream.value) params.stream = rseStream.value
    if (rseEvt.value) params.evt = rseEvt.value

    const resp = await api.get('/api/v1/plugins/runtime/record_schedule_executor/events', { params })
    const data = resp?.data || {}
    rseRows.value = Array.isArray(data.rows) ? data.rows : []
    rseHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    rseError.value = getApiErrorMessage(e, t('plugin.panels.fetchRecordPlanFailed')) // FIXED: 国际化
    rseRows.value = []
    rseHasMore.value = false
  } finally {
    rseLoading.value = false
  }
}

const rivLoading = ref(false)
const rivError = ref('')
const rivRows = ref<RuntimeRow[]>([])
const rivKeyword = ref('')
const rivRecordId = ref('')
const rivOkMode = ref<'all' | 'true' | 'false'>('all')
const rivNote = ref<string | null>(null)
const rivPage = ref(1)
const rivPageSize = ref(50)
const rivHasMore = ref(false)
const rivTimeRange = ref<[string, string] | null>(null)

const fetchRecordIndexVerifierEvents = async () => {
  rivLoading.value = true
  rivError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: rivPage.value,
      page_size: rivPageSize.value,
    }
    if (rivTimeRange.value?.[0]) params.start_at = rivTimeRange.value[0]
    if (rivTimeRange.value?.[1]) params.end_at = rivTimeRange.value[1]
    if (rivKeyword.value) params.keyword = rivKeyword.value
    if (rivRecordId.value) params.record_id = rivRecordId.value
    if (rivOkMode.value === 'true') params.ok = true
    if (rivOkMode.value === 'false') params.ok = false
    if (rivNote.value) params.note = rivNote.value

    const resp = await api.get('/api/v1/plugins/runtime/record_index_verifier/events', { params })
    const data = resp?.data || {}
    rivRows.value = Array.isArray(data.rows) ? data.rows : []
    rivHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    rivError.value = getApiErrorMessage(e, t('plugin.panels.fetchRecordVerifyFailed')) // FIXED: 国际化
    rivRows.value = []
    rivHasMore.value = false
  } finally {
    rivLoading.value = false
  }
}

const snapLoading = ref(false)
const snapError = ref('')
const snapRows = ref<RuntimeRow[]>([])
const snapKeyword = ref('')
const snapAsset = ref('')
const snapChannel = ref('')
const snapOkMode = ref<'all' | 'true' | 'false'>('all')
const snapPage = ref(1)
const snapPageSize = ref(50)
const snapHasMore = ref(false)
const snapTimeRange = ref<[string, string] | null>(null)

const fetchSnapshotRefreshEvents = async () => {
  snapLoading.value = true
  snapError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: snapPage.value,
      page_size: snapPageSize.value,
    }
    if (snapTimeRange.value?.[0]) params.start_at = snapTimeRange.value[0]
    if (snapTimeRange.value?.[1]) params.end_at = snapTimeRange.value[1]
    if (snapKeyword.value) params.keyword = snapKeyword.value
    if (snapAsset.value) params.asset = snapAsset.value
    if (snapChannel.value) params.channel = snapChannel.value
    if (snapOkMode.value === 'true') params.ok = true
    if (snapOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/snapshot_refresh/events', { params })
    const data = resp?.data || {}
    snapRows.value = Array.isArray(data.rows) ? data.rows : []
    snapHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    snapError.value = getApiErrorMessage(e, t('plugin.panels.fetchSnapshotRefreshFailed')) // FIXED: 国际化
    snapRows.value = []
    snapHasMore.value = false
  } finally {
    snapLoading.value = false
  }
}

const rtmpLoading = ref(false)
const rtmpError = ref('')
const rtmpRows = ref<RuntimeRow[]>([])
const rtmpKeyword = ref('')
const rtmpStream = ref('')
const rtmpSourceId = ref('')
const rtmpEvt = ref<string | null>(null)
const rtmpPage = ref(1)
const rtmpPageSize = ref(50)
const rtmpHasMore = ref(false)
const rtmpTimeRange = ref<[string, string] | null>(null)

const fetchRtmpPushMonitorEvents = async () => {
  rtmpLoading.value = true
  rtmpError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: rtmpPage.value,
      page_size: rtmpPageSize.value,
    }
    if (rtmpTimeRange.value?.[0]) params.start_at = rtmpTimeRange.value[0]
    if (rtmpTimeRange.value?.[1]) params.end_at = rtmpTimeRange.value[1]
    if (rtmpKeyword.value) params.keyword = rtmpKeyword.value
    if (rtmpStream.value) params.stream = rtmpStream.value
    if (rtmpSourceId.value) params.source_id = rtmpSourceId.value
    if (rtmpEvt.value) params.evt = rtmpEvt.value

    const resp = await api.get('/api/v1/plugins/runtime/rtmp_push_channel_monitor/events', { params })
    const data = resp?.data || {}
    rtmpRows.value = Array.isArray(data.rows) ? data.rows : []
    rtmpHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    rtmpError.value = getApiErrorMessage(e, t('plugin.panels.fetchRtmpMonitorFailed')) // FIXED: 国际化
    rtmpRows.value = []
    rtmpHasMore.value = false
  } finally {
    rtmpLoading.value = false
  }
}

const ppmLoading = ref(false)
const ppmError = ref('')
const ppmRows = ref<RuntimeRow[]>([])
const ppmKeyword = ref('')
const ppmStream = ref('')
const ppmEvt = ref<string | null>(null)
const ppmOkMode = ref<'all' | 'true' | 'false'>('all')
const ppmPage = ref(1)
const ppmPageSize = ref(50)
const ppmHasMore = ref(false)
const ppmTimeRange = ref<[string, string] | null>(null)

const fetchPullProxyMonitorEvents = async () => {
  ppmLoading.value = true
  ppmError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: ppmPage.value,
      page_size: ppmPageSize.value,
    }
    if (ppmTimeRange.value?.[0]) params.start_at = ppmTimeRange.value[0]
    if (ppmTimeRange.value?.[1]) params.end_at = ppmTimeRange.value[1]
    if (ppmKeyword.value) params.keyword = ppmKeyword.value
    if (ppmStream.value) params.stream = ppmStream.value
    if (ppmEvt.value) params.evt = ppmEvt.value
    if (ppmOkMode.value === 'true') params.ok = true
    if (ppmOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/pull_proxy_monitor/events', { params })
    const data = resp?.data || {}
    ppmRows.value = Array.isArray(data.rows) ? data.rows : []
    ppmHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    ppmError.value = getApiErrorMessage(e, t('plugin.panels.fetchPullProxyMonitorFailed')) // FIXED: 国际化
    ppmRows.value = []
    ppmHasMore.value = false
  } finally {
    ppmLoading.value = false
  }
}

const mqttLoading = ref(false)
const mqttError = ref('')
const mqttRows = ref<RuntimeRow[]>([])
const mqttKeyword = ref('')
const mqttDevice = ref('')
const mqttKind = ref<string | null>(null)
const mqttAlarmType = ref('')
const mqttOkMode = ref<'all' | 'true' | 'false'>('all')
const mqttPage = ref(1)
const mqttPageSize = ref(50)
const mqttHasMore = ref(false)
const mqttTimeRange = ref<[string, string] | null>(null)

const fetchMqttBridgeEvents = async () => {
  mqttLoading.value = true
  mqttError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: mqttPage.value,
      page_size: mqttPageSize.value,
    }
    if (mqttTimeRange.value?.[0]) params.start_at = mqttTimeRange.value[0]
    if (mqttTimeRange.value?.[1]) params.end_at = mqttTimeRange.value[1]
    if (mqttKeyword.value) params.keyword = mqttKeyword.value
    if (mqttDevice.value) params.device = mqttDevice.value
    if (mqttKind.value) params.kind = mqttKind.value
    if (mqttAlarmType.value) params.alarm_type = mqttAlarmType.value
    if (mqttOkMode.value === 'true') params.ok = true
    if (mqttOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/mqtt_bridge/events', { params })
    const data = resp?.data || {}
    mqttRows.value = Array.isArray(data.rows) ? data.rows : []
    mqttHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    mqttError.value = getApiErrorMessage(e, t('plugin.panels.fetchMqttBridgeFailed')) // FIXED: 国际化
    mqttRows.value = []
    mqttHasMore.value = false
  } finally {
    mqttLoading.value = false
  }
}

const feishuLoading = ref(false)
const feishuError = ref('')
const feishuRows = ref<RuntimeRow[]>([])
const feishuKeyword = ref('')
const feishuDevice = ref('')
const feishuAlarmType = ref('')
const feishuOkMode = ref<'all' | 'true' | 'false'>('all')
const feishuPage = ref(1)
const feishuPageSize = ref(50)
const feishuHasMore = ref(false)
const feishuTimeRange = ref<[string, string] | null>(null)

const fetchFeishuAlertEvents = async () => {
  feishuLoading.value = true
  feishuError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: feishuPage.value,
      page_size: feishuPageSize.value,
    }
    if (feishuTimeRange.value?.[0]) params.start_at = feishuTimeRange.value[0]
    if (feishuTimeRange.value?.[1]) params.end_at = feishuTimeRange.value[1]
    if (feishuKeyword.value) params.keyword = feishuKeyword.value
    if (feishuDevice.value) params.device = feishuDevice.value
    if (feishuAlarmType.value) params.alarm_type = feishuAlarmType.value
    if (feishuOkMode.value === 'true') params.ok = true
    if (feishuOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/feishu_alert/events', { params })
    const data = resp?.data || {}
    feishuRows.value = Array.isArray(data.rows) ? data.rows : []
    feishuHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    feishuError.value = getApiErrorMessage(e, t('plugin.panels.fetchFeishuAlarmFailed')) // FIXED: 国际化
    feishuRows.value = []
    feishuHasMore.value = false
  } finally {
    feishuLoading.value = false
  }
}

const wecomLoading = ref(false)
const wecomError = ref('')
const wecomRows = ref<RuntimeRow[]>([])
const wecomKeyword = ref('')
const wecomDevice = ref('')
const wecomAlarmType = ref('')
const wecomOkMode = ref<'all' | 'true' | 'false'>('all')
const wecomPage = ref(1)
const wecomPageSize = ref(50)
const wecomHasMore = ref(false)
const wecomTimeRange = ref<[string, string] | null>(null)

const fetchWecomAlertEvents = async () => {
  wecomLoading.value = true
  wecomError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: wecomPage.value,
      page_size: wecomPageSize.value,
    }
    if (wecomTimeRange.value?.[0]) params.start_at = wecomTimeRange.value[0]
    if (wecomTimeRange.value?.[1]) params.end_at = wecomTimeRange.value[1]
    if (wecomKeyword.value) params.keyword = wecomKeyword.value
    if (wecomDevice.value) params.device = wecomDevice.value
    if (wecomAlarmType.value) params.alarm_type = wecomAlarmType.value
    if (wecomOkMode.value === 'true') params.ok = true
    if (wecomOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/wecom_alert/events', { params })
    const data = resp?.data || {}
    wecomRows.value = Array.isArray(data.rows) ? data.rows : []
    wecomHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    wecomError.value = getApiErrorMessage(e, t('plugin.panels.fetchWecomAlarmFailed')) // FIXED: 国际化
    wecomRows.value = []
    wecomHasMore.value = false
  } finally {
    wecomLoading.value = false
  }
}

const smsLoading = ref(false)
const smsError = ref('')
const smsRows = ref<RuntimeRow[]>([])
const smsKeyword = ref('')
const smsDevice = ref('')
const smsAlarmType = ref('')
const smsOkMode = ref<'all' | 'true' | 'false'>('all')
const smsPage = ref(1)
const smsPageSize = ref(50)
const smsHasMore = ref(false)
const smsTimeRange = ref<[string, string] | null>(null)

const fetchSmsAlertEvents = async () => {
  smsLoading.value = true
  smsError.value = ''
  try {
    const params: Record<string, unknown> = {
      page: smsPage.value,
      page_size: smsPageSize.value,
    }
    if (smsTimeRange.value?.[0]) params.start_at = smsTimeRange.value[0]
    if (smsTimeRange.value?.[1]) params.end_at = smsTimeRange.value[1]
    if (smsKeyword.value) params.keyword = smsKeyword.value
    if (smsDevice.value) params.device = smsDevice.value
    if (smsAlarmType.value) params.alarm_type = smsAlarmType.value
    if (smsOkMode.value === 'true') params.ok = true
    if (smsOkMode.value === 'false') params.ok = false

    const resp = await api.get('/api/v1/plugins/runtime/sms_alert/events', { params })
    const data = resp?.data || {}
    smsRows.value = Array.isArray(data.rows) ? data.rows : []
    smsHasMore.value = Boolean(data?.meta?.has_more)
  } catch (e: unknown) {
    smsError.value = getApiErrorMessage(e, t('plugin.panels.fetchSmsAlarmFailed')) // FIXED: 国际化
    smsRows.value = []
    smsHasMore.value = false
  } finally {
    smsLoading.value = false
  }
}

// 兼容旧调用点：底部逻辑使用 fetch*Tasks / fetch*Logs 命名，但事件查询实现为 fetch*Events
const fetchTimelapseTasks = fetchTimelapseEvents
const fetchWebhookPusherLogs = fetchWebhookPusherEvents
const fetchS3SyncTasks = fetchS3SyncEvents
const fetchPtzTourTasks = fetchPtzTourEvents
const fetchAutoRecordTasks = fetchAutoRecordEvents
const fetchRecordScheduleExecutorTasks = fetchRecordScheduleExecutorEvents
const fetchRecordIndexVerifierTasks = fetchRecordIndexVerifierEvents
const fetchSnapshotRefreshTasks = fetchSnapshotRefreshEvents
const fetchRtmpPushChannelMonitorTasks = fetchRtmpPushMonitorEvents
const fetchPullProxyMonitorTasks = fetchPullProxyMonitorEvents
const fetchMqttBridgeTasks = fetchMqttBridgeEvents
const fetchFeishuAlertLogs = fetchFeishuAlertEvents
const fetchWecomAlertLogs = fetchWecomAlertEvents
const fetchSmsAlertLogs = fetchSmsAlertEvents

// 插件通用 runtime config 编辑器状态
type RuntimeField = { key: string; label?: string; type?: string; min?: number; max?: number }
const runtimeConfig = reactive<Record<string, unknown>>({})
const runtimeSchema = ref<{ fields?: RuntimeField[] }>({})
const runtimeFields = ref<RuntimeField[]>([])
const jsonText = reactive<Record<string, string>>({})
const showConfigForm = ref(false)
const runtimeMessage = ref('')
const loadingConfig = ref(false)
const savingConfig = ref(false)
const configError = ref('')
const iframeUrl = ref('')
const pluginDisplayName = ref('')
// 页面级 loading：onMounted / error 分支里会回填
const loading = ref(true)

const clearRuntimeConfig = () => {
  for (const k of Object.keys(runtimeConfig)) delete runtimeConfig[k]
}

const loadRuntimeConfig = async () => {
  loadingConfig.value = true
  configError.value = ''
  try {
    const resp = await api.get(`/api/v1/plugins/runtime/${pluginId.value}/config`)
    const data = resp?.data || {}
    runtimeSchema.value = data.schema || {}
    runtimeFields.value = Array.isArray(runtimeSchema.value?.fields) ? runtimeSchema.value.fields : []
    clearRuntimeConfig()

    const cfg = data.config && typeof data.config === 'object' ? data.config : {}
    for (const [k, v] of Object.entries(cfg)) {
      runtimeConfig[k] = v
    }

    // json 字段单独用文本编辑，保存时再 parse
    for (const f of runtimeFields.value) {
      const t = String(f.type || '').toLowerCase()
      const key = String(f.key)
      if (t === 'json') {
        const v = runtimeConfig[key]
        if (typeof v === 'string') jsonText[key] = v
        else jsonText[key] = JSON.stringify(v ?? {}, null, 2)
      }
      if (t === 'bool' && typeof runtimeConfig[key] !== 'boolean') {
        runtimeConfig[key] = Boolean(runtimeConfig[key])
      }
    }

    // 是否展示配置表单：只要 schema.fields 存在即可
    showConfigForm.value = runtimeFields.value.length > 0
    runtimeMessage.value = showConfigForm.value
      ? t('plugin.panels.pluginConfigurable', { name: pluginDisplayName.value || pluginId.value }) // FIXED: 国际化
      : t('plugin.panels.pluginNoSchema', { name: pluginDisplayName.value || pluginId.value }) // FIXED: 国际化
  } catch (e: unknown) {
    configError.value = getApiErrorMessage(e, t('plugin.panels.loadPluginConfigFailed')) // FIXED: 国际化
    showConfigForm.value = false
  } finally {
    loadingConfig.value = false
  }
}

const saveRuntimeConfig = async () => {
  if (!runtimeFields.value.length) return
  savingConfig.value = true
  configError.value = ''
  try {
    const configToSend: Record<string, unknown> = {}
    for (const f of runtimeFields.value) {
      const key = String(f.key)
      // FIX: [2026-07-04] 局部变量 t 遮蔽 useI18n 的 t 函数，JSON 解析失败时 TypeError [全栈工程师]
      const fieldType = String(f.type || '').toLowerCase()
      if (fieldType === 'json') {
        const txt = String(jsonText[key] ?? '').trim()
        if (!txt) {
          configToSend[key] = {}
          continue
        }
        try {
          configToSend[key] = JSON.parse(txt)
        } catch {
          throw new Error(t('plugin.panels.jsonParseFailed', { key })) // FIXED: 国际化
        }
      } else {
        configToSend[key] = runtimeConfig[key]
      }
    }
    await api.put(`/api/v1/plugins/runtime/${pluginId.value}/config`, { config: configToSend })
    ElMessage.success(t('plugin.panels.configSaved')) // FIXED: 国际化
  } catch (e: unknown) {
    const msg = (e as { message?: unknown } | null)?.message
    configError.value = typeof msg === 'string' ? msg : t('plugin.panels.saveFailed') // FIXED: 国际化
    ElMessage.error(configError.value)
  } finally {
    savingConfig.value = false
  }
}

/** P0-6: iframe 无法带 Bearer，plugin-assets 改由 HttpOnly cookie 认证（login 已设置 access_token cookie）。
 * 不再将 token 拼入 URL 查询参数，消除 token 暴露到日志/Referer/history 的风险（硬约束 #1）。
 */
const withPluginAssetsAuthToken = (url: unknown) => {
  return String(url || '').trim()
}

onMounted(async () => {
  if (!pluginId.value) {
    runtimeMessage.value = t('plugin.panels.missingPluginId') // FIXED: 国际化
    loading.value = false
    return
  }
  try {
    const res = await api.get('/api/v1/plugins/menus')
    const menus = Array.isArray(res.data) ? res.data : []
    const entry = menus.find(
      (m: Record<string, unknown>) =>
        m.plugin_id === pluginId.value ||
        m.path === `/plugins/runtime/${pluginId.value}` ||
        (typeof m.path === 'string' && m.path.endsWith(`/plugins/runtime/${pluginId.value}`))
    )
    if (entry?.frontend_url) {
      iframeUrl.value = withPluginAssetsAuthToken(entry.frontend_url)
      pluginDisplayName.value = String(entry.title || pluginId.value)
      runtimeMessage.value = t('plugin.panels.pluginInstalled', { name: pluginDisplayName.value }) // FIXED: 国际化
    } else {
      // 无 frontend_url 代表该插件未提供 oss 运行入口（后端能力为主时常见）。
      iframeUrl.value = ''
      pluginDisplayName.value = String(entry?.title || pluginId.value)
      // 尝试拉取 config_schema 并展示“通用配置页”
      await loadRuntimeConfig()
    }

    // stream_health：即使也有通用配置表单，也附加健康快照列表
    if (pluginId.value === 'stream_health') {
      await fetchStreamHealth()
      // 低频刷新：避免频繁打 ZLM
      if (streamHealthAutoTimer) clearInterval(streamHealthAutoTimer)
      streamHealthAutoTimer = setInterval(() => {
        fetchStreamHealth()
      }, 30000)
    }

    // sip_logger：专用日志查询页（不做轮询，手动刷新/翻页）
    if (pluginId.value === 'sip_logger') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      sipTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      sipLogPage.value = 1
      await fetchSipLoggerLogs()
    }

    // network_watchdog：不可达事件查询页（含 iframe 嵌入页下方运维表）
    if (pluginId.value === 'network_watchdog') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      nwTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      nwPage.value = 1
      await fetchNetworkWatchdogEvents()
    }

    // stream_idle：断流事件查询页
    if (pluginId.value === 'stream_idle') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      siTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      siPage.value = 1
      await fetchStreamIdleEvents()
    }

    // timelapse：截图事件查询页
    if (pluginId.value === 'timelapse') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      tlTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      tlPage.value = 1
      await fetchTimelapseEvents()
    }

    // webhook_pusher：推送事件查询
    if (pluginId.value === 'webhook_pusher') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      wpTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      wpPage.value = 1
      await fetchWebhookPusherEvents()
    }

    // s3_sync：上传事件查询
    if (pluginId.value === 's3_sync') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      s3TimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      s3Page.value = 1
      await fetchS3SyncEvents()
    }

    if (pluginId.value === 'ptz_tour') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      ptzTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      ptzPage.value = 1
      await fetchPtzTourEvents()
    }

    if (pluginId.value === 'auto_record') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      arTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      arPage.value = 1
      await fetchAutoRecordEvents()
    }

    if (pluginId.value === 'record_schedule_executor') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      rseTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      rsePage.value = 1
      await fetchRecordScheduleExecutorEvents()
    }

    if (pluginId.value === 'record_index_verifier') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      rivTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      rivPage.value = 1
      await fetchRecordIndexVerifierEvents()
    }

    if (pluginId.value === 'snapshot_refresh') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      snapTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      snapPage.value = 1
      await fetchSnapshotRefreshEvents()
    }

    if (pluginId.value === 'rtmp_push_channel_monitor') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      rtmpTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      rtmpPage.value = 1
      await fetchRtmpPushMonitorEvents()
    }

    if (pluginId.value === 'pull_proxy_monitor') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      ppmTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      ppmPage.value = 1
      await fetchPullProxyMonitorEvents()
    }

    if (pluginId.value === 'mqtt_bridge') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      mqttTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      mqttPage.value = 1
      await fetchMqttBridgeEvents()
    }

    if (pluginId.value === 'feishu_alert') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      feishuTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      feishuPage.value = 1
      await fetchFeishuAlertEvents()
    }

    if (pluginId.value === 'wecom_alert') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      wecomTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      wecomPage.value = 1
      await fetchWecomAlertEvents()
    }

    if (pluginId.value === 'sms_alert') {
      const end = new Date()
      const start = new Date(end.getTime() - 24 * 3600 * 1000)
      smsTimeRange.value = [formatDateTimeLocal(start), formatDateTimeLocal(end)]
      smsPage.value = 1
      await fetchSmsAlertEvents()
    }
  } catch {
    iframeUrl.value = ''
    pluginDisplayName.value = pluginId.value
    runtimeMessage.value = t('plugin.panels.missingPluginId') // FIXED: 国际化
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (streamHealthAutoTimer) {
    clearInterval(streamHealthAutoTimer)
    streamHealthAutoTimer = null
  }
})


onMounted(() => {
  if (isStreamHealthPlugin.value) {
    fetchStreamHealth()
    if (streamHealthAutoTimer) clearInterval(streamHealthAutoTimer)
    streamHealthAutoTimer = setInterval(() => {
      fetchStreamHealth()
    }, 10000)
  }
  if (isSipLoggerPlugin.value) fetchSipLoggerLogs()
  if (isNetworkWatchdogPlugin.value) fetchNetworkWatchdogEvents()
  if (isStreamIdlePlugin.value) fetchStreamIdleEvents()
  if (isTimelapsePlugin.value) fetchTimelapseTasks()
  if (isWebhookPusherPlugin.value) fetchWebhookPusherLogs()
  if (isS3SyncPlugin.value) fetchS3SyncTasks()
  if (isPtzTourPlugin.value) fetchPtzTourTasks()
  if (isAutoRecordPlugin.value) fetchAutoRecordTasks()
  if (isRecordScheduleExecutorPlugin.value) fetchRecordScheduleExecutorTasks()
  if (isRecordIndexVerifierPlugin.value) fetchRecordIndexVerifierTasks()
  if (isSnapshotRefreshPlugin.value) fetchSnapshotRefreshTasks()
  if (isRtmpPushChannelMonitorPlugin.value) fetchRtmpPushChannelMonitorTasks()
  if (isPullProxyMonitorPlugin.value) fetchPullProxyMonitorTasks()
  if (isMqttBridgePlugin.value) fetchMqttBridgeTasks()
  if (isFeishuAlertPlugin.value) fetchFeishuAlertLogs()
  if (isWecomAlertPlugin.value) fetchWecomAlertLogs()
  if (isSmsAlertPlugin.value) fetchSmsAlertLogs()
})

onBeforeUnmount(() => {
  if (streamHealthAutoTimer) {
    clearInterval(streamHealthAutoTimer)
    streamHealthAutoTimer = null
  }
})

watch(() => props.pluginId, (newId) => {
  if (streamHealthAutoTimer) {
    clearInterval(streamHealthAutoTimer)
    streamHealthAutoTimer = null
  }
  if (newId === 'stream_health') {
    fetchStreamHealth()
    streamHealthAutoTimer = setInterval(() => {
      fetchStreamHealth()
    }, 10000)
  }
  if (newId === 'sip_logger') fetchSipLoggerLogs()
  if (newId === 'network_watchdog') fetchNetworkWatchdogEvents()
  if (newId === 'stream_idle') fetchStreamIdleEvents()
  if (newId === 'timelapse') fetchTimelapseTasks()
  if (newId === 'webhook_pusher') fetchWebhookPusherLogs()
  if (newId === 's3_sync') fetchS3SyncTasks()
  if (newId === 'ptz_tour') fetchPtzTourTasks()
  if (newId === 'auto_record') fetchAutoRecordTasks()
  if (newId === 'record_schedule_executor') fetchRecordScheduleExecutorTasks()
  if (newId === 'record_index_verifier') fetchRecordIndexVerifierTasks()
  if (newId === 'snapshot_refresh') fetchSnapshotRefreshTasks()
  if (newId === 'rtmp_push_channel_monitor') fetchRtmpPushChannelMonitorTasks()
  if (newId === 'pull_proxy_monitor') fetchPullProxyMonitorTasks()
  if (newId === 'mqtt_bridge') fetchMqttBridgeTasks()
  if (newId === 'feishu_alert') fetchFeishuAlertLogs()
  if (newId === 'wecom_alert') fetchWecomAlertLogs()
  if (newId === 'sms_alert') fetchSmsAlertLogs()
})
</script>
