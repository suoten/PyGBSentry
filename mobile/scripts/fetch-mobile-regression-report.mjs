import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const outputPath = process.env.MOBILE_REGRESSION_REPORT_PATH || "scripts/mobile-regression-report.json";
const statusPath = process.env.MOBILE_REGRESSION_FETCH_STATUS_PATH || "scripts/mobile-regression.fetch-status.json";
const sourceFile = process.env.MOBILE_REGRESSION_REPORT_SOURCE_FILE || "";
const apiUrl = process.env.MOBILE_REGRESSION_REPORT_API_URL || "";
const apiToken = process.env.MOBILE_REGRESSION_REPORT_API_TOKEN || "";
const maxRetries = Math.max(0, Number(process.env.MOBILE_REGRESSION_FETCH_RETRIES || 2));
const retryDelayMs = Math.max(0, Number(process.env.MOBILE_REGRESSION_FETCH_RETRY_DELAY_MS || 1200));
const timeoutMs = Math.max(1000, Number(process.env.MOBILE_REGRESSION_FETCH_TIMEOUT_MS || 10000));
const tokenExpiresAt = process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_EXPIRES_AT || "";
const tokenExpiresSoonSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_EXPIRES_SOON_SEC || 86400));
const maxResponseBytes = Math.max(1024, Number(process.env.MOBILE_REGRESSION_FETCH_MAX_RESPONSE_BYTES || 1048576));
const fallbackFile = process.env.MOBILE_REGRESSION_REPORT_FALLBACK_FILE || "";
const allowStaleOnFailure = String(process.env.MOBILE_REGRESSION_FETCH_ALLOW_STALE_ON_FAILURE || "false").toLowerCase() === "true";
const staleMaxAgeSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_FETCH_STALE_MAX_AGE_SEC || 86400));

const outputFile = resolve(process.cwd(), outputPath);
const statusFile = resolve(process.cwd(), statusPath);
mkdirSync(dirname(outputFile), { recursive: true });
mkdirSync(dirname(statusFile), { recursive: true });

function log(message) {
  console.log(`[fetch-mobile-regression-report] ${message}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function writeStatus(payload) {
  writeFileSync(
    statusFile,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        ...payload
      },
      null,
      2
    )}\n`,
    "utf8"
  );
}

function parseDateMs(value) {
  if (!value) return Number.NaN;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function useFallback(reasonCode, message, extra = {}) {
  if (fallbackFile) {
    const fallback = resolve(process.cwd(), fallbackFile);
    if (existsSync(fallback)) {
      copyFileSync(fallback, outputFile);
      JSON.parse(readFileSync(outputFile, "utf8"));
      writeStatus({
        ok: true,
        degraded: true,
        source: "fallback_file",
        reason_code: reasonCode,
        message,
        fallback_file: fallbackFile,
        ...extra
      });
      log(`degraded fallback used: ${fallbackFile}`);
      process.exit(0);
    }
  }

  if (allowStaleOnFailure && existsSync(outputFile)) {
    const mtimeMs = statSync(outputFile).mtimeMs;
    const ageSec = Math.floor((Date.now() - mtimeMs) / 1000);
    if (ageSec <= staleMaxAgeSec) {
      JSON.parse(readFileSync(outputFile, "utf8"));
      writeStatus({
        ok: true,
        degraded: true,
        source: "stale_output",
        reason_code: reasonCode,
        message,
        stale_age_sec: ageSec,
        stale_max_age_sec: staleMaxAgeSec,
        ...extra
      });
      log(`degraded stale output used: age=${ageSec}s`);
      process.exit(0);
    }
  }
}

if (sourceFile) {
  const source = resolve(process.cwd(), sourceFile);
  if (!existsSync(source)) {
    writeStatus({ ok: false, reason_code: "SOURCE_FILE_NOT_FOUND", message: `source file not found: ${sourceFile}` });
    throw new Error(`SOURCE_FILE_NOT_FOUND: source file not found: ${sourceFile}`);
  }
  copyFileSync(source, outputFile);
  writeStatus({ ok: true, source: "file", reason_code: "OK", message: `copied from source file: ${sourceFile}` });
  log(`copied from source file: ${sourceFile} -> ${outputPath}`);
  process.exit(0);
}

if (!apiUrl) {
  writeStatus({ ok: false, source: "api", reason_code: "API_URL_MISSING", message: "api url not configured" });
  log("skip: api url not configured");
  process.exit(0);
}

if (tokenExpiresAt) {
  const expiresAtMs = parseDateMs(tokenExpiresAt);
  if (Number.isNaN(expiresAtMs)) {
    writeStatus({
      ok: false,
      source: "api",
      reason_code: "TOKEN_EXPIRES_AT_INVALID",
      message: `invalid token expires_at: ${tokenExpiresAt}`
    });
    throw new Error(`TOKEN_EXPIRES_AT_INVALID: invalid token expires_at: ${tokenExpiresAt}`);
  }
  const nowMs = Date.now();
  if (nowMs >= expiresAtMs) {
    useFallback("API_TOKEN_EXPIRED", "api token expired");
    writeStatus({
      ok: false,
      source: "api",
      reason_code: "API_TOKEN_EXPIRED",
      message: "api token expired",
      token_expires_at: tokenExpiresAt
    });
    throw new Error("API_TOKEN_EXPIRED: api token expired");
  }
}

const headers = {};
if (apiToken) {
  headers.Authorization = `Bearer ${apiToken}`;
}

let lastErrorCode = "UNKNOWN_FETCH_ERROR";
let lastErrorMessage = "unknown fetch error";
let lastHttpStatus = 0;

for (let attempt = 1; attempt <= maxRetries + 1; attempt += 1) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(apiUrl, { headers, signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) {
      lastErrorCode = res.status === 429 ? "RATE_LIMITED" : "HTTP_ERROR";
      lastErrorMessage = `http ${res.status} while fetching report`;
      lastHttpStatus = res.status;
      if (res.status === 429 && attempt <= maxRetries) {
        const retryAfter = Number(res.headers.get("retry-after") || 0);
        const retryAfterMs = retryAfter > 0 ? retryAfter * 1000 : retryDelayMs;
        log(`rate limited (429), retrying after ${retryAfterMs}ms...`);
        await sleep(retryAfterMs);
        continue;
      }
      throw new Error(lastErrorMessage);
    }
    const raw = await res.text();
    if (Buffer.byteLength(raw, "utf8") > maxResponseBytes) {
      lastErrorCode = "RESPONSE_TOO_LARGE";
      lastErrorMessage = `response too large: > ${maxResponseBytes} bytes`;
      throw new Error(lastErrorMessage);
    }
    if (!raw.trim()) {
      lastErrorCode = "EMPTY_BODY";
      lastErrorMessage = "empty response body";
      throw new Error(lastErrorMessage);
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      lastErrorCode = "INVALID_JSON";
      lastErrorMessage = "response is not valid json";
      throw new Error(lastErrorMessage);
    }

    const report =
      parsed && typeof parsed === "object" && parsed.report && typeof parsed.report === "object" ? parsed.report : parsed;
    writeFileSync(outputFile, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    JSON.parse(readFileSync(outputFile, "utf8"));
    writeStatus({
      ok: true,
      source: "api",
      reason_code: "OK",
      message: `saved report to ${outputPath}`,
      token_expires_at: tokenExpiresAt || undefined,
      token_expires_soon: tokenExpiresAt ? Date.now() + tokenExpiresSoonSec * 1000 >= parseDateMs(tokenExpiresAt) : false,
      attempts: attempt,
      retries: maxRetries,
      http_status: lastHttpStatus
    });
    log(`saved report to ${outputPath}`);
    process.exit(0);
  } catch (err) {
    if (lastErrorCode === "UNKNOWN_FETCH_ERROR") {
      const message = String((err && err.message) || err || "");
      if (message.toLowerCase().includes("abort")) {
        lastErrorCode = "REQUEST_TIMEOUT";
        lastErrorMessage = `request timeout after ${timeoutMs}ms`;
      } else {
        lastErrorCode = "REQUEST_FAILED";
        lastErrorMessage = message || "request failed";
      }
    }
    if (attempt <= maxRetries) {
      log(`attempt ${attempt} failed (${lastErrorCode}), retrying...`);
      await sleep(retryDelayMs);
      continue;
    }
  }
}

writeStatus({
  ok: false,
  source: "api",
  reason_code: lastErrorCode,
  message: lastErrorMessage,
  attempts: maxRetries + 1,
  retries: maxRetries,
  http_status: lastHttpStatus
});
useFallback(lastErrorCode, lastErrorMessage, {
  attempts: maxRetries + 1,
  retries: maxRetries,
  http_status: lastHttpStatus
});
throw new Error(`${lastErrorCode}: ${lastErrorMessage}`);
