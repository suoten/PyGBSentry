/** H265Web Player type declarations */
declare class H265WebPlayer {
  constructor(container: HTMLElement, options?: H265WebPlayer.Options)
  play(url: string, token?: string): void
  stop(): void
  destroy(): void
  pause(): void
  resume(): void
  mute(): void
  unmute(): void
  setVolume(volume: number): void
  fullScreen(): void
  exitFullScreen(): void
  on(event: string, callback: (...args: unknown[]) => void): void
  off(event: string, callback: (...args: unknown[]) => void): void
}

declare namespace H265WebPlayer {
  interface Options {
    decoder?: string
    token?: string
    autoPlay?: boolean
    debug?: boolean
    resize?: boolean
    fullscreen?: boolean
  }
}

export default H265WebPlayer
