import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const required =
  String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_REQUIRED || "false").toLowerCase() === "true";
const baselinePath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_PATH ||
  "scripts/mobile-regression-rotation.closeout-governance.baseline.json";
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_STATUS_PATH ||
  "scripts/mobile-regression.rotation-closeout-governance-baseline-status.json";
const maxReviewAgeDays = Math.max(
  1,
  Number(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_MAX_REVIEW_AGE_DAYS || 92)
);

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
  throw new Error(`[mobile-regression-rotation-closeout-governance-baseline] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({
    ok: true,
    reason_code: reasonCode,
    message,
    ...extra
  });
  console.log(`[mobile-regression-rotation-closeout-governance-baseline] ${reasonCode}: ${message}`);
}

function parseDateMs(value) {
  const ms = Date.parse(String(value || ""));
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function toArray(value) {
  return Array.isArray(value) ? value.map((x) => String(x || "").trim()).filter((x) => !!x) : [];
}

function toDedupeMap(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  for (const [k, v] of Object.entries(value)) {
    const code = String(k || "").trim().toUpperCase();
    const sec = Number(v);
    if (!code || Number.isNaN(sec) || sec < 0) continue;
    out[code] = sec;
  }
  return out;
}

const strictMode = required || policyEnv === "prod";
const baselineFile = resolve(process.cwd(), baselinePath);
if (!existsSync(baselineFile)) {
  if (strictMode) {
    fail("CLOSEOUT_GOV_BASELINE_FILE_MISSING", `governance baseline file missing: ${baselinePath}`);
  }
  ok("SKIPPED", `governance baseline file missing but strictMode=false: ${baselinePath}`);
  process.exit(0);
}

let baseline;
try {
  baseline = JSON.parse(readFileSync(baselineFile, "utf8"));
} catch {
  fail("CLOSEOUT_GOV_BASELINE_PARSE_FAILED", "failed to parse governance baseline json");
}

const version = String(baseline?.version || "");
const owner = String(baseline?.owner || "");
const approvers = toArray(baseline?.approvers);
const reviewCycleDays = Math.max(1, Number(baseline?.review_cycle_days || 0));
const lastReviewedAt = String(baseline?.last_reviewed_at || "");
const envDefaults = baseline?.env_defaults || {};
const changeControl = baseline?.change_control || {};

if (!version) fail("CLOSEOUT_GOV_BASELINE_VERSION_MISSING", "baseline.version is required");
if (!owner) fail("CLOSEOUT_GOV_BASELINE_OWNER_MISSING", "baseline.owner is required");
if (approvers.length < 2) fail("CLOSEOUT_GOV_BASELINE_APPROVERS_INSUFFICIENT", "baseline.approvers requires at least 2 approvers");
if (!Number.isFinite(reviewCycleDays) || reviewCycleDays <= 0) {
  fail("CLOSEOUT_GOV_BASELINE_REVIEW_CYCLE_INVALID", "baseline.review_cycle_days must be a positive number");
}
if (reviewCycleDays > 120) {
  fail("CLOSEOUT_GOV_BASELINE_REVIEW_CYCLE_TOO_LONG", "baseline.review_cycle_days should be <= 120");
}

const lastReviewedAtMs = parseDateMs(lastReviewedAt);
if (Number.isNaN(lastReviewedAtMs)) {
  fail("CLOSEOUT_GOV_BASELINE_LAST_REVIEW_INVALID", `invalid baseline.last_reviewed_at: ${lastReviewedAt}`);
}
const reviewAgeDays = Number(((Date.now() - lastReviewedAtMs) / (24 * 60 * 60 * 1000)).toFixed(2));
if (reviewAgeDays > maxReviewAgeDays) {
  fail("CLOSEOUT_GOV_BASELINE_REVIEW_EXPIRED", `baseline review expired: ${reviewAgeDays}d > ${maxReviewAgeDays}d`, {
    last_reviewed_at: lastReviewedAt,
    review_age_days: reviewAgeDays,
    max_review_age_days: maxReviewAgeDays
  });
}

const approverGroup = String(changeControl?.approver_group || "");
const rollbackRunbookId = String(changeControl?.rollback_runbook_id || "");
const rollbackChecklistId = String(changeControl?.rollback_checklist_id || "");
if (!approverGroup) fail("CLOSEOUT_GOV_CHANGE_CONTROL_APPROVER_GROUP_MISSING", "change_control.approver_group is required");
if (!rollbackRunbookId) fail("CLOSEOUT_GOV_CHANGE_CONTROL_ROLLBACK_RUNBOOK_MISSING", "change_control.rollback_runbook_id is required");
if (!rollbackChecklistId) fail("CLOSEOUT_GOV_CHANGE_CONTROL_ROLLBACK_CHECKLIST_MISSING", "change_control.rollback_checklist_id is required");

const requiredEnvs = ["prod", "canary"];
for (const env of requiredEnvs) {
  const cfg = envDefaults?.[env];
  if (!cfg || typeof cfg !== "object") {
    fail("CLOSEOUT_GOV_ENV_DEFAULT_MISSING", `baseline.env_defaults.${env} is required`);
  }
  const riskReasonCodes = toArray(cfg?.risk_reason_codes).map((x) => x.toUpperCase());
  const muteReasonCodes = toArray(cfg?.mute_reason_codes).map((x) => x.toUpperCase());
  const dedupeMap = toDedupeMap(cfg?.dedupe_window_sec_map);
  if (riskReasonCodes.length === 0) {
    fail("CLOSEOUT_GOV_RISK_REASON_CODES_EMPTY", `baseline.env_defaults.${env}.risk_reason_codes cannot be empty`);
  }
  if (Object.keys(dedupeMap).length === 0) {
    fail("CLOSEOUT_GOV_DEDUPE_MAP_EMPTY", `baseline.env_defaults.${env}.dedupe_window_sec_map cannot be empty`);
  }
  for (const code of muteReasonCodes) {
    if (!riskReasonCodes.includes(code)) {
      fail("CLOSEOUT_GOV_MUTE_NOT_IN_RISK", `${env} mute reason_code not in risk_reason_codes: ${code}`);
    }
  }
  for (const code of Object.keys(dedupeMap)) {
    if (!riskReasonCodes.includes(code)) {
      fail("CLOSEOUT_GOV_DEDUPE_NOT_IN_RISK", `${env} dedupe reason_code not in risk_reason_codes: ${code}`);
    }
  }
  if (env === "prod") {
    const mustHave = ["CLOSEOUT_SIGNOFF_OUT_OF_WINDOW", "CLOSEOUT_WINDOW_INVALID"];
    for (const code of mustHave) {
      if (!riskReasonCodes.includes(code)) {
        fail("CLOSEOUT_GOV_PROD_RISK_INCOMPLETE", `prod risk_reason_codes must contain ${code}`);
      }
      if (!Number.isFinite(dedupeMap[code])) {
        fail("CLOSEOUT_GOV_PROD_DEDUPE_INCOMPLETE", `prod dedupe_window_sec_map must contain ${code}`);
      }
    }
  }
}

ok("OK", "closeout governance baseline check passed", {
  version,
  owner,
  approver_count: approvers.length,
  review_cycle_days: reviewCycleDays,
  review_age_days: reviewAgeDays,
  max_review_age_days: maxReviewAgeDays,
  envs: requiredEnvs
});
