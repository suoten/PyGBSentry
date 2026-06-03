# cython: language_level=3
import hashlib
import json
from datetime import datetime, timezone, timedelta

cdef bint _verify_ed25519_signature(bytes payload, bytes signature, str public_key_b64):
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
        import base64
        cdef bytes pk_bytes = base64.b64decode(public_key_b64)
        cdef object verify_key = VerifyKey(pk_bytes)
        try:
            verify_key.verify(payload, signature)
            return True
        except BadSignatureError:
            return False
    except Exception:
        return False

cdef str _get_current_machine_code():
    try:
        import uuid
        import platform
        cdef long mac = uuid.getnode()
        cdef str mac_str = ":".join([("%012x" % mac)[i:i+2] for i in range(0, 12, 2)])
        cdef str hostname = platform.node()
        cdef str raw = f"{mac_str}@{hostname}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return ""

cdef str _get_current_instance_id():
    try:
        from app.core.plugin_manager import plugin_manager
        return str(plugin_manager.get_oss_instance_id() or "")
    except Exception:
        return ""

def verify_license_core(dict license_data, str tenant_id, str plugin_id,
                        str feature_code, str ed25519_public_key,
                        bint machine_code_enabled, bint activation_token_enabled,
                        int grace_period_seconds):
    cdef str signature = str(license_data.pop("signature", "") or "")
    cdef str sig_alg = str(license_data.pop("sig_alg", "ed25519")).lower()
    cdef str license_mode = str(license_data.pop("license_mode", "online")).lower()

    cdef str bound_tenant = str(license_data.get("tenant_id", "") or "")
    if bound_tenant and bound_tenant != tenant_id:
        return (False, "tenant_mismatch")

    cdef str bound_plugin = str(license_data.get("plugin_id", "") or "")
    if bound_plugin and bound_plugin != plugin_id:
        return (False, "plugin_mismatch")

    cdef list feature_codes = license_data.get("feature_codes") or []
    if isinstance(feature_codes, str):
        feature_codes = [item.strip() for item in feature_codes.split(",") if item.strip()]
    if feature_codes and feature_code not in feature_codes:
        return (False, "feature_not_licensed")

    cdef str expires_at_str = str(license_data.get("expires_at", "") or "")
    if expires_at_str:
        try:
            text = expires_at_str.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            expires_at = datetime.fromisoformat(text)
            if expires_at.tzinfo:
                expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if now > expires_at:
                if grace_period_seconds == -1:
                    pass
                elif grace_period_seconds > 0:
                    grace_deadline = expires_at + timedelta(seconds=grace_period_seconds)
                    if now > grace_deadline:
                        return (False, "license_expired")
                else:
                    return (False, "license_expired")
        except (ValueError, TypeError):
            return (False, "invalid_expires_at")

    if sig_alg != "ed25519":
        return (False, "unsupported_sig_alg")

    license_data["sig_alg"] = "ed25519"

    if machine_code_enabled and license_mode != "offline":
        cdef str lic_mc = str(license_data.get("machine_code", "") or "").strip()
        if lic_mc:
            cdef str current_mc = _get_current_machine_code()
            if not current_mc:
                return (False, "machine_code_unavailable")
            if lic_mc != current_mc:
                cdef str lic_instance_id = str(license_data.get("instance_id", "") or "").strip()
                if lic_instance_id:
                    cdef str current_iid = _get_current_instance_id()
                    if not current_iid or lic_instance_id != current_iid:
                        return (False, "machine_code_mismatch")
                else:
                    return (False, "machine_code_mismatch")

    if activation_token_enabled:
        cdef str act_token = str(license_data.get("activation_token", "") or "")
        if not act_token:
            return (False, "activation_token_missing")

    if ed25519_public_key:
        cdef bytes payload_bytes = json.dumps(license_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        import base64
        cdef bytes sig_bytes
        try:
            sig_bytes = base64.b64decode(signature)
        except Exception:
            return (False, "signature_decode_failed")
        if not _verify_ed25519_signature(payload_bytes, sig_bytes, ed25519_public_key):
            return (False, "signature_invalid")

    return (True, "ok")
