import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const cfgFile = resolve(process.cwd(), "scripts/mobile-regression-gate.config.json");
const reportPath = process.env.MOBILE_REGRESSION_REPORT_PATH || "scripts/mobile-regression-report.json";
const reportFile = resolve(process.cwd(), reportPath);
const required = String(process.env.MOBILE_REGRESSION_REQUIRED || "false").toLowerCase() === "true";

function fail(message) {
  throw new Error(`[mobile-regression-report] ${message}`);
}

if (!existsSync(reportFile)) {
  if (required) fail(`report file not found: ${reportPath}`);
  console.log(`[mobile-regression-report] skip: report not found (${reportPath}), required=false`);
  process.exit(0);
}

const cfg = JSON.parse(readFileSync(cfgFile, "utf8"));
const report = JSON.parse(readFileSync(reportFile, "utf8"));

const requiredTiers = Array.isArray(cfg.device_tiers) ? cfg.device_tiers : [];
const requiredNetworks = Array.isArray(cfg.network_profiles) ? cfg.network_profiles : [];
const thresholds = cfg.release_blocking_thresholds || {};

const minSuccessRate = Number(thresholds.min_success_rate);
const maxAvgStartupMs = Number(thresholds.max_avg_startup_ms);
const minAttempts = Number(thresholds.min_attempts);

if ([minSuccessRate, maxAvgStartupMs, minAttempts].some((x) => Number.isNaN(x))) {
  fail("invalid thresholds in config");
}

const results = Array.isArray(report.results) ? report.results : [];
if (results.length === 0) {
  fail("report.results is empty");
}

const tierSet = new Set();
const networkSet = new Set();
let totalAttempts = 0;
let weightedSuccessNumerator = 0;
let weightedStartupNumerator = 0;

for (const row of results) {
  const tier = String(row.device_tier || "");
  const profile = String(row.network_profile || "");
  const attempts = Number(row.attempts);
  const successRate = Number(row.success_rate);
  const avgStartup = Number(row.avg_startup_ms);
  if (!tier || !profile) fail("row missing device_tier/network_profile");
  if ([attempts, successRate, avgStartup].some((x) => Number.isNaN(x))) {
    fail(`row has non-number fields: ${tier}/${profile}`);
  }
  if (attempts <= 0) fail(`row attempts must be > 0: ${tier}/${profile}`);
  tierSet.add(tier);
  networkSet.add(profile);
  totalAttempts += attempts;
  weightedSuccessNumerator += successRate * attempts;
  weightedStartupNumerator += avgStartup * attempts;
}

for (const tier of requiredTiers) {
  if (!tierSet.has(tier)) fail(`missing device tier in report: ${tier}`);
}
for (const profile of requiredNetworks) {
  if (!networkSet.has(profile)) fail(`missing network profile in report: ${profile}`);
}

if (totalAttempts < minAttempts) {
  fail(`insufficient attempts: ${totalAttempts}, expected >= ${minAttempts}`);
}

const weightedSuccessRate = Number((weightedSuccessNumerator / totalAttempts).toFixed(2));
const weightedAvgStartupMs = Number((weightedStartupNumerator / totalAttempts).toFixed(2));

if (weightedSuccessRate < minSuccessRate) {
  fail(`weighted success rate too low: ${weightedSuccessRate}%, expected >= ${minSuccessRate}%`);
}
if (weightedAvgStartupMs > maxAvgStartupMs) {
  fail(`weighted avg startup too high: ${weightedAvgStartupMs}ms, expected <= ${maxAvgStartupMs}ms`);
}

console.log(
  `[mobile-regression-report] ok: attempts=${totalAttempts}, success=${weightedSuccessRate}%, startup=${weightedAvgStartupMs}ms`
);
