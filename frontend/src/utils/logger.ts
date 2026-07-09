/**
 * Lightweight logger — only outputs in development mode to avoid leaking
 * debug information in production builds.
 */

const isDev = import.meta.env.DEV

function _format(level: string, args: unknown[]): unknown[] {
  return [`[${level}]`, ...args]
}

export const logger = {
  debug(...args: unknown[]): void {
    if (isDev) {
      console.debug(..._format('DEBUG', args))
    }
  },
  info(...args: unknown[]): void {
    if (isDev) {
      console.info(..._format('INFO', args))
    }
  },
  warn(...args: unknown[]): void {
    console.warn(..._format('WARN', args))
  },
  error(...args: unknown[]): void {
    console.error(..._format('ERROR', args))
  },
}

export default logger
