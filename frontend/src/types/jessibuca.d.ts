/** Jessibuca Player type declarations */
declare class Jessibuca {
  constructor(container: HTMLElement, options?: Jessibuca.Options)
  play(url: string): void
  stop(): void
  destroy(): void
  pause(): void
  resume(): void
  mute(): void
  unmute(): void
  setVolume(volume: number): void
  fullScreen(): void
  exitFullScreen(): void
  screenshot(filename?: string, format?: string, quality?: number): string
  on(event: string, callback: (...args: unknown[]) => void): void
  off(event: string, callback: (...args: unknown[]) => void): void
  isPlaying(): boolean
  isMuted(): boolean
  resize(): void
}

declare namespace Jessibuca {
  interface Options {
    decoder?: string
    playURL?: string
    playing?: boolean
    debug?: boolean
    debugLevel?: number
    useWCS?: boolean
    useMSE?: boolean
    videoBuffer?: number
    videoBufferDelay?: number
    heartTimeout?: number
    loadingTimeout?: number
    supportWCSV?: boolean
    supportWCSH264?: boolean
    useOffscreen?: boolean
    autoPlay?: boolean
    showBandwidth?: boolean
    operateBtns?: OperateBtns
    background?: string
    hasAudio?: boolean
    hasVideo?: boolean
    rotate?: number
    timeout?: number
    heartTimeoutReplay?: boolean
    heartTimeoutMaxReplay?: number
    resize?: boolean
    fullscreen?: boolean
    screenshot?: boolean
    volume?: boolean
    pause?: boolean
    mute?: boolean
  }

  interface OperateBtns {
    fullscreen?: boolean
    screenshot?: boolean
    play?: boolean
    audio?: boolean
  }
}

export default Jessibuca
