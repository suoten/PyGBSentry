import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const specFile = resolve(process.cwd(), "scripts/native-player-capability.spec.json");
const reportPath = process.env.NATIVE_PLAYER_INTEGRATION_REPORT_PATH || "scripts/native-player-integration.report.json";
const reportFile = resolve(process.cwd(), reportPath);
const required = String(process.env.NATIVE_PLAYER_INTEGRATION_REQUIRED || "false").toLowerCase() === "true";

function fail(message) {
  throw new Error(`[native-player-integration] ${message}`);
}

if (!existsSync(reportFile)) {
  if (required) fail(`report file not found: ${reportPath}`);
  console.log(`[native-player-integration] skip: report not found (${reportPath}), required=false`);
  process.exit(0);
}

const spec = JSON.parse(readFileSync(specFile, "utf8"));
const report = JSON.parse(readFileSync(reportFile, "utf8"));

function checkPlatform(platform) {
  const platformSpec = spec?.platform_matrix?.[platform];
  if (!platformSpec) fail(`spec missing platform: ${platform}`);
  const row = report?.[platform];
  if (!row || typeof row !== "object") fail(`report missing platform: ${platform}`);
  if (row.bridge_injected !== true) fail(`${platform}.bridge_injected should be true`);
  if (row.is_supported !== true) fail(`${platform}.is_supported should be true`);
  const protocols = row.protocols || {};
  const requiredProtocols = Array.isArray(platformSpec.required_protocols) ? platformSpec.required_protocols : [];
  for (const p of requiredProtocols) {
    const pr = protocols[p];
    if (!pr || typeof pr !== "object") fail(`${platform}.protocols.${p} missing`);
    if (pr.passed !== true) fail(`${platform}.protocols.${p}.passed should be true`);
    const evidence = String(pr.evidence || "").trim();
    if (!evidence) fail(`${platform}.protocols.${p}.evidence missing`);
  }
}

checkPlatform("android");
checkPlatform("ios");

console.log(
  `[native-player-integration] ok: android=${spec.platform_matrix.android.required_protocols.join("|")}, ` +
    `ios=${spec.platform_matrix.ios.required_protocols.join("|")}`
);
