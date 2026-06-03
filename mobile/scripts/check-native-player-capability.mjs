import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const file = resolve(process.cwd(), "scripts/native-player-capability.spec.json");
const spec = JSON.parse(readFileSync(file, "utf8"));

function fail(message) {
  throw new Error(`[native-player-capability] ${message}`);
}

const bridgeKey = String(spec.bridge_key || "");
if (!bridgeKey) fail("bridge_key missing");
if (bridgeKey !== "__PG_BSENTRY_NATIVE_PLAYER_BRIDGE__") {
  fail(`bridge_key mismatch: ${bridgeKey}`);
}

const requiredMethods = Array.isArray(spec.required_methods) ? spec.required_methods : [];
for (const method of ["isSupported", "open"]) {
  if (!requiredMethods.includes(method)) {
    fail(`required_methods missing: ${method}`);
  }
}

const matrix = spec.platform_matrix || {};
for (const platform of ["android", "ios"]) {
  if (!matrix[platform]) fail(`platform_matrix missing: ${platform}`);
  const required = Array.isArray(matrix[platform].required_protocols) ? matrix[platform].required_protocols : [];
  if (required.length === 0) fail(`${platform}.required_protocols missing`);
}

const androidRequired = matrix.android.required_protocols || [];
const iosRequired = matrix.ios.required_protocols || [];
if (!androidRequired.includes("webrtc")) fail("android required protocol should include webrtc");
if (!androidRequired.includes("flv")) fail("android required protocol should include flv");
if (!iosRequired.includes("webrtc")) fail("ios required protocol should include webrtc");
if (!iosRequired.includes("hls")) fail("ios required protocol should include hls");

console.log(
  `[native-player-capability] ok: bridge=${bridgeKey}, ` +
    `android_required=${androidRequired.join("|")}, ios_required=${iosRequired.join("|")}`
);
