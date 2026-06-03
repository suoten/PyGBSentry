# Native Alert Weekly Report Signature Contract

## 1. Scope

This document defines the server-side verification contract for
`native_player_integration_alert_weekly_report` payloads published by
`editions/open-source/mobile/scripts/publish-native-integration-alert-report.mjs`.

The goal is to move from CI dry-run verification to online required verification
without changing signing semantics.

## 2. Request Model

### 2.1 Method and Body

- Method: `POST`
- Content-Type: `application/json`
- Body: JSON stringified payload sent by publisher

### 2.2 Signature Headers

Headers are configurable through CI variables, defaults shown below:

- `X-PyGBSentry-Signature`
- `X-PyGBSentry-Signature-Timestamp`
- `X-PyGBSentry-Signature-Nonce`
- `X-PyGBSentry-Signature-Algorithm`
- `X-PyGBSentry-Signature-Encoding`
- `X-PyGBSentry-Signature-Version`

Supported defaults:

- Algorithm: `sha256` (also allowed by current scripts: `sha1`, `sha512`)
- Encoding: `hex` (also allowed: `base64`)
- Prefix: `hmac`
- Version: `v1`

Signature field format:

```text
<prefix>-<algorithm>-<encoding>=<digest>
```

Example:

```text
hmac-sha256-hex=5f4dcc3b5aa765d61d8327deb882cf99...
```

## 3. Canonical String

Server must use exactly the same canonical string as publisher:

```text
<timestamp>\n<nonce>\n<body>
```

- `timestamp`: unix epoch seconds string
- `nonce`: UUID-like random string
- `body`: raw request body bytes interpreted as UTF-8 string

> Important: verify against the raw body string received over HTTP. Do not
> re-serialize JSON on server before verification.

## 4. Verification Steps

1. Validate required headers exist.
2. Validate algorithm/encoding/version are in allowlist.
3. Validate timestamp skew:
   - default max skew: `300s`
4. Validate nonce replay:
   - nonce must be unseen in TTL window
   - default TTL: `900s`
5. Recompute signature with shared secret.
6. Compare with provided signature in constant time.

## 5. Replay Store Design

Recommended nonce storage:

- Redis preferred:
  - key: `pygbsentry:weekly-report:nonce:<nonce>`
  - value: request metadata (`ts`, `repo`, `run_id`) or `1`
  - ttl: `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_NONCE_TTL_SEC`
- DB fallback:
  - unique index on `(nonce)`
  - cleanup job by `created_at` + TTL

## 6. Error Codes

Suggested server error code mapping (align with CI verify statuses):

- `SIGNATURE_HEADER_MISSING`
- `SIGNATURE_CONFIG_INVALID`
- `TIMESTAMP_INVALID`
- `TIMESTAMP_EXPIRED`
- `NONCE_MISSING`
- `NONCE_REPLAY`
- `SIGNATURE_MISMATCH`
- `VERIFY_SECRET_MISSING`

## 7. Rollout Plan

1. Keep CI verify in non-blocking mode (`VERIFY_REQUIRED=false`) while server
   endpoint is deployed.
2. Enable server-side verification logging and replay-store metrics.
3. Turn on CI required verify (`VERIFY_REQUIRED=true`) in canary branches.
4. Roll to main branch required mode after 3-7 days stable telemetry.

## 8. Config Mapping

Primary CI/env keys used by current scripts:

- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNING_SECRET`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_HEADER`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_TIMESTAMP_HEADER`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_NONCE_HEADER`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ALGORITHM_HEADER`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ENCODING_HEADER`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_VERSION_HEADER`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ALGORITHM`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_ENCODING`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_PREFIX`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_SIGNATURE_VERSION`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_REQUIRED`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_MAX_TIMESTAMP_SKEW_SEC`
- `NATIVE_PLAYER_INTEGRATION_ALERT_REPORT_VERIFY_NONCE_TTL_SEC`

## 9. Execution Checklist

Use the rollout checklist for backend implementation and launch:

- `editions/open-source/docs/NATIVE_ALERT_REPORT_SIGNATURE_ONLINE_CHECKLIST.md`
- `editions/open-source/docs/NATIVE_ALERT_REPORT_SIGNATURE_ROLLOUT_PLAN.md`
