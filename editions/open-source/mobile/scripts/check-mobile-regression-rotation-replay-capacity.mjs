import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const required = String(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_CAPACITY_REQUIRED || "false").toLowerCase() === "true";
const policyEnv = String(process.env.MOBILE_REGRESSION_POLICY_ENV || "dev").toLowerCase();
const statusPath =
  process.env.MOBILE_REGRESSION_ROTATION_REPLAY_CAPACITY_STATUS_PATH || "scripts/mobile-regression.rotation-replay-capacity-status.json";

const ttlSec = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_VERIFY_NONCE_TTL_SEC || 900));
const peakQps = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_STORE_PEAK_QPS || 1));
const burstFactor = Math.max(1, Number(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_STORE_BURST_FACTOR || 1.2));
const capacityRaw = String(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_STORE_CAPACITY || "");
const capacity = capacityRaw ? Number(capacityRaw) : Number.NaN;
const utilizationLimit = Math.max(0.1, Number(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_STORE_UTILIZATION_LIMIT || 0.8));
const headroomMin = Math.max(0, Number(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_STORE_HEADROOM_MIN || 500));
const provider = String(process.env.MOBILE_REGRESSION_ROTATION_REPLAY_STORE_PROVIDER || "redis");

function writeStatus(payload) {
  const file = resolve(process.cwd(), statusPath);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(
    file,
    `${JSON.stringify(
      {
        at: new Date().toISOString(),
        required,
        policy_env: policyEnv,
        provider,
        ...payload
      },
      null,
      2
    )}\n`,
    "utf8"
  );
}

function fail(reasonCode, message, extra = {}) {
  writeStatus({ ok: false, reason_code: reasonCode, message, ...extra });
  throw new Error(`[mobile-regression-rotation-replay-capacity] ${reasonCode}: ${message}`);
}

function ok(reasonCode, message, extra = {}) {
  writeStatus({ ok: true, reason_code: reasonCode, message, ...extra });
  console.log(`[mobile-regression-rotation-replay-capacity] ${reasonCode}: ${message}`);
}

const strictMode = required || policyEnv === "prod";
const requiredKeys = Math.ceil(peakQps * ttlSec * burstFactor);

if (Number.isNaN(capacity)) {
  if (strictMode) {
    fail("REPLAY_CAPACITY_MISSING", "replay store capacity is required in strict mode", {
      required_keys: requiredKeys
    });
  }
  ok("SKIPPED", "replay store capacity not configured, strictMode=false", { required_keys: requiredKeys });
  process.exit(0);
}

if (capacity <= 0) {
  fail("REPLAY_CAPACITY_INVALID", `invalid replay store capacity: ${capacity}`);
}

const utilization = Number((requiredKeys / capacity).toFixed(6));
const headroom = capacity - requiredKeys;

if (utilization > utilizationLimit) {
  fail("REPLAY_CAPACITY_UTILIZATION_HIGH", `utilization too high: ${utilization} > ${utilizationLimit}`, {
    required_keys: requiredKeys,
    capacity,
    utilization,
    utilization_limit: utilizationLimit
  });
}

if (headroom < headroomMin) {
  fail("REPLAY_CAPACITY_HEADROOM_LOW", `headroom too low: ${headroom} < ${headroomMin}`, {
    required_keys: requiredKeys,
    capacity,
    headroom,
    headroom_min: headroomMin
  });
}

ok("OK", "replay capacity check passed", {
  ttl_sec: ttlSec,
  peak_qps: peakQps,
  burst_factor: burstFactor,
  required_keys: requiredKeys,
  capacity,
  utilization,
  utilization_limit: utilizationLimit,
  headroom,
  headroom_min: headroomMin
});
