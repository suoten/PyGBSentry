import hashlib
import hmac
import json
import datetime
import base64
from loguru import logger
from typing import Any
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from app.core.config import settings



try:
    from app.core._license_native import verify_license_core as _native_verify_license_core
    USE_NATIVE_VERIFY = True
except ImportError:
    USE_NATIVE_VERIFY = False

def _canonical_payload(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _compute_signature(data: dict[str, Any], secret: str) -> str:
    payload = _canonical_payload(data)
    return hashlib.sha256(f"{payload}.{secret}".encode("utf-8")).hexdigest()

def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")

def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))

def verify_signed_payload(data: dict[str, Any], signature: str, secret: str | None) -> bool:
    if not secret or not signature:
        return False
    expected = _compute_signature(data, secret)
    return hmac.compare_digest(signature, expected)

def _load_private_key(pem_text: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem_text.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("invalid_private_key_type")
    return key

def _load_public_key(pem_text: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem_text.encode("utf-8"))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("invalid_public_key_type")
    return key

def verify_ed25519_signature(data: dict[str, Any], signature: str, public_key_pem: str | None) -> bool:
    if not signature or not public_key_pem:
        return False
    try:
        public_key = _load_public_key(public_key_pem)
        public_key.verify(_b64url_decode(signature), _canonical_payload(data).encode("utf-8"))
        return True
    except Exception:
        return False

def sign_license_payload(license_data: dict[str, Any], private_key_pem: str | None) -> dict[str, Any]:
    if not private_key_pem:
        raise ValueError("missing_private_key")
    private_key = _load_private_key(private_key_pem)
    payload = dict(license_data)
    payload.pop("signature", None)
    payload["sig_alg"] = "ed25519"
    signature = private_key.sign(_canonical_payload(payload).encode("utf-8"))
    payload["signature"] = _b64url_encode(signature)
    return payload

def generate_ed25519_keypair() -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return {"private_key_pem": private_pem, "public_key_pem": public_pem}

def parse_iso_datetime(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(text)
        if dt.tzinfo:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None

def _get_current_machine_code() -> str:
    """获取当前机器码，基于主机的 MAC 地址和主机名生成。"""
    import platform
    import uuid

    try:
        mac = uuid.getnode()
        mac_str = ":".join( [("%012x" % mac)[i : i + 2] for i in range(0, 12, 2)])
        hostname = platform.node()
        raw = f"{mac_str}@{hostname}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def verify_license_payload(
    license_data: dict[str, Any],
    tenant_id: str,
    plugin_id: str,
    feature_code: str,
) -> tuple[bool, str]:
    if USE_NATIVE_VERIFY:
        try:
            return _native_verify_license_core(
                license_data=dict(license_data),
                tenant_id=tenant_id,
                plugin_id=plugin_id,
                feature_code=feature_code,
                ed25519_public_key=settings.LICENSE_ED25519_PUBLIC_KEY or "",
                machine_code_enabled=bool(getattr(settings, "PLUGIN_LICENSE_MACHINE_CODE_ENABLED", False)),
                activation_token_enabled=bool(getattr(settings, "PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED", False)),
                grace_period_seconds=int(getattr(settings, "PLUGIN_LICENSE_OFFLINE_GRACE_PERIOD_SECONDS", 86400) or 0),
            )
        except Exception as e:
            logger.warning("Native license verify failed, falling back to Python: %s", e)
    return _verify_license_payload_python(license_data, tenant_id, plugin_id, feature_code)


def _verify_license_payload_python(
    license_data: dict[str, Any],
    tenant_id: str,
    plugin_id: str,
    feature_code: str,
) -> tuple[bool, str]:
    payload = dict(license_data)
    signature = str(payload.pop("signature", "") or "")
    sig_alg = str(payload.get("sig_alg", "ed25519")).lower()
    mode = str(payload.get("license_mode", "online")).lower()
    bound_tenant = str(payload.get("tenant_id", "") or "")
    bound_plugin = str(payload.get("plugin_id", "") or "")
    feature_codes = payload.get("feature_codes") or []
    if isinstance(feature_codes, str):
        feature_codes = [item.strip() for item in feature_codes.split(",") if item.strip()]
    expires_at = parse_iso_datetime(payload.get("expires_at"))
    now = datetime.datetime.now(datetime.timezone.utc) # FIXED: utcnow() deprecated in Python 3.12+
    if bound_tenant and bound_tenant != tenant_id:
        return False, "tenant_mismatch"
    if bound_plugin and bound_plugin != plugin_id:
        return False, "plugin_mismatch"
    if feature_codes and feature_code not in feature_codes:
        return False, "feature_not_licensed"
    if expires_at and now > expires_at:
        grace_seconds = int(getattr(settings, "PLUGIN_LICENSE_OFFLINE_GRACE_PERIOD_SECONDS", 86400) or 0)
        if grace_seconds == -1:
            return True, "ok_grace_period_unlimited"
        if grace_seconds > 0:
            grace_deadline = expires_at + datetime.timedelta(seconds=grace_seconds)
            if now <= grace_deadline:
                return True, "ok_grace_period"
        return False, "license_expired"
    if sig_alg != "ed25519":
        return False, "unsupported_sig_alg"
    payload["sig_alg"] = "ed25519"
    if getattr(settings, "PLUGIN_LICENSE_MACHINE_CODE_ENABLED", False):
        license_machine_code = str(payload.get("machine_code", "") or "").strip()
        if license_machine_code:
            current_machine_code = _get_current_machine_code()
            if not current_machine_code:
                logger.warning("[License] 无法获取当前机器码，拒绝授权验证（fail-close）")
                return False, "machine_code_unavailable"
            if license_machine_code != current_machine_code:
                instance_id = str(payload.get("instance_id", "") or "").strip()
                if instance_id:
                    try:
                        from app.core.plugin_manager import plugin_manager
                        current_instance_id = str(plugin_manager.get_oss_instance_id() or "")
                    except Exception:
                        current_instance_id = ""
                    if not current_instance_id:
                        logger.warning("[License] instance_id 回退校验失败：当前实例未注册，拒绝授权")
                        return False, "machine_code_mismatch"
                    if instance_id != current_instance_id:
                        logger.warning("[License] instance_id 不匹配: license=%s, current=%s", instance_id[:8], current_instance_id[:8])
                        return False, "machine_code_mismatch"
                    logger.info("[License] 机器码不匹配但 instance_id 一致，允许授权")
                else:
                    return False, "machine_code_mismatch"
    if getattr(settings, "PLUGIN_LICENSE_ACTIVATION_TOKEN_ENABLED", False):
        activation_token = str(payload.get("activation_token", "") or "")
        if not activation_token:
            logger.warning("许可证缺少 activation_token，激活令牌校验未通过")
            return False, "activation_token_missing"
    if mode == "offline":
        verify_key = settings.LICENSE_OFFLINE_PUBLIC_KEY or settings.LICENSE_ED25519_PUBLIC_KEY
        if settings.ENTERPRISE_OFFLINE_LICENSE_REQUIRED and not verify_key:
            return False, "offline_public_key_missing"
        if verify_key and not verify_ed25519_signature(payload, signature, verify_key):
            return False, "offline_signature_invalid"
        if not verify_key and not verify_signed_payload(payload, signature, settings.LICENSE_SIGNING_SECRET or settings.SECRET_KEY):
            return False, "offline_signature_invalid"
        return True, "ok"
    verify_key = settings.LICENSE_ED25519_PUBLIC_KEY
    if verify_key and not verify_ed25519_signature(payload, signature, verify_key):
        return False, "signature_invalid"
    if not verify_key and not verify_signed_payload(payload, signature, settings.LICENSE_SIGNING_SECRET or settings.SECRET_KEY):
        return False, "signature_invalid"
    return True, "ok"


def plugin_manifest_signing_public_key_pem() -> str:
    """校验 plugin.json 时优先使用专用公钥，否则回退许可证公钥。"""
    m = (getattr(settings, "PLUGIN_MANIFEST_ED25519_PUBLIC_KEY", None) or "").strip()
    if m:
        return m
    return (getattr(settings, "LICENSE_ED25519_PUBLIC_KEY", None) or "").strip()


def manifest_signature_install_error(metadata: dict[str, Any] | None) -> str | None:
    """
    安装前校验 plugin.json 可选字段 manifest_signature（Ed25519，与 license 同源算法）。
    - PLUGIN_MANIFEST_SIGNATURE_REQUIRED=true 时必须带有效签名。
    - 若存在 manifest_signature 则必须配置公钥且验签通过。
    返回 None 表示通过；否则为错误文案。
    """
    if not isinstance(metadata, dict):
        return None
    pub = plugin_manifest_signing_public_key_pem()
    req = bool(getattr(settings, "PLUGIN_MANIFEST_SIGNATURE_REQUIRED", False))
    sig = str(metadata.get("manifest_signature") or "").strip()
    if req and not sig:
        return "plugin.json 缺少 manifest_signature（已开启 PLUGIN_MANIFEST_SIGNATURE_REQUIRED）"
    if not sig:
        return None
    if not pub:
        return "plugin.json 含 manifest_signature 但未配置 PLUGIN_MANIFEST_ED25519_PUBLIC_KEY（或 LICENSE_ED25519_PUBLIC_KEY）"
    sig_alg = str(metadata.get("manifest_sig_alg") or "ed25519").lower()
    if sig_alg != "ed25519":
        return "不支持的 manifest_sig_alg（仅支持 ed25519）"
    payload = {k: v for k, v in metadata.items() if k != "manifest_signature"}
    if not verify_ed25519_signature(payload, sig, pub):
        return "plugin.json manifest 签名无效"
    return None


def sign_plugin_manifest_payload(metadata: dict[str, Any], private_key_pem: str | None) -> dict[str, Any]:
    """
    为 plugin.json 对象生成 manifest_signature（供平台/作者离线签名后写入包内）。
    签名覆盖除 manifest_signature 外的全部字段（canonical JSON）。
    """
    if not private_key_pem:
        raise ValueError("missing_private_key")
    private_key = _load_private_key(private_key_pem)
    base = dict(metadata)
    base.pop("manifest_signature", None)
    if "manifest_sig_alg" not in base:
        base["manifest_sig_alg"] = "ed25519"
    signature = private_key.sign(_canonical_payload(base).encode("utf-8"))
    out = dict(base)
    out["manifest_signature"] = _b64url_encode(signature)
    return out
