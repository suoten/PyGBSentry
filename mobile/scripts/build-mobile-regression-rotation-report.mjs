import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const historyPath = process.env.MOBILE_REGRESSION_ROTATION_HISTORY_PATH || "scripts/mobile-regression.rotation-history.json";
const reportJsonPath = process.env.MOBILE_REGRESSION_ROTATION_REPORT_JSON_PATH || "scripts/mobile-regression.rotation-report.json";
const reportMdPath = process.env.MOBILE_REGRESSION_ROTATION_REPORT_MD_PATH || "scripts/mobile-regression.rotation-report.md";
const closeoutStatusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_STATUS_PATH || "scripts/mobile-regression.rotation-closeout-status.json";
const windowDays = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_REPORT_WINDOW_DAYS || 7));

function readJsonSafe(path, fallback) {
  const file = resolve(process.cwd(), path);
  if (!existsSync(file)) return fallback;
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeText(path, content) {
  const file = resolve(process.cwd(), path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, content, "utf8");
}

const history = readJsonSafe(historyPath, { events: [] });
const allEvents = Array.isArray(history?.events) ? history.events : [];

const now = Date.now();
const windowStart = now - windowDays * 24 * 60 * 60 * 1000;
const events = allEvents.filter((x) => {
  const t = new Date(String(x?.at || "")).getTime();
  return !Number.isNaN(t) && t >= windowStart;
});

const stats = {
  total: events.length,
  passed: 0,
  failed: 0,
  skipped: 0
};
const byReasonCode = {};
const trendByDay = {};

for (const row of events) {
  if (row?.ok === true && row?.skipped !== true) stats.passed += 1;
  if (row?.ok !== true) stats.failed += 1;
  if (row?.skipped === true) stats.skipped += 1;
  const reason = String(row?.reason_code || "UNKNOWN");
  byReasonCode[reason] = (byReasonCode[reason] || 0) + 1;
  const day = String(row?.at || "").slice(0, 10) || "unknown";
  trendByDay[day] = (trendByDay[day] || 0) + 1;
}

const closeoutStatus = readJsonSafe(closeoutStatusPath, null);
const closeoutReasonCode = String(closeoutStatus?.reason_code || "");
const closeoutAttention = !!closeoutReasonCode && closeoutReasonCode !== "OK" && closeoutReasonCode !== "SKIPPED";
if (closeoutAttention) {
  const key = `CLOSEOUT_${closeoutReasonCode}`;
  byReasonCode[key] = (byReasonCode[key] || 0) + 1;
}

const attentionReasonCodes = [];
if (stats.failed > 0) {
  attentionReasonCodes.push("ROTATION_FAILED_EVENTS");
}
if (closeoutAttention) {
  attentionReasonCodes.push(`CLOSEOUT_${closeoutReasonCode}`);
}

const report = {
  generated_at: new Date().toISOString(),
  window_days: windowDays,
  window_start: new Date(windowStart).toISOString(),
  totals: stats,
  by_reason_code: byReasonCode,
  trend_by_day: trendByDay,
  attention_reason_codes: attentionReasonCodes,
  closeout_status: closeoutStatus
};

writeText(resolve(process.cwd(), reportJsonPath), `${JSON.stringify(report, null, 2)}\n`);

const topReasons = Object.entries(byReasonCode)
  .sort((a, b) => Number(b[1]) - Number(a[1]))
  .slice(0, 8);
const trendLines = Object.entries(trendByDay)
  .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
  .map(([day, count]) => `- ${day}: ${count}`);
const topReasonLines = topReasons.length > 0 ? topReasons.map(([code, count]) => `- ${code}: ${count}`) : ["- no data"];
const attentionLines =
  attentionReasonCodes.length > 0 ? attentionReasonCodes.map((code) => `- ${code}`) : ["- none"];
const closeoutSummaryLine = closeoutStatus
  ? `- reason_code=${String(closeoutStatus?.reason_code || "UNKNOWN")}, ok=${closeoutStatus?.ok === true}, required=${closeoutStatus?.required === true}`
  : "- no closeout status";
const closeoutWindowLine =
  closeoutStatus && (closeoutStatus?.window_start_at || closeoutStatus?.window_end_at)
    ? `- window=${String(closeoutStatus?.window_start_at || "")} ~ ${String(closeoutStatus?.window_end_at || "")}, signoff_at=${String(closeoutStatus?.signoff_at || "")}`
    : "- window/signoff not provided";

const markdown = [
  "## Mobile Regression Rotation Weekly Report",
  "",
  `- Window: last ${windowDays} day(s)`,
  `- Total events: ${stats.total}`,
  `- Passed: ${stats.passed}, Failed: ${stats.failed}, Skipped: ${stats.skipped}`,
  "",
  "### Top Reason Codes",
  ...topReasonLines,
  "",
  "### Trend By Day",
  ...(trendLines.length > 0 ? trendLines : ["- no data"]),
  "",
  "### Attention Reason Codes",
  ...attentionLines,
  "",
  "### Closeout Snapshot",
  closeoutSummaryLine,
  closeoutWindowLine,
  ""
].join("\n");

writeText(resolve(process.cwd(), reportMdPath), markdown);
console.log(`[build-mobile-regression-rotation-report] ok: events=${stats.total}, window=${windowDays}d`);
