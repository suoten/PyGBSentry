"""SIP / HTTP Digest Authentication helpers (RFC 2617 / RFC 7616).

Provides :class:`DigestAuth`, a stateless utility used by both the SIP server
(register handler) and the cascade platform service (client-side register).

Supported algorithms:
    * ``MD5``        — RFC 2617 qop=auth / no-qop
    * ``MD5-sess``   — RFC 2617 session algorithm (uses cnonce to derive HA1)
    * ``SHA-256``    — RFC 7616 (preferred when the peer advertises it)

The ``response`` value is computed exactly as specified by RFC 2617 section 3.2.2:

    HA1 = MD5(username ":" realm ":" password)                 (MD5)
    HA1 = MD5(MD5(username ":" realm ":" password) ":" nonce ":" cnonce)  (MD5-sess)
    HA2 = MD5(method ":" digest-uri-value)
    qop unspecified : response = MD5(HA1 ":" nonce ":" HA2)
    qop=auth        : response = MD5(HA1 ":" nonce ":" nc ":" cnonce ":" qop ":" HA2)
    qop=auth-int    : response = MD5(HA1 ":" nonce ":" nc ":" cnonce ":" qop ":" MD5(entity-body ":" HA2))

Nonce generation signs ``timestamp:random`` with HMAC-SHA256 so the server can
verify that a returned nonce was actually issued by it (anti-replay / forgery).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from typing import Optional

from app.core.config import settings


# Hash-function registry keyed by the algorithm token as it appears on the wire.
# Values are the hashlib constructor names. ``SHA256`` and ``SHA-256`` are both
# accepted because different peers spell it differently.
_HASH_BY_ALGORITHM = {
    "MD5": "md5",
    "MD5-SESS": "md5",
    "SHA-256": "sha256",
    "SHA256": "sha256",
    "SHA-256-SESS": "sha256",
    "SHA256-SESS": "sha256",
}


def _hashfun(algorithm: str):
    """Return the hashlib constructor for an algorithm token, defaulting to MD5."""
    key = (algorithm or "MD5").strip().upper()
    name = _HASH_BY_ALGORITHM.get(key, "md5")
    return getattr(hashlib, name)


def _is_session_algorithm(algorithm: str) -> bool:
    return (algorithm or "").strip().upper().endswith("-SESS")


def _hhex(data: str, algorithm: str) -> str:
    """Hex digest of ``data`` under ``algorithm``."""
    return _hashfun(algorithm)(data.encode("utf-8")).hexdigest()


class DigestAuth:
    """Stateless Digest authentication helper used by SIP register flows."""

    # --- nonce issuance -------------------------------------------------

    @staticmethod
    def _nonce_secret() -> bytes:
        """Secret used to sign issued nonces.

        Prefers ``SIP_NONCE_SECRET`` (dedicated, lower exposure) and falls back
        to ``SECRET_KEY``. Never returns an empty bytes — callers that need to
        *verify* a nonce should check for emptiness themselves.
        """
        secret = (settings.SIP_NONCE_SECRET or "").encode("utf-8", errors="ignore")
        if not secret:
            secret = (settings.SECRET_KEY or "").encode("utf-8", errors="ignore")
        return secret

    @staticmethod
    def generate_nonce() -> str:
        """Issue a signed nonce of the form ``timestamp:random:hmac_sig``.

        The signature is ``HMAC-SHA256(secret, "timestamp:random")`` so that
        :func:`validate_nonce_signature` can later confirm the nonce was issued
        by this server and has not been tampered with.
        """
        ts = int(time.time())
        rnd = secrets.token_hex(8)  # 16 hex chars
        secret = DigestAuth._nonce_secret()
        msg = f"{ts}:{rnd}".encode("utf-8")
        sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return f"{ts}:{rnd}:{sig}"

    @staticmethod
    def validate_nonce_signature(nonce: str) -> bool:
        """Return ``True`` if the nonce was signed by this server."""
        if not nonce:
            return False
        parts = nonce.split(":")
        if len(parts) != 3:
            return False
        ts_str, rnd, sig = parts
        secret = DigestAuth._nonce_secret()
        if not secret:
            return False
        msg = f"{ts_str}:{rnd}".encode("utf-8")
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    # --- Authorization header parsing ----------------------------------

    # Matches  key="value"  as well as  key=value  (unquoted, e.g. algorithm=MD5)
    _PARAM_RE = re.compile(r'(?P<key>[a-zA-Z0-9_-]+)\s*=\s*(?:"(?P<qval>[^"]*)"|(?P<val>[^,]+))')

    @staticmethod
    def parse_auth_header(auth_header: str) -> dict:
        """Parse a ``Digest`` Authorization / WWW-Authenticate header into a dict.

        Tolerant of quoting differences and whitespace. The scheme prefix
        (``Digest`` / ``Basic``) is stripped if present. Unquoted tokens such as
        ``algorithm=MD5`` are preserved verbatim (not wrapped in quotes).
        """
        if not auth_header:
            return {}
        raw = auth_header.strip()
        # Strip leading scheme, e.g. "Digest " or "Basic "
        if raw.lower().startswith("digest"):
            raw = raw[len("digest"):].lstrip()
        elif raw.lower().startswith("basic"):
            raw = raw[len("basic"):].lstrip()

        params: dict[str, str] = {}
        for m in DigestAuth._PARAM_RE.finditer(raw):
            key = m.group("key").lower()
            value = m.group("qval")
            if value is None:
                value = (m.group("val") or "").strip()
            params[key] = value
        return params

    @staticmethod
    def select_preferred_algorithm(auth_params: dict) -> str:
        """Pick the algorithm to use for verification.

        Servers may advertise several algorithms (e.g. ``MD5, SHA-256``). We prefer
        the strongest supported one, defaulting to ``MD5`` when the peer omits the
        field (RFC 2617: "if not present, it is assumed to be MD5").

        FIX: [2026-07-21 P0] 兼容非标准 SIP 客户端（如 EasyGBS 级联）：
        EasyGBS 在 Authorization 头中声明 ``algorithm=SHA-256``，但实际用 MD5 计算
        Response（response 长度 32 = MD5 输出，而非 SHA-256 的 64 字符）。
        严格按 algorithm 字段选择 SHA-256 会导致服务器计算的 expected_response
        长度 64，永远不等于设备实际 response 长度 32，造成永久认证失败 + IP 黑名单。

        修复策略：根据 auth.response 长度自动推断实际算法：
          - response 长度 = 32  → MD5（即使 algorithm 字段声称 SHA-256）
          - response 长度 = 64  → SHA-256
          - 其他长度           → 按 algorithm 字段选择
        当 algorithm 字段与 response 长度不一致时，输出 WARNING 日志说明该设备
        使用了非标准 algorithm 声明（便于运维识别非合规客户端）。
        """
        from loguru import logger as _logger

        alg_raw = (auth_params.get("algorithm") or "MD5").strip()
        # Some servers send a comma-separated list in the algorithm field.
        candidates = [a.strip().upper() for a in alg_raw.split(",") if a.strip()]
        if not candidates:
            declared_algo = "MD5"
        else:
            preference = ("SHA-256", "SHA256", "SHA-256-SESS", "MD5-SESS", "MD5")
            declared_algo = None
            for preferred in preference:
                for c in candidates:
                    if c == preferred:
                        declared_algo = preferred
                        break
                if declared_algo:
                    break
            if not declared_algo:
                first = candidates[0]
                if first.startswith("SHA256"):
                    declared_algo = "SHA-256" if first.endswith("-SESS") else "SHA-256"
                else:
                    declared_algo = first

        # FIX: [2026-07-21 P0] 根据 response 长度自动推断实际算法
        # 优先级：response 长度（硬证据） > algorithm 字段（声明）
        actual_response = (auth_params.get("response") or "").strip()
        if actual_response:
            resp_len = len(actual_response)
            if resp_len == 32:
                # 32 字符是 MD5 输出长度
                if declared_algo.upper() not in ("MD5", "MD5-SESS"):
                    _logger.warning(
                        f"[AUTH_ALGORITHM_MISMATCH] Device declares algorithm={declared_algo!r} "
                        f"but response length={resp_len} indicates MD5. "
                        f"This is a non-RFC-compliant SIP client (common with EasyGBS / similar "
                        f"cascade platforms) that misreports algorithm in Authorization header. "
                        f"Server will use MD5 for verification (based on response length). "
                        f"auth.username={auth_params.get('username')!r}"
                    )
                return "MD5"
            if resp_len == 64:
                # 64 字符是 SHA-256 输出长度
                if declared_algo.upper() not in ("SHA-256", "SHA256", "SHA-256-SESS", "SHA256-SESS"):
                    _logger.warning(
                        f"[AUTH_ALGORITHM_MISMATCH] Device declares algorithm={declared_algo!r} "
                        f"but response length={resp_len} indicates SHA-256. "
                        f"Server will use SHA-256 for verification (based on response length). "
                        f"auth.username={auth_params.get('username')!r}"
                    )
                return "SHA-256"
            # 其他长度：按 algorithm 字段选择（向后兼容）

        return declared_algo

    # --- response calculation (RFC 2617 §3.2.2) ------------------------

    @staticmethod
    def calculate_response(
        *,
        username: Optional[str],
        password: Optional[str],
        realm: Optional[str],
        method: str,
        uri: Optional[str],
        nonce: Optional[str],
        nc: Optional[str] = None,
        cnonce: Optional[str] = None,
        qop: Optional[str] = None,
        algorithm: str = "MD5",
        entity_body: str = "",
    ) -> str:
        """Compute the Digest ``response`` value per RFC 2617.

        Parameters mirror the fields of a Digest Authorization header. ``nc`` is
        the hex nonce-count string (e.g. ``"00000001"``); ``qop`` is the quality
        of protection actually used (``"auth"`` or ``"auth-int"``). When ``qop``
        is empty/None the legacy (no-qop) formula is used.
        """
        algorithm = (algorithm or "MD5").strip().upper()
        # Normalise SHA256 spelling so _HASH_BY_ALGORITHM resolves it.
        if algorithm == "SHA256":
            algorithm = "SHA-256"
        elif algorithm == "SHA256-SESS":
            algorithm = "SHA-256-SESS"

        username = username or ""
        password = password or ""
        realm = realm or ""
        uri = uri or ""
        nonce = nonce or ""
        qop = (qop or "").strip().lower()

        # HA1
        a1 = f"{username}:{realm}:{password}"
        ha1 = _hhex(a1, algorithm)
        if _is_session_algorithm(algorithm):
            # MD5-sess / SHA-256-sess: HA1 = H( H(a1) ":" nonce ":" cnonce )
            cnonce = cnonce or ""
            ha1 = _hhex(f"{ha1}:{nonce}:{cnonce}", algorithm)

        # HA2
        if qop == "auth-int":
            entity_hash = _hhex(entity_body or "", algorithm)
            a2 = f"{method}:{uri}:{entity_hash}"
        else:
            a2 = f"{method}:{uri}"
        ha2 = _hhex(a2, algorithm)

        # response
        if qop in ("auth", "auth-int"):
            nc = nc or "00000001"
            cnonce = cnonce or ""
            response = _hhex(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}", algorithm)
        else:
            response = _hhex(f"{ha1}:{nonce}:{ha2}", algorithm)
        return response

    # --- WWW-Authenticate challenge building ----------------------------

    @staticmethod
    def build_challenge(
        *,
        realm: Optional[str] = None,
        algorithm: str = "MD5",
        qop: str = "auth,auth-int",
        stale: bool = False,
        opaque: Optional[str] = None,
    ) -> str:
        """Build a ``WWW-Authenticate: Digest ...`` challenge string.

        Used by the SIP server when sending a 401 response to invite the client
        to authenticate. ``stale=True`` signals that the previous nonce expired
        and the client may retry with the same credentials and the new nonce.

        P1-fix [2026-07-17]: 默认 qop 改为 "auth,auth-int"，与 _send_register_401
        实际使用的 qop 保持一致。原默认 "auth" 会导致通过 build_challenge 生成的
        challenge 不会通告 auth-int，与 _send_register_401 行为分歧，未来调用方
        可能误用较弱 qop。
        """
        # P1-fix [2026-07-17]: realm 解析顺序与 _send_register_401 保持一致
        # （SIP_REALM > SIP_DOMAIN > PROJECT_NAME > "PyGBSentry"），避免 challenge
        # 与 verify 之间 realm 不匹配导致永远认证失败。
        realm = realm or (
            settings.SIP_REALM
            or settings.SIP_DOMAIN
            or settings.PROJECT_NAME
            or "PyGBSentry"
        )
        nonce = DigestAuth.generate_nonce()
        parts = [
            f'realm="{realm}"',
            f'nonce="{nonce}"',
            f"algorithm={algorithm}",
        ]
        if qop:
            parts.append(f"qop=\"{qop}\"")
        if opaque:
            parts.append(f'opaque="{opaque}"')
        if stale:
            parts.append("stale=true")
        return "Digest " + ", ".join(parts)
