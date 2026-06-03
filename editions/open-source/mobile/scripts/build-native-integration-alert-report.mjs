import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const historyPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_HISTORY_PATH || "scripts/native-player-integration.alert-history.json";
const reportJsonPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_JSON_PATH || "scripts/native-player-integration.alert-report.json";
const reportMdPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_MD_PATH || "scripts/native-player-integration.alert-report.md";
const windowDays = Math.max(1, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WINDOW_DAYS || 7));

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
  notified: 0,
  deduped: 0,
  skipped: 0,
  escalated: 0
};
const byLevel = {};
const byReasonCode = {};
const trendByDay = {};

for (const row of events) {
  if (row?.notified) stats.notified += 1;
  if (row?.deduped) stats.deduped += 1;
  if (row?.skipped) stats.skipped += 1;
  if (row?.should_escalate) stats.escalated += 1;

  const level = String(row?.level || "unknown");
  byLevel[level] = (byLevel[level] || 0) + 1;
  const reason = String(row?.reason_code || "UNKNOWN");
  byReasonCode[reason] = (byReasonCode[reason] || 0) + 1;
  const day = String(row?.at || "").slice(0, 10) || "unknown";
  trendByDay[day] = (trendByDay[day] || 0) + 1;
}

const report = {
  generated_at: new Date().toISOString(),
  window_days: windowDays,
  window_start: new Date(windowStart).toISOString(),
  totals: stats,
  by_level: byLevel,
  by_reason_code: byReasonCode,
  trend_by_day: trendByDay
};

writeText(resolve(process.cwd(), reportJsonPath), `${JSON.stringify(report, null, 2)}\n`);

const topReasons = Object.entries(byReasonCode)
  .sort((a, b) => Number(b[1]) - Number(a[1]))
  .slice(0, 8);
const trendLines = Object.entries(trendByDay)
  .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
  .map(([day, count]) => `- ${day}: ${count}`);
const topReasonLines =
  topReasons.length > 0 ? topReasons.map(([code, count]) => `- ${code}: ${count}`) : ["- 无数据"];

const markdown = [
  "## Native Integration Alert Weekly Report",
  "",
  `- Window: last ${windowDays} day(s)`,
  `- Total events: ${stats.total}`,
  `- Notified: ${stats.notified}, Deduped: ${stats.deduped}, Skipped: ${stats.skipped}, Escalated: ${stats.escalated}`,
  "",
  "### Top Reason Codes",
  ...topReasonLines,
  "",
  "### Trend By Day",
  ...(trendLines.length > 0 ? trendLines : ["- 无数据"]),
  ""
].join("\n");

writeText(resolve(process.cwd(), reportMdPath), markdown);
console.log(`[build-native-integration-alert-report] ok: events=${stats.total}, window=${windowDays}d`);
