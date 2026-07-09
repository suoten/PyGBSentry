"""License verification and machine-code generation (OSS edition).

Provides Ed25519 license-payload verification for paid plugins and a machine
fingerprint generator used for OSS↔marketplace instance registration. All
settings access is ``getattr``-safe so the module imports cleanly even when
license-related config keys are absent (the OSS default).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import platform
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

import logging

_logger = logging.getLogger(__name__)

# Clock-rollback detection state for offline license verification.
_last_verify_timestamps: dict[str, dict[str, float]] = {}
_LAST_VERIFY_TIMESTAMPS_MAX_SIZE = 10000


def _canonical_payload(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def _compute_signature(data: dict[str, Any], secret: str) -> str:
    payload = _canonical_payload(data)
    return hashlib.sha256(f"{payload}.{secret}".encode("utf-8")).hexdigest()


def verify_signed_payload(data: dict[str, Any], signature: str, secret: str | None) -> bool:
    if not secret or not signature:
        return False
    expected = _compute_signature(data, secret)
    return hmac.compare_digest(signature, expected)


def verify_ed25519_signature(data: dict[str, Any], signature: str, public_key_pem: str | None) -> bool:
    if not signature or not public_key_pem:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(_b64url_decode(signature), _canonical_payload(data).encode("utf-8"))
        return True
    except Exception as exc:
        _logger.debug("Ed25519 verify failed: %s: %s", type(exc).__name__, str(exc)[:200])
        return False


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _trim_verify_timestamps() -> None:
    if len(_last_verify_timestamps) <= _LAST_VERIFY_TIMESTAMPS_MAX_SIZE:
        return
    sorted_keys = sorted(
        _last_verify_timestamps.keys(),
        key=lambda k: _last_verify_timestamps[k].get("wall", 0),
    )
    for k in sorted_keys[: len(sorted_keys) // 2]:
        del _last_verify_timestamps[k]


def verify_license_payload(
    license_data: dict[str, Any],
    tenant_id: str,
    plugin_id: str,
    feature_code: str,
    machine_code: str | None = None,
    token_status_check: str | None = None,
    keyring: dict | None = None,
) -> tuple[bool, str]:
    """Verify a license payload's signature, binding and expiry.

    Returns ``(valid, reason)``. ``reason`` is ``"ok"`` on success.
    """
    payload = dict(license_data)
    signature = str(payload.pop("signature", "") or "")
    sig_alg = str(payload.get("sig_alg", "ed25519")).lower()
    mode = str(payload.get("license_mode", "online")).lower()
    bound_tenant = str(payload.get("tenant_id", "") or "")
    bound_plugin = str(payload.get("plugin_id", "") or "")
    bound_machine_code = str(payload.get("machine_code", "") or "").strip() or None
    feature_codes = payload.get("feature_codes") or []
    if isinstance(feature_codes, str):
        feature_codes = [item.strip() for item in feature_codes.split(",") if item.strip()]
    expires_at = parse_iso_datetime(payload.get("expires_at"))
    now = datetime.now(timezone.utc)

    activation_token_enabled = bool(getattr(settings, "PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED", False))
    license_token = str(payload.get("activation_token") or "").strip()
    if activation_token_enabled and license_token and token_status_check == "used":
        return False, "activation_token_used"

    if bound_tenant and bound_tenant != tenant_id:
        return False, "tenant_mismatch"
    if bound_plugin and bound_plugin != plugin_id:
        return False, "plugin_mismatch"
    machine_code_enabled = bool(getattr(settings, "PLUGIN_LICENSE_MACHINE_CODE_ENABLED", False))
    if machine_code_enabled and mode != "offline" and bound_machine_code and machine_code:
        if bound_machine_code != machine_code:
            return False, "machine_code_mismatch"
    if feature_code:
        if not feature_codes or feature_code not in feature_codes:
            return False, "feature_not_licensed"
    if expires_at and now > expires_at:
        return False, "license_expired"
    if sig_alg != "ed25519":
        return False, "unsupported_sig_alg"
    payload["sig_alg"] = "ed25519"

    if mode == "offline":
        license_hash = hashlib.sha256(_canonical_payload(payload).encode("utf-8")).hexdigest()
        mono_now = time.monotonic()
        wall_now = time.time()
        prev = _last_verify_timestamps.get(license_hash)
        if prev:
            mono_delta = mono_now - prev["mono"]
            wall_delta = wall_now - prev["wall"]
            if mono_delta > 1.0 and wall_delta < -0.5:
                return False, "clock_rollback_detected"
        _last_verify_timestamps[license_hash] = {"mono": mono_now, "wall": wall_now}
        _trim_verify_timestamps()

    def _retired_public_keys(kr: dict | None) -> list[str]:
        if not kr or not isinstance(kr.get("keys"), dict):
            return []
        out: list[str] = []
        for item in kr["keys"].values():
            if isinstance(item, dict) and str(item.get("status") or "").strip() == "retired":
                pub = str(item.get("public_key_pem") or "").strip()
                if pub:
                    out.append(pub)
        return out

    if mode == "offline":
        verify_key = getattr(settings, "LICENSE_OFFLINE_PUBLIC_KEY", None) or getattr(settings, "LICENSE_ED25519_PUBLIC_KEY", None)
        if getattr(settings, "ENTERPRISE_OFFLINE_LICENSE_REQUIRED", False) and not verify_key:
            return False, "offline_public_key_missing"
        if not verify_key:
            return False, "offline_public_key_missing"
        if not verify_ed25519_signature(payload, signature, verify_key):
            if not any(verify_ed25519_signature(payload, signature, rk) for rk in _retired_public_keys(keyring)):
                return False, "offline_signature_invalid"
        return True, "ok"

    verify_key = getattr(settings, "LICENSE_ED25519_PUBLIC_KEY", None)
    if verify_key and not verify_ed25519_signature(payload, signature, verify_key):
        if not any(verify_ed25519_signature(payload, signature, rk) for rk in _retired_public_keys(keyring)):
            return False, "signature_invalid"
    if not verify_key:
        return False, "public_key_missing"
    return True, "ok"


def _get_current_machine_code() -> str:
    """Generate a stable machine fingerprint for this host.

    Combines platform metadata and (where available) a hardware UUID to
    produce a deterministic SHA256 digest. Used for OSS↔marketplace instance
    registration and machine-bound licensing.
    """
    parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        platform.system(),
        platform.release(),
    ]
    # Best-effort hardware UUID.
    for getter in (_uuid_from_wmic, _uuid_from_macos, _uuid_from_dmi):
        try:
            hw = getter()
            if hw:
                parts.append(hw)
                break
        except Exception:
            continue
    raw = "|".join(str(p) for p in parts if p)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _uuid_from_wmic() -> str | None:
    import shutil
    import subprocess
    if not shutil.which("wmic"):
        return None
    out = subprocess.run(
        ["wmic", "csproduct", "get", "UUID"],
        capture_output=True, text=True, timeout=10,
    )
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if line and line.lower() not in ("uuid",) and "-" in line:
            return line
    return None


def _uuid_from_macos() -> str | None:
    import shutil
    import subprocess
    if not shutil.which("ioreg"):
        return None
    out = subprocess.run(
        ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
        capture_output=True, text=True, timeout=10,
    )
    for line in (out.stdout or "").splitlines():
        if "IOPlatformUUID" in line:
            return line.split('"')[-2] if '"' in line else ""
    return None


def _uuid_from_dmi() -> str | None:
    try:
        with open("/sys/class/dmi/id/product_uuid", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def plugin_manifest_signing_public_key_pem() -> str:
    m = (getattr(settings, "PLUGIN_MANIFEST_ED25519_PUBLIC_KEY", None) or "").strip()
    if m:
        return m
    return (getattr(settings, "LICENSE_ED25519_PUBLIC_KEY", None) or "").strip()


def manifest_signature_install_error(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    pub = plugin_manifest_signing_public_key_pem()
    req = bool(getattr(settings, "PLUGIN_MANIFEST_SIGNATURE_REQUIRED", False))
    sig = str(metadata.get("manifest_signature") or "").strip()
    if req and not sig:
        return "plugin.json missing manifest_signature"
    if not sig:
        return None
    if not pub:
        return "manifest signature present but no public key configured"
    if str(metadata.get("manifest_sig_alg") or "ed25519").lower() != "ed25519":
        return "unsupported manifest_sig_alg"
    payload = {k: v for k, v in metadata.items() if k != "manifest_signature"}
    if not verify_ed25519_signature(payload, sig, pub):
        return "invalid manifest signature"
    return None
