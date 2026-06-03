# Native Alert Signature Online Checklist

## 1. Pre-check

- [ ] Confirm weekly report receiver endpoint path and ownership.
- [ ] Confirm signing secret source (`Secrets Manager` / repo secret) and rotation owner.
- [ ] Confirm CI and server use the same header names and signature format.
- [ ] Confirm server can access stable replay store (Redis preferred).

## 2. Config Alignment

- [ ] `SIGNATURE_HEADER` is aligned.
- [ ] `SIGNATURE_TIMESTAMP_HEADER` is aligned.
- [ ] `SIGNATURE_NONCE_HEADER` is aligned.
- [ ] `SIGNATURE_ALGORITHM_HEADER` is aligned.
- [ ] `SIGNATURE_ENCODING_HEADER` is aligned.
- [ ] `SIGNATURE_VERSION_HEADER` is aligned.
- [ ] `SIGNATURE_ALGORITHM` allowlist includes current value.
- [ ] `SIGNATURE_ENCODING` allowlist includes current value.
- [ ] `SIGNATURE_PREFIX` and `SIGNATURE_VERSION` are aligned.

## 3. Canonical Verification

- [ ] Verify canonical string uses: `<timestamp>\n<nonce>\n<body>`.
- [ ] Verify server uses raw HTTP body string (no JSON re-serialization before sign).
- [ ] Verify signature comparison uses constant-time compare.
- [ ] Verify invalid/missing headers return explicit reason code.

## 4. Timestamp and Replay

- [ ] Configure max timestamp skew (`default: 300s`).
- [ ] Configure nonce TTL (`default: 900s`).
- [ ] Implement nonce replay reject in TTL window.
- [ ] Add nonce cleanup strategy (Redis TTL or DB retention job).
- [ ] Add replay metrics: total, replay_rejected, expired_rejected.

## 5. Observability

- [ ] Log request id, repo, run_id, verify result, reason_code (no secret leakage).
- [ ] Add metrics dashboard for verify pass/fail and failure reason distribution.
- [ ] Alert on verify failure spike (e.g., >5% in 10min).
- [ ] Expose failure samples to on-call with masked signature fields.

## 6. Rollout

- [ ] Stage A: CI verify non-blocking (`VERIFY_REQUIRED=false`), server verify enabled.
- [ ] Stage B: Canary branches enable required verify.
- [ ] Stage C: Main branch enable required verify.
- [ ] Stage D: Remove temporary compatibility logic after stable period.

## 7. Backout

- [ ] Emergency switch documented (`VERIFY_REQUIRED=false`).
- [ ] Keep receiver endpoint available while bypassing verify for recovery window.
- [ ] Incident template prepared for signature mismatch/replay incidents.
- [ ] Secret rotate runbook validated.

## 8. Acceptance Criteria

- [ ] 7 consecutive days with no unexplained verify failures in main branch.
- [ ] Replay rejection behaves as expected in synthetic tests.
- [ ] Timestamp skew boundary tests pass (`+/- max skew`).
- [ ] Observability dashboard and alert policy reviewed by backend/on-call owners.

## 9. References

- `editions/open-source/docs/NATIVE_ALERT_REPORT_SIGNATURE_CONTRACT.md`
- `editions/open-source/docs/NATIVE_ALERT_REPORT_SIGNATURE_ROLLOUT_PLAN.md`
