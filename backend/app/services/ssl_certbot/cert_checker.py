import os
import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from dataclasses import dataclass
from loguru import logger




class CertStatus(StrEnum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    MISSING = "missing"
    REQUEST_FAILED = "request_failed"
    CERTBOT_UNAVAILABLE = "certbot_unavailable"
    DISABLED = "disabled"


@dataclass
class CertInfo:
    domain: str = ""
    status: CertStatus = CertStatus.MISSING
    not_before: datetime | None = None
    not_after: datetime | None = None
    remaining_days: int = 0
    cert_path: str = ""
    last_renew_at: datetime | None = None
    last_check_at: datetime | None = None
    error: str = ""


async def check_cert_status(cert_file_path: str, domain: str) -> CertInfo:
    now = datetime.now(timezone.utc)
    info = CertInfo(domain=domain, cert_path=cert_file_path, last_check_at=now)

    if not os.path.isfile(cert_file_path):
        info.status = CertStatus.MISSING
        info.error = f"Certificate file not found: {cert_file_path}"
        return info

    try:
        proc = await asyncio.create_subprocess_exec(
            "openssl", "x509", "-in", cert_file_path, "-noout", "-dates", "-startdate",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0:
            info.status = CertStatus.MISSING
            info.error = f"openssl x509 failed: {stderr.decode().strip()}"
            return info

        output = stdout.decode().strip()
        not_before = None
        not_after = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("notBefore="):
                not_before = _parse_openssl_date(line.split("=", 1)[1])
            elif line.startswith("notAfter="):
                not_after = _parse_openssl_date(line.split("=", 1)[1])

        info.not_before = not_before
        info.not_after = not_after

        if not_after:
            remaining = (not_after - now).days
            info.remaining_days = remaining
            if remaining <= 0:
                info.status = CertStatus.EXPIRED
            else:
                info.status = CertStatus.VALID
        else:
            info.status = CertStatus.MISSING
            info.error = "Could not parse certificate dates"

    except asyncio.TimeoutError:
        info.status = CertStatus.REQUEST_FAILED
        info.error = "Certificate check timed out"
    except Exception as e:
        info.status = CertStatus.REQUEST_FAILED
        info.error = str(e)

    return info


def _parse_openssl_date(date_str: str) -> datetime | None:
    formats = [
        "%b %d %H:%M:%S %Y %Z",
        "%Y-%m-%d %H:%M:%S %Z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.strptime(date_str.strip(), "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("ValueError occurred")
    return None
