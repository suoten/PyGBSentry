import { createHmac, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const reportJsonPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_JSON_PATH || "scripts/native-player-integration.alert-report.json";
const reportMdPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_MD_PATH || "scripts/native-player-integration.alert-report.md";
const webhookUrl = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_URL || "";
const webhookToken = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_TOKEN || "";
const webhookUrlError = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_URL_ERROR || "";
const webhookUrlWarning = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_URL_WARNING || "";
const webhookUrlInfo = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_URL_INFO || "";
const escalationWebhookUrl = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_ESCALATION_WEBHOOK_URL || "";
const escalationWebhookToken = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_ESCALATION_WEBHOOK_TOKEN || "";
const webhookTokenError = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_TOKEN_ERROR || "";
const webhookTokenWarning = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_TOKEN_WARNING || "";
const webhookTokenInfo = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_TOKEN_INFO || "";
const extraWebhookUrls = String(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_WEBHOOK_URLS || "")
  .split(",")
  .map((x) => x.trim())
  .filter((x) => !!x);
const retries = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_PUBLISH_RETRIES || 1));
const retryDelayMs = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_PUBLISH_RETRY_DELAY_MS || 1000));
const publishStatusPath = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_PUBLISH_STATUS_PATH || "scripts/native-player-integration.alert-report-publish-status.json";
const signingSecret = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNING_SECRET || "";
const signatureHeader = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_HEADER || "X-PyGBSentry-Signature";
const signatureTimestampHeader = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_TIMESTAMP_HEADER || "X-PyGBSentry-Signature-Timestamp";
const signatureNonceHeader = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_NONCE_HEADER || "X-PyGBSentry-Signature-Nonce";
const signatureAlgorithmHeader = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ALGORITHM_HEADER || "X-PyGBSentry-Signature-Algorithm";
const signatureEncodingHeader = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ENCODING_HEADER || "X-PyGBSentry-Signature-Encoding";
const signatureVersionHeader = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_VERSION_HEADER || "X-PyGBSentry-Signature-Version";
const signatureAlgorithm = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ALGORITHM || "sha256";
const signatureEncoding = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ENCODING || "hex";
const signaturePrefix = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_PREFIX || "hmac";
const signatureVersion = process.env.NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_VERSION || "v1";

function log(message) {
  console.log(`[publish-native-integration-alert-report] ${message}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function writeJsonSafe(path, data) {
  const file = resolve(process.cwd(), path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function writePublishStatus(status) {
  writeJsonSafe(publishStatusPath, {
    updated_at: new Date().toISOString(),
    ...status
  });
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

function createSignature(body, timestamp, nonce) {
  if (!signingSecret) return null;
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

function pushTarget(targets, seen, url, token, channel) {
  if (!url) return;
  if (seen.has(url)) return;
  seen.add(url);
  targets.push({ url, token, channel });
}

const jsonFile = resolve(process.cwd(), reportJsonPath);
const mdFile = resolve(process.cwd(), reportMdPath);
if (!existsSync(jsonFile) || !existsSync(mdFile)) {
  log(`skip: report files missing json=${existsSync(jsonFile)} md=${existsSync(mdFile)}`);
  writePublishStatus({
    ok: false,
    skipped: true,
    reason_code: "REPORT_FILE_MISSING",
    json_exists: existsSync(jsonFile),
    md_exists: existsSync(mdFile)
  });
  process.exit(0);
}

const reportJson = JSON.parse(readFileSync(jsonFile, "utf8"));
const reportMarkdown = readFileSync(mdFile, "utf8");
const reportLevel = resolveReportLevel(reportJson);
const routedWebhookUrl = reportLevel === "error" ? webhookUrlError || webhookUrl : reportLevel === "warning" ? webhookUrlWarning || webhookUrl : webhookUrlInfo || webhookUrl;
const routedWebhookToken = reportLevel === "error" ? webhookTokenError || webhookToken : reportLevel === "warning" ? webhookTokenWarning || webhookToken : webhookTokenInfo || webhookToken;
const shouldEscalate = Number(reportJson?.totals?.escalated || 0) > 0;
const targets = [];
const targetSet = new Set();
pushTarget(targets, targetSet, routedWebhookUrl, routedWebhookToken, `route:${reportLevel}`);
for (const url of extraWebhookUrls) {
  pushTarget(targets, targetSet, url, webhookToken, "broadcast");
}
if (shouldEscalate) {
  pushTarget(targets, targetSet, escalationWebhookUrl, escalationWebhookToken || webhookToken, "escalation");
}

if (targets.length === 0) {
  log("skip: report webhook not configured");
  writePublishStatus({
    ok: false,
    skipped: true,
    reason_code: "WEBHOOK_NOT_CONFIGURED",
    level: reportLevel,
    should_escalate: shouldEscalate,
    target_count: 0
  });
  process.exit(0);
}

if (signingSecret) {
  if (!isSupportedSignatureAlgorithm(signatureAlgorithm)) {
    writePublishStatus({
      ok: false,
      skipped: false,
      reason_code: "SIGNATURE_CONFIG_INVALID",
      message: `unsupported signature algorithm: ${signatureAlgorithm}`
    });
    throw new Error(`unsupported signature algorithm: ${signatureAlgorithm}`);
  }
  if (!isSupportedSignatureEncoding(signatureEncoding)) {
    writePublishStatus({
      ok: false,
      skipped: false,
      reason_code: "SIGNATURE_CONFIG_INVALID",
      message: `unsupported signature encoding: ${signatureEncoding}`
    });
    throw new Error(`unsupported signature encoding: ${signatureEncoding}`);
  }
}

const payload = {
  type: "native_player_integration_alert_weekly_report",
  level: reportLevel,
  should_escalate: shouldEscalate,
  routed_channels: targets.map((x) => x.channel),
  target_count: targets.length,
  repository: process.env.GITHUB_REPOSITORY || "",
  branch: process.env.GITHUB_REF || "",
  run_id: process.env.GITHUB_RUN_ID || "",
  generated_at: reportJson.generated_at || new Date().toISOString(),
  window_days: reportJson.window_days || 7,
  totals: reportJson.totals || {},
  markdown: reportMarkdown,
  report: reportJson
};
const body = JSON.stringify(payload);
const dispatches = [];

for (const target of targets) {
  let sent = false;
  let lastHttpStatus = 0;
  for (let attempt = 1; attempt <= retries + 1; attempt += 1) {
    const headers = { "Content-Type": "application/json" };
    if (target.token) {
      headers.Authorization = `Bearer ${target.token}`;
    }
    let timestamp = "";
    let nonce = "";
    let signatureValue = "";
    if (signingSecret) {
      timestamp = String(Math.floor(Date.now() / 1000));
      nonce = randomUUID();
      const signature = createSignature(body, timestamp, nonce);
      signatureValue = signature;
      headers[signatureHeader] = signature;
      headers[signatureTimestampHeader] = timestamp;
      headers[signatureNonceHeader] = nonce;
      headers[signatureAlgorithmHeader] = signatureAlgorithm;
      headers[signatureEncodingHeader] = signatureEncoding;
      headers[signatureVersionHeader] = signatureVersion;
    }
    const res = await fetch(target.url, {
      method: "POST",
      headers,
      body
    });
    lastHttpStatus = res.status;
    if (res.ok) {
      sent = true;
      dispatches.push({
        target: target.url,
        channel: target.channel,
        ok: true,
        attempt,
        http_status: res.status,
        signed: !!signingSecret,
        signature_timestamp: timestamp || undefined,
        signature_nonce: nonce || undefined,
        signature_value: signatureValue || undefined
      });
      break;
    }
    if (attempt <= retries) {
      await sleep(retryDelayMs);
      continue;
    }
    const errorMessage = `publish failed: http ${res.status} target=${target.url} channel=${target.channel}`;
    dispatches.push({
      target: target.url,
      channel: target.channel,
      ok: false,
      attempt,
      http_status: res.status,
      signed: !!signingSecret,
      signature_timestamp: timestamp || undefined,
      signature_nonce: nonce || undefined,
      signature_value: signatureValue || undefined,
      error: errorMessage
    });
    writePublishStatus({
      ok: false,
      skipped: false,
      reason_code: "PUBLISH_HTTP_ERROR",
      level: reportLevel,
      should_escalate: shouldEscalate,
      target_count: targets.length,
      signed: !!signingSecret,
      failed_target: target.url,
      failed_channel: target.channel,
      failed_http_status: res.status,
      dispatches
    });
    throw new Error(errorMessage);
  }
  if (sent) {
    log(`report published target=${target.url} channel=${target.channel} level=${reportLevel} signed=${signingSecret ? "true" : "false"}`);
  } else {
    dispatches.push({
      target: target.url,
      channel: target.channel,
      ok: false,
      http_status: lastHttpStatus,
      signed: !!signingSecret
    });
  }
}

writePublishStatus({
  ok: true,
  skipped: false,
  reason_code: "OK",
  level: reportLevel,
  should_escalate: shouldEscalate,
  target_count: targets.length,
  signed: !!signingSecret,
  signature: signingSecret
    ? {
        header: signatureHeader,
        timestamp_header: signatureTimestampHeader,
        nonce_header: signatureNonceHeader,
        algorithm_header: signatureAlgorithmHeader,
        encoding_header: signatureEncodingHeader,
        version_header: signatureVersionHeader,
        algorithm: signatureAlgorithm,
        encoding: signatureEncoding,
        prefix: signaturePrefix,
        version: signatureVersion
      }
    : null,
  dispatches
});
