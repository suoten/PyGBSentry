import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const required = String(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_REQUIRED || "false").toLowerCase() === "true";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_STATUS_PATH ||
  "scripts/mobile-regression.rotation-verify-alert-stress-status.json";

const lastAt = String(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_LAST_AT || "");
const maxAgeDays = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_MAX_AGE_DAYS || 30));
const runbookId = String(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_RUNBOOK_ID || "");
const ticketId = String(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_TICKET_ID || "");

const errorCount = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_ERROR_COUNT || 0));
const warningCount = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_WARNING_COUNT || 0));
const infoCount = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_INFO_COUNT || 0));
const minErrorCount = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_MIN_ERROR_COUNT || 1));
const minWarningCount = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_ALERT_STRESS_MIN_WARNING_COUNT || 1));

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
  writeStatus({ ok: false, reason_code: reasonCode, message, ...extra });
  throw new Error(`[mobile-regression-rotation-verify-alert-stress] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({ ok: true, reason_code: reasonCode, message, ...extra });
  console.log(`[mobile-regression-rotation-verify-alert-stress] ${reasonCode}: ${message}`);
}

const strictMode = required || policyEnv === "prod";
if (!lastAt) {
  if (strictMode) {
    fail("VERIFY_ALERT_STRESS_MISSING", "verify alert stress timestamp missing");
  }
  ok("SKIPPED", "verify alert stress timestamp not provided, strictMode=false");
  process.exit(0);
}

const lastAtMs = parseDateMs(lastAt);
if (Number.isNaN(lastAtMs)) {
  fail("VERIFY_ALERT_STRESS_TIMESTAMP_INVALID", `invalid stress timestamp: ${lastAt}`);
}

const ageDays = Number(((Date.now() - lastAtMs) / (24 * 60 * 60 * 1000)).toFixed(2));
if (ageDays > maxAgeDays) {
  fail("VERIFY_ALERT_STRESS_OVERDUE", `verify alert stress overdue: ${ageDays}d > ${maxAgeDays}d`, {
    stress_last_at: lastAt,
    stress_age_days: ageDays,
    max_age_days: maxAgeDays
  });
}

if (strictMode && !runbookId) {
  fail("VERIFY_ALERT_STRESS_RUNBOOK_MISSING", "verify alert stress runbook id missing");
}
if (strictMode && !ticketId) {
  fail("VERIFY_ALERT_STRESS_TICKET_MISSING", "verify alert stress ticket id missing");
}
if (errorCount < minErrorCount) {
  fail("VERIFY_ALERT_STRESS_ERROR_COUNT_LOW", `error level stress count too low: ${errorCount} < ${minErrorCount}`);
}
if (warningCount < minWarningCount) {
  fail("VERIFY_ALERT_STRESS_WARNING_COUNT_LOW", `warning level stress count too low: ${warningCount} < ${minWarningCount}`);
}

ok("OK", "verify alert stress check passed", {
  stress_last_at: lastAt,
  stress_age_days: ageDays,
  max_age_days: maxAgeDays,
  error_count: errorCount,
  warning_count: warningCount,
  info_count: infoCount,
  min_error_count: minErrorCount,
  min_warning_count: minWarningCount,
  runbook_id: runbookId || undefined,
  ticket_id: ticketId || undefined
});
