from loguru import logger
from datetime import datetime, timezone
from app.services.ssl_certbot.certbot_config import load_certbot_settings, CertbotSettings
from app.services.ssl_certbot.cert_checker import check_cert_status, CertStatus, CertInfo
from app.services.ssl_certbot.certbot_client import certbot_certonly, certbot_renew
from app.services.ssl_certbot.nginx_reloader import reload_nginx
from app.core.config import settings



_settings: CertbotSettings | None = None
_last_cert_info: CertInfo | None = None


def _get_settings() -> CertbotSettings:
    global _settings
    if _settings is None:
        _settings = load_certbot_settings()
    return _settings


async def on_startup() -> None:
    global _last_cert_info
    try:
        cfg = _get_settings()
        if not cfg.is_effective:
            if cfg.enabled and not cfg.platform_supported:
                logger.info("SSL certbot: enabled but platform not supported (non-Linux), skipping")
            elif cfg.enabled and not cfg.certbot_available:
                logger.warning("SSL certbot: enabled but certbot not installed, skipping")
            elif cfg.enabled and not cfg.domain:
                logger.warning("SSL certbot: enabled but SSL_CERTBOT_DOMAIN not set, skipping")
            return

        logger.info("SSL certbot: checking certificate for %s ...", cfg.domain)
        cert_info = await check_cert_status(cfg.cert_file_path, cfg.domain)
        _last_cert_info = cert_info

        if cert_info.status == CertStatus.MISSING:
            logger.info("SSL certbot: no certificate found, requesting via certbot certonly ...")
            rc, output = await certbot_certonly(cfg)
            if rc == 0:
                logger.info("SSL certbot: certificate obtained successfully")
                await reload_nginx(cfg)
                _last_cert_info = await check_cert_status(cfg.cert_file_path, cfg.domain)
                _last_cert_info.last_renew_at = datetime.now(timezone.utc)
            else:
                logger.error("SSL certbot: certificate request failed: %s", output[:300])

        elif cert_info.status == CertStatus.EXPIRED:
            logger.warning("SSL certbot: certificate expired, attempting renewal ...")
            rc, output = await certbot_renew(cfg)
            if rc == 0:
                logger.info("SSL certbot: certificate renewed successfully")
                await reload_nginx(cfg)
                _last_cert_info = await check_cert_status(cfg.cert_file_path, cfg.domain)
                _last_cert_info.last_renew_at = datetime.now(timezone.utc)
            else:
                logger.error("SSL certbot: certificate renewal failed: %s", output[:300])

        elif cert_info.status == CertStatus.VALID and cert_info.remaining_days <= cfg.renew_threshold_days:
            logger.info(
                "SSL certbot: certificate expires in %d days (threshold: %d), attempting renewal ...",
                cert_info.remaining_days, cfg.renew_threshold_days,
            )
            rc, output = await certbot_renew(cfg)
            if rc == 0:
                logger.info("SSL certbot: certificate renewed successfully")
                await reload_nginx(cfg)
                _last_cert_info = await check_cert_status(cfg.cert_file_path, cfg.domain)
                _last_cert_info.last_renew_at = datetime.now(timezone.utc)
            else:
                logger.error("SSL certbot: certificate renewal failed: %s", output[:300])

        elif cert_info.status == CertStatus.VALID:
            logger.info("SSL certbot: certificate valid, expires in %d days", cert_info.remaining_days)

        else:
            logger.warning("SSL certbot: unexpected cert status %s", cert_info.status)

        if getattr(settings, "ENABLE_SIPS", False):
            logger.info("SSL certbot: SIPS is enabled — if ZLM does not auto-reload the renewed cert, restart ZLM")

    except Exception as e:
        logger.error("SSL certbot: on_startup error (non-fatal): %s", e)


async def get_status() -> CertInfo:
    cfg = _get_settings()
    if not cfg.is_effective:
        return CertInfo(domain=cfg.domain, status=CertStatus.DISABLED)
    cert_info = await check_cert_status(cfg.cert_file_path, cfg.domain)
    if cert_info.status == CertStatus.VALID and cert_info.remaining_days <= cfg.renew_threshold_days:
        cert_info.status = CertStatus.EXPIRING_SOON
    return cert_info


async def force_renew() -> tuple[bool, str]:
    cfg = _get_settings()
    if not cfg.is_effective:
        return False, "SSL certbot is not enabled or not available"
    try:
        rc, output = await certbot_renew(cfg)
        if rc == 0:
            await reload_nginx(cfg)
            global _last_cert_info
            _last_cert_info = await check_cert_status(cfg.cert_file_path, cfg.domain)
            _last_cert_info.last_renew_at = datetime.now(timezone.utc)
            return True, "Certificate renewed successfully"
        return False, f"Renewal failed: {output[:200]}"
    except Exception as e:
        return False, str(e)
