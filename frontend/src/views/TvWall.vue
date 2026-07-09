<template>
  <div class="app-page h-full flex flex-col">
    <PageContainer flex class="flex-1 min-h-0">
      <template #header>
        <PageHeader :title="t('tvWall.title')" :description="t('tvWall.description')">
          <template #actions>
            <div v-if="!isMobileRoute" class="flex flex-wrap gap-2 items-center">
              <el-tag
                size="small"
                :type="alarmWsConnected ? 'success' : (alarmWsReconnecting ? 'warning' : 'info')"
                effect="plain"
                class="alarm-tag"
              >
                <span class="flex items-center gap-1">
                  <el-icon><Connection /></el-icon>
                  {{ t('tvWall.alarmStream') }}{{ alarmWsConnected ? t('tvWall.connected') : (alarmWsReconnecting ? t('tvWall.reconnecting') : t('tvWall.disconnected')) }}
                </span>
              </el-tag>
              <span class="text-sm text-slate-600">{{ t('tvWall.layoutLabel') }}</span>
              <el-radio-group v-model="layout" size="small">
                <el-radio-button value="4">2×2</el-radio-button>
                <el-radio-button value="9">3×3</el-radio-button>
                <el-radio-button value="16">4×4</el-radio-button>
                <el-radio-button value="1+3">1+3</el-radio-button>
                <el-radio-button value="1+5">1+5</el-radio-button>
                <el-radio-button value="1+7">1+7</el-radio-button>
              </el-radio-group>
              <span class="text-sm text-slate-600 ml-2">{{ t('tvWall.mainRoam') }}</span>
              <el-select v-model="roamMainIndex" size="small" style="width: 100px">
                <el-option v-for="i in layoutCount" :key="i" :value="i - 1" :label="t('tvWall.cell', { n: i })" />
              </el-select>
              <el-select v-model="cycleSeconds" size="small" style="width: 140px">
                <el-option :value="0" :label="t('tvWall.closeRoam')" />
                <el-option :value="10" :label="t('tvWall.roamSeconds', { n: 10 })" />
                <el-option :value="20" :label="t('tvWall.roamSeconds', { n: 20 })" />
                <el-option :value="30" :label="t('tvWall.roamSeconds', { n: 30 })" />
              </el-select>
              <el-tooltip :content="t('tvWall.alarmAutoWallTip')" placement="bottom">
                <div class="flex items-center gap-2">
                  <span class="text-sm text-slate-600">{{ t('tvWall.alarmAutoWall') }}</span>
                  <el-switch v-model="alarmAutoWall" size="small" />
                </div>
              </el-tooltip>
              <el-button v-if="hasPlayingScreens" type="danger" size="small" @click="stopAll" class="stop-all-btn">
                <el-icon class="mr-1"><VideoPause /></el-icon>
                {{ t('tvWall.stopAll') }}
              </el-button>
              <el-button size="small" @click="settingsDrawerVisible = true" class="settings-btn">
                <el-icon class="mr-1"><Setting /></el-icon>
                {{ t('tvWall.tvWallSettings') }}
              </el-button>
            </div>
            <div v-else class="flex items-center gap-2">
              <el-tag
                size="small"
                :type="alarmWsConnected ? 'success' : (alarmWsReconnecting ? 'warning' : 'info')"
                effect="plain"
              >
                {{ alarmWsConnected ? t('tvWall.connected') : (alarmWsReconnecting ? t('tvWall.reconnecting') : t('tvWall.disconnected')) }}
              </el-tag>
              <el-button size="small" @click="settingsDrawerVisible = true">{{ t('tvWall.tvWallSettings') }}</el-button>
              <el-tooltip :content="t('tvWall.alarmAutoWallTip')" placement="bottom">
                <el-switch v-model="alarmAutoWall" size="small" />
              </el-tooltip>
              <el-button v-if="hasPlayingScreens" type="danger" size="small" @click="stopAll">{{ t('tvWall.stopAll') }}</el-button>
            </div>
          </template>
        </PageHeader>
      </template>

      <div class="flex-1 flex gap-3 overflow-hidden mt-3">
      <!-- Device Tree Sidebar (Fixed Left) -->
      <div class="w-72 flex-shrink-0 flex flex-col bg-white rounded border overflow-hidden" style="border-color: var(--el-border-color-lighter);">
        <div class="p-4 border-b" style="border-color: var(--el-border-color-lighter); background: var(--el-fill-color-extra-light);">
          <div class="font-bold text-slate-800 mb-3 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <el-icon class="text-purple-500"><Monitor /></el-icon>
              {{ t('tvWall.deviceDirectory') }}
            </div>
            <el-button link type="primary" size="small" @click="fetchTree">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
          <el-radio-group v-model="treeMode" size="small" @change="fetchTree" class="mb-3">
            <el-radio-button value="business">{{ t('tvWall.businessGroup') }}</el-radio-button>
            <el-radio-button value="region">{{ t('tvWall.adminRegion') }}</el-radio-button>
          </el-radio-group>
          <el-input v-model="filterText" :placeholder="t('tvWall.searchDevice')" size="small" clearable class="search-input" />
        </div>
        <div class="flex-1 overflow-auto p-3 min-h-0" style="background: var(--el-fill-color-extra-light);">
          <div v-if="loadingTree" class="flex justify-center py-12" style="color: var(--el-text-color-secondary)">
            <el-icon class="animate-spin text-2xl text-purple-500"><Loading /></el-icon>
          </div>
          <div v-else-if="!treeData.length" class="py-12 text-center">
            <el-icon class="text-5xl text-slate-300 mb-3"><FolderOpened /></el-icon>
            <div class="text-sm text-slate-500">{{ t('tvWall.noDevice') }}</div>
            <div class="text-xs text-slate-400 mt-1">{{ t('tvWall.addDeviceHint') }}</div>
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
            :folder-predicate="isTvWallTreeFolderNode"
            folder-icon-class="text-violet-500"
            base-channel-icon-class="text-purple-500"
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
      
      <!-- TV Wall Main Content -->
      <div class="flex-grow flex flex-col">
        <!-- 均分网格 -->
        <div
          v-if="!isRoamLayout"
          class="tv-wall-grid flex-grow grid gap-2 p-3 rounded overflow-hidden"
          :style="[gridStyle, { border: '1px solid rgba(51, 65, 85, 0.5)' }]"
        >
          <div
            v-for="index in maxScreens"
            :key="'g-' + index"
            class="screen-cell relative flex items-center justify-center overflow-hidden rounded-xl"
            :style="{ background: '#0f172a', border: roamMainIndex === index - 1 ? '2px solid #f59e0b' : (activeScreen === index - 1 ? '2px solid #4d8dff' : '1px solid #3a4558') }"
            :class="{ 'ring-1 ring-amber-400/90': roamMainIndex === index - 1, 'ring-1 ring-blue-400/80': activeScreen === index - 1 && roamMainIndex !== index - 1 }"
            @click="activeScreen = index - 1"
            v-show="index <= layoutCount"
          >
            <div v-if="(screens[index - 1]?.url || screens[index - 1]?.hls) && !screens[index - 1]?.error" class="w-full h-full relative" style="min-height: 100px;">
              <JessibucaPlayer
                :video-url="screens[index - 1].url"
                :hls-url="screens[index - 1].hls"
                :codec="screens[index - 1].codec"
                :has-audio="false"
                :auto-play="true"
                @refreshRequest="() => playInScreen({id: screens[index - 1].channelId, deviceId: screens[index - 1].deviceId, nodeType: screens[index - 1].nodeType, label: screens[index - 1].name}, index - 1)"
              />
              <div class="absolute top-3 left-3 bg-gradient-to-r from-black/80 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                <span class="font-semibold">{{ screens[index - 1].name }}</span>
                <span v-if="roamMainIndex === index - 1" class="ml-2 text-amber-400">⭐ {{ t('tvWall.mainScreen') }}</span>
              </div>

              <!-- Floating Action Bar (Top Right) -->
              <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                <el-button size="small" type="danger" circle @click.stop="stopScreen(index - 1)" :title="t('tvWall.closeChannel')">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              
              <!-- 录像入口：播放旁边提供“云端/设备录像” -->
              <div
                v-if="screens[index - 1]?.deviceId && screens[index - 1]?.channelId"
                class="absolute bottom-3 right-3 z-10 flex gap-2 pointer-events-auto"
              >
                <el-button size="small" type="danger" plain @click.stop="stopScreen(index - 1)">{{ t('tvWall.stopPlay') }}</el-button>
                <el-button size="small" type="primary" plain @click.stop="openRecordFromTv(index - 1, 'cloud')">{{ t('tvWall.cloudRecord') }}</el-button>
                <el-button size="small" type="success" plain @click.stop="openRecordFromTv(index - 1, 'device')">{{ t('tvWall.deviceRecord') }}</el-button>
              </div>
              <!-- Main Screen Badge -->
              <div v-if="roamMainIndex === index - 1" class="absolute top-3 right-3 bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1 text-xs text-white rounded-full font-semibold shadow-lg z-10">
                <el-icon class="mr-1"><Star /></el-icon>
                {{ t('tvWall.mainScreen') }}
              </div>
            </div>
            <div v-else-if="screens[index - 1]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
              <el-icon class="is-loading text-4xl text-purple-400 mb-3"><Loading /></el-icon>
              <div class="text-white/80 text-sm font-medium animate-pulse">{{ t('tvWall.requestingStream') }}</div>
              <div class="text-white/50 text-xs mt-2">{{ screens[index - 1].name }}</div>
            </div>
            <div v-else-if="screens[index - 1]?.error" class="w-full h-full flex flex-col items-center justify-center bg-black/40 relative group">
              <el-icon class="text-4xl text-red-500 mb-3"><Warning /></el-icon>
                <div class="text-red-400 text-sm font-medium max-w-[80%] text-center truncate" :title="screens[index - 1].errorMsg">{{ screens[index - 1].errorMsg || t('tvWall.playFailed') }}</div>
              <div class="text-white/50 text-xs mt-2">{{ screens[index - 1].name }}</div>
            </div>
            <div v-else class="empty-screen flex flex-col items-center justify-center">
              <div class="empty-number text-5xl font-bold mb-2">{{ index }}</div>
              <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                <el-icon><Pointer /></el-icon>
                {{ t('tvWall.doubleClickToPlay') }}
              </div>
            </div>
            <div
              v-if="isDragging"
              class="absolute inset-0 bg-gradient-to-br from-purple-500/20 to-pink-500/20 border-2 border-dashed border-purple-400 z-10 flex flex-col items-center justify-center rounded-xl"
              @dragover.prevent
              @drop="handleDrop($event, index - 1)"
            >
              <el-icon class="text-4xl text-purple-400 mb-2 animate-bounce"><Download /></el-icon>
              <span class="text-white font-semibold text-lg">{{ t('tvWall.dragHereToPlay') }}</span>
            </div>
          </div>
        </div>
        <!-- 开窗漫游：1+3 / 1+5 / 1+7 -->
        <div
          v-else
          class="tv-wall-grid flex-grow p-3 rounded overflow-hidden"
          :style="[roamGridStyle, { border: '1px solid rgba(51, 65, 85, 0.5)' }]"
        >
          <template v-if="layout === '1+3'">
            <div
              v-for="(cell, idx) in roamCells13"
              :key="'r13-' + idx"
              class="screen-cell relative flex items-center justify-center overflow-hidden rounded-xl"
              :style="[{ background: '#0f172a', border: roamMainIndex === cell.index ? '2px solid #f59e0b' : (activeScreen === cell.index ? '2px solid #4d8dff' : '1px solid #3a4558') }, cell.style]"
              :class="{ 'ring-1 ring-amber-400/90': roamMainIndex === cell.index, 'ring-1 ring-blue-400/80': activeScreen === cell.index && roamMainIndex !== cell.index }"
              @click="activeScreen = cell.index"
            >
              <template v-if="(screens[cell.index]?.url || screens[cell.index]?.hls) && !screens[cell.index]?.error">
                <div class="w-full h-full relative" style="min-height: 100px;">
                  <JessibucaPlayer
                    :video-url="screens[cell.index].url"
                    :hls-url="screens[cell.index].hls"
                    :codec="screens[cell.index].codec"
                    :has-audio="false"
                    :auto-play="true"
                    @refreshRequest="() => playInScreen({id: screens[cell.index].channelId, deviceId: screens[cell.index].deviceId, nodeType: screens[cell.index].nodeType, label: screens[cell.index].name}, cell.index)"
                  />
                  <div class="absolute top-3 left-3 bg-gradient-to-r from-black/80 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                    <span class="font-semibold">{{ screens[cell.index].name }}</span>
                    <span v-if="roamMainIndex === cell.index" class="ml-2 text-amber-400">⭐ {{ t('tvWall.mainScreen') }}</span>
                  </div>
                  <!-- 录像入口 -->
                  <div
                    v-if="screens[cell.index]?.deviceId && screens[cell.index]?.channelId"
                    class="absolute bottom-3 right-3 z-10 flex gap-2 pointer-events-auto"
                  >
                    <el-button size="small" type="danger" plain @click.stop="stopScreen(cell.index)">{{ t('tvWall.stopPlay') }}</el-button>
                    <el-button size="small" type="primary" plain @click.stop="openRecordFromTv(cell.index, 'cloud')">{{ t('tvWall.cloudRecord') }}</el-button>
                    <el-button size="small" type="success" plain @click.stop="openRecordFromTv(cell.index, 'device')">{{ t('tvWall.deviceRecord') }}</el-button>
                  </div>
                  <!-- Main Screen Badge -->
                  <div v-if="roamMainIndex === cell.index" class="absolute top-3 right-3 bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1 text-xs text-white rounded-full font-semibold shadow-lg z-10">
                    <el-icon class="mr-1"><Star /></el-icon>
                    {{ t('tvWall.mainScreen') }}
                  </div>
                </div>
              </template>
              <div v-else-if="screens[cell.index]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
                <el-icon class="is-loading text-4xl text-purple-400 mb-3"><Loading /></el-icon>
                <div class="text-white/80 text-sm font-medium animate-pulse">{{ t('tvWall.requestingStream') }}</div>
                <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
              </div>
              <div v-else-if="screens[cell.index]?.error" class="w-full h-full flex flex-col items-center justify-center bg-black/40 relative group">
                <el-icon class="text-4xl text-red-500 mb-3"><Warning /></el-icon>
                <div class="text-red-400 text-sm font-medium max-w-[80%] text-center truncate" :title="screens[cell.index].errorMsg">{{ screens[cell.index].errorMsg || t('tvWall.playFailed') }}</div>
                <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
              </div>
              <div v-else class="empty-screen flex flex-col items-center justify-center">
                <div class="empty-number text-4xl font-bold mb-1">{{ cell.index + 1 }}</div>
                <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                  <el-icon class="text-xs"><Pointer /></el-icon>
                  {{ t('tvWall.dragToPlay') }}
                </div>
              </div>
              <div
                v-if="isDragging"
                class="absolute inset-0 bg-gradient-to-br from-purple-500/20 to-pink-500/20 border-2 border-dashed border-purple-400 z-10 flex flex-col items-center justify-center rounded-xl"
                @dragover.prevent
                @drop="handleDrop($event, cell.index)"
              >
                <el-icon class="text-3xl text-purple-400 mb-1 animate-bounce"><Download /></el-icon>
                <span class="text-white font-semibold">{{ t('tvWall.dragHereToPlay') }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="layout === '1+5'">
            <div
              v-for="(cell, idx) in roamCells15"
              :key="'r15-' + idx"
              class="screen-cell relative flex items-center justify-center overflow-hidden rounded-xl"
              :style="[{ background: '#0f172a', border: roamMainIndex === cell.index ? '2px solid #f59e0b' : (activeScreen === cell.index ? '2px solid #4d8dff' : '1px solid #3a4558') }, cell.style]"
              :class="{ 'ring-1 ring-amber-400/90': roamMainIndex === cell.index, 'ring-1 ring-blue-400/80': activeScreen === cell.index && roamMainIndex !== cell.index }"
              @click="activeScreen = cell.index"
            >
              <template v-if="(screens[cell.index]?.url || screens[cell.index]?.hls) && !screens[cell.index]?.error">
                <JessibucaPlayer
                  :video-url="screens[cell.index].url"
                  :hls-url="screens[cell.index].hls"
                  :codec="screens[cell.index].codec"
                  :has-audio="false"
                  :auto-play="true"
                  @refreshRequest="() => playInScreen({id: screens[cell.index].channelId, deviceId: screens[cell.index].deviceId, nodeType: screens[cell.index].nodeType, label: screens[cell.index].name}, cell.index)"
                />
                <div class="absolute top-3 left-3 bg-gradient-to-r from-black/80 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                  <span class="font-semibold">{{ screens[cell.index].name }}</span>
                  <span v-if="roamMainIndex === cell.index" class="ml-2 text-amber-400">⭐ {{ t('tvWall.mainScreen') }}</span>
                </div>
                
                <!-- Floating Action Bar (Top Right) -->
                <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                  <el-button size="small" type="danger" circle @click.stop="stopScreen(cell.index)" :title="t('tvWall.closeChannel')">
                    <el-icon><Close /></el-icon>
                  </el-button>
                </div>
                
                <!-- 录像入口 -->
                <div
                  v-if="screens[cell.index]?.deviceId && screens[cell.index]?.channelId"
                  class="absolute bottom-3 right-3 z-10 flex gap-2 pointer-events-auto"
                >
                  <el-button size="small" type="danger" plain @click.stop="stopScreen(cell.index)">{{ t('tvWall.stopPlay') }}</el-button>
                  <el-button size="small" type="primary" plain @click.stop="openRecordFromTv(cell.index, 'cloud')">{{ t('tvWall.cloudRecord') }}</el-button>
                  <el-button size="small" type="success" plain @click.stop="openRecordFromTv(cell.index, 'device')">{{ t('tvWall.deviceRecord') }}</el-button>
                </div>
                <!-- Main Screen Badge -->
                <div v-if="roamMainIndex === cell.index" class="absolute top-3 right-3 bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1 text-xs text-white rounded-full font-semibold shadow-lg z-10">
                  <el-icon class="mr-1"><Star /></el-icon>
                  {{ t('tvWall.mainScreen') }}
                </div>
              </template>
              <div v-else-if="screens[cell.index]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
                <el-icon class="is-loading text-4xl text-purple-400 mb-3"><Loading /></el-icon>
                <div class="text-white/80 text-sm font-medium animate-pulse">{{ t('tvWall.requestingStream') }}</div>
                <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
              </div>
              <div v-else-if="screens[cell.index]?.error" class="w-full h-full flex flex-col items-center justify-center bg-black/40 relative group">
                <el-icon class="text-4xl text-red-500 mb-3"><Warning /></el-icon>
                <div class="text-red-400 text-sm font-medium max-w-[80%] text-center truncate" :title="screens[cell.index].errorMsg">{{ screens[cell.index].errorMsg || t('tvWall.playFailed') }}</div>
                <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
              </div>
              <div v-else class="empty-screen flex flex-col items-center justify-center">
                <div class="empty-number text-4xl font-bold mb-1">{{ cell.index + 1 }}</div>
                <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                  <el-icon class="text-xs"><Pointer /></el-icon>
                  {{ t('tvWall.dragToPlay') }}
                </div>
              </div>
              <div
                v-if="isDragging"
                class="absolute inset-0 bg-gradient-to-br from-purple-500/20 to-pink-500/20 border-2 border-dashed border-purple-400 z-10 flex flex-col items-center justify-center rounded-xl"
                @dragover.prevent
                @drop="handleDrop($event, cell.index)"
              >
                <el-icon class="text-3xl text-purple-400 mb-1 animate-bounce"><Download /></el-icon>
                <span class="text-white font-semibold">{{ t('tvWall.dragHereToPlay') }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="layout === '1+7'">
            <div
              v-for="(cell, idx) in roamCells17"
              :key="'r17-' + idx"
              class="screen-cell relative flex items-center justify-center overflow-hidden rounded-xl"
              :style="[{ background: '#0f172a', border: roamMainIndex === cell.index ? '2px solid #f59e0b' : (activeScreen === cell.index ? '2px solid #4d8dff' : '1px solid #3a4558') }, cell.style]"
              :class="{ 'ring-1 ring-amber-400/90': roamMainIndex === cell.index, 'ring-1 ring-blue-400/80': activeScreen === cell.index && roamMainIndex !== cell.index }"
              @click="activeScreen = cell.index"
            >
              <template v-if="(screens[cell.index]?.url || screens[cell.index]?.hls) && !screens[cell.index]?.error">
                <JessibucaPlayer
                  :video-url="screens[cell.index].url"
                  :hls-url="screens[cell.index].hls"
                  :codec="screens[cell.index].codec"
                  :has-audio="false"
                  :auto-play="true"
                  @refreshRequest="() => playInScreen({id: screens[cell.index].channelId, deviceId: screens[cell.index].deviceId, nodeType: screens[cell.index].nodeType, label: screens[cell.index].name}, cell.index)"
                />
                <div class="absolute top-3 left-3 bg-gradient-to-r from-black/80 to-transparent px-4 py-2 text-xs text-white rounded-r-lg pointer-events-none z-10 backdrop-blur-sm">
                  <span class="font-semibold">{{ screens[cell.index].name }}</span>
                  <span v-if="roamMainIndex === cell.index" class="ml-2 text-amber-400">⭐ {{ t('tvWall.mainScreen') }}</span>
                </div>
                
                <!-- Floating Action Bar (Top Right) -->
                <div class="absolute top-3 right-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                  <el-button size="small" type="danger" circle @click.stop="stopScreen(cell.index)" :title="t('tvWall.closeChannel')">
                    <el-icon><Close /></el-icon>
                  </el-button>
                </div>
                
                <!-- 录像入口 -->
                <div
                  v-if="screens[cell.index]?.deviceId && screens[cell.index]?.channelId"
                  class="absolute bottom-3 right-3 z-10 flex gap-2 pointer-events-auto"
                >
                  <el-button size="small" type="danger" plain @click.stop="stopScreen(cell.index)">{{ t('tvWall.stopPlay') }}</el-button>
                  <el-button size="small" type="primary" plain @click.stop="openRecordFromTv(cell.index, 'cloud')">{{ t('tvWall.cloudRecord') }}</el-button>
                  <el-button size="small" type="success" plain @click.stop="openRecordFromTv(cell.index, 'device')">{{ t('tvWall.deviceRecord') }}</el-button>
                </div>
                <!-- Main Screen Badge -->
                <div v-if="roamMainIndex === cell.index" class="absolute top-3 right-3 bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1 text-xs text-white rounded-full font-semibold shadow-lg z-10">
                  <el-icon class="mr-1"><Star /></el-icon>
                  {{ t('tvWall.mainScreen') }}
                </div>
              </template>
              <div v-else-if="screens[cell.index]?.loading" class="w-full h-full flex flex-col items-center justify-center bg-black/40">
                <el-icon class="is-loading text-4xl text-purple-400 mb-3"><Loading /></el-icon>
                <div class="text-white/80 text-sm font-medium animate-pulse">{{ t('tvWall.requestingStream') }}</div>
                <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
              </div>
              <div v-else-if="screens[cell.index]?.error" class="w-full h-full flex flex-col items-center justify-center bg-black/40 relative group">
                <el-icon class="text-4xl text-red-500 mb-3"><Warning /></el-icon>
                <div class="text-red-400 text-sm font-medium max-w-[80%] text-center truncate" :title="screens[cell.index].errorMsg">{{ screens[cell.index].errorMsg || t('tvWall.playFailed') }}</div>
                <div class="text-white/50 text-xs mt-2">{{ screens[cell.index].name }}</div>
              </div>
              <div v-else class="empty-screen flex flex-col items-center justify-center">
                <div class="empty-number text-4xl font-bold mb-1">{{ cell.index + 1 }}</div>
                <div class="empty-hint text-xs text-slate-400 flex items-center gap-1">
                  <el-icon class="text-xs"><Pointer /></el-icon>
                  {{ t('tvWall.dragToPlay') }}
                </div>
              </div>
              <div
                v-if="isDragging"
                class="absolute inset-0 bg-gradient-to-br from-purple-500/20 to-pink-500/20 border-2 border-dashed border-purple-400 z-10 flex flex-col items-center justify-center rounded-xl"
                @dragover.prevent
                @drop="handleDrop($event, cell.index)"
              >
                <el-icon class="text-3xl text-purple-400 mb-1 animate-bounce"><Download /></el-icon>
                <span class="text-white font-semibold">{{ t('tvWall.dragHereToPlay') }}</span>
              </div>
            </div>
          </template>
        </div>
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
        <span>{{ t('tvWall.deviceControl') }}{{ activeScreenData.name }}</span>
        <el-icon class="cursor-pointer hover:text-sky-500 transition-colors" @click="activeScreen = -1"><Close /></el-icon>
      </div>
      <div class="p-2 max-h-[calc(70vh-44px)] overflow-y-auto">
        <el-tabs>
          <el-tab-pane :label="t('tvWall.ptzControl')" name="ptz">
            <AdvancedPtzControl 
              :device-id="activeScreenData.deviceId" 
              :channel-id="activeScreenData.channelId" 
            />
          </el-tab-pane>
          <el-tab-pane :label="t('tvWall.voiceTalk')" name="talk">
            <TalkControl 
              :device-id="activeScreenData.deviceId" 
              :channel-id="activeScreenData.channelId" 
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
    </teleport>

    <el-drawer v-model="settingsDrawerVisible" :title="t('tvWall.tvWallSettings')" direction="btt" size="50%">
      <div class="tv-wall-controls">
        <div class="control-section">
          <div class="section-title">{{ t('tvWall.quickSwitch') }}</div>
          <div class="grid grid-cols-2 gap-3">
            <el-button
              v-if="!isSingleScreenMode"
              type="primary"
              size="large"
              @click="enterSingleScreenMode"
              class="control-btn"
            >
              <el-icon class="text-xl"><FullScreen /></el-icon>
            <span>{{ t('tvWall.switchSingle') }}</span>
            </el-button>
            <el-button
              v-else
              type="success"
              size="large"
              @click="exitSingleScreenMode"
              class="control-btn"
            >
              <el-icon class="text-xl"><Grid /></el-icon>
            <span>{{ t('tvWall.restoreLayout') }}</span>
            </el-button>
          </div>
        </div>

        <div class="control-section">
          <div class="section-title">
            <el-icon><Grid /></el-icon>
            {{ t('tvWall.windowLayout') }}
          </div>
          <div class="layout-buttons">
            <el-button
              v-for="layoutOption in layoutOptions"
              :key="layoutOption.value"
              :type="layout === layoutOption.value ? 'primary' : 'default'"
              size="large"
              @click="layout = layoutOption.value"
              class="layout-btn"
            >
              {{ layoutOption.label }}
            </el-button>
          </div>
        </div>

        <div class="control-section">
          <div class="section-title">
            <el-icon><VideoPlay /></el-icon>
            {{ t('tvWall.advancedSettings') }}
          </div>
          <div class="flex flex-wrap gap-4 items-center">
            <div class="setting-item">
              <span class="setting-label">{{ t('tvWall.mainScreen') }}</span>
              <el-select v-model="roamMainIndex" size="default" style="width: 100px">
                <el-option v-for="i in layoutCount" :key="i" :value="i - 1" :label="t('tvWall.cell', { n: i })" />
              </el-select>
            </div>
            <div class="setting-item">
              <span class="setting-label">{{ t('tvWall.patrol') }}</span>
              <el-select v-model="cycleSeconds" size="default" style="width: 140px">
                <el-option :value="0" :label="t('tvWall.close')" />
                <el-option :value="10" :label="t('tvWall.seconds', { n: 10 })" />
                <el-option :value="20" :label="t('tvWall.seconds', { n: 20 })" />
                <el-option :value="30" :label="t('tvWall.seconds', { n: 30 })" />
              </el-select>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n' // FIXED: 国际化
import { Loading, FolderOpened, Connection, VideoPause, Setting, Star, Monitor, Download, FullScreen, Grid, VideoPlay, Pointer } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import JessibucaPlayer from '../components/JessibucaPlayer.vue'
import AdvancedPtzControl from '../components/AdvancedPtzControl.vue'
import TalkControl from '../components/TalkControl.vue'
import api from '@/utils/http'
import { getApiErrorMessage } from '../utils/errorMessage'
import { buildWsUrlWithTicket } from '@/utils/wsTicket'  // P0-6: ws-ticket 认证
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import { Close } from '@element-plus/icons-vue'
import SharedChannelTree from '../components/channel/SharedChannelTree.vue'
import { useChannelTreeStats } from '../utils/channelTreeStats'
import { buildSourceTree } from '../utils/channelSourceTree'
import type { TvWallScreen, TreeNode } from '@/types/models'  // FIX: [2026-07-04] 补充 TreeNode 类型导入 [全栈工程师]
import { logger } from '@/utils/logger'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const isMobileRoute = computed(() => String(route.path || '').startsWith('/m/'))

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

const layout = ref('1+5')
const lastMultiLayout = ref<string>('1+5')
const isSingleScreenMode = computed(() => layout.value === '1')
const maxScreens = 16
const screens = ref<TvWallScreen[]>(new Array(maxScreens).fill(null))
const settingsDrawerVisible = ref(false)
const filterText = ref('')
// 兼容旧模板/缓存产物：保留 highContrastTree，避免运行时变量缺失
// SECURITY: 非敏感 UI 偏好（设备树状态高对比度开关）— 仅 'true'/'false'，不含敏感信息，可安全存入 localStorage
const highContrastTree = ref(localStorage.getItem('tree_status_high_contrast') === 'true')
type FilterableTreeRef = {
  filter?: (keyword: string) => void
}

const treeRef = ref<FilterableTreeRef | null>(null)
const treeData = ref<TvWallScreen[]>([])
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
const cycleSeconds = ref(0)
const cycleTimer = ref<number | null>(null)
const playQueue = ref<TvWallScreen[]>([])
const queueIndex = ref(0)
const ws = ref<WebSocket | null>(null)
const wsClosedByUser = ref(false)
const wsReconnectTimer = ref<number | null>(null)
const wsReconnectAttempts = ref(0)
const alarmWsConnected = ref(false)
const alarmWsReconnecting = ref(false)
const alarmAutoWall = ref(true)
const roamMainIndex = ref(0)
const activeScreen = ref(-1)
const playAbortControllers = new Map<number, AbortController>()
const devicePanelRef = ref<HTMLElement | null>(null)
const panelPos = ref({ x: 0, y: 0 })
const panelOffset = ref({ x: 0, y: 0 })
const panelDragged = ref(false)
let panelDragging = false
const PANEL_MARGIN = 16

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

const layoutOptions = [
  { value: '1', label: '1×1' },
  { value: '4', label: '2×2' },
  { value: '9', label: '3×3' },
  { value: '16', label: '4×4' },
  { value: '1+3', label: '1+3' },
  { value: '1+5', label: '1+5' },
  { value: '1+7', label: '1+7' }
]

const pendingAutoPlay = ref<{ deviceId: string; channelId: string; label?: string } | null>(null)

type RecordTab = 'cloud' | 'device'
const openRecordFromTv = (cellIndex: number, tab: RecordTab) => {
  const cell = screens.value[cellIndex]
  const deviceId = String(cell?.deviceId || '').trim()
  const channelId = String(cell?.channelId || '').trim()
  if (!deviceId || !channelId) return

  const nowIso = new Date().toISOString()
  router.push({
    path: '/devices',
    query: {
      device_id: deviceId,
      channel_id: channelId,
      tab,
      time: nowIso,
      window_minutes: 30
    }
  })
}

const layoutCount = computed(() => {
  if (layout.value === '1+3') return 4
  if (layout.value === '1+5') return 6
  if (layout.value === '1+7') return 8
  const n = parseInt(layout.value, 10)
  return Number.isNaN(n) ? 6 : n
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

const isTvWallTreeFolderNode = (node: TreeNode) => {
  return Array.isArray(node?.children) && node.children.length > 0
}

function enterSingleScreenMode() {
  if (!isSingleScreenMode.value) {
    lastMultiLayout.value = layout.value
    layout.value = '1'
    roamMainIndex.value = 0
  }
}

function exitSingleScreenMode() {
  if (isSingleScreenMode.value) {
    layout.value = lastMultiLayout.value || '9'
  }
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

const defaultProps = {
  children: 'children',
  label: 'label'
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
    const sourceTree = buildSourceTree(sourceList)
    treeData.value = sourceTree ? [sourceTree, ...deviceTree] : deviceTree
    rebuildTreeNodeStats()
    playQueue.value = collectPlayableNodes(treeData.value)
  } catch (e: unknown) {
    ElMessage.error(getApiErrorMessage(e, t('tvWall.loadTreeFailed')))
  } finally {
    loadingTree.value = false
  }
}

function _parseAutoPlayQuery() {
  const q = route.query as Record<string, unknown>
  const deviceId = String(q?.device_id || '').trim()
  const channelId = String(q?.channel_id || '').trim()
  if (!deviceId || !channelId) {
    pendingAutoPlay.value = null
    return
  }
  pendingAutoPlay.value = { deviceId, channelId, label: `${deviceId}/${channelId}` }
}

async function tryAutoPlayFromQuery() {
  _parseAutoPlayQuery()
  if (!pendingAutoPlay.value) return
  // 放到主屏（格1）
  const { deviceId, channelId, label } = pendingAutoPlay.value
  await playInScreen({ nodeType: 'channel', deviceId, id: channelId, label }, 0)
  // playInScreen 内部已有失败提示；这里补充一个成功反馈
  if (screens.value[0]?.channelId === channelId) {
    ElMessage.success(t('tvWall.startedPlaying', { label: label || channelId }))
  }
}

const collectPlayableNodes = (nodes: Record<string, unknown>[]): Record<string, unknown>[] => {
  const result: Record<string, unknown>[] = []
  const walk = (list: Record<string, unknown>[]) => {
    for (const node of list) {
      if (!node) continue
      if (node.nodeType === 'channel' || node.nodeType === 'source_stream') {
        result.push(node)
      }
      if (Array.isArray(node.children) && node.children.length) {
        walk(node.children)
      }
    }
  }
  walk(nodes)
  return result
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

const handleDoubleClick = async (data: Record<string, unknown>) => {
  if (data.nodeType !== 'channel' && data.nodeType !== 'source_stream') return
  
  // 检查该通道是否已经在某个格子中播放（避免重复上墙）
  const existingIndex = screens.value.findIndex(s => s && s.channelId === data.id)
  if (existingIndex !== -1) {
    activeScreen.value = existingIndex
    ElMessage.warning(t('tvWall.channelAlreadyPlaying', { index: existingIndex + 1 }))
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

const handleNodeClick = (data: Record<string, unknown>, node: TreeNode) => {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
    handleDoubleClick(data)
  } else {
    clickTimer = window.setTimeout(() => {
      clickTimer = null
      if (data.children) {
        node.expanded = !node.expanded
      }
    }, 250)
  }
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
    ElMessage.warning(t('tvWall.invalidDragData'))
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
  } catch {
    // 静默失败，stopAll 会统一反馈
  }
}

const playInScreen = async (channel: Record<string, unknown>, index: number) => {
  const current = screens.value[index]
  if (current?.channelId === channel.id && (current.url || current.hls) && !current.error && !current.loading) return
  if (current && !current.loading) {
    await releaseScreen(index)
  }
  const prevController = playAbortControllers.get(index)
  if (prevController) {
    prevController.abort()
    playAbortControllers.delete(index)
  }
  const controller = new AbortController()
  playAbortControllers.set(index, controller)
  const { signal } = controller
  try {
    let res: Record<string, unknown> | null
    if (channel.nodeType === 'source_stream') {
      res = await api.post(`/api/v1/integrations/sources/${channel.sourceId}/play`, null, { signal })
    } else {
      res = await api.post(
        `/api/v1/stream/play/${channel.deviceId}/${channel.id}`,
        null,
        { params: { stream_type: 'auto', async_mode: true }, signal }
      )
      
      if (res.status === 202 && res.data?.data?.session_id) {
        const sessionId = res.data.data.session_id // FIXED: 非空断言!改为隐式依赖外层if守卫
        let retryCount = 0
        while (true) {
          if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
          await new Promise(r => setTimeout(r, Number(res?.data?.data?.next_poll_ms || 600)))
          if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
          const pollRes = await api.post(`/api/v1/stream/play_status`, {  // FIXED-P2: W-10 session_id从URL路径改为请求体，防止URL泄露
            session_id: sessionId,
          }, { signal })
          if (
            pollRes.status === 202 &&
            (pollRes.data?.data?.status === 'waiting' || pollRes.data?.data?.status === 'starting')
          ) {
            retryCount++
            if (retryCount > 40) {
              throw new Error(t('tvWall.waitStreamTimeout'))
            }
            continue
          }
          res = pollRes
          break
        }
      }
    }
    
    const d = res.data || {} // FIXED: 空值保护，res.data可能为null/undefined
    const dd = res.data?.data || {}
    const url = d.wss_flv || d.ws_flv || d.flv || dd.wss_flv || dd.ws_flv || dd.flv
    const hls = d.wss_hls || d.ws_hls || d.hls || dd.wss_hls || dd.ws_hls || dd.hls
    
    if (!url && !hls) {
      throw new Error(t('tvWall.noPlayAddress'))
    }

    screens.value[index] = {
      app: d.app || 'live',
      stream: d.stream || channel.id,
      url,
      hls,
      codec: d.codec || dd.codec || 'h264',
      name: channel.label,
      deviceId: channel.deviceId,
      channelId: channel.id,
      nodeType: channel.nodeType || 'channel',
      error: false,
      loading: false
    }
  } catch (e: unknown) {
    if (signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) {
      return
    }
    logger.warn(t('tvWall.playFailed'), e)
    screens.value[index] = {
      ...(screens.value[index] || {}),
      loading: false,
      error: true,
      errorMsg: getApiErrorMessage(e, t('tvWall.playFailedRetry'))
    }
  } finally {
    playAbortControllers.delete(index)
  }
}

const stopScreen = async (index: number) => {
  const controller = playAbortControllers.get(index)
  if (controller) {
    controller.abort()
    playAbortControllers.delete(index)
  }
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
  } catch (e) { logger.warn(t('tvWall.stopStreamFailed'), e) }
}

const stopAll = async () => {
  playAbortControllers.forEach((controller) => controller.abort())
  playAbortControllers.clear()
  const currentScreens = [...screens.value]
  screens.value = new Array(maxScreens).fill(null)
  activeScreen.value = -1
  ElMessage.success(t('tvWall.stoppedAll'))
  
  try {
    await Promise.all(currentScreens.map(async (current) => {
      if (!current) return
      try {
        await api.post('/api/v1/stream/stop', {
          app: current.app,
          stream: current.stream,
          channel_id: current.channelId
        })
      } catch (e) { logger.warn(t('tvWall.stopStreamFailed'), e) }
    }))
  } catch (e) { logger.warn(t('tvWall.stopStreamFailed'), e) }
}

const clearCycleTimer = () => {
  if (cycleTimer.value !== null) {
    window.clearInterval(cycleTimer.value)
    cycleTimer.value = null
  }
}

const startCycle = () => {
  clearCycleTimer()
  const interval = Number(cycleSeconds.value)
  if (!interval || playQueue.value.length === 0) return
  const visibleCount = layoutCount.value
  cycleTimer.value = window.setInterval(async () => {
    if (playQueue.value.length === 0) return
    // P1-41: 200ms 错峰分批启动 — 避免同时拉流导致信令/网络瞬时拥塞（硬约束 #9）
    for (let i = 0; i < visibleCount; i++) {
      const node = playQueue.value[(queueIndex.value + i) % playQueue.value.length]
      playInScreen(node, i)
      if (i < visibleCount - 1) {
        await new Promise(resolve => setTimeout(resolve, 200))
      }
    }
    queueIndex.value = (queueIndex.value + visibleCount) % playQueue.value.length
  }, interval * 1000)
}

watch(cycleSeconds, () => {
  startCycle()
})

watch(layout, () => {
  roamMainIndex.value = Math.min(roamMainIndex.value, Math.max(0, layoutCount.value - 1))
  startCycle()
  // P1-42: 16 路分屏时基于 hardwareConcurrency/deviceMemory 显示性能警告（硬约束 #6）
  if (layout.value === '16') {
    const cores = navigator.hardwareConcurrency || 4
    const memory = (navigator as any).deviceMemory || 4
    if (cores < 4 || memory < 4) {
      ElMessage.warning(
        t('tvWall.perfWarning16', {
          cores,
          memory,
          defaultValue: `Performance warning: 16-screen grid on ${cores} cores / ${memory}GB RAM may cause lag. Consider using fewer screens.`,
        })
      )
    }
  }
})

onMounted(() => {
  fetchTree()
  initAlarmWebSocket()
  tryAutoPlayFromQuery()
  window.addEventListener('resize', handleWindowResize)
})

watch(
  () => route.query,
  () => {
    tryAutoPlayFromQuery()
  }
)

onBeforeUnmount(async () => {
  clearCycleTimer()
  handlePanelMouseUp()
  window.removeEventListener('resize', handleWindowResize)
  await stopAll()
  if (ws.value) {
    wsClosedByUser.value = true
    ws.value.close()
  }
  if (wsReconnectTimer.value != null) {
    clearTimeout(wsReconnectTimer.value)
    wsReconnectTimer.value = null
  }
})

const handleAlarmMessage = async (alarm: Record<string, unknown>) => {
  if (!alarmAutoWall.value) return
  if (!alarm || !alarm.device_id || !alarm.channel_id) return
  const target = 0
  const channel = {
    id: alarm.channel_id,
    label: alarm.description || alarm.channel_id,
    nodeType: 'channel',
    deviceId: alarm.device_id
  }
  await playInScreen(channel, target)
}

const initAlarmWebSocket = async () => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.host
  if (wsReconnectTimer.value != null) {
    clearTimeout(wsReconnectTimer.value)
    wsReconnectTimer.value = null
  }
  // P0-6: 通过 ws-ticket 认证，消除 URL 暴露 JWT token
  let wsUrl: string
  try {
    wsUrl = await buildWsUrlWithTicket('/api/v1/alarms/ws')
  } catch (e) {
    logger.warn('initAlarmWebSocket: failed to fetch ws-ticket', e)
    return
  }
  ws.value = new WebSocket(wsUrl)
  ws.value.onmessage = (event) => {
    try {
      const alarm = JSON.parse(event.data)
      handleAlarmMessage(alarm)
    } catch {
      // 忽略非 JSON 消息
    }
  }
  ws.value.onopen = () => {
    alarmWsConnected.value = true
    alarmWsReconnecting.value = false
    wsReconnectAttempts.value = 0
  }
  ws.value.onclose = () => {
    alarmWsConnected.value = false
    if (wsClosedByUser.value) return
    if (wsReconnectTimer.value != null) return
    alarmWsReconnecting.value = true
    wsReconnectAttempts.value += 1
    const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(wsReconnectAttempts.value, 5)))
    wsReconnectTimer.value = window.setTimeout(() => {
      wsReconnectTimer.value = null
      initAlarmWebSocket()
    }, delay)
  }
}
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

/* Action Buttons */
.stop-all-btn {
  transition: all var(--transition-time-02);
}
.stop-all-btn:hover {
  transform: none;
  box-shadow: none;
}
.settings-btn {
  transition: all var(--transition-time-02);
}
.settings-btn:hover {
  transform: none;
  box-shadow: none;
}

/* Alarm Tag */
.alarm-tag {
  background: var(--el-fill-color-extra-light);
}

.tv-wall-grid {
  background: linear-gradient(180deg, #0f172a 0%, #0b1220 100%);
  box-shadow: inset 0 0 0 1px rgba(51, 65, 85, 0.4);
}

.tv-wall-controls {
  padding: 20px 24px;
}

.control-section {
  margin-bottom: 24px;
}

.control-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title .el-icon {
  color: var(--el-color-primary);
}

.control-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 72px;
  border-radius: 6px;
  font-weight: 500;
  transition: all 0.3s;
}

.control-btn .el-icon {
  font-size: 24px;
}

.control-btn:hover {
  transform: none;
  box-shadow: none;
}

.layout-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.layout-btn {
  min-width: 72px;
  height: 40px;
  border-radius: 6px;
  font-weight: 500;
  transition: all 0.2s;
}

.layout-btn:hover {
  transform: none;
}

.setting-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.setting-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}
</style>
