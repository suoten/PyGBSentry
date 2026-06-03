import { createHmac, timingSafeEqual } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const alertStatusPath = process.env.MOBILE_REGRESSION_ROTATION_ALERT_STATUS_PATH || "scripts/mobile-regression.rotation-alert-status.json";
const verifyStatusPath = process.env.MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_STATUS_PATH || "scripts/mobile-regression.rotation-alert-verify-status.json";
const replayStatePath = process.env.MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_REPLAY_STATE_PATH || "scripts/mobile-regression.rotation-alert-verify-replay-state.json";
const verifyRequired = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_REQUIRED || "false").toLowerCase() === "true";

const signatureSecret = process.env.MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_SIGNING_SECRET || process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNING_SECRET || "";
const signatureAlgorithm = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_ALGORITHM || "sha256";
const signatureEncoding = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_ENCODING || "hex";
const signaturePrefix = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_PREFIX || "hmac";
const expectedSignatureKeyId = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_KEY_ID || "";
const skewSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_MAX_TIMESTAMP_SKEW_SEC || 300));
const nonceTtlSec = Math.max(skewSec, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_NONCE_TTL_SEC || 900));

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

function writeVerifyStatusAndExit(status, code = 0) {
  writeJsonSafe(verifyStatusPath, { updated_at: new Date().toISOString(), ...status });
  process.exit(code);
}

function safeEqual(a, b) {
  const aBuf = Buffer.from(String(a));
  const bBuf = Buffer.from(String(b));
  if (aBuf.length !== bBuf.length) return false;
  return timingSafeEqual(aBuf, bBuf);
}

function sign(body, timestamp, nonce) {
  const canonical = `${timestamp}\n${nonce}\n${body}`;
  const digest = createHmac(signatureAlgorithm, signatureSecret).update(canonical).digest(signatureEncoding);
  return `${signaturePrefix}-${signatureAlgorithm}-${signatureEncoding}=${digest}`;
}

if (!signatureSecret) {
  writeVerifyStatusAndExit({ ok: false, skipped: true, reason_code: "VERIFY_SECRET_MISSING" }, verifyRequired ? 1 : 0);
}

const alertStatus = readJsonSafe(alertStatusPath, null);
if (!alertStatus || alertStatus.skipped || alertStatus.ok !== true) {
  writeVerifyStatusAndExit({ ok: false, skipped: true, reason_code: "ALERT_STATUS_NOT_OK" }, verifyRequired ? 1 : 0);
}

const body = String(alertStatus.payload_body || "");
if (!body) {
  writeVerifyStatusAndExit({ ok: false, skipped: true, reason_code: "ALERT_PAYLOAD_BODY_MISSING" }, verifyRequired ? 1 : 0);
}

const dispatches = Array.isArray(alertStatus.dispatches) ? alertStatus.dispatches : [];
const signedDispatches = dispatches.filter(
  (x) => x?.ok === true && x?.signed === true && x?.signature_timestamp && x?.signature_nonce && x?.signature_value
);
if (signedDispatches.length === 0) {
  writeVerifyStatusAndExit({ ok: false, skipped: true, reason_code: "NO_SIGNED_DISPATCH" }, verifyRequired ? 1 : 0);
}

const replayState = readJsonSafe(replayStatePath, { nonces: {} });
const nonces = replayState && typeof replayState.nonces === "object" ? replayState.nonces : {};
const nowSec = Math.floor(Date.now() / 1000);
const replayWindowStart = nowSec - nonceTtlSec;
for (const key of Object.keys(nonces)) {
  if (Number(nonces[key]) < replayWindowStart) delete nonces[key];
}

const results = [];
for (const row of signedDispatches) {
  const timestamp = String(row.signature_timestamp || "");
  const nonce = String(row.signature_nonce || "");
  const providedSignature = String(row.signature_value || "");
  const signatureKeyId = String(row.signature_key_id || "");
  const timestampSec = Number(timestamp);
  const skew = Number.isNaN(timestampSec) ? Number.POSITIVE_INFINITY : Math.abs(nowSec - timestampSec);
  if (Number.isNaN(timestampSec)) {
    results.push({ target: row.target || "", ok: false, reason_code: "TIMESTAMP_INVALID" });
    continue;
  }
  if (skew > skewSec) {
    results.push({ target: row.target || "", ok: false, reason_code: "TIMESTAMP_EXPIRED" });
    continue;
  }
  if (!nonce) {
    results.push({ target: row.target || "", ok: false, reason_code: "NONCE_MISSING" });
    continue;
  }
  if (expectedSignatureKeyId && signatureKeyId !== expectedSignatureKeyId) {
    results.push({ target: row.target || "", ok: false, reason_code: "SIGNATURE_KEY_ID_MISMATCH" });
    continue;
  }
  const replayKey = `${signatureKeyId || "_"}:${nonce}`;
  if (nonces[replayKey] && Number(nonces[replayKey]) >= replayWindowStart) {
    results.push({ target: row.target || "", ok: false, reason_code: "NONCE_REPLAY" });
    continue;
  }
  const expected = sign(body, timestamp, nonce);
  if (!safeEqual(expected, providedSignature)) {
    results.push({ target: row.target || "", ok: false, reason_code: "SIGNATURE_MISMATCH" });
    continue;
  }
  nonces[replayKey] = nowSec;
  results.push({ target: row.target || "", ok: true, reason_code: "OK" });
}

writeJsonSafe(replayStatePath, { nonces });
const failed = results.filter((x) => x.ok !== true);
if (failed.length > 0) {
  writeVerifyStatusAndExit(
    {
      ok: false,
      skipped: false,
      reason_code: failed[0].reason_code || "VERIFY_FAILED",
      total: results.length,
      passed: results.length - failed.length,
      failed: failed.length,
      results
    },
    verifyRequired ? 1 : 0
  );
}

writeVerifyStatusAndExit({
  ok: true,
  skipped: false,
  reason_code: "OK",
  total: results.length,
  passed: results.length,
  failed: 0,
  results
});
