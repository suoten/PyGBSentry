import { createHmac } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const reportJsonPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_JSON_PATH || "scripts/native-player-integration.alert-report.json";
const reportMdPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_MD_PATH || "scripts/native-player-integration.alert-report.md";
const publishStatusPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_PUBLISH_STATUS_PATH || "scripts/native-player-integration.alert-report-publish-status.json";
const verifyStatusPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_STATUS_PATH || "scripts/native-player-integration.alert-report-verify-status.json";
const replayStatePath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_REPLAY_STATE_PATH || "scripts/native-player-integration.alert-report-replay-state.json";
const verifyRequired = String(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_REQUIRED || "false").toLowerCase() === "true";

const signatureSecret = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_SIGNING_SECRET || process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNING_SECRET || "";
const signatureAlgorithm = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ALGORITHM || "sha256";
const signatureEncoding = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ENCODING || "hex";
const signaturePrefix = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_PREFIX || "hmac";
const skewSec = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_MAX_TIMESTAMP_SKEW_SEC || 300));
const nonceTtlSec = Math.max(skewSec, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_NONCE_TTL_SEC || 900));

function log(message) {
  console.log(`[verify-native-integration-alert-report-signature] ${message}`);
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

function resolveReportLevel(reportJson) {
  const totals = reportJson?.totals || {};
  const byLevel = reportJson?.by_level || {};
  if (Number(totals.escalated || 0) > 0 || Number(byLevel.error || 0) > 0) return "error";
  if (Number(byLevel.warning || 0) > 0) return "warning";
  return "info";
}

function isSupportedSignatureAlgorithm(algorithm) {
  return algorithm === "sha256" || algorithm === "sha1" || algorithm === "sha512";
}

function isSupportedSignatureEncoding(encoding) {
  return encoding === "hex" || encoding === "base64";
}

function buildPayload(reportJson, reportMarkdown, publishStatus) {
  const reportLevel = String(publishStatus?.level || resolveReportLevel(reportJson));
  const shouldEscalate =
    typeof publishStatus?.should_escalate === "boolean"
      ? publishStatus.should_escalate
      : Number(reportJson?.totals?.escalated || 0) > 0;
  const routedChannels = Array.isArray(publishStatus?.dispatches)
    ? publishStatus.dispatches.map((x) => String(x?.channel || "")).filter((x) => !!x)
    : [];
  const targetCount = Number(publishStatus?.target_count || routedChannels.length || 0);
  return {
    type: "native_player_integration_alert_weekly_report",
    level: reportLevel,
    should_escalate: shouldEscalate,
    routed_channels: routedChannels,
    target_count: targetCount,
    repository: process.env.GITHUB_REPOSITORY || "",
    branch: process.env.GITHUB_REF || "",
    run_id: process.env.GITHUB_RUN_ID || "",
    generated_at: reportJson.generated_at || new Date().toISOString(),
    window_days: reportJson.window_days || 7,
    totals: reportJson.totals || {},
    markdown: reportMarkdown,
    report: reportJson
  };
}

function sign(body, timestamp, nonce) {
  if (!isSupportedSignatureAlgorithm(signatureAlgorithm)) {
    throw new Error(`unsupported signature algorithm: ${signatureAlgorithm}`);
  }
  if (!isSupportedSignatureEncoding(signatureEncoding)) {
    throw new Error(`unsupported signature encoding: ${signatureEncoding}`);
  }
  const canonical = `${timestamp}\n${nonce}\n${body}`;
  const digest = createHmac(signatureAlgorithm, signatureSecret).update(canonical).digest(signatureEncoding);
  return `${signaturePrefix}-${signatureAlgorithm}-${signatureEncoding}=${digest}`;
}

function writeVerifyStatusAndExit(status, code = 0) {
  writeJsonSafe(verifyStatusPath, {
    updated_at: new Date().toISOString(),
    ...status
  });
  process.exit(code);
}

if (!signatureSecret) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: true,
    reason_code: "VERIFY_SECRET_MISSING"
  }, verifyRequired ? 1 : 0);
}

const reportJsonFile = resolve(process.cwd(), reportJsonPath);
const reportMdFile = resolve(process.cwd(), reportMdPath);
if (!existsSync(reportJsonFile) || !existsSync(reportMdFile)) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: true,
    reason_code: "REPORT_FILE_MISSING",
    json_exists: existsSync(reportJsonFile),
    md_exists: existsSync(reportMdFile)
  }, verifyRequired ? 1 : 0);
}

const publishStatus = readJsonSafe(publishStatusPath, null);
if (!publishStatus) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: true,
    reason_code: "PUBLISH_STATUS_MISSING"
  }, verifyRequired ? 1 : 0);
}
if (publishStatus.skipped) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: true,
    reason_code: "PUBLISH_SKIPPED"
  }, verifyRequired ? 1 : 0);
}
if (publishStatus.ok !== true) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: true,
    reason_code: "PUBLISH_NOT_OK"
  }, verifyRequired ? 1 : 0);
}

const dispatches = Array.isArray(publishStatus.dispatches) ? publishStatus.dispatches : [];
const signedDispatches = dispatches.filter((x) => x?.ok === true && x?.signed === true && x?.signature_timestamp && x?.signature_nonce && x?.signature_value);
if (signedDispatches.length === 0) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: true,
    reason_code: "NO_SIGNED_DISPATCH"
  }, verifyRequired ? 1 : 0);
}

const reportJson = JSON.parse(readFileSync(reportJsonFile, "utf8"));
const reportMarkdown = readFileSync(reportMdFile, "utf8");
const payload = buildPayload(reportJson, reportMarkdown, publishStatus);
const body = JSON.stringify(payload);

const replayState = readJsonSafe(replayStatePath, { nonces: {} });
const nonces = replayState && typeof replayState === "object" && replayState.nonces && typeof replayState.nonces === "object" ? replayState.nonces : {};
const nowSec = Math.floor(Date.now() / 1000);
const replayWindowStart = nowSec - nonceTtlSec;
for (const key of Object.keys(nonces)) {
  if (Number(nonces[key]) < replayWindowStart) {
    delete nonces[key];
  }
}

const results = [];
for (const row of signedDispatches) {
  const timestamp = String(row.signature_timestamp || "");
  const nonce = String(row.signature_nonce || "");
  const providedSignature = String(row.signature_value || "");
  const timestampSec = Number(timestamp);
  const skew = Number.isNaN(timestampSec) ? Number.POSITIVE_INFINITY : Math.abs(nowSec - timestampSec);
  if (Number.isNaN(timestampSec)) {
    results.push({ target: row.target || "", channel: row.channel || "", ok: false, reason_code: "TIMESTAMP_INVALID" });
    continue;
  }
  if (skew > skewSec) {
    results.push({ target: row.target || "", channel: row.channel || "", ok: false, reason_code: "TIMESTAMP_EXPIRED", skew_sec: skew, max_skew_sec: skewSec });
    continue;
  }
  if (!nonce) {
    results.push({ target: row.target || "", channel: row.channel || "", ok: false, reason_code: "NONCE_MISSING" });
    continue;
  }
  if (nonces[nonce] && Number(nonces[nonce]) >= replayWindowStart) {
    results.push({ target: row.target || "", channel: row.channel || "", ok: false, reason_code: "NONCE_REPLAY" });
    continue;
  }

  const expectedSignature = sign(body, timestamp, nonce);
  if (expectedSignature !== providedSignature) {
    results.push({ target: row.target || "", channel: row.channel || "", ok: false, reason_code: "SIGNATURE_MISMATCH" });
    continue;
  }

  nonces[nonce] = nowSec;
  results.push({ target: row.target || "", channel: row.channel || "", ok: true, reason_code: "OK" });
}

writeJsonSafe(replayStatePath, { nonces });

const failed = results.filter((x) => x.ok !== true);
if (failed.length > 0) {
  writeVerifyStatusAndExit({
    ok: false,
    skipped: false,
    reason_code: failed[0].reason_code || "VERIFY_FAILED",
    verify_required: verifyRequired,
    skew_sec: skewSec,
    nonce_ttl_sec: nonceTtlSec,
    total: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    results
  }, verifyRequired ? 1 : 0);
}

log(`verify passed: ${results.length} dispatch(es)`);
writeVerifyStatusAndExit({
  ok: true,
  skipped: false,
  reason_code: "OK",
  verify_required: verifyRequired,
  skew_sec: skewSec,
  nonce_ttl_sec: nonceTtlSec,
  total: results.length,
  passed: results.length,
  failed: 0,
  results
});
