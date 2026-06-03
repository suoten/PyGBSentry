const isDev = import.meta.env.DEV

function warn(...args: unknown[]) {
  if (isDev) console.warn(...args)
}

function error(...args: unknown[]) {
  if (isDev) console.error(...args)
}

function info(...args: unknown[]) {
  if (isDev) console.info(...args)
}

export const logger = { warn, error, info }
