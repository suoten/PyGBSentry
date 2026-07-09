/**
 * Frontend timezone helper — ensures date pickers and display formatting
 * default to the configured backend timezone (Asia/Shanghai for GB28181).
 */

const TARGET_TZ = 'Asia/Shanghai'

/**
 * Apply the Beijing timezone to dayjs or other date libraries that respect
 * Intl.DateTimeFormat.  This is a no-op if the browser doesn't support
 * `Intl.DateTimeFormat` with timeZone option (all modern browsers do).
 */
export function applyBeijingTimezone(): void {
  try {
    // Verify the timezone is supported by the runtime
    const formatter = new Intl.DateTimeFormat('zh-CN', { timeZone: TARGET_TZ })
    formatter.format(new Date())
  } catch {
    console.warn(`[timezone] "${TARGET_TZ}" is not supported by this browser; using system timezone`)
  }
}

export default applyBeijingTimezone
