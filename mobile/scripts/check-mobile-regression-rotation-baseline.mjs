import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const required = String(process.env.MOBILE_REGRESSION_ROTATION_BASELINE_CHECK_REQUIRED || "false").toLowerCase() === "true";
const baselinePath = process.env.MOBILE_REGRESSION_ROTATION_BASELINE_PATH || "scripts/mobile-regression-rotation.baseline.json";
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_BASELINE_STATUS_PATH || "scripts/mobile-regression.rotation-baseline-status.json";
const maxAgeDays = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_BASELINE_MAX_AGE_DAYS || 14));

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

function fail(reasonCode, message, extra = {}) {
  writeStatus({
    ok: false,
    reason_code: reasonCode,
    message,
    ...extra
  });
  throw new Error(`[mobile-regression-rotation-baseline] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({
    ok: true,
    reason_code: reasonCode,
    message,
    ...extra
  });
  console.log(`[mobile-regression-rotation-baseline] ${reasonCode}: ${message}`);
}

function parseDateMs(value) {
  const ms = Date.parse(String(value || ""));
  return Number.isNaN(ms) ? Number.NaN : ms;
}

const strictMode = required || policyEnv === "prod";
const baselineFile = resolve(process.cwd(), baselinePath);
if (!existsSync(baselineFile)) {
  if (strictMode) {
    fail("BASELINE_FILE_MISSING", `baseline file missing: ${baselinePath}`);
  }
  ok("SKIPPED", `baseline file missing but strictMode=false: ${baselinePath}`);
  process.exit(0);
}

let baseline;
try {
  baseline = JSON.parse(readFileSync(baselineFile, "utf8"));
} catch {
  fail("BASELINE_PARSE_FAILED", "failed to parse baseline json");
}

const version = String(baseline?.version || "");
const frozenAt = String(baseline?.frozen_at || "");
const owner = String(baseline?.owner || "");
const approvers = Array.isArray(baseline?.approvers) ? baseline.approvers.filter((x) => !!String(x || "").trim()) : [];
const scope = baseline?.scope || {};
const rolloutWindow = baseline?.rollout_window || {};
const startAt = String(rolloutWindow?.start_at || "");
const endAt = String(rolloutWindow?.end_at || "");

if (!version) fail("BASELINE_VERSION_MISSING", "baseline.version is required");
if (!owner) fail("BASELINE_OWNER_MISSING", "baseline.owner is required");
if (approvers.length < 2) fail("BASELINE_APPROVERS_INSUFFICIENT", "baseline.approvers requires at least 2 approvers");

const frozenAtMs = parseDateMs(frozenAt);
if (Number.isNaN(frozenAtMs)) fail("BASELINE_FROZEN_AT_INVALID", `invalid baseline.frozen_at: ${frozenAt}`);
const baselineAgeDays = Number(((Date.now() - frozenAtMs) / (24 * 60 * 60 * 1000)).toFixed(2));
if (baselineAgeDays > maxAgeDays) {
  fail("BASELINE_TOO_OLD", `baseline too old: ${baselineAgeDays}d > ${maxAgeDays}d`, {
    frozen_at: frozenAt,
    baseline_age_days: baselineAgeDays,
    max_age_days: maxAgeDays
  });
}

const requiredScopeFlags = ["publish_signature", "alert_signature", "verify_replay", "key_rotation"];
for (const flag of requiredScopeFlags) {
  if (scope?.[flag] !== true) {
    fail("BASELINE_SCOPE_INCOMPLETE", `baseline.scope.${flag} must be true`);
  }
}

const startAtMs = parseDateMs(startAt);
const endAtMs = parseDateMs(endAt);
if (Number.isNaN(startAtMs) || Number.isNaN(endAtMs)) {
  fail("BASELINE_ROLLOUT_WINDOW_INVALID", "invalid rollout_window start_at/end_at");
}
if (endAtMs <= startAtMs) {
  fail("BASELINE_ROLLOUT_WINDOW_ORDER_INVALID", "rollout_window.end_at must be later than start_at");
}

ok("OK", "baseline freeze check passed", {
  version,
  owner,
  approver_count: approvers.length,
  frozen_at: frozenAt,
  baseline_age_days: baselineAgeDays,
  max_age_days: maxAgeDays,
  rollout_window_start_at: startAt,
  rollout_window_end_at: endAt
});
