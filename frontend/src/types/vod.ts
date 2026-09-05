export interface VodSource {
  url?: string
  type?: string
  mp4?: string
  hls?: string
  flv?: string
  https_hls?: string
  https_flv?: string
  ws_hls?: string
  ws_flv?: string
  wss_hls?: string
  wss_flv?: string
  [k: string]: unknown
}

/** 画质等级：auto 或 level_{height}p（如 level_720p） */
export type VodQualityLevel = 'auto' | `level_${number}p`

export interface VodPlayerConfig {
  autoplay: boolean
  muted: boolean
  loop: boolean
  preload: '' | 'metadata' | 'none' | 'auto'
  quality: VodQualityLevel
  debug: boolean
  adaptiveBuffer: boolean
  minBufferTime: number
  maxBufferTime: number
  startBufferTime: number
  bufferHealthThreshold: number
  enableQualityAdaptation: boolean
  smoothQualityTransition: boolean
  maxRetries: number
  retryDelay: number
  requestTimeout: number
}

export type VodPlayerStatus =
  | 'idle'
  | 'loading'
  | 'buffering'
  | 'ready'
  | 'playing'
  | 'paused'
  | 'ended'
  | 'error'

export interface VodPlayerState {
  status: VodPlayerStatus
  currentTime: number
  duration: number
  isBuffering: boolean
  bufferProgress: number
  qualityLevel: VodQualityLevel
  availableQualities: VodQualityLevel[]
  muted: boolean
  volume: number
  error?: string
}

export interface VodQualityMetrics {
  bitrate: number
  fps: number
  width: number
  height: number
  codec: string
  bufferDelay: number
  droppedFrames: number
  totalFrames: number
  latency: number
  lastUpdate: number
}

export type VodPlayerEvent =
  | 'play'
  | 'pause'
  | 'ended'
  | 'timeupdate'
  | 'error'
  | 'ready'
  | 'qualitychange'
  | 'metrics'
  | 'statechange'

export interface VodPlayerEventPayload {
  event: VodPlayerEvent
  currentTime?: number
  duration?: number
  error?: { code: string; message: string }
  [key: string]: unknown
}
