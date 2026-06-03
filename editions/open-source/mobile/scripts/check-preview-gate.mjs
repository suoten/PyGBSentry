import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const file = resolve(process.cwd(), "src/pages/preview/index.vue");
const text = readFileSync(file, "utf8");

function mustMatch(regex, label) {
  const m = text.match(regex);
  if (!m) {
    throw new Error(`missing ${label}`);
  }
  return m;
}

const successRateMatch = mustMatch(
  /const\s+PREVIEW_GATE_MIN_SUCCESS_RATE\s*=\s*(\d+(?:\.\d+)?)\s*;/,
  "PREVIEW_GATE_MIN_SUCCESS_RATE"
);
const startupMsMatch = mustMatch(
  /const\s+PREVIEW_GATE_MAX_AVG_STARTUP_MS\s*=\s*(\d+(?:\.\d+)?)\s*;/,
  "PREVIEW_GATE_MAX_AVG_STARTUP_MS"
);

const successRate = Number(successRateMatch[1]);
const startupMs = Number(startupMsMatch[1]);

if (Number.isNaN(successRate) || Number.isNaN(startupMs)) {
  throw new Error("preview gate thresholds are not numbers");
}

// Guardrail: prevent lowering quality bar accidentally.
if (successRate < 80) {
  throw new Error(`PREVIEW_GATE_MIN_SUCCESS_RATE too low: ${successRate} (expected >= 80)`);
}

if (startupMs > 4500) {
  throw new Error(`PREVIEW_GATE_MAX_AVG_STARTUP_MS too high: ${startupMs} (expected <= 4500)`);
}

if (!text.includes("previewPerfGate")) {
  throw new Error("previewPerfGate computed block missing");
}

console.log(
  `[preview-gate] ok: min_success_rate=${successRate}% max_avg_startup_ms=${startupMs}ms`
);
