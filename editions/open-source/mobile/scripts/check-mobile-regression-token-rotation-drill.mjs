import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const drillRequired = String(process.env.MOBILE_REGRESSION_ROTATION_DRILL_REQUIRED || "false").toLowerCase() === "true";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const drillLastAt = String(process.env.MOBILE_REGRESSION_ROTATION_LAST_AT || "");
const drillMaxAgeDays = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_MAX_AGE_DAYS || 30));
const runbookId = String(process.env.MOBILE_REGRESSION_ROTATION_RUNBOOK_ID || "");
const ticketId = String(process.env.MOBILE_REGRESSION_ROTATION_TICKET_ID || "");
const statusPath = process.env.MOBILE_REGRESSION_ROTATION_STATUS_PATH || "scripts/mobile-regression.rotation-drill-status.json";
const historyPath = process.env.MOBILE_REGRESSION_ROTATION_HISTORY_PATH || "scripts/mobile-regression.rotation-history.json";
const historyMaxEntries = Math.max(50, Number(process.env.MOBILE_REGRESSION_ROTATION_HISTORY_MAX_ENTRIES || 500));

function writeStatus(payload) {
  const file = resolve(process.cwd(), statusPath);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(
    file,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        drill_required: drillRequired,
        ...payload
      },
      null,
      2
    )}\n`,
    "utf8"
  );
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

function appendHistory(event) {
  const history = readJsonSafe(historyPath, { events: [] });
  const events = Array.isArray(history?.events) ? history.events : [];
  const next = [
    {
      at: new Date().toISOString(),
      policy_env: policyEnv,
      drill_required: drillRequired,
      ...event
    },
    ...events
  ].slice(0, historyMaxEntries);
  writeJsonSafe(historyPath, { events: next });
}

function parseDateMs(v) {
  if (!v) return Number.NaN;
  const ms = Date.parse(v);
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function fail(reasonCode, message, extra = {}) {
  appendHistory({
    ok: false,
    skipped: false,
    reason_code: reasonCode,
    message,
    ...extra
  });
  writeStatus({
    ok: false,
    reason_code: reasonCode,
    message,
    ...extra
  });
  throw new Error(`[mobile-regression-rotation] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  appendHistory({
    ok: true,
    skipped: reasonCode === "SKIPPED",
    reason_code: reasonCode,
    message,
    ...extra
  });
  writeStatus({
    ok: true,
    reason_code: reasonCode,
    message,
    ...extra
  });
  console.log(`[mobile-regression-rotation] ${reasonCode}: ${message}`);
}

if (!drillLastAt) {
  if (drillRequired) {
    fail("ROTATION_DRILL_MISSING", "rotation drill timestamp missing");
  }
  ok("SKIPPED", "rotation drill timestamp not provided, required=false");
  process.exit(0);
}

const drillLastAtMs = parseDateMs(drillLastAt);
if (Number.isNaN(drillLastAtMs)) {
  fail("ROTATION_DRILL_TIMESTAMP_INVALID", `invalid rotation timestamp: ${drillLastAt}`);
}

const nowMs = Date.now();
const ageDays = Number(((nowMs - drillLastAtMs) / (24 * 60 * 60 * 1000)).toFixed(2));
if (ageDays > drillMaxAgeDays) {
  fail("ROTATION_DRILL_OVERDUE", `rotation drill overdue: ${ageDays}d > ${drillMaxAgeDays}d`, {
    drill_last_at: drillLastAt,
    drill_age_days: ageDays,
    max_age_days: drillMaxAgeDays
  });
}

if (drillRequired && !runbookId) {
  fail("ROTATION_RUNBOOK_MISSING", "rotation runbook id missing");
}
if (drillRequired && !ticketId) {
  fail("ROTATION_TICKET_MISSING", "rotation ticket id missing");
}

ok("OK", "rotation drill check passed", {
  drill_last_at: drillLastAt,
  drill_age_days: ageDays,
  max_age_days: drillMaxAgeDays,
  runbook_id: runbookId || undefined,
  ticket_id: ticketId || undefined
});
