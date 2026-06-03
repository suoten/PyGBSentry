# Mobile Regression Rotation Signature Contract

## 1. Scope

This contract defines server-side verification rules for:

- `mobile_regression_rotation_weekly_report`
- `mobile_regression_rotation_trend_alert`

Payloads are emitted by:

- `publish-mobile-regression-rotation-report.mjs`
- `notify-mobile-regression-rotation-trend.mjs`

## 2. Signature Model

### 2.1 Headers

Default headers (all configurable by env/vars):

- `X-PyGBSentry-Signature`
- `X-PyGBSentry-Signature-Timestamp`
- `X-PyGBSentry-Signature-Nonce`
- `X-PyGBSentry-Signature-Algorithm`
- `X-PyGBSentry-Signature-Encoding`
- `X-PyGBSentry-Signature-Version`
- `X-PyGBSentry-Signature-Key-Id`

### 2.2 Signature Value

```text
<prefix>-<algorithm>-<encoding>=<digest>
```

Defaults:

- algorithm: `sha256`
- encoding: `hex`
- prefix: `hmac`
- version: `v1`

### 2.3 Canonical String

```text
<timestamp>\n<nonce>\n<body>
```

Server must verify against raw body string (no JSON re-serialization).

## 3. Verification Rules

1. Required headers present.
2. `key_id` recognized and mapped to active verification key.
3. timestamp skew within configured window (`default 300s`).
4. nonce replay rejected within TTL (`default 900s`).
5. signature recomputed with selected key and compared in constant time.

## 4. Key Rotation

- Maintain key ring keyed by `key_id`.
- Allow overlap window for old/new key ids.
- Recommended rollout:
  - Add new key id (verify only)
  - Switch sender key id
  - Retire old key id after stability window

## 5. Replay Store

Recommended nonce key:

```text
rotation-signature:<key_id>:<nonce>
```

- Redis TTL preferred.
- Persist reasoned reject metrics for replay attempts.

## 6. Error Codes

- `SIGNATURE_HEADER_MISSING`
- `SIGNATURE_KEY_ID_MISMATCH`
- `TIMESTAMP_INVALID`
- `TIMESTAMP_EXPIRED`
- `NONCE_MISSING`
- `NONCE_REPLAY`
- `SIGNATURE_MISMATCH`
- `VERIFY_SECRET_MISSING`

## 7. CI Gray Switch

Use repository variables:

- `MOBILE_REGRESSION_ROTATION_PUBLISH_VERIFY_REQUIRED`
- `MOBILE_REGRESSION_ROTATION_ALERT_VERIFY_REQUIRED`
- `MOBILE_REGRESSION_ROTATION_ALERT_REQUIRED`

Recommended sequence:

1. all `false` (observe only)
2. canary branches `true`
3. main `true` after stable telemetry

## 8. Closeout Alert Governance

Closeout alert trigger policy supports global + environment override:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_REASON_CODES`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_REASON_CODES_PROD`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_REASON_CODES_CANARY`

Resolution order:

1. use env-specific list when non-empty (`prod` / `canary`)
2. fallback to global list

Closeout level mapping supports dedicated override:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_LEVEL_OVERRIDES`
- format: `REASON_CODE=error|warning|info,...`
- final level precedence:
  1. `MOBILE_REGRESSION_ROTATION_ALERT_LEVEL_OVERRIDES`
  2. `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_LEVEL_OVERRIDES`
  3. closeout default (`*_OUT_OF_WINDOW`/`*_INVALID` => `error`, others => `warning`)

Closeout mute list supports global + environment override:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_MUTE_REASON_CODES`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_MUTE_REASON_CODES_PROD`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_MUTE_REASON_CODES_CANARY`

Resolution order:

1. use env-specific list when non-empty (`prod` / `canary`)
2. fallback to global list

Closeout dedupe window template supports global + environment override:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_DEDUPE_WINDOW_SEC_MAP`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_DEDUPE_WINDOW_SEC_MAP_PROD`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_ALERT_DEDUPE_WINDOW_SEC_MAP_CANARY`
- format: `REASON_CODE=seconds,...`

Dedupe window precedence:

1. closeout env-specific reason map
2. closeout global reason map
3. generic `MOBILE_REGRESSION_ROTATION_ALERT_DEDUPE_WINDOW_SEC`

## 9. Consumer Field Mapping

For `mobile_regression_rotation_trend_alert` payload:

- `reason_code`: unified top-level alert reason (rotation threshold or closeout)
- `level`: final routed level
- `closeout_risk`: whether closeout reason matched active risk list
- `closeout_reason_code`: raw closeout check reason
- `closeout_alert_reason_codes`: effective risk reason list (after env override resolution)
- `closeout_status`: full closeout snapshot from check status file
- `closeout_signal.reason_code`: normalized closeout reason for server rules
- `closeout_signal.risk_matched`: same semantic as `closeout_risk`
- `closeout_signal.recommended_level`: resolved closeout level before routing
- `closeout_signal.level_source`: `closeout_level_override` or `closeout_default`
- `closeout_mute_reason_codes`: effective closeout mute list (after env override resolution)
- `policy_audit`: effective policy snapshot for explainability/audit
- `policy_audit.closeout_reason_codes.source`: `global|prod|canary`
- `policy_audit.closeout_mute_reason_codes.source`: `global|prod|canary`
- `policy_audit.closeout_dedupe_window_sec_map.source`: `global|prod|canary`
- `policy_audit.dedupe_window_sec_effective`: resolved dedupe window for current event

Server consumers should:

1. trust `reason_code` + `level` for routing
2. use `closeout_signal.*` for policy audit and explanation
3. persist `closeout_alert_reason_codes` with alert event for replay/debug
4. persist `policy_audit` when event is `MUTED` or `DEDUPED` for change-trace

## 10. Governance Baseline Gate

Closeout governance baseline can be enforced by CI gate:

- script: `check-mobile-regression-rotation-closeout-governance-baseline.mjs`
- baseline file: `mobile-regression-rotation.closeout-governance.baseline.json`
- status file: `mobile-regression.rotation-closeout-governance-baseline-status.json`

Gate controls:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_REQUIRED`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_PATH`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_STATUS_PATH`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_BASELINE_MAX_REVIEW_AGE_DAYS`

Baseline must include:

- owner + approvers (>=2)
- quarterly review cadence (`review_cycle_days`)
- `last_reviewed_at` within max review age
- change-control rollback metadata (`approver_group`, `rollback_runbook_id`, `rollback_checklist_id`)
- env defaults for `prod` and `canary`:
  - `risk_reason_codes`
  - `mute_reason_codes`
  - `dedupe_window_sec_map`

## 11. Quarterly Review Reminder Gate

Quarterly governance review reminder can be enforced by CI gate:

- script: `check-mobile-regression-rotation-closeout-governance-review-reminder.mjs`
- status file: `mobile-regression.rotation-closeout-governance-review-reminder-status.json`

Gate controls:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_REMINDER_REQUIRED`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_REMINDER_STATUS_PATH`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_GOVERNANCE_REVIEW_DUE_SOON_DAYS`

Reminder reason codes:

- `OK`: review still healthy
- `CLOSEOUT_GOV_REVIEW_DUE_SOON`: within due-soon window
- `CLOSEOUT_GOV_REVIEW_OVERDUE`: review already overdue

Recommended service-side handling:

1. treat `CLOSEOUT_GOV_REVIEW_DUE_SOON` as warning notification
2. treat `CLOSEOUT_GOV_REVIEW_OVERDUE` as error notification and require owner action
3. persist `review_due_at` + `review_days_until_due` for dashboard trend

## 12. Unified Dashboard Aggregation

Unified dashboard builder:

- script: `build-mobile-regression-rotation-closeout-governance-dashboard.mjs`
- outputs:
  - `mobile-regression.rotation-closeout-dashboard.json`
  - `mobile-regression.rotation-closeout-dashboard.md`

Data sources:

- `mobile-regression.rotation-alert-status.json`
- `mobile-regression.rotation-closeout-governance-review-reminder-status.json`
- `mobile-regression.rotation-closeout-governance-baseline-status.json`
- history archives:
  - `mobile-regression.rotation-closeout-alert-history.json`
  - `mobile-regression.rotation-closeout-review-history.json`

Dashboard trend sections:

- alert reason trend (`trends.alerts.by_reason_code`)
- closeout reason trend (`trends.alerts.by_closeout_reason_code`)
- review reminder trend (`trends.reviews.by_reason_code`)
- latest snapshots (`latest.alert`, `latest.review`, `latest.baseline`)

## 13. Dashboard Publish Contract

Dashboard publish builder:

- script: `publish-mobile-regression-rotation-closeout-governance-dashboard.mjs`
- status file: `mobile-regression.rotation-closeout-dashboard-publish-status.json`

Publish controls:

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_REQUIRED`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_STATUS_PATH`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URL`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_TOKEN`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URL_PROD`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URL_CANARY`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_TOKEN_PROD`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_TOKEN_CANARY`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_WEBHOOK_URLS`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_RETRIES`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_PUBLISH_RETRY_DELAY_MS`

Optional request signing (same canonical model):

- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNING_SECRET`
- `MOBILE_REGRESSION_ROTATION_CLOSEOUT_DASHBOARD_SIGNATURE_*`

Payload contract:

- `type=mobile_regression_rotation_closeout_governance_dashboard`
- `markdown`: rendered dashboard text
- `dashboard`: full JSON dashboard object
- `repository`, `branch`, `run_id`, `generated_at`, `window_days`, `policy_env`

## 14. Backend Persistence API

Open-source backend provides closeout dashboard persistence/query endpoints:

- `POST /api/v1/reports/mobile-regression/closeout-governance-dashboard/ingest`
- `GET /api/v1/reports/mobile-regression/closeout-governance-dashboard/latest`
- `GET /api/v1/reports/mobile-regression/closeout-governance-dashboard/history`
- `GET /api/v1/reports/mobile-regression/closeout-governance-dashboard/summary`
- `GET /api/v1/reports/mobile-regression/closeout-governance-dashboard/drilldown`

Ingest behavior:

- accepted roles: `owner|admin|operator`
- idempotency:
  - prefer payload `idempotency_key`
  - fallback auto-key: `tenant_id|run_id|generated_at|policy_env|window_days` hash
- local store file:
  - `editions/open-source/backend/data/reports/mobile-regression-rotation-closeout-governance-dashboard-events.json`
- max entries controlled by env:
  - `MOBILE_CLOSEOUT_DASHBOARD_STORE_MAX_ENTRIES` (default `2000`)

History query:

- supports `limit`, `offset`
- supports filters: `policy_env`, `reason_code` (mapped from latest alert closeout reason)

Summary query:

- supports `days` window aggregation (1~180)
- returns:
  - `by_env`
  - `by_reason_code`
  - `by_closeout_reason_code`
  - `trend_by_day`
  - `latest`

Drilldown query:

- supports filters:
  - `policy_env`
  - `reason_code` (latest alert reason)
  - `closeout_reason_code` (latest alert closeout reason)
  - `received_day` (`YYYY-MM-DD`, match by `received_at` day)
- supports pagination: `limit`, `offset`
- supports `include_dashboard=true` to return full dashboard payload + markdown

## 15. Mobile Regression Credential Governance

Mobile regression fetch policy check supports credential governance controls:

- script: `check-mobile-regression-fetch-policy.mjs`
- status file: `mobile-regression.policy-status.json`

Credential policy controls:

- `MOBILE_REGRESSION_REPORT_API_URL`
- `MOBILE_REGRESSION_REPORT_API_TOKEN`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_EXPIRES_AT`
- `MOBILE_REGRESSION_REPORT_TOKEN_MIN_TTL_SEC`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_MIN_LENGTH`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_SOURCE`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_SOURCE_ALLOWED`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_SCOPES`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_REQUIRED_SCOPES`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_FORBIDDEN_SCOPES`
- `MOBILE_REGRESSION_REPORT_API_TOKEN_ENFORCE_MIN_PRIVILEGE`

Policy behavior:

1. canary/prod requires API URL + token + `expires_at`
2. enforce token min TTL and min length baseline
3. enforce allowed token source
4. enforce required scopes and reject forbidden scopes (least privilege)
5. prod forbids stale fallback policy

Credential policy reason codes:

- `REPORT_API_URL_MISSING`
- `TOKEN_MISSING`
- `TOKEN_TOO_SHORT`
- `TOKEN_EXPIRES_AT_MISSING`
- `TOKEN_EXPIRES_AT_INVALID`
- `TOKEN_EXPIRED`
- `TOKEN_ROTATION_REQUIRED`
- `TOKEN_SOURCE_MISSING`
- `TOKEN_SOURCE_NOT_ALLOWED`
- `TOKEN_SCOPES_MISSING`
- `TOKEN_SCOPE_INSUFFICIENT`
- `TOKEN_SCOPE_OVER_PRIVILEGED`
