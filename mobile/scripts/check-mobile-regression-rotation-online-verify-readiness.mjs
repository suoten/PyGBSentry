import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const required = String(process.env.MOBILE_REGRESSION_ROTATION_ONLINE_VERIFY_REQUIRED || "false").toLowerCase() === "true";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_ONLINE_VERIFY_STATUS_PATH || "scripts/mobile-regression.rotation-online-verify-status.json";

const publishVerifyRequired = String(process.env.MOBILE_REGRESSION_ROTATION_PUBLISH_VERIFY_REQUIRED || "false").toLowerCase() === "true";
const alertVerifyRequired = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_REQUIRED || "false").toLowerCase() === "true";
const trendAlertRequired = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_REQUIRED || "false").toLowerCase() === "true";

const reportKeyId = String(process.env.MOBILE_REGRESSION_ROTATION_REPORT_SIGNATURE_KEY_ID || "");
const alertKeyId = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_KEY_ID || "");
const reportVerifySecret = String(process.env.MOBILE_REGRESSION_ROTATION_PUBLISH_VERIFY_SIGNING_SECRET || process.env.MOBILE_REGRESSION_ROTATION_REPORT_SIGNING_SECRET || "");
const alertVerifySecret = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_SIGNING_SECRET || process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNING_SECRET || "");

const skewSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_MAX_TIMESTAMP_SKEW_SEC || 300));
const nonceTtlSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_NONCE_TTL_SEC || 900));

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
  writeStatus({ ok: false, reason_code: reasonCode, message, ...extra });
  throw new Error(`[mobile-regression-rotation-online-verify] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({ ok: true, reason_code: reasonCode, message, ...extra });
  console.log(`[mobile-regression-rotation-online-verify] ${reasonCode}: ${message}`);
}

if (skewSec <= 0) {
  fail("VERIFY_SKEW_INVALID", "verify max timestamp skew must be > 0", { skew_sec: skewSec });
}
if (nonceTtlSec < skewSec) {
  fail("VERIFY_NONCE_TTL_INVALID", "nonce ttl must be >= skew", { skew_sec: skewSec, nonce_ttl_sec: nonceTtlSec });
}

if (policyEnv === "prod" || required) {
  if (!publishVerifyRequired) fail("PUBLISH_VERIFY_NOT_REQUIRED", "publish verify should be required in prod/required mode");
  if (!alertVerifyRequired) fail("ALERT_VERIFY_NOT_REQUIRED", "alert verify should be required in prod/required mode");
  if (!trendAlertRequired) fail("TREND_ALERT_NOT_REQUIRED", "trend alert should be required in prod/required mode");
}

if ((publishVerifyRequired || required) && !reportVerifySecret) {
  fail("PUBLISH_VERIFY_SECRET_MISSING", "publish verify signing secret missing");
}
if ((alertVerifyRequired || required) && !alertVerifySecret) {
  fail("ALERT_VERIFY_SECRET_MISSING", "alert verify signing secret missing");
}

if ((publishVerifyRequired || required) && !reportKeyId) {
  fail("PUBLISH_KEY_ID_MISSING", "publish signature key_id missing");
}
if ((alertVerifyRequired || required) && !alertKeyId) {
  fail("ALERT_KEY_ID_MISSING", "alert signature key_id missing");
}

ok("OK", "online verify readiness check passed", {
  publish_verify_required: publishVerifyRequired,
  alert_verify_required: alertVerifyRequired,
  trend_alert_required: trendAlertRequired,
  report_key_id: reportKeyId || undefined,
  alert_key_id: alertKeyId || undefined,
  skew_sec: skewSec,
  nonce_ttl_sec: nonceTtlSec
});
