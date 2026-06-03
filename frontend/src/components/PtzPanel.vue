<template>
  <div class="ptz-controls p-4" style="background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;">
    <!-- 云台方向控制 -->
    <div class="grid grid-cols-3 gap-2 mb-4 w-32 mx-auto">
      <div></div>
      <el-button circle :icon="ArrowUp" @mousedown="sendPtz('up')" @mouseup="stopPtz" />
      <div></div>
      
      <el-button circle :icon="ArrowLeft" @mousedown="sendPtz('left')" @mouseup="stopPtz" />
      <el-button circle :icon="Refresh" @click="stopPtz" />
      <el-button circle :icon="ArrowRight" @mousedown="sendPtz('right')" @mouseup="stopPtz" />
      
      <div></div>
      <el-button circle :icon="ArrowDown" @mousedown="sendPtz('down')" @mouseup="stopPtz" />
      <div></div>
    </div>
    
    <!-- 变焦控制 -->
    <div class="flex justify-center gap-4 mb-4">
      <el-button circle :icon="ZoomIn" @mousedown="sendPtz('zoomin')" @mouseup="stopPtz" />
      <el-button circle :icon="ZoomOut" @mousedown="sendPtz('zoomout')" @mouseup="stopPtz" />
    </div>

    <!-- 光圈控制 -->
    <el-divider>{{ t('ptz.iris') }}</el-divider>
    <div class="flex justify-center gap-4 mb-4">
      <el-button size="small" @mousedown="sendIris('in')" @mouseup="stopIris">
        <el-icon class="mr-1"><Plus /></el-icon>
        {{ t('ptz.large') }}
      </el-button>
      <el-button size="small" @mousedown="sendIris('out')" @mouseup="stopIris">
        <el-icon class="mr-1"><Minus /></el-icon>
        {{ t('ptz.small') }}
      </el-button>
    </div>

    <!-- 聚焦控制 -->
    <el-divider>{{ t('ptz.focus') }}</el-divider>
    <div class="flex justify-center gap-4 mb-4">
      <el-button size="small" @mousedown="sendFocus('near')" @mouseup="stopFocus">
        <el-icon class="mr-1"><Aim /></el-icon>
        {{ t('ptz.near') }}
      </el-button>
      <el-button size="small" @mousedown="sendFocus('far')" @mouseup="stopFocus">
        <el-icon class="mr-1"><View /></el-icon>
        {{ t('ptz.far') }}
      </el-button>
    </div>

    <!-- 预置位管理 -->
    <el-divider>{{ t('ptz.preset') }}</el-divider>
    
    <div class="preset-section">
      <!-- 预置位列表 -->
      <div class="preset-list mb-3">
        <el-scrollbar max-height="120px">
          <div class="flex flex-wrap gap-2">
            <el-button
              v-for="preset in presetList"
              :key="preset.id"
              size="small"
              :type="currentPreset === preset.id ? 'primary' : 'default'"
              @click="callPreset(preset.id)"
              class="preset-btn"
            >
              {{ preset.name }}
            </el-button>
            <el-empty v-if="presetList.length === 0" :description="t('ptz.noPresets')" :image-size="60" />
          </div>
        </el-scrollbar>
      </div>

      <!-- 预置位操作 -->
      <div class="preset-actions flex gap-2">
        <el-input-number 
          v-model="selectedPresetId" 
          :min="1" 
          :max="255" 
          size="small" 
          style="width: 80px"
          :placeholder="t('ptz.presetId')"  <!-- FIXED: 国际化 -->
        />
        <el-button size="small" type="primary" @click="setPreset" :loading="settingPreset">
          <el-icon class="mr-1"><Plus /></el-icon>
          {{ t('ptz.set') }}
        </el-button>
        <el-button size="small" type="success" @click="callPreset(selectedPresetId)" :loading="callingPreset">
          <el-icon class="mr-1"><VideoPlay /></el-icon>
          {{ t('ptz.call') }}
        </el-button>
        <el-button size="small" type="danger" @click="deletePreset" :loading="deletingPreset">
          <el-icon class="mr-1"><Delete /></el-icon>
          {{ t('ptz.delete') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Refresh, ZoomIn, ZoomOut, Plus, VideoPlay, Delete, Minus, Aim, View } from '@element-plus/icons-vue'
import api from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  deviceId: string
  channelId: string
}>()

const lastPtzErrorAt = ref(0)
const selectedPresetId = ref(1)
const currentPreset = ref<number | null>(null)
const settingPreset = ref(false)
const callingPreset = ref(false)
const deletingPreset = ref(false)

// 预置位列表（优先后端维护）
const presetList = ref<Array<{id: number, name: string}>>([])

const loadPresets = async () => {
  try {
    const stateRes = await api.get(`/api/v1/control/${props.deviceId}/${props.channelId}/state`, {
      params: { cruise_id: 1, scan_id: 0 }
    })
    const list = Array.isArray(stateRes?.data?.preset_list) ? stateRes.data.preset_list : []
    presetList.value = list
      .map((item: Record<string, unknown>) => ({
        id: Number(item?.preset_id),
        name: t('ptz.presetName', { id: Number(item?.preset_id) })  // FIXED: 国际化
      }))
      .filter((item: { id: number }) => Number.isInteger(item.id) && item.id >= 1 && item.id <= 255)
      .sort((a: { id: number }, b: { id: number }) => a.id - b.id)
  } catch {
    try {
      const res = await api.get(`/api/v1/control/${props.deviceId}/${props.channelId}/preset/list`)
      const list = Array.isArray(res?.data?.preset_list) ? res.data.preset_list : []
      presetList.value = list
        .map((item: Record<string, unknown>) => ({
          id: Number(item?.preset_id),
          name: t('ptz.presetName', { id: Number(item?.preset_id) })  // FIXED: 国际化
        }))
        .filter((item: { id: number }) => Number.isInteger(item.id) && item.id >= 1 && item.id <= 255)
        .sort((a: { id: number }, b: { id: number }) => a.id - b.id)
    } catch {
      presetList.value = []
    }
  }
}

const syncPresetState = async () => {
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/state`, {
      preset_list: presetList.value.map((item) => ({
        preset_id: item.id,
        preset_name: item.name
      })),
      cruise_id: 1,
      scan_id: 0
    })
  } catch {
    // 同步失败不阻断主流程
  }
}

const sendPtz = async (command: string) => {
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/ptz`, {
      command: command,
      speed: 128
    })
  } catch (error) {
    const now = Date.now()
    if (now - lastPtzErrorAt.value > 2000) {
      lastPtzErrorAt.value = now
      const friendly = getFriendlyError(error)
      ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    }
  }
}

const stopPtz = async () => {  // FIXED: 添加async/await，避免PTZ停止指令静默失败
  await sendPtz('stop')
}

// ==================== 光圈控制 ====================
const sendIris = async (command: string) => {
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/iris`, {
      command: command,
      speed: 128
    })
  } catch (error) {
    const now = Date.now()
    if (now - lastPtzErrorAt.value > 2000) {
      lastPtzErrorAt.value = now
      const friendly = getFriendlyError(error)
      ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    }
  }
}

const stopIris = () => {
  sendIris('stop')
}

// ==================== 聚焦控制 ====================
const sendFocus = async (command: string) => {
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/focus`, {
      command: command,
      speed: 128
    })
  } catch (error) {
    const now = Date.now()
    if (now - lastPtzErrorAt.value > 2000) {
      lastPtzErrorAt.value = now
      const friendly = getFriendlyError(error)
      ElMessage.warning(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    }
  }
}

const stopFocus = () => {
  sendFocus('stop')
}

// ==================== 预置位管理 ====================
// 设置预置位
const setPreset = async () => {
  settingPreset.value = true
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/preset/set`, { preset_id: selectedPresetId.value })  // FIXED: 使用独立路由/preset/set+body与后端对齐
    
    await loadPresets()
    await syncPresetState()
    ElMessage.success(t('ptz.setSuccess', { id: selectedPresetId.value }))  // FIXED: 国际化
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    settingPreset.value = false
  }
}

// 调用预置位
const callPreset = async (presetId: number) => {
  callingPreset.value = true
  try {
    await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/preset`, { preset_id: presetId })  // FIXED: 使用独立路由/preset+body与后端对齐
    currentPreset.value = presetId
    ElMessage.success(t('ptz.callSuccess', { id: presetId }))  // FIXED: 国际化
  } catch (error) {
    const friendly = getFriendlyError(error)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    callingPreset.value = false
  }
}

// 删除预置位
const deletePreset = async () => {
  try {
    await ElMessageBox.confirm(
      t('ptz.deleteConfirm', { id: selectedPresetId.value }),  // FIXED: 国际化
      t('ptz.confirmDelete'),  // FIXED: 国际化
      {
        confirmButtonText: t('common.ok'),  // FIXED: 国际化
        cancelButtonText: t('common.cancel'),  // FIXED: 国际化
        type: 'warning'
      }
    )
    
    deletingPreset.value = true
    try {
      await api.post(`/api/v1/control/${props.deviceId}/${props.channelId}/preset/delete`, { preset_id: selectedPresetId.value })  // FIXED: 使用独立路由/preset/delete+body与后端对齐
      
      await loadPresets()
      await syncPresetState()
      if (currentPreset.value === selectedPresetId.value) {
        currentPreset.value = null
      }
      
      ElMessage.success(t('ptz.deleteSuccess', { id: selectedPresetId.value }))  // FIXED: 国际化
    } catch (error) {
      const friendly = getFriendlyError(error)
      ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
    } finally {
      deletingPreset.value = false
    }
  } catch {
    // 用户取消
  }
}

onMounted(() => {
  void loadPresets()
})

watch(
  () => [props.deviceId, props.channelId],
  () => {
    void loadPresets()
  }
)
</script>

<style scoped>
.ptz-controls {
  max-width: 300px;
}

.preset-section {
  margin-top: 8px;
}

.preset-list {
  min-height: 60px;
  max-height: 120px;
  overflow-y: auto;
}

.preset-btn {
  min-width: 70px;
}

.preset-actions {
  flex-wrap: wrap;
  justify-content: center;
}
</style>
