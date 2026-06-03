# Native Alert Signature Rollout Plan

## 1. Owner Matrix

### Backend Owner

- Implement online signature verification endpoint logic.
- Enforce canonical string verification: `<timestamp>\n<nonce>\n<body>`.
- Add timestamp skew check and nonce replay rejection.
- Expose structured error codes and verification metrics.

### DevOps Owner

- Provision and rotate signing secret in secret manager.
- Prepare replay store (Redis preferred) and TTL policy.
- Configure monitoring dashboard and failure alerts.
- Validate backout switch and incident response path.

### CI Admin Owner

- Keep `VERIFY_REQUIRED=false` during initial online shadow phase.
- Enable canary branch required verify once telemetry is stable.
- Enable main branch required verify after canary acceptance.
- Maintain Step Summary visibility and failure triage links.

## 2. Rollout Timeline Template

Use the following template for real execution dates:

```text
Phase A (Day 1-2): Online Shadow
- VERIFY_REQUIRED=false
- Server verify enabled (log/metrics only)
- Target: verify failure rate < 5%

Phase B (Day 3-4): Canary Required
- VERIFY_REQUIRED=true on canary branches only
- Target: no unexplained blocking failures for 48h

Phase C (Day 5-7): Main Required
- VERIFY_REQUIRED=true on main branch
- Target: stable pass rate and no replay false positives

Phase D (Day 8+): Stabilize
- Remove temporary compatibility logic
- Confirm runbook and rotation cadence
```

## 3. Stage Gates

- Gate A -> B:
  - Failure reason distribution is explained and actionable.
  - Replay store latency and availability meet SLO.
- Gate B -> C:
  - Canary required mode stable for at least 2 days.
  - No unknown `SIGNATURE_MISMATCH` incidents.
- Gate C -> D:
  - 7 days stable in main required mode.
  - Alert noise remains under agreed threshold.

## 4. Escalation Rules

- Immediate rollback to `VERIFY_REQUIRED=false` when:
  - Main branch verify failures spike above 10% in 10 minutes.
  - Replay store outage blocks online verification.
  - Unknown signature mismatches impact delivery continuity.
- Notify:
  - Backend owner
  - DevOps owner
  - On-call incident commander

## 5. Evidence Artifacts

- CI Step Summary snapshots (publish + verify status).
- Server verify metrics dashboard screenshots.
- Replay store health report.
- Incident/backout drill records.

