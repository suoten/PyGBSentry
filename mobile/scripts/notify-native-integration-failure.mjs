import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const webhookUrl = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_WEBHOOK_URL || "";
const webhookToken = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_WEBHOOK_TOKEN || "";
const webhookUrlError = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_WEBHOOK_URL_ERROR || "";
const webhookUrlWarning = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_WEBHOOK_URL_WARNING || "";
const webhookUrlInfo = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_WEBHOOK_URL_INFO || "";
const escalationWebhookUrl = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_ESCALATION_WEBHOOK_URL || "";
const statusPath = process.env.NATIVE_PLAYER_INTEGRATION_FETCH_STATUS_PATH || "scripts/native-player-integration.fetch-status.json";
const required = String(process.env.NATIVE_PLAYER_INTEGRATION_REQUIRED || "false").toLowerCase() === "true";
const fetchOutcome = String(process.env.NATIVE_PLAYER_FETCH_OUTCOME || "").toLowerCase();
const gateOutcome = String(process.env.NATIVE_PLAYER_GATE_OUTCOME || "").toLowerCase();
const muteReasonCodes = String(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_MUTE_REASON_CODES || "")
  .split(",")
  .map((x) => x.trim().toUpperCase())
  .filter((x) => !!x);
const levelOverridesRaw = String(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_LEVEL_OVERRIDES || "");
const escalateReasonCodes = String(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_ESCALATE_REASON_CODES || "")
  .split(",")
  .map((x) => x.trim().toUpperCase())
  .filter((x) => !!x);
const notifyRetries = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_RETRIES || 1));
const notifyRetryDelayMs = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_RETRY_DELAY_MS || 1000));
const dedupeWindowSec = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_DEDUPE_WINDOW_SEC || 600));
const dedupeStatePath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_DEDUPE_STATE_PATH || "scripts/native-player-integration.alert-dedupe.json";
const alertSummaryPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_SUMMARY_PATH || "scripts/native-player-integration.alert-summary.json";
const alertHistoryPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_HISTORY_PATH || "scripts/native-player-integration.alert-history.json";
const alertHistoryMaxEntries = Math.max(50, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_HISTORY_MAX_ENTRIES || 500));
const jobUrl = String(process.env.GITHUB_SERVER_URL || "") && String(process.env.GITHUB_REPOSITORY || "") && String(process.env.GITHUB_RUN_ID || "")
  ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
  : "";

function log(message) {
  console.log(`[notify-native-integration-failure] ${message}`);
}

function shouldNotify() {
  if (!required) return false;
  return fetchOutcome === "failure" || gateOutcome === "failure";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readJsonSafe(path, fallback) {
  const file = resolve(process.cwd(), path);
  if (!existsSync(file)) return fallback;
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonSafe(path, data) {
  const file = resolve(process.cwd(), path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function appendAlertHistory(event) {
  const history = readJsonSafe(alertHistoryPath, { events: [] });
  const events = Array.isArray(history?.events) ? history.events : [];
  const next = [
    {
      at: new Date().toISOString(),
      ...event
    },
    ...events
  ].slice(0, alertHistoryMaxEntries);
  writeJsonSafe(alertHistoryPath, { events: next });
}

function parseLevelOverrides() {
  const out = {};
  if (!levelOverridesRaw) return out;
  const rows = levelOverridesRaw.split(",").map((x) => x.trim()).filter((x) => !!x);
  for (const row of rows) {
    const [k, v] = row.split("=").map((x) => String(x || "").trim());
    if (!k || !v) continue;
    const upperK = k.toUpperCase();
    const lowerV = v.toLowerCase();
    if (lowerV === "error" || lowerV === "warning" || lowerV === "info") {
      out[upperK] = lowerV;
    }
  }
  return out;
}

function defaultLevelByReason(reasonCode) {
  const code = String(reasonCode || "").toUpperCase();
  if (code === "OK") return "info";
  if (code === "API_URL_MISSING" || code === "SOURCE_FILE_NOT_FOUND" || code === "INVALID_JSON") return "warning";
  return "error";
}

if (!shouldNotify()) {
  log("skip: gate not failed or not required");
  appendAlertHistory({
    notified: false,
    deduped: false,
    skipped: true,
    skip_reason: "gate_not_failed_or_not_required",
    required_gate: required,
    fetch_outcome: fetchOutcome || "unknown",
    gate_outcome: gateOutcome || "unknown"
  });
  process.exit(0);
}

let status = null;
const statusFile = resolve(process.cwd(), statusPath);
if (existsSync(statusFile)) {
  try {
    const rawStatus = readFileSync(statusFile, "utf8").replace(/^\uFEFF/, "");
    status = JSON.parse(rawStatus);
  } catch {
    status = { reason_code: "STATUS_PARSE_FAILED", message: "failed to parse status json" };
  }
}

const reasonCode = String((status && status.reason_code) || "UNKNOWN").toUpperCase();
if (muteReasonCodes.includes(reasonCode)) {
  log(`skip: reason_code muted (${reasonCode})`);
  writeJsonSafe(alertSummaryPath, {
    at: new Date().toISOString(),
    notified: false,
    deduped: false,
    skipped: true,
    skip_reason: "reason_code_muted",
    reason_code: reasonCode
  });
  appendAlertHistory({
    notified: false,
    deduped: false,
    skipped: true,
    skip_reason: "reason_code_muted",
    reason_code: reasonCode,
    required_gate: required,
    fetch_outcome: fetchOutcome || "unknown",
    gate_outcome: gateOutcome || "unknown"
  });
  process.exit(0);
}

const levelOverrides = parseLevelOverrides();
const level = levelOverrides[reasonCode] || defaultLevelByReason(reasonCode);
const routedWebhookUrl = level === "error" ? webhookUrlError || webhookUrl : level === "warning" ? webhookUrlWarning || webhookUrl : webhookUrlInfo || webhookUrl;
const shouldEscalate = (fetchOutcome === "failure" && gateOutcome === "failure") || escalateReasonCodes.includes(reasonCode);
const webhookTargets = [routedWebhookUrl, shouldEscalate ? escalationWebhookUrl : ""].filter((x, i, arr) => !!x && arr.indexOf(x) === i);

const dedupeKey = `${reasonCode}|${String(process.env.GITHUB_REF || "local")}|${level}`;
const nowMs = Date.now();
const dedupeState = readJsonSafe(dedupeStatePath, { records: {} });
const records = (dedupeState && typeof dedupeState === "object" && dedupeState.records && typeof dedupeState.records === "object")
  ? dedupeState.records
  : {};
const lastSentMs = Number(records[dedupeKey] || 0);
const inDedupeWindow = dedupeWindowSec > 0 && lastSentMs > 0 && nowMs - lastSentMs < dedupeWindowSec * 1000;
if (inDedupeWindow) {
  log(`skip: dedupe window hit key=${dedupeKey}`);
  writeJsonSafe(alertSummaryPath, {
    at: new Date().toISOString(),
    notified: false,
    deduped: true,
    dedupe_key: dedupeKey,
    dedupe_window_sec: dedupeWindowSec,
    level,
    reason_code: reasonCode,
    fetch_outcome: fetchOutcome || "unknown",
    gate_outcome: gateOutcome || "unknown",
    targets: webhookTargets.length
  });
  appendAlertHistory({
    notified: false,
    deduped: true,
    skipped: true,
    skip_reason: "dedupe_window",
    dedupe_key: dedupeKey,
    dedupe_window_sec: dedupeWindowSec,
    level,
    reason_code: reasonCode,
    required_gate: required,
    fetch_outcome: fetchOutcome || "unknown",
    gate_outcome: gateOutcome || "unknown",
    targets: webhookTargets.length
  });
  process.exit(0);
}

if (webhookTargets.length === 0) {
  log("skip: webhook url not configured");
  writeJsonSafe(alertSummaryPath, {
    at: new Date().toISOString(),
    notified: false,
    deduped: false,
    level,
    reason_code: reasonCode,
    fetch_outcome: fetchOutcome || "unknown",
    gate_outcome: gateOutcome || "unknown",
    targets: 0,
    message: "webhook url not configured"
  });
  appendAlertHistory({
    notified: false,
    deduped: false,
    skipped: true,
    skip_reason: "webhook_not_configured",
    level,
    reason_code: reasonCode,
    required_gate: required,
    fetch_outcome: fetchOutcome || "unknown",
    gate_outcome: gateOutcome || "unknown",
    targets: 0
  });
  process.exit(0);
}

const payload = {
  type: "native_player_integration_gate_failure",
  level,
  reason_code: reasonCode,
  required_gate: required,
  fetch_outcome: fetchOutcome || "unknown",
  gate_outcome: gateOutcome || "unknown",
  repository: process.env.GITHUB_REPOSITORY || "",
  branch: process.env.GITHUB_REF || "",
  actor: process.env.GITHUB_ACTOR || "",
  run_id: process.env.GITHUB_RUN_ID || "",
  run_url: jobUrl,
  mute_reason_codes: muteReasonCodes,
  level_overrides: levelOverrides,
  escalate_reason_codes: escalateReasonCodes,
  should_escalate: shouldEscalate,
  routed_targets_count: webhookTargets.length,
  status: status || { reason_code: "STATUS_FILE_MISSING", message: "fetch status file not found" }
};

const headers = { "Content-Type": "application/json" };
if (webhookToken) {
  headers.Authorization = `Bearer ${webhookToken}`;
}

for (const target of webhookTargets) {
  let sent = false;
  for (let attempt = 1; attempt <= notifyRetries + 1; attempt += 1) {
    const res = await fetch(target, {
      method: "POST",
      headers,
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      sent = true;
      break;
    }
    if (attempt <= notifyRetries) {
      await sleep(notifyRetryDelayMs);
      continue;
    }
    throw new Error(`webhook notify failed: http ${res.status} target=${target}`);
  }
  if (sent) {
    log(`alert sent to ${target}`);
  }
}

records[dedupeKey] = nowMs;
writeJsonSafe(dedupeStatePath, {
  records
});
writeJsonSafe(alertSummaryPath, {
  at: new Date().toISOString(),
  notified: true,
  deduped: false,
  dedupe_key: dedupeKey,
  dedupe_window_sec: dedupeWindowSec,
  level,
  reason_code: reasonCode,
  fetch_outcome: fetchOutcome || "unknown",
  gate_outcome: gateOutcome || "unknown",
  targets: webhookTargets.length,
  should_escalate: shouldEscalate
});
appendAlertHistory({
  notified: true,
  deduped: false,
  skipped: false,
  dedupe_key: dedupeKey,
  dedupe_window_sec: dedupeWindowSec,
  level,
  reason_code: reasonCode,
  required_gate: required,
  fetch_outcome: fetchOutcome || "unknown",
  gate_outcome: gateOutcome || "unknown",
  targets: webhookTargets.length,
  should_escalate: shouldEscalate
});

log("alert done");
