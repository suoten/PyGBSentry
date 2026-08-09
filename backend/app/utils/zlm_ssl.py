"""ZLMediaKit 合并 PEM 校验与组装（与官方文档：私钥 + 证书链 拼接一致）。"""

from __future__ import annotations


def _strip_pem(s: str) -> str:
    return (s or "").strip()


def validate_and_merge_ssl_pem(
    *,
    merged_pem: str | None = None,
    cert_pem: str | None = None,
    key_pem: str | None = None,
) -> str:
    """
    返回合并后的 PEM 文本（UTF-8）。
    优先使用 merged_pem；否则用 key_pem + cert_pem 按 ZLM 推荐顺序拼接。
    """
    m = _strip_pem(merged_pem or "")
    if m:
        if "BEGIN" not in m or "END" not in m:
            raise ValueError("Invalid merged PEM format: BEGIN/END markers required")  # i18n
        if "PRIVATE KEY" not in m and "RSA PRIVATE KEY" not in m:
            raise ValueError("No private key block (PRIVATE KEY) detected in merged PEM")  # i18n
        if "CERTIFICATE" not in m:
            raise ValueError("No certificate block (CERTIFICATE) detected in merged PEM")  # i18n
        return m + "\n"

    c = _strip_pem(cert_pem or "")
    k = _strip_pem(key_pem or "")
    if not c and not k:
        raise ValueError("Provide 'merged PEM' or both 'cert chain PEM' and 'private key PEM'")  # i18n
    if not c or not k:
        raise ValueError("Cert chain and private key must both be provided, or use 'merged PEM'")  # i18n
    if "BEGIN" not in c or "CERTIFICATE" not in c:
        raise ValueError("Invalid cert chain PEM format")  # i18n
    if "BEGIN" not in k or ("PRIVATE KEY" not in k and "RSA PRIVATE KEY" not in k):
        raise ValueError("Invalid private key PEM format")  # i18n
    return k.rstrip() + "\n" + c.rstrip() + "\n"
