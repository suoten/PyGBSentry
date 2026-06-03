<template>
  <div class="share-panel">
    <div class="share-intro">
      <div class="intro-icon">
        <el-icon><Share /></el-icon>
      </div>
      <div class="intro-text">
        <div class="intro-title">分享视频流</div>
        <div class="intro-desc">复制下方链接与他人共享视频</div>
      </div>
    </div>

    <div class="share-section">
      <div class="section-title">
        <el-icon><Link /></el-icon>
        播放地址
      </div>
      <div class="url-input-group">
        <el-input
          v-model="playUrl"
          readonly
          type="textarea"
          :rows="2"
          class="share-url-input"
        />
        <div class="url-actions">
          <el-button type="primary" @click="copyPlayUrl" :icon="DocumentCopy">
            复制地址
          </el-button>
          <el-button @click="openPlayUrl" :icon="TopRight">
            新标签打开
          </el-button>
        </div>
      </div>
    </div>

    <div class="share-section">
      <div class="section-title">
        <el-icon><Monitor /></el-icon>
        嵌入代码
      </div>
      <div class="url-input-group">
        <el-input
          v-model="iframeCode"
          readonly
          type="textarea"
          :rows="3"
          class="share-url-input"
        />
        <div class="url-actions">
          <el-button type="primary" @click="copyIframeCode" :icon="DocumentCopy">
            复制代码
          </el-button>
        </div>
      </div>
    </div>

    <div class="share-section">
      <div class="section-title">
        <el-icon><Box /></el-icon>
        二维码分享
      </div>
      <div class="qr-section">
        <div class="qr-placeholder">
          <canvas v-if="qrDataUrl" class="qr-canvas" />
          <template v-else>
            <el-icon class="text-5xl text-slate-300"><Picture /></el-icon>
            <span class="text-slate-400 text-sm mt-2">二维码生成</span>
          </template>
          <el-button size="small" class="mt-2" @click="generateQR" :loading="qrLoading">
            {{ qrDataUrl ? '重新生成' : '生成二维码' }}
          </el-button>
          <el-button v-if="qrDataUrl" size="small" class="mt-1" @click="downloadQR">
            下载二维码
          </el-button>
        </div>
      </div>
    </div>

    <el-divider>分享设置</el-divider>

    <div class="share-settings">
      <div class="setting-item">
        <span class="setting-label">有效期</span>
        <el-select v-model="shareExpiry" size="small" style="width: 140px">
          <el-option label="永久有效" value="never" />
          <el-option label="1小时" value="1h" />
          <el-option label="24小时" value="24h" />
          <el-option label="7天" value="7d" />
        </el-select>
      </div>

      <div class="setting-item">
        <span class="setting-label">访问密码</span>
        <el-switch v-model="requirePassword" size="small" />
      </div>

      <div v-if="requirePassword" class="setting-item password-item">
        <span class="setting-label">设置密码</span>
        <el-input
          v-model="sharePassword"
          placeholder="请输入密码"
          size="small"
          show-password
          style="width: 180px"
        />
      </div>

      <div class="setting-item">
        <span class="setting-label">允许录制</span>
        <el-switch v-model="allowRecord" size="small" />
      </div>

      <div class="setting-item">
        <span class="setting-label">水印</span>
        <el-switch v-model="enableWatermark" size="small" />
      </div>
    </div>

    <div class="generate-share-btn">
      <el-button type="primary" size="large" @click="generateShareLink" :icon="MagicStick">
        生成分享链接
      </el-button>
    </div>

    <div v-if="recentShares.length > 0" class="recent-shares">
      <div class="section-title">
        <el-icon><Clock /></el-icon>
        最近分享
      </div>
      <div class="share-list">
        <div v-for="(item, index) in recentShares" :key="index" class="share-item">
          <div class="share-item-info">
            <div class="share-item-time">{{ formatTime(item.time) }}</div>
            <div class="share-item-url truncate">{{ item.url }}</div>
          </div>
          <div class="share-item-actions">
            <el-button size="small" link @click="copyShareUrl(item.url)">
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
            <el-button size="small" link type="danger" @click="removeShare(index)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import {
  Share,
  Link,
  Monitor,
  Box,
  DocumentCopy,
  TopRight,
  Picture,
  MagicStick,
  Clock,
  Delete
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'

const props = defineProps<{
  videoUrl?: string
  title?: string
}>()

const shareExpiry = ref('never')
const requirePassword = ref(false)
const sharePassword = ref('')
const allowRecord = ref(true)
const enableWatermark = ref(false)
const recentShares = ref<Array<{ time: Date; url: string }>>([])

const playUrl = computed(() => props.videoUrl || '')

const iframeCode = computed(() => {
  if (!props.videoUrl) return ''
  const title = encodeURIComponent(props.title || '视频播放')
  return `<iframe src="${props.videoUrl}" title="${title}" width="640" height="480" frameborder="0" allowfullscreen></iframe>`
})

const copyPlayUrl = async () => {
  if (!playUrl.value) {
    ElMessage.warning('暂无播放地址')
    return
  }
  try {
    await navigator.clipboard.writeText(playUrl.value)
    ElMessage.success('播放地址已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

const openPlayUrl = () => {
  if (!playUrl.value) {
    ElMessage.warning('暂无播放地址')
    return
  }
  window.open(playUrl.value, '_blank')
}

const copyIframeCode = async () => {
  if (!iframeCode.value) {
    ElMessage.warning('暂无嵌入代码')
    return
  }
  try {
    await navigator.clipboard.writeText(iframeCode.value)
    ElMessage.success('嵌入代码已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

const qrDataUrl = ref('')
const qrLoading = ref(false)

const generateQR = async () => {
  if (!playUrl.value) {
    ElMessage.warning('暂无播放地址，请先开始播放')
    return
  }
  qrLoading.value = true
  try {
    qrDataUrl.value = await QRCode.toDataURL(playUrl.value, {
      width: 200,
      margin: 2,
      color: { dark: '#1e40af', light: '#ffffff' }
    })
    await nextTick()
    const canvas = document.querySelector('.qr-canvas') as HTMLCanvasElement
    if (canvas) {
      const ctx = canvas.getContext('2d')
      if (ctx) {
        const img = new Image()
        img.onload = () => {
          canvas.width = img.width
          canvas.height = img.height
          ctx.drawImage(img, 0, 0)
        }
        img.src = qrDataUrl.value
      }
    }
    ElMessage.success('二维码已生成')
  } catch {
    ElMessage.error('二维码生成失败')
  } finally {
    qrLoading.value = false
  }
}

const downloadQR = () => {
  if (!qrDataUrl.value) return
  const link = document.createElement('a')
  link.download = `share-qr-${Date.now()}.png`
  link.href = qrDataUrl.value
  link.click()
  ElMessage.success('二维码已下载')
}

const generateShareLink = () => {
  if (!playUrl.value) {
    ElMessage.warning('请先开始播放')
    return
  }
  
  const shareUrl = playUrl.value
  
  recentShares.value.unshift({
    time: new Date(),
    url: shareUrl
  })
  
  if (recentShares.value.length > 5) {
    recentShares.value = recentShares.value.slice(0, 5)
  }
  
  ElMessage.success('分享链接已生成')
}

const copyShareUrl = async (url: string) => {
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success('分享链接已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

const removeShare = (index: number) => {
  recentShares.value.splice(index, 1)
  ElMessage.success('已删除')
}

const formatTime = (date: Date) => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  if (diff < 60000) {
    return '刚刚'
  } else if (diff < 3600000) {
    return `${Math.floor(diff / 60000)}分钟前`
  } else if (diff < 86400000) {
    return `${Math.floor(diff / 3600000)}小时前`
  } else {
    return date.toLocaleDateString('zh-CN')
  }
}
</script>

<style scoped>
.share-panel {
  padding: 8px 4px;
}

.share-intro {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-radius: 12px;
  margin-bottom: 20px;
}

.intro-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #3b82f6 0%, #2563eb 100%);
  border-radius: 12px;
}

.intro-icon .el-icon {
  font-size: 24px;
  color: white;
}

.intro-text {
  flex: 1;
}

.intro-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e40af;
  margin-bottom: 4px;
}

.intro-desc {
  font-size: 13px;
  color: #60a5fa;
}

.share-section {
  margin-bottom: 20px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12px;
}

.url-input-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.share-url-input :deep(.el-textarea__inner) {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}

.url-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.qr-section {
  padding: 20px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: 12px;
  border: 1px dashed #d1d5db;
}

.qr-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.qr-canvas {
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.share-settings {
  padding: 4px;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f3f4f6;
}

.setting-item:last-child {
  border-bottom: none;
}

.password-item {
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.setting-label {
  font-size: 14px;
  color: #4b5563;
  font-weight: 500;
}

.generate-share-btn {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}

.generate-share-btn .el-button {
  width: 100%;
  border-radius: 10px;
  font-weight: 600;
}

.recent-shares {
  margin-top: 20px;
}

.share-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.share-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: 10px;
  border: 1px solid #e5e7eb;
}

.share-item-info {
  flex: 1;
  min-width: 0;
}

.share-item-time {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.share-item-url {
  font-size: 12px;
  color: #4b5563;
  font-family: monospace;
}

.share-item-actions {
  display: flex;
  gap: 4px;
}
</style>
