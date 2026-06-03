import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const required = String(process.env.MOBILE_REGRESSION_ROTATION_EMERGENCY_DRILL_REQUIRED || "false").toLowerCase() === "true";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const lastAt = String(process.env.MOBILE_REGRESSION_ROTATION_EMERGENCY_DRILL_LAST_AT || "");
const maxAgeDays = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_EMERGENCY_DRILL_MAX_AGE_DAYS || 30));
const runbookId = String(process.env.MOBILE_REGRESSION_ROTATION_EMERGENCY_DRILL_RUNBOOK_ID || "");
const ticketId = String(process.env.MOBILE_REGRESSION_ROTATION_EMERGENCY_DRILL_TICKET_ID || "");
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_EMERGENCY_DRILL_STATUS_PATH || "scripts/mobile-regression.rotation-emergency-drill-status.json";

function writeStatus(payload) {
  const file = resolve(process.cwd(), statusPath);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(
    file,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        required,
        policy_env: policyEnv,
        ...payload
      },
      null,
      2
    )}\n`,
    "utf8"
  );
}

function parseDateMs(value) {
  if (!value) return Number.NaN;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function fail(reasonCode, message, extra = {}) {
  writeStatus({
    ok: false,
    reason_code: reasonCode,
    message,
    ...extra
  });
  throw new Error(`[mobile-regression-rotation-emergency-drill] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({
    ok: true,
    reason_code: reasonCode,
    message,
    ...extra
  });
  console.log(`[mobile-regression-rotation-emergency-drill] ${reasonCode}: ${message}`);
}

const strictMode = required || policyEnv === "prod";
if (!lastAt) {
  if (strictMode) {
    fail("EMERGENCY_DRILL_MISSING", "emergency drill timestamp missing");
  }
  ok("SKIPPED", "emergency drill timestamp not provided, strictMode=false");
  process.exit(0);
}

const lastAtMs = parseDateMs(lastAt);
if (Number.isNaN(lastAtMs)) {
  fail("EMERGENCY_DRILL_TIMESTAMP_INVALID", `invalid emergency drill timestamp: ${lastAt}`);
}

const ageDays = Number(((Date.now() - lastAtMs) / (24 * 60 * 60 * 1000)).toFixed(2));
if (ageDays > maxAgeDays) {
  fail("EMERGENCY_DRILL_OVERDUE", `emergency drill overdue: ${ageDays}d > ${maxAgeDays}d`, {
    emergency_drill_last_at: lastAt,
    emergency_drill_age_days: ageDays,
    max_age_days: maxAgeDays
  });
}

if (strictMode && !runbookId) {
  fail("EMERGENCY_DRILL_RUNBOOK_MISSING", "emergency drill runbook id missing");
}
if (strictMode && !ticketId) {
  fail("EMERGENCY_DRILL_TICKET_MISSING", "emergency drill ticket id missing");
}

ok("OK", "emergency drill check passed", {
  emergency_drill_last_at: lastAt,
  emergency_drill_age_days: ageDays,
  max_age_days: maxAgeDays,
  runbook_id: runbookId || undefined,
  ticket_id: ticketId || undefined
});
