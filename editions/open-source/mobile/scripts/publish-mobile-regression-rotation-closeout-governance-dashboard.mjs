import { createHmac, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const dashboardJsonPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_JSON_PATH ||
  "scripts/mobile-regression.rotation-closeout-dashboard.json";
const dashboardMdPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_MD_PATH ||
  "scripts/mobile-regression.rotation-closeout-dashboard.md";
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_STATUS_PATH ||
  "scripts/mobile-regression.rotation-closeout-dashboard-publish-status.json";
const webhookUrl = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URL || "";
const webhookToken = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_TOKEN || "";
const webhookUrlProd = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URL_PROD || "";
const webhookUrlCanary = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URL_CANARY || "";
const webhookTokenProd = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_TOKEN_PROD || "";
const webhookTokenCanary = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_TOKEN_CANARY || "";
const extraWebhookUrls = String(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URLS || "")
  .split(",")
  .map((x) => x.trim())
  .filter((x) => !!x);
const retries = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_RETRIES || 1));
const retryDelayMs = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_RETRY_DELAY_MS || 1000));
const signingSecret = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNING_SECRET || "";
const signatureHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_HEADER || "X-PyGBSentry-Signature";
const signatureTimestampHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_TIMESTAMP_HEADER || "X-PyGBSentry-Signature-Timestamp";
const signatureNonceHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_NONCE_HEADER || "X-PyGBSentry-Signature-Nonce";
const signatureAlgorithmHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_ALGORITHM_HEADER || "X-PyGBSentry-Signature-Algorithm";
const signatureEncodingHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_ENCODING_HEADER || "X-PyGBSentry-Signature-Encoding";
const signatureVersionHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_VERSION_HEADER || "X-PyGBSentry-Signature-Version";
const signatureKeyIdHeader =
  process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_KEY_ID_HEADER || "X-PyGBSentry-Signature-Key-Id";
const signatureAlgorithm = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_ALGORITHM || "sha256";
const signatureEncoding = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_ENCODING || "hex";
const signaturePrefix = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_PREFIX || "hmac";
const signatureVersion = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_VERSION || "v1";
const signatureKeyId = process.env.MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_KEY_ID || "";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function writeStatus(payload) {
  const file = resolve(process.cwd(), statusPath);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(
    file,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        policy_env: policyEnv,
        ...payload
      },
      null,
      2
    )}\n`,
    "utf8"
  );
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

function pushTarget(targets, seen, url, token, channel) {
  if (!url) return;
  if (seen.has(url)) return;
  seen.add(url);
  targets.push({ url, token, channel });
}

const jsonFile = resolve(process.cwd(), dashboardJsonPath);
const mdFile = resolve(process.cwd(), dashboardMdPath);
if (!existsSync(jsonFile) || !existsSync(mdFile)) {
  writeStatus({
    ok: false,
    skipped: true,
    reason_code: "DASHBOARD_FILE_MISSING",
    json_exists: existsSync(jsonFile),
    md_exists: existsSync(mdFile)
  });
  process.exit(0);
}

const envRouteUrl = policyEnv === "prod" ? webhookUrlProd : policyEnv === "canary" ? webhookUrlCanary : "";
const envRouteToken =
  policyEnv === "prod"
    ? webhookTokenProd || webhookToken
    : policyEnv === "canary"
      ? webhookTokenCanary || webhookToken
      : webhookToken;
const targets = [];
const targetSet = new Set();
pushTarget(targets, targetSet, envRouteUrl || webhookUrl, envRouteToken, `env:${policyEnv}`);
for (const url of extraWebhookUrls) {
  pushTarget(targets, targetSet, url, webhookToken, "broadcast");
}

if (targets.length === 0) {
  writeStatus({
    ok: false,
    skipped: true,
    reason_code: "WEBHOOK_NOT_CONFIGURED"
  });
  process.exit(0);
}

const dashboard = JSON.parse(readFileSync(jsonFile, "utf8"));
const markdown = readFileSync(mdFile, "utf8");
const payload = {
  type: "mobile_regression_rotation_closeout_governance_dashboard",
  repository: process.env.GITHUB_REPOSITORY || "",
  branch: process.env.GITHUB_REF || "",
  run_id: process.env.GITHUB_RUN_ID || "",
  generated_at: dashboard.generated_at || new Date().toISOString(),
  window_days: dashboard.window_days || 14,
  policy_env: policyEnv,
  markdown,
  dashboard
};
payload.idempotency_key = [payload.run_id || "", payload.generated_at || "", payload.policy_env || ""].join("|");
const body = JSON.stringify(payload);
const dispatches = [];

for (const target of targets) {
  let sent = false;
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
      signatureValue = createSignature(body, timestamp, nonce);
      headers[signatureHeader] = signatureValue;
      headers[signatureTimestampHeader] = timestamp;
      headers[signatureNonceHeader] = nonce;
      headers[signatureAlgorithmHeader] = signatureAlgorithm;
      headers[signatureEncodingHeader] = signatureEncoding;
      headers[signatureVersionHeader] = signatureVersion;
      if (signatureKeyId) {
        headers[signatureKeyIdHeader] = signatureKeyId;
      }
    }
    const res = await fetch(target.url, {
      method: "POST",
      headers,
      body
    });
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
        signature_value: signatureValue || undefined,
        signature_key_id: signatureKeyId || undefined
      });
      break;
    }
    if (attempt <= retries) {
      await sleep(retryDelayMs);
      continue;
    }
    dispatches.push({
      target: target.url,
      channel: target.channel,
      ok: false,
      attempt,
      http_status: res.status,
      signed: !!signingSecret
    });
    writeStatus({
      ok: false,
      skipped: false,
      reason_code: "PUBLISH_HTTP_ERROR",
      target: target.url,
      channel: target.channel,
      http_status: res.status,
      dispatches
    });
    throw new Error(`publish closeout governance dashboard failed: http ${res.status} target=${target.url}`);
  }
  if (!sent) {
    throw new Error(`publish closeout governance dashboard failed: target=${target.url}`);
  }
}

writeStatus({
  ok: true,
  skipped: false,
  reason_code: "OK",
  retries,
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
        key_id_header: signatureKeyIdHeader,
        algorithm: signatureAlgorithm,
        encoding: signatureEncoding,
        prefix: signaturePrefix,
        version: signatureVersion,
        key_id: signatureKeyId || undefined
      }
    : null,
  dispatches
});
