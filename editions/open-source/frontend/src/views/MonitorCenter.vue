<template>
  <div class="app-page h-full flex flex-col">
    <PageContainer flex class="flex-1 min-h-0">
      <template #header>
        <PageHeader title="监控中心" description="支持双击或拖拽通道上屏，并可进行云台控制与语音对讲。">
          <template #actions>
            <div class="flex gap-2">
              <el-button size="small" @click="showSidebar = !showSidebar" plain>
                <el-icon class="mr-1"><Fold v-if="showSidebar" /><Expand v-else /></el-icon>
                {{ showSidebar ? '隐藏设备树' : '显示设备树' }}
              </el-button>
              <el-radio-group v-model="layout" size="small">
                <el-radio-button value="1">单画面</el-radio-button>
                <el-radio-button value="4">2×2</el-radio-button>
                <el-radio-button value="9">3×3</el-radio-button>
                <el-radio-button value="16">4×4</el-radio-button>
                <el-radio-button value="1+3">1+3</el-radio-button>
                <el-radio-button value="1+5">1+5</el-radio-button>
                <el-radio-button value="1+7">1+7</el-radio-button>
              </el-radio-group>
              <el-button v-if="hasPlayingScreens" type="danger" size="small" @click="stopAll">停止全部画面</el-button>
            </div>
          </template>
        </PageHeader>
      </template>
      
      <div class="flex-1 flex gap-3 overflow-hidden mt-3">
      <!-- Device Tree Sidebar (Fixed Left) -->
      <div
        class="flex-shrink-0 flex flex-col bg-white rounded border overflow-hidden transition-all duration-300"
        :class="showSidebar ? 'w-72 opacity-100' : 'w-0 opacity-0 border-none'"
        style="border-color: var(--el-border-color-lighter);"
      >
        <div class="p-4 border-b" style="border-color: var(--el-border-color-lighter); background: var(--el-fill-color-extra-light);">
          <div class="flex items-center justify-between mb-3">
            <div class="font-bold text-slate-800 flex items-center gap-2">
              <el-icon class="text-sky-500"><VideoCamera /></el-icon>
              设备目录
            </div>
            <el-button link type="primary" size="small" @click="fetchTree">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
          <el-radio-group v-model="treeMode" size="small" @change="fetchTree" class="mb-3">
            <el-radio-button value="business">业务分组</el-radio-button>
            <el-radio-button value="region">行政区划</el-radio-button>
          </el-radio-group>
          <el-input v-model="filterText" placeholder="搜索设备/通道..." size="small" clearable class="search-input" />
        </div>
        <div class="flex-1 overflow-auto p-3 min-h-0" style="background: var(--el-fill-color-extra-light);">
          <div v-if="loadingTree" class="flex justify-center py-12" style="color: var(--el-text-color-secondary)">
            <el-icon class="animate-spin text-2xl text-sky-500"><Loading /></el-icon>
          </div>
          <div v-else-if="!treeData.length" class="py-12 text-center">
            <el-icon class="text-5xl text-slate-300 mb-3"><FolderOpened /></el-icon>
            <div class="text-sm text-slate-500">暂无设备或接入源</div>
            <div class="text-xs text-slate-400 mt-1">请先添加设备或多协议接入</div>
          </div>
          <SharedChannelTree
            v-else
            ref="treeRef"
            :data="treeData"
            :props-config="defaultProps"
            :default-expand-all="true"
            :filter-node-method="filterNode"
            @node-click="handleNodeClick"
            :draggable="true"
            @node-drag-start="handleDragStart"
            :tree-class="['device-tree', { 'tree-contrast': highContrastTree }]"
            :folder-predicate="isMonitorTreeFolderNode"
            folder-icon-class="text-amber-500"
            base-channel-icon-class="text-emerald-500"
            :show-status-badge="shouldShowStatusBadge"
            :show-node-stats="shouldShowNodeStats"
            :get-node-stats="getNodeStats"
            :get-node-stats-tone="getNodeStatsTone"
            :show-playing-tag="true"
            :is-channel-playing="isChannelPlaying"
            :highlight-current="true"
          />
        </div>
      </div>
      
      <!-- Monitor Grid -->
      <!-- 均分网格布局 -->
      <div
        v-if="!isRoamLayout"
        class="monitor-grid-wrapper flex-grow grid gap-2 p-3 rounded border"
        :style="[gridStyle, { borderColor: 'rgba(51, 65, 85, 0.5)' }]"
      >
        <div
          v-for="index in maxScreens"
          :key="'g-' + index"
          class="screen-cell relative flex items-center justify-center overflow-hidden group rounded border"
          :style="{ borderColor: activeScreen === index - 1 ? '#4d8dff' : '#3a4558' }"
          :class="{'ring-1 ring-blue-400/80': activeScreen === index - 1}"
          @click="activeScreen = index - 1"
          v-show="index <= layoutCount"
        >
          <div v-if="(screens[index-1]?.url || screens[index-1]?.hls) && !screens[index-1]?.error" class="w-full h-full relative" style="min-height: 100px;">
             <JessibucaPlayer 
               :ref="(el) => setPlayerRef(el, index-1)"
               :video-url="screens[index-1].url" 
               :hls-url="screens[index-1].hls" 
               :codec="screens[index-1].codec" 
               :has-audio="false"
               :auto-play="true"
               @refreshRequest="() => playInScreen({id: screens[index-1].channelId, deviceId: screens[index-1].deviceId, nodeType: screens[index-1].nodeType, label: screens[index-1].name}, index-1)"
             />
             <div class="absolute top-3 left-3 bg-gradient-to-r from-black/70 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
               <span class="font-semibold">{{ screens[index-1].name }}</span>
             </div>
             
             <!-- Floating Action Bar (Top Right) -->
             <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
               <el-button size="small" type="primary" circle @click.stop="takeScreenshot(index-1)" title="截图">
                 <el-icon><Camera /></el-icon>
               </el-button>
               <el-button size="small" type="danger" circle @click.stop="stopScreen(index-1)" title="关闭通道">
                 <el-icon><Close /></el-icon>
               </el-button>
             </div>
             
             <!-- Bottom Info Bar -->
             <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3 opacity-0 group-hover:opacity-100 transition-all duration-300 z-10">
               <div class="flex items-center justify-between text-xs text-white/80">
                 <span class="flex items-center gap-1">
                   <el-icon class="text-emerald-400"><CircleCheck /></el-icon>
                   正在播放
                 </span>
                 <div class="flex items-center gap-3">
                   <span>{{ new Date().toLocaleTimeString('zh-CN') }}</span>
                   <button @click.stop="stopScreen(index-1)" class="hover:text-red-400 transition-colors flex items-center justify-center" title="停止播放">
                     <el-icon class="text-base"><VideoPause /></el-icon>
                   </button>
                 </div>
               </div>
             </div>
          </div>
          <div v-else-if="screens[index-1]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
            <el-icon class="is-loading text-4xl text-sky-400 mb-3"><Loading /></el-icon>
            <div class="text-white/80 text-sm font-medium animate-pulse">正在向设备请求视频流...</div>
            <div class="text-white/50 text-xs mt-2">{{ screens[index-1].name }}</div>
          </div>
          <div v-else-if="screens[index-1]?.error" class="w-full h-full flex flex-col items-center justify-center bg-black/40 relative group">
            <el-icon class="text-4xl text-red-500 mb-3"><Warning /></el-icon>
            <div class="text-red-400 text-sm font-medium max-w-[80%] text-center truncate" :title="screens[index-1].errorMsg">{{ screens[index-1].errorMsg || '视频播放失败' }}</div>
            <div class="text-white/50 text-xs mt-2">{{ screens[index-1].name }}</div>
          </div>
          <div v-else class="empty-screen flex flex-col items-center justify-center">
            <div class="empty-number text-5xl font-bold mb-2">{{ index }}</div>
            <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
              <el-icon><Pointer /></el-icon>
              双击或拖拽通道播放
            </div>
          </div>
          
          <!-- Drop Overlay -->
          <div 
            v-if="isDragging"
            class="absolute inset-0 bg-gradient-to-br from-sky-500/20 to-blue-500/20 border-2 border-dashed border-sky-400 z-10 flex flex-col items-center justify-center rounded-xl"
            @dragover.prevent
            @drop="handleDrop($event, index-1)"
          >
            <el-icon class="text-4xl text-sky-400 mb-2 animate-bounce"><Download /></el-icon>
            <span class="text-white font-semibold text-lg">拖拽到此处开始播放</span>
          </div>
        </div>
      </div>
      <!-- 1+N布局 -->
      <div
        v-else
        class="monitor-grid-wrapper flex-grow p-3 rounded border overflow-hidden"
        :style="[roamGridStyle, { borderColor: 'rgba(51, 65, 85, 0.5)' }]"
      >
        <template v-if="layout === '1+3'">
          <div
            v-for="(cell, idx) in roamCells13"
            :key="'r13-' + idx"
            class="screen-cell relative flex items-center justify-center overflow-hidden group rounded border"
            :style="[{ borderColor: activeScreen === cell.index ? '#4d8dff' : '#3a4558' }, cell.style]"
            :class="{'ring-1 ring-blue-400/80': activeScreen === cell.index}"
            @click="activeScreen = cell.index"
          >
            <template v-if="(screens[cell.index]?.url || screens[cell.index]?.hls) && !screens[cell.index]?.error">
              <div class="w-full h-full relative" style="min-height: 100px;">
                <JessibucaPlayer
                  :ref="(el) => setPlayerRef(el, cell.index)"
                  :video-url="screens[cell.index].url"
                  :hls-url="screens[cell.index].hls"
                  :codec="screens[cell.index].codec"
                  :has-audio="false"
                  :auto-play="true"
                  @refreshRequest="() => playInScreen({id: screens[cell.index].channelId, deviceId: screens[cell.index].deviceId, nodeType: screens[cell.index].nodeType, label: screens[cell.index].name}, cell.index)"
                />
                <div class="absolute top-3 left-3 bg-gradient-to-r from-black/70 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                  <span class="font-semibold">{{ screens[cell.index].name }}</span>
                </div>
                
                <!-- Floating Action Bar (Top Right) -->
                <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                  <el-button size="small" type="primary" circle @click.stop="takeScreenshot(cell.index)" title="截图">
                    <el-icon><Camera /></el-icon>
                  </el-button>
                  <el-button size="small" type="danger" circle @click.stop="stopScreen(cell.index)" title="关闭通道">
                    <el-icon><Close /></el-icon>
                  </el-button>
                </div>
              </div>
            </template>
            <div v-else-if="screens[cell.index]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
              <el-icon class="is-loading text-4xl text-sky-400 mb-3"><Loading /></el-icon>
              <div class="text-white/80 text-sm font-medium animate-pulse">正在向设备请求视频流...</div>
              <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
            </div>
            <div v-else-if="screens[cell.index]?.error" class="w-full h-full flex flex-col items-center justify-center bg-black/40 relative group">
              <el-icon class="text-4xl text-red-500 mb-3"><Warning /></el-icon>
              <div class="text-red-400 text-sm font-medium max-w-[80%] text-center truncate" :title="screens[cell.index].errorMsg">{{ screens[cell.index].errorMsg || '视频播放失败' }}</div>
              <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
            </div>
            <div v-else class="empty-screen flex flex-col items-center justify-center">
              <div class="empty-number text-4xl font-bold mb-1">{{ cell.index + 1 }}</div>
              <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                <el-icon class="text-xs"><Pointer /></el-icon>
                双击或拖拽通道播放
              </div>
            </div>
            <div
              v-if="isDragging"
              class="absolute inset-0 bg-gradient-to-br from-sky-500/20 to-blue-500/20 border-2 border-dashed border-sky-400 z-10 flex flex-col items-center justify-center rounded-xl"
              @dragover.prevent
              @drop="handleDrop($event, cell.index)"
            >
              <el-icon class="text-3xl text-sky-400 mb-1 animate-bounce"><Download /></el-icon>
              <span class="text-white font-semibold">拖拽到此处开始播放</span>
            </div>
          </div>
        </template>
        <template v-else-if="layout === '1+5'">
          <div
            v-for="(cell, idx) in roamCells15"
            :key="'r15-' + idx"
            class="screen-cell relative flex items-center justify-center overflow-hidden group rounded border"
            :style="[{ borderColor: activeScreen === cell.index ? '#4d8dff' : '#3a4558' }, cell.style]"
            :class="{'ring-1 ring-blue-400/80': activeScreen === cell.index}"
            @click="activeScreen = cell.index"
          >
            <template v-if="(screens[cell.index]?.url || screens[cell.index]?.hls) && !screens[cell.index]?.error">
              <div class="w-full h-full relative" style="min-height: 100px;">
                <JessibucaPlayer
                  :ref="(el) => setPlayerRef(el, cell.index)"
                  :video-url="screens[cell.index].url"
                  :hls-url="screens[cell.index].hls"
                  :codec="screens[cell.index].codec"
                  :has-audio="false"
                  :auto-play="true"
                  @refreshRequest="() => playInScreen({id: screens[cell.index].channelId, deviceId: screens[cell.index].deviceId, nodeType: screens[cell.index].nodeType, label: screens[cell.index].name}, cell.index)"
                />
                <div class="absolute top-3 left-3 bg-gradient-to-r from-black/70 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                  <span class="font-semibold">{{ screens[cell.index].name }}</span>
                </div>
                
                <!-- Floating Action Bar (Top Right) -->
                <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                  <el-button size="small" type="primary" circle @click.stop="takeScreenshot(cell.index)" title="截图">
                    <el-icon><Camera /></el-icon>
                  </el-button>
                  <el-button size="small" type="danger" circle @click.stop="stopScreen(cell.index)" title="关闭通道">
                    <el-icon><Close /></el-icon>
                  </el-button>
                </div>
              </div>
            </template>
            <div v-else-if="screens[cell.index]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
              <el-icon class="is-loading text-4xl text-sky-400 mb-3"><Loading /></el-icon>
              <div class="text-white/80 text-sm font-medium animate-pulse">正在向设备请求视频流...</div>
              <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
            </div>
            <div v-else class="empty-screen flex flex-col items-center justify-center">
              <div class="empty-number text-4xl font-bold mb-1">{{ cell.index + 1 }}</div>
              <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                <el-icon class="text-xs"><Pointer /></el-icon>
                双击或拖拽通道播放
              </div>
            </div>
            <div
              v-if="isDragging"
              class="absolute inset-0 bg-gradient-to-br from-sky-500/20 to-blue-500/20 border-2 border-dashed border-sky-400 z-10 flex flex-col items-center justify-center rounded-xl"
              @dragover.prevent
              @drop="handleDrop($event, cell.index)"
            >
              <el-icon class="text-3xl text-sky-400 mb-1 animate-bounce"><Download /></el-icon>
              <span class="text-white font-semibold">拖拽到此处开始播放</span>
            </div>
          </div>
        </template>
        <template v-else-if="layout === '1+7'">
          <div
            v-for="(cell, idx) in roamCells17"
            :key="'r17-' + idx"
            class="screen-cell relative flex items-center justify-center overflow-hidden group rounded border"
            :style="[{ borderColor: activeScreen === cell.index ? '#4d8dff' : '#3a4558' }, cell.style]"
            :class="{'ring-1 ring-blue-400/80': activeScreen === cell.index}"
            @click="activeScreen = cell.index"
          >
            <template v-if="(screens[cell.index]?.url || screens[cell.index]?.hls) && !screens[cell.index]?.error">
              <div class="w-full h-full relative" style="min-height: 100px;">
                <JessibucaPlayer
                  :ref="(el) => setPlayerRef(el, cell.index)"
                  :video-url="screens[cell.index].url"
                  :hls-url="screens[cell.index].hls"
                  :codec="screens[cell.index].codec"
                  :has-audio="false"
                  :auto-play="true"
                  @refreshRequest="() => playInScreen({id: screens[cell.index].channelId, deviceId: screens[cell.index].deviceId, nodeType: screens[cell.index].nodeType, label: screens[cell.index].name}, cell.index)"
                />
                <div class="absolute top-3 left-3 bg-gradient-to-r from-black/70 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                  <span class="font-semibold">{{ screens[cell.index].name }}</span>
                </div>
                
                <!-- Floating Action Bar (Top Right) -->
                <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                  <el-button size="small" type="primary" circle @click.stop="takeScreenshot(cell.index)" title="截图">
                    <el-icon><Camera /></el-icon>
                  </el-button>
                  <el-button size="small" type="danger" circle @click.stop="stopScreen(cell.index)" title="关闭通道">
                    <el-icon><Close /></el-icon>
                  </el-button>
                </div>
              </div>
            </template>
            <div v-else-if="screens[cell.index]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
              <el-icon class="is-loading text-4xl text-sky-400 mb-3"><Loading /></el-icon>
              <div class="text-white/80 text-sm font-medium animate-pulse">正在向设备请求视频流...</div>
              <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
            </div>
            <div v-else class="empty-screen flex flex-col items-center justify-center">
              <div class="empty-number text-4xl font-bold mb-1">{{ cell.index + 1 }}</div>
              <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                <el-icon class="text-xs"><Pointer /></el-icon>
                双击或拖拽通道播放
              </div>
            </div>
            <div
              v-if="isDragging"
              class="absolute inset-0 bg-gradient-to-br from-sky-500/20 to-blue-500/20 border-2 border-dashed border-sky-400 z-10 flex flex-col items-center justify-center rounded-xl"
              @dragover.prevent
              @drop="handleDrop($event, cell.index)"
            >
              <el-icon class="text-3xl text-sky-400 mb-1 animate-bounce"><Download /></el-icon>
              <span class="text-white font-semibold">拖拽到此处开始播放</span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Device Control Panel (Floating Bottom Right) -->
    <teleport to="body">
    <div
      v-if="activeScreenData"
      ref="devicePanelRef"
      class="fixed shadow-xl rounded-xl overflow-hidden w-[420px] max-w-[42vw]"
      :style="devicePanelStyle"
    >
      <div
           class="px-3 py-2 text-sm font-semibold flex justify-between items-center cursor-move select-none border-b"
           @mousedown.stop.prevent="handlePanelMouseDown"
           style="background: var(--el-fill-color-light); color: var(--el-text-color-primary); border-color: var(--el-border-color-lighter);">
        <span>设备控制：{{ activeScreenData.name }}</span>
        <el-icon class="cursor-pointer hover:text-sky-500 transition-colors" @click="activeScreen = -1"><Close /></el-icon>
      </div>
      <div class="p-2 max-h-[calc(70vh-44px)] overflow-y-auto">
        <el-tabs>
          <el-tab-pane label="云台控制" name="ptz">
            <AdvancedPtzControl 
              :device-id="activeScreenData.deviceId" 
              :channel-id="activeScreenData.channelId" 
            />
          </el-tab-pane>
          <el-tab-pane label="语音对讲" name="talk">
            <TalkControl 
              :device-id="activeScreenData.deviceId" 
              :channel-id="activeScreenData.channelId" 
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
    </teleport>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { Close, VideoCamera, Folder, Loading, FolderOpened, CircleCheck, Download, Pointer, VideoPause, Fold, Expand, Camera } from '@element-plus/icons-vue'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import SharedChannelTree from '../components/channel/SharedChannelTree.vue'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import AdvancedPtzControl from '../components/AdvancedPtzControl.vue'
import TalkControl from '../components/TalkControl.vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { getFriendlyError, getApiErrorMessage } from '../utils/errorMessage'
import { useChannelTreeStats } from '../utils/channelTreeStats'
import { buildSourceTree } from '../utils/channelSourceTree'
import type { Device, Channel, TreeNode, Alarm, VideoRecord, PluginRuntimeRow, BillingPlan, Subscription, Order, License, CascadePlatform, StreamProxy, StreamPush, ScheduleItem, TvWallScreen, ConferenceSession, DiagResult, AuditLog, ApiKey, WorkOrder, AssetLedger, Maintenance, StructuredEvent, PluginConfig } from '@/types/models'
import { logger } from '@/utils/logger'

const treeMode = ref<'business' | 'region'>('business')

const isPlayableTreeChannel = (node: TreeNode) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  if (nodeType !== 'channel' && nodeType !== 'source_stream') return false
  if (Number(node?.status) !== 1) return false
  if (nodeType === 'source_stream') return true
  const gbId = String(node?.id || '')
  const typeCode = gbId ? gbId.substring(10, 13) : ''
  return ['131', '132', '111', '112', '118'].includes(typeCode)
}

const shouldShowStatusBadge = (node: TreeNode) => {
  const nodeType = String(node?.nodeType || '').toLowerCase()
  return ['channel', 'source_stream', 'device'].includes(nodeType)
}

const getNodeStatusTone = (node: TreeNode) => {
  return Number(node?.status) === 1 ? 'online' : 'offline'
}

const getNodeStatusText = (node: TreeNode) => {
  return Number(node?.status) === 1 ? '在线' : '离线'
}
const showSidebar = ref(true)
const layout = ref('1+5')
const activeScreen = ref(-1)
const maxScreens = 16
const screens = ref(new Array(maxScreens).fill(null))
const filterText = ref('')
// 兼容旧模板/缓存产物：保留 highContrastTree，避免运行时变量缺失
const highContrastTree = ref(localStorage.getItem('tree_status_high_contrast') === 'true')
type FilterableTreeRef = {
  filter?: (keyword: string) => void
}

const treeRef = ref<FilterableTreeRef | null>(null)
const treeData = ref<TreeNode[]>([])
const loadingTree = ref(false)
const {
  rebuildTreeNodeStats,
  shouldShowNodeStats,
  getNodeStats,
  getNodeStatsTone
} = useChannelTreeStats(treeData, {
  countableNodeTypes: ['channel', 'source_stream'],
  statsVisibleNodeTypes: ['root', 'directory', 'region', 'source_root', 'source_protocol'],
  isPlayableChannel: isPlayableTreeChannel
})
const isDragging = ref(false)
const devicePanelRef = ref<HTMLElement | null>(null)
const panelPos = ref({ x: 0, y: 0 })
const panelOffset = ref({ x: 0, y: 0 })
const panelDragged = ref(false)
let panelDragging = false
const PANEL_MARGIN = 16

const layoutCount = computed(() => {
  if (layout.value === '1+3') return 4
  if (layout.value === '1+5') return 6
  if (layout.value === '1+7') return 8
  const n = parseInt(layout.value, 10)
  return Number.isNaN(n) ? 4 : n
})

const isRoamLayout = computed(() => layout.value === '1+3' || layout.value === '1+5' || layout.value === '1+7')

const hasPlayingScreens = computed(() => {
  return screens.value.some(s => s?.url)
})

const isChannelPlaying = (channelId: string) => {
  return screens.value
    .slice(0, layoutCount.value)
    .some((s: Record<string, unknown>) => s && s.channelId === channelId && ((s.url || s.hls) || s.loading))
}

const isMonitorTreeFolderNode = (node: TreeNode) => {
  return Array.isArray(node?.children) && node.children.length > 0
}

const gridStyle = computed(() => {
  if (isRoamLayout.value) return {}
  const cols = Math.sqrt(layoutCount.value)
  return {
    gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
    gridTemplateRows: `repeat(${cols}, minmax(0, 1fr))`
  }
})

const roamGridStyle = computed(() => {
  if (layout.value === '1+3') {
    return {
      display: 'grid',
      gridTemplateColumns: '2fr 1fr',
      gridTemplateRows: '1fr 1fr 1fr',
      gridTemplateAreas: '"big s0" "big s1" "big s2"',
      gap: '4px',
      height: '100%'
    }
  }
  if (layout.value === '1+5') {
    return {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr 1fr',
      gridTemplateRows: '1fr 1fr 1fr',
      gap: '4px',
      height: '100%'
    }
  }
  if (layout.value === '1+7') {
    return {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr 1fr 1fr',
      gridTemplateRows: '1fr 1fr 1fr 1fr',
      gap: '4px',
      height: '100%'
    }
  }
  return { display: 'grid', gap: '4px', height: '100%' }
})

const roamCells13 = computed(() => [
  { index: 0, style: { gridArea: 'big' } },
  { index: 1, style: { gridArea: 's0' } },
  { index: 2, style: { gridArea: 's1' } },
  { index: 3, style: { gridArea: 's2' } }
])

const roamCells15 = computed(() => [
  { index: 0, style: { gridRow: '1 / 3', gridColumn: '1 / 3' } },
  { index: 1, style: { gridRow: '1 / 2', gridColumn: '3 / 4' } },
  { index: 2, style: { gridRow: '2 / 3', gridColumn: '3 / 4' } },
  { index: 3, style: { gridRow: '3 / 4', gridColumn: '1 / 2' } },
  { index: 4, style: { gridRow: '3 / 4', gridColumn: '2 / 3' } },
  { index: 5, style: { gridRow: '3 / 4', gridColumn: '3 / 4' } }
])

const roamCells17 = computed(() => [
  { index: 0, style: { gridRow: '1 / 4', gridColumn: '1 / 4' } },
  { index: 1, style: { gridRow: '1 / 2', gridColumn: '4 / 5' } },
  { index: 2, style: { gridRow: '2 / 3', gridColumn: '4 / 5' } },
  { index: 3, style: { gridRow: '3 / 4', gridColumn: '4 / 5' } },
  { index: 4, style: { gridRow: '4 / 5', gridColumn: '1 / 2' } },
  { index: 5, style: { gridRow: '4 / 5', gridColumn: '2 / 3' } },
  { index: 6, style: { gridRow: '4 / 5', gridColumn: '3 / 4' } },
  { index: 7, style: { gridRow: '4 / 5', gridColumn: '4 / 5' } }
])

const activeScreenData = computed(() => {
  if (activeScreen.value >= 0 && screens.value[activeScreen.value]) {
    return screens.value[activeScreen.value]
  }
  return null
})

const getPanelSize = () => {
  // Use fixed defaults if DOM element isn't fully rendered yet
  const width = devicePanelRef.value?.offsetWidth || 420
  // PtzControl content can be quite tall, default to a larger height to prevent clipping
  const height = devicePanelRef.value?.offsetHeight || 580
  return { width, height }
}

const clampPanelPos = (x: number, y: number) => {
  const { width, height } = getPanelSize()
  // Ensure the panel doesn't go off screen
  const maxX = Math.max(PANEL_MARGIN, window.innerWidth - width - PANEL_MARGIN)
  // Give some extra bottom margin for the taskbar/dock
  const maxY = Math.max(PANEL_MARGIN, window.innerHeight - height - PANEL_MARGIN - 20)
  return {
    x: Math.min(Math.max(x, PANEL_MARGIN), maxX),
    y: Math.min(Math.max(y, PANEL_MARGIN), maxY)
  }
}

const placePanelDefault = () => {
  const { width, height } = getPanelSize()
  // Place near bottom right by default, but above the main UI edge
  panelPos.value = clampPanelPos(window.innerWidth - width - 30, window.innerHeight - height - 40)
}

const devicePanelStyle = computed(() => ({
  zIndex: 9999,
  background: 'var(--el-bg-color)',
  border: '1px solid var(--el-border-color-lighter)',
  left: `${panelPos.value.x}px`,
  top: `${panelPos.value.y}px`
}))

const handlePanelMouseMove = (ev: MouseEvent) => {
  if (!panelDragging) return
  panelPos.value = clampPanelPos(ev.clientX - panelOffset.value.x, ev.clientY - panelOffset.value.y)
}

const handlePanelMouseUp = () => {
  panelDragging = false
  window.removeEventListener('mousemove', handlePanelMouseMove)
  window.removeEventListener('mouseup', handlePanelMouseUp)
}

const handlePanelMouseDown = (ev: MouseEvent) => {
  if (!devicePanelRef.value) return
  const rect = devicePanelRef.value.getBoundingClientRect()
  panelOffset.value = {
    x: ev.clientX - rect.left,
    y: ev.clientY - rect.top
  }
  panelDragging = true
  panelDragged.value = true
  window.addEventListener('mousemove', handlePanelMouseMove)
  window.addEventListener('mouseup', handlePanelMouseUp)
}

const handleWindowResize = () => {
  if (!activeScreenData.value) return
  panelPos.value = clampPanelPos(panelPos.value.x, panelPos.value.y)
}

watch(activeScreenData, (val) => {
  if (!val) {
    panelDragged.value = false
    return
  }
  requestAnimationFrame(() => {
    if (!panelDragged.value) {
      placePanelDefault()
      return
    }
    panelPos.value = clampPanelPos(panelPos.value.x, panelPos.value.y)
  })
})

const defaultProps = {
  children: 'children',
  label: 'label',
}

const fetchTree = async () => {
  loadingTree.value = true
  try {
    const treeUrl = treeMode.value === 'business' 
      ? '/api/v1/devices/tree/business' 
      : '/api/v1/devices/tree'
    const [deviceTreeRes, sourceRes] = await Promise.all([
      api.get(treeUrl),
      api.get('/api/v1/integrations/sources')
    ])
    const deviceTree = Array.isArray(deviceTreeRes.data) ? deviceTreeRes.data : []
    const sourceList = Array.isArray(sourceRes.data) ? sourceRes.data : []
    const sourceTree = buildSourceTree(sourceList, {
      resolveStatus: (item: Record<string, unknown>) => {
        const rtmpRunning = item?.extra?.['runtime.rtmp.is_running']
        const proxyRunning = item?.extra?.['runtime.proxy.is_running']
        const runningVal = (rtmpRunning != null ? rtmpRunning : proxyRunning)
        const running = typeof runningVal === 'boolean' ? runningVal : String(runningVal || '') === 'true'
        return running ? 1 : 0
      }
    })
    treeData.value = sourceTree ? [sourceTree, ...deviceTree] : deviceTree
    rebuildTreeNodeStats()
  } catch (e: unknown) {
    const msg = getApiErrorMessage(e, '加载设备目录失败')
    ElMessage.error(typeof msg === 'string' ? msg : '加载设备目录失败')
  } finally {
    loadingTree.value = false
  }
}

watch(filterText, (val) => {
  treeRef.value?.filter?.(val)
})

watch(highContrastTree, (val) => {
  localStorage.setItem('tree_status_high_contrast', val ? 'true' : 'false')
})


const filterNode = (value: string, data: Record<string, unknown>) => {
  if (!value) return true
  return String(data.label || '').includes(value)
}

let clickTimer: number | null = null

const handleNodeClick = (data: Record<string, unknown>, node: TreeNode) => {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
    // Double click logic
    handleDoubleClick(data)
  } else {
    // Single click logic
    clickTimer = window.setTimeout(() => {
      clickTimer = null
      if (data.children) {
        node.expanded = !node.expanded
      }
    }, 250)
  }
}

const handleDoubleClick = async (data: Record<string, unknown>) => {
  if (data.nodeType !== 'channel' && data.nodeType !== 'source_stream') return
  
  // 检查该通道是否已经在某个格子中播放（避免重复上墙）
  const existingIndex = screens.value.findIndex(s => s && s.channelId === data.id)
  if (existingIndex !== -1) {
    activeScreen.value = existingIndex
    ElMessage.warning(`该通道已经在画面 ${existingIndex + 1} 中播放`)
    return
  }
  
  // Find first empty screen or use active
  let targetIndex = -1
  for (let i = 0; i < layoutCount.value; i++) {
    if (!screens.value[i]?.url && !screens.value[i]?.loading) {
      targetIndex = i
      break
    }
  }
  if (targetIndex === -1) {
    targetIndex = activeScreen.value >= 0 ? activeScreen.value : 0
  }

  activeScreen.value = targetIndex
  
  // 先在格子中占位并显示加载状态
  screens.value[targetIndex] = {
    loading: true,
    name: data.label || data.name,
    channelId: data.id || data.gb_id,
    deviceId: data.deviceId,
    nodeType: data.nodeType
  }

  await playInScreen(data, targetIndex)
}

const handleDragStart = (node: TreeNode, ev: DragEvent) => {
  if (node.data.nodeType !== 'channel' && node.data.nodeType !== 'source_stream') {
    ev.preventDefault()
    return
  }
  isDragging.value = true
  ev.dataTransfer.setData('text/plain', JSON.stringify(node.data))
}

const handleDrop = async (ev: DragEvent, index: number) => {
  isDragging.value = false
  try {
    const data = JSON.parse(ev.dataTransfer.getData('text/plain'))
    
    screens.value[index] = {
      loading: true,
      name: data.label,
      channelId: data.id,
      deviceId: data.deviceId,
      nodeType: data.nodeType
    }

    await playInScreen(data, index)
    activeScreen.value = index
  } catch {
    ElMessage.warning('拖拽数据无效，请从设备目录拖拽通道')
  }
}

const playerRefs = ref<Record<number, any>>({})

const setPlayerRef = (el: HTMLElement | null, index: number) => {
  if (el) {
    playerRefs.value[index] = el
  } else {
    delete playerRefs.value[index]
  }
}

const takeScreenshot = (index: number) => {
  const player = playerRefs.value[index]
  if (player && typeof player.performScreenshot === 'function') {
    player.performScreenshot()
  } else {
    ElMessage.warning(t('monitor.playerNotReady'))  // FIXED: 硬编码中文→i18n
  }
}

const releaseScreen = async (index: number) => {
  const current = screens.value[index]
  if (!current) return
  try {
    await api.post('/api/v1/stream/stop', {
      app: current.app,
      stream: current.stream,
      channel_id: current.channelId
    })
  } catch (e) {
    console.warn(`停止流失败(app=${current.app}, stream=${current.stream}):`, e)
  }
}

const playInScreen = async (channel: Record<string, unknown>, index: number) => {
  const current = screens.value[index]
  if (current?.channelId === channel.id && (current.url || current.hls) && !current.error && !current.loading) return
  if (current && !current.loading) {
    await releaseScreen(index)
  }

  screens.value[index] = {
    loading: true,
    name: channel.label || channel.name,
    channelId: channel.id || channel.gb_id,
    deviceId: channel.deviceId,
    nodeType: channel.nodeType
  }

  let abortController: AbortController | null = null
  const MIN_POLL_MS = 150

  try {
    abortController = new AbortController()
    let res: Record<string, unknown> | null

    if (channel.nodeType === 'source_stream') {
      res = await api.post(`/api/v1/integrations/sources/${channel.sourceId}/play`, null, { signal: abortController.signal })
    } else {
      res = await api.post(
        `/api/v1/stream/play/${channel.deviceId}/${channel.id}`,
        null,
        { params: { stream_type: 'auto', async_mode: true }, signal: abortController.signal }
      )

      if (res.status === 202 && res.data?.data?.session_id) {
        const sessionId = res.data?.data?.session_id
        let retryCount = 0
        while (true) {
          if (abortController.signal.aborted) return
          await new Promise(r => setTimeout(r, MIN_POLL_MS))
          if (abortController.signal.aborted) return
          const pollRes = await api.get(`/api/v1/stream/play_status/${sessionId}`, { signal: abortController.signal })
          if (
            pollRes.status === 202 &&
            (pollRes.data?.data?.status === 'waiting' || pollRes.data?.data?.status === 'starting')
          ) {
            retryCount++
            if (retryCount > 60) {
              throw new Error('等待媒体流超时')
            }
            continue
          }
          res = pollRes
          break
        }
      }
    }

    if (abortController.signal.aborted) return

    const d = res.data || {} // FIXED: 空值保护，res.data可能为null/undefined
    const dd = res.data?.data || {}
    const url = d.wss_flv || d.ws_flv || d.flv || dd.wss_flv || dd.ws_flv || dd.flv
    const hls = d.wss_hls || d.ws_hls || d.hls || dd.wss_hls || dd.ws_hls || dd.hls

    if (!url && !hls) {
      throw new Error('未获取到播放地址或设备响应超时')
    }

    screens.value[index] = {
      app: d.app || 'live',
      stream: d.stream || channel.id,
      url,
      hls,
      codec: d.codec || dd.codec || 'h264',
      name: channel.label || channel.name,
      deviceId: channel.deviceId,
      channelId: channel.id || channel.gb_id,
      nodeType: channel.nodeType || 'channel',
      error: false,
      loading: false
    }
  } catch (error: unknown) {
    const err = error as Record<string, unknown> | undefined
    const isCanceled = err?.name === 'CanceledError' || err?.name === 'AbortError' || err?.code === 'ERR_CANCELED' || err?._isCanceled || String(err?.message || '').toLowerCase() === 'canceled'
    if (isCanceled) {
      screens.value[index] = null
      return
    }
    logger.warn('播放失败', error)
    const failedScreen = screens.value[index]
    screens.value[index] = {
      ...(failedScreen || {}),
      loading: false,
      error: true,
      errorMsg: getApiErrorMessage(error, '拉流失败，请稍后重试')
    }
    if (failedScreen?.app && failedScreen?.stream) {
      try { await api.post('/api/v1/stream/stop', { app: failedScreen.app, stream: failedScreen.stream }) } catch { /* best-effort cleanup */ }
    }
  } finally {
    abortController = null
  }
}

const stopScreen = async (index: number) => {
  const current = screens.value[index]
  screens.value[index] = null
  if (activeScreen.value === index) {
    activeScreen.value = -1
  }
  if (!current) return
  try {
    await api.post('/api/v1/stream/stop', {
      app: current.app,
      stream: current.stream,
      channel_id: current.channelId
    })
  } catch (e) { logger.warn('停止流失败:', e) }
}

const stopAll = async () => {
  const currentScreens = [...screens.value]
  screens.value = new Array(maxScreens).fill(null)
  activeScreen.value = -1
  ElMessage.success(t('monitor.allStopped'))  // FIXED: 硬编码中文→i18n
  
  try {
    // 后台并发执行停止请求，不阻塞界面
    await Promise.all(currentScreens.map(async (current) => {
      if (!current) return
      try {
        await api.post('/api/v1/stream/stop', {
          app: current.app,
          stream: current.stream,
          channel_id: current.channelId
        })
      } catch (e) { logger.warn('停止流失败:', e) }
    }))
  } catch (e) { logger.warn('批量停止流失败:', e) }
}

onMounted(() => {
  fetchTree()
  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(async () => {
  handlePanelMouseUp()
  window.removeEventListener('resize', handleWindowResize)
  await stopAll()
})
</script>

<style scoped>
/* Custom Scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: var(--el-fill-color-light);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 3px;
  transition: background 0.3s;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--el-text-color-placeholder);
}

/* Device Tree Styles */
.device-tree {
  background: transparent;
}
.device-tree :deep(.el-tree-node__content) {
  height: 36px;
  border-radius: 6px;
  margin: 2px 0;
  transition: all 0.2s;
}
.device-tree :deep(.el-tree-node__content:hover) {
  background: var(--el-fill-color-extra-light);
}
.device-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: var(--el-color-primary-light-9);
}
.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding-right: 8px;
}
.tree-label {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tree-text {
  color: var(--el-text-color-regular);
}
.tree-text.is-playing {
  color: var(--el-color-primary);
  font-weight: 700;
}
.playing-tag {
  margin-left: 4px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
}
.tree-status-pill {
  min-width: 44px;
  text-align: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
}
.tree-status-pill--online {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.tree-status-pill--offline {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.tree-stats-badge {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 16px;
  font-weight: 600;
}
.tree-stats-badge--good {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.tree-stats-badge--warn {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.tree-stats-badge--bad {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.tree-stats-badge--muted {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}

/* Screen Cell Styles */
.screen-cell {
  transition: all var(--transition-time-02);
  background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
}
.screen-cell:hover {
  transform: none;
  box-shadow: none;
}

/* Empty Screen Styles */
.empty-screen {
  background: linear-gradient(180deg, #111827 0%, #0b1220 100%);
}

.empty-number {
  text-shadow: none;
  color: #94a3b8;
  font-weight: 800;
}

.empty-hint {
  opacity: 0.9;
  color: #64748b;
  transition: opacity 0.3s;
}

.screen-cell:hover .empty-hint {
  opacity: 1;
}

/* Search Input */
.search-input :deep(.el-input__wrapper) {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: none;
  transition: all var(--transition-time-02);
}
.search-input :deep(.el-input__wrapper:hover) {
  border-color: var(--el-border-color);
}
.search-input :deep(.el-input__wrapper.is-focus) {
  border-color: var(--el-color-primary);
  box-shadow: none;
}

.monitor-grid-wrapper {
  background: linear-gradient(180deg, #0f172a 0%, #0b1220 100%);
  box-shadow: inset 0 0 0 1px rgba(51, 65, 85, 0.4);
}
</style>
