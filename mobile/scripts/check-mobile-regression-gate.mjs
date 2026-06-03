import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const file = resolve(process.cwd(), "scripts/mobile-regression-gate.config.json");
const raw = readFileSync(file, "utf8");
const cfg = JSON.parse(raw);

const REQUIRED_DEVICE_TIERS = ["android_mid", "android_high", "ios_mainstream"];
const REQUIRED_NETWORK_PROFILES = ["lan", "4g", "weak_net_loss5_jitter120"];
const BASELINE = {
  min_success_rate: 80,
  max_avg_startup_ms: 4500,
  min_attempts: 20
};

function fail(message) {
  throw new Error(`[mobile-regression-gate] ${message}`);
}

if (!Array.isArray(cfg.device_tiers) || cfg.device_tiers.length === 0) {
  fail("device_tiers missing");
}
for (const tier of REQUIRED_DEVICE_TIERS) {
  if (!cfg.device_tiers.includes(tier)) {
    fail(`required device tier missing: ${tier}`);
  }
}

if (!Array.isArray(cfg.network_profiles) || cfg.network_profiles.length === 0) {
  fail("network_profiles missing");
}
for (const profile of REQUIRED_NETWORK_PROFILES) {
  if (!cfg.network_profiles.includes(profile)) {
    fail(`required network profile missing: ${profile}`);
  }
}

const t = cfg.release_blocking_thresholds || {};
const minSuccessRate = Number(t.min_success_rate);
const maxAvgStartupMs = Number(t.max_avg_startup_ms);
const minAttempts = Number(t.min_attempts);

if (Number.isNaN(minSuccessRate) || Number.isNaN(maxAvgStartupMs) || Number.isNaN(minAttempts)) {
  fail("release_blocking_thresholds has non-number value");
}

if (minSuccessRate < BASELINE.min_success_rate) {
  fail(`min_success_rate too low: ${minSuccessRate}, expected >= ${BASELINE.min_success_rate}`);
}
if (maxAvgStartupMs > BASELINE.max_avg_startup_ms) {
  fail(`max_avg_startup_ms too high: ${maxAvgStartupMs}, expected <= ${BASELINE.max_avg_startup_ms}`);
}
if (minAttempts < BASELINE.min_attempts) {
  fail(`min_attempts too low: ${minAttempts}, expected >= ${BASELINE.min_attempts}`);
}

console.log(
  `[mobile-regression-gate] ok: tiers=${cfg.device_tiers.length} networks=${cfg.network_profiles.length} ` +
    `thresholds(success>=${minSuccessRate}%, startup<=${maxAvgStartupMs}ms, attempts>=${minAttempts})`
);
