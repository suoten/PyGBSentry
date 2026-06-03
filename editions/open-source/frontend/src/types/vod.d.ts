/**
 * 点播播放器类型定义
 */

export type VodQualityLevel = 'auto' | '1080p' | '720p' | '480p' | '360p'

export interface VodSource {
  /** 原始文件URL (MP4) */
  mp4?: string
  /** HTTP-FLV 流地址 */
  flv?: string
  /** WebSocket-FLV 流地址 */
  ws_flv?: string
  /** WebSocket over TLS FLV */
  wss_flv?: string
  /** HTTPS FLV */
  https_flv?: string
  /** HLS 流地址 */
  hls?: string
  /** WebSocket HLS */
  ws_hls?: string
  /** WebSocket over TLS HLS */
  wss_hls?: string
  /** HTTPS HLS */
  https_hls?: string
  /** WebRTC 地址 */
  webrtc?: string
  /** WebRTC over TLS */
  rtcs?: string
  /** 提示信息 */
  hint?: string
}

export interface VodPlayerState {
  /** 播放器状态 */
  status: 'idle' | 'loading' | 'buffering' | 'playing' | 'paused' | 'ended' | 'error'
  /** 当前播放时间 (秒) */
  currentTime: number
  /** 视频总时长 (秒) */
  duration: number
  /** 是否正在缓冲 */
  isBuffering: boolean
  /** 缓冲进度 0-100 */
  bufferProgress: number
  /** 当前画质等级 */
  qualityLevel: VodQualityLevel
  /** 可用画质列表 */
  availableQualities: VodQualityLevel[]
  /** 错误信息 */
  error?: string
  /** 是否静音 */
  muted: boolean
  /** 音量 0-1 */
  volume: number
}

export interface VodQualityMetrics {
  /** 码率 (kbps) */
  bitrate: number
  /** 帧率 */
  fps: number
  /** 视频宽度 */
  width: number
  /** 视频高度 */
  height: number
  /** 编码器 */
  codec: string
  /** 缓冲延迟 (ms) */
  bufferDelay: number
  /**丢帧数 */
  droppedFrames: number
  /** 总帧数 */
  totalFrames: number
  /** 网络延迟 (ms) */
  latency: number
  /** 最后更新时间 */
  lastUpdate: number
}

export interface VodPlayerConfig {
  /** 自动播放 */
  autoplay?: boolean
  /** 静音播放 (解决浏览器自动播放策略) */
  muted?: boolean
  /** 循环播放 */
  loop?: boolean
  /** 预加载策略: 'none' | 'metadata' | 'auto' */
  preload?: 'none' | 'metadata' | 'auto'
  /** 初始画质 */
  quality?: VodQualityLevel
  /** 启用调试日志 */
  debug?: boolean
  /** 自适应缓冲启用 */
  adaptiveBuffer?: boolean
  /** 最小缓冲时间 (ms) */
  minBufferTime?: number
  /** 最大缓冲时间 (ms) */
  maxBufferTime?: number
  /** 起始缓冲时间 (ms) */
  startBufferTime?: number
  /** 缓冲健康阈值 (0-1) */
  bufferHealthThreshold?: number
  /** 启用画质自适应 */
  enableQualityAdaptation?: boolean
  /** 画质切换平滑过渡 */
  smoothQualityTransition?: boolean
  /** 错误重试次数 */
  maxRetries?: number
  /** 重试延迟 (ms) */
  retryDelay?: number
  /** 请求超时 (ms) */
  requestTimeout?: number
}

/** 播放事件类型 */
export type VodPlayerEvent = 
  | 'play'
  | 'pause'
  | 'ended'
  | 'timeupdate'
  | 'durationchange'
  | 'waiting'
  | 'playing'
  | 'error'
  | 'stalled'
  | 'qualitychange'
  | 'bufferingchange'
  | 'metricsupdate'
  | 'ready'
  | 'sourcechange'

export interface VodPlayerEventPayload {
  play: { currentTime: number }
  pause: { currentTime: number }
  ended: { totalTime: number }
  timeupdate: { currentTime: number; duration: number }
  durationchange: { duration: number }
  waiting: { reason: string }
  playing: { latency: number }
  error: { code: string; message: string }
  stalled: { duration: number }
  qualitychange: { from: VodQualityLevel; to: VodQualityLevel }
  bufferingchange: { isBuffering: boolean; progress: number }
  metricsupdate: VodQualityMetrics
  ready: { duration: number }
  sourcechange: { source: VodSource }
}

/** 录像回放信息 */
export interface RecordPlaybackInfo {
  /** 录像ID */
  recordId: string
  /** 设备ID */
  deviceId: string
  /** 通道ID */
  channelId: string
  /** 开始时间 (ISO8601) */
  startTime: string
  /** 结束时间 (ISO8601) */
  endTime: string
  /** 可用播放源 */
  sources: VodSource
  /** 录像时长 (秒) */
  duration: number
  /** 文件大小 (字节) */
  fileSize: number
  /** 录像类型: 'cloud' | 'device' */
  recordType: 'cloud' | 'device'
}

/** 跨文件无缝回放段 */
export interface SeamlessSegment {
  /** 段ID */
  id: string
  /** 开始时间 (Unix时间戳 秒) */
  startTime: number
  /** 结束时间 (Unix时间戳 秒) */
  endTime: number
  /** 播放源 */
  sources: VodSource
  /** 优先级 (用于预加载) */
  priority: number
  /** 是否已预加载 */
  preloaded: boolean
}

/** 无缝回放会话 */
export interface SeamlessPlaybackSession {
  /** 会话ID */
  sessionId: string
  /** 录像ID列表 */
  recordIds: string[]
  /** 段列表 */
  segments: SeamlessSegment[]
  /** 当前播放段索引 */
  currentSegmentIndex: number
  /** 总时长 */
  totalDuration: number
  /** 预加载状态 */
  preloadStatus: 'idle' | 'preloading' | 'ready' | 'error'
}
