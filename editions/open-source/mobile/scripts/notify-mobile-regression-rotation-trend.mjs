import { createHmac, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const reportPath = process.env.MOBILE_REGRESSION_ROTATION_REPORT_JSON_PATH || "scripts/mobile-regression.rotation-report.json";
const statusPath = process.env.MOBILE_REGRESSION_ROTATION_ALERT_STATUS_PATH || "scripts/mobile-regression.rotation-alert-status.json";
const closeoutStatusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_STATUS_PATH || "scripts/mobile-regression.rotation-closeout-status.json";
const webhookUrl = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_URL || "";
const webhookToken = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_TOKEN || "";
const webhookUrlError = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_URL_ERROR || "";
const webhookUrlWarning = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_URL_WARNING || "";
const webhookUrlInfo = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_URL_INFO || "";
const webhookUrlProd = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_URL_PROD || "";
const webhookUrlCanary = process.env.MOBILE_REGRESSION_ROTATION_ALERT_WEBHOOK_URL_CANARY || "";
const muteReasonCodes = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_MUTE_REASON_CODES || "")
  .split(",")
  .map((x) => x.trim().toUpperCase())
  .filter((x) => !!x);
const levelOverridesRaw = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_LEVEL_OVERRIDES || "");
const dedupeWindowSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_ALERT_DEDUPE_WINDOW_SEC || 600));
const dedupeStatePath = process.env.MOBILE_REGRESSION_ROTATION_ALERT_DEDUPE_STATE_PATH || "scripts/mobile-regression.rotation-alert-dedupe.json";
const notifyRetries = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_ALERT_RETRIES || 1));
const notifyRetryDelayMs = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_ALERT_RETRY_DELAY_MS || 1000));
const signingSecret = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNING_SECRET || "";
const signatureHeader = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_HEADER || "X-PyGBSentry-Signature";
const signatureTimestampHeader =
  process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_TIMESTAMP_HEADER || "X-PyGBSentry-Signature-Timestamp";
const signatureNonceHeader = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_NONCE_HEADER || "X-PyGBSentry-Signature-Nonce";
const signatureAlgorithmHeader =
  process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_ALGORITHM_HEADER || "X-PyGBSentry-Signature-Algorithm";
const signatureEncodingHeader =
  process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_ENCODING_HEADER || "X-PyGBSentry-Signature-Encoding";
const signatureVersionHeader =
  process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_VERSION_HEADER || "X-PyGBSentry-Signature-Version";
const signatureKeyIdHeader =
  process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_KEY_ID_HEADER || "X-PyGBSentry-Signature-Key-Id";
const signatureAlgorithm = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_ALGORITHM || "sha256";
const signatureEncoding = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_ENCODING || "hex";
const signaturePrefix = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_PREFIX || "hmac";
const signatureVersion = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_VERSION || "v1";
const signatureKeyId = process.env.MOBILE_REGRESSION_ROTATION_ALERT_SIGNATURE_KEY_ID || "";
const required = String(process.env.MOBILE_REGRESSION_ROTATION_ALERT_REQUIRED || "false").toLowerCase() === "true";
const failCountThreshold = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_ALERT_FAIL_COUNT_THRESHOLD || 2));
const failRateThreshold = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_ALERT_FAIL_RATE_THRESHOLD || 0.3));
const closeoutRiskReasonCodesDefault = String(
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_REASON_CODES ||
    "CLOSEOUT_INFO_MISSING,CLOSEOUT_SIGNOFF_AT_MISSING,CLOSEOUT_SIGNOFF_OWNERS_INSUFFICIENT,CLOSEOUT_POSTMORTEM_ID_MISSING,CLOSEOUT_SIGNOFF_AT_INVALID,CLOSEOUT_WINDOW_INVALID,CLOSEOUT_WINDOW_ORDER_INVALID,CLOSEOUT_SIGNOFF_OUT_OF_WINDOW"
);
const closeoutRiskReasonCodesProdRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_REASON_CODES_PROD || "");
const closeoutRiskReasonCodesCanaryRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_REASON_CODES_CANARY || "");
const closeoutLevelOverridesRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_LEVEL_OVERRIDES || "");
const closeoutMuteReasonCodesDefaultRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_MUTE_REASON_CODES || "");
const closeoutMuteReasonCodesProdRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_MUTE_REASON_CODES_PROD || "");
const closeoutMuteReasonCodesCanaryRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_MUTE_REASON_CODES_CANARY || "");
const closeoutDedupeWindowMapDefaultRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_DEDUPE_WINDOW_SEC_MAP || "");
const closeoutDedupeWindowMapProdRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_DEDUPE_WINDOW_SEC_MAP_PROD || "");
const closeoutDedupeWindowMapCanaryRaw = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_DEDUPE_WINDOW_SEC_MAP_CANARY || "");
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const dispatches = [];

function writeStatus(payload) {
  const file = resolve(process.cwd(), statusPath);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(
    file,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        required,
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
  throw new Error(`[mobile-regression-rotation-alert] ${reasonCode}: ${message}`);
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

function parseCsvUpper(raw) {
  return String(raw || "")
    .split(",")
    .map((x) => x.trim().toUpperCase())
    .filter((x) => !!x);
}

function parseLevelOverrides(raw) {
  const out = {};
  if (!raw) return out;
  const rows = raw.split(",").map((x) => x.trim()).filter((x) => !!x);
  for (const row of rows) {
    const [k, v] = row.split("=").map((x) => String(x || "").trim());
    if (!k || !v) continue;
    const code = k.toUpperCase();
    const level = v.toLowerCase();
    if (level === "error" || level === "warning" || level === "info") {
      out[code] = level;
    }
  }
  return out;
}

function parseDedupeWindowMap(raw) {
  const out = {};
  if (!raw) return out;
  const rows = raw.split(",").map((x) => x.trim()).filter((x) => !!x);
  for (const row of rows) {
    const [k, v] = row.split("=").map((x) => String(x || "").trim());
    if (!k || !v) continue;
    const code = k.toUpperCase();
    const sec = Math.max(0, Number(v));
    if (!Number.isNaN(sec)) {
      out[code] = sec;
    }
  }
  return out;
}

function resolveEnvValue(globalValue, prodValue, canaryValue, env) {
  if (env === "prod" && prodValue) return { value: prodValue, source: "prod" };
  if (env === "canary" && canaryValue) return { value: canaryValue, source: "canary" };
  return { value: globalValue, source: "global" };
}

function pushTarget(targets, seen, url) {
  if (!url) return;
  if (seen.has(url)) return;
  seen.add(url);
  targets.push(url);
}

function isSupportedSignatureAlgorithm(algorithm) {
  return algorithm === "sha256" || algorithm === "sha1" || algorithm === "sha512";
}

function isSupportedSignatureEncoding(encoding) {
  return encoding === "hex" || encoding === "base64";
}

function createSignature(body, timestamp, nonce) {
  if (!isSupportedSignatureAlgorithm(signatureAlgorithm)) {
    throw new Error(`unsupported signature algorithm: ${signatureAlgorithm}`);
  }
  if (!isSupportedSignatureEncoding(signatureEncoding)) {
    throw new Error(`unsupported signature encoding: ${signatureEncoding}`);
  }
  const canonical = `${timestamp}\n${nonce}\n${body}`;
  const digest = createHmac(signatureAlgorithm, signingSecret).update(canonical).digest(signatureEncoding);
  return `${signaturePrefix}-${signatureAlgorithm}-${signatureEncoding}=${digest}`;
}

const reportFile = resolve(process.cwd(), reportPath);
if (!existsSync(reportFile)) {
  writeStatus({ ok: false, skipped: true, reason_code: "REPORT_FILE_MISSING" });
  if (required) fail("REPORT_FILE_MISSING", "rotation report missing");
  process.exit(0);
}

const report = JSON.parse(readFileSync(reportFile, "utf8"));
const totals = report?.totals || {};
const total = Math.max(0, Number(totals.total || 0));
const failed = Math.max(0, Number(totals.failed || 0));
const failRate = total > 0 ? Number((failed / total).toFixed(4)) : 0;
const closeoutRiskReasonCodes = resolveEnvValue(
  parseCsvUpper(closeoutRiskReasonCodesDefault),
  parseCsvUpper(closeoutRiskReasonCodesProdRaw),
  parseCsvUpper(closeoutRiskReasonCodesCanaryRaw),
  policyEnv
);
const closeoutMuteReasonCodes = resolveEnvValue(
  parseCsvUpper(closeoutMuteReasonCodesDefaultRaw),
  parseCsvUpper(closeoutMuteReasonCodesProdRaw),
  parseCsvUpper(closeoutMuteReasonCodesCanaryRaw),
  policyEnv
);
const closeoutDedupeWindowMap = resolveEnvValue(
  parseDedupeWindowMap(closeoutDedupeWindowMapDefaultRaw),
  parseDedupeWindowMap(closeoutDedupeWindowMapProdRaw),
  parseDedupeWindowMap(closeoutDedupeWindowMapCanaryRaw),
  policyEnv
);
const closeoutStatus = readJsonSafe(closeoutStatusPath, null);
const closeoutReasonCode = String(closeoutStatus?.reason_code || "").toUpperCase();
const closeoutRisk = !!closeoutReasonCode && closeoutRiskReasonCodes.value.includes(closeoutReasonCode);
const closeoutMuted = closeoutRisk && closeoutMuteReasonCodes.value.includes(closeoutReasonCode);
const effectiveDedupeWindowSec =
  closeoutRisk && Number.isFinite(closeoutDedupeWindowMap.value[closeoutReasonCode])
    ? Number(closeoutDedupeWindowMap.value[closeoutReasonCode])
    : dedupeWindowSec;
const policyAudit = {
  policy_env: policyEnv,
  closeout_reason_codes: {
    source: closeoutRiskReasonCodes.source,
    effective: closeoutRiskReasonCodes.value
  },
  closeout_mute_reason_codes: {
    source: closeoutMuteReasonCodes.source,
    effective: closeoutMuteReasonCodes.value
  },
  closeout_dedupe_window_sec_map: {
    source: closeoutDedupeWindowMap.source,
    effective: closeoutDedupeWindowMap.value
  },
  dedupe_window_sec_global: dedupeWindowSec,
  dedupe_window_sec_effective: effectiveDedupeWindowSec,
  dedupe_window_reason_override_applied:
    closeoutRisk && Number.isFinite(closeoutDedupeWindowMap.value[closeoutReasonCode]) && effectiveDedupeWindowSec !== dedupeWindowSec
};
const thresholdTriggered = failed >= failCountThreshold || failRate >= failRateThreshold;
const shouldAlert = closeoutRisk || thresholdTriggered;
const reasonCode = !shouldAlert
  ? "NO_ALERT"
  : closeoutRisk
    ? closeoutReasonCode
    : failed >= failCountThreshold
      ? "FAILED_COUNT_HIGH"
      : "FAILED_RATE_HIGH";
if (closeoutMuted) {
  writeStatus({
    ok: true,
    skipped: true,
    reason_code: "MUTED",
    mute_reason_code: reasonCode,
    mute_scope: "closeout",
    closeout_reason_code: closeoutReasonCode || undefined,
    closeout_alert_reason_codes: closeoutRiskReasonCodes.value,
    closeout_mute_reason_codes: closeoutMuteReasonCodes.value,
    policy_audit: policyAudit
  });
  process.exit(0);
}
if (muteReasonCodes.includes(reasonCode)) {
  writeStatus({
    ok: true,
    skipped: true,
    reason_code: "MUTED",
    mute_reason_code: reasonCode,
    mute_scope: "global",
    policy_audit: policyAudit
  });
  process.exit(0);
}

if (!shouldAlert) {
  writeStatus({
    ok: true,
    skipped: true,
    reason_code: "NO_ALERT",
    failed,
    total,
    fail_rate: failRate,
    fail_count_threshold: failCountThreshold,
    fail_rate_threshold: failRateThreshold,
    closeout_reason_code: closeoutReasonCode || undefined,
    closeout_alert_reason_codes: closeoutRiskReasonCodes.value,
    closeout_mute_reason_codes: closeoutMuteReasonCodes.value,
    policy_audit: policyAudit
  });
  process.exit(0);
}

const levelOverrides = parseLevelOverrides(levelOverridesRaw);
const closeoutLevelOverrides = parseLevelOverrides(closeoutLevelOverridesRaw);
const closeoutDefaultLevel = reasonCode.includes("OUT_OF_WINDOW") || reasonCode.includes("INVALID") ? "error" : "warning";
const closeoutLevel = closeoutLevelOverrides[reasonCode] || closeoutDefaultLevel;
const level = levelOverrides[reasonCode] || (reasonCode === "FAILED_COUNT_HIGH" ? "error" : reasonCode === "FAILED_RATE_HIGH" ? "warning" : closeoutLevel);
const routedLevelWebhook = level === "error" ? webhookUrlError || webhookUrl : level === "warning" ? webhookUrlWarning || webhookUrl : webhookUrlInfo || webhookUrl;
const envWebhook = policyEnv === "prod" ? webhookUrlProd : policyEnv === "canary" ? webhookUrlCanary : "";
const targets = [];
const targetSet = new Set();
pushTarget(targets, targetSet, envWebhook || routedLevelWebhook || webhookUrl);

const dedupeKey = `${reasonCode}|${policyEnv}|${level}`;
const dedupeState = readJsonSafe(dedupeStatePath, { records: {} });
const records = dedupeState && typeof dedupeState.records === "object" ? dedupeState.records : {};
const lastSentMs = Number(records[dedupeKey] || 0);
const nowMs = Date.now();
const inDedupeWindow = effectiveDedupeWindowSec > 0 && lastSentMs > 0 && nowMs - lastSentMs < effectiveDedupeWindowSec * 1000;
if (inDedupeWindow) {
  writeStatus({
    ok: true,
    skipped: true,
    deduped: true,
    reason_code: "DEDUPED",
    dedupe_key: dedupeKey,
    dedupe_window_sec: effectiveDedupeWindowSec,
    level,
    failed,
    total,
    fail_rate: failRate,
    policy_audit: policyAudit
  });
  process.exit(0);
}

if (targets.length === 0) {
  if (required) fail("WEBHOOK_NOT_CONFIGURED", "alert webhook not configured", { failed, total, fail_rate: failRate, level });
  writeStatus({
    ok: false,
    skipped: true,
    reason_code: "WEBHOOK_NOT_CONFIGURED",
    level,
    failed,
    total,
    fail_rate: failRate
  });
  process.exit(0);
}

const payload = {
  type: "mobile_regression_rotation_trend_alert",
  repository: process.env.GITHUB_REPOSITORY || "",
  branch: process.env.GITHUB_REF || "",
  run_id: process.env.GITHUB_RUN_ID || "",
  fail_count_threshold: failCountThreshold,
  fail_rate_threshold: failRateThreshold,
  reason_code: reasonCode,
  level,
  policy_env: policyEnv,
  closeout_risk: closeoutRisk,
  closeout_reason_code: closeoutReasonCode || undefined,
  closeout_alert_reason_codes: closeoutRiskReasonCodes.value,
  closeout_mute_reason_codes: closeoutMuteReasonCodes.value,
  closeout_level_override: closeoutLevelOverrides[closeoutReasonCode] || undefined,
  closeout_status: closeoutStatus || undefined,
  closeout_signal:
    closeoutStatus && closeoutReasonCode
      ? {
          reason_code: closeoutReasonCode,
          risk_matched: closeoutRisk,
          recommended_level: closeoutLevel,
          level_source: closeoutLevelOverrides[closeoutReasonCode] ? "closeout_level_override" : "closeout_default"
        }
      : undefined,
  failed,
  total,
  fail_rate: failRate,
  report
};
const body = JSON.stringify(payload);

const headers = { "Content-Type": "application/json" };
if (webhookToken) {
  headers.Authorization = `Bearer ${webhookToken}`;
}

for (const target of targets) {
  let sent = false;
  for (let attempt = 1; attempt <= notifyRetries + 1; attempt += 1) {
    const reqHeaders = { ...headers };
    let timestamp = "";
    let nonce = "";
    let signatureValue = "";
    if (signingSecret) {
      timestamp = String(Math.floor(Date.now() / 1000));
      nonce = randomUUID();
      signatureValue = createSignature(body, timestamp, nonce);
      reqHeaders[signatureHeader] = signatureValue;
      reqHeaders[signatureTimestampHeader] = timestamp;
      reqHeaders[signatureNonceHeader] = nonce;
      reqHeaders[signatureAlgorithmHeader] = signatureAlgorithm;
      reqHeaders[signatureEncodingHeader] = signatureEncoding;
      reqHeaders[signatureVersionHeader] = signatureVersion;
      if (signatureKeyId) {
        reqHeaders[signatureKeyIdHeader] = signatureKeyId;
      }
    }
    const res = await fetch(target, {
      method: "POST",
      headers: reqHeaders,
      body
    });
    if (res.ok) {
      sent = true;
      dispatches.push({
        target,
        ok: true,
        attempt,
        http_status: res.status,
        signed: !!signingSecret,
        signature_timestamp: timestamp || undefined,
        signature_nonce: nonce || undefined,
        signature_value: signatureValue || undefined,
        signature_key_id: signatureKeyId || undefined
      });
      records[dedupeKey] = nowMs;
      writeJsonSafe(dedupeStatePath, { records });
      break;
    }
    if (attempt <= notifyRetries) {
      await sleep(notifyRetryDelayMs);
      continue;
    }
    fail("ALERT_HTTP_ERROR", `http ${res.status} while notifying trend alert`, {
      failed,
      total,
      fail_rate: failRate,
      http_status: res.status,
      target,
      signed: !!signingSecret,
      dispatches,
      payload_body: body
    });
  }
  if (!sent) {
    fail("ALERT_SEND_FAILED", "failed to send trend alert", { target });
  }
}

writeStatus({
  ok: true,
  skipped: false,
  reason_code: "OK",
  alert_reason_code: reasonCode,
  level,
  policy_env: policyEnv,
  dedupe_key: dedupeKey,
  dedupe_window_sec: effectiveDedupeWindowSec,
  policy_audit: policyAudit,
  signed: !!signingSecret,
  signature: signingSecret
    ? {
        header: signatureHeader,
        timestamp_header: signatureTimestampHeader,
        nonce_header: signatureNonceHeader,
        algorithm_header: signatureAlgorithmHeader,
        encoding_header: signatureEncodingHeader,
        version_header: signatureVersionHeader,
        key_id_header: signatureKeyIdHeader,
        algorithm: signatureAlgorithm,
        encoding: signatureEncoding,
        prefix: signaturePrefix,
        version: signatureVersion,
        key_id: signatureKeyId || undefined
      }
    : null,
  payload_body: body,
  dispatches,
  failed,
  total,
  fail_rate: failRate
});
