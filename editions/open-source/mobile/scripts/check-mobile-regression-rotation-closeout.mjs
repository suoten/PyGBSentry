import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const required = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_REQUIRED || "false").toLowerCase() === "true";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const statusPath = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_STATUS_PATH || "scripts/mobile-regression.rotation-closeout-status.json";

const signoffAt = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_SIGNOFF_AT || "");
const signoffOwners = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_SIGNOFF_OWNERS || "")
  .split(",")
  .map((x) => x.trim())
  .filter((x) => !!x);
const windowStartAt = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_WINDOW_START_AT || "");
const windowEndAt = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_WINDOW_END_AT || "");
const postmortemId = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_POSTMORTEM_ID || "");

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
  const ms = Date.parse(String(value || ""));
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function fail(reasonCode, message, extra = {}) {
  writeStatus({ ok: false, reason_code: reasonCode, message, ...extra });
  throw new Error(`[mobile-regression-rotation-closeout] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({ ok: true, reason_code: reasonCode, message, ...extra });
  console.log(`[mobile-regression-rotation-closeout] ${reasonCode}: ${message}`);
}

const strictMode = required || policyEnv === "prod";
if (!signoffAt && !windowStartAt && !windowEndAt && signoffOwners.length === 0 && !postmortemId) {
  if (strictMode) {
    fail("CLOSEOUT_INFO_MISSING", "closeout info missing in strict mode");
  }
  ok("SKIPPED", "closeout info not provided, strictMode=false");
  process.exit(0);
}

if (!signoffAt) fail("CLOSEOUT_SIGNOFF_AT_MISSING", "closeout signoff timestamp missing");
if (signoffOwners.length < 2) fail("CLOSEOUT_SIGNOFF_OWNERS_INSUFFICIENT", "closeout signoff owners must be at least 2");
if (!postmortemId) fail("CLOSEOUT_POSTMORTEM_ID_MISSING", "closeout postmortem id missing");

const signoffAtMs = parseDateMs(signoffAt);
if (Number.isNaN(signoffAtMs)) fail("CLOSEOUT_SIGNOFF_AT_INVALID", `invalid closeout signoff timestamp: ${signoffAt}`);

const windowStartMs = parseDateMs(windowStartAt);
const windowEndMs = parseDateMs(windowEndAt);
if (Number.isNaN(windowStartMs) || Number.isNaN(windowEndMs)) {
  fail("CLOSEOUT_WINDOW_INVALID", "invalid closeout window start/end timestamp");
}
if (windowEndMs <= windowStartMs) {
  fail("CLOSEOUT_WINDOW_ORDER_INVALID", "closeout window end_at must be later than start_at");
}
if (signoffAtMs < windowStartMs || signoffAtMs > windowEndMs) {
  fail("CLOSEOUT_SIGNOFF_OUT_OF_WINDOW", "signoff timestamp is outside closeout window", {
    signoff_at: signoffAt,
    window_start_at: windowStartAt,
    window_end_at: windowEndAt
  });
}

ok("OK", "closeout check passed", {
  signoff_at: signoffAt,
  signoff_owners: signoffOwners,
  window_start_at: windowStartAt,
  window_end_at: windowEndAt,
  postmortem_id: postmortemId
});
