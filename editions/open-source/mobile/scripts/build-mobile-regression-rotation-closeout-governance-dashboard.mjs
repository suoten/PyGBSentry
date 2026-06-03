import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const windowDays = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WINDOW_DAYS || 14));
const alertStatusPath =
  process.env.MOBILE_REGRESSION_ROTATION_ALERT_STATUS_PATH || "scripts/mobile-regression.rotation-alert-status.json";
const reviewStatusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_REMINDER_STATUS_PATH ||
  "scripts/mobile-regression.rotation-closeout-governance-review-reminder-status.json";
const baselineStatusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_STATUS_PATH ||
  "scripts/mobile-regression.rotation-closeout-governance-baseline-status.json";
const alertHistoryPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_ALERT_HISTORY_PATH ||
  "scripts/mobile-regression.rotation-closeout-alert-history.json";
const reviewHistoryPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_REVIEW_HISTORY_PATH ||
  "scripts/mobile-regression.rotation-closeout-review-history.json";
const dashboardJsonPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_JSON_PATH ||
  "scripts/mobile-regression.rotation-closeout-dashboard.json";
const dashboardMdPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_MD_PATH ||
  "scripts/mobile-regression.rotation-closeout-dashboard.md";

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

function normalizeTsMs(v) {
  const ms = Date.parse(String(v || ""));
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function readEvents(path) {
  const data = readJsonSafe(path, { events: [] });
  const events = Array.isArray(data?.events) ? data.events : [];
  return events
    .filter((x) => !Number.isNaN(normalizeTsMs(x?.at)))
    .sort((a, b) => normalizeTsMs(a?.at) - normalizeTsMs(b?.at));
}

function appendEvent(historyPath, next) {
  if (!next || Number.isNaN(normalizeTsMs(next?.at))) return;
  const history = readJsonSafe(historyPath, { events: [] });
  const events = Array.isArray(history?.events) ? history.events : [];
  const exists = events.some((x) => String(x?.at || "") === String(next?.at || "") && String(x?.reason_code || "") === String(next?.reason_code || ""));
  if (!exists) {
    events.push(next);
  }
  writeText(historyPath, `${JSON.stringify({ events }, null, 2)}\n`);
}

function pickAlertEvent(status) {
  if (!status || !status.at) return null;
  return {
    at: status.at,
    policy_env: String(status.policy_env || policyEnv || "unknown"),
    reason_code: String(status.alert_reason_code || status.reason_code || "UNKNOWN"),
    status_reason_code: String(status.reason_code || "UNKNOWN"),
    level: String(status.level || "unknown"),
    closeout_reason_code: String(status.closeout_reason_code || ""),
    mute_scope: String(status.mute_scope || ""),
    deduped: status.deduped === true,
    skipped: status.skipped === true
  };
}

function pickReviewEvent(status) {
  if (!status || !status.at) return null;
  return {
    at: status.at,
    policy_env: String(status.policy_env || policyEnv || "unknown"),
    reason_code: String(status.reason_code || "UNKNOWN"),
    review_due_at: String(status.review_due_at || ""),
    review_days_until_due: Number(status.review_days_until_due || 0),
    owner: String(status.owner || "")
  };
}

function toWindowEvents(events, windowStartMs) {
  return events.filter((x) => normalizeTsMs(x?.at) >= windowStartMs);
}

function inc(map, key) {
  const k = String(key || "UNKNOWN");
  map[k] = (map[k] || 0) + 1;
}

const alertStatus = readJsonSafe(alertStatusPath, null);
const reviewStatus = readJsonSafe(reviewStatusPath, null);
const baselineStatus = readJsonSafe(baselineStatusPath, null);

appendEvent(alertHistoryPath, pickAlertEvent(alertStatus));
appendEvent(reviewHistoryPath, pickReviewEvent(reviewStatus));

const alertEventsAll = readEvents(alertHistoryPath);
const reviewEventsAll = readEvents(reviewHistoryPath);
const windowStartMs = Date.now() - windowDays * 24 * 60 * 60 * 1000;
const alertEvents = toWindowEvents(alertEventsAll, windowStartMs);
const reviewEvents = toWindowEvents(reviewEventsAll, windowStartMs);

const alertByEnv = {};
const alertByReason = {};
const alertByCloseoutReason = {};
const reviewByReason = {};
const reviewByEnv = {};

for (const e of alertEvents) {
  inc(alertByEnv, e.policy_env || "unknown");
  inc(alertByReason, e.reason_code || "UNKNOWN");
  if (e.closeout_reason_code) {
    inc(alertByCloseoutReason, e.closeout_reason_code);
  }
}
for (const e of reviewEvents) {
  inc(reviewByEnv, e.policy_env || "unknown");
  inc(reviewByReason, e.reason_code || "UNKNOWN");
}

const latestReview = reviewEventsAll.length > 0 ? reviewEventsAll[reviewEventsAll.length - 1] : null;
const latestAlert = alertEventsAll.length > 0 ? alertEventsAll[alertEventsAll.length - 1] : null;

const dashboard = {
  generated_at: new Date().toISOString(),
  window_days: windowDays,
  policy_env: policyEnv,
  sources: {
    alert_status_path: alertStatusPath,
    review_status_path: reviewStatusPath,
    baseline_status_path: baselineStatusPath,
    alert_history_path: alertHistoryPath,
    review_history_path: reviewHistoryPath
  },
  latest: {
    alert: latestAlert,
    review: latestReview,
    baseline: baselineStatus
  },
  trends: {
    alerts: {
      total: alertEvents.length,
      by_env: alertByEnv,
      by_reason_code: alertByReason,
      by_closeout_reason_code: alertByCloseoutReason
    },
    reviews: {
      total: reviewEvents.length,
      by_env: reviewByEnv,
      by_reason_code: reviewByReason
    }
  }
};

writeText(dashboardJsonPath, `${JSON.stringify(dashboard, null, 2)}\n`);

const alertReasonLines = Object.entries(alertByReason)
  .sort((a, b) => Number(b[1]) - Number(a[1]))
  .map(([k, v]) => `- ${k}: ${v}`);
const reviewReasonLines = Object.entries(reviewByReason)
  .sort((a, b) => Number(b[1]) - Number(a[1]))
  .map(([k, v]) => `- ${k}: ${v}`);
const closeoutReasonLines = Object.entries(alertByCloseoutReason)
  .sort((a, b) => Number(b[1]) - Number(a[1]))
  .map(([k, v]) => `- ${k}: ${v}`);

const markdown = [
  "## Mobile Regression Rotation Closeout Governance Dashboard",
  "",
  `- Window: last ${windowDays} day(s)`,
  `- Policy env: ${policyEnv}`,
  `- Alerts in window: ${alertEvents.length}`,
  `- Reviews in window: ${reviewEvents.length}`,
  "",
  "### Alert Reason Trend",
  ...(alertReasonLines.length > 0 ? alertReasonLines : ["- no data"]),
  "",
  "### Closeout Reason Trend",
  ...(closeoutReasonLines.length > 0 ? closeoutReasonLines : ["- no data"]),
  "",
  "### Review Reminder Trend",
  ...(reviewReasonLines.length > 0 ? reviewReasonLines : ["- no data"]),
  "",
  "### Latest Snapshot",
  latestAlert
    ? `- latest_alert: at=${latestAlert.at}, reason=${latestAlert.reason_code}, closeout_reason=${latestAlert.closeout_reason_code || "n/a"}`
    : "- latest_alert: no data",
  latestReview
    ? `- latest_review: at=${latestReview.at}, reason=${latestReview.reason_code}, due_at=${latestReview.review_due_at || "n/a"}, days_until_due=${latestReview.review_days_until_due}`
    : "- latest_review: no data",
  baselineStatus
    ? `- latest_baseline: reason=${String(baselineStatus.reason_code || "UNKNOWN")}, review_age_days=${String(baselineStatus.review_age_days || "n/a")}`
    : "- latest_baseline: no data",
  ""
].join("\n");

writeText(dashboardMdPath, markdown);
console.log(
  `[build-mobile-regression-rotation-closeout-governance-dashboard] ok: alerts=${alertEvents.length}, reviews=${reviewEvents.length}, window=${windowDays}d`
);
