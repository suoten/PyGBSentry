import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const required =
  String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_REMINDER_REQUIRED || "false").toLowerCase() ===
  "true";
const baselinePath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_PATH ||
  "scripts/mobile-regression-rotation.closeout-governance.baseline.json";
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_REMINDER_STATUS_PATH ||
  "scripts/mobile-regression.rotation-closeout-governance-review-reminder-status.json";
const dueSoonDays = Math.max(
  1,
  Number(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_DUE_SOON_DAYS || 14)
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
  throw new Error(`[mobile-regression-rotation-closeout-governance-review] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({
    ok: true,
    reason_code: reasonCode,
    message,
    ...extra
  });
  console.log(`[mobile-regression-rotation-closeout-governance-review] ${reasonCode}: ${message}`);
}

function parseDateMs(value) {
  const ms = Date.parse(String(value || ""));
  return Number.isNaN(ms) ? Number.NaN : ms;
}

const baselineFile = resolve(process.cwd(), baselinePath);
if (!existsSync(baselineFile)) {
  if (required) {
    fail("CLOSEOUT_GOV_REVIEW_BASELINE_FILE_MISSING", `governance baseline file missing: ${baselinePath}`);
  }
  ok("SKIPPED", `governance baseline file missing, required=false: ${baselinePath}`);
  process.exit(0);
}

let baseline;
try {
  baseline = JSON.parse(readFileSync(baselineFile, "utf8"));
} catch {
  fail("CLOSEOUT_GOV_REVIEW_BASELINE_PARSE_FAILED", "failed to parse governance baseline json");
}

const reviewCycleDays = Math.max(1, Number(baseline?.review_cycle_days || 0));
const lastReviewedAt = String(baseline?.last_reviewed_at || "");
const owner = String(baseline?.owner || "");
if (!lastReviewedAt) {
  fail("CLOSEOUT_GOV_REVIEW_LAST_REVIEWED_AT_MISSING", "baseline.last_reviewed_at is required");
}
const lastReviewedAtMs = parseDateMs(lastReviewedAt);
if (Number.isNaN(lastReviewedAtMs)) {
  fail("CLOSEOUT_GOV_REVIEW_LAST_REVIEWED_AT_INVALID", `invalid baseline.last_reviewed_at: ${lastReviewedAt}`);
}
if (!Number.isFinite(reviewCycleDays) || reviewCycleDays <= 0) {
  fail("CLOSEOUT_GOV_REVIEW_CYCLE_INVALID", "baseline.review_cycle_days must be a positive number");
}

const dueAtMs = lastReviewedAtMs + reviewCycleDays * 24 * 60 * 60 * 1000;
const nowMs = Date.now();
const daysUntilDue = Number(((dueAtMs - nowMs) / (24 * 60 * 60 * 1000)).toFixed(2));
const reviewAgeDays = Number(((nowMs - lastReviewedAtMs) / (24 * 60 * 60 * 1000)).toFixed(2));
const dueAt = new Date(dueAtMs).toISOString();

if (daysUntilDue < 0) {
  const payload = {
    owner: owner || undefined,
    review_cycle_days: reviewCycleDays,
    review_age_days: reviewAgeDays,
    review_due_at: dueAt,
    review_days_until_due: daysUntilDue,
    due_soon_days: dueSoonDays,
    recommended_action: "run quarterly governance review and update baseline.last_reviewed_at"
  };
  if (required) {
    fail("CLOSEOUT_GOV_REVIEW_OVERDUE", `governance review overdue by ${Math.abs(daysUntilDue)} day(s)`, payload);
  }
  ok("CLOSEOUT_GOV_REVIEW_OVERDUE", "governance review overdue (non-blocking)", payload);
  process.exit(0);
}

if (daysUntilDue <= dueSoonDays) {
  ok("CLOSEOUT_GOV_REVIEW_DUE_SOON", "governance review due soon", {
    owner: owner || undefined,
    review_cycle_days: reviewCycleDays,
    review_age_days: reviewAgeDays,
    review_due_at: dueAt,
    review_days_until_due: daysUntilDue,
    due_soon_days: dueSoonDays,
    recommended_action: "schedule governance review before due date"
  });
  process.exit(0);
}

ok("OK", "governance review reminder check passed", {
  owner: owner || undefined,
  review_cycle_days: reviewCycleDays,
  review_age_days: reviewAgeDays,
  review_due_at: dueAt,
  review_days_until_due: daysUntilDue,
  due_soon_days: dueSoonDays
});
