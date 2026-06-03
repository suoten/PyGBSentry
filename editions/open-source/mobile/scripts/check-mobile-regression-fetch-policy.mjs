import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const policyRequired = String(process.env.MOBILE_REGRESSION_POLICY_REQUIRED || "false").toLowerCase() === "true";
const requiredGate = String(process.env.MOBILE_REGRESSION_REQUIRED || "false").toLowerCase() === "true";
const reportApiUrl = String(process.env.MOBILE_REGRESSION_REPORT_API_URL || "").trim();
const reportApiToken = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN || "");
const tokenExpiresAt = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_EXPIRES_AT || "");
const tokenMinTtlSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_REPORT_TOKEN_MIN_TTL_SEC || 604800));
const tokenMinLength = Math.max(0, Number(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_MIN_LENGTH || 20));
const tokenSource = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_SOURCE || "").trim().toLowerCase();
const tokenSourceAllowed = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_SOURCE_ALLOWED || "secrets")
  .split(",")
  .map((x) => String(x || "").trim().toLowerCase())
  .filter(Boolean);
const tokenScopes = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_SCOPES || "")
  .split(",")
  .map((x) => String(x || "").trim().toLowerCase())
  .filter(Boolean);
const requiredScopes = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_REQUIRED_SCOPES || "mobile-regression.read")
  .split(",")
  .map((x) => String(x || "").trim().toLowerCase())
  .filter(Boolean);
const forbiddenScopes = String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_FORBIDDEN_SCOPES || "admin,write:*")
  .split(",")
  .map((x) => String(x || "").trim().toLowerCase())
  .filter(Boolean);
const enforceMinPrivilege =
  String(process.env.MOBILE_REGRESSION_REPORT_API_TOKEN_ENFORCE_MIN_PRIVILEGE || "false").toLowerCase() === "true";
const allowStaleOnFailure = String(process.env.MOBILE_REGRESSION_FETCH_ALLOW_STALE_ON_FAILURE || "false").toLowerCase() === "true";
const fallbackFile = String(process.env.MOBILE_REGRESSION_REPORT_FALLBACK_FILE || "");
const staleMaxAgeSec = Math.max(0, Number(process.env.MOBILE_REGRESSION_FETCH_STALE_MAX_AGE_SEC || 86400));
const statusPath = process.env.MOBILE_REGRESSION_POLICY_STATUS_PATH || "scripts/mobile-regression.policy-status.json";

function writeStatus(payload) {
  const file = resolve(process.cwd(), statusPath);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(
    file,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        policy_env: policyEnv,
        policy_required: policyRequired,
        required_gate: requiredGate,
        ...payload
      },
      null,
      2
    )}\n`,
    "utf8"
  );
}

function parseDateMs(v) {
  if (!v) return Number.NaN;
  const ms = Date.parse(v);
  return Number.isNaN(ms) ? Number.NaN : ms;
}

function fail(reasonCode, message, extra = {}) {
  writeStatus({
    ok: false,
    reason_code: reasonCode,
    message,
    ...extra
  });
  throw new Error(`[mobile-regression-policy] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({
    ok: true,
    reason_code: reasonCode,
    message,
    ...extra
  });
  console.log(`[mobile-regression-policy] ${reasonCode}: ${message}`);
}

const tokenExpiresAtMs = parseDateMs(tokenExpiresAt);
const nowMs = Date.now();
const tokenTtlSec = Number.isNaN(tokenExpiresAtMs) ? -1 : Math.floor((tokenExpiresAtMs - nowMs) / 1000);

const strictPolicy = policyRequired || requiredGate || policyEnv === "prod";
const strictOrCanary = strictPolicy || policyEnv === "canary";
if (strictOrCanary && !reportApiUrl) {
  fail("REPORT_API_URL_MISSING", "report api url is required for canary/prod policy");
}
if (strictOrCanary && !reportApiToken) {
  fail("TOKEN_MISSING", "report api token is required for canary/prod policy");
}
if (reportApiToken && tokenMinLength > 0 && reportApiToken.length < tokenMinLength) {
  fail("TOKEN_TOO_SHORT", `token length too short: ${reportApiToken.length} < ${tokenMinLength}`);
}
if ((strictPolicy || policyEnv === "canary") && !tokenExpiresAt) {
  fail("TOKEN_EXPIRES_AT_MISSING", "token expires_at is required for canary/prod policy");
}
if (tokenExpiresAt && Number.isNaN(tokenExpiresAtMs)) {
  fail("TOKEN_EXPIRES_AT_INVALID", `invalid token expires_at: ${tokenExpiresAt}`);
}
if (tokenExpiresAt && tokenTtlSec <= 0) {
  fail("TOKEN_EXPIRED", "token already expired", { token_expires_at: tokenExpiresAt, token_ttl_sec: tokenTtlSec });
}
if (tokenExpiresAt && tokenTtlSec > 0 && tokenTtlSec < tokenMinTtlSec) {
  fail("TOKEN_ROTATION_REQUIRED", `token ttl too short: ${tokenTtlSec}s < ${tokenMinTtlSec}s`, {
    token_expires_at: tokenExpiresAt,
    token_ttl_sec: tokenTtlSec,
    token_min_ttl_sec: tokenMinTtlSec
  });
}

if (policyEnv === "prod") {
  if (allowStaleOnFailure) {
    fail("STALE_NOT_ALLOWED_IN_PROD", "allow_stale_on_failure must be false in prod");
  }
  if (fallbackFile) {
    fail("FALLBACK_NOT_ALLOWED_IN_PROD", "fallback file should not be configured in prod");
  }
}

if (policyEnv === "canary") {
  if (allowStaleOnFailure && staleMaxAgeSec > 172800) {
    fail("STALE_WINDOW_TOO_LARGE", `stale_max_age_sec too large for canary: ${staleMaxAgeSec}`);
  }
}

if (strictOrCanary || enforceMinPrivilege) {
  if (!tokenSource) {
    fail("TOKEN_SOURCE_MISSING", "token source is required when min-privilege policy is enabled");
  }
  if (tokenSourceAllowed.length > 0 && !tokenSourceAllowed.includes(tokenSource)) {
    fail("TOKEN_SOURCE_NOT_ALLOWED", `token source not allowed: ${tokenSource}`, {
      token_source_allowed: tokenSourceAllowed
    });
  }
  if (requiredScopes.length > 0 && tokenScopes.length === 0) {
    fail("TOKEN_SCOPES_MISSING", "token scopes are required when min-privilege policy is enabled", {
      required_scopes: requiredScopes
    });
  }
  const missingRequiredScopes = requiredScopes.filter((scope) => !tokenScopes.includes(scope));
  if (missingRequiredScopes.length > 0) {
    fail("TOKEN_SCOPE_INSUFFICIENT", `token missing required scopes: ${missingRequiredScopes.join(",")}`, {
      required_scopes: requiredScopes,
      token_scopes: tokenScopes
    });
  }
  const matchedForbiddenScopes = forbiddenScopes.filter((scope) => tokenScopes.includes(scope));
  if (matchedForbiddenScopes.length > 0) {
    fail("TOKEN_SCOPE_OVER_PRIVILEGED", `token has forbidden scopes: ${matchedForbiddenScopes.join(",")}`, {
      forbidden_scopes: forbiddenScopes,
      token_scopes: tokenScopes
    });
  }
}

ok("OK", "mobile regression fetch policy check passed", {
  report_api_url: reportApiUrl || undefined,
  token_expires_at: tokenExpiresAt || undefined,
  token_length: reportApiToken ? reportApiToken.length : undefined,
  token_ttl_sec: tokenTtlSec > 0 ? tokenTtlSec : undefined,
  token_min_ttl_sec: tokenMinTtlSec,
  token_min_length: tokenMinLength || undefined,
  token_source: tokenSource || undefined,
  token_source_allowed: tokenSourceAllowed,
  token_scopes: tokenScopes,
  required_scopes: requiredScopes,
  forbidden_scopes: forbiddenScopes,
  enforce_min_privilege: enforceMinPrivilege,
  allow_stale_on_failure: allowStaleOnFailure,
  fallback_configured: !!fallbackFile,
  stale_max_age_sec: staleMaxAgeSec
});
