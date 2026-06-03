import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const outputPath = process.env.NATIVE_PLAYER_INTEGRATION_REPORT_PATH || "scripts/native-player-integration.report.json";
const statusPath = process.env.NATIVE_PLAYER_INTEGRATION_FETCH_STATUS_PATH || "scripts/native-player-integration.fetch-status.json";
const sourceFile = process.env.NATIVE_PLAYER_INTEGRATION_REPORT_SOURCE_FILE || "";
const apiUrl = process.env.NATIVE_PLAYER_INTEGRATION_REPORT_API_URL || "";
const apiToken = process.env.NATIVE_PLAYER_INTEGRATION_REPORT_API_TOKEN || "";
const maxRetries = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_FETCH_RETRIES || 2));
const retryDelayMs = Math.max(0, Number(process.env.NATIVE_PLAYER_INTEGRATION_FETCH_RETRY_DELAY_MS || 1200));
const timeoutMs = Math.max(1000, Number(process.env.NATIVE_PLAYER_INTEGRATION_FETCH_TIMEOUT_MS || 10000));

const outputFile = resolve(process.cwd(), outputPath);
const statusFile = resolve(process.cwd(), statusPath);
mkdirSync(dirname(outputFile), { recursive: true });
mkdirSync(dirname(statusFile), { recursive: true });

function log(message) {
  console.log(`[fetch-native-player-integration-report] ${message}`);
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
      lastErrorCode = "HTTP_ERROR";
      lastErrorMessage = `http ${res.status} while fetching report`;
      lastHttpStatus = res.status;
      throw new Error(lastErrorMessage);
    }
    const raw = await res.text();
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

    // Accept either direct report object or wrapped object: { report: {...} }.
    const report =
      parsed && typeof parsed === "object" && parsed.report && typeof parsed.report === "object" ? parsed.report : parsed;
    writeFileSync(outputFile, `${JSON.stringify(report, null, 2)}\n`, "utf8");

    // Quick sanity readback to avoid writing malformed file.
    JSON.parse(readFileSync(outputFile, "utf8"));
    writeStatus({
      ok: true,
      source: "api",
      reason_code: "OK",
      message: `saved report to ${outputPath}`,
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
throw new Error(`${lastErrorCode}: ${lastErrorMessage}`);
